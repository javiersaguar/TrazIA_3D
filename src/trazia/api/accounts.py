"""Acceso a TrazIA con sesiones revocables y permisos comprobados en la API."""

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, update
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders

from trazia.store.accounts import Account, AccountSession

ADMINS = ("javier.saguar", "iria.lozano", "miguel.vera", "alejandro.cuevas")
NAMES = {
    "javier.saguar": "Javier Saguar",
    "iria.lozano": "Iria Lozano",
    "miguel.vera": "Miguel Vera",
    "alejandro.cuevas": "Alejandro Cuevas",
    "revisor": "Revisor de TR",
}
GUEST = "invitado"
LOGIN_ROLES = ("admin", "usuario")
LOCAL_OWNER = "javier.saguar"
ADMIN_ONLY = "/admin"
AVATAR_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_AVATAR = 1024 * 1024
AVATAR = re.compile(r"/auth/avatar/[a-z0-9._-]{1,80}")
TEAM_PHOTOS = Path(__file__).with_name("equipo")
SESSION_COOKIE = "trazia_session"
SESSION_SECONDS = 12 * 60 * 60
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def request_username(request: Request) -> str | None:
    return getattr(getattr(request.state, "account", None), "username", None)


PUBLIC = {("GET", "/health"), ("HEAD", "/health"), ("POST", "/auth/login"), ("POST", "/auth/guest")}
READ_ONLY_METHODS = {"GET", "HEAD"}
CATALOGUE_FILE = re.compile(r"/catalogue/designs/[0-9a-f-]{36}/file")
router = APIRouter()


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024**2)


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{_derive(password, salt).hex()}"


def _bootstrap_password() -> str:
    filename = os.getenv("TRAZIA_ADMIN_PASSWORD_FILE")
    if filename:
        try:
            password = Path(filename).read_text(encoding="utf-8-sig").rstrip("\r\n")
        except (OSError, UnicodeError):
            raise RuntimeError("No se pudo leer el archivo de contraseña de TrazIA.") from None
    else:
        password = os.getenv("TRAZIA_ADMIN_PASSWORD", "")
    if not 8 <= len(password) <= 256:
        raise RuntimeError("Configura una contraseña de administrador de 8 a 256 caracteres.")
    return password


def _users() -> tuple[str, ...]:
    """Usuarios habituales: `TRAZIA_USUARIOS` (separados por comas), por defecto `revisor`."""
    raw = os.getenv("TRAZIA_USUARIOS", "revisor")
    return tuple(u.strip().lower() for u in raw.split(",") if u.strip() and u.strip() not in ADMINS)


def seed_accounts(store) -> None:
    with Session(store.engine) as db:
        wanted = [(user, "admin") for user in ADMINS] + [(user, "usuario") for user in _users()]
        missing = [(user, role) for user, role in wanted if db.get(Account, user) is None]
        if missing:
            password = _bootstrap_password()
            for user, role in missing:
                db.add(Account(username=user, role=role, password_hash=_password_hash(password)))
        if db.get(Account, GUEST) is None:
            db.add(Account(username=GUEST, role="guest"))
        db.commit()


def sync_local_owner_password(store) -> bool:
    """Sincroniza la cuenta de la vista previa con su archivo de contraseña configurado."""
    password = _bootstrap_password()
    with Session(store.engine) as db:
        account = db.get(Account, LOCAL_OWNER)
        if not account or account.role != "admin" or not account.password_hash:
            raise RuntimeError("La cuenta administradora de la vista previa no está preparada.")
        salt, expected = account.password_hash.split(":")
        if hmac.compare_digest(_derive(password, bytes.fromhex(salt)), bytes.fromhex(expected)):
            return False
        account.password_hash = _password_hash(password)
        db.add(account)
        db.execute(delete(AccountSession).where(AccountSession.username == account.username))
        db.commit()
        return True


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class SignedInAccount:
    username: str
    role: str
    can_switch_role: bool


def _signed_in(account: Account, viewing_role: str | None = None) -> SignedInAccount:
    can_switch = account.username in ADMINS and account.role == "admin"
    role = "usuario" if can_switch and viewing_role == "usuario" else account.role
    return SignedInAccount(account.username, role, can_switch)


def _find_account(store, token: str | None) -> SignedInAccount | None:
    if token is None or not TOKEN.fullmatch(token):
        return None
    with Session(store.engine) as db:
        session = db.get(AccountSession, _digest(token))
        if session and session.expires_at > time.time():
            account = db.get(Account, session.username)
            if account:
                return _signed_in(account, session.viewing_role)
    return None


class LoginRate:
    """Límites separados para autenticación con contraseña y entrada de invitados."""

    def __init__(self):
        self.lock = Lock()
        self.attempts = {kind: deque() for kind in ("admin", "guest")}
        self.hash_slots = BoundedSemaphore(4)

    def check(self, request: Request, kind: str) -> None:
        address = request.client.host if request.client else ""
        limit = 16 if kind == "admin" else 90
        now = time.monotonic()
        with self.lock:
            attempts = self.attempts[kind]
            while attempts and attempts[0][0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= 600 or sum(ip == address for _, ip in attempts) >= limit:
                raise HTTPException(
                    429,
                    "Demasiados intentos. Vuelve a probar en un minuto.",
                    headers={"Retry-After": "60"},
                )
            attempts.append((now, address))


class AccountAccess:
    def __init__(self, app, allowed_origins: list[str]):
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        method = request.method
        path = scope["path"]
        if method not in READ_ONLY_METHODS | {"OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in self.allowed_origins:
                return await JSONResponse(
                    {"detail": "Origen de la petición no permitido."}, status_code=403
                )(scope, receive, send)
        if method == "OPTIONS" or (method, path) in PUBLIC:
            return await self.app(scope, receive, send)
        account = await run_in_threadpool(
            _find_account, request.app.state.store, request.cookies.get(SESSION_COOKIE)
        )
        if account is None:
            return await JSONResponse({"detail": "Inicia sesión para acceder."}, status_code=401)(
                scope, receive, send
            )
        if account.role == "usuario":
            if path == ADMIN_ONLY or path.startswith(ADMIN_ONLY + "/"):
                return await JSONResponse(
                    {"detail": "Esta sección es solo para administradores."}, status_code=403
                )(scope, receive, send)
        elif account.role != "admin" and not (
            (method, path) == ("POST", "/auth/logout")
            or method in READ_ONLY_METHODS
            and (
                path in ("/auth/session", "/catalogue")
                or CATALOGUE_FILE.fullmatch(path)
                or AVATAR.fullmatch(path)
            )
        ):
            return await JSONResponse(
                {"detail": "El acceso de invitado es de solo lectura."}, status_code=403
            )(scope, receive, send)
        request.state.account = account

        async def uncached(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "private, no-store"
            await send(message)

        return await self.app(scope, receive, uncached)


def _avatar_path(store, username: str) -> Path | None:
    """Foto subida por la cuenta; si no hay, la del equipo que viene con la plataforma."""
    for folder in (Path(store.root) / "avatars", TEAM_PHOTOS):
        for extension in AVATAR_TYPES.values():
            candidate = folder / f"{username}.{extension}"
            if candidate.is_file():
                return candidate
    return None


def _profile(store, username: str) -> dict[str, str | None]:
    avatar = _avatar_path(store, username)
    return {
        "username": username,
        "name": NAMES.get(username, username),
        "avatar": f"/auth/avatar/{username}?v={avatar.stat().st_mtime_ns}" if avatar else None,
    }


def _identity(account: SignedInAccount, store) -> dict:
    return {
        **_profile(store, account.username),
        "role": account.role,
        "can_switch_role": account.can_switch_role,
        "team": [_profile(store, username) for username in ADMINS]
        if account.can_switch_role
        else [],
        # Fotos de quien firma cambios y versiones: cualquier sesión las ve junto al autor.
        "profiles": [_profile(store, username) for username in NAMES],
    }


def _cookie_secure() -> bool:
    return os.getenv("TRAZIA_AUTH_COOKIE_SECURE", "1") != "0"


def _start_session(request: Request, account: Account) -> Response:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with Session(request.app.state.store.engine) as db:
        db.execute(delete(AccountSession).where(AccountSession.expires_at <= now))
        previous = request.cookies.get(SESSION_COOKIE)
        if previous and TOKEN.fullmatch(previous):
            existing = db.get(AccountSession, _digest(previous))
            if existing:
                db.delete(existing)
        db.add(
            AccountSession(
                digest=_digest(token), username=account.username, expires_at=now + SESSION_SECONDS
            )
        )
        db.commit()
    response = JSONResponse(
        _identity(_signed_in(account), request.app.state.store),
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_SECONDS,
        path="/",
        secure=_cookie_secure(),
        httponly=True,
        samesite="strict",
    )
    return response


class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)


@router.post("/auth/login")
def login(request: Request, body: Login):
    limiter = request.app.state.login_rate
    limiter.check(request, "admin")
    with Session(request.app.state.store.engine) as db:
        account = db.get(Account, body.username.strip().lower())
    valid_role = account is not None and account.role in LOGIN_ROLES and account.password_hash
    salt, expected = account.password_hash.split(":") if valid_role else ("00" * 16, "00" * 64)
    if not limiter.hash_slots.acquire(blocking=False):
        raise HTTPException(429, "Hay varios accesos en curso. Vuelve a probar en unos segundos.")
    try:
        valid_password = hmac.compare_digest(
            _derive(body.password, bytes.fromhex(salt)), bytes.fromhex(expected)
        )
    finally:
        limiter.hash_slots.release()
    if not (valid_role and valid_password):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    return _start_session(request, account)


@router.post("/auth/guest")
def enter_as_guest(request: Request):
    request.app.state.login_rate.check(request, "guest")
    with Session(request.app.state.store.engine) as db:
        account = db.get(Account, GUEST)
    if account is None:
        raise HTTPException(503, "El acceso de invitado no está disponible.")
    return _start_session(request, account)


@router.get("/auth/session")
def current_session(request: Request):
    return JSONResponse(
        _identity(request.state.account, request.app.state.store),
        headers={"Cache-Control": "no-store"},
    )


class SessionRole(BaseModel):
    role: Literal["admin", "usuario"]


@router.put("/auth/session/role", status_code=204)
def select_session_role(request: Request, body: SessionRole):
    account: SignedInAccount = request.state.account
    if not account.can_switch_role:
        raise HTTPException(403, "Esta cuenta no puede cambiar el rol de su sesión.")
    with Session(request.app.state.store.engine) as db:
        result = db.exec(
            update(AccountSession)
            .where(
                AccountSession.digest == _digest(request.cookies[SESSION_COOKIE]),
                AccountSession.username == account.username,
                AccountSession.expires_at > time.time(),
            )
            .values(viewing_role="usuario" if body.role == "usuario" else None)
        )
        if result.rowcount != 1:
            raise HTTPException(401, "La sesión ha caducado. Vuelve a iniciar sesión.")
        db.commit()
    return Response(status_code=204)


@router.put("/auth/avatar")
async def set_avatar(request: Request, file: UploadFile):
    """Foto de perfil de la cuenta en sesión: PNG, JPEG o WebP de hasta 1 MB."""
    account = request.state.account
    if account.role == "guest":
        raise HTTPException(403, "El invitado no tiene perfil.")
    extension = AVATAR_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(415, "La foto debe ser PNG, JPEG o WebP.")
    content = await file.read(MAX_AVATAR + 1)
    if len(content) > MAX_AVATAR:
        raise HTTPException(413, "La foto no puede pasar de 1 MB.")
    folder = Path(request.app.state.store.root) / "avatars"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{account.username}.*"):
        old.unlink()
    (folder / f"{account.username}.{extension}").write_bytes(content)
    return JSONResponse(
        _identity(account, request.app.state.store), headers={"Cache-Control": "no-store"}
    )


@router.get("/auth/avatar/{username}")
def get_avatar(request: Request, username: str):
    path = _avatar_path(request.app.state.store, username)
    if path is None:
        raise HTTPException(404, "Sin foto de perfil.")
    media = {v: k for k, v in AVATAR_TYPES.items()}[path.suffix[1:]]
    return FileResponse(path, media_type=media, headers={"Cache-Control": "private, max-age=60"})


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    with Session(request.app.state.store.engine) as db:
        session = db.get(AccountSession, _digest(request.cookies[SESSION_COOKIE]))
        if session:
            db.delete(session)
            db.commit()
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=_cookie_secure(), httponly=True, samesite="strict"
    )
    return response

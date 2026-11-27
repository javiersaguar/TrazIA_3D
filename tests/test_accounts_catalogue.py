"""Acceso por roles y persistencia independiente del navegador."""

import secrets

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from trazia.api.accounts import ADMINS, SESSION_COOKIE
from trazia.api.app import create_app
from trazia.store.accounts import Account, AccountSession


@pytest.fixture()
def settings(monkeypatch, tmp_path):
    secret = secrets.token_hex(12)
    password_file = tmp_path / "clave.txt"
    password_file.write_text(secret + "\n", encoding="utf-8")
    monkeypatch.setenv("TRAZIA_AUTH", "1")
    monkeypatch.setenv("TRAZIA_AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("TRAZIA_ADMIN_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("TRAZIA_CORS_ORIGINS", "http://localhost:3120")
    return tmp_path / "data", secret, password_file


def start(client, user, secret):
    return client.post("/auth/login", json={"username": user, "password": secret})


def test_seeded_admins_use_separate_hashes_and_logout_revokes_session(settings):
    data, secret, _ = settings
    with TestClient(create_app(data_root=data, seed=False)) as client:
        assert client.get("/catalogue").status_code == 401
        assert start(client, ADMINS[0], "contraseña incorrecta").status_code == 401
        assert start(client, "invitado", secret).status_code == 401
        for user in ADMINS:
            response = start(client, user, secret)
            assert response.json() | {"name": None, "avatar": None} == {
                "username": user,
                "role": "admin",
                "name": None,
                "avatar": None,
            }
            cookie = response.headers["set-cookie"]
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie
            assert secret not in cookie
        token = client.cookies[SESSION_COOKIE]
        with Session(client.app.state.store.engine) as db:
            hashes = [a.password_hash for a in db.exec(select(Account)).all() if a.role == "admin"]
            assert len(set(hashes)) == 4
            assert all(secret not in value for value in hashes)
            assert all(s.digest != token for s in db.exec(select(AccountSession)).all())
        assert client.post("/auth/logout").status_code == 204
        assert (
            client.get("/auth/session", headers={"Cookie": f"{SESSION_COOKIE}={token}"}).status_code
            == 401
        )


def test_publication_survives_restart_and_guest_cannot_write(settings):
    data, secret, password_file = settings
    pdf = b"%PDF-1.4\n%%EOF\n"
    with TestClient(create_app(data_root=data, seed=False)) as admin:
        assert start(admin, ADMINS[0], secret).status_code == 200
        assert (
            admin.post(
                "/catalogue/groups",
                json={"kind": "project", "name": "Proyecto de prueba"},
                headers={"Origin": "https://example.org"},
            ).status_code
            == 403
        )
        project = admin.post(
            "/catalogue/groups", json={"kind": "project", "name": "Proyecto de prueba"}
        ).json()
        body = {"name": "Plano de prueba", "family": "vertical", "project": project["id"]}
        result = admin.post("/catalogue/designs", data=body, files={"file": ("plano.pdf", pdf)})
        assert result.status_code == 201
        design_id = result.json()["id"]
        assert (
            admin.post(
                "/catalogue/designs", data=body, files={"file": ("falso.pdf", b"<svg>")}
            ).status_code
            == 422
        )

    password_file.unlink()
    with TestClient(create_app(data_root=data, seed=False)) as guest:
        assert guest.post("/auth/guest").json() == {"username": "invitado", "role": "guest"}
        assert guest.get("/catalogue").json()["designs"][0]["id"] == design_id
        assert guest.get(f"/catalogue/designs/{design_id}/file").content == pdf
        assert guest.get("/correcciones").status_code == 403
        assert (
            guest.post("/catalogue/groups", json={"kind": "family", "name": "Invitado"}).status_code
            == 403
        )
        assert (
            guest.post(
                "/catalogue/designs", data=body, files={"file": ("plano.pdf", pdf)}
            ).status_code
            == 403
        )
        assert guest.patch(f"/catalogue/designs/{design_id}", json=body).status_code == 403
        assert guest.post("/documents", files={"file": ("plano.pdf", pdf)}).status_code == 403

        assert start(guest, ADMINS[1], secret).status_code == 200
        result = guest.patch(
            f"/catalogue/designs/{design_id}", json={"family": "tank", "project": "demo"}
        )
        assert result.status_code == 200
        assert guest.get("/catalogue").json()["designs"][0]["family"] == "tank"

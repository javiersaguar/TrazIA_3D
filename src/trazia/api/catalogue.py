"""Catálogo compartido y publicación de diseños en el almacén IFC."""

import re
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trazia.store.accounts import CatalogueGroup, PublishedDesign

router = APIRouter(prefix="/catalogue")
MAX_DESIGN_BYTES = 25 * 1024**2
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".ifc": ("application/x-step", b"ISO-10303-21;"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK\x03\x04"),
    ".xls": ("application/vnd.ms-excel", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}


def _name(name: str) -> str:
    name = name.strip()
    if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise HTTPException(422, "Introduce un nombre válido.")
    return name


def _group(design: CatalogueGroup) -> dict:
    return {"id": design.id, "name": design.name, "custom": True}


def _design(design: PublishedDesign) -> dict:
    return {
        "id": design.id,
        "name": design.name,
        "family": design.family,
        "project": design.project,
        "filename": design.filename,
        "size": design.size,
        "shared": True,
        "stage": "recibido",
        "publishedAt": datetime.fromtimestamp(design.published_at, UTC).isoformat(),
    }


class GroupInput(BaseModel):
    kind: Literal["family", "project"]
    name: str = Field(max_length=120)


class Assignment(BaseModel):
    family: str = Field(max_length=64)
    project: str = Field(max_length=64)


def _validate_destinations(db: Session, family: str, project: str) -> None:
    for role, value in (("family", family), ("project", project)):
        # Las colecciones de la aplicación llevan un slug; las creadas aquí usan UUID.
        if not SLUG.fullmatch(value):
            raise HTTPException(422, "Selecciona una familia y un proyecto válidos.")
        try:
            UUID(value)
        except ValueError:
            continue
        group = db.get(CatalogueGroup, value)
        if group is None or group.kind != role:
            raise HTTPException(422, "La familia o el proyecto ya no está disponible.")


@router.get("")
def catalogue(request: Request):
    with Session(request.app.state.store.engine) as db:
        groups = db.exec(select(CatalogueGroup).order_by(CatalogueGroup.name)).all()
        designs = db.exec(
            select(PublishedDesign).order_by(PublishedDesign.published_at.desc())
        ).all()
        return {
            "families": [_group(group) for group in groups if group.kind == "family"],
            "projects": [_group(group) for group in groups if group.kind == "project"],
            "designs": [_design(design) for design in designs],
        }


@router.post("/groups", status_code=201)
def add_group(request: Request, body: GroupInput):
    group = CatalogueGroup(id=str(uuid4()), kind=body.kind, name=_name(body.name))
    with Session(request.app.state.store.engine) as db:
        db.add(group)
        db.commit()
        return _group(group)


@router.post("/designs", status_code=201)
def publish_design(
    request: Request,
    name: Annotated[str, Form(max_length=120)],
    family: Annotated[str, Form(max_length=64)],
    project: Annotated[str, Form(max_length=64)],
    file: Annotated[UploadFile, File()],
):
    store = request.app.state.store
    title = _name(name)
    filename = _name(PurePosixPath((file.filename or "").replace("\\", "/")).name)
    kind = TYPES.get(Path(filename).suffix.lower())
    if len(filename) > 180 or kind is None:
        raise HTTPException(422, "Sube un IFC, PDF, Excel, PNG o JPEG con un nombre válido.")
    media_type, signature = kind
    content = file.file.read(MAX_DESIGN_BYTES + 1)
    if len(content) > MAX_DESIGN_BYTES:
        raise HTTPException(413, "Cada diseño puede ocupar hasta 25 MB.")
    if not content.startswith(signature):
        raise HTTPException(422, "El contenido del archivo no coincide con el formato indicado.")
    with Session(store.engine) as db:
        _validate_destinations(db, family, project)
        design = PublishedDesign(
            id=str(uuid4()),
            name=title,
            family=family,
            project=project,
            filename=filename,
            media_type=media_type,
            sha256=store.put_design(content),
            size=len(content),
            published_at=time.time(),
            published_by=request.state.account.username,
        )
        db.add(design)
        db.commit()
        return _design(design)


@router.patch("/designs/{identity}")
def assign_design(request: Request, identity: UUID, body: Assignment):
    with Session(request.app.state.store.engine) as db:
        design = db.get(PublishedDesign, str(identity))
        if design is None:
            raise HTTPException(404, "El diseño no está disponible.")
        _validate_destinations(db, body.family, body.project)
        design.family, design.project = body.family, body.project
        db.commit()
        return _design(design)


@router.get("/designs/{identity}/file")
def design_file(request: Request, identity: UUID):
    store = request.app.state.store
    with Session(store.engine) as db:
        design = db.get(PublishedDesign, str(identity))
        if design is None:
            raise HTTPException(404, "El diseño no está disponible.")
        path = store.catalogue_blobs / design.sha256[:2] / design.sha256
        if not path.is_file():
            raise HTTPException(404, "El archivo de este diseño no está disponible.")
        return FileResponse(
            path,
            filename=design.filename,
            media_type=design.media_type,
            headers={"X-Content-Type-Options": "nosniff"},
        )

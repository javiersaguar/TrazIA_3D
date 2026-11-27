"""Fichas de equipo: búsqueda por código para nuevas subidas, borrado completo y retirada.

Una ficha es un equipo de un proyecto (`project_id` + `equipment_id`) con todas sus revisiones.

- `GET /equipment/match?tag=` devuelve las fichas con ese código, sin distinguir mayúsculas ni
  espacios, para que una subida nueva se guarde como otra versión de la ficha existente.
- `DELETE /equipment/{project_id}/{equipment_id}` borra todas sus revisiones. Si alguna está
  protegida (aprobada, en un trabajo activo o enlazada por un cambio de diseño) responde 409 y no
  borra ninguna; la ficha se puede retirar entonces del catálogo conservando su historial.
- `POST /equipment/retire` oculta una ficha del catálogo sin borrar nada.

Borrar o retirar deja un registro en `retired`, de modo que la siembra de la demo y del lote no
recupera la ficha al reiniciar la API. Una lectura nueva del mismo equipo la vuelve a mostrar.
Solo los administradores borran o retiran fichas.
"""

import json
import logging
import re

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlmodel import Session, select

from trazia.model import Identifier, Model
from trazia.store import RetiredRecord, RevisionRecord

router = APIRouter()
logger = logging.getLogger("trazia.api.fichas")


def tag_key(tag: str) -> str:
    return re.sub(r"\s+", "", tag).upper()


def _ficha_id(project_id: str, equipment_id: str | None, tag: str) -> str:
    return f"ficha:{project_id}:{equipment_id or 'tag=' + tag_key(tag)}"


def retire(session: Session, *, project_id, equipment_id, tag, mode, actor, revision=None):
    identity = (
        f"rev:{project_id}:{equipment_id}:{revision}"
        if revision is not None
        else _ficha_id(project_id, equipment_id, tag)
    )
    record = session.get(RetiredRecord, identity) or RetiredRecord(
        id=identity, project_id=project_id, tag_key=tag_key(tag), mode=mode
    )
    record.equipment_id, record.revision, record.mode, record.actor = (
        equipment_id,
        revision,
        mode,
        actor,
    )
    session.add(record)


def retired_ficha(session: Session, project_id: str, equipment_id: str | None, tag: str) -> bool:
    rows = session.exec(
        select(RetiredRecord).where(
            RetiredRecord.project_id == project_id, RetiredRecord.revision.is_(None)
        )
    ).all()
    key = tag_key(tag)
    return any(
        (equipment_id and row.equipment_id == equipment_id)
        or (row.equipment_id is None and row.tag_key == key)
        for row in rows
    )


def retired_revision(session: Session, project_id: str, equipment_id: str, revision: str) -> bool:
    return session.get(RetiredRecord, f"rev:{project_id}:{equipment_id}:{revision}") is not None


def skip_seed(session: Session, project_id: str, equipment_id: str, tag: str, revision: str):
    """La siembra no recupera lo que alguien borró o retiró."""
    return retired_ficha(session, project_id, equipment_id, tag) or retired_revision(
        session, project_id, equipment_id, revision
    )


def hidden_fichas(session: Session) -> set[tuple[str, str]]:
    """(proyecto, equipo) retirados del catálogo con su historial conservado."""
    rows = session.exec(
        select(RetiredRecord).where(
            RetiredRecord.mode == "retired", RetiredRecord.revision.is_(None)
        )
    ).all()
    return {(row.project_id, row.equipment_id) for row in rows if row.equipment_id}


def retired_tags(session: Session) -> set[tuple[str, str]]:
    rows = session.exec(select(RetiredRecord).where(RetiredRecord.revision.is_(None))).all()
    return {(row.project_id, row.tag_key) for row in rows}


def restore(session: Session, project_id: str, equipment_id: str, tag: str, revision: str):
    """Una lectura nueva del equipo lo devuelve al catálogo."""
    for identity in (
        _ficha_id(project_id, equipment_id, tag),
        _ficha_id(project_id, None, tag),
        f"rev:{project_id}:{equipment_id}:{revision}",
    ):
        if (record := session.get(RetiredRecord, identity)) is not None:
            session.delete(record)


def _require_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= 128:
        raise HTTPException(428, "Se requiere Idempotency-Key de 1 a 128 caracteres")
    return value


def _require_admin(request: Request):
    account = getattr(request.state, "account", None)
    if account is not None and account.role != "admin":
        raise HTTPException(403, "Solo un administrador puede borrar o retirar fichas.")


def _actor(request: Request) -> str | None:
    from .accounts import request_username

    return request_username(request)


@router.get("/equipment/match")
def match(request: Request, tag: str, project_id: str | None = None):
    """Fichas con el mismo código, con sus revisiones y la huella de sus originales."""
    key = tag_key(tag)
    if not key:
        return []
    with Session(request.app.state.store.engine) as session:
        hidden = hidden_fichas(session)
        query = select(RevisionRecord)
        if project_id:
            query = query.where(RevisionRecord.project_id == project_id)
        fichas: dict[tuple[str, str], dict] = {}
        for row in session.exec(query).all():
            if tag_key(row.tag) != key or (row.project_id, row.equipment_id) in hidden:
                continue
            payload = json.loads(row.payload)
            ficha = fichas.setdefault(
                (row.project_id, row.equipment_id),
                {
                    "project_id": row.project_id,
                    "equipment_id": row.equipment_id,
                    "tag": row.tag,
                    "dataset": payload.get("dataset"),
                    "revisions": [],
                },
            )
            ficha["revisions"].append(
                {
                    "label": row.revision,
                    "approved": bool(payload.get("approval")),
                    "documents": [
                        {"filename": d["filename"], "sha256": d["sha256"]}
                        for d in payload.get("documents", [])
                    ],
                }
            )
        return sorted(fichas.values(), key=lambda f: (f["project_id"], f["equipment_id"]))


@router.delete("/equipment/{project_id}/{equipment_id}")
def delete_ficha(
    request: Request,
    project_id: str,
    equipment_id: str,
    idempotency_key: str | None = Header(None),
):
    _require_admin(request)
    key = _require_key(idempotency_key)
    store = request.app.state.store
    actor = _actor(request)

    def action(session: Session):
        from .revision_delete import blockers, remove_revision

        rows = session.exec(
            select(RevisionRecord).where(
                RevisionRecord.project_id == project_id,
                RevisionRecord.equipment_id == equipment_id,
            )
        ).all()
        if not rows:
            raise HTTPException(404, "No existe esa ficha")
        tag = rows[0].tag
        protected = [
            f"Rev {row.revision}: {reason}" for row in rows if (reason := blockers(session, row))
        ]
        if protected:
            raise HTTPException(
                409,
                f"No se puede borrar la ficha {tag} ({project_id}). "
                + " ".join(protected)
                + " Puedes retirarla del catálogo conservando su historial.",
            )
        removed = [remove_revision(session, store, row) for row in rows]
        retire(
            session,
            project_id=project_id,
            equipment_id=equipment_id,
            tag=tag,
            mode="deleted",
            actor=actor,
        )
        data = {
            "project_id": project_id,
            "equipment_id": equipment_id,
            "tag": tag,
            "revisions": [row.revision for row in rows],
            "blobs_removed": sum(item["blobs_removed"] for item in removed),
        }
        return {"data": data, "status": 200}

    result = store.perform(f"DELETE /equipment/{project_id}/{equipment_id}", key, {}, action)
    if result["status"] == 200:
        event = {"event": "ficha_deleted", "actor": actor, **result["data"]}
        logger.info(json.dumps(event, ensure_ascii=False))
    return JSONResponse(result["data"], status_code=result["status"])


class RetireInput(Model):
    project_id: Identifier
    equipment_id: Identifier | None = None
    tag: str = Field(min_length=1, max_length=120)


@router.post("/equipment/retire")
def retire_ficha(request: Request, body: RetireInput, idempotency_key: str | None = Header(None)):
    _require_admin(request)
    key = _require_key(idempotency_key)
    actor = _actor(request)

    def action(session: Session):
        retire(
            session,
            project_id=body.project_id,
            equipment_id=body.equipment_id,
            tag=body.tag,
            mode="retired",
            actor=actor,
        )
        return {"data": body.model_dump() | {"retired": True}, "status": 200}

    result = request.app.state.store.perform(
        "POST /equipment/retire", key, body.model_dump(), action
    )
    logger.info(json.dumps({"event": "ficha_retired", "actor": actor, **body.model_dump()}))
    return JSONResponse(result["data"], status_code=result["status"])

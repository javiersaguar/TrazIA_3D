"""Listado y borrado de los documentos registrados con `POST /documents`.

Borrar nunca rompe la trazabilidad: si una revisión guardada cita el SHA-256 del original
o un trabajo en cola o en curso usa el registro, la API responde 409 y no toca nada. El
blob del almacén solo se elimina cuando ningún otro registro, artefacto, resultado de
trabajo ni vista previa comparte ese SHA-256.
"""

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from trazia.store import DocumentRecord, JobCacheRecord, JobRecord, RevisionRecord

from .change_proposals import referenced

router = APIRouter()
logger = logging.getLogger("trazia.api.documents")
ACTIVE = ("queued", "running")
# Los registros que crea la propia API al sembrar la demo, el lote o un diseño llevan prefijo.
SEEDED = ("seed-", "lote-", "design-")


def citations(session: Session) -> dict[str, list[str]]:
    """SHA-256 de cada original citado → revisiones guardadas que lo citan."""
    cited: dict[str, list[str]] = {}
    for identity, payload in session.exec(select(RevisionRecord.id, RevisionRecord.payload)):
        for document in json.loads(payload).get("documents", []):
            revisions = cited.setdefault(document["sha256"], [])
            if identity not in revisions:
                revisions.append(identity)
    return cited


def active_jobs(session: Session) -> dict[str, list[str]]:
    """ID de registro documental → trabajos en cola o en curso que lo usan."""
    used: dict[str, list[str]] = {}
    rows = session.exec(
        select(JobRecord.id, JobRecord.request_json).where(
            JobRecord.kind == "pipeline", JobRecord.status.in_(ACTIVE)
        )
    )
    for job_id, request_json in rows:
        for identity in json.loads(request_json).get("documents", []):
            used.setdefault(identity, []).append(job_id)
    return used


def describe(record: DocumentRecord, cited: dict, jobs: dict) -> dict:
    return {
        **record.model_dump(),
        "uploaded": not record.id.startswith(SEEDED),
        "cited_by": cited.get(record.sha256, []),
        "active_jobs": jobs.get(record.id, []),
    }


@router.get("/documents")
def list_documents(request: Request):
    with Session(request.app.state.store.engine) as session:
        cited, jobs = citations(session), active_jobs(session)
        records = session.exec(select(DocumentRecord).order_by(DocumentRecord.filename)).all()
        return [describe(record, cited, jobs) for record in records]


def shared_elsewhere(session: Session, sha: str) -> bool:
    if referenced(session, sha):
        return True
    if session.exec(select(JobRecord.id).where(JobRecord.result_sha256 == sha)).first():
        return True
    return (
        session.exec(select(JobCacheRecord.key).where(JobCacheRecord.result_sha256 == sha)).first()
        is not None
    )


@router.delete("/documents/{identity}")
def delete_document(request: Request, identity: str, idempotency_key: str | None = Header(None)):
    if idempotency_key is None or not 1 <= len(idempotency_key) <= 128:
        raise HTTPException(428, "Se requiere Idempotency-Key de 1 a 128 caracteres")
    store = request.app.state.store

    def action(session: Session):
        record = session.get(DocumentRecord, identity)
        if record is None:
            raise HTTPException(404, "No existe ese documento")
        revisions = citations(session).get(record.sha256, [])
        if revisions:
            listed = ", ".join(revisions[:3]) + ("…" if len(revisions) > 3 else "")
            raise HTTPException(
                409,
                f"No se puede borrar {record.filename}: lo cita la revisión guardada {listed}. "
                "Borrarlo rompería la verificación de originales por SHA-256.",
            )
        if active_jobs(session).get(record.id):
            raise HTTPException(
                409,
                f"No se puede borrar {record.filename}: lo está usando un trabajo en curso. "
                "Espera a que termine o cancélalo.",
            )
        sha = record.sha256
        session.delete(record)
        session.flush()
        # El original se conserva si otro registro u otro artefacto comparte su SHA-256.
        blob_removed = False if shared_elsewhere(session, sha) else store.discard(sha)
        return {
            "data": {"id": identity, "sha256": sha, "blob_removed": blob_removed},
            "status": 200,
        }

    result = store.perform(f"DELETE /documents/{identity}", idempotency_key, {}, action)
    if result["status"] == 200:
        from .accounts import request_username

        logger.info(
            json.dumps(
                {"event": "document_deleted", "actor": request_username(request), **result["data"]},
                ensure_ascii=False,
            )
        )
    return JSONResponse(result["data"], status_code=result["status"])

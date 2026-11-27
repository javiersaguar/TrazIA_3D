"""Borrado de una revisión guardada (`DELETE /revisions/{id}`).

Solo se borran borradores. La API responde 409 y no toca nada si la revisión está aprobada,
si un trabajo en cola o en curso la usa (como memoria o como destino) o si una propuesta de
cambio la enlaza con otra revisión, porque esa otra revisión perdería su derivación. Al borrar
se eliminan también su auditoría, sus sesiones de revisión, sus propuestas sin aplicar y sus
artefactos publicados; los originales citados se conservan y pasan a poder borrarse si nada
más los cita. El borrado queda registrado para que la siembra de la demo o del lote no la
recupere al reiniciar la API.
"""

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from trazia.store import (
    AuditRecord,
    ChangeProposalRecord,
    JobRecord,
    ReviewSessionRecord,
    RevisionArtifactRecord,
    RevisionRecord,
)

from .documents import ACTIVE, shared_elsewhere
from .repository import check_match, get_revision

router = APIRouter()
logger = logging.getLogger("trazia.api.revisions")


def blockers(session: Session, record: RevisionRecord) -> str | None:
    payload = json.loads(record.payload)
    if payload.get("approval"):
        return "Está aprobada; una revisión aprobada no se borra."
    for job_id, request_json in session.exec(
        select(JobRecord.id, JobRecord.request_json).where(
            JobRecord.kind == "pipeline", JobRecord.status.in_(ACTIVE)
        )
    ):
        request = json.loads(request_json)
        target = (request.get("project_id"), request.get("equipment_id"), request.get("revision"))
        if request.get("previous_id") == record.id or target == (
            record.project_id,
            record.equipment_id,
            record.revision,
        ):
            return f"La usa el trabajo en curso {job_id}; espera a que termine o cancélalo."
    proposals = session.exec(
        select(ChangeProposalRecord).where(
            (ChangeProposalRecord.revision_id == record.id)
            | (ChangeProposalRecord.applied_revision_id == record.id)
        )
    ).all()
    for proposal in proposals:
        applied = proposal.applied_revision_id
        if proposal.revision_id == record.id and applied and applied != record.id:
            if session.get(RevisionRecord, applied):
                return f"La revisión {applied} se creó con un cambio de diseño sobre esta."
        if applied == record.id and proposal.revision_id != record.id:
            return (
                f"Se creó con un cambio de diseño sobre {proposal.revision_id}; "
                "para deshacerlo usa la reversión del cambio."
            )
    return None


def reemplazo_bloqueado(session: Session, record: RevisionRecord) -> str | None:
    """Una versión en borrador se puede volver a leer. Una aprobada, o enlazada a un cambio, no."""
    payload = json.loads(record.payload)
    if payload.get("approval"):
        return "Esa versión está aprobada; indica otra versión."
    proposals = session.exec(
        select(ChangeProposalRecord).where(
            (ChangeProposalRecord.revision_id == record.id)
            | (ChangeProposalRecord.applied_revision_id == record.id)
        )
    ).all()
    for proposal in proposals:
        applied = proposal.applied_revision_id
        if proposal.revision_id == record.id and applied and applied != record.id:
            if session.get(RevisionRecord, applied):
                return f"La revisión {applied} se creó con un cambio de diseño sobre esta."
        if applied == record.id and proposal.revision_id != record.id:
            return (
                f"Se creó con un cambio de diseño sobre {proposal.revision_id}; "
                "para deshacerlo usa la reversión del cambio."
            )
    return None


def remove_revision(session: Session, store, record: RevisionRecord) -> dict:
    """Borra la revisión con lo que cuelga de ella. Quien llama comprueba antes `blockers`."""
    blobs: set[str] = set()
    removed = {"audit": 0, "review_sessions": 0, "proposals": 0, "artifacts": 0}
    for model, key in (
        (AuditRecord, "audit"),
        (ReviewSessionRecord, "review_sessions"),
        (ChangeProposalRecord, "proposals"),
        (RevisionArtifactRecord, "artifacts"),
    ):
        for child in session.exec(select(model).where(model.revision_id == record.id)).all():
            if isinstance(child, RevisionArtifactRecord):
                blobs.add(child.sha256)
            if isinstance(child, ChangeProposalRecord) and child.preview_ifc_sha256:
                blobs.add(child.preview_ifc_sha256)
            session.delete(child)
            removed[key] += 1
    for job in session.exec(select(JobRecord).where(JobRecord.revision_id == record.id)):
        job.revision_id = None
        session.add(job)
    session.delete(record)
    session.flush()
    discarded = sum(store.discard(sha) for sha in blobs if not shared_elsewhere(session, sha))
    return {"id": record.id, "removed": removed, "blobs_removed": discarded}


@router.delete("/revisions/{identity}")
def delete_revision(
    request: Request,
    identity: str,
    if_match: str | None = Header(None),
    idempotency_key: str | None = Header(None),
):
    if idempotency_key is None or not 1 <= len(idempotency_key) <= 128:
        raise HTTPException(428, "Se requiere Idempotency-Key de 1 a 128 caracteres")
    store = request.app.state.store
    from .accounts import request_username

    actor = request_username(request)

    def action(session: Session):
        record = get_revision(session, identity)
        check_match(record, if_match)
        if reason := blockers(session, record):
            raise HTTPException(409, f"No se puede borrar la revisión {record.revision}: {reason}")
        data = remove_revision(session, store, record)
        from .fichas import retire

        retire(
            session,
            project_id=record.project_id,
            equipment_id=record.equipment_id,
            tag=record.tag,
            revision=record.revision,
            mode="deleted",
            actor=actor,
        )
        return {"data": data, "status": 200}

    result = store.perform(
        f"DELETE /revisions/{identity}", idempotency_key, {"if_match": if_match}, action
    )
    if result["status"] == 200:
        logger.info(
            json.dumps(
                {"event": "revision_deleted", "actor": actor, **result["data"]},
                ensure_ascii=False,
            )
        )
    return JSONResponse(result["data"], status_code=result["status"])

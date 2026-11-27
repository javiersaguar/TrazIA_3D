from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import update
from sqlmodel import Session, select

from trazia.model import Revision, load_revision
from trazia.store import AuditRecord, DocumentRecord, RevisionRecord, Store

from .auto_approval import aprobar_al_guardar
from .fichas import skip_seed


def revision_id(revision: Revision) -> str:
    return f"{revision.project_id}:{revision.equipment.id}:{revision.revision}"


def read_original(store: Store, digest: str) -> bytes:
    try:
        return store.read(digest)
    except FileNotFoundError as error:
        raise HTTPException(404, "Falta el original de la revisión") from error
    except (OSError, ValueError) as error:
        raise HTTPException(409, "No se puede verificar el original de la revisión") from error


def get_revision(session: Session, identity: str) -> RevisionRecord:
    record = session.get(RevisionRecord, identity)
    if record is None and identity in ("A", "B"):
        record = session.exec(
            select(RevisionRecord).where(
                RevisionRecord.project_id == "DEMO-PLANT",
                RevisionRecord.tag == "V-101",
                RevisionRecord.revision == identity,
            )
        ).first()
    if record is None:
        raise HTTPException(404, "No existe esa revisión")
    return record


def check_match(record: RevisionRecord, if_match: str | None):
    if if_match is None:
        raise HTTPException(428, "Se requiere If-Match con el ETag de la revisión")
    if if_match != f'"{record.version}"':
        raise HTTPException(412, "La revisión ha cambiado; vuelva a cargarla antes de editar")


def load_stored_revision(record: RevisionRecord) -> Revision:
    try:
        revision = Revision.model_validate_json(record.payload)
    except ValidationError as error:
        raise HTTPException(409, "La revisión almacenada no cumple el contrato") from error
    if (
        revision.project_id,
        revision.equipment.id,
        revision.equipment.tag.value,
        revision.revision,
    ) != (record.project_id, record.equipment_id, record.tag, record.revision):
        raise HTTPException(409, "Los identificadores de la revisión no coinciden con su registro")
    return revision


def save_revision(
    session: Session,
    record: RevisionRecord,
    revision: Revision,
    *,
    path: str,
    actor: str,
    seconds: float | None = None,
    review_session_id: str | None = None,
    undo_of: int | None = None,
):
    before = record.payload
    version = record.version
    changed = session.exec(
        update(RevisionRecord)
        .where(RevisionRecord.id == record.id, RevisionRecord.version == version)
        .values(
            payload=revision.model_dump_json(),
            version=version + 1,
            tag=revision.equipment.tag.value,
        )
    )
    if changed.rowcount != 1:
        raise HTTPException(412, "Otra persona ha modificado la revisión")
    audit = AuditRecord(
        revision_id=record.id,
        path=path,
        actor=actor,
        before_json=before,
        after_json=revision.model_dump_json(),
        seconds=seconds,
        review_session_id=review_session_id,
        undo_of=undo_of,
    )
    session.add(audit)
    session.flush()
    return {
        "data": revision.model_dump(mode="json"),
        "version": version + 1,
        "status": 200,
        "audit_id": audit.id,
    }


def seed_demo(store: Store, root: Path):
    with Session(store.engine) as session:
        for suffix in ("a", "b"):
            revision = load_revision(root / "examples" / f"vessel_rev_{suffix}.json")
            identity = revision_id(revision)
            if session.get(RevisionRecord, identity) or skip_seed(
                session,
                revision.project_id,
                revision.equipment.id,
                revision.equipment.tag.value,
                revision.revision,
            ):
                continue
            for document in revision.documents:
                content = (root / "examples" / "documents" / document.filename).read_bytes()
                digest = store.put(content)
                if digest != document.sha256:
                    raise ValueError("La demo no coincide con los hashes de sus originales")
                session.add(
                    DocumentRecord(
                        id=f"seed-{suffix}-{document.id}",
                        document_id=document.id,
                        filename=document.filename,
                        revision=document.revision,
                        sha256=digest,
                        size=len(content),
                    )
                )
            session.add(
                RevisionRecord(
                    id=identity,
                    project_id=revision.project_id,
                    equipment_id=revision.equipment.id,
                    tag=revision.equipment.tag.value,
                    revision=revision.revision,
                    payload=revision.model_dump_json(),
                )
            )
        session.commit()


def _originals(dataset: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(dataset.rglob("*")):
        if path.is_file():
            found.setdefault(path.name.lower(), path)
    return found


def seed_dataset(store: Store, lote: Path, dataset: Path) -> int:
    """Carga en la API las revisiones de un `trazia lote` sobre el dataset real.

    Cada revisión entra con sus originales, que deben estar en `dataset` y coincidir con el hash
    citado. Las que ya están en el almacén no se tocan: conservan la revisión humana hecha en la
    API. Devuelve cuántas revisiones nuevas entran.
    """
    originals = _originals(dataset)
    nuevas = 0
    with Session(store.engine) as session:
        for path in sorted(lote.glob("*/rev*/revision.json")):
            revision = load_revision(path)
            identity = revision_id(revision)
            if session.get(RevisionRecord, identity) or skip_seed(
                session,
                revision.project_id,
                revision.equipment.id,
                revision.equipment.tag.value,
                revision.revision,
            ):
                continue
            documentos = []
            for document in revision.documents:
                original = originals.get(document.filename.lower())
                if original is None:
                    raise ValueError(f"Falta el original {document.filename} en {dataset}")
                content = original.read_bytes()
                digest = store.put(content)
                if digest != document.sha256:
                    raise ValueError(f"{document.filename} no coincide con el hash de la revisión")
                documentos.append(
                    DocumentRecord(
                        id=f"lote-{identity}-{document.id}",
                        document_id=document.id,
                        filename=document.filename,
                        revision=document.revision,
                        sha256=digest,
                        size=len(content),
                    )
                )
            for record in documentos:
                if session.get(DocumentRecord, record.id) is None:
                    session.add(record)
            revision, aprobacion = aprobar_al_guardar(identity, revision)
            session.add(
                RevisionRecord(
                    id=identity,
                    project_id=revision.project_id,
                    equipment_id=revision.equipment.id,
                    tag=revision.equipment.tag.value,
                    revision=revision.revision,
                    payload=revision.model_dump_json(),
                )
            )
            if aprobacion is not None:
                session.flush()
                session.add(aprobacion)
            nuevas += 1
        session.commit()
    return nuevas

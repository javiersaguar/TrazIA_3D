import asyncio
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import Field, ValidationError
from sqlalchemy import cast, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, select

from trazia.copilot import CopilotAnswer, CopilotUnavailable
from trazia.copilot.cache import answer_cached
from trazia.copilot.grounded import ask as ask_copilot
from trazia.copilot.voice import MAX_AUDIO_BYTES
from trazia.ifc import build_ifc
from trazia.lote import _orden as revision_order
from trazia.model import FieldState, Identifier, Model, Revision, Source
from trazia.queue import ProcessQueue
from trazia.review import approve
from trazia.revisions import compare
from trazia.store import (
    AuditRecord,
    DocumentRecord,
    EventRecord,
    IdempotencyConflict,
    JobRecord,
    RevisionRecord,
    Store,
)

from . import review_sessions
from .cors import origins
from .jobs import TERMINAL, recover_jobs, run_job
from .repository import (
    check_match,
    get_revision,
    load_stored_revision,
    read_original,
    save_revision,
    seed_dataset,
    seed_demo,
)
from .security import UploadLimit
from .validation import (
    REFERENCE_SYSTEM,
    RevisionLabel,
    diagnostics,
    issues_for,
    validate_revision_label,
)

MAX_UPLOAD = 25 * 1024 * 1024


class JobInput(Model):
    documents: list[str] = Field(min_length=1, max_length=30)
    project_id: Identifier = "DEMO-PLANT"
    equipment_id: Identifier = Field(
        default="vessel-001", description="ID estable del equipo; no cambia al renombrar el tag"
    )
    revision: RevisionLabel = "C"
    strategy: str = Field(default="lectura", min_length=1, max_length=80)
    providers: list[str] = Field(default_factory=list, max_length=10)
    dataset: Literal["synthetic", "real"] = "synthetic"
    previous_id: str | None = None
    timeout_seconds: float = Field(default=300, gt=0, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=5)
    retry_backoff_seconds: float = Field(default=1, ge=0, le=30)


class EquipmentJobInput(JobInput):
    tag: str = Field(min_length=1, max_length=120, pattern=r"^\S(?:[^\r\n]*\S)?$")
    revision: RevisionLabel = Field()


class FieldInput(Model):
    state: FieldState
    value: float | str | None = None
    unit: str | None = Field(default=None, min_length=1)
    decimal_separator: Literal[".", ","] | None = None
    source: Source | None = None
    explanation: str | None = Field(default=None, max_length=2000)
    actor: str = Field(min_length=2, max_length=100)
    seconds: float | None = Field(default=None, ge=0, le=3600)
    review_session_id: str | None = None
    action: Literal["accept", "correct", "assume", "reject"] | None = None
    expected: dict | None = None


class UndoInput(Model):
    actor: str = Field(min_length=2, max_length=100)
    seconds: float | None = Field(default=None, ge=0, le=3600)
    review_session_id: str | None = None


class CopilotInput(Model):
    question: str = Field(min_length=1, max_length=2000)
    revision_id: str = Field(min_length=1, max_length=300)
    path: str | None = Field(default=None, max_length=300)
    previous_id: str | None = Field(default=None, max_length=300)


class ApprovalInput(Model):
    reviewer: str = Field(min_length=2, max_length=100)


def require_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= 128:
        raise HTTPException(428, "Se requiere Idempotency-Key de 1 a 128 caracteres")
    return value


def reply(result: dict):
    headers = {"ETag": f'"{result["version"]}"'} if "version" in result else {}
    if result.get("audit_id") is not None:
        headers["X-Audit-Id"] = str(result["audit_id"])
    return JSONResponse(result["data"], status_code=result.get("status", 200), headers=headers)


def create_app(
    *,
    data_root: Path | None = None,
    root: Path | None = None,
    database_url: str | None = None,
    seed: bool = True,
) -> FastAPI:
    from trazia.runtime import configure_offline

    configure_offline()
    accounts_enabled = os.getenv("TRAZIA_AUTH", "0") == "1"
    repo = (root or Path(os.getenv("TRAZIA_ROOT", "."))).resolve()
    data = data_root or Path(os.getenv("TRAZIA_DATA", "data"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(data, database_url or os.getenv("TRAZIA_DATABASE_URL"))
        queue = ProcessQueue(lambda identity: run_job(store, identity))
        app.state.store = store
        app.state.queue = queue
        app.state.copilot_limit = asyncio.Semaphore(4)
        if accounts_enabled:
            from .accounts import LoginRate, seed_accounts

            seed_accounts(store)
            app.state.login_rate = LoginRate()
        try:
            if seed and (lote := os.getenv("TRAZIA_LOTE", "").strip()):
                # Datos del reto: las revisiones del lote con sus originales, sin la demo.
                dataset = Path(os.getenv("TRAZIA_DATASET_DIR", "data/Dataset-tecnicasreunidas"))
                await asyncio.to_thread(seed_dataset, store, Path(lote), dataset)
            elif seed:
                seed_demo(store, repo)
            await recover_jobs(store, queue)
            yield
        finally:
            await queue.close()
            store.close()

    app = FastAPI(title="TrazIA-3D", version="0.3", lifespan=lifespan)
    from .admin import ModeloPreferido, RevisionLote, entrada_reintento
    from .admin import router as admin_router
    from .change_proposals import router as proposals_router
    from .copilot_contexts import router as copilot_contexts_router
    from .copilot_voice import router as copilot_voice_router
    from .design_drawings import router as drawings_router
    from .documents import router as documents_router
    from .fichas import router as fichas_router
    from .revision_delete import router as revision_delete_router
    from .snapshots import router as snapshots_router

    for router in (
        documents_router,
        fichas_router,
        revision_delete_router,
        admin_router,
        snapshots_router,
        proposals_router,
        copilot_contexts_router,
        copilot_voice_router,
        drawings_router,
    ):
        app.include_router(router)
    app.add_middleware(ModeloPreferido)
    app.add_middleware(UploadLimit, limit=MAX_UPLOAD + 1024 * 1024)
    app.add_middleware(UploadLimit, limit=MAX_AUDIO_BYTES + 8 * 1024, paths=("/copiloto/voice",))
    if accounts_enabled:
        from .accounts import AccountAccess
        from .accounts import router as accounts_router
        from .catalogue import MAX_DESIGN_BYTES
        from .catalogue import router as catalogue_router

        app.include_router(accounts_router)
        app.include_router(catalogue_router)
        app.add_middleware(
            UploadLimit, limit=MAX_DESIGN_BYTES + 1024**2, paths=("/catalogue/designs",)
        )
        app.add_middleware(UploadLimit, limit=8192, paths=("/auth/login", "/auth/guest"))
        app.add_middleware(AccountAccess, allowed_origins=origins())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "If-Match", "Last-Event-ID"],
        expose_headers=["ETag", "X-Audit-Id"],
    )

    @app.exception_handler(IdempotencyConflict)
    async def conflict(_, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid(_, error):
        issues = issues_for(error, _.path_params.get("path"))
        return JSONResponse(
            {
                "detail": "No se ha guardado el cambio. "
                + "; ".join(f"{i['path']}: {i['message']} {i['action']}" for i in issues),
                "issues": issues,
            },
            status_code=422,
        )

    @app.get("/reference-system")
    def reference_system():
        return REFERENCE_SYSTEM

    @app.post("/review-sessions", status_code=201)
    def start_review_session(
        request: Request,
        body: review_sessions.SessionInput,
        idempotency_key: str | None = Header(None),
    ):
        def action(session):
            record = get_revision(session, body.revision_id)
            return {"data": review_sessions.start(session, record, body), "status": 201}

        return reply(
            request.app.state.store.perform(
                "POST review-sessions", require_key(idempotency_key), body.model_dump(), action
            )
        )

    @app.post("/review-sessions/{session_id}/finish")
    def finish_review_session(request: Request, session_id: str, body: review_sessions.FinishInput):
        with Session(request.app.state.store.engine) as session:
            return review_sessions.finish(session, session_id, body.active_seconds)

    @app.get("/revisions/{identity}/review-metrics")
    def review_metrics(request: Request, identity: str):
        with Session(request.app.state.store.engine) as session:
            record = get_revision(session, identity)
            result = review_sessions.metrics(session, record.id)
            model = Revision.model_validate_json(record.payload)
            return {
                **result,
                "equipment_tag": record.tag,
                "dataset": model.dataset,
                "pending_fields": len(model.pending_review()),
                "approved": model.approval is not None,
            }

    @app.get("/revisions/{identity}/validation")
    def review_validation(request: Request, identity: str):
        with Session(request.app.state.store.engine) as session:
            record = get_revision(session, identity)
            return diagnostics(load_stored_revision(record))

    @app.get("/health")
    def health():
        from trazia.runtime import offline

        return {
            "status": "ok",
            "schema_version": "0.3",
            "queue": "process",
            "offline": offline(),
        }

    @app.post("/documents", status_code=201)
    async def upload(
        request: Request,
        file: Annotated[UploadFile, File()],
        document_id: Annotated[str | None, Form()] = None,
        revision: Annotated[str, Form()] = "A",
        kind: Annotated[Literal["GA", "HDM", "VESOR", "ESTRUCTURA"] | None, Form()] = None,
        equipment_tag: Annotated[str | None, Form(max_length=80)] = None,
        inspect_revision: Annotated[bool, Form()] = False,
        idempotency_key: str | None = Header(None),
    ):
        key = require_key(idempotency_key)
        try:
            revision = validate_revision_label((await request.form()).get("revision", revision))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        content = await file.read(MAX_UPLOAD + 1)
        if not content or len(content) > MAX_UPLOAD:
            raise HTTPException(413, "El documento debe tener entre 1 byte y 25 MiB")
        filename = (file.filename or "documento.pdf").replace("\\", "/").rsplit("/", 1)[-1]
        if Path(filename).suffix.lower() not in (".pdf", ".xlsx", ".png", ".jpg", ".jpeg"):
            raise HTTPException(415, "Formato no admitido: use PDF, XLSX o imagen PNG/JPEG")
        digest = hashlib.sha256(content).hexdigest()
        if equipment_tag is not None:
            from trazia.lectura.clasificar import TAG

            if not TAG.fullmatch(equipment_tag):
                raise HTTPException(422, "El tag del equipo no es válido")
            equipment_tag = equipment_tag.upper()
        logical_id = document_id or f"DOC-{digest[:16]}"
        if not logical_id or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in logical_id
        ):
            raise HTTPException(422, "El identificador documental no es válido")
        body = {
            "filename": filename,
            "sha256": digest,
            "document_id": logical_id,
            "revision": revision,
        }
        if kind is not None:
            body["kind"] = kind
        if equipment_tag is not None:
            body["equipment_tag"] = equipment_tag
        detection = None
        if inspect_revision and Path(filename).suffix.lower() == ".pdf":
            from trazia.ingest import dataset_filename, ingest_bytes

            body["inspect_revision"] = True
            named = dataset_filename(filename)
            detection = {
                "filename_revision": named.revision if named else None,
                "drawing_revision": None,
            }
            try:
                bundle = await asyncio.to_thread(
                    ingest_bytes, content, filename, logical_id, revision
                )
            except ValueError:
                pass
            else:
                if label := bundle.document.drawing_revision:
                    detection["drawing_revision"] = {
                        "value": label.value,
                        "page": label.source.page,
                        "locator": label.source.locator,
                    }

        def action(session):
            request.app.state.store.put(content)
            record = DocumentRecord(
                id=str(uuid4()),
                document_id=logical_id,
                filename=filename,
                revision=revision,
                sha256=digest,
                size=len(content),
                kind=kind,
                equipment_tag=equipment_tag,
            )
            session.add(record)
            data = record.model_dump()
            if detection is not None:
                data["revision_detection"] = detection
            return {"data": data, "status": 201}

        return reply(request.app.state.store.perform("POST /documents", key, body, action))

    @app.get("/equipment")
    def equipment(request: Request):
        from .fichas import hidden_fichas

        with Session(request.app.state.store.engine) as session:
            hidden = hidden_fichas(session)
            rows = [
                row
                for row in session.exec(
                    select(RevisionRecord).order_by(
                        RevisionRecord.project_id, RevisionRecord.tag, RevisionRecord.equipment_id
                    )
                ).all()
                if (row.project_id, row.equipment_id) not in hidden
            ]
            grouped = {}
            for row in sorted(
                rows, key=lambda item: (item.project_id, item.tag, revision_order(item.revision))
            ):
                item = grouped.setdefault(
                    (row.project_id, row.equipment_id),
                    {
                        "tag": row.tag,
                        "kind": "Recipiente vertical",
                        "area": "Unidad 100",
                        "revisions": [],
                        "revision_meta": {},
                        "status": "draft",
                        "illustrative": False,
                        "ifcUrl": "",
                        "project_id": row.project_id,
                        "equipment_id": row.equipment_id,
                    },
                )
                revision = load_stored_revision(row)
                item["tag"] = row.tag
                item["kind"] = revision.equipment.kind
                item["revisions"].append(row.revision)
                ifc_url = f"/revisions/{quote(row.id, safe='')}/ifc?draft=true&v={row.version}"
                item["revision_meta"][row.revision] = {
                    "version": row.version,
                    "dataset": revision.dataset,
                    "lod": revision.equipment.lod,
                    "identity": row.id,
                    "ifcUrl": ifc_url,
                    "documents": [
                        {"id": document.id, "filename": document.filename}
                        for document in revision.documents
                    ],
                    "approved": revision.approval is not None,
                }
                item["ifcUrl"] = ifc_url
                item["revision_id"] = row.id
                item["status"] = "approved" if revision.approval else "draft"
            return list(grouped.values())

    @app.get("/equipment/{tag}/revisions/{rev}", response_model=Revision)
    def revision(request: Request, tag: str, rev: str, project_id: str = "DEMO-PLANT"):
        with Session(request.app.state.store.engine) as session:
            row = session.exec(
                select(RevisionRecord).where(
                    RevisionRecord.tag == tag,
                    RevisionRecord.revision == rev,
                    RevisionRecord.project_id == project_id,
                )
            ).first()
            if row is None:
                raise HTTPException(404, "No existe esa revisión del equipo")
            return JSONResponse(
                load_stored_revision(row).model_dump(mode="json"),
                headers={"ETag": f'"{row.version}"'},
            )

    @app.get("/revisions/{identity}", response_model=Revision)
    def revision_by_id(request: Request, identity: str):
        with Session(request.app.state.store.engine) as session:
            row = get_revision(session, identity)
            return JSONResponse(
                load_stored_revision(row).model_dump(mode="json"),
                headers={"ETag": f'"{row.version}"'},
            )

    @app.get("/revisions/{identity}/fields")
    def review_fields(request: Request, identity: str):
        with Session(request.app.state.store.engine) as session:
            row = get_revision(session, identity)
            model = load_stored_revision(row)
            return JSONResponse(
                {
                    path: value.model_dump(mode="json")
                    for path, value in model.traced_fields().items()
                },
                headers={"ETag": f'"{row.version}"'},
            )

    @app.patch("/revisions/{identity}/fields/{path}", response_model=Revision)
    def update_field(
        request: Request,
        identity: str,
        path: str,
        body: FieldInput,
        if_match: str | None = Header(None),
        idempotency_key: str | None = Header(None),
    ):
        def action(session):
            record = get_revision(session, identity)
            check_match(record, if_match)
            model = load_stored_revision(record)
            target = model.traced_fields().get(path)
            if target is None:
                raise HTTPException(404, "No existe ese campo")
            if body.expected is not None and type(target).model_validate(body.expected) != target:
                raise HTTPException(
                    412, "El campo ha cambiado; recarga y revisa su evidencia antes de editar"
                )
            if body.source is not None and (
                body.source.design is not None or body.source.channel == "diseno"
            ):
                raise HTTPException(422, "Una corrección debe citar un original de la revisión")
            if body.state == "corrected" and body.value is None:
                raise HTTPException(422, "Corregir requiere un valor")
            from trazia.families.preliminares import es_preliminar

            if (
                es_preliminar(target)
                and body.state in ("accepted", "candidate")
                and body.value is None
            ):
                raise HTTPException(
                    422,
                    "Es un valor preliminar: falta en el plano. Corrígelo con el valor real.",
                )
            expected = {
                "accept": "accepted",
                "correct": "corrected",
                "assume": "assumed",
                "reject": "abstained",
            }
            if body.action and expected[body.action] != body.state:
                raise HTTPException(422, "La acción no corresponde al estado solicitado")
            if body.review_session_id:
                review_sessions.validate_clock(
                    session, body.review_session_id, record.id, body.actor, body.seconds
                )
            from .normalization import normalize_patch

            value, unit, source = normalize_patch(target, body)
            if body.value is not None:
                target.value = value
                target.interval = None
                if body.source is None:
                    target.source = target.source.model_copy(
                        update={
                            "channel": "humano",
                            "grounded": None,
                            "strategy": None,
                            "model": None,
                            "prompt_sha256": None,
                        }
                    )
            if unit is not None:
                target.unit = unit
                target.interval = None
            if source is not None:
                target.source = source
            target.state = body.state
            if "explanation" in body.model_fields_set:
                target.explanation = body.explanation
            if body.action == "reject":
                target.explanation = "Rechazado por el revisor. " + (
                    body.explanation or "Hace falta una lectura nueva."
                )
            model.approval = None
            model = Revision.model_validate_json(model.model_dump_json())
            return save_revision(
                session,
                record,
                model,
                path=path,
                actor=body.actor,
                seconds=body.seconds,
                review_session_id=body.review_session_id,
            )

        fingerprint = {**body.model_dump(mode="json"), "if_match": if_match}
        result = request.app.state.store.perform(
            f"PATCH {identity}/{path}", require_key(idempotency_key), fingerprint, action
        )
        return reply(result)

    @app.post("/revisions/{identity}/audit/{audit_id}/undo", response_model=Revision)
    def undo_field(
        request: Request,
        identity: str,
        audit_id: int,
        body: UndoInput,
        if_match: str | None = Header(None),
        idempotency_key: str | None = Header(None),
    ):
        def action(session):
            record = get_revision(session, identity)
            check_match(record, if_match)
            original = session.get(AuditRecord, audit_id)
            if not original or original.revision_id != record.id or original.path.startswith("$"):
                raise HTTPException(404, "No existe esa acción de campo en esta revisión")
            if session.exec(select(AuditRecord).where(AuditRecord.undo_of == audit_id)).first():
                raise HTTPException(409, "Esta acción ya se ha deshecho")
            model = load_stored_revision(record)
            before = Revision.model_validate_json(original.before_json)
            after = Revision.model_validate_json(original.after_json)
            target = model.traced_fields().get(original.path)
            old = before.traced_fields().get(original.path)
            changed = after.traced_fields().get(original.path)
            if target is None or old is None or changed is None or target != changed:
                raise HTTPException(
                    409, "El campo ha cambiado después de esta acción; recárgalo antes de deshacer"
                )
            if body.review_session_id:
                review_sessions.validate_clock(
                    session, body.review_session_id, record.id, body.actor, body.seconds
                )
            for key in type(old).model_fields:
                setattr(target, key, getattr(old, key))
            model.approval = None
            model = Revision.model_validate_json(model.model_dump_json())
            return save_revision(
                session,
                record,
                model,
                path=original.path,
                actor=body.actor,
                seconds=body.seconds,
                review_session_id=body.review_session_id,
                undo_of=audit_id,
            )

        result = request.app.state.store.perform(
            f"POST undo/{identity}/{audit_id}",
            require_key(idempotency_key),
            {**body.model_dump(), "if_match": if_match},
            action,
        )
        return reply(result)

    @app.post("/revisions/{identity}/approve", response_model=Revision)
    def approve_revision(
        request: Request,
        identity: str,
        body: ApprovalInput,
        if_match: str | None = Header(None),
        idempotency_key: str | None = Header(None),
    ):
        def action(session):
            record = get_revision(session, identity)
            check_match(record, if_match)
            model = load_stored_revision(record)
            if model.pending_review():
                raise HTTPException(409, "Quedan campos sin aceptar o corregir")
            originals = {
                d.id: read_original(request.app.state.store, d.sha256) for d in model.documents
            }
            try:
                approved = approve(model, body.reviewer, originals)
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
            return save_revision(session, record, approved, path="$approval", actor=body.reviewer)

        return reply(
            request.app.state.store.perform(
                f"POST approve/{identity}",
                require_key(idempotency_key),
                {**body.model_dump(), "if_match": if_match},
                action,
            )
        )

    @app.get("/revisions/{identity}/audit")
    def audit(request: Request, identity: str):
        with Session(request.app.state.store.engine) as session:
            row = get_revision(session, identity)
            actions = session.exec(
                select(AuditRecord)
                .where(AuditRecord.revision_id == row.id)
                .order_by(AuditRecord.id)
            ).all()
            return {
                "actions": [a.model_dump() for a in actions],
                "review_seconds": (
                    sum(a.seconds or 0 for a in actions)
                    if any(a.seconds is not None for a in actions)
                    else None
                ),
                "timed_actions": sum(a.seconds is not None for a in actions),
                "untimed_actions": sum(a.seconds is None for a in actions),
                "measurement": "sum_reported_action_seconds",
            }

    @app.get("/revisions/{identity}/ifc")
    def ifc(
        request: Request,
        identity: str,
        schema: Literal["IFC4", "IFC4X3", "IFC2X3"] = "IFC4",
        draft: bool = False,
    ):
        with Session(request.app.state.store.engine) as session:
            row = get_revision(session, identity)
            model = load_stored_revision(row)
        if not draft and model.approval is not None:
            for document in model.documents:
                read_original(request.app.state.store, document.sha256)
        try:
            content = (
                build_ifc(model, draft=draft, schema=schema, details=model.dataset == "synthetic")
                .to_string()
                .encode()
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        filename = quote(f"{model.equipment.tag.value}_{model.revision}", safe="")
        return Response(
            content,
            media_type="application/x-step",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
                f"{'_DRAFT' if draft else ''}.ifc"
            },
        )

    @app.get("/revisions/{identity}/documents/{document_id}")
    def original(request: Request, identity: str, document_id: str):
        with Session(request.app.state.store.engine) as session:
            model = load_stored_revision(get_revision(session, identity))
        document = next((d for d in model.documents if d.id == document_id), None)
        if document is None:
            raise HTTPException(404, "El documento no pertenece a la revisión")
        return Response(
            read_original(request.app.state.store, document.sha256),
            media_type="application/pdf"
            if document.filename.lower().endswith(".pdf")
            else "application/octet-stream",
        )

    @app.post("/equipment/{tag}/jobs", status_code=202)
    async def create_job(
        request: Request, tag: str, body: JobInput, idempotency_key: str | None = Header(None)
    ):
        return await submit_job(request, tag, body, idempotency_key)

    @app.post("/jobs", status_code=202)
    async def create_equipment_job(
        request: Request, body: EquipmentJobInput, idempotency_key: str | None = Header(None)
    ):
        # El tag va en el cuerpo para admitir identificadores de plano con barras.
        return await submit_job(request, body.tag, body, idempotency_key)

    @app.post("/admin/lote/reintentar", status_code=202)
    async def retry_batch_revision(
        request: Request, body: RevisionLote, idempotency_key: str | None = Header(None)
    ):
        key = require_key(idempotency_key)
        config = await asyncio.to_thread(entrada_reintento, request, body)
        return await submit_job(request, body.tag, EquipmentJobInput.model_validate(config), key)

    async def submit_job(request: Request, tag: str, body: JobInput, idempotency_key: str | None):
        def action(session):
            logical_ids = set()
            for identity in body.documents:
                document = session.get(DocumentRecord, identity)
                if document is None:
                    raise HTTPException(404, "No existe un documento del trabajo")
                if document.document_id in logical_ids:
                    raise HTTPException(422, "Identificadores documentales duplicados")
                logical_ids.add(document.document_id)
            identity = f"{body.project_id}:{body.equipment_id}:{body.revision}"
            keys = ("project_id", "equipment_id", "revision")
            if request.app.state.store.engine.dialect.name == "postgresql":
                session.exec(select(func.pg_advisory_xact_lock(func.hashtext(identity))))
                request_payload = cast(JobRecord.request_json, JSONB)
                project, equipment_id, revision = (request_payload[key].as_string() for key in keys)
            else:
                project, equipment_id, revision = (
                    func.json_extract(JobRecord.request_json, f"$.{key}") for key in keys
                )
            active = session.exec(
                select(JobRecord.id).where(
                    JobRecord.kind == "pipeline",
                    JobRecord.status.in_(("queued", "running")),
                    project == body.project_id,
                    equipment_id == body.equipment_id,
                    revision == body.revision,
                )
            ).first()
            if active:
                raise HTTPException(409, "Ya hay un trabajo activo para la revisión de destino")
            existing = session.get(RevisionRecord, identity)
            if existing is not None:
                from .revision_delete import reemplazo_bloqueado

                if reason := reemplazo_bloqueado(session, existing):
                    raise HTTPException(409, reason)
            if body.previous_id:
                previous = get_revision(session, body.previous_id)
                if (previous.project_id, previous.equipment_id) != (
                    body.project_id,
                    body.equipment_id,
                ):
                    raise HTTPException(
                        422, "La memoria debe pertenecer al mismo equipo y proyecto"
                    )
                if load_stored_revision(previous).dataset != body.dataset:
                    raise HTTPException(422, "La revisión anterior debe usar el mismo dataset")
            from .accounts import request_username

            config = {
                **body.model_dump(mode="json"),
                "tag": tag,
                "actor": request_username(request),
            }
            if body.previous_id:
                config["previous_id"] = previous.id
            from trazia.runtime import offline

            if offline():
                from .job_cache import CacheMiss, load

                try:
                    load(request.app.state.store, session, config)
                except CacheMiss as failure:
                    raise HTTPException(409, str(failure)) from failure
            job = JobRecord(
                id=str(uuid4()),
                tag=tag,
                request_json=json.dumps(config),
            )
            session.add(job)
            return {"data": {"job_id": job.id, "status": "queued"}, "status": 202}

        result = request.app.state.store.perform(
            f"POST jobs/{tag}",
            require_key(idempotency_key),
            body.model_dump(mode="json", exclude={"tag"}),
            action,
        )
        await request.app.state.queue.enqueue(result["data"]["job_id"])
        return reply(result)

    @app.get("/jobs/{identity}")
    def job(request: Request, identity: str, include_candidates: bool = False):
        with Session(request.app.state.store.engine) as session:
            record = session.get(JobRecord, identity)
            if record is None:
                raise HTTPException(404, "No existe ese trabajo")
            result = record.model_dump(exclude={"request_json", "run_json", "warnings_json"})
            result["run"] = json.loads(record.run_json) if record.run_json else None
            result["warnings"] = json.loads(record.warnings_json)
            if record.kind == "pipeline":
                config = json.loads(record.request_json)
                result["strategy"] = config.get("strategy")
                result["dataset"] = config.get("dataset")
                result["documents"] = [
                    doc.filename
                    for doc_id in config.get("documents", [])
                    if (doc := session.get(DocumentRecord, doc_id)) is not None
                ]
        if include_candidates and result["status"] == "error" and result["result_sha256"]:
            try:
                partial = json.loads(request.app.state.store.read(result["result_sha256"]))
                result["missing_data"] = partial["missing_data"]
                result["candidates"] = partial["candidates"]
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise HTTPException(
                    409, "No se puede verificar el resultado del trabajo"
                ) from error
        return result

    @app.post("/jobs/{identity}/cancel")
    async def cancel(request: Request, identity: str, idempotency_key: str | None = Header(None)):
        def action(session):
            record = session.get(JobRecord, identity)
            if record is None:
                raise HTTPException(404, "No existe ese trabajo")
            if record.status not in TERMINAL:
                record.cancel_requested, record.status = True, "cancelled"
                record.updated_at, record.lease_until = time.time(), None
                session.add(record)
            return {"data": {"job_id": identity, "status": record.status}}

        result = request.app.state.store.perform(
            f"POST cancel/{identity}", require_key(idempotency_key), {}, action
        )
        await request.app.state.queue.cancel(identity)
        return reply(result)

    @app.get("/jobs/{identity}/events")
    async def events(request: Request, identity: str, last_event_id: int = Header(0, ge=0)):
        with Session(request.app.state.store.engine) as session:
            if session.get(JobRecord, identity) is None:
                raise HTTPException(404, "No existe ese trabajo")

        async def stream():
            cursor, heartbeat = last_event_id, time.monotonic()
            while not await request.is_disconnected():
                with Session(request.app.state.store.engine) as session:
                    record = session.get(JobRecord, identity)
                    finished = record.status in TERMINAL
                    batch = session.exec(
                        select(EventRecord)
                        .where(EventRecord.job_id == identity, EventRecord.id > cursor)
                        .order_by(EventRecord.id)
                        .limit(100)
                    ).all()
                for entry in batch:
                    cursor = entry.id
                    yield f"id: {cursor}\nevent: stage\ndata: {entry.model_dump_json()}\n\n"
                if finished and len(batch) < 100:
                    yield f"event: complete\ndata: {json.dumps({'status': record.status})}\n\n"
                    break
                if time.monotonic() - heartbeat > 10:
                    yield ": heartbeat\n\n"
                    heartbeat = time.monotonic()
                await asyncio.sleep(0.15)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/diff")
    def diff(
        request: Request,
        before: str = Query("A", alias="from"),
        after: str = Query("B", alias="to"),
        layers: bool = False,
        marks: bool = False,
    ):
        with Session(request.app.state.store.engine) as session:
            a = load_stored_revision(get_revision(session, before))
            b = load_stored_revision(get_revision(session, after))
        try:
            originals = None
            if layers:
                originals = {
                    d.sha256: read_original(request.app.state.store, d.sha256)
                    for d in a.documents + b.documents
                }
            elif marks:
                originals = {}
                for document in b.documents:
                    if not document.filename.lower().endswith(".pdf"):
                        continue
                    try:
                        originals[document.sha256] = request.app.state.store.read(document.sha256)
                    except (OSError, ValueError):
                        # Un original perdido o no verificable no impide leer los demás.
                        continue
            report = compare(
                a,
                b,
                include_geometry=layers,
                originals=originals,
                include_visual=layers or not marks,
            )
            return report
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/diff/bcf")
    def bcf(
        request: Request,
        before: str = Query("A", alias="from"),
        after: str = Query("B", alias="to"),
    ):
        from trazia.bcf import export_bcf

        with Session(request.app.state.store.engine) as session:
            a = load_stored_revision(get_revision(session, before))
            b = load_stored_revision(get_revision(session, after))
        try:
            payload = export_bcf(a, b)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return Response(
            payload,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=changes_DRAFT.bcfzip"},
        )

    @app.get("/diff/visual")
    def diff_visual(
        request: Request,
        document_id: str,
        page: int = Query(1, ge=1),
        before: str = Query("A", alias="from"),
        after: str = Query("B", alias="to"),
    ):
        from trazia.families.change_detection import render_pdf, visual_diff_images

        with Session(request.app.state.store.engine) as session:
            a = load_stored_revision(get_revision(session, before))
            b = load_stored_revision(get_revision(session, after))
        originals = []
        for revision in (a, b):
            document = next(
                (
                    d
                    for d in revision.documents
                    if d.id == document_id and d.filename.lower().endswith(".pdf")
                ),
                None,
            )
            if document is None:
                raise HTTPException(404, "Falta ese PDF en una revisión")
            try:
                originals.append(
                    render_pdf(read_original(request.app.state.store, document.sha256), page)
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
        result, image = visual_diff_images(*originals, return_png=True)
        if image is None:
            raise HTTPException(409, result.get("detail", "No se pudo alinear"))
        return Response(image, media_type="image/png", headers={"X-Alignment": result["method"]})

    @app.post("/copiloto", response_model=CopilotAnswer)
    async def copilot(request: Request, body: CopilotInput):
        if not body.question.strip():
            raise HTTPException(422, "Escribe una pregunta")
        store = request.app.state.store
        with Session(store.engine) as session:
            record = get_revision(session, body.revision_id)
            revision = load_stored_revision(record)
            identity, version = record.id, record.version
            previous = None
            if body.previous_id:
                previous = load_stored_revision(get_revision(session, body.previous_id))
                if (previous.project_id, previous.equipment.id) != (
                    revision.project_id,
                    revision.equipment.id,
                ):
                    raise HTTPException(422, "La comparación debe ser del mismo proyecto y equipo")
            # Índice del proyecto para «¿qué equipos hay?»: solo etiquetas y revisiones.
            project = {}
            for tag, label in session.exec(
                select(RevisionRecord.tag, RevisionRecord.revision)
                .where(RevisionRecord.project_id == record.project_id)
                .order_by(RevisionRecord.tag, RevisionRecord.revision)
            ).all():
                project.setdefault(tag, []).append(label)
        try:
            async with asyncio.timeout(15):
                async with request.app.state.copilot_limit:
                    return await answer_cached(
                        revision,
                        body.question.strip(),
                        cache_root=store.root / "cache/copilot",
                        call=ask_copilot,
                        revision_id=identity,
                        revision_version=version,
                        path=body.path,
                        previous=previous,
                        project=project,
                        read_document=store.read,
                    )
        except CopilotUnavailable as error:
            raise HTTPException(503, str(error)) from error
        except TimeoutError as error:
            raise HTTPException(503, "El copiloto ha agotado el tiempo de consulta") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    return app

"""Lote del dataset, métricas de funcionamiento e historial de exportaciones.

- `GET /lote/resumen`: estado de cada revisión del lote cargado (`TRAZIA_LOTE`), también las que
  no llegan a modelo, con su motivo. Lo usa Documentos.
- `GET /admin/metricas`: trabajos, etapas, revisiones, llamadas a modelos de lenguaje y lote,
  con los totales del periodo anterior para comparar.
- `GET|POST /admin/exportaciones`: historial de ficheros exportados con la huella de sus datos y
  si esa huella sigue coincidiendo con la revisión actual (`vigente`).
- `GET /admin/revisiones/{id}/resumen`: estado, huella, campos y exportaciones de una revisión.
- `GET /ajustes/modelos`: modelos de lenguaje que se pueden elegir en Ajustes.
- `GET /admin/revisiones/{id}/campos.csv` y `/informe.pdf`: campos con valor, unidad, fuente y
  confianza, y un informe de la revisión. Ambos dicen si la revisión está aprobada o en borrador.

Con cuentas activas, `/admin/*` es solo para administradores (`accounts.AccountAccess`).
"""

import csv
import io
import json
import os
import statistics
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import func
from sqlmodel import Session, select

from trazia.model import Model
from trazia.store import AuditRecord, EventRecord, JobRecord, RevisionRecord

from .repository import get_revision, load_stored_revision, read_original

router = APIRouter()


def _lote() -> Path | None:
    lote = os.getenv("TRAZIA_LOTE", "").strip()
    return Path(lote) if lote else None


def _leer_jsonl(path: Path):
    try:
        with path.open(encoding="utf-8") as lineas:
            for linea in lineas:
                try:
                    fila = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(fila, dict):
                    yield fila
    except OSError:
        return


class ModeloPreferido:
    """Lee la cookie `trazia_modelo` y la deja en `cloud.PREFERENCIA` durante la petición."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from trazia.copilot import cloud

        valor = "auto"
        for clave, contenido in scope.get("headers", []):
            if clave != b"cookie":
                continue
            for parte in contenido.decode("latin-1").split(";"):
                nombre, _, dato = parte.strip().partition("=")
                if nombre == "trazia_modelo":
                    valor = dato
        token = cloud.PREFERENCIA.set(valor if valor in cloud.PREFERENCIAS else "auto")
        try:
            await self.app(scope, receive, send)
        finally:
            cloud.PREFERENCIA.reset(token)


@router.get("/ajustes/modelos")
def ajustes_modelos(request: Request):
    from trazia.copilot import cloud

    return {"actual": cloud.PREFERENCIA.get(), "opciones": cloud.modelos()}


def lote_resumen() -> list[dict]:
    """Filas del lote cargado, sin filtrar."""
    lote = _lote()
    if lote is None:
        return []
    try:
        filas = json.loads((lote / "resumen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    campos = (
        "tag",
        "revision",
        "documentos",
        "estado",
        "error",
        "familia",
        "lod",
        "boquillas",
        "lod",
        "campos",
        "pendientes",
        "cambios",
        "documentos_con_error",
        "avisos_documentos",
    )
    proyecto = os.getenv("TRAZIA_LOTE_PROYECTO", "INDESIAHACK")
    return [
        {k: fila.get(k) for k in campos} | {"segundos": fila.get("segundos"), "proyecto": proyecto}
        for fila in filas
    ]


@router.get("/lote/resumen")
def lote_resumen_visible(request: Request):
    """Filas del lote, sin las fichas que alguien borró o retiró del catálogo."""
    from .fichas import retired_tags, tag_key

    with Session(request.app.state.store.engine) as session:
        retiradas = retired_tags(session)
    return [
        fila
        for fila in lote_resumen()
        if (fila["proyecto"], tag_key(str(fila.get("tag") or ""))) not in retiradas
    ]


_TIPOS = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/lote/documentos/{nombre}")
def lote_documento(nombre: str):
    """Original de cualquier revisión del lote, también de las que no llegan a modelo.

    Solo sirve ficheros que el propio resumen del lote cita, buscados por nombre dentro del
    dataset; así Documentos puede abrir todos los planos y hojas de datos del reto.
    """
    lote = _lote()
    if lote is None or "/" in nombre or "\\" in nombre:
        raise HTTPException(404, "Documento no encontrado")
    try:
        filas = json.loads((lote / "resumen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        filas = []
    citados = {d.lower() for fila in filas for d in fila.get("documentos") or []}
    if nombre.lower() not in citados:
        raise HTTPException(404, "Documento no encontrado en el lote")
    entrada = Path(os.getenv("TRAZIA_DATASET_DIR", "data/Dataset-tecnicasreunidas")).resolve()
    ruta = next(
        (p for p in sorted(entrada.rglob("*")) if p.is_file() and p.name.lower() == nombre.lower()),
        None,
    )
    if ruta is None or ruta.suffix.lower() not in _TIPOS:
        raise HTTPException(404, "El original no está en el dataset de este equipo")
    return Response(
        ruta.read_bytes(),
        media_type=_TIPOS[ruta.suffix.lower()],
        headers={"Content-Disposition": f'inline; filename="{ruta.name}"'},
    )


class RevisionLote(Model):
    proyecto: str
    tag: str
    revision: str


@router.get("/admin/lote")
def lote_activo(request: Request):
    proyecto = os.getenv("TRAZIA_LOTE_PROYECTO", "INDESIAHACK")
    filas = {
        (proyecto, f["tag"], f["revision"]): {**f, "proyecto": proyecto} for f in lote_resumen()
    }
    with Session(request.app.state.store.engine) as session:
        trabajos = session.exec(
            select(JobRecord).where(JobRecord.kind == "pipeline").order_by(JobRecord.created_at)
        ).all()
        for job in trabajos:
            config = json.loads(job.request_json)
            if not config.get("project_id") or not config.get("revision"):
                continue
            key = (config["project_id"], job.tag, config["revision"])
            fila = filas.setdefault(key, {"proyecto": key[0], "tag": key[1], "revision": key[2]})
            fila.update(
                job_id=job.id,
                estado="ok" if job.status == "done" else job.status,
                error=job.error,
                segundos=job.elapsed_seconds,
            )
    return list(filas.values())


REINTENTABLES = frozenset({"error", "timeout", "faltan_datos", "cancelled"})


def entrada_reintento(request: Request, body: RevisionLote):
    from hashlib import sha256

    from trazia.lote import agrupar, identificador
    from trazia.store import DocumentRecord

    fila = next(
        (
            f
            for f in lote_activo(request)
            if (f["proyecto"], f["tag"], f["revision"]) == (body.proyecto, body.tag, body.revision)
        ),
        None,
    )
    if fila is None:
        raise HTTPException(409, "Esta revisión no está pendiente de reintento.")
    if fila.get("estado") == "ok":
        raise HTTPException(409, "Esta revisión ya tiene modelo: no hay nada que reintentar.")
    store = request.app.state.store
    # Un trabajo en curso llega a la cola, que responde igual a una repetición idempotente y
    # rechaza un segundo trabajo activo para la misma revisión.
    if fila.get("job_id"):
        with Session(store.engine) as session:
            config = json.loads(session.get(JobRecord, fila["job_id"]).request_json)
            config.pop("actor", None)
            return config
    if fila["estado"] not in REINTENTABLES:
        raise HTTPException(409, "Esta revisión no está pendiente de reintento.")

    entrada = Path(os.getenv("TRAZIA_DATASET_DIR", "data/Dataset-tecnicasreunidas")).resolve()
    docs = agrupar(entrada).get(body.tag, {}).get(body.revision, [])
    if not docs or sorted(d.path.name for d in docs) != sorted(fila.get("documentos") or []):
        raise HTTPException(409, "Los originales del lote no están disponibles para esta revisión.")
    ids = []
    with Session(store.engine) as session:
        for doc in docs:
            if not doc.path.resolve().is_relative_to(entrada):
                raise HTTPException(409, "El original está fuera del directorio del lote.")
            digest = store.put(doc.path.read_bytes())
            identity = sha256(
                json.dumps([doc.document_id, doc.path.name, body.revision, digest]).encode()
            ).hexdigest()
            session.merge(
                DocumentRecord(
                    id=identity,
                    document_id=doc.document_id,
                    filename=doc.path.name,
                    revision=body.revision,
                    sha256=digest,
                    size=doc.path.stat().st_size,
                )
            )
            ids.append(identity)
        session.commit()
    return {
        "tag": body.tag,
        "revision": body.revision,
        "project_id": body.proyecto,
        "equipment_id": identificador(body.tag).lower(),
        "documents": ids,
        "strategy": "lectura",
        "dataset": os.getenv("TRAZIA_LOTE_DATASET", "real"),
        "providers": [],
    }


def _percentil(valores: list[float], q: float) -> float | None:
    if not valores:
        return None
    if len(valores) == 1:
        return round(valores[0], 2)
    return round(statistics.quantiles(valores, n=100, method="inclusive")[int(q) - 1], 2)


def _instante(entrada: dict) -> float | None:
    try:
        return datetime.fromisoformat(entrada["at"]).timestamp()
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _fecha(instante: float) -> str:
    return datetime.fromtimestamp(instante, timezone.utc).isoformat(timespec="seconds")


def _trabajo_visible(trabajo: JobRecord) -> dict:
    datos = json.loads(trabajo.request_json)
    return {
        "id": trabajo.id,
        "equipo": trabajo.tag,
        "tipo": trabajo.kind,
        "estado": trabajo.status,
        "fecha": _fecha(trabajo.created_at),
        "autor": datos.get("actor"),
    }


def _actividad_revisiones(session: Session, revisiones, aprobaciones) -> list[dict]:
    actividad = {}

    def anotar(identity, instante, actor, accion):
        anterior = actividad.get(identity)
        if anterior is None or anterior[0] < instante:
            actividad[identity] = (instante, actor, accion)

    for identity, approval in aprobaciones.items():
        if (instante := _instante({"at": approval.get("timestamp")})) is not None:
            anotar(identity, instante, approval.get("reviewer"), "aprobada")
    ultimas_ediciones = select(func.max(AuditRecord.id)).group_by(AuditRecord.revision_id)
    for edicion in session.exec(select(AuditRecord).where(AuditRecord.id.in_(ultimas_ediciones))):
        if edicion.path != "$approval" or edicion.revision_id not in aprobaciones:
            anotar(edicion.revision_id, edicion.created_at, edicion.actor, "actualizada")
    trabajos = session.exec(
        select(JobRecord).where(
            JobRecord.kind == "pipeline",
            JobRecord.status == "done",
            JobRecord.revision_id.is_not(None),
        )
    )
    for trabajo in trabajos:
        anotar(
            trabajo.revision_id,
            trabajo.updated_at,
            json.loads(trabajo.request_json).get("actor"),
            "creada",
        )
    por_id = {revision.id: revision for revision in revisiones}
    return [
        {
            "id": identity,
            "equipo": por_id[identity].tag,
            "proyecto": por_id[identity].project_id,
            "revision": por_id[identity].revision,
            "accion": accion,
            "fecha": _fecha(instante),
            "autor": actor,
        }
        for identity, (instante, actor, accion) in sorted(
            actividad.items(), key=lambda item: (item[1][0], item[0]), reverse=True
        )
        if identity in por_id
    ][:5]


@router.get("/admin/metricas")
def metricas(request: Request, rango: Literal["1h", "24h", "7d"] = "24h"):
    ahora = time.time()
    cubos, paso = {"1h": (12, 300), "24h": (24, 3600), "7d": (7, 86400)}[rango]
    desde = ahora - cubos * paso

    def indice(t):
        return min(cubos - 1, int((t - desde) // paso))

    def serie(instantes):
        valores = [0] * cubos
        for t in instantes:
            if desde <= t <= ahora:
                valores[indice(t)] += 1
        return valores

    store = request.app.state.store
    with Session(store.engine) as session:
        trabajos = session.exec(
            select(JobRecord).where(JobRecord.created_at.between(desde, ahora))
        ).all()
        finalizados = session.exec(
            select(JobRecord.updated_at).where(
                JobRecord.updated_at.between(desde, ahora), JobRecord.status == "done"
            )
        ).all()
        activos = dict(
            session.exec(
                select(JobRecord.status, func.count())
                .where(JobRecord.status.in_(("queued", "running")))
                .group_by(JobRecord.status)
            ).all()
        )
        recientes = session.exec(
            select(JobRecord).order_by(JobRecord.created_at.desc(), JobRecord.id.desc()).limit(5)
        ).all()
        errores = session.exec(
            select(JobRecord)
            .where(
                JobRecord.updated_at.between(desde, ahora),
                JobRecord.status.in_(("error", "timeout")),
            )
            .order_by(JobRecord.updated_at.desc())
        ).all()
        eventos = session.exec(
            select(EventRecord).where(EventRecord.created_at.between(desde, ahora))
        ).all()
        # Mismo tamaño de ventana justo antes: sirve para comparar el periodo con el anterior.
        antes = desde - cubos * paso
        previos = dict(
            session.exec(
                select(JobRecord.status, func.count())
                .where(JobRecord.created_at >= antes, JobRecord.created_at < desde)
                .group_by(JobRecord.status)
            ).all()
        )
        previos_terminados = dict(
            session.exec(
                select(JobRecord.status, func.count())
                .where(
                    JobRecord.updated_at >= antes,
                    JobRecord.updated_at < desde,
                    JobRecord.status.in_(("done", "error", "timeout")),
                )
                .group_by(JobRecord.status)
            ).all()
        )
        previas_duraciones = session.exec(
            select(JobRecord.elapsed_seconds).where(
                JobRecord.created_at >= antes,
                JobRecord.created_at < desde,
                JobRecord.elapsed_seconds.is_not(None),
            )
        ).all()
        revisiones = session.exec(select(RevisionRecord)).all()
        aprobaciones = {
            revision.id: approval
            for revision in revisiones
            if (approval := json.loads(revision.payload).get("approval"))
        }
        actividad_revisiones = _actividad_revisiones(session, revisiones, aprobaciones)
    duraciones = [t.elapsed_seconds for t in trabajos if t.elapsed_seconds is not None]
    etapas: dict[str, Counter] = {}
    histogramas = {}
    for evento in eventos:
        etapas.setdefault(evento.stage, Counter())[evento.status] += 1
        if evento.duration_seconds is not None:
            bins = histogramas.setdefault(evento.stage, [0] * 5)
            bins[sum(evento.duration_seconds >= limite for limite in (1, 5, 15, 60))] += 1
    from trazia.llm.enrutador import registro_path
    from trazia.vision.policy import registry_path

    proveedores = {}
    llamadas = []
    llamadas_previas = 0
    for entrada in _leer_jsonl(registro_path()):
        t = _instante(entrada)
        if entrada.get("estado") != "ok" or t is None:
            continue
        if antes <= t < desde:
            llamadas_previas += 1
        if not desde <= t <= ahora:
            continue
        llamadas.append(t)
        proveedor = proveedores.setdefault(
            entrada.get("proveedor") or "Sin identificar",
            {
                "llamadas": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "coste_eur": 0.0,
                "segundos": [],
                "coste_serie": [0.0] * cubos,
                "tokens_serie": [0] * cubos,
            },
        )
        proveedor["llamadas"] += 1
        i = indice(t)
        for campo in ("tokens_in", "tokens_out"):
            valor = entrada.get(campo)
            if valor is None:
                proveedor[campo] = None
                proveedor["tokens_serie"][i] = None
            else:
                if proveedor[campo] is not None:
                    proveedor[campo] += valor
                if proveedor["tokens_serie"][i] is not None:
                    proveedor["tokens_serie"][i] += valor
        coste = entrada.get("coste_eur") if entrada.get("coste_conocido", True) else None
        if coste is None:
            proveedor["coste_eur"] = None
            proveedor["coste_serie"][i] = None
        else:
            if proveedor["coste_eur"] is not None:
                proveedor["coste_eur"] += coste
            if proveedor["coste_serie"][i] is not None:
                proveedor["coste_serie"][i] += coste
        if entrada.get("segundos") is not None:
            proveedor["segundos"].append(entrada["segundos"])
    for proveedor in proveedores.values():
        proveedor["p50_s"] = _percentil(proveedor.pop("segundos"), 50)
    envios = sum(
        1
        for e in _leer_jsonl(registry_path())
        if (t := _instante(e)) is not None and desde <= t <= ahora
    )
    lote = lote_resumen()
    return {
        "generado": datetime.fromtimestamp(ahora, timezone.utc).isoformat(timespec="seconds"),
        "intervalos": [
            datetime.fromtimestamp(desde + i * paso, timezone.utc).isoformat(timespec="seconds")
            for i in range(cubos)
        ],
        "trabajos": {
            "total": len(trabajos),
            "por_estado": dict(Counter(t.status for t in trabajos)),
            "p50_s": _percentil(duraciones, 50),
            "p95_s": _percentil(duraciones, 95),
            "por_hora": serie(t.created_at for t in trabajos),
            "finalizados_por_hora": serie(finalizados),
            "errores_por_hora": serie(t.updated_at for t in errores),
            "activos": sum(activos.values()),
            "en_cola": activos.get("queued", 0),
            "en_ejecucion": activos.get("running", 0),
            "recientes": [_trabajo_visible(t) for t in recientes],
            "cache": sum(1 for t in trabajos if t.cache_hit),
        },
        "anterior": {
            "trabajos": sum(previos.values()),
            "finalizados": previos_terminados.get("done", 0),
            "errores": previos_terminados.get("error", 0) + previos_terminados.get("timeout", 0),
            "p50_s": _percentil(list(previas_duraciones), 50),
            "llamadas": llamadas_previas,
        },
        "errores": [
            {
                "id": t.id,
                "equipo": t.tag,
                "tipo": t.kind,
                "estado": t.status,
                "motivo": t.error,
                "fecha": _fecha(t.updated_at),
            }
            for t in errores[:20]
        ],
        "duraciones": histogramas,
        "etapas": {nombre: dict(c) for nombre, c in sorted(etapas.items())},
        "revisiones": {
            "total": len(revisiones),
            "aprobadas": len(aprobaciones),
            "recientes": actividad_revisiones,
        },
        "modelos": {
            "llamadas": len(llamadas),
            "envios_externos": envios,
            "por_proveedor": proveedores,
            "por_hora": serie(llamadas),
        },
        "lote": {
            "revisiones": len(lote),
            "con_modelo": sum(1 for f in lote if f["estado"] == "ok"),
            "por_estado": dict(Counter(f["estado"] for f in lote)),
            "segundos_p50": _percentil(
                [f["segundos"] for f in lote if f["segundos"] is not None], 50
            ),
        },
    }


class ExportInput(Model):
    formato: Literal["IFC", "BCF", "CSV", "PDF"]
    revision_id: str = Field(min_length=1, max_length=300)
    previous_id: str | None = Field(default=None, max_length=300)


def _historial(request: Request) -> Path:
    return Path(request.app.state.store.root) / "exportaciones.jsonl"


def _huellas_actuales(request: Request, ids) -> dict[str, str | None]:
    """Huella corta de cada revisión tal como está ahora; `None` si ya no existe."""
    huellas: dict[str, str | None] = {}
    with Session(request.app.state.store.engine) as session:
        for identity in ids:
            record = session.get(RevisionRecord, identity) if identity else None
            try:
                huellas[identity] = (
                    load_stored_revision(record).fingerprint()[:12] if record else None
                )
            except HTTPException:
                huellas[identity] = None
    return huellas


def _con_vigencia(filas: list[dict], huellas: dict[str, str | None]) -> list[dict]:
    """Una exportación está vigente si su huella coincide con los datos actuales."""
    return [
        fila
        | {
            "vigente": None
            if huellas.get(fila.get("revision_id")) is None
            else huellas[fila["revision_id"]] == fila.get("huella")
        }
        for fila in filas
    ]


@router.get("/admin/exportaciones")
def exportaciones(request: Request):
    filas = list(reversed(deque(_leer_jsonl(_historial(request)), maxlen=200)))
    huellas = _huellas_actuales(request, {f.get("revision_id") for f in filas})
    return _con_vigencia(filas, huellas)


@router.get("/admin/revisiones/{identity}/resumen")
def resumen_revision(request: Request, identity: str):
    """Lo que hay que saber antes de exportar: estado, huella, campos y exportaciones previas."""
    revision = _revision(request, identity)
    campos = revision.traced_fields()
    confianzas = [c.source.confidence for c in campos.values() if c.source.confidence is not None]
    huella = revision.fingerprint()[:12]
    previas = _con_vigencia(
        [f for f in _leer_jsonl(_historial(request)) if f.get("revision_id") == identity],
        {identity: huella},
    )
    aprobacion = revision.approval
    return {
        "id": identity,
        "tag": revision.equipment.tag.value,
        "revision": revision.revision,
        "proyecto": revision.project_id,
        "dataset": revision.dataset,
        "huella": huella,
        "aprobacion": {
            "revisor": aprobacion.reviewer,
            "fecha": aprobacion.timestamp.isoformat(timespec="seconds"),
        }
        if aprobacion
        else None,
        "campos": len(campos),
        "por_estado": dict(Counter(c.state for c in campos.values())),
        "pendientes": len(revision.pending_review()),
        "confianza_media": round(statistics.fmean(confianzas), 3) if confianzas else None,
        "documentos": len(revision.documents),
        "exportaciones": len(previas),
        "ultima_exportacion": previas[-1] if previas else None,
    }


@router.post("/admin/exportaciones", status_code=201)
def anotar_exportacion(request: Request, body: ExportInput):
    """Anota una exportación con la huella de los datos con que se genera."""
    from .change_proposals import published_ifc

    store = request.app.state.store
    with Session(store.engine) as session:
        record = get_revision(session, body.revision_id)
        revision = load_stored_revision(record)
        publicado = published_ifc(session, record, revision) if body.formato == "IFC" else None
        previa = (
            load_stored_revision(get_revision(session, body.previous_id))
            if body.previous_id
            else None
        )
    if body.formato == "BCF" and previa is None:
        raise HTTPException(422, "El BCF compara dos revisiones: indica la anterior.")
    if previa and (previa.project_id, previa.equipment.id) != (
        revision.project_id,
        revision.equipment.id,
    ):
        raise HTTPException(422, "Las dos revisiones deben pertenecer al mismo equipo.")
    if body.formato == "IFC":
        from trazia.ifc import build_ifc

        if revision.approval:
            for doc in revision.documents:
                read_original(store, doc.sha256)
        if publicado and not revision.approval:
            contenido = read_original(store, publicado)
        else:
            try:
                contenido = (
                    build_ifc(
                        revision,
                        draft=not revision.approval,
                        details=revision.dataset == "synthetic",
                    )
                    .to_string()
                    .encode()
                )
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
    elif body.formato == "BCF":
        from trazia.bcf import export_bcf

        contenido = export_bcf(previa, revision)
    elif body.formato == "CSV":
        contenido = _csv(revision)
    else:
        contenido = _pdf(revision)
    digest = store.put(contenido)
    alcance = f"{revision.equipment.tag.value} rev {revision.revision}"
    if previa is not None:
        alcance = f"{revision.equipment.tag.value} rev {previa.revision} → {revision.revision}"
    fila = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "formato": body.formato,
        "archivo": digest,
        "nombre": _nombre(revision, {"BCF": "bcfzip"}.get(body.formato, body.formato.lower())),
        "alcance": alcance,
        "revision_id": body.revision_id,
        "huella": revision.fingerprint()[:12],
        "estado": "Aprobado" if revision.approval else "Borrador",
        "usuario": getattr(getattr(request.state, "account", None), "username", None),
    }
    path = _historial(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


@router.get("/admin/exportaciones/{digest}/archivo")
def descargar_exportacion(request: Request, digest: str):
    fila = next((f for f in _leer_jsonl(_historial(request)) if f.get("archivo") == digest), None)
    if not fila:
        raise HTTPException(404, "La exportación no tiene un archivo guardado.")
    tipos = {
        "IFC": "application/x-step",
        "BCF": "application/zip",
        "CSV": "text/csv",
        "PDF": "application/pdf",
    }
    from urllib.parse import quote

    return Response(
        read_original(request.app.state.store, digest),
        media_type=tipos[fila["formato"]],
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(fila["nombre"], safe="")
        },
    )


def _revision(request: Request, identity: str):
    with Session(request.app.state.store.engine) as session:
        return load_stored_revision(get_revision(session, identity))


def _texto(valor) -> str:
    if isinstance(valor, float):
        return f"{valor:g}"
    return "" if valor is None else str(valor)


def _filas(revision) -> list[dict]:
    filas = []
    for ruta, campo in revision.traced_fields().items():
        fuente = campo.source
        filas.append(
            {
                "campo": ruta,
                "valor": _texto(getattr(campo, "value", None)),
                "unidad": _texto(getattr(campo, "unit", None)),
                "documento": fuente.document_id,
                "pagina": _texto(fuente.page),
                "confianza": _texto(fuente.confidence),
                "estado": _texto(campo.state),
            }
        )
    return filas


def _nombre(revision, extension: str) -> str:
    estado = "APROBADO" if revision.approval else "DRAFT"
    tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in revision.equipment.tag.value)
    return f"{tag}_rev{revision.revision}_{estado}.{extension}"


def _csv(revision) -> bytes:
    salida = io.StringIO()
    escritor = csv.DictWriter(
        salida,
        fieldnames=["campo", "valor", "unidad", "documento", "pagina", "confianza", "estado"],
    )
    escritor.writeheader()
    escritor.writerows(_filas(revision))
    return salida.getvalue().encode("utf-8-sig")


def _pdf(revision) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        TableStyle,
    )

    salida = io.BytesIO()
    doc = SimpleDocTemplate(
        salida,
        pagesize=landscape(A4),
        title=f"Informe de revisión {revision.equipment.tag.value}",
        leftMargin=34,
        rightMargin=34,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    azul = colors.HexColor("#163f61")
    styles["Title"].alignment = TA_LEFT
    styles["Title"].textColor = azul
    styles["Title"].fontSize = 26
    styles["Title"].leading = 31
    styles["Title"].spaceAfter = 16
    filas = _filas(revision)
    titulo = escape(str(revision.equipment.tag.value))
    etiqueta = escape(str(revision.revision))
    estado = (
        "Aprobado por " + escape(revision.approval.reviewer)
        if revision.approval
        else "Borrador · DRAFT"
    )
    partes = [
        Spacer(1, 60),
        Paragraph("Informe de revisión", styles["Title"]),
        Paragraph(f"{titulo} · revisión {etiqueta}", styles["Heading1"]),
        Paragraph(estado, styles["Heading2"]),
        Paragraph(
            f"Proyecto {escape(revision.project_id)} · {len(filas)} campos", styles["BodyText"]
        ),
        Paragraph(
            "Datos sintéticos" if revision.dataset == "synthetic" else "Datos del proyecto",
            styles["BodyText"],
        ),
        Paragraph(f"Huella de la revisión: {revision.fingerprint()}", styles["BodyText"]),
        PageBreak(),
        Paragraph(f"{titulo} · campos de la revisión {etiqueta}", styles["Heading2"]),
    ]
    tabla = [["Campo", "Valor", "Unidad", "Documento", "Página", "Confianza"]]
    for fila in filas:
        tabla.append(
            [
                Paragraph(escape(str(fila[k] or "-")), styles["BodyText"])
                for k in ("campo", "valor", "unidad", "documento", "pagina", "confianza")
            ]
        )
    tabla_pdf = LongTable(
        tabla, colWidths=[198, 145, 60, 162, 55, 72], repeatRows=1, hAlign="LEFT", splitInRow=1
    )
    tabla_pdf.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), azul),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#edf4f9")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 2.5),
            ]
        )
    )

    def pie(lienzo, documento):
        lienzo.setFont("Helvetica", 9)
        lienzo.drawRightString(doc.pagesize[0] - 34, 22, f"TrazIA-3D  ·  {documento.page}")

    doc.build([*partes, tabla_pdf], onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()


@router.get("/admin/revisiones/{identity}/campos.csv")
def campos_csv(request: Request, identity: str):
    revision = _revision(request, identity)
    return Response(
        _csv(revision),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={_nombre(revision, 'csv')}"},
    )


@router.get("/admin/revisiones/{identity}/informe.pdf")
def informe_pdf(request: Request, identity: str):
    revision = _revision(request, identity)
    return Response(
        _pdf(revision),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={_nombre(revision, 'pdf')}"},
    )

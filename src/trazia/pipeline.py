"""Ingiere documentos, llama al lector y comprueba el IFC DRAFT."""

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import lectura
from .extraction import Candidate, MissingDataError, assemble
from .ingest import IMAGE_SUFFIXES, DocumentKind, dataset_filename, image_to_pdf, ingest_bytes
from .lectura.clasificar import Metadata, classify, plan_b_ocr
from .model import Revision, RunInfo, Source
from .reconcile import resolve
from .reconcile.grounding import is_grounded

__all__ = ["InputDocument", "PipelineResult", "RunInfo", "StageEvent", "process"]


@dataclass(frozen=True)
class InputDocument:
    filename: str  # GAD_<TAG>_rev1.pdf, HDM_<TAG>_rev1.xlsx, VESOR_<TAG>.pdf…
    data: bytes
    document_id: str  # GA-<TAG>, HDM-<TAG>, VESOR-<TAG>
    kind: DocumentKind | None = None
    equipment_tag: str | None = None
    tag_hint: str | None = None


@dataclass(frozen=True)
class StageEvent:
    stage: str
    status: Literal["ok", "omitido", "error"]
    file: str
    detail: str


@dataclass
class PipelineResult:
    revision: Revision | None
    candidates: list[Candidate]
    warnings: list[str]
    error: str | None
    run: RunInfo
    conflicts: list[str] = field(default_factory=list)
    missing_data: bool = False
    unsupported_type: str | None = None


KINDS = {
    "GA": "plano de disposición general",
    "HDM": "hoja de datos mecánicos",
    "VESOR": "orientación de boquillas",
    "ESTRUCTURA": "estructura auxiliar",
}
FILENAME_LOCATOR = "Nombre del archivo"


def _tag_from_filename(bundles) -> Candidate | None:
    """El tag cuando ningún documento lo trae escrito: el dataset llega sin cajetines.

    La evidencia es el nombre del archivo, no una región de la página, y el campo pasa por la misma
    revisión humana que cualquier otro.
    """
    for bundle in bundles:
        if info := dataset_filename(bundle.document.filename):
            name = bundle.document.filename
            return Candidate(
                path="tag",
                value=bundle.equipment_tag if info.mechanical_kind else info.tag,
                unit="1",
                source=Source(
                    document_id=bundle.document.id,
                    page=1,
                    locator=f"{FILENAME_LOCATOR}: {name}",
                    confidence=0.6,
                ),
                channel="nombre_archivo",
                text_original=name,
                explanation="Ningún documento trae el tag escrito: sale del nombre del archivo.",
            )
    return None


def _tag_from_metadata(
    metadata: list[tuple[InputDocument, Metadata]],
) -> tuple[str, Candidate] | None:
    for doc, info in metadata:
        if info.tag_source is not None and info.tag:
            line = info.tag_source
            return doc.filename, Candidate(
                path="tag",
                value=info.tag,
                unit="1",
                text_original=line.text,
                source=line.source.model_copy(
                    update={"locator": f"Cajetín de equipo: {line.text}"}
                ),
            )
    return None


def _tag_declared(doc: InputDocument, tag: str, reason: str, *, confidence: float) -> Candidate:
    return Candidate(
        path="tag",
        value=tag,
        unit="1",
        source=Source(document_id=doc.document_id, page=1, locator=reason, confidence=confidence),
        explanation=reason,
    )


_UNSUPPORTED_LABELS = {
    "pump": "bomba",
    "compressor": "compresor",
    "heat_exchanger": "intercambiador",
    "air_cooler": "aeroenfriador",
    "fan": "ventilador",
    "agitator": "agitador",
    "filter": "filtro",
    "generic": "equipo genérico",
}


def process(
    documents: list[InputDocument],
    *,
    project_id: str,
    equipment_id: str,
    revision: str,
    strategy: str | None = None,
    previous: Revision | None = None,
    providers: list[str] | None = None,
    dataset: Literal["synthetic", "real"] = "synthetic",
    on_event: Callable[[StageEvent], None] | None = None,
    reader: Callable[..., list[Candidate]] | None = None,
    preliminary: bool = False,
) -> PipelineResult:
    """Lee, reconcilia y ensambla una revisión DRAFT con su IFC.

    `preliminary=True` (la API) no corta el proceso cuando faltan datos obligatorios: los crea
    como valores preliminares marcados para revisión. El lote y el banco lo dejan en `False`
    para seguir contando esas filas como `faltan_datos`.
    """
    if strategy is not None:
        # Estrategias A/B/C/D del estudio (trazia-3d); sin estrategia, la lectura de main.
        from .pipeline_estrategias import process as process_estrategia

        return process_estrategia(
            documents,
            project_id=project_id,
            equipment_id=equipment_id,
            revision=revision,
            strategy=strategy,
            previous=previous,
            providers=providers,
            dataset=dataset,
            on_event=on_event,
            preliminary=preliminary,
        )
    started = time.perf_counter()

    def emit(event: StageEvent) -> None:
        if on_event:
            on_event(event)

    # Conserva el nombre histórico de este campo del contrato 0.3.
    run = RunInfo(strategy="lectura", providers=[], seconds=0.0, external_calls=0, cost_eur=0.0)
    warnings: list[str] = []

    def finish(rev, candidates, error, conflicts=(), *, missing_data=False, unsupported_type=None):
        run.seconds = time.perf_counter() - started
        return PipelineResult(
            rev, candidates, warnings, error, run, list(conflicts), missing_data, unsupported_type
        )

    bundles = []
    metadata: list[tuple[InputDocument, Metadata]] = []
    raw: dict[str, bytes] = {}
    seen: dict[str, str] = {}  # sha256 del original → nombre del primero que lo trajo
    for doc in documents:
        digest = hashlib.sha256(doc.data).hexdigest()
        if digest in seen:
            warnings.append(f"{doc.filename} es idéntico a {seen[digest]}: se lee una sola vez.")
            emit(StageEvent("ingest", "omitido", doc.filename, f"Duplicado de {seen[digest]}."))
            continue
        try:
            bundle = ingest_bytes(doc.data, doc.filename, doc.document_id, revision)
            data = doc.data
            if Path(doc.filename).suffix.lower() in IMAGE_SUFFIXES:
                # Una imagen se lee como un PDF escaneado; la huella sigue siendo la del original.
                data = image_to_pdf(doc.data)
                name = str(Path(doc.filename).with_suffix(".pdf"))
                image_warnings = bundle.warnings[1:]  # el aviso de imagen ya no aplica
                bundle = ingest_bytes(data, name, doc.document_id, revision)
                bundle.document.filename = Path(doc.filename).name
                bundle.document.sha256 = digest
                bundle.warnings = image_warnings + bundle.warnings
            if bundle.media_type == "pdf" and (
                legible := _capa_ocr(data, doc, revision, digest, emit)
            ):
                data, bundle = legible
        except Exception as exc:  # pdfminer lanza sus propias excepciones con bytes corruptos
            reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            warnings.append(f"Ingesta fallida de {doc.filename}: {reason}")
            emit(StageEvent("ingest", "error", doc.filename, f"No se pudo leer: {reason}"))
            continue
        seen[digest] = doc.filename
        raw[doc.document_id] = data
        warnings += bundle.warnings
        pages = bundle.document.page_count
        emit(
            StageEvent(
                "ingest",
                "ok",
                doc.filename,
                f"SHA-256 registrado · {pages} página(s)." if pages else "SHA-256 registrado.",
            )
        )
        info = classify(
            bundle, kind=doc.kind, equipment_tag=doc.equipment_tag, tag_hint=doc.tag_hint, data=data
        )
        metadata.append((doc, info))
        bundle.kind, bundle.equipment_tag = info.kind, info.tag
        kind = KINDS.get(info.kind)
        location = (
            f" · pág. {info.kind_source.source.page}, «{info.kind_source.text[:160]}»"
            if info.kind_source
            else ""
        )
        detail = (
            f"Clasificado como {info.kind} ({kind}) por {info.reason}{location}."
            if kind
            else info.reason
        )
        if kind is None:
            warnings.append(f"{doc.filename}: {detail}.")
        emit(
            StageEvent(
                "classify",
                "ok" if kind else "omitido",
                doc.filename,
                detail,
            )
        )
        if info.kind in ("GA", "VESOR"):
            for page in bundle.sparse_pages:
                message = f"{doc.filename}, página {page}: plano sin texto: necesita OCR"
                if plan_b_ocr(info.kind, info.tag):
                    message += " (plan B de OCR disponible si hay marcas de referencia)"
                warnings.append(message)
                emit(StageEvent("extract.ocr", "omitido", doc.filename, message))
        bundles.append(bundle)
    if not bundles:
        detail = warnings[0] if len(warnings) == 1 else "No se pudo leer ningún documento."
        return finish(None, [], detail)
    explicit = [(doc, doc.equipment_tag) for doc, _ in metadata if doc.equipment_tag]
    if len({tag for _, tag in explicit}) > 1:
        return finish(None, [], "Los tags indicados manualmente no coinciden.")

    try:
        warning_counts = [len(bundle.warnings) for bundle in bundles]
        readings = (reader or lectura.leer)(
            bundles, raw=raw, dataset=dataset, previous=previous, providers=providers
        )
    except Exception as exc:
        reason = _reason(exc)
        emit(StageEvent("extract", "error", equipment_id, reason))
        return finish(None, [], f"Falló la lectura: {reason}")
    for bundle, count in zip(bundles, warning_counts, strict=True):
        warnings.extend(bundle.warnings[count:])
        for notice in bundle.warnings[count:]:
            if notice.startswith("Plan B de OCR:"):
                emit(StageEvent("extract.ocr", "ok", bundle.document.filename, notice))
    emit(StageEvent("extract", "ok", equipment_id, f"{len(readings)} candidatos de lectura."))
    candidates = _ground(readings, bundles, warnings, emit, equipment_id)
    if explicit:
        doc, tag = explicit[0]
        candidates = [c for c in candidates if c.path != "tag"]
        candidates.append(_tag_declared(doc, tag, "Tag indicado manualmente", confidence=1))
    elif not any(c.path == "tag" for c in candidates):
        if citado := _tag_from_metadata(metadata):
            filename, tag = citado
            candidates.append(tag)
            emit(StageEvent("classify", "ok", filename, tag.source.locator))
        elif tag := _tag_from_filename(bundles):
            candidates.append(tag)
            warnings.append(f"Tag tomado del nombre del archivo: {tag.value}.")
        elif hinted := next(((doc, info.tag) for doc, info in metadata if info.tag), None):
            doc, tag = hinted
            candidates.append(
                _tag_declared(doc, tag, "Tag tomado de la carpeta del equipo", confidence=0.55)
            )
            warnings.append(f"Tag tomado de la carpeta del equipo: {tag}.")
    resolution = resolve(candidates)
    warnings += resolution.warnings
    emit(
        StageEvent(
            "reconcile",
            "ok",
            equipment_id,
            f"{len(resolution.chosen)} campos · "
            f"{len(resolution.conflicts)} conflictos para revisión.",
        )
    )
    chosen = resolution.chosen
    declared = next(
        (
            c.value
            for c in chosen
            if c.path == "attributes.equipment_type" and c.state != "abstained"
        ),
        None,
    )
    supported = {"vertical_vessel", "horizontal_vessel", "column", "tank", "pump", "compressor"}
    unsupported = (
        _UNSUPPORTED_LABELS.get(declared, str(declared))
        if declared is not None and declared not in supported
        else None
    )
    unsupported_message = f"tipología no soportada: {unsupported}" if unsupported else None
    if unsupported_message:
        warnings.append(unsupported_message)

    try:
        model = assemble(
            bundles,
            chosen,
            project_id=project_id,
            equipment_id=equipment_id,
            revision=revision,
            dataset=dataset,
            warnings=warnings,
            preliminary=preliminary,
        )
    except ValueError as exc:
        # Solo la falta de datos se explica por la tipología. Otro error (un valor que el
        # contrato rechaza, por ejemplo) se dice tal cual: taparlo escondería el fallo real.
        if unsupported_message and isinstance(exc, MissingDataError):
            emit(StageEvent("family", "error", equipment_id, unsupported_message))
            return finish(
                None,
                chosen,
                unsupported_message,
                resolution.conflicts,
                unsupported_type=unsupported,
            )
        reason = _reason(exc)
        if isinstance(exc, MissingDataError) and declared in ("pump", "compressor"):
            machine = _UNSUPPORTED_LABELS[declared]
            labels = {
                "envelope.size.x": "longitud",
                "envelope.size.y": "anchura",
                "envelope.size.z": "altura",
                "tag": "identificador",
            }
            missing = [label for path, label in labels.items() if path in reason]
            if missing:
                reason = f"Cotas verificables pendientes ({machine}): " + ", ".join(missing) + "."
        emit(StageEvent("family", "error", equipment_id, reason))
        return finish(
            None,
            chosen,
            reason,
            resolution.conflicts,
            missing_data=isinstance(exc, MissingDataError),
        )
    if unsupported_message and model.equipment.lod != 1:
        emit(StageEvent("family", "error", equipment_id, unsupported_message))
        return finish(
            None, chosen, unsupported_message, resolution.conflicts, unsupported_type=unsupported
        )
    if model.equipment.kind in ("pump", "compressor"):
        warnings.append(
            "Envolvente LOD 1 de la bancada y el equipo principal. Revisa su alcance en el plano."
        )
    emit(
        StageEvent(
            "family",
            "ok",
            equipment_id,
            f"{unsupported_message} · solo envolvente LOD 1."
            if unsupported_message
            else f"{model.equipment.kind} · LOD {model.equipment.lod} · "
            f"{len(model.equipment.nozzles)} boquillas.",
        )
    )
    try:
        from .ifc import build_ifc

        build_ifc(model, draft=True)
        emit(StageEvent("ifc", "ok", equipment_id, "IFC4 DRAFT con GUID estables."))
        emit(
            StageEvent("validate", "ok", equipment_id, "Geometría válida · pendiente de revisión.")
        )
    except ValueError as exc:
        emit(StageEvent("ifc", "error", equipment_id, str(exc).splitlines()[0]))
        return finish(None, chosen, str(exc).splitlines()[0], resolution.conflicts)
    return finish(model, chosen, None, resolution.conflicts, unsupported_type=unsupported)


def _capa_ocr(data, doc, revision, digest, emit):
    """Páginas sin texto (escaneo, foto o texto convertido en trazos): capa OCR y rayado.

    Devuelve el PDF derivado y su `Bundle`, con la huella del original, o `None` si no hace
    falta o no hay motor de OCR. Así las mismas reglas leen planos de cualquier fabricante.
    `TRAZIA_CAPA_OCR=0` la desactiva.
    """
    if os.environ.get("TRAZIA_CAPA_OCR", "1") == "0":
        return None
    from .ocr.capa_texto import paginas_sin_texto, pdf_legible
    from .ocr.engine import OcrUnavailable

    try:
        paginas = paginas_sin_texto(data)
        if not paginas:
            return None
        nuevo, leidas = pdf_legible(data, paginas)
        bundle = ingest_bytes(nuevo, doc.filename, doc.document_id, revision)
    except (OcrUnavailable, ImportError, ValueError, OSError) as exc:
        emit(StageEvent("extract.ocr", "omitido", doc.filename, f"Capa OCR no disponible: {exc}"))
        return None
    bundle.document.sha256 = digest
    lista = ", ".join(str(p.numero) for p in leidas)
    textos = sum(p.horizontales + p.verticales for p in leidas)
    aviso = (
        f"Capa OCR en páginas sin texto ({lista}): {textos} rótulos reconocidos y "
        f"{sum(p.reglas for p in leidas)} trazos de tabla reconstruidos; confianza del OCR en "
        "cada cita."
    )
    bundle.warnings.insert(0, aviso)
    emit(StageEvent("extract.ocr", "ok", doc.filename, aviso))
    return nuevo, bundle


def _reason(exc: Exception) -> str:
    """Frase útil de un error: de una validación de Pydantic, la causa y no la cabecera."""
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    for line in lines:
        if line.startswith("Value error,"):
            return line.removeprefix("Value error,").split(" [type=")[0].strip()
    return lines[0] if lines else type(exc).__name__


# Canales cuyos valores salen de un modelo: si su cita no los respalda, no entran (DEC-10).
MODEL_CHANNELS = {"vision", "detector"}


def _ground(candidates, bundles, warnings, emit, equipment_id, evidence=None):
    """Marca `grounded` en cada candidato y descarta los de modelo que su cita no respalda."""
    lines = {b.document.id: b.lines or (evidence or {}).get(b.document.id, []) for b in bundles}
    kept, dropped = [], []
    for c in candidates:
        if c.grounded is None and c.source.document_id in lines:
            c = c.model_copy(update={"grounded": is_grounded(c, lines[c.source.document_id])})
        if c.grounded is False and c.channel in MODEL_CHANNELS:
            dropped.append(c)
            continue
        kept.append(c)
    if dropped:
        paths = ", ".join(sorted({c.path for c in dropped})[:5])
        warnings.append(f"{len(dropped)} lecturas de modelo sin respaldo en su cita: {paths}")
    emit(
        StageEvent(
            "validate",
            "ok",
            equipment_id,
            f"Cita comprobada · {len(dropped)} valores de modelo descartados por no estar "
            "en su región.",
        )
    )
    return kept

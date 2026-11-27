"""Entrada del lector de planos GA y hojas de datos mecánicos."""

import io
from collections.abc import Mapping, Sequence
from typing import Literal

import pdfplumber

from ..extraction import Candidate, LabelExtractor
from ..ingest import Bundle, dataset_filename
from ..model import NozzleSchedule, Revision
from ..ocr.engine import OcrUnavailable
from ..ocr.pdf_words import lines_in_pdf_points
from ..ocr.plan_b import bearing_notices, explicit_bearings, nearby_bearings
from . import (
    cdg,
    columna,
    columna_alzado,
    cotas_generales,
    datos_diseno,
    mecanicos,
    planos_externos,
    posicion,
    soldaduras,
    vision_llm,
)
from .clasificar import classify, plan_b_ocr
from .hdm import read_candidates
from .tablas import _en_caja, _segmentos_linea, _texto_caja, expandir_marcas, leer_ga


def leer(
    documentos: Sequence[Bundle],
    *,
    raw: Mapping[str, bytes],
    dataset: Literal["synthetic", "real"],
    previous: Revision | None = None,
    providers: Sequence[str] | None = None,
) -> list[Candidate]:
    """Recibe documentos ya ingeridos y devuelve candidatos con fuente por campo.

    Cada documento incluye su ID, nombre y evidencia textual. `raw` contiene los bytes
    legibles por ID (las imágenes se convierten en PDF), si se parte de originales.
    `dataset` identifica el origen de los datos. `previous` es la revisión anterior y
    `providers` enumera proveedores solicitados, cuando el invocador los indica.
    """
    if dataset == "synthetic":
        lectura_etiquetada = LabelExtractor().extract(documentos)
        if any(c.path == "diameter" for c in lectura_etiquetada):
            return lectura_etiquetada
    mechanical = [
        (bundle, info.mechanical_kind)
        for bundle in documentos
        if (info := dataset_filename(bundle.document.filename))
        and info.mechanical_kind
        and bundle.kind in ("GA", None)
        and bundle.document.id in raw
    ]
    if mechanical:
        if len(mechanical) != 1:
            raise ValueError("Sube una única lámina GA de bomba o compresor por revisión.")
        bundle, kind = mechanical[0]
        return mecanicos.leer(bundle, raw[bundle.document.id], kind)
    candidatos = []
    planos = []
    planos_bundles = []
    vesores = []
    plan_b = []
    for bundle in documentos:
        doc = bundle.document
        if bundle.kind is None:
            info = classify(bundle, data=raw.get(doc.id))
            kind, tag = info.kind, info.tag
        else:
            kind, tag = bundle.kind, bundle.equipment_tag
        if kind is None or bundle.media_type != "pdf" or doc.id not in raw:
            continue
        if plan_b_ocr(kind, tag):
            plan_b.append(bundle)
        if kind == "HDM":
            fields, notices = read_candidates(raw[doc.id], doc.id)
            candidatos.extend(fields)
            bundle.warnings.extend(notices)
            continue
        if kind == "VESOR":
            vesores.append(doc.id)
            continue
        if kind != "GA":
            continue
        resultado = leer_ga(io.BytesIO(raw[doc.id]), documento=doc.id, nombre=doc.filename, tag=tag)
        if inventario := resultado.get("nozzle_schedule"):
            doc.nozzle_schedule = NozzleSchedule.model_validate(inventario)
        if any(
            c["path"] == "attributes.equipment_type" and c["value"] == "column"
            for c in resultado["candidates"]
        ):
            resultado["candidates"].extend(
                columna.leer_columna(raw[doc.id], doc.id, resultado["candidates"], bundle.warnings)
            )
            if not any(c["path"].startswith("column.sections.") for c in resultado["candidates"]):
                # Alzado tumbado sin marcas de virola: tramos y faldón por la cota y la silueta.
                conocidas = {c["path"] for c in resultado["candidates"]}
                resultado["candidates"].extend(
                    c
                    for c in columna_alzado.leer(raw[doc.id], doc.id, bundle.warnings)
                    if c["path"] not in conocidas
                )
        resultado["candidates"].extend(cdg.leer(raw[doc.id], doc.id))
        resultado["candidates"].extend(datos_diseno.leer(raw[doc.id], doc.id))
        planos.append((doc.id, resultado))
        planos_bundles.append(bundle)
        for dato in resultado["candidates"]:
            dato["confidence_raw"] = dato["source"]["confidence"]
            dato["unit"] = dato["unit"] or "1"
            if dato["path"].startswith("nozzles.") and dato["path"].endswith(
                (".projection", ".projection_basis", ".size_nps")
            ):
                dato["channel"] = "tabla"
            candidatos.append(Candidate.model_validate(dato))
    candidatos.extend(_cotas_generales(documentos, raw, candidatos))
    candidatos.extend(_planos_externos(documentos, raw, candidatos))
    known_marks = {
        candidate.path.split(".")[1]
        for candidate in candidatos
        if candidate.path.startswith("nozzles.")
    }
    for bundle in plan_b:
        if known_marks:
            _ocr_plan_b(bundle, raw[bundle.document.id], known_marks)
    posiciones = _posiciones(planos, vesores, raw)
    bases = {
        (c.path, c.source.document_id) for c in posiciones if c.path.endswith(".projection_basis")
    }
    proyecciones = {
        (c.path, c.source.document_id)
        for c in posiciones
        if c.source.rule == "horizontal.proyeccion_individual"
    }
    leidos = [
        c
        for c in candidatos
        if (c.path, c.source.document_id) not in proyecciones
        and (c.value != "desconocida" or (c.path, c.source.document_id) not in bases)
    ] + posiciones
    if providers:
        leidos = _vision(planos_bundles, raw, leidos, providers[0], dataset)
    # Uniones soldadas deducidas de las piezas citadas (J6); `assemble` aún no las usa.
    return leidos + soldaduras.inferir(leidos)


def _cotas_generales(documentos, raw, candidatos):
    """Cotas principales escritas en texto, solo para las rutas que ninguna regla ha dado."""
    tipos = {c.value for c in candidatos if c.path == "attributes.equipment_type"}
    tipo = next(iter(tipos)) if len(tipos) == 1 else None
    conocidas = {c.path for c in candidatos}
    nuevas: dict[str, Candidate] = {}
    descartadas: set[str] = set()
    for bundle in documentos:
        doc = bundle.document
        kind = bundle.kind or classify(bundle).kind
        if kind not in ("GA", "HDM") or doc.id not in raw:
            continue
        for dato in cotas_generales.leer(raw[doc.id], doc.id, tipo):
            if dato["path"] in conocidas:
                continue
            dato["confidence_raw"] = dato["source"]["confidence"]
            candidato = Candidate.model_validate(dato)
            previo = nuevas.get(candidato.path)
            if previo is not None and previo.value != candidato.value:
                descartadas.add(candidato.path)
                bundle.warnings.append(
                    f"Cotas generales: {candidato.path} vale {previo.value} y {candidato.value}"
                    " según el documento; se deja para revisión."
                )
                continue
            nuevas.setdefault(candidato.path, candidato)
    return [c for path, c in nuevas.items() if path not in descartadas]


def _planos_externos(documentos, raw, candidatos):
    """Formatos de otros fabricantes (unidades imperiales, cajetines, tablas con marcas de una
    letra), solo para las rutas que ninguna regla del formato del reto ha dado."""
    tipos = {c.value for c in candidatos if c.path == "attributes.equipment_type"}
    tipo = next(iter(tipos)) if len(tipos) == 1 else None
    conocidas = {c.path for c in candidatos}
    marcas = {c.path.split(".")[1] for c in candidatos if c.path.startswith("nozzles.")}
    nuevas: dict[str, Candidate] = {}
    for bundle in documentos:
        doc = bundle.document
        kind = bundle.kind or classify(bundle).kind
        if kind not in ("GA", "HDM") or doc.id not in raw:
            continue
        for dato in planos_externos.leer(raw[doc.id], doc.id, tipo):
            ruta = dato["path"]
            if ruta in conocidas or ruta in nuevas:
                continue
            if ruta.startswith("nozzles.") and ruta.split(".")[1] in marcas:
                continue
            dato["confidence_raw"] = dato["source"]["confidence"]
            nuevas[ruta] = Candidate.model_validate(dato)
    return list(nuevas.values())


def _vision(bundles, raw, leidos, spec, dataset):
    """J4: visión solo en los huecos y validador de lo dudoso, con la política de envíos."""
    from ..vision.base import PolicyError, VisionError
    from ..vision.providers import get_provider

    if not bundles:
        return leidos
    try:
        proveedor = get_provider(spec, dataset=dataset)
    except (VisionError, PolicyError) as error:
        bundles[0].warnings.append(f"Visión ({spec}) no disponible: {error}")
        return leidos
    for bundle in bundles:
        try:
            leidos, informe = vision_llm.aplicar(proveedor, bundle, raw[bundle.document.id], leidos)
        except (VisionError, PolicyError, OSError) as error:
            bundle.warnings.append(f"Visión {bundle.document.id}: {error}")
            continue
        bundle.warnings.append(informe.resumen())
        bundle.warnings.extend(f"Visión {bundle.document.id}: {e}" for e in informe.errores[:3])
    return leidos


def _ocr_plan_b(bundle: Bundle, data: bytes, known_marks: set[str]) -> None:
    doc = bundle.document
    try:
        pages = lines_in_pdf_points(data, doc.id, tiles=True)
    except (OcrUnavailable, OSError) as error:
        bundle.warnings.append(f"OCR {doc.id}: {error}")
        return
    bundle.warnings.append(f"Plan B de OCR: ejecutado para {doc.filename}.")
    lines = [line for rows in pages.values() for line in rows]
    readings = explicit_bearings(lines, known_marks)
    confirmed = {(item.mark, item.bearing, item.evidence["page"]) for item in readings}
    suggestions = [
        item
        for item in nearby_bearings(lines, known_marks)
        if (item.mark, item.bearing, item.evidence["page"]) not in confirmed
    ]
    if not readings:
        bundle.warnings.append(f"OCR {doc.id}: no se leyó una marca registrada junto a su ángulo.")
    bundle.warnings.extend(bearing_notices(readings + suggestions))


def _posiciones(planos, vesores, raw):
    tipos = {
        c["value"]
        for _, resultado in planos
        for c in resultado["candidates"]
        if c["path"] == "attributes.equipment_type"
    }
    if tipos not in ({"horizontal_vessel"}, {"vertical_vessel"}, {"column"}):
        return []
    es_columna = tipos == {"column"}
    horizontal = "horizontal_vessel" in tipos
    registro = {
        marca: nodo["kind"]
        for _, resultado in planos
        for marca, nodo in resultado["identifiers"].items()
    }
    if "nozzle" not in registro.values():
        return []
    documentos = [*planos, *((id_doc, None) for id_doc in vesores if horizontal)]
    lecturas = []
    for id_doc, resultado in documentos:
        tabla = (resultado or {}).get("nozzle_schedule")
        inventario = {marca: marca for marca in (tabla or {}).get("rows", {})}
        posiciones = []
        notas = []
        with pdfplumber.open(io.BytesIO(raw[id_doc])) as pdf:
            for page in pdf.pages:
                palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
                palabras = [p for p in palabras if _en_caja(p, page.bbox)]
                lineas = [_texto_caja(g) for g in _segmentos_linea(palabras)]
                marcas = {}
                for palabra in palabras:
                    literal = palabra["text"].upper()
                    if literal in marcas or registro.get(literal) == "bom_item":
                        continue
                    normalizadas = expandir_marcas(literal)
                    if len(normalizadas) == 1 and registro.get(normalizadas[0]) == "nozzle":
                        marcas[literal] = normalizadas[0]
                if horizontal:
                    datos = posicion.horizontal(
                        page, palabras, lineas, id_doc, marcas, vesor=resultado is None
                    )
                    if inventario:
                        notas.extend(posicion.notas_proyeccion_radial(page, lineas))
                        datos.extend(
                            posicion.alzado_con_tangente(
                                page,
                                palabras,
                                lineas,
                                id_doc,
                                marcas | inventario,
                                raw[id_doc],
                                resultado["candidates"],
                            )
                        )
                        posiciones.extend(datos)
                    lecturas.extend(datos)
                    if resultado is not None:
                        lecturas.extend(
                            posicion.bases_horizontales(
                                page, lineas, datos, resultado["candidates"]
                            )
                        )
                elif es_columna:
                    lecturas.extend(
                        columna.posiciones(
                            page, palabras, lineas, id_doc, marcas, resultado["nozzle_labels"]
                        )
                    )
                    # Columna tumbada: «±N TO T.L.» y ángulos escritos junto a los globos.
                    ya = {c.path for c in lecturas}
                    lecturas.extend(
                        c
                        for c in columna_alzado.posiciones(page, palabras, id_doc, marcas)
                        if c.path not in ya
                    )
                else:
                    lecturas.extend(
                        posicion.vertical(
                            page,
                            palabras,
                            lineas,
                            id_doc,
                            marcas,
                            resultado["nozzle_labels"],
                            resultado["candidates"],
                        )
                    )
                page.close()
        if horizontal and inventario:
            lecturas.extend(
                posicion.base_eje_por_seccion(id_doc, notas, posiciones, resultado["candidates"])
            )
    return lecturas

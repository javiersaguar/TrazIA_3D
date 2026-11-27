"""Lee la envolvente de bombas y compresores de sus vistas ortogonales."""

import re
from dataclasses import dataclass

from ..extraction import Candidate
from ..extractors.mechanical import pump_envelope
from ..extractors.units import parse_number
from ..ingest import Bundle, EvidenceLine
from ..model import Source
from ..ocr.engine import OcrUnavailable, ocr_pdf_lines
from .mecanicos_exteriores import exteriores
from .tipologia import normalizar

# Las cotas del cuerpo bajo estas convenciones están en mm. En gálibos con
# unidades dobles se lee la primera columna, que corresponde al sistema métrico.
_NUMBER = r"(\d+(?:[,.]\d+)?)"
_MIN_OCR_CONFIDENCE = 0.90


@dataclass
class Dimension:
    lines: list[EvidenceLine]
    parts: list[float]

    def candidate(self, axis):
        lines = self.lines
        value = round(sum(self.parts), 3)
        # La confianza de OCR describe la transcripción, no cuál de las
        # cotas de la vista representa el gálibo. Esa elección queda a revisión.
        original = lines[0].source
        source = original.model_copy(update={"confidence": min(0.85, original.confidence)})
        explanation = "Cota de la envolvente de la bancada y su equipo principal."
        if len(self.parts) > 1:
            boxes = [line.source.bbox for line in lines]
            source = source.model_copy(
                update={
                    "bbox": (
                        min(b[0] for b in boxes),
                        min(b[1] for b in boxes),
                        max(b[2] for b in boxes),
                        max(b[3] for b in boxes),
                    ),
                    "confidence": min(0.85, *(line.source.confidence for line in lines)),
                    "rule": "envolvente.cadena_de_cotas",
                }
            )
            terms = " + ".join(f"{part:g}" for part in self.parts)
            explanation = f"Altura de la envolvente por cotas encadenadas: {terms} = {value:g} mm."
        return Candidate(
            path=f"envelope.size.{axis}",
            value=value,
            unit="mm",
            source=source,
            text_original=" · ".join(line.text for line in lines),
            channel="cota",
            explanation=explanation,
        )


def _label(lines, pattern, page=None):
    return next(
        (
            x
            for x in lines
            if (page is None or x.source.page == page) and re.search(pattern, normalizar(x.text))
        ),
        None,
    )


def _pick(lines, pattern, *, page, box=(0, 0, 1, 1), vertical=None):
    values = {}
    for line in lines:
        if line.source.page != page or line.source.bbox is None:
            continue
        x0, y0, x1, y1 = line.source.bbox
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        if not (box[0] <= x <= box[2] and box[1] <= y <= box[3]):
            continue
        if vertical is not None and ((y1 - y0) > (x1 - x0)) != vertical:
            continue
        match = re.fullmatch(pattern, normalizar(line.text).strip())
        if match is None:
            continue
        parts = [parse_number(v) for v in match.groups()]
        if any(v is None or v <= 0 for v in parts):
            continue
        if line.source.locator.startswith("OCR") and line.source.confidence < _MIN_OCR_CONFIDENCE:
            continue
        values.setdefault(tuple(parts), Dimension([line], parts))
    return next(iter(values.values())) if len(values) == 1 else None


def _sum(*dimensions):
    if any(d is None for d in dimensions):
        return None
    return Dimension(
        [line for d in dimensions for line in d.lines],
        [part for d in dimensions for part in d.parts],
    )


def _labelled_dimensions(lines, page):
    patterns = (
        r"(?:OVERALL LENGTH|LONGITUD TOTAL)\s*[:=]\s*",
        r"(?:OVERALL WIDTH|ANCHURA TOTAL|ANCHO TOTAL)\s*[:=]\s*",
        r"(?:OVERALL HEIGHT|ALTURA TOTAL)\s*[:=]\s*",
    )
    return tuple(_pick(lines, f"{p}{_NUMBER}\\s*MM", page=page) for p in patterns)


def _pump_oh2(lines):
    front = _label(lines, r"^FRONT[- ]VIEW$")
    if front is None:
        return None
    page = front.source.page
    plan = _label(lines, r"^TOP[- ]VIEW$", page)
    pump = _label(lines, r"\bPUMP TYPE IS OH2\b", page)
    if not plan or not pump:
        return None
    fx, fy, fx1, _ = front.source.bbox
    # Largo bajo el alzado; ancho en planta y vista transversal (deben
    # coincidir); altura entre la base y la salida de la bomba.
    x = _pick(lines, _NUMBER, page=page, box=(fx, fy - 0.025, fx1 + 0.01, fy), vertical=False)
    y = _pick(
        lines,
        _NUMBER,
        page=page,
        box=(fx + 0.34, fy - 0.024, fx + 0.41, fy + 0.005),
        vertical=False,
    )
    width = _pick(
        lines,
        _NUMBER,
        page=page,
        box=(0.045, plan.source.bbox[1] - 0.19, 0.06, plan.source.bbox[1] - 0.155),
        vertical=True,
    )
    if not y or not width or width.parts != y.parts:
        y = None
    z = _pick(lines, _NUMBER, page=page, box=(0.047, fy - 0.20, 0.063, fy - 0.165), vertical=True)
    return pump, (x, y, z)


def _pump_skid(lines):
    pump = _label(lines, r"^PUMP NO\.", 1)
    if not pump or not _label(lines, r"\bDIMENSIONS ARE IN MM\b", 1):
        return None
    if not _label(lines, r"^DATUM$", 1):
        return None
    # El largo se repite en planta y alzado. El ancho visible está acotado
    # por fuera de los centros de anclaje. En la vista axial hay tres
    # cotas encadenadas desde el fondo hasta la brida de descarga.
    x = _pick(lines, _NUMBER, page=1, box=(0.23, 0.36, 0.31, 0.39), vertical=False)
    check = _pick(lines, _NUMBER, page=1, box=(0.23, 0.88, 0.31, 0.91), vertical=False)
    if not x or not check or check.parts != x.parts:
        x = None
    y = _pick(lines, _NUMBER, page=1, box=(0.48, 0.19, 0.506, 0.216), vertical=False)
    z = _sum(
        *(
            _pick(lines, _NUMBER, page=1, box=(0.797, lo, 0.826, hi), vertical=False)
            for lo, hi in ((0.625, 0.655), (0.73, 0.76), (0.80, 0.83))
        )
    )
    return pump, (x, y, z)


def _compressor_frame(lines):
    front = _label(lines, r"^FRONT VIEW$", 1)
    compressor = _label(lines, r"^COMPRESSOR$", 1)
    if not front or not compressor or not _label(lines, r"^TOP VIEW$", 1):
        return None
    x = _pick(lines, _NUMBER + r"\s+\(BASE FRAME\)(?:\s+.*)?", page=1, vertical=False)
    y = _pick(lines, r"\(BASE FRAME\)\s+" + _NUMBER, page=1, vertical=True)
    body = _pick(
        lines, _NUMBER + r"\s+" + _NUMBER, page=1, box=(0.434, 0.19, 0.442, 0.23), vertical=True
    )
    base = _pick(lines, _NUMBER, page=1, box=(0.385, 0.241, 0.395, 0.256), vertical=True)
    return compressor, (x, y, _sum(body, base))


def _compressor_baseplate(lines):
    front = _label(lines, r"^VIEW FROM A$", 1)
    datum = _label(lines, r"^T\.O\.B\. = TOP OF BASEPLATE$", 1)
    if not front or not datum or not _label(lines, r"^PLAN VIEW$", 1):
        return None
    x = _pick(lines, _NUMBER + r"\s+\d+'.* BASEPLATE", page=1, vertical=False)
    y = _pick(lines, r"BASEPLATE\s+" + _NUMBER + r"\s+\d+'.*", page=1, vertical=True)
    body = _pick(
        lines, _NUMBER + r"\s+\d+'.*", page=1, box=(0.029, 0.20, 0.04, 0.27), vertical=True
    )
    base = _pick(
        lines, _NUMBER + r"\s+\d+'.*", page=1, box=(0.05, 0.32, 0.066, 0.35), vertical=True
    )
    return datum, (x, y, _sum(body, base))


def leer(bundle: Bundle, data: bytes, kind: str) -> list[Candidate]:
    lines = bundle.lines
    name = bundle.document.filename
    family_pattern = (
        r"^(?:CENTRIFUGAL PUMP|BOMBA CENTRIFUGA)\b"
        if kind == "pump"
        else r"^(?:CENTRIFUGAL COMPRESSOR|COMPRESOR CENTRIFUGO)\b"
    )
    family = _label(lines, family_pattern)
    if family:
        explicit = _labelled_dimensions(lines, family.source.page)
        if any(explicit):
            return _cerrar(bundle, kind, _candidates(kind, family.source, explicit))
    if kind == "pump":
        if explicit_pump := pump_envelope(lines):
            return _cerrar(bundle, kind, explicit_pump)
        layout = _pump_skid(lines)
        if layout is None and _label(lines, r"^EARTHING BOSS DETAIL$", 1):
            try:
                try:
                    ocr = ocr_pdf_lines(data, bundle.document.id, pages=[1, 2], dpi=300, tiles=True)
                except ValueError:
                    ocr = ocr_pdf_lines(data, bundle.document.id, pages=[1], dpi=300, tiles=True)
            except OcrUnavailable:
                bundle.warnings.append(
                    f"{name}: OCR local no disponible para las cotas de la bomba."
                )
            else:
                bundle.lines.extend(ocr)
                layout = _pump_oh2(ocr)
                if layout:
                    bundle.warnings.append(f"{name}: cotas de la bomba leídas con OCR local.")
    else:
        layout = _compressor_frame(lines) or _compressor_baseplate(lines)
    if layout:
        label, dimensions = layout
        return _cerrar(bundle, kind, _candidates(kind, label.source, dimensions))
    source = (
        family.source
        if family
        else Source(
            document_id=bundle.document.id,
            page=1,
            confidence=0.60,
            locator=f"Nombre del archivo: {name}",
        )
    )
    return _cerrar(bundle, kind, _candidates(kind, source, (None, None, None)))


def _cerrar(bundle, kind, candidates):
    """Añade el tren y las toberas de proceso sin sustituir la envolvente ya leída."""
    dims = []
    for axis in "xyz":
        found = next((c.value for c in candidates if c.path == f"envelope.size.{axis}"), None)
        dims.append(found)
    if candidates and all(isinstance(v, int | float) and v > 0 for v in dims):
        candidates = [
            *candidates,
            *exteriores(bundle.lines, kind, (dims[0], dims[1], dims[2]), candidates[0].source),
        ]
    return candidates


def _candidates(kind, datum, dimensions):
    out = [Candidate(path="attributes.equipment_type", value=kind, unit="1", source=datum)]
    for axis, dimension in zip("xyz", dimensions, strict=True):
        if dimension:
            out.append(dimension.candidate(axis))
        out.append(
            Candidate(
                path=f"envelope.origin.{axis}",
                value=0.0,
                unit="mm",
                source=datum.model_copy(update={"rule": "asumido.origen_bancada"}),
                state="assumed",
                explanation=(
                    "Origen local en la esquina inferior de la envolvente; "
                    "sin coordenadas de planta."
                ),
            )
        )
    return out

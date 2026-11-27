"""Clasificación documental citada a partir de la capa de texto."""

import re
from collections import defaultdict
from dataclasses import dataclass

from ..ingest import Bundle, DocumentKind, EvidenceLine, dataset_filename
from ..model import Source
from .tipologia import normalizar

TAG = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,79}", re.I)
_TAG_LABEL = r"(?:EQUIPMENT\s+(?:TAG|NO\.?)|ITEM\s+NO\.?|TAG(?:\s+NO\.?)?|EQUIPO)"
_REV_LABEL = r"(?:REV(?:ISION)?\.?)"
_LABELS = {
    "tag": (_TAG_LABEL, r"[\w-]+"),
    "revision": (_REV_LABEL, r"[A-Z0-9]{1,8}"),
}
_TAG_EN_TITULO = re.compile(
    r"^(?:GENERAL\s+ARR[AE]NGEMENT(?:\s+DRAWING)?\s+FOR"
    r"|(?:DISPOSICION|ARREGLO|PLANO)\s+GENERAL\s+DE)\s+([A-Z0-9_-]+)$"
)
_HEADINGS: tuple[tuple[DocumentKind, str, str], ...] = (
    (
        "HDM",
        r"^(?:MECHANICAL\s+)?(?:DATA\s*SHEET|HOJA\s+DE\s+DATOS)(?:\b|$)",
        "su encabezado de hoja de datos",
    ),
    (
        "GA",
        r"\b(?:GENERAL\s*ARR[AE]NGEM|GENERAL\s+(?:DRAWING|VIEW\s+TANK)\b"
        r"|(?:DISPOSICION|ARREGLO|PLANO)\s+GENERAL\b)",
        "su cajetín de disposición general",
    ),
    (
        "GA",
        r"\b(?:STOMPENLIJST|NOZZLES?\s+(?:LIST|SCHEDULE)|LISTA\s+DE\s+(?:BOQUILLAS|TUBULADURAS))\b",
        "su tabla de boquillas",
    ),
    (
        "GA",
        r"^(?:PRESSURE\s+)?VESSEL\s+ASSEMBLY$",
        "su título de conjunto del recipiente",
    ),
    (
        "VESOR",
        r"^(?:(?:VESSEL\s+)?NOZZLES?(?:\s*(?:&|AND)\s+PLATFORMS?)?\s+ORIENTATION|ORIENTATION\s+OF\s+NOZZLES|ORIENTACION\s+DE\s+BOQUILLAS|VESOR)\b",
        "su encabezado de orientación de boquillas",
    ),
    (
        "ESTRUCTURA",
        r"^(?:STRUCTURAL\s+(?:ARRANGEMENT|DRAWING)|ESTRUCTURA\s+AUXILIAR"
        r"|(?:SECTION\s+VIEW\s+)?TANK\s+STEEL\s+STRUCTURE"
        r"|TOP\s+OF\s+GRATING\s+WALKWAY\s+FOUNDATION)\b",
        "su rótulo de estructura auxiliar",
    ),
)


@dataclass(frozen=True)
class Metadata:
    kind: DocumentKind | None
    tag: str | None
    revision: str | None
    reason: str
    kind_source: EvidenceLine | None = None
    tag_source: EvidenceLine | None = None
    revision_source: EvidenceLine | None = None


def _group_pages(lines):
    pages = defaultdict(list)
    for line in lines:
        pages[line.source.page].append(line)
    return pages


def _adjacent(line, page):
    """Celdas alineadas del mismo cajetín, debajo o a la derecha de la etiqueta."""
    if not line.source.bbox:
        return
    x0, y0, x1, y1 = line.source.bbox
    h = y1 - y0
    for cell in page:
        if cell is line or not cell.source.bbox:
            continue
        a, b, c, e = cell.source.bbox
        if (0 <= a - x1 < 0.09 and abs(b - y0) <= h) or (
            0 <= b - y1 < 0.02 and a < x1 and c > x0 and e - y0 < max(h * 5, 0.025)
        ):
            yield cell


def _label(lines, key):
    label, value = _LABELS[key]
    direct = re.compile(rf"^{label}(?:\s*[:#=]\s*|\s+)({value})\s*$")
    standalone = re.compile(rf"^{label}\s*[:#=]?$")
    loose = re.compile(value)
    matches = {}
    for page in _group_pages(lines).values():
        for line in page:
            canon = normalizar(line.text).strip()
            if match := direct.fullmatch(canon):
                matches.setdefault(match[1], line)
            if standalone.fullmatch(canon):
                for cell in _adjacent(line, page):
                    candidate = normalizar(cell.text).strip()
                    if loose.fullmatch(candidate):
                        matches.setdefault(candidate, cell)
    if key == "tag":
        for line in lines:
            match = _TAG_EN_TITULO.fullmatch(normalizar(line.text).strip())
            if match and any(char.isdigit() for char in match[1]):
                matches.setdefault(match[1], line)
        matches = {
            value: line
            for value, line in matches.items()
            if TAG.fullmatch(value)
            and value not in {"NO", "TAG", "TYPE", "ITEM", "NAME", "NUMBER", "REV"}
        }
    if len(matches) == 1:
        return next(iter(matches.items()))
    return None, None


_REVISION_DEL_PLANO = re.compile(
    r"^(?:DRAWING\s+REV(?:ISION)?|REV(?:ISION)?\s+DEL\s+PLANO)[.\s:#=]+([A-Z0-9]{1,8})$"
)
_NUMERO_DE_PLANO = re.compile(r"^(?:DRAWING|DOCUMENT)\s+(?:NO\.?|NUMBER)\b")


def revision_del_plano(lines: list[EvidenceLine]) -> tuple[str | None, EvidenceLine | None]:
    """Un rótulo explícito o un campo Rev. junto al número de plano en el cajetín."""
    revisiones = {}
    for row in lines:
        if match := _REVISION_DEL_PLANO.fullmatch(normalizar(row.text).strip()):
            revisiones.setdefault(match[1], row)
    for page in _group_pages(lines).values():
        for row in page:
            box = row.source.bbox
            if box is None or box[1] < 0.75 or not _NUMERO_DE_PLANO.match(normalizar(row.text)):
                continue
            vecinos = [
                line
                for line in page
                if (b := line.source.bbox)
                and abs(b[1] - box[1]) <= 0.05
                and box[0] - 0.05 <= b[0] <= box[2] + 0.12
            ]
            valor, evidence = _label(vecinos, "revision")
            if valor:
                revisiones.setdefault(valor, evidence)
    if len(revisiones) == 1:
        return next(iter(revisiones.items()))
    return None, None


def _nozzle_columns(lines):
    from .tablas import _columna, _tipo

    for page in _group_pages(lines).values():
        rows: list[list[EvidenceLine]] = []
        for line in sorted(
            (line for line in page if line.source.bbox), key=lambda line: line.source.bbox[1]
        ):
            if rows and line.source.bbox[1] - rows[-1][0].source.bbox[1] < 0.008:
                rows[-1].append(line)
            else:
                rows.append([line])
        for row in rows:
            cells = [(_columna(cell.text), cell) for cell in row]
            roles = [role for role, _ in cells]
            if _tipo(roles) == "ga_table" or {"mark", "size_nps", "standout"} <= set(roles):
                headers = [
                    cell
                    for role, cell in cells
                    if role in ("mark", "size_nps", "rating", "standout")
                ]
                headers.sort(key=lambda cell: cell.source.bbox[0])
                boxes = [cell.source.bbox for cell in headers]
                bbox = (
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                )
                return EvidenceLine(
                    text=" / ".join(cell.text for cell in headers),
                    source=headers[0].source.model_copy(update={"bbox": bbox}),
                )
    return None


def _kind(lines):
    texts = [(line, normalizar(line.text)) for line in lines]
    for kind, pattern, reason in _HEADINGS:
        if line := next((line for line, text in texts if re.search(pattern, text)), None):
            return kind, reason, line
    if line := _nozzle_columns(lines):
        return "GA", "su tabla de boquillas", line
    # Un GA escaneado puede conservar solo los rótulos de ejes y de orientación.
    if roof := next((line for line, text in texts if "FLOATING ROOF" in text), None):
        if any("PLANTNORTH" in re.sub(r"\s+", "", text) for _, text in texts):
            return "GA", "sus rótulos de techo y norte de planta", roof
    # Lámina de detalles del GA: varias vistas de boquillas a distintas alturas.
    sections = [line for line, text in texts if re.match(r"^(TOP|MID|BOTTOM) SIDE NOZZLES\b", text)]
    if len(sections) >= 2:
        return "GA", "sus secciones de boquillas", sections[0]
    return None, "No se pudo clasificar por el contenido; indique el tipo documental", None


def _alternative_text(data: bytes, document_id: str) -> list[EvidenceLine]:
    """Segunda lectura de la capa de texto cuando las fuentes CAD entremezclan caracteres."""
    from pypdfium2 import PdfDocument, PdfiumError

    from ..pdf_limits import PDFIUM_LOCK

    lines = []
    try:
        with PDFIUM_LOCK, PdfDocument(data) as pdf:
            for i, page in enumerate(pdf, 1):
                rows = page.get_textpage().get_text_bounded().splitlines()
                lines.extend(
                    EvidenceLine(
                        text=text.strip(),
                        source=Source(
                            document_id=document_id,
                            page=i,
                            confidence=0.75,
                            locator=f"Texto de página {i}",
                        ),
                    )
                    for text in rows
                    if text.strip()
                )
                page.close()
    except (PdfiumError, OSError, ValueError):
        return []
    return lines


def classify(
    bundle: Bundle, *, kind=None, equipment_tag=None, tag_hint=None, data: bytes | None = None
) -> Metadata:
    named = dataset_filename(bundle.document.filename)
    if kind is not None:
        document_kind, reason, source = kind, "indicación manual", None
    elif named:
        document_kind, reason, source = named.kind, "su nombre", None
    else:
        document_kind, reason, source = _kind(bundle.lines)
        if document_kind is None and data is not None and bundle.media_type == "pdf":
            document_kind, reason, source = _kind(_alternative_text(data, bundle.document.id))
    tag_source = revision_source = None
    if named:
        tag, revision = named.catalogue_tag, named.revision
        # Las cargas anteriores a separar los GA pueden reintentarse con su tag antiguo.
        if named.mechanical_kind and tag_hint == named.tag:
            tag = tag_hint
    else:
        tag, tag_source = _label(bundle.lines, "tag") if document_kind == "GA" else (None, None)
        revision, revision_source = _label(bundle.lines, "revision")
    return Metadata(
        document_kind,
        equipment_tag or tag or tag_hint,
        revision,
        reason,
        source,
        None if equipment_tag else tag_source,
        revision_source,
    )


def plan_b_ocr(kind: DocumentKind | None, tag: str | None) -> bool:
    # Alcance del OCR existente, validado con estos dos originales.
    return (kind, tag) in {("VESOR", "62T02"), ("GA", "BP-T-710")}

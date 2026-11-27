"""Lee HDM vectoriales y devuelve candidatos con citas en puntos PDF."""

import argparse
import io
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber

from ..extraction import Candidate as FieldCandidate
from ..extractors.units import parse_nps
from ..model import Source
from ..units import UnitError, normalize

NOZZLE_TITLE = re.compile(r"NOZZLES? MECHANICAL INFORMATION|NOZZLE AND MANHOLE SCHEDULE", re.I)
WEIGHT = r"WEI(?:GHT|GTH|HGT)"
GENERAL_TITLE = re.compile(
    rf"DESIGN SPECIFICATION|MATERIAL SPECIFICATION|{WEIGHT}\s*&\s*CAPACITY",
    re.I,
)
TANK_TITLE = re.compile(r"SIZE LIMITATIONS", re.I)
MARK = re.compile(r"([A-Z]{1,3})(\d{1,3})([A-Z]?)")
MISSING = re.compile(r"REFER(?: TO)? (?:THE )?SKETCH|\bHOLD\b|^(?:[-–—]+|N/?A|TBD)$", re.I)
_PARENTESIS_HOLD = re.compile(r"\s*\(\s*HOLD\s*\)", re.I)
RATING_STANDARD = re.compile(r"\b(?:API|ASME|ANSI|AWWA|EN)\s*[A-Z]?\s*\d", re.I)
EXPLICIT_RATING = re.compile(r"\b(?:CLASS\s*\d+|PN\s*\d+|\d+\s*#)", re.I)
PROJECTION_TOPIC = re.compile(
    r'\b(?:projections?|flange face|face of (?:the )?flange|dimension\s+["“]?L["”]?)\b', re.I
)
PROJECTION_ORIGIN = re.compile(r"\bfrom\b", re.I)
PROJECTION_BASIS = re.compile(
    r"\s+(?:the\s+)?(?:"
    r"(?P<axis>(?:vessel\s+)?(?:cent(?:er|re)[ -]?line|cent(?:ral|er|re) axis))|"
    r"(?P<shell>(?:vessel\s+)?shell|vessel wall|"
    r"(?:outside|outer)(?: surface)? (?:of (?:the )?)?shell))\b",
    re.I,
)
CONDITIONAL_BASIS = re.compile(
    r"\b(?:except|unless|excluding|only|otherwise)\b"
    r"|\bfor (?:vertical|horizontal|axial|radial|nozzles? (?:on|at|in|above|below))\b",
    re.I,
)
NOTE_MARK = r"[A-Z]{1,3}\s*\d{1,3}[A-Z]?"
NOTE_MARKS = rf"{NOTE_MARK}(?:\s*[/,–—-]\s*(?:{NOTE_MARK}|\d{{1,3}}|[A-Z])|\s+and\s+{NOTE_MARK})*"
PROJECTION_SCOPE = re.compile(
    rf"(?:^|\b(?:for|nozzles?)\s+)(?P<marks>{NOTE_MARKS})(?=\s|[:.]|$)", re.I
)

HEADERS = (
    ("mark", r"MARK(?: Nº| NO\.?)?|ITEM|NOZZLE (?:NO\.?|MARK)"),
    ("quantity", r"QTY\.?|QUANTITY|Q'TY"),
    ("size_nps", r"SIZE(?: \(?NPS\)?)?|NPS|NOMINAL SIZE"),
    ("service", r"SERVICE|SERIVCE|DESCRIPTION"),
    ("projection", r"PROJ(?:ECTION)?\.?(?: [\"“”]?[L][\"“”]?)?"),
    ("rating", r"RATING|CLASS"),
    ("facing", r"TYPE[-/ ]?FACING|FACING|FLANGE TYPE|TYPE"),
    ("schedule", r"SCH(?:EDULE|DULE)?\.?|NECK THICKNESS"),
)
HEADER_PATTERNS = tuple(
    (name, re.compile(r"(?<!\w)(?:" + pattern + r")(?!\w)", re.I)) for name, pattern in HEADERS
)

GENERAL_FIELDS = (
    ("design_pressure", r"DESIGN (?:INTERNAL )?PRESSURE", "pressure", None),
    ("design_temperature", r"DESIGN TEMP(?:ERATURE)?", "temperature", "C"),
    ("mawp", r"MAWP|MAX(?:IMUM)?\.? ALLOWABLE WORKING PRESSURE", "pressure", None),
    ("mdmt", r"MDMT|MIN(?:IMUM)?\.? DESIGN METAL TEMP(?:ERATURE)?", "temperature", "C"),
    ("pwht", r"PWHT|POST[- ]?WELD HEAT TREATMENT|STRESS RELIEVING", None, None),
    ("insulation_thickness", r"INSULATION(?: THICKNESS)?", "length", "mm"),
    ("weight_transport", rf"(?:TRANSPORT|SHIPPING)(?: {WEIGHT})?", "mass", "kg"),
    ("weight_empty", rf"(?:EMPTY|DRY|SHUT[- ]DOWN)(?: {WEIGHT})?", "mass", "kg"),
    ("weight_operating", rf"(?:OPERAT(?:ING|ION)|FULL)(?: {WEIGHT})?", "mass", "kg"),
    (
        "weight_test",
        rf"(?:FIELD )?(?:HYDRO(?:STATIC)?(?: ?TEST)?|TEST)(?: {WEIGHT})?",
        "mass",
        "kg",
    ),
    ("capacity", r"(?:TOTAL |VESSEL )?(?:CAPACITY|VOLUME)", "volume", "m3"),
)
NUMBER = r"[+\-−]?\d+(?:[.,]\d+)*(?: \d{3}(?:[.,]\d+)*)*"
UNITS = {
    "length": r"mm|cm|m|in|ft",
    "pressure": r"kgf?\s*/\s*cm[2²]|[kM]Pa|bar(?:\s*\(?[ga]\)?)?|psi[ga]?",
    "temperature": r"[°º]?\s*[CF]",
    "mass": r"kgs?|t|lbs?",
    "volume": r"m[3³]|liters?|l",
}
PIECES = (
    r"SHELL(?:\s*/\s*CONE)?|HEADS?|BOTTOMS?|TOP HEAD|BOTTOM HEAD|SKIRT|SUPPORTS?"
    r"|(?:NOZZLE |BODY )?FLANGES?(?:\s*/\s*FORGING)?|NOZZLE NECKS?"
)
PIECE_FIELD = re.compile(
    rf"(?P<piece>SHELL\s*&\s*HEADS|{PIECES})(?: (?:MATERIAL|THICKNESS|THK\.?|PLATE))?"
    rf"|(?:MATERIAL|THICKNESS|THK\.?) (?:OF )?(?P<reverse>{PIECES})",
    re.I,
)
TANK_COURSE = re.compile(
    r"(?:SHELL )?(?:COURSE|RING)\s*(?:NO\.?\s*)?(\d+)(?:\s+TH(?:ICKNESS|K)\.?)?",
    re.I,
)
TANK_INLINE_DIMENSIONS = (
    ("diameter", re.compile(rf"\bTank Diameter\s*\*?\s*I\.?D\.?\s*:?\s*({NUMBER}\s*m)\b", re.I)),
    ("height", re.compile(rf"\bShell Height\s*\*?\s*:?\s*({NUMBER}\s*m)\b", re.I)),
)
TANK_COURSE_RANGE = re.compile(
    rf"\bShell,?\s+Course\s+_*([1-9]\d*)_*\s+to\s+_*([1-9]\d*)_*\s+(.+?)\s*/\s*({NUMBER})",
    re.I,
)
ROOF_KIND = re.compile(
    r"\b(?:FIXED ROOF TYPE|ROOF TYPE|TYPE OF (?:FIXED )?ROOF)[^;]{0,65}"
    r"\b(SUPPORTED DOME|DOME[D]?|CONE|CONICAL|FLAT)\b",
    re.I,
)
TANK_CAPACITY = (
    ("capacity", re.compile(rf"\bCapacity\s*:\s*Maximum\s*\*?\s*({NUMBER})", re.I)),
    ("capacity_working", re.compile(rf"\bNet Working\s*\*?\s*({NUMBER})", re.I)),
)


@dataclass(frozen=True)
class Citation:
    document_id: str
    page: int
    bbox: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True)
class Candidate:
    path: str
    value: str | float
    unit: str
    source: Citation
    confidence: float = 0.9
    unit_original: str | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class Notice:
    path: str
    message: str
    source: Citation


@dataclass
class HDMReading:
    candidates: list[Candidate] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    appearances: dict[str, list[Citation]] = field(default_factory=dict)

    def emit(self, path: str, value: str | float, source: Citation, unit: str = "1", **extra):
        self.candidates.append(Candidate(path, value, unit, source, **extra))

    def warn(self, path: str, message: str, source: Citation):
        self.notices.append(Notice(path, message, source))


def expand_marks(text: str) -> list[str]:
    """Expande rangos, listas y sufijos de una celda de marcas."""
    marks: dict[str, None] = {}
    previous = None
    compact = re.sub(r"\s*\(HOLD\)$", "", text.upper())
    compact = re.sub(r"\s+", "", compact).replace("–", "-").replace("—", "-")
    for token in re.split(r"[/,;]", compact):
        if previous and re.fullmatch(r"[A-Z]", token):
            token = f"{previous[1]}{int(previous[2])}{token}"
        elif previous and token.isdecimal():
            token = f"{previous[1]}{token}"
        start, separator, end = token.partition("-")
        match = MARK.fullmatch(start)
        if not match and re.fullmatch(r"\d{1,3}[A-Z]{1,3}", start):
            match = MARK.fullmatch(start[::-1])
        if not match:
            return []
        prefix, number, suffix = match.groups()
        first = int(number)
        if not separator:
            marks[f"{prefix}{first}{suffix}"] = None
        else:
            last = MARK.fullmatch(f"{prefix}{end}" if end.isdecimal() else end)
            if not last or last[1] != prefix or suffix or last[3]:
                return []
            if not 0 <= int(last[2]) - first < 99:
                return []
            for n in range(first, int(last[2]) + 1):
                marks[f"{prefix}{n}"] = None
        previous = match
    return list(marks)


def _text(words: list[dict]) -> str:
    return " ".join(word["text"] for word in words)


def _citation(words: list[dict], document_id: str, page: int) -> Citation:
    return Citation(
        document_id,
        page,
        (
            min(word["x0"] for word in words),
            min(word["top"] for word in words),
            max(word["x1"] for word in words),
            max(word["bottom"] for word in words),
        ),
        _text(words),
    )


def _rows(page) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for word in sorted(page.extract_words(x_tolerance=1.5), key=lambda word: word["top"]):
        if rows and abs(rows[-1][0]["top"] - word["top"]) <= 3:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(row, key=lambda word: word["x0"]) for row in rows]


def _header(words: list[dict]) -> dict[str, float]:
    offsets = []
    n = 0
    for word in words:
        offsets.append((n, word["x0"]))
        n += len(word["text"]) + 1
    row = _text(words)
    return {
        name: next(x for offset, x in reversed(offsets) if offset <= match.start())
        for name, pattern in HEADER_PATTERNS
        if (match := pattern.search(row)) is not None
    }


def _merge_edges(values) -> list[float]:
    edges: list[float] = []
    for value in sorted(values):
        if not edges or value - edges[-1] > 2:
            edges.append(value)
    return edges


def _column_rules(page, y: float, columns: dict[str, float]) -> dict[str, tuple[float, float]]:
    edges = _merge_edges(
        edge["x0"] for edge in page.vertical_edges if edge["top"] < y < edge["bottom"]
    )
    intervals = list(zip(edges, edges[1:]))
    rules = {}
    for name, x in columns.items():
        for left, right in intervals:
            if left <= x < right:
                rules[name] = (left, right)
                break
    if len(rules) < len(columns) or len(set(rules.values())) < len(rules):
        return {}
    return rules


def _cells(
    words: list[dict], columns: dict[str, float], rules: dict[str, tuple[float, float]]
) -> dict[str, str]:
    cells: dict[str, list[dict]] = {}
    for word in words:
        x = (word["x0"] + word["x1"]) / 2
        if rules:
            column = next((name for name, (a, b) in rules.items() if a <= x < b), None)
        else:
            column = min(columns, key=lambda name: abs(columns[name] - word["x0"]))
        if column:
            cells.setdefault(column, []).append(word)
    return {name: _text(cell).strip() for name, cell in cells.items()}


def _table(page, rows: list[list[dict]]) -> tuple[dict, dict, list[list[dict]]]:
    for i, row in enumerate(rows):
        columns = _header(row)
        if "mark" not in columns or not {"service", "quantity", "size_nps"} & columns.keys():
            continue
        y = (row[0]["top"] + row[0]["bottom"]) / 2
        for nearby in rows[max(0, i - 4) : i + 4]:
            for name, x in _header(nearby).items():
                columns.setdefault(name, x)
        if "size_nps" not in columns:
            continue
        rules = _column_rules(page, y, columns)
        if not rules:
            return columns, rules, rows[i + 1 :]
        mark_x = sum(rules["mark"]) / 2
        boundaries = _merge_edges(
            edge["top"]
            for edge in page.horizontal_edges
            if edge["x0"] < mark_x < edge["x1"] and edge["top"] > y
        )
        if len(boundaries) < 3:
            return columns, rules, rows[i + 1 :]
        groups = [[] for _ in boundaries]
        for words in rows[i + 1 :]:
            for word in words:
                center = (word["top"] + word["bottom"]) / 2
                for index, (top, bottom) in enumerate(zip(boundaries, boundaries[1:])):
                    if top <= center < bottom:
                        groups[index].append(word)
                        break
        return columns, rules, [group for group in groups if group]
    return {}, {}, []


def _quantity(
    result: HDMReading, path: str, value: str, source: Citation, magnitude: str, unit: str | None
) -> None:
    try:
        parsed = normalize(value, magnitude, default_unit=unit)
    except UnitError as exc:
        result.warn(path, str(exc), source)
        return
    result.emit(path, parsed.value, source, parsed.unit, unit_original=parsed.unit_original)
    for notice in parsed.notices:
        result.warn(path, notice, source)


def _measured(
    result: HDMReading,
    path: str,
    text: str,
    source: Citation,
    magnitude: str,
    unit: str | None,
    *,
    unit_in_label: bool = False,
) -> None:
    value = re.match(rf"(?P<number>{NUMBER})(?:\s*(?P<unit>{UNITS[magnitude]})(?!\w))?", text, re.I)
    if not value:
        result.warn(path, f"Valor pendiente: {text}", source)
        return
    suffix = text[value.end() :].lstrip()
    if not value["unit"] and not unit_in_label and re.match(r"[\w°º/″\"]", suffix):
        result.warn(path, f"Unidad o formato no reconocido: {text}", source)
        return
    original_unit = value["unit"] or unit
    _quantity(result, path, value["number"], source, magnitude, original_unit)


def _table_row(
    result: HDMReading,
    cells: dict[str, str],
    source: Citation,
) -> None:
    marks = expand_marks(cells.get("mark", ""))
    if not marks:
        return
    quantity = cells.get("quantity", "")
    if quantity.isdecimal() and int(quantity) != len(marks):
        result.warn("nozzles", "La cantidad de la fila no coincide con sus marcas", source)
        if len(marks) > 1:
            return
    for mark in marks:
        prefix = f"nozzles.{mark}"
        result.appearances.setdefault(mark, []).append(source)
        for name in ("size_nps", "service", "projection", "rating", "facing", "schedule"):
            value = cells.get(name)
            if not value:
                continue
            path = f"{prefix}.{name}"
            # «8 (HOLD)» cita el 8 y marca que está en hold. «(HOLD)» solo sigue pendiente.
            limpio = _PARENTESIS_HOLD.sub("", value).strip()
            en_hold = limpio != value.strip()
            if not limpio or MISSING.search(limpio):
                result.warn(path, f"Valor pendiente: {value}", source)
                continue
            if en_hold:
                result.warn(path, f"Valor en hold: {value}", source)
            value = limpio
            if name == "size_nps":
                size = parse_nps(value)
                if size is None:
                    result.warn(path, f"Tamaño no reconocido: {value}", source)
                    continue
                nps, outside = size
                result.emit(path, nps, source, "in", unit_original="NPS")
                if outside is not None:
                    result.emit(
                        f"{prefix}.diameter",
                        outside,
                        source,
                        "mm",
                        explanation="Diámetro exterior según ASME B36.10",
                    )
            elif name == "projection":
                _quantity(result, path, value, source, "length", "mm")
            elif (
                name == "rating"
                and RATING_STANDARD.search(value)
                and not EXPLICIT_RATING.search(value)
            ):
                result.warn(path, f"Norma citada sin clase de presión: {value}", source)
            else:
                result.emit(path, value, source)


def _tank_row(result: HDMReading, line: str, source: Citation) -> None:
    for name, pattern in TANK_INLINE_DIMENSIONS:
        if match := pattern.search(line):
            _quantity(result, f"tank.{name}", match[1], source, "length", None)
            if name == "diameter":
                result.emit("attributes.diameter_basis", "inside", source)
    if match := ROOF_KIND.search(line):
        word = match[1].casefold()
        roof = "domed" if "dome" in word else ("flat" if word == "flat" else "conical")
        result.emit("tank.roof", roof, source)
    for name, pattern in TANK_CAPACITY:
        if match := pattern.search(line):
            # El formulario coloca la nota y el indicador VTC entre el número y la unidad.
            tail = re.sub(r"^\s*\([^)]*\)", "", line[match.end() :])
            if unit := re.match(r"\s*(m[3³]|l)\b", tail, re.I):
                _quantity(result, f"attributes.{name}", match[1], source, "volume", unit[1])
                if "(VTC)" in line[match.end() : match.end() + 9].upper():
                    result.warn(
                        f"attributes.{name}", "Valor por confirmar por el proveedor", source
                    )
    if match := TANK_COURSE_RANGE.search(line):
        start, end = int(match[1]), int(match[2])
        if 0 <= end - start < 99:
            for course in range(start, end + 1):
                prefix = f"tank.courses.{course}"
                _quantity(result, f"{prefix}.thickness", match[4], source, "length", "mm")
                result.emit(f"{prefix}.material", match[3], source)
    key, colon, value = line.partition(":")
    if colon and (course := TANK_COURSE.fullmatch(key.strip())):
        _measured(
            result,
            f"tank.courses.{int(course[1])}.thickness",
            value.strip(),
            source,
            "length",
            "mm",
        )


def _piece_fields(
    result: HDMReading, line: str, source: Citation, *, material_section: bool
) -> None:
    match = PIECE_FIELD.match(line)
    if not match:
        return
    piece_name = re.sub(r"\s+", " ", (match["piece"] or match["reverse"]).lower())
    if piece_name in {"head", "bottom", "bottoms"}:
        piece_name = "heads"
    pieces = ("shell", "heads") if "&" in piece_name else (piece_name.split(" / ")[0],)
    key, value = match[0], line[match.end() :].lstrip(" :")
    if not value or (not material_section and not re.search(r"MATERIAL|THICKNESS|THK", key, re.I)):
        return
    if re.search(r"THICKNESS|THK", key, re.I):
        material, thickness = "", value
    elif (
        material_section
        and "MATERIAL" not in key.upper()
        and (
            tail := re.search(
                r"(?<=\s)(\d+(?:\s*[,;]\s*\d+)+|\d+(?:[.,]\d+)?)(?:\s*\(AF\))?$", value
            )
        )
        and not re.search(r"\b(?:Gr|Grade|Tp|Type)\.?$", value[: tail.start()].rstrip(), re.I)
    ):
        material, thickness = value[: tail.start()].rstrip(), tail[1]
    else:
        material, thickness = value, ""
    for piece in pieces:
        piece = piece.replace(" ", "_")
        if material and not MISSING.search(material):
            result.emit(f"attributes.material_{piece}", material, source)
        if thickness and not MISSING.search(thickness):
            path = f"attributes.{piece}_thickness"
            if re.search(r",\s+\d|,\d+,|;\s*\d|/\s*\d", thickness):
                result.emit(f"{path}es", thickness, source)
            else:
                _measured(result, path, thickness, source, "length", "mm")


def _general_row(
    result: HDMReading, source: Citation, *, tank: bool, material_section: bool
) -> None:
    line = re.sub(r"^(?:\d+[.)]?\s+)+", "", source.text)
    if tank:
        _tank_row(result, line, source)
        if TANK_CAPACITY[0][1].search(line):
            return
    for name, pattern, magnitude, default_unit in GENERAL_FIELDS:
        key = re.match(rf"(?:{pattern})(?![\w-])", line, re.I)
        if not key:
            continue
        tail = line[key.end() :].lstrip(" :=")
        unit = default_unit
        label = re.match(rf"\(?({UNITS[magnitude]})\)?(?!\w)", tail, re.I) if magnitude else None
        if label:
            unit = label[1]
            tail = tail[label.end() :].lstrip(" :=")
        if name == "insulation_thickness" and tail.startswith("/ Type:"):
            tail = tail.removeprefix("/ Type:").strip()
        if tail and not tail.startswith(("+", "(Upset)")):
            path = f"attributes.{name}"
            if MISSING.search(tail):
                result.warn(path, f"Valor pendiente: {tail}", source)
            elif magnitude and (name != "insulation_thickness" or re.match(NUMBER, tail)):
                _measured(
                    result, path, tail, source, magnitude, unit, unit_in_label=label is not None
                )
            else:
                name = "insulation" if name == "insulation_thickness" else name
                result.emit(f"attributes.{name}", tail.split(" Wind code:")[0], source)
        return
    _piece_fields(result, line, source, material_section=material_section)


def read_hdm(path: Path | str, *, document_id: str | None = None) -> HDMReading:
    """Lee páginas tituladas de una HDM y conserva el origen de cada valor."""
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        return _read_pdf(pdf, document_id or path.stem)


def read_candidates(data: bytes, document_id: str) -> tuple[list[FieldCandidate], list[str]]:
    """Entrega candidatos del contrato, con cajas normalizadas para la API y el pipeline."""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        reading = _read_pdf(pdf, document_id)
        page_boxes = {page.page_number: page.bbox for page in pdf.pages}
    candidates = []
    warnings = [
        f"{document_id} · página {notice.source.page} · {notice.path}: {notice.message}"
        for notice in reading.notices
    ]
    for item in reading.candidates:
        cite = item.source
        left, top, right, bottom = page_boxes[cite.page]
        x0, y0, x1, y1 = cite.bbox
        bbox = (
            max(0.0, (x0 - left) / (right - left)),
            max(0.0, (y0 - top) / (bottom - top)),
            min(1.0, (x1 - left) / (right - left)),
            min(1.0, (y1 - top) / (bottom - top)),
        )
        if not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
            continue
        candidates.append(
            FieldCandidate(
                path=item.path,
                value=item.value,
                unit=item.unit,
                source=Source(
                    document_id=document_id,
                    page=cite.page,
                    bbox=bbox,
                    locator=cite.text,
                    confidence=item.confidence,
                    channel="hoja_datos",
                    text_original=cite.text,
                    unit_original=item.unit_original,
                ),
                channel="hoja_datos",
                confidence_raw=item.confidence,
                text_original=cite.text,
                unit_original=item.unit_original,
                explanation=item.explanation,
            )
        )
    return candidates, warnings


def _read_pdf(pdf, document_id: str) -> HDMReading:
    result = HDMReading()
    pages = [_rows(page) for page in pdf.pages]
    tank = any(TANK_TITLE.search(_text(row)) for rows in pages for row in rows)
    for page, rows in zip(pdf.pages, pages, strict=True):
        page_number = page.page_number
        table_start = next(
            (i for i, row in enumerate(rows) if NOZZLE_TITLE.search(_text(row))), None
        )
        if table_start is not None:
            columns, rules, table_rows = _table(page, rows[table_start + 1 :])
            for row in table_rows:
                _table_row(
                    result,
                    _cells(row, columns, rules),
                    _citation(row, document_id, page_number),
                )
        if tank or any(GENERAL_TITLE.search(_text(row)) for row in rows):
            material_section = False
            for row in rows:
                source = _citation(row, document_id, page_number)
                if title := GENERAL_TITLE.search(source.text):
                    material_section = title[0].upper().startswith("MATERIAL")
                    continue
                _general_row(result, source, tank=tank, material_section=material_section)
    _projection_references(result, pages, document_id)
    return result


def _projection_references(result: HDMReading, pages, document_id: str) -> None:
    marks = {
        candidate.path.split(".")[1]
        for candidate in result.candidates
        if candidate.path.endswith(".projection")
    }
    if not marks:
        return
    general: list[tuple[str | None, Citation]] = []
    scoped: dict[str, list[tuple[str | None, Citation]]] = {}
    for page, rows in enumerate(pages, 1):
        for row in rows:
            text = _text(row)
            if not PROJECTION_TOPIC.search(text):
                continue
            for clause in text.split(";"):
                origins = list(PROJECTION_ORIGIN.finditer(clause))
                if not origins:
                    continue
                scopes = list(PROJECTION_SCOPE.finditer(clause.strip()))
                named = {
                    mark
                    for scope in scopes
                    for mark in expand_marks(re.sub(r"\s+and\s+", ",", scope["marks"], flags=re.I))
                }
                if not named and not PROJECTION_TOPIC.search(clause):
                    continue
                # Una regla condicionada a la posición requiere conocer qué marcas la cumplen.
                # BTL y otras tangentes no son referencias de eje ni de pared.
                match = PROJECTION_BASIS.match(clause, origins[0].end())
                conditional = CONDITIONAL_BASIS.search(clause) is not None
                basis = match.lastgroup if match and len(origins) == 1 and not conditional else None
                note = (basis, _citation(row, document_id, page))
                if named:
                    for mark in named & marks:
                        scoped.setdefault(mark, []).append(note)
                    if conditional:
                        general.append((None, note[1]))
                else:
                    general.append(note)
    for mark in sorted(marks):
        notes = scoped.get(mark, general)
        bases = {basis for basis, _ in notes}
        path = f"nozzles.{mark}.projection_basis"
        if len(bases) == 1 and None not in bases:
            basis, source = notes[0]
            result.emit(path, basis, source)
        elif notes:
            for source in dict.fromkeys(source for _, source in notes):
                result.warn(path, "Referencia de proyección sin resolver: " + source.text, source)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="+", type=Path, help="HDM locales")
    args = parser.parse_args()
    result = {path.stem: asdict(read_hdm(path)) for path in args.pdf}
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

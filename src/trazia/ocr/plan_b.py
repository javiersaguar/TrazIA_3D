"""Rumbos explícitos con evidencia OCR para las láminas del plan B."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

MARK = r"[A-Z]{1,3}\s*\d{1,3}[A-Z]?"
ANGLE = r"\d{1,3}(?:[.,]\d+)?"
ANGLE_LABEL = re.compile(rf"(?P<bearing>{ANGLE})\s*[°º]")
PAIR = re.compile(
    rf"(?:(?P<mark>{MARK})\s*[:=·-]?\s*(?P<angle>{ANGLE})\s*[°º]"
    rf"|(?P<angle_first>{ANGLE})\s*[°º]\s*[:=·-]?\s*(?P<mark_last>{MARK}))",
    re.I,
)
PENDING = re.compile(r"\b(?:HOLD|PENDIENTE)\b", re.I)
NOTE_MARK = re.compile(rf"(?<!\w){MARK}(?!\w)", re.I)


def _normalize(text: str) -> str:
    return re.sub(r"(?<=[A-Z])0+(?=\d)", "", re.sub(r"\s+", "", text.upper()))


@dataclass(frozen=True)
class BearingReading:
    mark: str
    bearing: float
    evidence: dict
    hold_evidence: dict | None = None
    mark_evidence: dict | None = None


def explicit_bearings(lines: Iterable[dict], known_marks: set[str]) -> list[BearingReading]:
    """Exige marca registrada y ángulo en la misma lectura. Conserva el HOLD por separado."""
    holds = {}
    pairs = []
    for line in lines:
        text = line["text"].strip()
        if PENDING.search(text):
            for match in NOTE_MARK.finditer(text):
                mark = _normalize(match[0])
                if mark in known_marks:
                    holds.setdefault(mark, line)
            text = re.sub(r"\s*\(?\s*(?:ON\s+)?(?:HOLD|PENDIENTE)\s*\)?\s*$", "", text, flags=re.I)
        match = PAIR.fullmatch(text)
        if match:
            mark = _normalize(match["mark"] or match["mark_last"])
            bearing = float((match["angle"] or match["angle_first"]).replace(",", "."))
            if mark in known_marks and 0 <= bearing < 360:
                pairs.append((mark, bearing, line))
    return [BearingReading(mark, value, line, holds.get(mark)) for mark, value, line in pairs]


def _adjacent(a: dict, b: dict) -> bool:
    """Busca rótulos contiguos y alineados, con tolerancia relativa a su tamaño."""
    gaps = []
    for start, end in (("x0", "x1"), ("top", "bottom")):
        size = min(a[end] - a[start], b[end] - b[start])
        if size <= 0:
            return False
        gaps.append((max(a[start], b[start]) - min(a[end], b[end])) / size)
    alignment, separation = sorted(gaps)
    return alignment <= -0.8 and -0.4 <= separation <= 0.5


def nearby_bearings(lines: Iterable[dict], known_marks: set[str]) -> list[BearingReading]:
    """Sugiere pares únicos para revisión con las dos cajas OCR por separado."""
    marks = []
    angles = []
    holds = {}
    for line in lines:
        text = line["text"].strip()
        doc = line["document_id"]
        if PENDING.search(text):
            for match in NOTE_MARK.finditer(text):
                holds.setdefault((doc, _normalize(match[0])), line)
        if line.get("confidence", 0) < 0.70:
            continue
        if match := ANGLE_LABEL.fullmatch(text):
            value = float(match["bearing"].replace(",", "."))
            if 0 <= value < 360:
                angles.append((value, line))
        elif NOTE_MARK.fullmatch(text) and (mark := _normalize(text)) in known_marks:
            marks.append((mark, line))

    by_mark: dict[int, list[int]] = {}
    by_angle: dict[int, list[int]] = {}
    for i, (_, mark_line) in enumerate(marks):
        for j, (_, angle_line) in enumerate(angles):
            if (
                mark_line["document_id"] == angle_line["document_id"]
                and mark_line["page"] == angle_line["page"]
                and _adjacent(mark_line, angle_line)
            ):
                by_mark.setdefault(i, []).append(j)
                by_angle.setdefault(j, []).append(i)

    readings = []
    for i, options in by_mark.items():
        if len(options) != 1 or len(by_angle[options[0]]) != 1:
            continue
        mark, mark_line = marks[i]
        value, angle_line = angles[options[0]]
        hold = holds.get((mark_line["document_id"], mark))
        readings.append(BearingReading(mark, value, angle_line, hold, mark_line))
    return readings


def _box(source: dict) -> str:
    return ", ".join(f"{source[key]:.1f}" for key in ("x0", "top", "x1", "bottom"))


def bearing_notices(readings: list[BearingReading]) -> list[str]:
    """Expone rumbos citables al revisar sin inferir el marco del plano."""
    notices = []
    for item in readings:
        source = item.evidence
        reason = (
            f"HOLD según «{item.hold_evidence['text']}» (p. {item.hold_evidence['page']})"
            if item.hold_evidence
            else "pendiente de verificar el norte y el sentido del plano"
        )
        if item.mark_evidence is not None:
            mark = item.mark_evidence
            notices.append(
                f"OCR {source['document_id']} · p. {source['page']} · posible asociación "
                f"para cotejar con la línea de llamada: marca «{mark['text']}» "
                f"[{_box(mark)}], ángulo «{source['text']}» [{_box(source)}] · {reason}."
            )
            continue
        notices.append(
            f"OCR {source['document_id']} · p. {source['page']} · caja PDF [{_box(source)}] "
            f"· {item.mark}: rumbo {item.bearing:g}° en «{source['text']}» · {reason}."
        )
    return notices

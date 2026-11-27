"""Genera un GA nuevo de recipiente horizontal para una prueba fuera del catálogo."""

import argparse
import json
from dataclasses import asdict, dataclass
from math import cos, radians, sin
from pathlib import Path
from types import SimpleNamespace

from process_documents import INK, dimension, frame, ga_canvas, path, table, text, view_title

TAG = "KO-V-9207"
SHELL_ID = 2460
THK = 18
RADIUS = (SHELL_ID + 2 * THK) / 2
TANGENTS = 5600
HEAD_DEPTH = 624
CENTERLINE = 1670
SADDLES = (1220, 4270)
SADDLE_WIDTH = 420
SADDLE_SPAN = 1920
SCALE = 20
POINTS = 72 / (25.4 * 2 * SCALE)


@dataclass(frozen=True)
class Nozzle:
    mark: str
    nps: str
    dn: int
    od: float
    neck: float
    station: int
    clock: int
    projection: int
    service: str
    flange_type: str = "WN"

    @property
    def level(self):
        return round(CENTERLINE + cos(radians(self.clock)) * self.projection)


NOZZLES = (
    Nozzle("N1", "8", 200, 219.1, 8.18, 830, 0, 1605, "GAS INLET"),
    Nozzle("N2", "6", 150, 168.3, 7.11, 4630, 0, 1580, "GAS OUTLET"),
    Nozzle("N3", "3", 80, 88.9, 5.49, 5170, 180, 1440, "LIQUID DRAIN"),
    Nozzle("N4", "2", 50, 60.3, 3.91, 1880, 90, 1480, "LEVEL CONNECTION"),
    Nozzle("N5", "4", 100, 114.3, 6.02, 3930, 225, 1550, "LIQUID OUTLET"),
    Nozzle("M1", "18", 450, 457.0, 12.70, 2940, 0, 1640, "MANWAY"),
)


def axis(pdf, x0, y0, x1, y1):
    pdf.saveState()
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.26)
    pdf.setDash([7, 2.4, 1.1, 2.4])
    pdf.line(x0, y0, x1, y1)
    pdf.restoreState()


def mark(pdf, px, py, cx, cy, item):
    pdf.setStrokeColor(INK)
    pdf.setFillColor("#ffffff")
    pdf.setLineWidth(0.32)
    pdf.line(px, py, cx, cy)
    pdf.circle(px, py, 1.15, stroke=1, fill=1)
    pdf.circle(cx, cy, 7, stroke=1, fill=1)
    text(pdf, cx - 4.6, cy - 2.25, item, 6.3, True)


def shell(pdf, x, y, factor=POINTS):
    radius, length, depth = (value * factor for value in (RADIUS, TANGENTS, HEAD_DEPTH))
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.65)
    pdf.rect(x, y - radius, length, 2 * radius)
    pdf.arc(x - depth, y - radius, x + depth, y + radius, 90, 180)
    pdf.arc(x + length - depth, y - radius, x + length + depth, y + radius, 270, 180)
    pdf.setLineWidth(0.32)
    pdf.line(x + length / 2, y - radius, x + length / 2, y + radius)
    axis(pdf, x - depth - 12, y, x + length + depth + 12, y)
    return radius, length, depth


def nozzle_stem(pdf, base, end, width, *, back=False):
    dx, dy = end[0] - base[0], end[1] - base[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length < 0.5:
        return
    nx, ny = -dy / length, dx / length
    points = [
        (x + side * nx * width / 2, y + side * ny * width / 2)
        for (x, y), side in ((base, -1), (end, -1), (end, 1), (base, 1))
    ]
    pdf.saveState()
    if back:
        pdf.setDash(3, 1.6)
    path(pdf, points, fill=None if back else "#ffffff", weight=0.4, closed=True)
    pdf.setLineWidth(0.72)
    pdf.setStrokeColor(INK)
    pdf.line(
        end[0] - nx * (width / 2 + 2),
        end[1] - ny * (width / 2 + 2),
        end[0] + nx * (width / 2 + 2),
        end[1] + ny * (width / 2 + 2),
    )
    pdf.restoreState()


def elevation(pdf):
    x0, center = 437, 622
    radius, length, depth = shell(pdf, x0, center)
    floor = center - CENTERLINE * POINTS
    pdf.line(x0 - depth - 8, floor, x0 + length + depth + 15, floor)
    text(pdf, x0 - depth - 2, floor + 3, "EL. +0.000", 6.4)
    for i, station in enumerate(SADDLES):
        x = x0 + station * POINTS
        shoulder = center - radius + 12
        foot = SADDLE_WIDTH * POINTS / 2
        path(
            pdf,
            [
                (x - foot, floor),
                (x - foot + 4, shoulder),
                (x + foot - 4, shoulder),
                (x + foot, floor),
            ],
            fill="#ffffff",
            closed=True,
            weight=0.48,
        )
        pdf.rect(x - foot, floor, 2 * foot, 3.6)
        text(pdf, x - 18, floor - 10, "FIXED SADDLE" if i == 0 else "SLIDING SADDLE", 5.8)
    for item in NOZZLES:
        sx = x0 + item.station * POINTS
        radial = cos(radians(item.clock))
        end = sx, center + item.projection * POINTS * radial
        if abs(radial) < 0.05:
            pdf.circle(sx, center, item.od * POINTS / 2, stroke=1, fill=0)
            pdf.circle(sx, center, item.od * POINTS / 2 + 3, stroke=1, fill=0)
        else:
            nozzle_stem(
                pdf, (sx, center + radius * radial), end, item.od * POINTS, back=item.clock > 180
            )
        if radial > 0.1:
            mark(pdf, *end, sx, 760, item.mark)
            text(pdf, sx + 9, 756, f"+{item.level}", 6)
        elif abs(radial) > 0.1:
            mark(pdf, *end, sx + (10 if item.mark == "N3" else -13), floor - 13, item.mark)
        else:
            mark(pdf, *end, sx - 36, center + 24, item.mark)
    text(pdf, x0 - 4, center + radius + 4, "T.L.", 6.2)
    text(pdf, x0 + length - 8, center + radius + 4, "T.L.", 6.2)
    path(
        pdf,
        [
            (x0 + length + depth * 0.79, center + 54),
            (x0 + length + 64, center + 72),
            (x0 + length + 93, center + 72),
        ],
        weight=0.28,
    )
    text(pdf, x0 + length + 96, center + 69, "ELLIPSOIDAL HEAD 2:1", 6.6)
    text(pdf, x0 + length + 96, center + 59, "624 O/A HEAD DEPTH", 6.6)
    text(pdf, x0 + length / 2 + 8, center + 8, "I.D. Ø2460 x 18 mm", 7)
    dimension(pdf, x0, center - radius, x0 + length, center - radius, -51, "5600 (T.L. TO T.L.)")
    dimension(pdf, x0 - depth, center, x0 + length + depth, center, -160, "6848 O/A SHELL & HEADS")
    dimension(
        pdf,
        x0 + length + depth,
        floor,
        x0 + length + depth,
        center,
        -21,
        "1670",
        vertical=True,
    )
    view_title(pdf, 557, 789, "FRONT VIEW - HORIZONTAL VESSEL", SCALE)


def end_view(pdf):
    x, y, radius = 209, 623, RADIUS * POINTS
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.64)
    pdf.circle(x, y, radius, stroke=1, fill=0)
    pdf.saveState()
    pdf.setDash(3, 1.8)
    pdf.circle(x, y, SHELL_ID / 2 * POINTS, stroke=1, fill=0)
    pdf.restoreState()
    axis(pdf, x - 113, y, x + 113, y)
    axis(pdf, x, y - 117, x, y + 120)
    for phi in (0, 90, 180, 270):
        a = radians(phi)
        text(pdf, x + 116 * sin(a) - 5, y + 116 * cos(a) + 4, f"{phi}°", 7)
    for item in (NOZZLES[2], NOZZLES[3], NOZZLES[4]):
        phi = radians(item.clock)
        direction = sin(phi), cos(phi)
        base = tuple(origin + delta * radius for origin, delta in zip((x, y), direction))
        end = tuple(
            origin + delta * item.projection * POINTS for origin, delta in zip((x, y), direction)
        )
        nozzle_stem(pdf, base, end, item.od * POINTS, back=item.clock > 180)
        mark(
            pdf,
            *end,
            (end[0] - 17 if item.clock != 90 else end[0] + 22),
            end[1] + (13 if item.clock != 180 else -18),
            item.mark,
        )
    text(pdf, x - 25, y + 10, "I.D. Ø2460", 7, True)
    floor = y - CENTERLINE * POINTS
    pdf.line(x - 70, floor, x + 70, floor)
    dimension(pdf, x - radius, floor, x - radius, y, 33, "1670", vertical=True)
    view_title(pdf, 153, 789, 'VIEW "A" - FROM LEFT', SCALE)


def lower_views(pdf):
    x, y = 101, 338
    plan_scale = 25
    factor = POINTS * SCALE / plan_scale
    radius, length, depth = shell(pdf, x, y, factor)
    view_title(pdf, 83, 453, "KEY PLAN - TOP VIEW", plan_scale)
    for item in NOZZLES:
        xx = x + item.station * factor
        side = sin(radians(item.clock))
        if abs(side) > 0.05:
            nozzle_stem(
                pdf,
                (xx, y + radius * side),
                (xx, y + item.projection * factor * side),
                item.od * factor,
            )
        else:
            pdf.circle(xx, y, item.od * factor / 2, stroke=1, fill=0)
        mark(
            pdf,
            xx,
            y + item.projection * factor * side,
            xx,
            y + (radius + 9) * (1 if side >= 0 else -1),
            item.mark,
        )
    for station in SADDLES:
        xx = x + station * factor
        axis(pdf, xx, y - radius - 8, xx, y + radius + 8)
        text(pdf, xx - 12, y - radius + 4, f"+{station}", 6)
    dimension(
        pdf,
        x + SADDLES[0] * factor,
        y - radius,
        x + SADDLES[1] * factor,
        y - radius,
        -14,
        "3050 C/C SADDLES",
    )
    dimension(pdf, x - depth, y, x + length + depth, y, 91, "6848 O/A")
    view_title(pdf, 648, 440, "SADDLE SECTION B-B", None)
    sx, sy = 720, 273
    pdf.arc(sx - radius, sy + 28, sx + radius, sy + 28 + 2 * radius, 216, 108)
    path(
        pdf,
        [(sx - 63, sy + 63), (sx - 56, sy + 7), (sx + 56, sy + 7), (sx + 63, sy + 63)],
        closed=False,
        weight=0.62,
    )
    pdf.rect(sx - 72, sy, 144, 7)
    axis(pdf, sx, sy - 4, sx, sy + 90)
    text(pdf, sx - 47, sy + 16, "BASE PLATE - TYP.", 6.6)
    dimension(pdf, sx - 72, sy, sx + 72, sy, -12, str(SADDLE_SPAN))
    text(pdf, sx - 68, sy - 29, f"AXIAL BASE WIDTH: {SADDLE_WIDTH}", 6.4)
    view_title(pdf, 870, 440, "TYPICAL NOZZLE / N4", None)
    dx, dy = 948, 332
    path(
        pdf,
        [
            (dx - 70, dy - 31),
            (dx - 70, dy + 31),
            (dx - 66, dy + 31),
            (dx - 66, dy + 8),
            (dx + 50, dy + 8),
            (dx + 50, dy + 18),
            (dx + 58, dy + 18),
            (dx + 58, dy - 18),
            (dx + 50, dy - 18),
            (dx + 50, dy - 8),
            (dx - 66, dy - 8),
            (dx - 66, dy - 31),
        ],
        closed=True,
        weight=0.57,
    )
    axis(pdf, dx - 83, dy, dx + 76, dy)
    text(pdf, dx - 40, dy + 43, "Ø60.3 x 3.91 THK.", 7)
    text(pdf, dx + 29, dy - 37, "WN RF", 6.5)
    text(pdf, 868, 270, "VIEW SHOWS FLANGE AND NECK ONLY.", 6.3)


def schedules(pdf):
    text(pdf, 42, 224, "LISTA DE BOQUILLAS / NOZZLE LIST", 8.4, True)
    rows = [
        (
            n.mark,
            f'{n.nps}" [DN {n.dn}]',
            f"{n.od:g}",
            f"{n.neck:g}",
            "150#",
            "ASME B16.5",
            n.flange_type,
            "RF",
            n.projection,
            n.station,
            f"+{n.level}",
            f"{n.clock}°",
            n.service,
        )
        for n in NOZZLES
    ]
    table(
        pdf,
        42,
        214,
        (
            "POS.",
            "SIZE",
            "OD (mm)",
            "THK.",
            "RATING",
            "CODE",
            "TYPE",
            "FACE",
            "PROJECTION",
            "STATION",
            "EL. (mm)",
            "ORIENT.",
            "DESCRIPTION",
        ),
        rows,
        (29, 68, 45, 39, 39, 63, 30, 29, 62, 52, 57, 48, 140),
        18,
        font=6.4,
    )
    text(pdf, 766, 239, "LISTA DE MATERIALES / MATERIAL LIST", 8.2, True)
    material = [
        ("V01", "99092071", "1", "SHELL COURSE 1", "SA-516 GR. 70"),
        ("V02", "99092072", "1", "SHELL COURSE 2", "SA-516 GR. 70"),
        ("F01", "99092073", "2", "2:1 ELLIPSOIDAL HEAD", "SA-516 GR. 70"),
        ("S01", "99092074", "1", "FIXED SADDLE", "CARBON STEEL"),
        ("S02", "99092075", "1", "SLIDING SADDLE", "CARBON STEEL"),
    ]
    table(
        pdf,
        766,
        230,
        ("POS.", "CODE", "QTY.", "DESCRIPTION", "MATERIAL"),
        material,
        (40, 61, 28, 143, 114),
        12,
        font=6.2,
    )
    notes = (
        "N1. PROJECTION: FROM VESSEL CENTRELINE (C/L) TO FACE OF FLANGE.",
        "N2. ORIENTATION CLOCKWISE AS SEEN FROM VIEW A, 0° AT TOP.",
        "N3. ELEVATIONS FROM LOCAL DATUM EL. +0.000. STATIONS FROM LEFT T.L.",
        "N4. GENERAL ARRANGEMENT FOR A SYNTHETIC EXTRACTION TEST.",
    )
    for i, note in enumerate(notes):
        text(pdf, 766, 148 - 12 * i, note, 6.3)
    text(pdf, 42, 62, "ITEM NO. / EQUIPO", 6.6)
    text(pdf, 42, 44, TAG, 12, True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, default=Path("generated/plano-no-visto"))
    out = parser.parse_args().salida
    incoming = out / "entrada"
    incoming.mkdir(parents=True, exist_ok=True)
    target = incoming / f"GAD_{TAG}_rev0.pdf"
    pdf = ga_canvas(target, f"{TAG} | General arrangement | Synthetic")
    info = SimpleNamespace(code=TAG, setting="Ensayo")
    frame(pdf, info, "0", "GA-001", "General arrangement - horizontal knock-out drum", "1 / 1")
    elevation(pdf)
    end_view(pdf)
    lower_views(pdf)
    schedules(pdf)
    pdf.save()
    truth = {
        "dataset": "synthetic",
        "equipment": TAG,
        "family": "horizontal",
        "support": "saddles",
        "inside_diameter_mm": SHELL_ID,
        "tangent_to_tangent_mm": TANGENTS,
        "head_depth_mm": HEAD_DEPTH,
        "shell_thickness_mm": THK,
        "centerline_elevation_mm": CENTERLINE,
        "saddle_pitch_mm": SADDLES[1] - SADDLES[0],
        "saddle_positions_mm": SADDLES,
        "saddle_width_mm": SADDLE_WIDTH,
        "saddle_span_mm": SADDLE_SPAN,
        "projection_basis": "centerline_to_face",
        "nozzles": [{**asdict(item), "elevation_mm": item.level} for item in NOZZLES],
    }
    (out / "verdad.json").write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()

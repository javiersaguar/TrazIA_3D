from io import BytesIO

import pytest
from reportlab.pdfgen.canvas import Canvas

from trazia.ocr.engine import ocr_pdf_lines
from trazia.ocr.plan_b import bearing_notices, explicit_bearings, nearby_bearings


def test_plan_b_conserva_rumbos_y_hold_sin_asociar_otras_marcas():
    def line(text):
        return {
            "text": text,
            "document_id": "VESOR-SYN",
            "page": 1,
            "x0": 120.0,
            "top": 92.5,
            "x1": 157.5,
            "bottom": 101.0,
        }

    rows = [
        line("128°R7"),
        line("2. R7 ORIENTATION UNDER HOLD."),
        line("N01: 42,5°"),
        line("N90 75°"),
        line("N2 390°"),
        line("N3"),
        line("155°"),
    ]
    readings = explicit_bearings(rows, {"R7", "N1", "N2", "N3"})
    assert [(item.mark, item.bearing) for item in readings] == [("R7", 128), ("N1", 42.5)]
    assert readings[0].hold_evidence is rows[1]
    assert readings[1].hold_evidence is None
    warnings = bearing_notices(readings)
    assert "128°R7" in warnings[0] and "[120.0, 92.5, 157.5, 101.0]" in warnings[0]
    assert "HOLD según" in warnings[0]
    assert "norte y el sentido" in warnings[1]


def test_paginacion_ocr_vacia_o_invalida_no_procesa_un_pdf():
    pdf = BytesIO()
    canvas = Canvas(pdf)
    canvas.drawString(50, 100, "Texto")
    canvas.save()
    assert ocr_pdf_lines(pdf.getvalue(), "VESOR-SYN", pages=[]) == []
    with pytest.raises(ValueError, match="Página OCR fuera"):
        ocr_pdf_lines(pdf.getvalue(), "VESOR-SYN", pages=[0])


def test_ocr_sugiere_rotulos_contiguos_y_conserva_las_dos_citas():
    def line(text, box, *, page=1, confidence=0.95):
        return {
            "text": text,
            "document_id": "GA-SYN",
            "page": page,
            "confidence": confidence,
            **dict(zip(("x0", "top", "x1", "bottom"), box, strict=True)),
        }

    mark = line("R07", (10, 10, 21, 21))
    angle = line("112,5°", (11, 23, 22, 41))
    hold = line("R7: orientación pendiente HOLD", (50, 50, 90, 60), page=2)
    candidates = [
        mark,
        angle,
        hold,
        line("S9", (30, 100, 50, 120)),
        line("245°", (46, 108, 62, 123)),
        line("Q1", (100, 100, 110, 110)),
        line("66°", (100, 115, 110, 125), page=2),
        line("Q2", (40, 200, 52, 220)),
        line("85°", (69, 204, 82, 223)),
        line("Q3", (75, 238, 87, 253)),
        line("30°", (88, 239, 100, 253), confidence=0.50),
        line("Q4", (25, 265, 43, 287)),
        line("35°", (46, 276, 65, 291)),
        line("U2", (20, 300, 30, 310)),
        line("55°", (20, 311, 30, 321)),
        line("U3", (20, 322, 30, 332)),
        line("U7", (70, 320, 80, 330)),
        line("125°", (70, 307, 80, 318)),
        line("135°", (70, 331, 80, 343)),
        line("U8", (13, 390, 25, 400)),
        line("375°", (13, 401, 24, 411)),
    ]

    known = {"R7", "S9", "Q1", "Q2", "Q3", "Q4", "U2", "U3", "U7", "U8"}
    reading, diagonal = nearby_bearings(candidates, known)
    assert (reading.mark, reading.bearing, diagonal.mark, diagonal.bearing) == (
        "R7",
        112.5,
        "S9",
        245,
    )
    assert reading.evidence is angle and reading.mark_evidence is mark
    assert reading.hold_evidence is hold
    notice = bearing_notices([reading])[0]
    assert "posible asociación" in notice and "línea de llamada" in notice
    assert "«R07» [10.0, 10.0, 21.0, 21.0]" in notice
    assert "«112,5°» [11.0, 23.0, 22.0, 41.0]" in notice
    assert "HOLD según" in notice

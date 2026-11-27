"""Alzado sintético de columna: diámetro, tangentes, faldón y tramos con cita y comprobación.

Todo es inventado (columna C-1 de tres virolas y faldón de dos tramos): no hay datos de TR.
Las cotas giradas no tienen capa de texto y se simulan como líneas OCR.
"""

import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from trazia.extraction import Candidate, assemble
from trazia.ingest import ingest_bytes
from trazia.lectura import columna

DOC = "GA-C1"
CURSOS = {
    "V01": (3000, 10),
    "V02": (3000, 10),
    "V03": (2900, 12),
    "V04": (1500, 12),
    "V05": (1000, 16),
}


def _alzado():
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=A4)
    for x, y, texto in (
        (60, 760, "T.L."),
        (60, 300, "T.L."),
        (60, 290, "EL.±0.00"),
        (60, 80, "GROUND"),
        (120, 700, "V01"),
        (120, 560, "V02"),
        (120, 400, "V03"),
        (120, 250, "V04"),
        (120, 150, "V05"),
        (200, 600, "D.I./I.D. Ø1200"),
        (200, 255, "D.I./I.D. Ø1196"),
        (200, 150, "D.I./I.D. Ø1190"),
    ):
        doc.drawString(x, y, texto)
    doc.save()
    return buffer.getvalue()


def _cursos():
    salida = []
    for tramo, (alto, espesor) in CURSOS.items():
        for campo, valor in (("height", alto), ("thickness", espesor)):
            salida.append(
                {
                    "path": f"shell.courses.{tramo}.{campo}",
                    "value": float(valor),
                    "unit": "mm",
                    "source": {
                        "document_id": DOC,
                        "page": 1,
                        "locator": f"{tramo} THK. {espesor} x {alto}",
                        "confidence": 0.85,
                    },
                }
            )
    return salida


def _ocr(tangentes="9000", faldon="2600"):
    def falso(pdf, documento, *, pages, tiles):
        assert tiles and documento == DOC
        # Cajas en puntos PDF con origen arriba; el texto girado es más alto que ancho.
        return {
            pages[0]: [
                {"text": tangentes, "x0": 62, "x1": 70, "top": 290, "bottom": 320},
                {"text": faldon, "x0": 62, "x1": 70, "top": 600, "bottom": 630},
            ]
        }

    return falso


def _leer(monkeypatch, **ocr):
    monkeypatch.setattr(columna, "lines_in_pdf_points", _ocr(**ocr))
    avisos = []
    datos = columna.leer_columna(_alzado(), DOC, _cursos(), avisos)
    return {d["path"]: d for d in datos}, avisos


def test_la_columna_sale_del_alzado_con_cita_y_cuadre(monkeypatch):
    campos, avisos = _leer(monkeypatch)
    assert avisos == []
    assert campos["diameter"]["value"] == 1200
    assert campos["attributes.diameter_basis"]["value"] == "inside"
    assert campos["height"]["value"] == 9000
    assert campos["height"]["source"]["rule"] == "ga.columna_tangentes_ocr"
    # Orden de abajo arriba por la posición de la marca en el alzado.
    orden = {t: campos[f"column.sections.{t}.order"]["value"] for t in ("V01", "V02", "V03")}
    assert orden == {"V03": 1, "V02": 2, "V01": 3}
    assert "column.sections.V04.order" not in campos
    assert campos["skirt_height"]["value"] == 2600
    # El tramo más alto del faldón (V04) da el espesor y su diámetro interior rotulado.
    assert campos["skirt_thickness"]["value"] == 12
    assert campos["skirt_thickness"]["source"]["rule"] == "ga.columna_faldon_espesor"
    assert campos["attributes.skirt_diameter"]["value"] == 1196 + 2 * 12


def test_una_cota_que_no_cuadra_con_las_virolas_no_sale(monkeypatch):
    campos, avisos = _leer(monkeypatch, tangentes="12000")
    assert "height" not in campos and "column.sections.V01.order" not in campos
    assert campos["diameter"]["value"] == 1200
    assert any("no cuadra" in aviso for aviso in avisos)


def test_sin_ocr_la_columna_sigue_pidiendo_sus_cotas(monkeypatch):
    def sin_ocr(*args, **kwargs):
        raise OSError("sin motor")

    monkeypatch.setattr(columna, "lines_in_pdf_points", sin_ocr)
    avisos = []
    campos = {d["path"] for d in columna.leer_columna(_alzado(), DOC, _cursos(), avisos)}
    assert "height" not in campos and "skirt_height" not in campos
    assert any("OCR no disponible" in aviso for aviso in avisos)


def test_la_columna_leida_se_ensambla_con_tramos_y_faldon(monkeypatch):
    campos, _ = _leer(monkeypatch)
    pdf = _alzado()
    bundle = ingest_bytes(pdf, "drawing.pdf", DOC, "A")
    fuente = {"document_id": DOC, "page": 1, "locator": "C-1", "confidence": 0.9}
    datos = [
        *campos.values(),
        *_cursos(),
        {"path": "tag", "value": "C-1", "unit": "1", "source": fuente},
        {"path": "attributes.equipment_type", "value": "column", "unit": "1", "source": fuente},
        {"path": "attributes.support", "value": "skirt", "unit": "1", "source": fuente},
    ]
    candidatos = [Candidate.model_validate(d) for d in datos]
    borrador = assemble([bundle], candidatos, project_id="DEMO", equipment_id="C1", revision="A")
    equipo = borrador.equipment
    assert [s.id for s in equipo.column.sections] == ["V03", "V02", "V01"]
    assert sum(s.height.value for s in equipo.column.sections) == pytest.approx(8900)
    assert equipo.diameter.value == 1200 and equipo.height.value == 9000
    assert equipo.skirt_height.value == 2600 and equipo.skirt_thickness.value == 12


def _planta():
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=A4)
    for x, y, texto in (
        (60, 760, "T.L."),
        (60, 748, "EL.±0.00"),
        (200, 400, "270°"),
        (395, 400, "90°"),
        (250, 270, "ORIENTACIONES - VISTA POR ARRIBA"),
        (296, 515, "N1"),
        (377, 319, "N2"),
        (60, 100, "1.- CENTER LINE OF VESSEL TO FLANGE FACE, OR ELEVATION FROM TANGENT"),
        (430, 600, "EL.+4500"),
        (430, 588, "C.D.G. / C.O.G."),
        (430, 576, "EMPTY"),
    ):
        doc.drawString(x, y, texto)
    doc.save()
    return buffer.getvalue()


def test_las_boquillas_de_columna_toman_cota_base_y_angulo_de_planta():
    import pdfplumber

    from trazia.lectura.tablas import _segmentos_linea, _texto_caja

    cota = {
        "path": "nozzles.N1.elevation",
        "value": 1500.0,
        "unit": "mm",
        "source": {"document_id": DOC, "page": 1, "locator": "EL.+1500", "confidence": 0.85},
    }
    with pdfplumber.open(io.BytesIO(_planta())) as pdf:
        page = pdf.pages[0]
        palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
        lineas = [_texto_caja(g) for g in _segmentos_linea(palabras)]
        datos = columna.posiciones(page, palabras, lineas, DOC, {"N1": "N1", "N2": "N2"}, [cota])
    campos = {c.path: c for c in datos}
    assert campos["nozzles.N1.elevation"].source.rule == "vertical.elevacion_tangente"
    assert campos["nozzles.N1.projection_basis"].value == "axis"
    assert "nozzles.N2.projection_basis" not in campos  # sin cota EL. propia
    # 0° arriba y sentido horario; el ángulo medido queda supuesto para la revisión.
    assert campos["nozzles.N1.azimuth"].value == 0
    assert campos["nozzles.N2.azimuth"].value == 135
    assert campos["nozzles.N2.azimuth"].state == "assumed"


def test_la_cota_del_centro_de_gravedad_se_lee_con_su_condicion():
    from trazia.lectura import cdg

    (dato,) = cdg.leer(_planta(), DOC)
    assert (dato["path"], dato["value"]) == ("attributes.cog_elevation", 4500)
    assert dato["source"]["rule"] == "ga.cdg_elevacion"

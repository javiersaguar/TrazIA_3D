"""Alzado sintético de columna tumbada: dos diámetros con cono, faldón y cotas en cadena.

Todo es inventado (columna C-2, 1 pt = 25 mm): no hay datos de TR. La tangente superior está a
la izquierda y el faldón a la derecha, como en los GA que dibujan la columna en horizontal.
"""

import io

import pytest
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

from trazia.extraction import Candidate, assemble
from trazia.ingest import ingest_bytes
from trazia.lectura import columna_alzado

DOC = "GA-C2"


def _girado(doc, x, y, texto):
    doc.saveState()
    doc.translate(x, y)
    doc.rotate(90)
    doc.drawString(0, 0, texto)
    doc.restoreState()


def _cota(doc, x0, x1, y, texto):
    doc.setLineWidth(0.25)
    doc.line(x0, y, x1, y)
    doc.drawString((x0 + x1) / 2 - 10, y + 3, texto)


def _alzado(*, con_cota_del_tramo=True):
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=landscape(A3))
    doc.setFont("Helvetica", 8)
    # Silueta: Ø1500 de x=100 a 640, cono hasta 660 y Ø2000 hasta la tangente (x=900).
    doc.setLineWidth(1)
    for y in (530, 470):
        doc.line(100, y, 640, y)
    for y in (540, 460):
        doc.line(660, y, 1020, y)
    doc.setLineWidth(0.25)
    doc.line(640, 530, 660, 540)
    doc.line(640, 470, 660, 460)
    _cota(doc, 100, 900, 780, "20000")
    doc.drawString(460, 768, "T.T.L. TO B.T.L.")
    _cota(doc, 900, 1020, 760, "3000")
    if con_cota_del_tramo:
        _cota(doc, 660, 900, 740, "6000")
    doc.drawString(644, 723, "500")
    _girado(doc, 300, 480, "I.D. Ø1500")
    _girado(doc, 780, 470, "I.D. Ø2000")
    _girado(doc, 960, 470, "I.D. Ø1980")
    doc.drawString(950, 550, "12 THK.")
    doc.save()
    return buffer.getvalue()


def _campos(pdf):
    avisos = []
    datos = columna_alzado.leer(pdf, DOC, avisos)
    return {d["path"]: d for d in datos}, avisos


def test_los_tramos_salen_de_la_silueta_y_las_cotas_rotuladas():
    campos, avisos = _campos(_alzado())
    assert not avisos
    tramos = {
        ruta.removeprefix("column.sections."): dato["value"]
        for ruta, dato in campos.items()
        if ruta.startswith("column.sections.")
    }
    assert tramos == {
        "T1.order": 1,
        "T1.diameter": 2000,
        "T1.height": 6000,
        "T2.order": 2,
        "T2.diameter": 2000,
        "T2.top_diameter": 1500,
        "T2.height": 500,
        "T3.order": 3,
        "T3.diameter": 1500,
        "T3.height": 13500,
    }
    assert campos["height"]["value"] == 20000
    assert campos["column.sections.T1.height"]["source"]["text_original"] == "6000"
    assert campos["skirt_height"]["value"] == 3000
    assert campos["skirt_thickness"]["value"] == 12
    assert campos["attributes.skirt_diameter"]["value"] == 2004
    assert all("state" not in dato for dato in campos.values())
    assert all(d["source"]["document_id"] == DOC for d in campos.values())


def test_sin_cota_rotulada_el_tramo_medido_queda_supuesto():
    campos, _ = _campos(_alzado(con_cota_del_tramo=False))
    medido = campos["column.sections.T1.height"]
    assert medido["value"] == pytest.approx(6000, rel=0.01)
    assert medido["state"] == "assumed"
    assert medido["source"]["rule"] == "ga.columna_alzado_medida"


def test_la_columna_tumbada_se_ensambla_con_cono_y_faldon():
    pdf = _alzado()
    campos, _ = _campos(pdf)
    bundle = ingest_bytes(pdf, "drawing.pdf", DOC, "A")
    fuente = {"document_id": DOC, "page": 1, "locator": "C-2", "confidence": 0.9}
    datos = [
        *campos.values(),
        {"path": "tag", "value": "C-2", "unit": "1", "source": fuente},
        {"path": "attributes.equipment_type", "value": "column", "unit": "1", "source": fuente},
        {"path": "attributes.support", "value": "skirt", "unit": "1", "source": fuente},
    ]
    candidatos = [Candidate.model_validate(d) for d in datos]
    borrador = assemble([bundle], candidatos, project_id="DEMO", equipment_id="C2", revision="A")
    tramos = borrador.equipment.column.sections
    assert [(s.diameter.value, s.top_diameter and s.top_diameter.value) for s in tramos] == [
        (2000, None),
        (2000, 1500),
        (1500, None),
    ]
    assert sum(s.height.value for s in tramos) == pytest.approx(20000)
    assert borrador.equipment.skirt_height.value == 3000


def test_sin_cota_de_faldon_no_se_inventa_nada():
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=landscape(A3))
    doc.setFont("Helvetica", 8)
    _cota(doc, 100, 900, 780, "20000")
    doc.drawString(460, 768, "T.T.L. TO B.T.L.")
    _girado(doc, 300, 480, "I.D. Ø1500")
    doc.save()
    campos, avisos = _campos(buffer.getvalue())
    assert campos == {}
    assert any("faldón" in aviso for aviso in avisos)


def _globos_y_cotas():
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=landscape(A3))
    doc.setFont("Helvetica", 8)
    # Alzado tumbado: cada cota va al lado de su globo; N3 tiene dos cotas distintas.
    doc.drawString(100, 700, "N1")
    doc.drawString(120, 700, "+12000 TO T.L.")
    doc.drawString(400, 700, "- 1400 TO T.L.")
    doc.drawString(470, 700, "N2")
    doc.drawString(700, 700, "N3")
    doc.drawString(720, 700, "+5000 TO T.L.")
    doc.drawString(700, 650, "N3")
    doc.drawString(720, 650, "+5200 TO T.L.")
    # Sección: el ángulo vale para los globos en fila a su lado.
    doc.drawString(300, 400, "330º")
    doc.drawString(325, 400, "N1")
    doc.drawString(342, 400, "N2")
    doc.drawString(600, 400, "N3")
    doc.drawString(620, 400, "90º")
    doc.drawString(100, 200, "4.- EXCEPT OTHERWISE INDICATED, NOZZLE PROJECTIONS")
    doc.drawString(100, 190, "SHALL BE MEASURED FROM THE CENTERLINE OF THE")
    doc.save()
    return buffer.getvalue()


def test_cotas_a_tangente_y_angulos_junto_a_los_globos():
    import pdfplumber

    with pdfplumber.open(io.BytesIO(_globos_y_cotas())) as pdf:
        page = pdf.pages[0]
        palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
        datos = columna_alzado.posiciones(page, palabras, DOC, {m: m for m in ("N1", "N2", "N3")})
    leido = {c.path: c.value for c in datos}
    assert leido == {
        "nozzles.N1.elevation": 12000,
        "nozzles.N2.elevation": -1400,
        "nozzles.N1.azimuth": 330,
        "nozzles.N2.azimuth": 330,
        "nozzles.N3.azimuth": 90,
        "nozzles.N1.projection_basis": "axis",
        "nozzles.N2.projection_basis": "axis",
    }
    regla = {c.path: c.source.rule for c in datos}
    assert regla["nozzles.N1.elevation"] == "vertical.elevacion_tangente"
    assert regla["nozzles.N2.azimuth"] == "columna.azimut_rotulado"

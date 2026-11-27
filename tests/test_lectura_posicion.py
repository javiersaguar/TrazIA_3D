from pathlib import Path

import pdfplumber
import pytest
from reportlab.pdfgen import canvas

from trazia.extraction import Candidate
from trazia.lectura.posicion import alzado_con_tangente, horizontal, vertical
from trazia.lectura.tablas import _segmentos_linea, _texto_caja
from trazia.model import Source
from trazia.reconcile import resolve


def _globo(pdf, x, y, marca):
    pdf.circle(x, y, 12)
    pdf.drawCentredString(x, y - 4, marca)


def _girado(pdf, x, y, texto):
    pdf.saveState()
    pdf.translate(x, y)
    pdf.rotate(90)
    pdf.drawString(0, 0, texto)
    pdf.restoreState()


def _plano(path: Path, referencia: str):
    pdf = canvas.Canvas(str(path), pagesize=(700, 700))
    pdf.setFont("Helvetica", 11)
    for x, y, dato in (
        (180, 490, "0°"),
        (295, 380, "90°"),
        (180, 269, "180°"),
        (66, 380, "270°"),
    ):
        pdf.drawCentredString(x, y, dato)
    _globo(pdf, 180, 522, "N01")
    _globo(pdf, 204, 522, "N02")
    _globo(pdf, 180, 238, "N03")
    pdf.drawString(347, 654, "FRONT VIEW")
    _girado(pdf, 360, 503, referencia)
    _girado(pdf, 451, 522, "+1150")
    _globo(pdf, 446, 581, "N01")
    pdf.save()


def _leer(path, *, vesor):
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        palabras = page.extract_words()
        lineas = [_texto_caja(g) for g in _segmentos_linea(palabras)]
        return horizontal(page, palabras, lineas, "P", {"N01": "N1", "N02": "N2"}, vesor=vesor)


def test_estacion_y_azimut_citan_el_globo_y_respetan_registro(tmp_path):
    path = tmp_path / "plano.pdf"
    _plano(path, "0.0 (Ref.)")
    datos = {c.path: c for c in _leer(path, vesor=False)}
    assert {p: c.value for p, c in datos.items()} == {
        "nozzles.N1.azimuth": 0.0,
        "nozzles.N2.azimuth": 0.0,
        "nozzles.N1.station": 1150.0,
    }
    assert all(c.source.page == 1 and c.source.bbox for c in datos.values())
    vesor = _leer(path, vesor=True)
    assert len(vesor) == 2
    assert all(c.channel == "vesor" and c.path.endswith(".azimuth") for c in vesor)


def test_sin_cero_de_tangente_no_se_emite_la_estacion(tmp_path):
    path = tmp_path / "plano.pdf"
    _plano(path, "1.0 (Ref.)")
    assert all(c.path.endswith(".azimuth") for c in _leer(path, vesor=False))


@pytest.mark.parametrize("datum", ["T.L. EL. + 0.000", "W.P. AT T.L."])
def test_alzado_usa_tangente_cero_y_el_eje_de_la_seccion(tmp_path, datum):
    ruta = tmp_path / "alzado.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(1100, 680))
    pdf.setFont("Helvetica", 10)
    _girado(pdf, 100, 430, datum)
    _girado(pdf, 460, 466, "EL. + 6000")
    _girado(pdf, 213, 400, "EL. + 2000")
    pdf.drawCentredString(280, 605, "6000 T.L. TO T.L.")
    pdf.drawCentredString(280, 120, "ELEVATION")
    for x, y, texto in (
        (760, 500, "0°"),
        (915, 345, "90°"),
        (760, 190, "180°"),
        (605, 345, "270°"),
        (760, 132, "VIEW 'D-D'"),
    ):
        pdf.drawCentredString(x, y, texto)
    for x, y in ((220, 471), (760, 218)):
        globo = pdf.beginPath()
        globo.moveTo(x - 10, y)
        for dx, dy in ((-5, 9), (5, 9), (10, 0), (5, -9), (-5, -9), (-10, 0)):
            globo.lineTo(x + dx, y + dy)
        pdf.drawPath(globo)
        pdf.drawCentredString(x, y - 3, "J2")
    pdf.save()

    with pdfplumber.open(ruta) as original:
        page = original.pages[0]
        palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
        lineas = list(map(_texto_caja, _segmentos_linea(palabras)))
        datos = alzado_con_tangente(
            page, palabras, lineas, "P", {"J2": "J2"}, ruta.read_bytes(), []
        )
    if datum == "W.P. AT T.L.":
        assert datos == []
    else:
        assert {c.path: c.value for c in datos} == {
            "nozzles.J2.station": 2000,
            "nozzles.J2.azimuth": 180,
        }
        assert all(c.source.bbox and c.source.page == 1 for c in datos)


@pytest.mark.parametrize("con_norte", [False, True])
def test_planta_vertical_sin_flecha_norte_supone_la_escala_del_plano(tmp_path, con_norte):
    path = tmp_path / "planta.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(700, 700))
    pdf.setFont("Helvetica", 11)
    for x, y, texto in (
        (180, 490, "0°"),
        (295, 380, "90°"),
        (180, 269, "180°"),
        (66, 380, "270°"),
        (180, 230, "TOP VIEW"),
        (326, 380, "N1"),
    ):
        pdf.drawCentredString(x, y, texto)
    puntos = [(316, 384), (321, 393), (331, 393), (336, 384), (331, 375), (321, 375)]
    for a, b in zip(puntos, puntos[1:] + puntos[:1], strict=True):
        pdf.line(*a, *b)
    if con_norte:
        pdf.drawCentredString(351, 520, "N")
        pdf.line(351, 508, 351, 452)
        pdf.line(351, 508, 348, 493)
        pdf.line(351, 508, 354, 493)
    pdf.save()
    with pdfplumber.open(path) as original:
        page = original.pages[0]
        palabras = page.extract_words()
        lineas = [_texto_caja(g) for g in _segmentos_linea(palabras)]
        rotulos = [{"path": "nozzles.N1.elevation", "value": 500}]
        proyecciones = [{"path": "nozzles.N1.projection"}]
        datos = vertical(page, palabras, lineas, "P", {"N1": "N1"}, rotulos, proyecciones)
    assert datos[0].path == "nozzles.N1.bearing" and datos[0].value == 90.0
    azimuts = [c for c in datos if c.path.endswith(".azimuth")]
    assert [c.value for c in azimuts] == [0.0]
    if con_norte:
        assert azimuts[0].source.rule == "vertical.azimut_desde_norte"
        assert azimuts[0].state is None
    else:
        assert azimuts[0].source.rule == "vertical.azimut_escala_plano"
        assert azimuts[0].state == "assumed" and "no dibuja el Norte" in azimuts[0].explanation


def test_proyeccion_del_ga_conserva_el_valor_discrepante_de_la_hdm():
    path = "nozzles.N1.projection"
    ga = Candidate(
        path=path,
        value=610.0,
        unit="mm",
        source=Source(document_id="GA", page=1, locator="610", confidence=0.8),
        channel="tabla",
    )
    hdm = Candidate(
        path=path,
        value=410.0,
        unit="mm",
        source=Source(document_id="HDM", page=1, locator="410", confidence=0.95),
        channel="hoja_datos",
    )
    [preferida] = resolve([hdm, ga]).chosen
    assert preferida.value == 610.0 and preferida.state == "conflict"
    assert preferida.source.document_id == "GA"
    [alternativa] = preferida.alternatives
    assert alternativa.value == 410.0 and alternativa.source.document_id == "HDM"

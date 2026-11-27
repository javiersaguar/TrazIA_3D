"""Planos de otros fabricantes: unidades imperiales, cajetines y escaneos sin texto."""

import io

import pdfplumber
import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from trazia.lectura import planos_externos
from trazia.ocr import capa_texto
from trazia.ocr.engine import OcrLine


def _pdf(lineas, tamano=(800, 500)):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=tamano)
    pdf.setFont("Helvetica", 9)
    for x, y, texto in lineas:
        pdf.drawString(x, y, texto)
    pdf.save()
    return buffer.getvalue()


def _por_ruta(datos):
    return {d["path"]: d["value"] for d in datos}


def test_titulo_en_pulgadas_tabla_de_marcas_de_una_letra_y_item_no():
    datos = planos_externos.leer(
        _pdf(
            [
                (500, 60, "HORIZONTAL SEPARATOR"),
                (500, 45, '36" OD x 120" S/S'),
                (40, 460, "VESSEL NAME: Hot Separator ITEM NO.: D-506"),
                (40, 300, "MK. NO. SIZE RTG. FCG. SERVICE"),
                (40, 285, 'W 1 6" 600# RF Vapor Outlet'),
                (40, 270, 'L1/L2 2 2" 600# RF Level Bridle'),
            ]
        ),
        "DOC-1",
        None,
    )
    campos = _por_ruta(datos)
    assert campos["attributes.equipment_type"] == "horizontal_vessel"
    assert campos["horizontal.diameter"] == pytest.approx(914.4)
    assert campos["horizontal.length"] == pytest.approx(3048.0)
    assert campos["attributes.diameter_basis"] == "outside"
    assert campos["tag"] == "D-506"
    assert campos["nozzles.W.size_nps"] == 6
    assert campos["nozzles.W.rating"] == "600#"
    assert campos["nozzles.W.service"] == "Vapor Outlet"
    assert campos["nozzles.L1.size_nps"] == campos["nozzles.L2.size_nps"] == 2
    citas = [d["source"] for d in datos if d["path"] == "horizontal.diameter"]
    assert citas[0]["rule"] == "texto.imperial_diametro_por_longitud"
    assert 0 <= citas[0]["bbox"][0] < citas[0]["bbox"][2] <= 1


@pytest.mark.parametrize(
    ("lineas", "esperado"),
    [
        (["-5'-6\"ID-", "24'-0\" T/T"], {"diameter": 1676.4, "height": 7315.2}),
        # Lo que devuelve el OCR: comilla leída como «°» e I como 1.
        (["4 -5'-6°1D-", "24'-0°T/T"], {"diameter": 1676.4, "height": 7315.2}),
        (["OD 4'-11 29/64\" [1510]", "(D=1510-H=2438)"], {"diameter": 1510, "height": 2438}),
    ],
)
def test_cotas_en_pies_y_pulgadas(lineas, esperado):
    datos = planos_externos.leer(
        _pdf([(60, 400 - 20 * i, t) for i, t in enumerate(lineas)]), "DOC-1", None
    )
    campos = _por_ruta(datos)
    for ruta, valor in esperado.items():
        assert campos[ruta] == pytest.approx(valor)


def test_valores_distintos_de_la_misma_cota_no_se_proponen():
    datos = planos_externos.leer(
        _pdf([(60, 400, "-5'-6\" ID"), (60, 380, "-6'-0\" ID")]), "DOC-1", None
    )
    assert "diameter" not in _por_ruta(datos)


def test_cajas_de_lecturas_giradas_vuelven_a_la_pagina():
    caja = (0.1, 0.2, 0.3, 0.25)
    # Girar la imagen 90° antihorario y volver: misma caja.
    girada = (caja[1], 1 - caja[2], caja[3], 1 - caja[0])
    assert capa_texto._girar([OcrLine("x", girada, 1)], 90)[0].bbox == pytest.approx(caja)
    girada = (1 - caja[3], caja[0], 1 - caja[1], caja[2])
    assert capa_texto._girar([OcrLine("x", girada, 1)], 270)[0].bbox == pytest.approx(caja)


def test_cada_rotulo_vertical_conserva_su_mejor_sentido_de_lectura():
    vertical = (0.5, 0.2, 0.52, 0.4)
    sube = [OcrLine("24'-0\" T/T", vertical, 0.95)]
    baja = [OcrLine("T/T \"0-'42", vertical, 0.6)]
    rectas = [OcrLine("2", (0.5, 0.25, 0.52, 0.27), 0.5), OcrLine("ITEM", (0.1, 0.1, 0.2, 0.12), 1)]
    horizontales, verticales = capa_texto._combinar(rectas, sube, baja, 1.0)
    assert [(linea.text, sentido) for linea, sentido in verticales] == [("24'-0\" T/T", 270)]
    assert [linea.text for linea in horizontales] == ["ITEM"]


def _escaneo(tmp_path):
    """PDF con solo una imagen de la página, girada 90° con /Rotate como un escáner."""
    imagen = Image.new("L", (1700, 1100), 255)
    dibujo = ImageDraw.Draw(imagen)
    try:
        fuente = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        fuente = ImageFont.load_default(size=34)
    dibujo.text((120, 120), "HORIZONTAL SEPARATOR", fill=0, font=fuente)
    dibujo.text((120, 200), '36" OD x 120" S/S', fill=0, font=fuente)
    for i in range(4):
        dibujo.line((100, 400 + 60 * i, 1500, 400 + 60 * i), fill=0, width=3)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 396))
    pdf.drawImage(ImageReader(imagen), 0, 0, 612, 396)
    pdf.save()
    return buffer.getvalue()


def test_escaneo_sin_texto_recibe_capa_ocr_y_rayado(tmp_path, monkeypatch):
    pytest.importorskip("rapidocr")
    pytest.importorskip("cv2")
    monkeypatch.setenv("TRAZIA_OCR_CACHE", str(tmp_path / "ocr"))
    data = _escaneo(tmp_path)
    assert capa_texto.paginas_sin_texto(data) == [1]
    nuevo, leidas = capa_texto.pdf_legible(data, [1])
    assert leidas[0].horizontales >= 2 and leidas[0].reglas >= 4
    with pdfplumber.open(io.BytesIO(nuevo)) as pdf:
        texto = pdf.pages[0].extract_text()
        assert len([e for e in pdf.pages[0].edges if e["orientation"] == "h"]) >= 4
    assert "SEPARATOR" in texto.upper()
    campos = _por_ruta(planos_externos.leer(nuevo, "DOC-1", None))
    assert campos["horizontal.diameter"] == pytest.approx(914.4)

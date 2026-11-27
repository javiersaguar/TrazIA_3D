"""Tabla DESIGN DATA y pernos de anclaje de un GA sintético; cambios exactos de atributos.

Datos inventados (recipiente D-1): no hay nada de TR.
"""

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from trazia.lectura import cambios, datos_diseno


def _ga(filas):
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer, pagesize=A4)
    doc.drawString(60, 800, "DESIGN DATA")
    for y, (etiqueta, unidad, valor) in zip(range(780, 0, -16), filas, strict=False):
        doc.drawString(60, y, etiqueta)
        doc.drawString(330, y, unidad)
        doc.drawString(420, y, valor)
    doc.drawString(60, 200, "W/ Rf pad 4 x M24 Anchors")
    doc.save()
    return buffer.getvalue()


def test_la_tabla_de_diseno_da_valores_unicos_con_unidad():
    pdf = _ga(
        [
            ("MAWP", "Kgf/cm²", "8.96 LIMITED BY: NOZZLE REINFORCEMENT"),
            ("DESIGN PRESSURE", "Kgf/cm²", "8 / FV"),
            ("OPERATION TEMPERATURE", "ºC", "35"),
            ("OPERATION PRESSURE", "Kgf/cm² (BAR)", "3.9 (3.8)"),
            ("HYDROSTATIC TEST PRESSURE SHOP/FIELD", "Kgf/cm²", "11.44 / 11.44"),
            ("CORROSION ALLOWANCE", "mm", "3.2 (VESSEL)"),
        ]
    )
    campos = {c["path"]: c for c in datos_diseno.leer(pdf, "GA-D1")}
    assert (campos["attributes.mawp"]["value"], campos["attributes.mawp"]["unit"]) == (
        8.96,
        "kgf/cm2",
    )
    assert campos["attributes.operating_temperature"]["value"] == 35
    assert campos["attributes.operating_pressure"]["value"] == 3.9
    assert campos["attributes.hydrotest_pressure"]["value"] == 11.44
    assert campos["attributes.corrosion_allowance"]["value"] == 3.2
    assert "attributes.design_pressure" not in campos
    assert campos["attributes.anchor_bolts"]["value"] == "4 x M24"
    assert campos["attributes.mawp"]["source"]["rule"] == "ga.datos_diseno"


def test_dos_valores_distintos_no_son_un_valor():
    pdf = _ga([("HYDROSTATIC TEST PRESSURE SHOP/FIELD", "Kgf/cm²", "11.44 / 12.1")])
    assert "attributes.hydrotest_pressure" not in {
        c["path"] for c in datos_diseno.leer(pdf, "GA-D1")
    }


def test_un_atributo_en_mm_cambia_aunque_sea_menos_de_un_milimetro():
    base = {"path": "attributes.corrosion_allowance", "unit": "mm"}
    assert not cambios.iguales({**base, "value": 3.0}, {**base, "value": 3.2})
    # Una cota de geometría sigue con la tolerancia de medida.
    cota = {"path": "nozzles.N1.elevation", "unit": "mm"}
    assert cambios.iguales({**cota, "value": 1200.0}, {**cota, "value": 1200.6})

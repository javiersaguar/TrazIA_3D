import json

import pytest
from reportlab.pdfgen import canvas

from scripts.lectura_ga import leer_pdf
from trazia.lote import procesar_carpeta
from trazia.model import Source


@pytest.mark.parametrize(
    ("texto", "tipo", "soporte"),
    [
        (("VESSEL", 'DETAIL "LEGS"', "EL.+ 300"), "vertical_vessel", "legs"),
        (("HORIZONTAL VESSEL", "FIXED SADDLE", "Weld leg (z)"), "horizontal_vessel", "saddles"),
        (("AMINE ABSORBER", "SKIRT O.D."), "column", "skirt"),
        (("GENERAL VIEW TANK", "TOP EDGE OF TANK FOUNDATION"), "tank", "none"),
        (("VESSEL", "Weld leg (z)", "SUPPORTS (Saddles, skirt, legs)"), None, None),
    ],
)
def test_ga_clasificacion_citada(tmp_path, texto, tipo, soporte):
    ruta = tmp_path / "GAD_EJ-01_rev2.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 600))
    for i, linea in enumerate(texto):
        pdf.drawString(23, 560 - 25 * i, linea)
    pdf.save()

    lectura = leer_pdf(ruta)
    assert lectura["equipment_tag"] == "EJ-01"
    assert lectura["revision"] == "rev2"
    campos = {c["path"]: c for c in lectura["candidates"]}
    for nombre, valor in (("equipment_type", tipo), ("support", soporte)):
        ruta_campo = f"attributes.{nombre}"
        if valor is None:
            assert ruta_campo not in campos
            continue
        candidato = campos[ruta_campo]
        assert candidato["value"] == valor
        cita = Source.model_validate(candidato["source"])
        assert cita.page == 1
        assert cita.locator in texto and cita.bbox
        if cita.rule == "ga.tipologia.patas_alzado":
            assert cita.inferred_region and cita.inferred_region.page == 1
            assert "EL.+ 300" in candidato["explanation"]


def test_ga_lee_pesos_individuales_y_combinados_con_cita(tmp_path):
    ruta = tmp_path / "GAD_EJ-02_rev1.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 500))
    pdf.drawString(34, 400, "WEIGHT EMPTY / OPERATION / FULL")
    pdf.drawString(330, 400, "Kg 100 / 150 / 200")
    pdf.drawString(34, 350, "FIELD HYDROTEST WEIGHT (Kg)")
    pdf.drawString(330, 350, "240")
    pdf.save()
    campos = {c["path"]: c for c in leer_pdf(ruta)["candidates"]}
    for key, valor in (("empty", 100), ("operating", 150), ("full", 200), ("test", 240)):
        candidato = campos["attributes.weight_" + key]
        assert (candidato["value"], candidato["unit"]) == (valor, "kg")
        assert str(valor) in candidato["source"]["locator"]


def test_lote_exporta_tipologia_aunque_no_haya_geometria(tmp_path):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    salida = tmp_path / "salida"
    plano = entrada / "GAD_EJ-01_revA.pdf"
    pdf = canvas.Canvas(str(plano))
    pdf.drawString(50, 600, "HORIZONTAL VESSEL")
    pdf.drawString(50, 560, "FIXED SADDLE")
    pdf.save()

    [fila] = procesar_carpeta(entrada, salida, dataset="synthetic", trabajo=tmp_path / "trabajo")
    assert fila.estado == "faltan_datos"
    archivo = salida / "EJ-01" / "revA" / "candidatos.json"
    campos = {c["path"]: c for c in json.loads(archivo.read_text(encoding="utf-8"))}
    assert campos["attributes.equipment_type"]["value"] == "horizontal_vessel"
    assert campos["attributes.support"]["value"] == "saddles"
    assert campos["attributes.support"]["source"]["document_id"] == "GA-EJ-01"


def _plano(ruta, lineas):
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 600))
    for i, linea in enumerate(lineas):
        pdf.drawString(23, 560 - 25 * i, linea)
    pdf.save()
    return {c["path"]: c for c in leer_pdf(ruta)["candidates"]}


def test_tanque_sin_cita_de_apoyo_queda_en_cimentacion(tmp_path):
    campos = _plano(tmp_path / "GAD_EJ-T-01_rev1.pdf", ["FLOATING ROOF", "BOTTOM SUMP"])
    soporte = campos["attributes.support"]
    assert soporte["value"] == "none"
    assert soporte["source"]["rule"] == "ga.tipologia.tanque_en_cimentacion"
    assert soporte["source"]["locator"] == "FLOATING ROOF"
    assert soporte["source"]["confidence"] < 0.8


@pytest.mark.parametrize(("tag", "tipo"), [("EJ-C-01", "column"), ("EJ-V-01", None)])
def test_faldon_y_letra_c_del_tag_dan_columna(tmp_path, tag, tipo):
    campos = _plano(tmp_path / f"GAD_{tag}_rev2.pdf", ["SKIRT NOZZLES AND BASE RING"])
    assert campos["attributes.support"]["value"] == "skirt"
    if tipo is None:
        assert "attributes.equipment_type" not in campos
        return
    candidato = campos["attributes.equipment_type"]
    assert candidato["value"] == tipo
    assert candidato["source"]["rule"] == "ga.tipologia.faldon_y_tag"
    assert tag in candidato["explanation"]


def test_masas_con_errata_tabla_sin_unidad_y_en_castellano(tmp_path):
    campos = _plano(
        tmp_path / "GAD_EJ-03_rev1.pdf",
        [
            "Fabrication Weigth (kg): 5800",
            "WEIGHT TABLE (Kgs.)",
            "OPERATING WEIGHT 367600 EMPTY WEIGHT + FULL OF LIQUID",
            "TRANSPORTATION WEIGHT 88500",
            "PESO PRUEBA HIDRÁULICA TALLER 615770 kg",
        ],
    )
    esperado = {"fabrication": 5800, "operating": 367600, "transport": 88500, "test": 615770}
    for clase, valor in esperado.items():
        candidato = campos[f"attributes.weight_{clase}"]
        assert (candidato["value"], candidato["unit"]) == (valor, "kg")
        assert str(valor) in candidato["source"]["locator"]
    assert "HIDRÁULICA" in campos["attributes.weight_test"]["source"]["locator"]


def test_masa_sin_unidad_no_se_lee_sin_tabla_en_kg(tmp_path):
    campos = _plano(tmp_path / "GAD_EJ-04_rev1.pdf", ["OPERATING WEIGHT 367600"])
    assert "attributes.weight_operating" not in campos

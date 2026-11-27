import pytest
from reportlab.pdfgen import canvas

from scripts.lectura_ga import _valor_nps, leer_pdf


def _tabla(pdf, x, y, filas):
    lado, alto = 77, 18
    ancho = len(filas[0]) * lado
    for i, fila in enumerate(filas):
        pdf.line(x, y - i * alto, x + ancho, y - i * alto)
        for j, texto in enumerate(fila):
            lineas = texto.splitlines()
            base = y - i * alto - (7 if len(lineas) > 1 else 13)
            for k, linea in enumerate(lineas):
                pdf.drawString(x + j * lado + 4, base - 8 * k, linea)
    pdf.line(x, y - len(filas) * alto, x + ancho, y - len(filas) * alto)
    for j in range(len(filas[0]) + 1):
        pdf.line(x + j * lado, y, x + j * lado, y - len(filas) * alto)


@pytest.mark.parametrize(("marca", "cantidad"), [("ITEM", "QUANT."), ("Pos.", "Qty.")])
def test_ga_separa_tabla_de_boquillas_materiales_y_notas(tmp_path, marca, cantidad):
    ruta = tmp_path / "GA_DEMO.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(1160, 820))
    pdf.setFont("Helvetica", 8)
    _tabla(
        pdf,
        26,
        690,
        [
            (marca, cantidad, "SIZE", "RATING", "FACE", "SERVICE"),
            ("N01", "1", '2"', "300#", "RF", "Drain"),
            ("L1-2", "2", '1-1/2"', "150#", "FF", "Level"),
            ("S01", "1", "D. 300", "--", "-", "Skirt access"),
            ("TOEBEHOREN - ACCESSORIES", "", "", "", "", ""),
            ("X01", "2", "2", "", "", "Saddles"),
        ],
    )
    _tabla(
        pdf,
        635,
        690,
        [
            ("MARK", "QTY", "DESCRIPTION", "MATERIAL", "CODE"),
            ("V01", "1", "THK. 12 x 8 x 24", "SA-X", "00012345"),
        ],
    )
    pdf.drawString(50, 480, "N1. NOTA GENERAL")
    pdf.drawString(50, 450, "4 x M30")
    pdf.drawString(50, 410, "N01")
    pdf.save()

    salida = leer_pdf(ruta)
    assert set(salida["identifiers"]) == {"N1", "L1", "L2", "V01"}
    assert salida["identifiers"]["V01"]["kind"] == "bom_item"
    assert salida["identifiers"]["V01"]["code"] == "00012345"
    assert {i["role"] for i in salida["identifiers"]["N1"]["appearances"]} == {"ga_table", "label"}
    assert "M30" in {a["text"] for a in salida["identifiers_discarded"]}
    campos = {c["path"]: c for c in salida["candidates"]}
    assert campos["nozzles.N1.rating"]["value"] == "300#"
    assert campos["nozzles.L2.size_nps"]["value"] == 1.5
    # Diámetro exterior de la serie ASME B36.10 para el NPS de la tabla.
    assert campos["nozzles.N1.diameter"]["value"] == 60.3
    assert campos["nozzles.L2.diameter"]["value"] == 48.3
    assert campos["nozzles.N1.diameter"]["unit"] == "mm"
    assert campos["shell.courses.V01.thickness"]["value"] == 12
    assert campos["nozzles.N1.rating"]["source"]["page"] == 1
    assert all(0 <= v <= 1 for v in campos["nozzles.N1.rating"]["source"]["bbox"])
    inventario = salida["nozzle_schedule"]
    assert inventario["complete"]
    assert set(inventario["rows"]) == {"N1", "L1", "L2"}
    assert "N01" in inventario["rows"]["N1"]["source"]["locator"]
    assert inventario["rows"]["N1"]["fields"]["rating"]["value"] == "300#"


def test_nozzle_schedule_con_cabecera_agrupada_y_tablas_contiguas(tmp_path):
    ruta = tmp_path / "plano.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(1130, 620))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(420, 470, "K99")
    pdf.showPage()
    pdf.setFont("Helvetica", 8)
    x0, y0 = 215, 535
    paso, alto = 79, 32
    datos = [
        ("K01A/B", "3", "Nivel", "2", "REFER SKETCH/\n450", "80/100", "150#", "LWNRF"),
        ("J 2/3", "6", "Ventilación", "2", "460", "-", "150#", "WNRF"),
    ]
    x1, pie = x0 + len(datos[0]) * paso, y0 - (len(datos) + 1) * alto
    for y in (y0 + 26, y0, y0 - alto, y0 - 2 * alto, pie):
        pdf.line(x0, y, x1, y)
    for i in range(len(datos[0]) + 1):
        x = x0 + i * paso
        techo = y0 + 26 if i in (0, len(datos[0])) else y0 - 16 if i == 7 else y0
        pdf.line(x, techo, x, pie)
    pdf.line(x0 + 5 * paso, y0 - 16, x1, y0 - 16)
    pdf.drawCentredString((x0 + x1) / 2, y0 + 10, "NOZZLE SCHEDULE")
    for i, t in enumerate(
        ("NOZZLE", "SIZE INCH", "SERVICE", "QTY", "PROJECTION", "NECK", "FLANGE DETAIL")
    ):
        pdf.drawString(x0 + i * paso + 6, y0 - 10, t)
    for i, t in ((0, "MARK"), (5, "SCH."), (6, "RATING"), (7, "TYPE & FACE")):
        pdf.drawString(x0 + i * paso + 6, y0 - 25, t)
    for fila, valores in enumerate(datos, 1):
        for i, valor in enumerate(valores):
            for renglon, t in enumerate(valor.splitlines()):
                pdf.drawString(x0 + i * paso + 6, y0 - fila * alto - 13 - renglon * 8, t)
    _tabla(pdf, 18, y0 + 26, [("DESIGN DATA", "UNIT"), ("K98", "125")])
    _tabla(pdf, x1 + 8, y0 + 26, [("WEIGHT TABLE", "VALUE"), ("K97", "280")])
    pdf.save()

    resultado = leer_pdf(ruta)
    tabla = resultado["nozzle_schedule"]
    assert tabla["complete"]
    assert set(resultado["identifiers"]) == set(tabla["rows"]) == {"K1A", "K1B", "J2", "J3"}
    for marca, fila in tabla["rows"].items():
        assert fila["source"]["page"] == 2 and fila["source"]["bbox"]
        campos = fila["fields"]
        assert campos["mark"]["value"] == ("K01A/B" if marca.startswith("K") else "J 2/3")
        for campo in campos.values():
            assert campo["source"]["page"] == 2 and campo["source"]["bbox"]
    campos = tabla["rows"]["K1A"]["fields"]
    assert campos["schedule"]["value"] == "80/100"
    assert campos["facing"]["value"] == "LWNRF"
    assert campos["projection_reference"]["value"] == "REFER SKETCH/450"
    assert "projection" not in campos


@pytest.mark.parametrize(
    ("texto", "nps"),
    [('12" [DN 300]', 12), ('1-1/2" [DN 40]', 1.5), ('8" (HOLD)', 8), ("[DN 300]", None)],
)
def test_tamano_nps_con_leyenda_dn(texto, nps):
    assert _valor_nps(texto) == nps


@pytest.mark.parametrize(
    ("cabecera", "nota", "base"),
    [
        ("PROJECTION", ["N4. Projections from the flange face to the central axis."], "axis"),
        ("PROYEC. (1)", ["1.- Desde la virola hasta la cara de la brida."], "shell"),
        (
            "PROYEC. (1)",
            ["(1) From the vessel axis", "or from the nearest tangent line."],
            "desconocida",
        ),
        ("STANDOUT", [], "desconocida"),
    ],
)
def test_ga_proyeccion_con_nota_y_aviso(tmp_path, cabecera, nota, base):
    ruta = tmp_path / "GA_DEMO.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 500))
    pdf.setFont("Helvetica", 8)
    _tabla(
        pdf,
        26,
        410,
        [
            ("ITEM", "SIZE", "RATING", "TIPO\nTYPE", cabecera),
            ("D1", '12" [DN 300]', "300#", "WN", "410"),
            ("D2", '2"', "300#", "SW", "SEE DRAWING"),
        ],
    )
    for i, linea in enumerate(nota):
        pdf.drawString(28, 240 - 10 * i, linea)
    pdf.save()

    salida = leer_pdf(ruta)
    campos = {c["path"]: c for c in salida["candidates"]}
    assert campos["nozzles.D1.size_nps"]["value"] == 12
    assert campos["nozzles.D1.flange_type"]["value"] == "WN"
    assert campos["nozzles.D1.projection"]["value"] == 410
    assert campos["nozzles.D1.projection"]["source"]["locator"] == "410"
    referencia = campos["nozzles.D1.projection_basis"]
    assert referencia["value"] == base
    if nota:
        assert referencia["source"]["locator"] == " ".join(nota)
    assert bool(salida["warnings"]) == (base == "desconocida")
    assert "nozzles.D2.projection" not in campos


@pytest.mark.parametrize("pieza", ["V01", "V1"])
def test_ga_registro_pieza_y_boquilla_con_cabecera_bilingue(tmp_path, pieza):
    ruta = tmp_path / "GA_DEMO.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(1160, 820))
    pdf.setFont("Helvetica", 8)
    _tabla(pdf, 26, 690, [("ITEM", "SIZE", "RATING"), ("V1", '6"', "150#")])
    _tabla(
        pdf,
        635,
        690,
        [
            ("Pos.\nItem", "Cant.\nQty.", "Designación", "Calidad material", "Código ID."),
            (pieza, "1", "ESP. 16 x 23 x 45\nTHK. 16 x 23 x 45", "SA-X", "00012345"),
        ],
    )
    pdf.drawString(50, 410, pieza)
    pdf.save()

    salida = leer_pdf(ruta)
    boquilla = salida["identifiers"]["V1"]
    elemento = salida["identifiers"][pieza if pieza != "V1" else "bom_item__V1"]
    assert boquilla["kind"] == "nozzle"
    assert all(a["role"] == "ga_table" for a in boquilla["appearances"])
    assert elemento["kind"] == "bom_item"
    assert elemento["code"] == "00012345"
    if pieza == "V01":
        assert any(a["role"] == "label" for a in elemento["appearances"])
    else:
        assert elemento["id"] == "V1"
        assert any(
            a["text"] == "V1" and a["reason"] == "id ambiguo"
            for a in salida["identifiers_discarded"]
        )
    campos = {c["path"]: c["value"] for c in salida["candidates"]}
    assert (
        campos[f"shell.courses.{pieza}.thickness"],
        campos[f"shell.courses.{pieza}.height"],
        campos[f"shell.courses.{pieza}.development"],
    ) == (16, 23, 45)


def test_ga_asocia_rotulos_con_marcas_de_su_pagina_sin_inventar_el_marco(tmp_path):
    ruta = tmp_path / "GAD_EJ-03_rev1.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 500))
    pdf.setFont("Helvetica", 8)
    _tabla(
        pdf,
        26,
        400,
        [("ITEM", "SIZE", "RATING"), ("A1", '4"', "150#"), ("B2", '4"', "150#")],
    )
    pdf.drawString(80, 240, "A01")
    pdf.drawString(76, 225, "EL.+ 1200")
    pdf.drawString(76, 201, "EL.+ 1350")
    pdf.drawString(220, 190, "B2 AZIMUT 90°")
    pdf.drawString(220, 160, "M30 45°")
    pdf.showPage()
    pdf.drawString(76, 225, "EL.+ 800")
    pdf.save()

    salida = leer_pdf(ruta)
    rotulos = {
        r["path"]: (r["value"], r["association"], r["source"]["locator"])
        for r in salida["nozzle_labels"]
    }
    assert rotulos == {
        "nozzles.A1.elevation": (1200, "proximidad", "EL.+ 1200"),
        "nozzles.B2.azimuth": (90, "explicita", "B2 AZIMUT 90°"),
    }
    assert not set(rotulos) & {c["path"] for c in salida["candidates"]}


def test_un_rotulo_bajo_una_fila_de_globos_da_la_cota_a_toda_la_fila():
    from trazia.lectura.rotulos import asociar, leer_rotulos

    def globo(x, y):
        return {"page": 1, "role": "label", "bbox": (x, y, x + 10, y + 10)}

    ids = {
        marca: {"kind": "nozzle", "appearances": [globo(x, y)]}
        for marca, x, y in (
            ("N1", 100, 100),
            ("N2", 116, 100),
            ("N3", 132, 100),  # fila sobre «EL.+ 900»
            ("N4", 300, 100),  # globo suelto, lejos
        )
    }
    rotulos = leer_rotulos([("EL.+ 900", (100, 115, 140, 124))])
    asociados = {
        marca: (rotulo.valor, tipo)
        for rotulo, marca, tipo, _ in asociar(rotulos, ids, 1, lambda m: [m])
    }
    assert asociados == {n: (900.0, "fila") for n in ("N1", "N2", "N3")}
    # Un globo solo no forma fila: sigue la asociación por proximidad.
    solo = {"N4": ids["N4"]}
    rotulos = leer_rotulos([("EL.+ 500", (296, 115, 316, 124))])
    assert [(m, t) for _, m, t, _ in asociar(rotulos, solo, 1, lambda m: [m])] == [
        ("N4", "proximidad")
    ]

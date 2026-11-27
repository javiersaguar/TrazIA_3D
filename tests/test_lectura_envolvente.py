import pytest
from reportlab.pdfgen import canvas

from trazia.lectura.tablas import leer_pdf


@pytest.mark.parametrize("axial", (1750, 1765))
def test_virola_separa_el_desarrollo_axial_de_la_distancia_a_la_brida(tmp_path, axial):
    path = tmp_path / "GAD_EJ-07_rev1.pdf"
    doc = canvas.Canvas(str(path))
    for y, dato in (
        (750, "LATERAL VIEW"),
        (710, f"2 1 SHELL ØINT. 600mm; Des.= {axial}x1916mm THK. 10mm"),
        (680, "1 1 ELLIPSOIDAL HEAD 2:1 ØINT. 600mm; H= 190 mm"),
        (650, "DETAIL LEGS"),
        (620, "10 3 ANGLE PROFILE"),
        (600, "11 3 BASE PLATE"),
    ):
        doc.drawString(100, y, dato)
    doc.saveState()
    doc.translate(70, 410)
    doc.rotate(90)
    doc.drawString(0, 0, "2000 (TL TO F.F)")
    doc.restoreState()
    doc.save()
    campos = {c["path"]: c for c in leer_pdf(path)["candidates"]}
    # Como en el oro: `height` hasta la cara de la brida y el desarrollo de la chapa aparte.
    assert campos["height"]["value"] == 2000
    assert campos["height"]["source"]["rule"] == "ga.tl_a_cara"
    assert campos["attributes.shell_height"]["value"] == axial
    assert campos["attributes.height_to_flange"]["value"] == 2000
    assert campos["diameter"]["value"] == 600
    assert campos["head_depth"]["value"] == 190
    assert campos["legs.count"]["value"] == 3
    assert "legs.height" not in campos
    assert campos["height"]["source"]["bbox"] and campos["height"]["source"]["page"] == 1


def test_horizontal_separa_cota_impresa_y_fondo_asumido(tmp_path):
    path = tmp_path / "GAD_EJ-08_rev1.pdf"
    doc = canvas.Canvas(str(path))
    for y, dato in (
        (750, "HORIZONTAL VESSEL"),
        (710, "ID Ø1400 x 8mm"),
        (680, "Ellipsoidal head 2:1"),
        (610, "4200(T.L. To T.L.)"),
    ):
        doc.drawString(100, y, dato)
    doc.save()
    campos = {c["path"]: c for c in leer_pdf(path)["candidates"]}
    assert campos["horizontal.diameter"]["value"] == 1400
    assert campos["horizontal.length"]["value"] == 4200
    assert campos["horizontal.head_depth"]["value"] == 350
    assert campos["horizontal.head_depth"]["state"] == "assumed"
    assert "horizontal.saddle_width" not in campos
    assert "attributes.shell_thickness" not in campos


@pytest.mark.parametrize("espesor_central", (11, 13))
def test_espesor_horizontal_exige_tramos_consecutivos_y_uniformes(tmp_path, espesor_central):
    path = tmp_path / "GAD_EJ-08_rev1.pdf"
    doc = canvas.Canvas(str(path))
    for x, y, dato in (
        (100, 750, "HORIZONTAL VESSEL"),
        (100, 710, "ID Ø1400 x 8mm"),
        (70, 650, "50"),
        (70, 635, "S.F."),
        (140, 650, "1200 x 11 1.2"),
        (280, 650, f"1400 x {espesor_central} 1.3"),
        (420, 650, "1100 x 11 1.4"),
        (560, 650, "50"),
        (560, 635, "S.F."),
        (280, 618, "3800(T.L. To T.L.)"),
    ):
        doc.drawString(x, y, dato)
    doc.save()
    campos = {c["path"]: c for c in leer_pdf(path)["candidates"]}
    espesor = campos.get("attributes.shell_thickness")
    if espesor_central == 11:
        assert espesor["value"] == 11
        assert espesor["source"]["rule"] == "ga.espesor_tramos_virola"
        assert espesor["source"]["bbox"] and "1100 x 11 1.4" in espesor["source"]["locator"]
        # J6: cada tramo es una virola con su estación desde la T.L. izquierda (tras el S.F.).
        virolas = {
            ruta: c["value"] for ruta, c in campos.items() if ruta.startswith("shell.courses.")
        }
        assert virolas["shell.courses.1-2.station"] == 50
        assert virolas["shell.courses.1-3.station"] == 1250
        assert virolas["shell.courses.1-4.station"] == 2650
        assert virolas["shell.courses.1-4.height"] == 1100
        assert campos["shell.courses.1-3.station"]["source"]["rule"] == "ga.tramos_virola"
    else:
        assert espesor is None
        assert not any(ruta.startswith("shell.courses.") for ruta in campos)


@pytest.mark.parametrize(
    ("cota_anclajes", "ancho_fija", "ancho_movil", "ancho_comun"),
    ((125, 215, 215, 215), (125, 240, 215, None), (155, 215, None, None)),
)
def test_ancho_movil_depende_de_su_contorno_y_sus_anclajes(
    tmp_path, cota_anclajes, ancho_fija, ancho_movil, ancho_comun
):
    path = tmp_path / "GAD_EJ-08_rev1.pdf"
    doc = canvas.Canvas(str(path))
    for x, y, texto in (
        (100, 750, "HORIZONTAL VESSEL"),
        (100, 710, "ID Ø1400 x 8mm"),
        (240, 620, "4200(T.L. To T.L.)"),
        (265, 550, "Section C-C (1 : 20)"),
        (275, 535, "Foundation Plan"),
        (410, 524, str(ancho_fija)),
        (372, 487, "Fixed"),
        (120, 491, str(cota_anclajes)),
        (197, 325, "Sliding"),
        (197, 310, "Saddle"),
    ):
        doc.drawString(x, y, texto)
    doc.rect(145, 215, 30.48, 255)
    doc.circle(151.5, 458, 2.2)
    doc.circle(169.2, 458, 2.2)
    doc.line(175.48, 289, 192, 305)
    doc.save()

    campos = {c["path"]: c for c in leer_pdf(path)["candidates"]}
    assert campos["attributes.saddle_width_fixed"]["value"] == ancho_fija
    movil = campos.get("attributes.saddle_width_sliding", {})
    comun = campos.get("horizontal.saddle_width", {})
    assert movil.get("value") == ancho_movil
    assert comun.get("value") == ancho_comun
    if ancho_movil is not None:
        assert movil["state"] == "assumed" and movil["source"]["page"] == 1
        assert "Sliding Saddle" in movil["source"]["locator"]
        assert "cota entre sus anclajes" in movil["explanation"]

from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from scripts.lectura_hdm import expand_marks, read_hdm
from trazia.extractors.units import parse_nps
from trazia.lectura.hdm import read_candidates


def _line(pdf, y, text):
    pdf.drawString(36, y, text)


def _table_row(pdf, y, *values):
    for x, value in zip((36, 98, 155, 205, 315, 403, 467, 547), values, strict=True):
        pdf.drawString(x, y, value)


def test_hdm_tr_lee_tabla_y_especificaciones_con_citas(tmp_path: Path):
    path = tmp_path / "HDM_PRUEBA.pdf"
    pdf = Canvas(str(path), pagesize=(612, 792))
    pdf.setFont("Helvetica", 9)
    _line(pdf, 740, "DESIGN SPECIFICATION")
    _line(pdf, 720, "1 MAWP: 900 kPa")
    _line(pdf, 700, "2 Design Pressure: 3,5 kgf/cm²")
    _line(pdf, 680, "3 MDMT: -22 °C")
    _line(pdf, 660, "4 PWHT: Required")
    _line(pdf, 640, "5 Insulation Thickness: 21,5 mm")
    _line(pdf, 610, "MATERIAL SPECIFICATION")
    _line(pdf, 590, "1 Shell Material: SA-516 Gr 65")
    _line(pdf, 570, "2 Shell Thickness: 31,28, 25, 24,19")
    _line(pdf, 550, "3 Head Thickness: 11 mm")
    _line(pdf, 520, "WEIGHT & CAPACITY")
    _line(pdf, 500, "1 Transport Weight: 1730 kg")
    _line(pdf, 480, "2 Empty Weight: 1985 kg")
    _line(pdf, 460, "3 Operating Weight: 2505 kg")
    _line(pdf, 440, "4 Test Weight: 2905 kg")
    _line(pdf, 420, "5 Capacity: 2300 l")
    pdf.showPage()
    pdf.setFont("Helvetica", 9)
    _line(pdf, 740, "NOZZLES MECHANICAL INFORMATION")
    _table_row(
        pdf,
        716,
        "Mark",
        "Quantity",
        "Size",
        "Service",
        'Projection "L"',
        "Rating",
        "Type-Facing",
        "Schedule",
    )
    _table_row(pdf, 695, "M1-5", "5", '1 1/2"', "Drain", "53,6 mm", "300#", "WN-RF", "80")
    _table_row(pdf, 672, "N1/N3", "2", '2"', "Vent", "Refer Sketch", "150#", "WN-RF", "40")
    _table_row(pdf, 649, "N13 A/B", "2", '4"', "Overflow", "(HOLD)", "150#", "WN-RF", "40")
    _table_row(pdf, 635, "Q1-4", "2", '2"', "Drain", "-", "150#", "WN-RF", "40")
    _line(pdf, 620, "Projection measured from the centerline to the flange face")
    pdf.save()

    reading = read_hdm(path, document_id="HDM-sintetica")
    values = {item.path: item for item in reading.candidates}
    assert sorted(reading.appearances) == ["M1", "M2", "M3", "M4", "M5", "N1", "N13A", "N13B", "N3"]
    assert values["nozzles.M3.size_nps"].value == 1.5
    assert values["nozzles.M3.diameter"].value == 48.3
    assert values["nozzles.M3.projection"].value == 53.6
    assert values["nozzles.M3.projection_basis"].value == "axis"
    assert values["nozzles.N3.rating"].value == "150#"
    assert values["nozzles.N13A.service"].value == "Overflow"
    assert "nozzles.N1.projection" not in values
    assert "nozzles.N13A.projection" not in values
    assert {notice.path for notice in reading.notices} >= {
        "nozzles",
        "nozzles.N1.projection",
        "nozzles.N13A.projection",
    }
    assert values["attributes.mawp"].value == pytest.approx(9)
    assert values["attributes.design_pressure"].value == pytest.approx(3.4323275)
    assert values["attributes.mdmt"].value == -22
    assert values["attributes.pwht"].value == "Required"
    assert values["attributes.insulation_thickness"].value == 21.5
    assert values["attributes.material_shell"].value == "SA-516 Gr 65"
    assert values["attributes.shell_thicknesses"].value == "31,28, 25, 24,19"
    assert values["attributes.heads_thickness"].value == 11
    assert values["attributes.weight_transport"].value == 1730
    assert values["attributes.weight_empty"].value == 1985
    assert values["attributes.weight_operating"].value == 2505
    assert values["attributes.weight_test"].value == 2905
    assert values["attributes.capacity"].value == pytest.approx(2.3)
    for item in reading.candidates:
        x0, top, x1, bottom = item.source.bbox
        assert item.source.document_id == "HDM-sintetica"
        assert 0 <= x0 < x1 <= 612
        assert 0 <= top < bottom <= 792
        assert item.source.page in (1, 2)
        assert item.source.text
    assert values["nozzles.M3.projection_basis"].source.text.startswith("Projection measured")
    candidates, warnings = read_candidates(path.read_bytes(), "HDM-sintetica")
    candidate = next(item for item in candidates if item.path == "nozzles.M3.projection")
    assert candidate.source.document_id == "HDM-sintetica" and candidate.source.page == 2
    assert candidate.source.channel == "hoja_datos" and candidate.value == 53.6
    assert all(0 <= coordinate <= 1 for coordinate in candidate.source.bbox)
    assert any("nozzles.N1.projection" in warning for warning in warnings)


def test_hdm_api_650_lee_tanque_y_boquillas(tmp_path: Path):
    path = tmp_path / "HDM_TANQUE.pdf"
    pdf = Canvas(str(path), pagesize=(612, 792))
    pdf.setFont("Helvetica", 9)
    _line(pdf, 740, "Size Limitations")
    _line(pdf, 719, "4. Size Limitations * Tank Diameter * ID: 12.45 m Shell Height* 16.3 m")
    _line(pdf, 690, "5 Capacity: Maximum* 1841 (VTC) m3 Net Working* 1732 (note 6) m3")
    _line(pdf, 666, "Shell Course 1 Thickness: 13.6 mm")
    _line(pdf, 644, "Shell Course 2 Thickness: 12,5 mm")
    pdf.showPage()
    pdf.setFont("Helvetica", 9)
    _line(pdf, 760, "2 Fixed Roof Type* Yes, Supported Dome (Note 18)")
    _line(pdf, 740, "NOZZLE and MANHOLE SCHEDULE")
    _table_row(pdf, 715, "Mark", "Qty.", "NPS", "Service", "Projection", "Class", "Facing", "Sch.")
    _table_row(pdf, 695, "L1-8", "8", '3/4"', "Sampling", "35 mm", "300#", "RF", "XXS")
    _table_row(pdf, 674, "MW1", "1", '24"', "Access", "62 mm", "150#", "RF", "STD")
    pdf.save()

    reading = read_hdm(path)
    values = {item.path: item.value for item in reading.candidates}
    assert len(reading.appearances) == 9
    assert values["tank.diameter"] == 12450
    assert values["attributes.diameter_basis"] == "inside"
    assert values["tank.height"] == 16300
    assert values["tank.roof"] == "domed"
    assert values["attributes.capacity"] == 1841
    assert values["attributes.capacity_working"] == 1732
    assert values["tank.courses.1.thickness"] == 13.6
    assert values["tank.courses.2.thickness"] == 12.5
    assert values["nozzles.L8.diameter"] == 26.7
    assert values["nozzles.MW1.rating"] == "150#"
    assert "nozzles.MW1.projection_basis" not in values
    assert not any(
        item.path == "attributes.capacity" and "Valor pendiente" in item.message
        for item in reading.notices
    )


@pytest.mark.parametrize("general_condicionada", [False, True])
def test_referencia_de_proyeccion_por_marca(tmp_path, general_condicionada):
    path = tmp_path / "proyecciones.pdf"
    pdf = Canvas(str(path), pagesize=(612, 792))
    pdf.setFont("Helvetica", 9)
    general = "Dimension L is from the vessel centerline to the flange face"
    if general_condicionada:
        general += " and from BTL for nozzles on dish end"
    _line(pdf, 742, general)
    pdf.showPage()
    pdf.setFont("Helvetica", 9)
    _line(pdf, 740, "NOZZLES MECHANICAL INFORMATION")
    _table_row(pdf, 716, "Mark", "Qty.", "NPS", "Service", "Projection", "Rating", "Facing", "Sch.")
    _table_row(pdf, 695, "N1/N2", "2", '3"', "Vent", "130 mm", "150#", "RF", "40")
    _table_row(pdf, 674, "N3", "1", '3"', "Return", "270 mm", "150#", "RF", "40")
    _table_row(pdf, 653, "N4", "1", '3"', "Drain", "210 mm", "150#", "RF", "40")
    _table_row(pdf, 632, "N5", "1", '3"', "Access", "HOLD", "150#", "RF", "40")
    _table_row(pdf, 611, "N6", "1", '3"', "Drain", "420 mm", "150#", "RF", "40")
    _line(pdf, 548, "Nozzles N1 and N2: projection from the outer surface of the shell")
    _line(pdf, 526, "N3: projection from the centreline")
    _line(pdf, 505, "Projection from the shell wall for nozzle N3")
    _line(pdf, 484, "N5: projection from the vessel centerline")
    _line(pdf, 463, "N6: projection from the bottom tangent line")
    pdf.save()

    reading = read_hdm(path)
    fields = {item.path: item for item in reading.candidates}
    for mark in ("N1", "N2"):
        item = fields[f"nozzles.{mark}.projection_basis"]
        assert item.value == "shell" and item.source.page == 2
        assert f"{mark}" in item.source.text
    if general_condicionada:
        assert "nozzles.N4.projection_basis" not in fields
        assert any(
            item.path == "nozzles.N4.projection_basis" and "BTL" in item.source.text
            for item in reading.notices
        )
    else:
        item = fields["nozzles.N4.projection_basis"]
        assert item.value == "axis" and item.source.page == 1
    for mark in ("N3", "N5", "N6"):
        assert f"nozzles.{mark}.projection_basis" not in fields
    conflicts = [n.source.text for n in reading.notices if n.path == "nozzles.N3.projection_basis"]
    assert conflicts == [
        "N3: projection from the centreline",
        "Projection from the shell wall for nozzle N3",
    ]
    assert any(n.path == "nozzles.N6.projection_basis" for n in reading.notices)
    candidates, warnings = read_candidates(path.read_bytes(), "HDM-SINTETICA")
    basis = next(c for c in candidates if c.path == "nozzles.N2.projection_basis")
    assert basis.source.page == 2 and basis.source.document_id == "HDM-SINTETICA"
    assert sum("nozzles.N3.projection_basis" in warning for warning in warnings) == 2


def test_pesos_con_errata_y_rating_de_norma_no_se_confunden(tmp_path):
    path = tmp_path / "HDM-T.pdf"
    pdf = Canvas(str(path), pagesize=(612, 792))
    pdf.setFont("Helvetica", 9)
    _line(pdf, 740, "WEIGTH & CAPACITY")
    _line(pdf, 710, "1 Empty Weigth (kg): 4120")
    _line(pdf, 680, "2 Shipping Weigth: 3,8 t")
    _line(pdf, 650, "3 Insulation Thickness: 8 furlongs")
    pdf.showPage()
    pdf.setFont("Helvetica", 9)
    _line(pdf, 740, "NOZZLES MECHANICAL INFORMATION")
    _table_row(pdf, 715, "Mark", "Qty.", "NPS", "Service", "Projection", "Rating", "Facing", "Sch.")
    _table_row(pdf, 682, "Q1", "1", '3"', "Drain", "100 mm", "API 650", "RF", "STD")
    pdf.save()
    reading = read_hdm(path)
    values = {item.path: item.value for item in reading.candidates}
    assert values["attributes.weight_empty"] == 4120
    assert values["attributes.weight_transport"] == 3800
    assert "attributes.insulation_thickness" not in values
    assert "nozzles.Q1.rating" not in values
    assert {item.path for item in reading.notices} >= {
        "attributes.insulation_thickness",
        "nozzles.Q1.rating",
    }


def test_hdm_cabecera_escalonada_y_columnas_auxiliares(tmp_path: Path):
    path = tmp_path / "tabla.pdf"
    pdf = Canvas(str(path), pagesize=(612, 792))
    pdf.setFont("Helvetica", 9)
    _line(pdf, 750, "NOZZLES MECHANICAL INFORMATION")
    edges = (40, 65, 117, 157, 200, 321, 386, 433, 492, 550)
    for x in edges:
        pdf.line(x, 630, x, 738)
    for y in (738, 698, 674, 650, 630):
        pdf.line(edges[0], y, edges[-1], y)
    pdf.drawString(165, 728, "Size")
    pdf.drawString(326, 728, 'Projection "L"')
    pdf.drawString(391, 727, "Rating")
    pdf.drawString(494, 728, "Notes")
    for x, text in ((73, "Mark"), (121, "Qty."), (211, "Service"), (392, "(Notes 1, 3)")):
        pdf.drawString(x, 713, text)
    for y, index, mark, size in ((688, "8", "Q1", "2"), (664, "9", "Q3", '3" (HOLD)')):
        for x, text in (
            (47, index),
            (75, mark),
            (129, "1"),
            (158, size),
            (203, "Cleaning Water"),
            (335, "475"),
            (393, "300#"),
            (497, "Review 2"),
        ):
            pdf.drawString(x, y, text)
    pdf.drawString(207, 678, "Return")
    pdf.save()

    reading = read_hdm(path)
    values = {item.path: item.value for item in reading.candidates}
    assert sorted(reading.appearances) == ["Q1", "Q3"]
    assert values["nozzles.Q1.service"] == "Cleaning Water Return"
    assert values["nozzles.Q1.projection"] == 475
    assert values["nozzles.Q1.rating"] == "300#"
    assert values["nozzles.Q3.size_nps"] == 3
    assert any(
        item.path == "nozzles.Q3.size_nps" and "hold" in item.message.casefold()
        for item in reading.notices
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("N01", ["N1"]),
        ("n 3", ["N3"]),
        ("K3A/B", ["K3A", "K3B"]),
        ("10N", ["N1"]),
        ("pump", []),
        ("N5-M6", []),
    ],
)
def test_expansion_de_marcas(text, expected):
    assert expand_marks(text) == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ('1/8"', (0.125, 10.3)),
        ('1-1/2"', (1.5, 48.3)),
        ("NPS 2,5", (2.5, 73)),
        ("DN 40", None),
        ('1/0"', None),
    ],
)
def test_nps_no_se_confunde_con_pulgadas_geometricas_o_dn(size, expected):
    assert parse_nps(size) == expected

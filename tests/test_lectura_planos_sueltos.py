"""GA subidos sin HDM: posición de boquillas en la tabla, cabeceras en dos líneas, rótulos
girados de una columna tumbada y planos de bombas."""

import pytest
from reportlab.pdfgen import canvas

from scripts.lectura_ga import leer_pdf
from trazia.extraction import Candidate
from trazia.lectura import columna
from trazia.lectura.tipologia import indicios_tipologia
from trazia.model import Source
from trazia.pipeline import InputDocument, process


def _rejilla(pdf, x, y, anchos, altos):
    ancho, alto = sum(anchos), sum(altos)
    for i in range(len(altos) + 1):
        pdf.line(x, y - sum(altos[:i]), x + ancho, y - sum(altos[:i]))
    for j in range(len(anchos) + 1):
        pdf.line(x + sum(anchos[:j]), y, x + sum(anchos[:j]), y - alto)


def test_tabla_con_estacion_y_orientacion_da_la_posicion_de_cada_boquilla(tmp_path):
    ruta = tmp_path / "GAD_KO-V-1_rev0.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 500))
    pdf.setFont("Helvetica", 8)
    cabecera = ("POS.", "SIZE", "RATING", "PROJECTION", "STATION", "EL. (mm)", "ORIENT.")
    filas = [
        cabecera,
        ("N1", '8" [DN 200]', "150#", "1605", "830", "+3275", "0°"),
        ("N2", '3"', "150#", "1440", "5170", "+230", "180°"),
    ]
    _rejilla(pdf, 26, 400, [70] * len(cabecera), [18] * len(filas))
    for i, fila in enumerate(filas):
        for j, texto in enumerate(fila):
            pdf.drawString(30 + 70 * j, 400 - 18 * i - 13, texto)
    pdf.drawString(30, 300, "N1. PROJECTION: FROM VESSEL CENTRELINE (C/L) TO FACE OF FLANGE.")
    pdf.save()

    campos = {c["path"]: c for c in leer_pdf(ruta)["candidates"]}
    assert campos["nozzles.N1.station"]["value"] == 830
    assert campos["nozzles.N1.station"]["unit"] == "mm"
    assert campos["nozzles.N2.station"]["value"] == 5170
    assert campos["nozzles.N1.azimuth"]["value"] == 0
    assert campos["nozzles.N2.azimuth"]["value"] == 180
    assert campos["nozzles.N2.azimuth"]["unit"] == "deg"
    # La cota EL. de la tabla es desde el datum, no la estación: no se toma como posición.
    assert "nozzles.N1.elevation" not in campos


def test_cabecera_en_dos_lineas_abre_la_tabla_de_boquillas(tmp_path):
    """«NOMINAL / SIZE» partido en dos líneas bajo una fila «NOZZLE … RATING» (BF-C-0008)."""
    ruta = tmp_path / "GAD_BF-C-9_rev1.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(700, 500))
    pdf.setFont("Helvetica", 8)
    anchos, altos = [70, 70, 70, 70], [30, 18, 18]
    _rejilla(pdf, 26, 400, anchos, altos)
    pdf.drawString(30, 400 - 18, "NOZZLE")
    pdf.drawString(100, 400 - 18, "QUANTITY")
    pdf.drawString(170, 400 - 10, "NOMINAL")
    pdf.drawString(170, 400 - 26, "SIZE")
    pdf.drawString(240, 400 - 18, "RATING")
    for i, fila in enumerate((("A1", "1", '3"', "#300"), ("B2", "1", '8"', "#300"))):
        for j, texto in enumerate(fila):
            pdf.drawString(30 + 70 * j, 400 - 30 - 18 * i - 13, texto)
    pdf.save()

    salida = leer_pdf(ruta)
    campos = {c["path"]: c["value"] for c in salida["candidates"]}
    assert campos["nozzles.A1.size_nps"] == 3
    assert campos["nozzles.B2.size_nps"] == 8
    assert campos["nozzles.A1.rating"] == "#300"
    assert set(salida["nozzle_schedule"]["rows"]) == {"A1", "B2"}


@pytest.mark.parametrize(
    ("texto", "clase"), [("#300", 300), ("# 150", 150), ("300#", 300), ("PN16", None)]
)
def test_clase_de_brida_con_almohadilla_delante(texto, clase):
    from trazia.families.bridas import parse_class

    assert parse_class(texto) == clase


def test_rotulos_girados_de_la_columna_se_leen_en_los_dos_sentidos():
    # pdfplumber da al revés el texto girado de un alzado tumbado.
    assert columna._derecho("0+.LE", columna._DATUM_EL) == "EL.+0"
    assert columna._derecho("EL.+0.000", columna._DATUM_EL) == "EL.+0.000"
    assert columna._derecho("05141+.LE", columna._DATUM_EL) is None
    assert any(columna._TL.search(t) for t in columna._sentidos(".I.T.L/.L.T.B"))
    assert columna._hueco((10, 10, 20, 20), (20, 5, 30, 15)) == 0
    assert columna._hueco((0, 0, 10, 10), (13, 14, 20, 20)) == 5


def test_normas_de_bombas_y_compresores_dan_su_familia():
    caja = (0, 0, 10, 10)
    assert [(c, v) for c, v, *_ in indicios_tipologia([("as per API 682", caja)], [])] == [
        ("equipment_type", "pump")
    ]
    assert [v for _, v, *_ in indicios_tipologia([("2 x API 617", caja)], [])] == ["compressor"]
    # Un indicio de recipiente pesa más que una nota con la norma de una bomba.
    indicios = indicios_tipologia(
        [("HORIZONTAL VESSEL", caja), ("PUMP SEAL AS PER API 682", caja)], []
    )
    mejor = max(indicios, key=lambda indicio: indicio[2])
    assert mejor[1] == "horizontal_vessel"


@pytest.mark.parametrize("tipo", ["pump", "compressor"])
def test_norma_de_equipo_rotativo_no_pide_campos_de_recipiente(tmp_path, tipo):
    ruta = tmp_path / "BOMBA-GA1-Rev0.pdf"
    pdf = canvas.Canvas(str(ruta), pagesize=(400, 300))
    pdf.drawString(30, 200, "as per API 682")
    pdf.save()

    def lector(bundles, **_):
        fuente = Source(
            document_id=bundles[0].document.id,
            page=1,
            bbox=(0.05, 0.2, 0.4, 0.3),
            locator="API 682",
            confidence=0.8,
        )
        return [
            Candidate(path="attributes.equipment_type", value=tipo, unit="1", source=fuente),
            Candidate(path="tag", value="P-101", unit="1", source=fuente),
        ]

    resultado = process(
        [InputDocument(ruta.name, ruta.read_bytes(), "DOC-1")],
        project_id="P",
        equipment_id="P-101",
        revision="0",
        dataset="real",
        reader=lector,
    )
    # Sin modo preliminar falta la envolvente del equipo, nunca los campos de un recipiente.
    assert resultado.revision is None
    assert resultado.missing_data
    assert "longitud, anchura, altura" in resultado.error
    assert "diameter" not in resultado.error

"""Fondos de columna supuestos desde los tramos, y cabeceras de la tabla de boquillas."""

from trazia.extraction import Candidate
from trazia.lectura import ensamblar, tablas
from trazia.model import Source

FUENTE = Source(document_id="GA-C2", page=1, locator="C-2", confidence=0.9)


def _c(path, value, unit="mm"):
    return Candidate(path=path, value=value, unit=unit, source=FUENTE)


def _columna(*datos):
    return {c.path: c for c in [_c("attributes.equipment_type", "column", "1"), *datos]}


def test_fondos_con_el_primer_y_el_ultimo_tramo():
    elegidos = _columna(
        _c("column.sections.T1.order", 1, "1"),
        _c("column.sections.T1.diameter", 2600),
        _c("column.sections.T2.order", 2, "1"),
        _c("column.sections.T2.diameter", 2600),
        _c("column.sections.T2.top_diameter", 1950),
        _c("column.sections.T3.order", 3, "1"),
        _c("column.sections.T3.diameter", 1950),
    )
    ensamblar.completar(elegidos)
    abajo = elegidos["attributes.column_head_depth_bottom"]
    arriba = elegidos["attributes.column_head_depth_top"]
    assert (abajo.value, arriba.value) == (650, 488)
    assert abajo.state == arriba.state == "assumed"
    assert abajo.source.rule == "fondo.supuesto_2_1"


def test_fondo_elipsoidal_rotulado_no_es_supuesto():
    elegidos = _columna(
        _c("attributes.head_type", "ellipsoidal_2_1", "1"),
        _c("column.sections.T1.diameter", 1100),
    )
    ensamblar.completar(elegidos)
    for lado in ("bottom", "top"):
        fondo = elegidos[f"attributes.column_head_depth_{lado}"]
        assert fondo.value == 275
        assert fondo.state != "assumed"


def test_tramos_sin_orden_no_dan_fondos():
    elegidos = _columna(
        _c("column.sections.T1.diameter", 2600),
        _c("column.sections.T2.diameter", 1950),
    )
    ensamblar.completar(elegidos)
    assert "attributes.column_head_depth_bottom" not in elegidos


def test_cabeceras_nozzle_nominal_y_norma_de_brida():
    assert tablas._columna("NOZZLE") == "mark"
    assert tablas._columna("NOMINAL SIZE") == "size_nps"
    assert tablas._columna("FLANGE STANDARD") == ""
    assert tablas._columna("Nozzle\nType") == ""
    assert tablas._columna("NOZZLES") == ""
    assert tablas._columna("FLANGE TYPE") == tablas._columna("FLANGE")

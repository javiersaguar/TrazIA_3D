"""Azimut supuesto cuando una revisión deja la orientación de las boquillas sin definir."""

from trazia.extraction import Candidate
from trazia.lectura.orientacion import REGLA, azimuts_supuestos
from trazia.model import Source


def _fila(path, value, unit="mm"):
    return Candidate(
        path=path,
        value=value,
        unit=unit,
        source=Source(
            document_id="GA-BF-C-0003",
            page=2,
            locator=path,
            confidence=0.8,
            text_original=str(value),
            unit_original=unit,
        ),
        channel="tabla",
    )


def test_copia_el_azimut_de_la_revision_siguiente_como_supuesto():
    actual = [
        _fila("nozzles.N1.elevation", 1200),
        _fila("nozzles.N1.diameter", 50),
        _fila("nozzles.N2.size_nps", 2, "in"),
    ]
    siguiente = [
        {
            "path": "nozzles.N1.azimuth",
            "value": 90,
            "source": {"document_id": "GA-REV2", "page": 4},
        },
        {"path": "nozzles.N2.azimuth", "value": 180.0},
        {"path": "nozzles.N3.azimuth", "value": 0},
    ]
    supuestos = azimuts_supuestos(actual, siguiente)
    por_marca = {c.path: c for c in supuestos}
    assert set(por_marca) == {"nozzles.N1.azimuth", "nozzles.N2.azimuth"}
    n1 = por_marca["nozzles.N1.azimuth"]
    assert n1.value == 90 and n1.unit == "deg" and n1.state == "assumed"
    assert n1.source.rule == REGLA and n1.source.confidence == 0.5
    assert n1.source.document_id == "GA-BF-C-0003" and n1.source.page == 2
    assert "GA-REV2" in n1.explanation and "pág. 4" in n1.explanation


def test_no_supone_si_esta_revision_ya_trae_algun_azimut():
    actual = [_fila("nozzles.N1.diameter", 50), _fila("nozzles.N1.azimuth", 45, "deg")]
    siguiente = [{"path": "nozzles.N2.azimuth", "value": 90}]
    assert azimuts_supuestos(actual, siguiente) == []


def test_ignora_azimuts_que_no_son_un_angulo():
    actual = [_fila("nozzles.N1.diameter", 50)]
    assert azimuts_supuestos(actual, [{"path": "nozzles.N1.azimuth", "value": "N"}]) == []

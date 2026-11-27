import pytest

from scripts.lectura_ga import expandir_marcas


@pytest.mark.parametrize(
    ("texto", "cantidad", "esperado"),
    [
        ("n 01", None, ["N1"]),
        ("L01–L03", 3, ["L1", "L2", "L3"]),
        ("L1-6", 2, []),
        ("L1-6", None, []),
        ("N1/N3", None, ["N1", "N3"]),
        ("N13 A/B", 2, ["N13A", "N13B"]),
        ("K3A/B", 2, ["K3A", "K3B"]),
        ("N4 (HOLD)", None, ["N4"]),
        ("N1.", None, []),
        ("4 x M30", None, []),
        ("N3-X4", 2, []),
    ],
)
def test_marcas_por_celda(texto, cantidad, esperado):
    assert expandir_marcas(texto, cantidad) == esperado


def test_invertido_solo_si_la_geometria_lo_indica():
    assert expandir_marcas("1N") == []
    assert expandir_marcas("1N", invertida=True) == ["N1"]

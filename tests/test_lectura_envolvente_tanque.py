"""Tangentes «TL. to TL.» y tabla de datos de un tanque en el GA, con palabras sintéticas."""

from trazia.lectura import envolvente


def _palabra(texto, x0, top, ancho=None, alto=8.0):
    ancho = ancho if ancho is not None else 5.0 * len(texto)
    return {"text": texto, "x0": x0, "x1": x0 + ancho, "top": top, "bottom": top + alto}


def test_tangentes_con_y_sin_punto_tras_la_t():
    for texto in ("11800 TL. to TL.", "5700 T.L. TO T.L.", "5700 (T.L. TO T.L.)"):
        assert envolvente._TANGENTES.search(texto), texto
    assert envolvente._TANGENTES.search("11800 TL. to TL.")[1] == "11800"
    assert not envolvente._TANGENTES.search("11800 TL TO TL")


def _tabla_tanque(diametro="Ø12,5m", altura="14,0m"):
    return [
        _palabra("Inside", 100, 50),
        _palabra("diameter", 132, 50),
        _palabra("Cyl.", 240, 50),
        _palabra("height", 262, 50),
        _palabra("Nominal", 10, 67),
        _palabra("volume", 50, 67),
        _palabra("1500", 80, 67),
        _palabra("m³", 102, 67),
        _palabra("x", 120, 67),
        _palabra("tank", 130, 67),
        _palabra(diametro, 180, 67),
        _palabra("x", 222, 67),
        _palabra("tank", 232, 67),
        _palabra(altura, 300, 67),
    ]


def test_tabla_de_datos_del_tanque_da_diametro_y_altura():
    leido = {
        ruta: (valor, unidad, regla)
        for ruta, valor, unidad, _, _, regla, _ in envolvente._tanque(_tabla_tanque())
    }
    assert leido["tank.diameter"] == (12500, "mm", "ga.tanque_diametro_interior")
    assert leido["attributes.diameter_basis"][0] == "inside"
    assert leido["tank.height"] == (14000, "mm", "ga.tanque_altura_cilindro")


def test_sin_cabecera_o_con_valores_dudosos_no_lee_el_tanque():
    palabras = _tabla_tanque()
    assert envolvente._tanque([p for p in palabras if p["text"] != "Cyl."]) == []
    # Un solo valor en metros: no se sabe a qué columna corresponde.
    assert envolvente._tanque([p for p in palabras if p["text"] != "14,0m"]) == []
    # Sin la unidad («14,0») no se sabe si son metros.
    assert envolvente._tanque(_tabla_tanque(altura="14,0")) == []

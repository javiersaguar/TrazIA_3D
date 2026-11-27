"""bench.aprobacion: etiquetas frente al oro y precisión de la aprobación automática."""

import json
from pathlib import Path

from bench import aprobacion

EJEMPLO = Path(__file__).resolve().parents[1] / "examples" / "vessel_rev_a.json"


def test_coincide_numeros_con_tolerancia_y_codigos_por_palabras():
    assert aprobacion.coincide(2000.4, "2000")
    assert not aprobacion.coincide(2100, 2000)
    assert aprobacion.coincide("ellipsoidal_2_1", "2:1 ellipsoidal")
    assert aprobacion.coincide("ellipsoidal_2_1", "2:1 ellipsoidal (solo fondo inferior)")
    assert aprobacion.coincide("SA-516-70", "SA 516-70")
    assert not aprobacion.coincide("Internal floating roof no", "S355J2+N")
    assert not aprobacion.coincide("no", "no aplica en este plano")  # una palabra no basta


def _lote_con_oro(tmp_path):
    revision = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    atributos = revision["equipment"]["attributes"]
    for nombre, confianza in (("design_pressure", 0.85), ("material", 0.9)):
        atributos[nombre]["source"].update(confidence=confianza, grounded=True)
    carpeta = tmp_path / "lote" / "V-9" / "rev1"
    carpeta.mkdir(parents=True)
    (carpeta / "revision.json").write_text(json.dumps(revision), encoding="utf-8")
    oro = {
        "tag": "V-9",
        "revisiones": {
            "rev1": {
                "equipment_type": "vertical_vessel",
                "support": "skirt",
                "campos": {
                    "attributes.design_pressure": {"valor": 16, "unidad": "barg"},
                    "attributes.material": {"valor": "SA 516-70"},
                    "attributes.operating_weight": {"valor": 9999, "unidad": "kg"},
                    "attributes.design_temperature": {"valor": None},
                    "diameter": {"valor": 2000, "base": "interior"},
                },
                "boquillas": {},
            }
        },
    }
    (tmp_path / "oro").mkdir()
    (tmp_path / "oro" / "V-9.json").write_text(json.dumps(oro), encoding="utf-8")
    return tmp_path / "lote", tmp_path / "oro"


def test_mide_lo_que_se_aprobaria_solo_sin_copiar_valores(tmp_path):
    lote, oro = _lote_con_oro(tmp_path)
    r = aprobacion.evaluar(lote, oro)
    # Sin valor en el oro o con base propia, el campo no se juzga.
    assert r["juzgados"] == {"n": 3, "aciertos": 2, "precision": 0.6667}
    api = r["aprobacion_automatica"]["0.8"]
    assert (api["n"], api["aciertos"]) == (2, 2)
    assert (api["resto"]["n"], api["resto"]["aciertos"]) == (1, 0)
    assert r["por_equipo"]["V-9"]["n"] == 3
    salida = json.dumps(r) + aprobacion.markdown(r)
    for valor in ("9999", "SA 516", "SA-516", "16.0"):
        assert valor not in salida

"""bench.oro solo puntúa diámetro, longitud y proyección en una base común (datos inventados)."""

import pytest

from bench import oro


def _pred(valores=None, reglas=None, candidatos=None, modelo=True):
    return oro.Prediccion(
        modelo=modelo,
        fuente="revision" if modelo else "candidatos",
        valores=dict(valores or {}),
        reglas=dict(reglas or {}),
        candidatos=dict(candidatos or {}),
    )


CAMPOS = {
    "diameter": {"valor": 800, "unidad": "mm", "base": "inside"},
    "attributes.shell_thickness": {"valor": 10, "unidad": "mm"},
    "height": {"valor": 2100, "unidad": "mm", "base": "T.L. a cara de brida del cuerpo"},
}


def test_diametro_exterior_del_modelo_frente_a_interior_del_oro():
    pred = _pred({"diameter": 820}, {"diameter": "vertical.diametro_exterior"})
    medida = oro.comparar_diametro(CAMPOS, pred)
    assert medida["error"] == 0 and medida["no_comparable"] is None
    assert medida["base"].startswith("outside (oro convertido")


def test_diametro_sin_espesor_o_sin_base_no_es_comparable():
    sin_espesor = {"diameter": CAMPOS["diameter"]}
    pred = _pred({"diameter": 820}, {"diameter": "vertical.diametro_exterior"})
    assert "sin espesor de virola" in oro.comparar_diametro(sin_espesor, pred)["no_comparable"]
    sin_base_oro = {"diameter": {"valor": 800, "base": "sin indicar (ID u OD)"}}
    assert oro.comparar_diametro(sin_base_oro, pred)["no_comparable"] == "el oro no indica ID u OD"
    leido_sin_base = oro.comparar_diametro(CAMPOS, _pred({"diameter": 800}))
    assert leido_sin_base == {
        "error": None,
        "base": None,
        "no_comparable": "la lectura no indica ID u OD",
    }


def test_diametro_con_la_misma_base_desde_los_candidatos():
    pred = _pred(
        {"diameter": 808},
        candidatos={"attributes.diameter_basis": "inside"},
        modelo=False,
    )
    assert oro.comparar_diametro(CAMPOS, pred)["error"] == pytest.approx(0.01)


def test_longitud_hasta_la_brida_no_se_compara_con_la_de_tangentes():
    medida = oro.comparar_longitud(CAMPOS, _pred({"height": 2100}))
    assert medida["error"] is None
    assert medida["no_comparable"] == "oro «T.L. a cara de brida del cuerpo» y modelo «tl-tl»"
    tangentes = {"height": {"valor": 2000, "base": "T.L.-T.L."}}
    assert oro.comparar_longitud(tangentes, _pred({"height": 2100}))["error"] == 0.05
    sin_modelo = oro.comparar_longitud(tangentes, _pred({"height": 2000}, modelo=False))
    assert sin_modelo["no_comparable"] == "la lectura no indica la base"


def test_altura_de_tanque_en_la_base_de_la_virola():
    campos = {"tank.height": {"valor": 9000, "base": "altura cilíndrica"}}
    medida = oro.comparar_longitud(campos, _pred({"tank.height": 9000}))
    assert medida["error"] == 0 and medida["base"] == "virola"


def test_proyeccion_desde_el_eje_pasada_a_la_virola():
    oro_boq = {
        "N1": {"standout_mm": 1000, "standout_base": "eje"},
        "N2": {"standout_mm": 300, "standout_base": "T.L."},
        "N3": {"standout_mm": 1000, "standout_base": None},
        "N4": {"standout_mm": 1000, "standout_base": "eje"},
    }
    pred_boq = {m: {"projection": 590} for m in oro_boq}
    pred = _pred(
        reglas={"nozzles.n1.projection": "virola.proyeccion_desde_eje"},
        candidatos={
            "nozzles.N2.projection_basis": "axis",
            "nozzles.N3.projection_basis": "axis",
            "nozzles.N4.projection_basis": "axis",
        },
    )
    diferencias, no_comparables = oro.comparar_proyecciones(
        CAMPOS, oro_boq, pred_boq, sorted(oro_boq), pred
    )
    # N1: 1000 desde el eje menos el radio exterior del oro (400 + 10) = 590 desde la virola.
    # N4: las dos desde el eje, 590 frente a 1000. N2 (T.L.) y N3 (sin base) no se comparan.
    assert diferencias == [0, 410] and no_comparables == 2


def test_el_informe_cuenta_los_no_comparables():
    filas = [
        {
            **{clave: 0 for clave in _CLAVES_SUMADAS},
            "modelo": True,
            "ifc_valido": True,
            "tipo_ok": True,
            "soporte_ok": True,
            "boquillas_colocadas": 0,
            "falsos_ids_como_boquilla": [],
            "error_diametro": None,
            "diametro_no_comparable": "el oro no indica ID u OD",
            "error_longitud": 0.01,
            "longitud_no_comparable": None,
            "error_proyeccion_mm": 5.0,
            "proyecciones_evaluables": 3,
            "proyecciones_no_comparables": 2,
            "error_elevacion_mm": None,
            "error_azimut_deg": None,
            "error_cota_soldadura_mm": None,
        }
    ]
    agregado = oro.agregar(filas, {})
    assert agregado["no_comparables"] == {
        "diametro": 1,
        "longitud": 0,
        "proyecciones": 2,
        "proyecciones_evaluables": 3,
    }
    assert agregado["error_proyeccion_mm"] == {"mediana": 5.0, "n": 1}
    texto = oro.markdown({"agregado": agregado, "filas": []})
    assert "no comparables por la base: 1" in texto and "Proyección (mediana): 5 mm" in texto


_CLAVES_SUMADAS = (
    "marcas_oro",
    "marcas_leidas",
    "marcas_acertadas",
    "nps_ok",
    "nps_evaluables",
    "rating_ok",
    "rating_evaluables",
    "fuera_de_tabla",
    "soldaduras_oro",
    "soldaduras_encontradas",
    "soldaduras_leidas",
    "soldaduras_falsas",
    "soldaduras_sin_oro",
    "soldaduras_pieza_ok",
    "soldaduras_pieza_evaluables",
    "piezas_oro",
    "piezas_presentes",
    "piezas_campos_ok",
    "piezas_campos_evaluables",
)


def test_proyeccion_de_horizontal_ya_pasada_a_la_virola():
    # El ensamblado horizontal resta el radio y deja la regla `horizontal.proyeccion_desde_eje`;
    # el candidato de base sigue diciendo «axis», pero el valor del modelo es desde la virola.
    oro_boq = {"N1": {"standout_mm": 1000, "standout_base": "eje"}}
    pred = _pred(
        reglas={"nozzles.N1.projection": "horizontal.proyeccion_desde_eje"},
        candidatos={"nozzles.N1.projection_basis": "axis"},
    )
    diferencias, no_comparables = oro.comparar_proyecciones(
        CAMPOS, oro_boq, {"N1": {"projection": 590}}, ["N1"], pred
    )
    assert diferencias == [0] and no_comparables == 0


def test_estacion_de_horizontal_frente_a_la_posicion_axial():
    # En un horizontal `elevation` es la altura sobre el suelo y la estación va en `position.x`.
    modelo = {"elevation": 2500, "position.x": 1150}
    assert oro.diferencia_cota({"station_mm": 1150}, modelo) == 0
    assert oro.diferencia_cota({"station_mm": 1150}, {"elevation": 2500}) is None
    assert oro.diferencia_cota({"station_mm": 1150}, {"station": 1100}) == 50
    assert oro.diferencia_cota({"elevation_mm": 2400}, modelo) == 100
    assert oro.diferencia_cota({}, modelo) is None


def test_azimut_vertical_vuelve_a_la_escala_del_plano():
    # La lectura guarda 90 − rumbo (0° hacia +X, antihorario); el oro va en la escala del plano.
    pred = _pred(
        reglas={
            "nozzles.A1.azimuth": "vertical.azimut_escala_plano",
            "nozzles.L5.azimuth": "vertical.azimut_desde_norte",
        }
    )
    assert oro.azimut_en_plano(pred, "A1", 90) == 0
    assert oro.azimut_en_plano(pred, "L5", 315) == 135
    # Sin regla vertical (ángulo de cabezal de un horizontal) el valor no cambia.
    assert oro.azimut_en_plano(pred, "N1", 180) == 180
    assert oro.azimut_en_plano(pred, "A1", None) is None

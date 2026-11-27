"""bench.oro con un oro y un lote inventados: sin datos de TR."""

import json

from bench import oro


def _escribir(path, datos):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(datos), encoding="utf-8")


ORO = {
    "tag": "T-1",
    "revisiones": {
        "rev1": {
            "equipment_type": "horizontal_vessel",
            "support": "saddles",
            "campos": {
                "horizontal.diameter": {"valor": 2000, "unidad": "mm", "base": "inside"},
                "horizontal.length": {"valor": 6000, "unidad": "mm", "base": "T.L.-T.L."},
            },
            "boquillas": {
                "N1": {
                    "size_nps": 8,
                    "rating": "150#",
                    "standout_mm": 1500,
                    "standout_base": "eje",
                    "station_mm": 1000,
                    "azimuth_deg": 350,
                },
                "N2": {
                    "size_nps": 4,
                    "rating": "300#",
                    "standout_mm": 1500,
                    "standout_base": "eje",
                },
                "K5": {"size_nps": 2, "rating": "150#", "standout_mm": 600},
            },
            "piezas": {
                "V01": {"codigo": "00000001", "espesor_mm": 10, "altura_mm": 2000},
                "V02": {"codigo": "00000002", "espesor_mm": 12, "altura_mm": None},
            },
        },
        "rev2": {
            "igual_que": "rev1",
            "boquillas_eliminadas": ["K5"],
            "boquillas_modificadas": {"N2": {"standout_mm": 1400}},
        },
    },
    "fuera_de_tabla": [
        {"texto": "M30", "clase": "rosca", "revisiones": ["rev1"]},
        {"texto": "N7.", "clase": "nota", "revisiones": ["rev2"]},
    ],
    "cambios_rev1_rev2": [
        {"tipo": "boquilla_eliminada", "marca": "K5"},
        {"tipo": "boquilla_modificada", "marca": "N2", "campo": "standout_mm"},
        {"tipo": "sin_cambio_real", "ruta": "attributes.volume"},
    ],
}


def test_rev2_se_resuelve_desde_rev1():
    revs = oro.revisiones_efectivas(ORO)
    assert set(revs["rev2"]["boquillas"]) == {"N1", "N2"}
    assert revs["rev2"]["boquillas"]["N2"]["standout_mm"] == 1400
    assert revs["rev1"]["boquillas"]["N2"]["standout_mm"] == 1500  # rev1 no se modifica
    assert revs["rev2"]["equipment_type"] == "horizontal_vessel"


def test_mide_candidatos_modelo_y_cambios(tmp_path):
    _escribir(tmp_path / "oro" / "T-1.json", ORO)
    lote = tmp_path / "lote"
    # rev1 sin modelo: solo candidatos (el de menor confianza no cuenta)
    _escribir(
        lote / "T-1" / "rev1" / "candidatos.json",
        [
            {"path": "horizontal.diameter", "value": 2010, "confidence_raw": 0.9},
            {"path": "horizontal.diameter", "value": 50, "confidence_raw": 0.1},
            {"path": "attributes.diameter_basis", "value": "inside", "confidence_raw": 0.9},
            {"path": "nozzles.n1.size_nps", "value": 8},
            {"path": "nozzles.n1.rating", "value": "150 lb"},
            {"path": "nozzles.x9.size_nps", "value": 2},
            {"path": "nozzles.n1.station", "value": 1040},
            {"path": "nozzles.n1.azimuth", "value": 10},
            {"path": "nozzles.m30.size_nps", "value": 1},
            {"path": "shell.courses.V01.code", "value": "00000001"},
            {"path": "shell.courses.V01.thickness", "value": 10.0},
            {"path": "shell.courses.V01.height", "value": 2100.0},
        ],
    )
    # rev2 con modelo: rutas anidadas del contrato, boquillas como lista con id
    equipo = {
        "kind": "horizontal_vessel",
        "support": "saddles",
        "attributes": {"diameter_basis": {"value": "inside", "unit": "1"}},
        "horizontal": {
            "diameter": {"value": 2000, "unit": "mm"},
            "length": {"value": 5700, "unit": "mm"},
        },
        "nozzles": [
            {"id": "n1", "projection": {"value": 1500, "unit": "mm"}},
            {"id": "n2", "projection": {"value": 1450, "unit": "mm"}},
        ],
    }
    _escribir(lote / "T-1" / "rev2" / "revision.json", {"equipment": equipo})
    _escribir(
        lote / "T-1" / "rev2" / "candidatos.json",
        [
            {"path": "nozzles.n1.projection_basis", "value": "axis"},
            {"path": "nozzles.n2.projection_basis", "value": "axis"},
        ],
    )
    (lote / "T-1" / "rev2" / "modelo.ifc").write_text("ISO-10303-21;", encoding="utf-8")
    _escribir(
        lote / "T-1" / "cambios_rev1_rev2.json",
        {"changes": [{"path": "nozzles.k5.id"}, {"path": "diameter"}]},
    )
    _escribir(lote / "resumen.json", [{"tag": "T-1", "revision": "2", "avisos": 1, "segundos": 2}])

    informe = oro.evaluar(lote, tmp_path / "oro")
    rev1, rev2 = informe["filas"]

    assert rev1["fuente"] == "candidatos" and not rev1["modelo"]
    assert round(rev1["error_diametro"], 3) == 0.005
    assert (rev1["marcas_acertadas"], rev1["marcas_leidas"], rev1["marcas_oro"]) == (1, 3, 3)
    assert rev1["nps_ok"] == 1 and rev1["rating_ok"] == 1
    assert rev1["error_elevacion_mm"] == 40  # estación del oro frente a la cota leída
    assert rev1["error_azimut_deg"] == 20  # 350° y 10° distan 20°, no 340°
    assert rev1["falsos_ids_como_boquilla"] == ["M30"] and rev1["fuera_de_tabla"] == 1
    assert (rev1["piezas_oro"], rev1["piezas_presentes"]) == (2, 1)
    assert rev1["piezas_faltantes"] == ["V02"]
    assert (rev1["piezas_campos_ok"], rev1["piezas_campos_evaluables"]) == (2, 3)

    assert rev2["modelo"] and rev2["ifc_valido"] and rev2["tipo_ok"] and rev2["soporte_ok"]
    assert rev2["error_diametro"] == 0
    assert round(rev2["error_longitud"], 2) == 0.05
    assert rev2["error_proyeccion_mm"] == 25  # mediana de |1500-1500| y |1450-1400|
    assert rev2["segundos"] == 2
    assert rev2["fuera_de_tabla"] == 1 and rev2["falsos_ids_como_boquilla"] == []
    assert rev2["piezas_oro"] == 2  # las piezas de rev1 se heredan con igual_que

    cambios = informe["cambios"]["T-1"]
    assert cambios == {
        "evaluables": 2,
        "acertados": 1,
        "a_revision": 0,
        "faltantes": 1,
        "falsos": 1,
        "predichos": 2,
    }
    agregado = informe["agregado"]
    assert agregado["fuera_de_tabla"] == {"evaluables": 2, "contados_como_boquilla": 1}
    assert agregado["piezas"]["presentes"] == 1
    texto = oro.markdown(informe)
    assert "Medida contra el oro" in texto and "Falsos IDs" in texto


def test_boquillas_sin_colocar_cuentan_como_marcas(tmp_path):
    carpeta = tmp_path / "T-1" / "rev1"
    equipo = {
        "kind": "horizontal_vessel",
        "nozzles": [{"id": "N1", "projection": {"value": 1500, "unit": "mm"}}],
    }
    _escribir(carpeta / "revision.json", {"equipment": equipo, "unplaced_nozzles": ["N2", "K5"]})
    _escribir(
        carpeta / "candidatos.json",
        [
            {"path": "nozzles.N2.size_nps", "value": 4, "confidence_raw": 0.9},
            {"path": "nozzles.N2.rating", "value": "300 lb", "confidence_raw": 0.9},
            {"path": "nozzles.N1.size_nps", "value": 99, "confidence_raw": 0.9},
        ],
    )
    pred = oro.leer_prediccion(carpeta)
    assert pred.colocadas == 1
    assert set(pred.boquillas()) == {"N1", "N2", "K5"}
    assert pred.boquillas()["N2"]["size_nps"] == 4
    assert "size_nps" not in pred.boquillas()["N1"]  # la colocada manda: no se mezcla

    fila = oro.medir_revision(oro.revisiones_efectivas(ORO)["rev1"], pred)
    assert (fila["marcas_acertadas"], fila["boquillas_colocadas"]) == (3, 1)
    assert fila["nps_ok"] == 1 and fila["rating_ok"] == 1


def test_soldaduras_por_marca_cota_y_alias():
    oro_sold = [
        {"id": "W:1|2", "tipo": "circumferential", "une": ["1", "2"], "cota_mm": 50},
        {"id": "W:2|3", "tipo": "circumferential", "une": ["2", "3"], "cota_mm": 1975},
        {"id": "W:2:LONG", "tipo": "longitudinal", "une": ["2"], "id_alias": "W:SHELL:LONG"},
        {"id": "W:D1|1", "tipo": "nozzle", "une": ["D1", "1"], "id_alias": "W:D1|HEAD_BOTTOM"},
        {"id": "W:A1|2", "tipo": "nozzle", "une": ["A1", "2"], "id_alias": "W:A1|SHELL"},
    ]
    leidas = {
        "W:SHELL|HEAD_BOTTOM": {
            "kind": "circumferential",
            "joins": "SHELL|HEAD_BOTTOM",
            "elevation_mm": 0.0,
        },
        "W:SHELL|BODY_FLANGE": {"kind": "circumferential", "elevation_mm": 2100.0},
        "W:SHELL:LONG": {"kind": "longitudinal"},
        "W:D1|SHELL": {"kind": "nozzle", "joins": "D1|SHELL"},
        "W:A1|SHELL": {"kind": "nozzle", "joins": "A1|SHELL"},
        "W:Z9|SHELL": {"kind": "nozzle", "joins": "Z9|SHELL"},
    }
    m = oro.medir_soldaduras(oro_sold, leidas)
    # 1975 frente a 2100 queda fuera de los 100 mm: no se encuentra y su lectura cuenta como falsa
    assert (m["soldaduras_encontradas"], m["soldaduras_falsas"]) == (4, 2)
    assert m["error_cota_soldadura_mm"] == 50
    assert (m["soldaduras_pieza_ok"], m["soldaduras_pieza_evaluables"]) == (
        1,
        2,
    )  # D1 no va en SHELL


def test_soldaduras_del_oro_por_revision():
    datos = {
        **ORO,
        "soldaduras": [
            {"id": "W:K5|?", "tipo": "nozzle", "une": ["K5", None], "revisiones": ["rev1"]},
            {"id": "W:N1|1", "tipo": "nozzle", "une": ["N1", "1"], "revisiones": ["rev1", "rev2"]},
        ],
    }
    revs = oro.revisiones_efectivas(datos)
    assert [s["id"] for s in revs["rev1"]["soldaduras"]] == ["W:K5|?", "W:N1|1"]
    assert [s["id"] for s in revs["rev2"]["soldaduras"]] == ["W:N1|1"]


def test_elevacion_vertical_del_modelo_desde_la_tangente(tmp_path):
    oro_rev = {
        "equipment_type": "vertical_vessel",
        "support": "legs",
        "campos": {},
        "boquillas": {"A1": {"elevation_mm": 1200}, "L1": {"elevation_mm": 1100}},
    }
    carpeta = tmp_path / "T-2" / "rev2"
    equipo = {
        "kind": "vertical_vessel",
        "legs": {"height": {"value": 1000, "unit": "mm"}},
        "nozzles": [{"id": "A1", "elevation": {"value": 2210, "unit": "mm"}}],
    }
    _escribir(carpeta / "revision.json", {"equipment": equipo, "unplaced_nozzles": ["L1"]})
    # L1 sin colocar: su elevación sale de los candidatos, que ya miden desde la T.L.
    _escribir(carpeta / "candidatos.json", [{"path": "nozzles.L1.elevation", "value": 1100}])
    pred = oro.leer_prediccion(carpeta)
    assert pred.tangente_inferior() == 1000
    fila = oro.medir_revision(oro_rev, pred)
    assert fila["elevaciones_evaluables"] == 2
    assert fila["error_elevacion_mm"] == 5  # mediana de |2210 - 1000 - 1200| y |1100 - 1100|


def test_rutas_de_cambio_del_oro_frente_al_contrato():
    datos = {
        "cambios_rev1_rev2": [
            {"tipo": "campo_modificado", "ruta": "attributes.shell_height"},
            {"tipo": "campo_modificado", "ruta": "attributes.shell_courses_thickness"},
        ]
    }
    predichos = [
        {"path": "height"},
        {"path": "tank.courses.1.thickness"},
        {"path": "tank.courses.2.thickness"},
        {"path": "attributes.shell_thickness"},
    ]
    medida = oro.medir_cambios(datos, predichos)
    assert (medida["acertados"], medida["falsos"]) == (2, 0)


def test_piezas_del_modelo_se_completan_con_los_candidatos(tmp_path):
    # El contrato aún no lleva `shell.courses`: con modelo, las piezas siguen en los candidatos.
    carpeta = tmp_path / "T-1" / "rev1"
    equipo = {
        "kind": "horizontal_vessel",
        "shell": {"courses": [{"id": "V02", "code": {"value": "X", "unit": "1"}}]},
    }
    _escribir(carpeta / "revision.json", {"equipment": equipo})
    _escribir(
        carpeta / "candidatos.json",
        [
            {"path": "shell.courses.V01.code", "value": "00000001", "confidence_raw": 0.9},
            {"path": "shell.courses.V01.thickness", "value": 10.0, "confidence_raw": 0.9},
            {"path": "shell.courses.V01.height", "value": 2000.0, "confidence_raw": 0.9},
            {"path": "shell.courses.V02.code", "value": "00000002", "confidence_raw": 0.9},
            {"path": "shell.courses.V02.thickness", "value": 12.0, "confidence_raw": 0.9},
        ],
    )
    pred = oro.leer_prediccion(carpeta)
    assert pred.modelo
    assert pred.piezas()["V02"] == {"code": "X", "thickness": 12.0}  # el modelo manda
    fila = oro.medir_revision(oro.revisiones_efectivas(ORO)["rev1"], pred)
    assert (fila["piezas_presentes"], fila["piezas_oro"]) == (2, 2)
    assert (fila["piezas_campos_ok"], fila["piezas_campos_evaluables"]) == (4, 5)


def test_soldaduras_sin_oro_no_son_falsas():
    leidas = {"W:N1|SHELL": {"kind": "nozzle", "joins": "N1|SHELL"}}
    sin_oro = oro.medir_soldaduras(None, leidas)
    assert (sin_oro["soldaduras_falsas"], sin_oro["soldaduras_sin_oro"]) == (0, 1)
    assert sin_oro["soldaduras_leidas"] == 1 and sin_oro["soldaduras_oro"] == 0
    # Una lista vacía sí es oro: el plano no tiene uniones y la leída es falsa.
    vacio = oro.medir_soldaduras([], leidas)
    assert (vacio["soldaduras_falsas"], vacio["soldaduras_sin_oro"]) == (1, 0)
    assert oro.revisiones_efectivas(ORO)["rev1"]["soldaduras"] is None
    assert oro.revisiones_efectivas({**ORO, "soldaduras": []})["rev1"]["soldaduras"] == []


def test_cambio_que_la_comparacion_manda_a_revisar():
    datos = {
        "cambios_rev1_rev2": [
            {"tipo": "campo_añadido", "ruta": "attributes.cog_elevation"},
            {"tipo": "boquilla_modificada", "marca": "N2", "campo": "standout_mm"},
            {"tipo": "campo_modificado", "ruta": "diameter"},
        ]
    }
    predichos = [{"path": "nozzles.N2.projection"}]
    revisar = [{"path": "attributes.cog_elevation", "motivo": "solo_en_una_revision"}]
    medida = oro.medir_cambios(datos, predichos, revisar)
    assert (medida["acertados"], medida["a_revision"], medida["faltantes"]) == (1, 1, 1)
    assert medida["falsos"] == 0  # lo que va a `revisar` no se da por cambio
    assert oro.medir_cambios(datos, predichos)["a_revision"] == 0


def test_cambio_por_marca_exige_la_marca_entera():
    datos = {
        "cambios_rev1_rev2": [
            {"tipo": "boquilla_modificada", "marca": "N1", "campo": "rating"},
            {"tipo": "boquilla_modificada", "marca": "N13A", "campo": "size_nps"},
        ]
    }
    predichos = [
        {"path": "nozzles.N1.rating"},
        {"path": "nozzles.N10.service"},
        {"path": "nozzles.N13A.size_nps"},
        {"path": "nozzles.N13"},
    ]
    medida = oro.medir_cambios(datos, predichos)
    assert (medida["acertados"], medida["falsos"]) == (2, 2)


def test_cambio_de_boquilla_exige_el_campo_si_el_oro_lo_da():
    datos = {
        "cambios_rev1_rev2": [
            {"tipo": "boquilla_modificada", "marca": "A1", "campo": "standout_mm"},
            {"tipo": "boquilla_modificada", "marca": "A1", "campo": "elevation_mm"},
            {"tipo": "boquilla_modificada", "marca": "L1", "campo": "elevation_mm/size_nps"},
            {"tipo": "boquilla_modificada", "marca": "S1", "campo": "hold"},
            {"tipo": "boquilla_eliminada", "marca": "K5"},
        ]
    }
    predichos = [
        {"path": "nozzles.A1.projection"},
        {"path": "nozzles.L1.size_nps"},
        {"path": "nozzles.S1.service"},  # campo desconocido en el oro: basta la marca
        {"path": "nozzles.K5"},
        {"path": "nozzles.K5.service"},  # la baja se casa por la marca, con o sin campo
        {"path": "nozzles.N2"},  # una baja no da por bueno un cambio de campo
    ]
    medida = oro.medir_cambios(datos, predichos)
    # La cota de A1 no se lee: la proyección no la da por buena.
    assert (medida["acertados"], medida["faltantes"], medida["falsos"]) == (4, 1, 1)

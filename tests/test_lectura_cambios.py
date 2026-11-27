"""Cambios entre revisiones por ID a partir de lo leído, con datos sintéticos."""

import json

from trazia import lote
from trazia import pipeline as pipeline_mod
from trazia.extraction import Candidate
from trazia.lectura.cambios import comparar_candidatos
from trazia.model import RunInfo, Source


def _c(path, value, unit="mm", confianza=0.9, texto=None):
    return {
        "path": path,
        "value": value,
        "unit": unit,
        "source": {
            "document_id": "GA-EJ-V-01",
            "page": 1,
            "locator": texto or f"{path} {value}",
            "confidence": confianza,
        },
    }


def _tabla(ident, nps=2.0):
    return [_c(f"nozzles.{ident}.size_nps", nps, "in"), _c(f"nozzles.{ident}.rating", "300#", "1")]


def _rutas(resultado, operacion=None):
    return {c["path"] for c in resultado["changes"] if operacion in (None, c["operation"])}


def test_solo_cambia_lo_leido_en_las_dos_revisiones():
    antes = [*_tabla("N1"), _c("nozzles.N1.projection", 610), _c("diameter", 800)]
    despues = [*_tabla("N1"), _c("nozzles.N1.projection", 410), _c("height", 1940)]
    resultado = comparar_candidatos(antes, despues)
    assert _rutas(resultado) == {"nozzles.N1.projection"}
    cambio = resultado["changes"][0]
    assert cambio["before"]["value"] == 610 and cambio["after"]["value"] == 410
    assert cambio["affects_geometry"] and cambio["after_source"]["page"] == 1
    assert resultado["nivel"] == "candidatos"
    assert resultado["por_id"]["cambiados"]["N1"]["projection"] == [610, 410]
    # «diameter» solo en rev1 y «height» solo en rev2: no son altas ni bajas.
    assert resultado["summary"]["rutas_solo_antes"] == 1
    assert resultado["summary"]["rutas_solo_despues"] == 1


def test_tolerancia_y_texto_con_letras_sueltas_no_son_cambio():
    antes = [_c("nozzles.N1.elevation", 2879.0), _c("nozzles.N1.service", "Gauge H a t ch", "1")]
    despues = [_c("nozzles.N1.elevation", 2879.6), _c("nozzles.N1.service", "Gauge Hatch", "1")]
    assert comparar_candidatos(antes, despues)["changes"] == []


def test_alta_y_baja_de_boquilla_solo_con_la_tabla_en_las_dos():
    antes = [*_tabla("N1"), *_tabla("K5")]
    despues = [*_tabla("N1"), *_tabla("N2")]
    resultado = comparar_candidatos(antes, despues)
    assert _rutas(resultado, "removed") == {"nozzles.K5"}
    assert _rutas(resultado, "added") == {"nozzles.N2"}
    assert resultado["por_id"]["bajas"] == ["K5"]
    assert resultado["por_id"]["altas"] == ["N2"]
    # Sin tabla en rev2 no se puede decir que una boquilla haya desaparecido.
    assert comparar_candidatos(antes, [_c("diameter", 800)])["changes"] == []


def test_un_giro_de_casi_todos_los_rumbos_es_cambio_de_marco():
    antes = [_c(f"nozzles.N{i}.bearing", r, "deg") for i, r in enumerate((0, 90, 180, 270), 1)]
    despues = [_c(f"nozzles.N{i}.bearing", r, "deg") for i, r in enumerate((90, 45, 270, 0), 1)]
    resultado = comparar_candidatos(antes, despues)
    assert resultado["changes"] == []
    assert {c["motivo"] for c in resultado["revisar"]} == {"marco_de_rumbos"}
    # Una boquilla que gira sola sí es un cambio.
    despues = [*antes[:3], _c("nozzles.N4.bearing", 315, "deg")]
    assert _rutas(comparar_candidatos(antes, despues)) == {"nozzles.N4.bearing"}


def test_sch_y_cara_con_la_misma_grafia_no_son_cambio():
    antes = [_c("nozzles.N1.schedule", "80", "1"), _c("nozzles.N1.facing", "R.F.", "1")]
    despues = [_c("nozzles.N1.schedule", "Sch.80", "1"), _c("nozzles.N1.facing", "WNRF", "1")]
    resultado = comparar_candidatos(antes, despues)
    assert resultado["changes"] == []
    assert resultado["revisar"] == []
    distinto = comparar_candidatos(
        [_c("nozzles.N1.schedule", "80", "1"), _c("nozzles.N1.facing", "R.F.", "1")],
        [_c("nozzles.N1.schedule", "Sch.40", "1"), _c("nozzles.N1.facing", "FF", "1")],
    )
    assert _rutas(distinto) == {"nozzles.N1.schedule", "nozzles.N1.facing"}


def test_la_raiz_nueva_hereda_los_sufijos():
    antes = [
        *_tabla("N13A", 8),
        *_tabla("N13B", 8),
        _c("nozzles.N13A.service", "Foam", "1"),
        _c("nozzles.N13B.service", "Foam", "1"),
    ]
    despues = [*_tabla("N13", 6), _c("nozzles.N13.service", "Foam", "1")]
    resultado = comparar_candidatos(antes, despues)
    assert _rutas(resultado, "added") == set()
    assert _rutas(resultado, "removed") == set()
    assert resultado["por_id"]["altas"] == []
    assert resultado["por_id"]["bajas"] == []
    assert resultado["por_id"]["cambiados"]["N13A"]["size_nps"] == [8, 6]
    assert resultado["por_id"]["cambiados"]["N13B"]["size_nps"] == [8, 6]
    # Un solo sufijo no se hereda: puede ser un cambio de marca de verdad.
    suelta = comparar_candidatos(_tabla("N13A", 8), _tabla("N13", 6))
    assert _rutas(suelta, "removed") == {"nozzles.N13A"}
    assert _rutas(suelta, "added") == {"nozzles.N13"}


def test_espesor_con_otra_notacion_va_a_revisar():
    antes = [_c("nozzles.V1.schedule", "160", "1"), _c("nozzles.V2.schedule", "SCH 80", "1")]
    despues = [_c("nozzles.V1.schedule", "THK: 15.85", "1"), _c("nozzles.V2.schedule", "160", "1")]
    resultado = comparar_candidatos(antes, despues)
    assert _rutas(resultado) == {"nozzles.V2.schedule"}
    assert [c["path"] for c in resultado["revisar"]] == ["nozzles.V1.schedule"]
    assert _rutas(
        comparar_candidatos(
            [_c("nozzles.V1.schedule", "THK: 12.70", "1")],
            [_c("nozzles.V1.schedule", "THK: 15.85", "1")],
        )
    ) == {"nozzles.V1.schedule"}


def test_schedule_y_cara_con_otra_notacion_no_son_cambio():
    # El GA da «80» y «R.F.»; la HDM, «Sch.80» y la cara junto al tipo de brida («WNRF»).
    antes = [
        _c("nozzles.N1.schedule", "80", "1"),
        _c("nozzles.N1.facing", "R.F.", "1"),
        _c("nozzles.N2.facing", "R.F.", "1"),
        _c("nozzles.N3.facing", "SORF", "1"),
        _c("nozzles.N4.facing", "RF", "1"),
        _c("nozzles.N5.schedule", "SCH 80", "1"),
    ]
    despues = [
        _c("nozzles.N1.schedule", "Sch.80", "1"),
        _c("nozzles.N1.facing", "WNRF", "1"),
        _c("nozzles.N2.facing", "LWNRF", "1"),
        _c("nozzles.N3.facing", "WNRF", "1"),
        _c("nozzles.N4.facing", "RTJ", "1"),
        _c("nozzles.N5.schedule", "Sch.160", "1"),
    ]
    resultado = comparar_candidatos(antes, despues)
    # Cambia el tipo de brida dado en las dos, la cara o el número de schedule.
    assert _rutas(resultado) == {"nozzles.N3.facing", "nozzles.N4.facing", "nozzles.N5.schedule"}
    assert resultado["revisar"] == []


def test_el_lote_escribe_cambios_aunque_no_haya_modelo(tmp_path, monkeypatch):
    for variable in (*lote.CACHES, "TRAZIA_REGISTRO_ENVIOS"):
        monkeypatch.delenv(variable, raising=False)
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    for rev in ("1", "2"):
        (entrada / f"GAD_EJ-V-01_rev{rev}.pdf").write_bytes(b"%PDF-1.4 sintetico")
    proyecciones = {"1": 610.0, "2": 410.0}

    def leer_sin_modelo(documentos, *, revision, **_):
        fuente = Source(document_id="GA-EJ-V-01", page=1, locator='N1 2" 300#', confidence=0.9)
        candidatos = [
            Candidate(path="nozzles.N1.size_nps", value=2.0, unit="in", source=fuente),
            Candidate(
                path="nozzles.N1.projection", value=proyecciones[revision], unit="mm", source=fuente
            ),
        ]
        run = RunInfo(strategy="lectura", providers=[], seconds=0, external_calls=0)
        return pipeline_mod.PipelineResult(
            None, candidatos, [], "Faltan datos explícitos: diameter", run, missing_data=True
        )

    monkeypatch.setattr(pipeline_mod, "process", leer_sin_modelo)
    filas = lote.procesar_carpeta(entrada, tmp_path / "salida", dataset="synthetic")
    assert [f.estado for f in filas] == ["faltan_datos", "faltan_datos"]
    assert filas[1].cambios == 1
    archivo = tmp_path / "salida" / "EJ-V-01" / "cambios_rev1_rev2.json"
    cambios = json.loads(archivo.read_text(encoding="utf-8"))
    assert cambios["nivel"] == "candidatos"
    assert [c["path"] for c in cambios["changes"]] == ["nozzles.N1.projection"]


def test_completar_anade_lo_leido_que_el_modelo_no_tiene():
    from trazia.lectura.cambios import completar

    altura = {"path": "height", "operation": "modified", "affects_geometry": True}
    peso = {"path": "attributes.weight_full", "operation": "removed"}
    modelo = {
        "changes": [altura, peso],
        "por_id": {
            "altas": [],
            "bajas": [],
            "cambiados": {},
            "sin_marca": [altura, peso],
            "delta_del_plano": {"N1": "2"},
        },
        "summary": {"changes": 1, "geometry_changes": 1},
    }
    leido = comparar_candidatos(
        [_c("height", 1925.0), *_tabla("D1"), _c("nozzles.D1.projection", 610)],
        [_c("height", 1940.0), *_tabla("D1"), _c("nozzles.D1.projection", 410)],
    )
    resultado = completar(modelo, leido)
    assert [c["path"] for c in resultado["changes"]] == ["height", "nozzles.D1.projection"]
    assert resultado["changes"][1]["nivel"] == "candidatos"
    assert "nivel" not in resultado["changes"][0]
    assert resultado["summary"]["changes"] == 2
    assert resultado["summary"]["changes_from_candidates"] == 1
    assert resultado["summary"]["geometry_changes"] == 2
    assert resultado["por_id"]["sin_marca"] == [altura]
    assert resultado["por_id"]["delta_del_plano"] == {"N1": "2"}
    assert resultado["por_id"]["cambiados"]["D1"]["projection"] == [610, 410]
    assert [c["path"] for c in resultado["revisar"]] == ["attributes.weight_full"]
    assert modelo["por_id"]["sin_marca"] == [altura, peso]


def test_el_cambio_de_una_union_deducida_es_derivado():
    antes = [_c("welds.W:SHELL|BODY_FLANGE.elevation_mm", 1925.0)]
    despues = [_c("welds.W:SHELL|BODY_FLANGE.elevation_mm", 1940.0)]
    resultado = comparar_candidatos(antes, despues)
    assert resultado["changes"] == []
    assert [c["path"] for c in resultado["derivados"]] == ["welds.W:SHELL|BODY_FLANGE.elevation_mm"]


def test_completar_conserva_la_revision_con_cita_sin_promoverla_a_cambio():
    from trazia.lectura.cambios import completar

    ruta = "nozzles.M7.schedule"
    pendiente = {"path": ruta, "motivo": "notacion_de_espesor", "source_scope": "nozzle_schedule"}
    leido = {
        "changes": [{"path": ruta}, {"path": "height"}],
        "revisar": [{"path": ruta, "motivo": "notacion_de_espesor"}],
    }
    resultado = completar({"changes": [], "revisar": [pendiente]}, leido)
    assert resultado["revisar"] == [pendiente]
    assert [c["path"] for c in resultado["changes"]] == ["height"]


def test_completar_lleva_la_orientacion_del_modelo_a_revisar_si_cambia_el_marco():
    from trazia.lectura.cambios import completar

    azimut = {"path": "nozzles.A1.azimuth", "operation": "modified", "affects_geometry": True}
    posicion = {"path": "nozzles.A1.position.x", "operation": "modified", "affects_geometry": True}
    proyeccion = {"path": "nozzles.D1.projection", "operation": "modified"}
    modelo = {
        "changes": [azimut, posicion, proyeccion],
        "por_id": {
            "altas": [],
            "bajas": [],
            "cambiados": {
                "A1": {
                    "citas": [],
                    "citas_por_campo": {"azimuth": [], "position.x": []},
                    "azimuth": [90.0, 0.0],
                    "position.x": [0.0, 410.0],
                },
                "D1": {
                    "citas": [],
                    "citas_por_campo": {"projection": []},
                    "projection": [610, 410],
                },
            },
            "sin_marca": [],
            "delta_del_plano": {},
        },
    }
    leido = {
        "changes": [],
        "revisar": [{"path": "nozzles.A1.bearing", "motivo": "marco_de_rumbos"}],
    }
    resultado = completar(modelo, leido)
    assert [c["path"] for c in resultado["changes"]] == ["nozzles.D1.projection"]
    motivos = {c["path"]: c["motivo"] for c in resultado["revisar"]}
    assert motivos["nozzles.A1.azimuth"] == "marco_de_rumbos"
    assert motivos["nozzles.A1.position.x"] == "marco_de_rumbos"
    assert set(resultado["por_id"]["cambiados"]) == {"D1"}


def test_completar_sin_boquillas_leidas_antes_no_da_por_alta_lo_que_no_se_ve():
    from trazia.lectura.cambios import completar

    colocada = {"path": "nozzles.P1.elevation", "operation": "added", "affects_geometry": True}
    nueva = {"path": "nozzles.N9.elevation", "operation": "added", "affects_geometry": True}
    modelo = {
        "changes": [colocada, nueva],
        "por_id": {"altas": ["N9", "P1"], "bajas": [], "cambiados": {}, "sin_marca": []},
    }
    leido = {
        "changes": [{"path": "nozzles.N9", "operation": "added"}],
        "por_id": {"altas": ["N9"]},
        "sin_boquillas": {"antes": True, "despues": False},
    }
    resultado = completar(modelo, leido)
    assert [c["path"] for c in resultado["changes"]] == ["nozzles.N9.elevation", "nozzles.N9"]
    assert resultado["revisar"][0]["motivo"] == "boquilla_sin_alta_ni_baja_en_la_lectura"
    assert resultado["por_id"]["altas"] == ["N9"]

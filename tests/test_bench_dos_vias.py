"""bench.dos_vias con un oro, un marco y un lote inventados: sin datos de TR."""

import json

from bench import dos_vias


def _escribir(path, datos):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(datos), encoding="utf-8")


def _oro(tag, tipo="column"):
    rev = {"equipment_type": tipo, "support": "skirt", "campos": {}, "boquillas": {"N1": {}}}
    return {
        "tag": tag,
        "revisiones": {"rev1": rev, "rev2": {"igual_que": "rev1"}},
        "cambios_rev1_rev2": [],
    }


def _columna(alturas):
    secciones = [
        {"id": f"V{i:02d}", "height": {"value": h, "unit": "mm"}} for i, h in enumerate(alturas, 1)
    ]
    return {
        "equipment": {
            "kind": "column",
            "support": "skirt",
            "column": {"sections": secciones},
            "nozzles": [{"id": "N1", "projection": {"value": 100, "unit": "mm"}}],
        }
    }


def test_tabla_separa_vessels_y_mide_las_tangentes(tmp_path):
    oro, marcos, lote, datos = (tmp_path / n for n in ("oro", "marcos", "lote", "datos"))
    _escribir(oro / "T-1.json", _oro("T-1"))
    _escribir(oro / "T-2.json", _oro("T-2"))
    _escribir(marcos / "T-1.json", {"tag": "T-1", "z_tl_inferior_mm": 80, "z_tl_superior_mm": 3080})
    _escribir(marcos / "T-2.json", {"tag": "T-2", "z_tl_inferior_mm": None})
    # T-1: columna con IFC de TR y modelo en las dos revisiones; rev2 difiere 10 mm.
    _escribir(lote / "T-1" / "rev1" / "revision.json", _columna([1000, 2000]))
    _escribir(lote / "T-1" / "rev2" / "revision.json", _columna([1000, 2010]))
    # T-2: IFC de TR sin modelo nuestro. T-3: sin oro, en mechanical/ con documentos sueltos.
    _escribir(lote / "T-2" / "rev1" / "candidatos.json", [])
    _escribir(
        lote / "resumen.json",
        [
            {"tag": "T-1", "revision": "1", "estado": "ok"},
            {"tag": "T-3", "revision": "0", "estado": "faltan_datos"},
        ],
    )
    for ifc in ("vessels/SET-A/T-1/T-1.ifc", "vessels/SET-A/T-2/T-2.ifc"):
        (datos / ifc).parent.mkdir(parents=True, exist_ok=True)
        (datos / ifc).write_text("ISO-10303-21;", encoding="utf-8")
    (datos / "mechanical").mkdir()
    (datos / "mechanical" / "T-3-GA1-Rev0.pdf").write_bytes(b"%PDF")

    resultado = dos_vias.tabla(lote, oro, marcos, datos, commit="abc1234")
    t1, t2 = resultado["equipos"]
    assert (t1["grupo"], t1["set"]) == ("vessels", "SET-A")
    assert t1["via_1"]["con_modelo"] == 2 and t1["via_1"]["marcas"]["acertadas"] == 2
    assert t1["via_2"]["tangentes_mm"] == {"rev1": 0, "rev2": 10}
    assert t1["via_2"]["texto"] == "entre tangentes 10 mm (2/2 rev)"
    assert t2["via_2"]["estado"] == "sin_modelo"  # antes que el marco sin tangentes
    assert resultado["sin_oro"] == [
        {"tag": "T-3", "grupo": "mechanical", "estados": {"0": "faltan_datos"}}
    ]

    texto = dos_vias.markdown(resultado)
    assert "`abc1234`" in texto and "## `vessels/`" in texto
    assert "el oro no anota cambios" in texto
    assert "| T-3 | mechanical | rev0: faltan_datos |" in texto


def test_sin_ifc_de_tr_no_se_mide_la_via_2(tmp_path):
    medida = dos_vias.via_2("T-9", ["rev1"], tmp_path, tmp_path, ifc_tr=False)
    assert medida == {"estado": "sin_ifc_tr", "texto": "sin IFC de TR"}

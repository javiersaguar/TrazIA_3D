"""Lote local por carpeta: agrupación por tag y revisión, salidas y resumen."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from trazia import lote
from trazia.cli import main

EJEMPLOS = Path(__file__).resolve().parents[1] / "examples" / "documents"


@pytest.fixture(autouse=True)
def _caches_limpias(monkeypatch):
    """El lote fija variables TRAZIA_*: se restauran al acabar cada prueba."""
    for variable in (*lote.CACHES, "TRAZIA_REGISTRO_ENVIOS"):
        monkeypatch.delenv(variable, raising=False)


def _volumen(tmp_path):
    """Imita `/Volumes/<catálogo>/<esquema>/<volumen>/...` con subcarpetas y ruido."""
    entrada = tmp_path / "Volumes" / "indesia" / "ga2model" / "datos" / "lote1"
    (entrada / "planos").mkdir(parents=True)
    (entrada / "listas").mkdir()
    for path in EJEMPLOS.glob("GAD_*.pdf"):
        shutil.copy(path, entrada / "planos" / path.name)
    for path in EJEMPLOS.glob("HDM_*.xlsx"):
        shutil.copy(path, entrada / "listas" / path.name)
    (entrada / "LEEME.txt").write_text("no es un documento del reto", encoding="utf-8")
    (entrada / "planos" / "otro_V-101.pdf").write_bytes(b"%PDF-1.4")
    return entrada


def test_agrupa_por_tag_y_revision_en_orden(tmp_path):
    for nombre in (
        "GAD_P-7_rev10.pdf",
        "GAD_P-7_rev2.pdf",
        "HDM_P-7_rev2.xlsx",
        "VESOR_P-7.pdf",
        "GAD_T 1_revA.pdf",
        "notas.pdf",
    ):
        (tmp_path / nombre).write_bytes(b"x")
    grupos = lote.agrupar(tmp_path)
    assert list(grupos) == ["P-7", "T 1"]
    assert list(grupos["P-7"]) == ["2", "10"]
    assert [d.path.name for d in grupos["P-7"]["2"]] == [
        "GAD_P-7_rev2.pdf",
        "HDM_P-7_rev2.xlsx",
        "VESOR_P-7.pdf",
    ]
    assert [d.document_id for d in grupos["P-7"]["10"]] == ["GA-P-7", "VESOR-P-7"]
    assert grupos["T 1"]["A"][0].document_id == "GA-T-1"


def test_configurar_cache_respeta_variables_fijadas(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAZIA_OCR_CACHE", "/ya/fijada")
    fijadas = lote.configurar_cache(tmp_path)
    assert fijadas["TRAZIA_OCR_CACHE"] == "/ya/fijada"
    assert fijadas["TRAZIA_VISION_CACHE"] == str(tmp_path / "cache" / "vision")
    assert fijadas["TRAZIA_REGISTRO_ENVIOS"] == str(tmp_path / "registro_envios.jsonl")


def test_lote_completo_por_cli(tmp_path):
    entrada, salida = _volumen(tmp_path), tmp_path / "salida"
    codigo = main(
        [
            "lote",
            str(entrada),
            "-o",
            str(salida),
            "--dataset",
            "synthetic",
        ]
    )
    assert codigo == 0
    for etiqueta in ("A", "B"):
        carpeta = salida / "V-101" / f"rev{etiqueta}"
        revision = json.loads((carpeta / "revision.json").read_text(encoding="utf-8"))
        assert revision["revision"] == etiqueta
        assert revision["equipment"]["id"] == "v-101"
        assert revision["run"]["strategy"] == "lectura"
        assert (carpeta / "modelo.ifc").read_text(encoding="utf-8").startswith("ISO-10303-21")
        eventos = json.loads((carpeta / "eventos.json").read_text(encoding="utf-8"))
        assert eventos["error"] is None and eventos["eventos"]
    cambios = json.loads((salida / "V-101" / "cambios_revA_revB.json").read_text("utf-8"))
    assert cambios["changes"]
    por_id = cambios["por_id"]
    assert por_id["altas"] == ["N4"]
    assert "N3" in por_id["cambiados"]
    assert len(por_id["cambiados"]["N3"]["citas"]) >= 2
    assert any(change["path"] == "height" for change in por_id["sin_marca"])
    with (salida / "resumen.csv").open(encoding="utf-8") as handle:
        filas = list(csv.DictReader(handle))
    assert [(f["tag"], f["revision"], f["estado"]) for f in filas] == [
        ("V-101", "A", "ok"),
        ("V-101", "B", "ok"),
    ]
    assert filas[1]["cambios"] == str(len(cambios["changes"]))
    assert not (salida / "_trabajo" / "cache" / "detector").exists()


def test_un_equipo_roto_no_detiene_el_lote(tmp_path):
    (tmp_path / "entrada").mkdir()
    (tmp_path / "entrada" / "GAD_X-1_rev1.pdf").write_bytes(b"no es un pdf")
    filas = lote.procesar_carpeta(tmp_path / "entrada", tmp_path / "salida", dataset="synthetic")
    assert len(filas) == 1 and filas[0].estado == "error" and filas[0].error
    resumen = json.loads((tmp_path / "salida" / "resumen.json").read_text(encoding="utf-8"))
    assert resumen[0]["tag"] == "X-1"
    assert (tmp_path / "salida" / "X-1" / "rev1" / "eventos.json").is_file()
    candidatos = tmp_path / "salida" / "X-1" / "rev1" / "candidatos.json"
    assert json.loads(candidatos.read_text("utf8")) == []


def test_resumen_compartible_no_lleva_datos_del_plano():
    filas = [
        lote.Fila(
            "V-9001",
            "A",
            ["GAD_V-9001_revA.pdf"],
            "ok",
            familia="column",
            lod=2,
            boquillas=5,
            campos=30,
            pendientes=4,
            avisos=1,
            segundos=2.0,
            carpeta="/Volumes/tr/V-9001/revA",
        ),
        lote.Fila(
            "V-9001",
            "B",
            ["GAD_V-9001_revB.pdf"],
            "error",
            error="Falta el diámetro 2400 mm de V-9001",
            segundos=1.0,
        ),
        lote.Fila(
            "P-17",
            "1",
            ["GAD_P-17_rev1.pdf"],
            "error",
            error="ValueError: cota 1250 fuera de rango",
            segundos=3.0,
        ),
        lote.Fila(
            "P-17",
            "2",
            ["GAD_P-17_rev2.pdf"],
            "error",
            error="IFC inválido: IfcCartesianPoint 1250",
            segundos=4.0,
        ),
    ]
    resumen = lote.resumen_compartible(filas)
    texto = json.dumps(resumen, ensure_ascii=False)
    for secreto in ("V-9001", "P-17", "2400", "1250", "GAD_", "/Volumes", "diámetro"):
        assert secreto not in texto
    assert resumen["equipos"] == 2 and resumen["revisiones"] == 4
    assert resumen["estado"] == {"error": 3, "ok": 1}
    assert resumen["errores"] == {"ValueError": 1, "ifc_invalido": 1, "pipeline": 1}
    assert [r["equipo"] for r in resumen["por_revision"]] == ["E01", "E01", "E02", "E02"]
    assert resumen["segundos"] == {"total": 10.0, "mediana": 3.0, "max": 4.0}


def test_lote_mecanico_y_hdm_pdf_sin_lectura(tmp_path):
    entrada = tmp_path / "data"
    entrada.mkdir()
    for nombre, revision in (
        ("BOMBA-GA1-Rev0.pdf", "A"),
        ("BOMBA-GA2-Rev0.pdf", "B"),
        ("COMPRESOR-GA2-Rev1.pdf", "A"),
        ("HDM_BOMBA-GA1.pdf", "A"),
    ):
        shutil.copy(EJEMPLOS / f"GAD_V-101_rev{revision}.pdf", entrada / nombre)
    # La hoja corresponde solo a la bomba GA1 y se conserva aunque repita contenido.
    hdm = entrada / "HDM_BOMBA-GA1.pdf"
    hdm.write_bytes(hdm.read_bytes() + b"\n% hoja sintetica")
    grupos = lote.agrupar(entrada)
    assert list(grupos) == ["BOMBA-GA1", "BOMBA-GA2", "COMPRESOR-GA2"]
    assert [doc.kind for doc in grupos["BOMBA-GA1"]["0"]] == ["GA", "HDM"]
    assert [doc.document_id for doc in grupos["BOMBA-GA1"]["0"]] == [
        "GA-BOMBA-GA1",
        "HDM-BOMBA-GA1",
    ]
    salida = tmp_path / "generated"
    filas = lote.procesar_carpeta(entrada, salida)
    assert [(fila.tag, fila.revision, fila.estado) for fila in filas] == [
        ("BOMBA-GA1", "0", "faltan_datos"),
        ("BOMBA-GA2", "0", "faltan_datos"),
        ("COMPRESOR-GA2", "1", "faltan_datos"),
    ]
    eventos = json.loads((salida / "BOMBA-GA1" / "rev0" / "eventos.json").read_text("utf-8"))
    hdm_event = next(
        event
        for event in eventos["eventos"]
        if event["stage"] == "classify" and event["file"] == "HDM_BOMBA-GA1.pdf"
    )
    assert "hoja de datos mecánicos" in hdm_event["detail"]
    assert (
        len([e for e in eventos["eventos"] if e["stage"] == "ingest" and e["status"] == "ok"]) == 2
    )
    assert not list(salida.rglob("*.ifc"))


def test_hoja_de_datos_del_prefijo_acompana_a_cada_ga(tmp_path):
    entrada = tmp_path / "data"
    entrada.mkdir()
    for nombre in ("BOMBA-GA1-Rev0.pdf", "BOMBA-GA2-Rev0.pdf", "HDM_BOMBA.pdf"):
        shutil.copy(EJEMPLOS / "GAD_V-101_revA.pdf", entrada / nombre)
    grupos = lote.agrupar(entrada)
    # Cada GA<n> es otra máquina: la hoja que solo nombra el prefijo acompaña a las dos.
    assert list(grupos) == ["BOMBA-GA1", "BOMBA-GA2"]
    for tag in ("BOMBA-GA1", "BOMBA-GA2"):
        docs = grupos[tag]["0"]
        assert [doc.document_id for doc in docs] == [f"GA-{tag}", "HDM-BOMBA"]
        assert "común a BOMBA-GA1, BOMBA-GA2" in docs[1].alertas[-1]


def test_sin_lectura_no_se_dicen_cero_cambios(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    entrada = tmp_path / "data"
    entrada.mkdir()
    for revision in ("1", "2"):
        canvas = Canvas(str(entrada / f"GAD_X-1_rev{revision}.pdf"), invariant=1)
        canvas.rect(70, 110, 210, 190)  # solo dibujo: nada que leer salvo el nombre
        canvas.showPage()
        canvas.save()
    salida = tmp_path / "generated"
    filas = lote.procesar_carpeta(entrada, salida)
    assert [fila.cambios for fila in filas] == [None, None]
    assert not list(salida.rglob("cambios_*.json"))
    assert lote.SIN_LECTURA.format("1", "2") in filas[1].avisos_documentos


def test_rechaza_un_dataset_desconocido(tmp_path):
    with pytest.raises(ValueError, match="sintetico"):
        lote.procesar_carpeta(EJEMPLOS, tmp_path / "salida", dataset="sintetico")
    assert not (tmp_path / "salida").exists()


def test_un_documento_que_no_se_lee_no_pasa_en_silencio(tmp_path, capsys):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    shutil.copy(EJEMPLOS / "GAD_V-101_revA.pdf", entrada / "GAD_V-101_revA.pdf")
    shutil.copy(EJEMPLOS / "HDM_V-101_revA.xlsx", entrada / "HDM_V-101_revA.xlsx")
    (entrada / "VESOR_V-101.pdf").write_bytes(b"no es un pdf")
    salida = tmp_path / "salida"
    codigo = main(["lote", str(entrada), "--output", str(salida), "--dataset", "synthetic"])
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert [(f["estado"], f["documentos_con_error"]) for f in resumen] == [
        ("ok", ["VESOR_V-101.pdf"])
    ]
    assert "Aviso: V-101 revA siguió sin VESOR_V-101.pdf" in capsys.readouterr().out
    assert codigo == 1
    with (salida / "resumen.csv").open(encoding="utf-8") as handle:
        assert next(csv.DictReader(handle))["documentos_con_error"] == "VESOR_V-101.pdf"
    compartible = lote.resumen_compartible([lote.Fila(**fila) for fila in resumen])
    assert compartible["con_documentos_con_error"] == 1
    assert compartible["por_revision"][0]["documentos_con_error"] == 1
    assert "VESOR" not in json.dumps(compartible)


def test_sin_ninguna_cota_la_familia_queda_como_no_reconocida():
    assert not lote._hay_geometria([{"path": "tag"}, {"path": "attributes.service"}])
    assert lote._hay_geometria([{"path": "tag"}, {"path": "diameter"}])
    error = f"{lote.FAMILIA_NO_RECONOCIDA} {lote.SIN_FAMILIA}"
    assert lote._tipo_error(error) == "familia_no_reconocida"
    assert "diameter" not in error and "skirt" not in error
    assert lote._hay_tipo([{"path": "tag"}, {"path": "attributes.equipment_type"}])
    assert lote._tipo_error("Faltan datos explícitos: diameter") == "faltan_datos"

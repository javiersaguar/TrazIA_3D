"""Herramientas del evento: cifras del pitch, sintéticos por perfil y triaje."""

import importlib
import json
from pathlib import Path

import pytest

from bench import cifras as modulo_cifras
from bench.triaje import informe, peticiones, triar
from synthetic.desde_perfil import generar_parecido, plan
from synthetic.vendors import VENDORS

RAIZ = Path(__file__).resolve().parents[1]


def _perfil(**cambios) -> dict:
    perfil = {
        "archivos": {"total": 20},
        "equipos": {
            "total": 10,
            "revisiones_por_equipo": {"1": 4, "2": 5, "3": 1},
            "documentos_por_tipo": {"GA": 16, "HDM": 8, "VESOR": 2},
            "combinaciones_de_tipos": {"GA+HDM": 6, "GA": 4},
        },
        "pdf": {
            "documentos": 18,
            "clase": {"vectorial": 10, "escaneado": 8},
            "paginas_por_documento": {"n": 18, "min": 1, "mediana": 1, "max": 6},
            "formato_de_pagina": {"A3": 12, "A1": 6},
            "rotacion_declarada": {"0": 15, "90": 3},
            "con_texto_girado": 2,
        },
        "ifc": {"archivos": 3},
        "imagenes": {"documentos": 0},
        "contenido": {
            "documentos_con_texto": 10,
            "documentos_con_patron": {"unidad_pulgadas": 3, "coma_decimal": 4, "nps": 3},
            "idioma": {"es": 4, "en": 3},
        },
    }
    for clave, valor in cambios.items():
        perfil[clave] = valor
    return perfil


def test_plan_sigue_la_mezcla_del_perfil_y_nunca_usa_reservados():
    p = plan(_perfil())
    assert p["casos"] == 10
    assert not any(VENDORS[v].reserved for v in p["proveedores"])
    imperial = [v for v in p["proveedores"] if VENDORS[v].length_unit != "mm"]
    espanol = [v for v in p["proveedores"] if VENDORS[v].lang == "es"]
    assert len(imperial) == 3 and len(espanol) == 4
    assert p["degradaciones"] == ["vectorial", "escaneado_limpio", "escaneado_pobre"]
    assert p["sin_hoja_de_datos_cada"] == 2  # 4 de 10 equipos sin HDM
    assert p["paquete_cada"] == 4
    huecos = "\n".join(p["huecos"])
    assert "giradas" in huecos and "A1" in huecos and "más de dos revisiones" in huecos
    assert "VESOR" in huecos


def test_plan_sin_texto_usa_todos_los_publicos():
    contenido = {"documentos_con_texto": 0, "documentos_con_patron": {}, "idioma": {}}
    p = plan(_perfil(contenido=contenido), casos=3)
    assert p["casos"] == 3 and len(p["proveedores"]) == 6


def test_generar_parecido_escribe_el_conjunto_y_el_plan(tmp_path):
    resultado = generar_parecido(_perfil(), tmp_path, casos=2)
    raiz = Path(resultado["carpeta"])
    assert json.loads((raiz / "plan.json").read_text(encoding="utf-8"))["casos"] == 2
    manifest = json.loads((raiz / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True and len(manifest["cases"]) == 2


def _lote(tmp_path) -> Path:
    filas = []
    for tag, rev, error, etapa in [
        ("V-101", "A", None, None),
        ("V-101", "B", "IFC inválido: falta la virola de 1200 mm", None),
        ("P-2001A", "1", "ValueError: no se lee 3/4 in", "extract_tables"),
        ("C-300", "1", "ValueError: otra cosa", "extract_tables"),
    ]:
        filas.append(
            {
                "tag": tag,
                "revision": rev,
                "documentos": [f"GAD_{tag}_rev{rev}.pdf"],
                "estado": "error" if error else "ok",
                "error": error,
                "segundos": 1.0,
                "carpeta": "/Volumes/no/existe",
            }
        )
        eventos = [{"stage": "ingest", "status": "ok", "file": "x", "detail": "secreto"}]
        if etapa:
            eventos.append({"stage": etapa, "status": "error", "file": "x", "detail": "3/4 in"})
        eventos.append({"stage": "memory", "status": "omitido", "file": "", "detail": ""})
        carpeta = tmp_path / tag / f"rev{rev}"
        carpeta.mkdir(parents=True)
        (carpeta / "eventos.json").write_text(
            json.dumps({"eventos": eventos, "avisos": ["V-101 aviso"], "error": error}),
            encoding="utf-8",
        )
    (tmp_path / "resumen.json").write_text(json.dumps(filas), encoding="utf-8")
    return tmp_path


def test_triaje_agrupa_por_categoria_y_etapa_sin_datos_del_plano(tmp_path):
    triaje = triar(_lote(tmp_path))
    assert triaje["revisiones"] == 4 and triaje["equipos"] == 3 and triaje["fallidas"] == 3
    assert triaje["etapas_con_error"] == {"extract_tables": 2}
    assert triaje["etapas_omitidas"] == {"memory": 4}
    primero, segundo = triaje["problemas"]
    assert (primero["categoria"], primero["etapa"], primero["revisiones"]) == (
        "ValueError",
        "extract_tables",
        2,
    )
    assert primero["casos"] == ["E02/3", "E03/4"]
    assert (segundo["categoria"], segundo["etapa"]) == ("ifc_invalido", "ifc")
    texto = json.dumps(triaje) + informe(triaje) + "".join(peticiones(triaje))
    for prohibido in ("V-101", "P-2001A", "3/4 in", "1200", "secreto", "GAD_", "Volumes"):
        assert prohibido not in texto
    assert "2 de 4 revisiones fallan con la categoría ValueError" in peticiones(triaje)[0]


def test_triaje_sin_fallos(tmp_path):
    (tmp_path / "resumen.json").write_text(
        json.dumps([{"tag": "V-1", "revision": "1", "estado": "ok", "error": None}]),
        encoding="utf-8",
    )
    assert "Sin fallos" in informe(triar(tmp_path))


def test_cifras_del_evento_al_pitch_y_al_guion(tmp_path):
    filas = [
        {"tag": "V-101", "revision": "A", "documentos": [], "estado": "ok", "segundos": 2.0},
        {"tag": "V-101", "revision": "B", "documentos": [], "estado": "error", "segundos": 4.0},
    ]
    cifras = modulo_cifras.cifras_evento(_perfil(), filas, None)
    assert cifras["datos"]["equipos"] == 10
    assert cifras["datos"]["revisiones"] == 4 + 10 + 3
    assert cifras["lote"] == {
        "equipos": 1,
        "revisiones": 2,
        "correctas": 1,
        "errores": 1,
        "segundos_total": 6.0,
        "segundos_mediana": 4.0,
    }
    assert "V-101" not in json.dumps(cifras)
    (tmp_path / "pitch").mkdir(parents=True)
    pitch, guion = modulo_cifras.aplicar(cifras, tmp_path, minutos_revision=12)
    modulo = pitch.read_text(encoding="utf-8")
    assert modulo.startswith("// Generado") and '"correctas": 1' in modulo
    frases = guion.read_text(encoding="utf-8")
    assert "10 equipos y 17 revisiones" in frases
    assert "No tenemos aún la cifra contra los modelos de TR" in frases
    assert "baja a 320" in frases  # 1600 revisiones × 12 min


def _dos_vias() -> dict:
    via_1 = {"marcas": {"oro": 4, "leidas": 3, "acertadas": 3}}
    return {
        "commit": "abc1234",
        "lote": "lote_a3",
        "equipos": [
            {
                "tag": "BF-C-0003",
                "via_1": via_1,
                "via_2": {
                    "estado": "medido",
                    "tangentes_mm": {"rev1": 0.0, "rev2": 12.0},
                    "texto": "entre tangentes 12 mm",
                },
            },
            {"tag": "80V01", "via_1": via_1, "via_2": {"estado": "sin_ifc_tr"}},
        ],
        "agregado": {
            "revisiones": 4,
            "con_modelo": 3,
            "ifc_validos": 3,
            "marcas": {"oro": 8, "leidas": 6, "acertadas": 6},
            "nps": {"ok": 5, "evaluables": 6},
            "boquillas_colocadas": {"colocadas": 2, "leidas": 6},
            "cambios": {
                "evaluables": 10,
                "acertados": 7,
                "a_revision": 1,
                "faltantes": 2,
                "falsos": 1,
            },
            "soldaduras": {"oro": 9, "encontradas": 5, "leidas": 7, "falsas": 1, "sin_oro": 0},
        },
    }


def test_cifras_del_oro_solo_agregados_y_sin_tocar_el_lote(tmp_path):
    oro = modulo_cifras.cifras_oro(_dos_vias())
    assert oro["cambios"] == {"acertados": 7, "evaluables": 10, "falsos": 1, "a_revision": 1}
    assert oro["via_2"] == {"equipos": 1, "error_tangentes_mm_max": 12.0}
    assert "BF-C-0003" not in json.dumps(oro) and "80V01" not in json.dumps(oro)
    (tmp_path / "pitch").mkdir(parents=True)
    lote = {"equipos": 2, "revisiones": 4, "correctas": 3, "errores": 0}
    cifras = {
        "fecha": "2026-11-26",
        "dataset": "real",
        "datos": None,
        "lote": lote,
        "evaluacion": None,
    }
    modulo_cifras.aplicar(cifras, tmp_path, minutos_revision=None)
    _, guion = modulo_cifras.aplicar_oro(_dos_vias(), tmp_path)
    aplicadas = modulo_cifras.leer_aplicadas(tmp_path)
    assert aplicadas["lote"] == lote and aplicadas["oro"]["soldaduras"]["encontradas"] == 5
    assert "acertamos 7 de 10 cambios entre revisiones, con 1 falso" in guion.read_text(
        encoding="utf-8"
    )


def test_cifras_de_la_aprobacion_automatica_sin_tags(tmp_path):
    resultado = {
        "lote": "lote_x",
        "umbral_api": 0.8,
        "juzgados": {"n": 170, "aciertos": 160, "precision": 0.94},
        "por_equipo": {"BF-C-0003": {"n": 4}, "80V01": {"n": 6}},
        "aprobacion_automatica": {
            "0.8": {"n": 102, "aciertos": 100, "resto": {"n": 68, "aciertos": 60}}
        },
    }
    (tmp_path / "pitch").mkdir(parents=True)
    lote = {"equipos": 2, "revisiones": 4, "correctas": 3, "errores": 0}
    cifras = {"fecha": "2026-11-26", "dataset": "real", "datos": None, "lote": lote}
    modulo_cifras.aplicar(cifras, tmp_path, minutos_revision=None)
    modulo_cifras.aplicar_aprobacion(resultado, tmp_path)
    aplicadas = modulo_cifras.leer_aplicadas(tmp_path)
    assert aplicadas["lote"] == lote
    assert aplicadas["aprobacion"] == {
        "lote": "lote_x",
        "umbral": 0.8,
        "equipos": 2,
        "juzgados": 170,
        "aprobados_solos": 102,
        "aciertos": 100,
        "resto": {"n": 68, "aciertos": 60},
    }
    assert "BF-C-0003" not in json.dumps(aplicadas)


def test_frases_con_evaluacion_y_sin_tiempo():
    cifras = {
        "fecha": "2026-11-26",
        "dataset": "real",
        "datos": None,
        "evaluacion": {
            "equipos": 5,
            "error_relativo_diametro": 0.012,
            "boquillas_recall": 0.8,
            "error_posicion_mm": 35.0,
            "chamfer_mm": 20.0,
            "convenio_por_exclusion": True,
        },
    }
    frases = modulo_cifras.frases_guion(cifras)
    assert "error medio del 1,2 %" in frases and "8,0 de cada diez" in frases
    assert "convenio ajustado" not in frases
    assert "no se dice la frase del ahorro" in frases


def _repo_con_origen(tmp_path) -> Path:
    import subprocess

    def git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    origen, repo = tmp_path / "origen.git", tmp_path / "repo"
    git("init", "--bare", "-b", "main", str(origen), cwd=tmp_path)
    git("init", "-b", "main", str(repo), cwd=tmp_path)
    for clave, valor in (("user.name", "Equipo"), ("user.email", "equipo@example.com")):
        git("config", clave, valor, cwd=repo)
    git("config", "core.hooksPath", "/dev/null", cwd=repo)
    texto = (
        "# Trabajo previo al evento · BORRADOR\n\n"
        "El tag todavía no se crea.\n\n"
        "- Fecha/hora de corte: pendiente.\n"
        "- Commit exacto de la base: pendiente.\n"
        "- Tag publicado: pendiente.\n"
        "- Declaración entregada a la organización: pendiente.\n"
    )
    (repo / "PREVIOUS_WORK.md").write_text(texto, encoding="utf-8", newline="\n")
    git("add", ".", cwd=repo)
    git("commit", "-m", "Base", cwd=repo)
    git("remote", "add", "origin", str(origen), cwd=repo)
    git("push", "-u", "origin", "main", cwd=repo)
    return repo


def _script(monkeypatch, nombre, repo):
    monkeypatch.syspath_prepend(str(RAIZ / "scripts"))
    modulo = importlib.import_module(nombre)
    monkeypatch.setattr(modulo, "RAIZ", repo)
    if hasattr(modulo, "REGISTRO"):
        monkeypatch.setattr(modulo, "REGISTRO", repo / "PREVIOUS_WORK.md")
    return modulo


def test_arranque_cierra_el_registro_y_etiqueta_la_base(monkeypatch, tmp_path, capsys):
    import subprocess

    repo = _repo_con_origen(tmp_path)
    arranque = _script(monkeypatch, "arranque_evento", repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert arranque.main([]) == 0  # ensayo: no cambia nada
    assert "pendiente" in (repo / "PREVIOUS_WORK.md").read_text(encoding="utf-8")
    assert arranque.main(["--aplicar", "--push"]) == 0
    texto = (repo / "PREVIOUS_WORK.md").read_text(encoding="utf-8")
    assert f"- Commit exacto de la base: `{base}`." in texto
    assert "- Declaración entregada a la organización: pendiente." in texto
    etiquetado = subprocess.run(
        ["git", "rev-list", "-n", "1", "pre-hackathon-baseline"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert etiquetado == base
    remoto = subprocess.run(
        ["git", "ls-remote", "--tags", "origin"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "pre-hackathon-baseline" in remoto
    with pytest.raises(SystemExit, match="ya existe"):
        arranque.main(["--aplicar"])

    entrega = _script(monkeypatch, "entrega", repo)
    informe = entrega.Informe()
    entrega.comprobar_git(informe)
    entrega.comprobar_registro(informe)
    salida = capsys.readouterr().out
    assert "✓ Tag en origin" in salida and "✓ main = origin/main" in salida
    assert "Declaración entregada a la organización: pendiente" in salida
    assert informe.fallos == 1  # solo la declaración, que rellena una persona


def test_entrega_detecta_coautores_y_correos_ajenos(monkeypatch, tmp_path, capsys):
    import subprocess

    repo = _repo_con_origen(tmp_path)
    (repo / ".github").mkdir()
    (repo / ".github" / "autores.txt").write_text("equipo@example.com\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    firma = "Co-" + "Authored-By: Alguien <a@b.c>"
    subprocess.run(["git", "commit", "-m", f"Cambio\n\n{firma}"], cwd=repo, check=True)
    entrega = _script(monkeypatch, "entrega", repo)
    informe = entrega.Informe()
    entrega.comprobar_autoria(informe)
    salida = capsys.readouterr().out
    assert "✓ Autores" in salida and "✗ Commits con coautor o firma" in salida


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.syspath_prepend(str(RAIZ / "scripts"))
    return importlib.import_module("demo")


def test_reiniciar_demo_restaura_la_api_sin_borrar_ni_tocar_lo_privado(demo, tmp_path):
    datos, inicial, apartado = tmp_path / "data", tmp_path / "inicial", tmp_path / "apartado"
    (datos / "store" / "rev").mkdir(parents=True)
    (datos / "store" / "rev" / "a.json").write_text("inicial", encoding="utf-8")
    (datos / "trazia.sqlite3").write_text("base inicial", encoding="utf-8")
    for intocable in ("private/plano.pdf", "cache/vision.json"):
        (datos / intocable).parent.mkdir(parents=True, exist_ok=True)
        (datos / intocable).write_text("no tocar", encoding="utf-8")

    assert demo.reiniciar_api(datos, inicial, apartado) is None  # sin inicial, no hace nada
    assert demo.guardar_inicial(datos, inicial) == ["trazia.sqlite3", "store"]
    assert not (inicial / "private").exists() and not (inicial / "cache").exists()

    # Se usa la demo: cambia la base y aparece una revisión nueva
    (datos / "trazia.sqlite3").write_text("base usada", encoding="utf-8")
    (datos / "store" / "rev" / "b.json").write_text("nueva", encoding="utf-8")
    copia = demo.reiniciar_api(datos, inicial, apartado)

    assert (datos / "trazia.sqlite3").read_text(encoding="utf-8") == "base inicial"
    assert sorted(p.name for p in (datos / "store" / "rev").iterdir()) == ["a.json"]
    assert (copia / "trazia.sqlite3").read_text(encoding="utf-8") == "base usada"
    assert (copia / "store" / "rev" / "b.json").is_file()  # lo anterior se aparta, no se borra
    for intocable in ("private/plano.pdf", "cache/vision.json"):
        assert (datos / intocable).read_text(encoding="utf-8") == "no tocar"


def test_guardar_inicial_sin_estado_de_la_api_avisa(demo, tmp_path):
    with pytest.raises(SystemExit, match="arranca la demo"):
        demo.guardar_inicial(tmp_path / "vacio", tmp_path / "inicial")


def test_entrega_detecta_documentos_de_tr_y_nombres_ajenos(monkeypatch, tmp_path, capsys):
    import subprocess

    repo = _repo_con_origen(tmp_path)
    (repo / ".github").mkdir()
    (repo / ".github" / "autores.txt").write_text("equipo@example.com\n", encoding="utf-8")
    (repo / "examples").mkdir()
    (repo / "examples" / "GAD_EJ-01_revA.pdf").write_bytes(b"%PDF-sintetico")
    (repo / "docs").mkdir()
    (repo / "docs" / "plano.pdf").write_bytes(b"%PDF-1.7")
    subprocess.run(["git", "add", "-f", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "Planos"], cwd=repo, check=True)
    entrega = _script(monkeypatch, "entrega", repo)
    informe = entrega.Informe()
    entrega.comprobar_datos(informe)
    entrega.comprobar_autoria(informe)
    salida = capsys.readouterr().out
    assert "✗ Documentos versionados sin permiso: docs/plano.pdf" in salida
    assert "examples" not in salida.split("sin permiso:")[1].splitlines()[0]
    assert "! Nombres de autor que no son del equipo: Equipo" in salida

    (repo / ".guardian-permitidos").write_text("docs/\n", encoding="utf-8")
    informe = entrega.Informe()
    entrega.comprobar_datos(informe)
    salida = capsys.readouterr().out
    assert informe.fallos == 0
    assert "! 1 documentos fuera de examples/ admitidos por .guardian-permitidos (docs)" in salida


def test_entrega_exige_tag_y_commit_en_el_registro(monkeypatch, tmp_path, capsys):
    repo = _repo_con_origen(tmp_path)
    registro = repo / "PREVIOUS_WORK.md"
    registro.write_text("# Trabajo previo\n\n- Etiqueta: `pre-hackathon-baseline`.\n", "utf-8")
    entrega = _script(monkeypatch, "entrega", repo)
    informe = entrega.Informe()
    entrega.comprobar_registro(informe)
    assert informe.fallos == 1 and "no cita el tag" in capsys.readouterr().out
    registro.write_text(registro.read_text("utf-8") + "- Commit: `" + "a" * 40 + "`.\n", "utf-8")
    informe = entrega.Informe()
    entrega.comprobar_registro(informe)
    assert informe.fallos == 0

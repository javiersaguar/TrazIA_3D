"""Tabla de cifras por equipo con las dos vías de medida (A3, punto de control 4).

    python -m bench.dos_vias <salida_del_lote> [--datos data/Dataset-tecnicasreunidas]
        [--oro eval/verdad] [--marcos eval/marcos] [--commit <hash>] [--salida generated/a3]

- **Vía 1**: `bench.oro` contra el oro de planos, agrupado por equipo. Cada cifra lleva su
  denominador: revisiones, marcas, campos o cambios.
- **Vía 2**: frente al IFC de TR. Hoy solo se mide la distancia entre tangentes de las columnas:
  la suma de los tramos del modelo frente a las tangentes del marco (`eval/marcos/<TAG>.json`,
  sacadas del IFC de TR). El lector genérico `bench.referencia` no sirve para estas columnas: la
  envolvente incluye las plataformas.

Las cifras de `vessels/`, que tienen oro con revisión exhaustiva, van separadas de las del resto
del dataset, que no tiene oro y solo da el estado del lote.

La salida va a `generated/`, que Git ignora. La tabla solo lleva recuentos y errores, sin valores
de los planos.
"""

import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from . import oro as bench_oro


def _mediana(filas, clave):
    valores = [f[clave] for f in filas if f.get(clave) is not None]
    return (statistics.median(valores) if valores else None), len(valores)


def _suma(filas, clave):
    return sum(f.get(clave) or 0 for f in filas)


def _fraccion(x, n) -> str:
    return f"{x}/{n}" if n else "—"


def _con_n(texto: str, n: int) -> str:
    return "—" if not n else f"{texto} ({n})"


def _tramos_del_modelo(carpeta: Path) -> float | None:
    """Suma de las alturas de `column.sections` del modelo, o None si no hay modelo de columna."""
    path = carpeta / "revision.json"
    if not path.exists():
        return None
    equipo = json.loads(path.read_text(encoding="utf-8")).get("equipment", {})
    tramos = (equipo.get("column") or {}).get("sections") or []
    alturas = [bench_oro._numero((t.get("height") or {}).get("value")) for t in tramos]
    if not alturas or any(a is None for a in alturas):
        return None
    return sum(alturas)


def via_2(tag: str, revisiones: list[str], lote: Path, marcos: Path, ifc_tr: bool) -> dict:
    """Distancia entre tangentes del modelo frente al marco tomado del IFC de TR."""
    if not ifc_tr:
        return {"estado": "sin_ifc_tr", "texto": "sin IFC de TR"}
    marco_path = marcos / f"{tag}.json"
    if not marco_path.exists():
        return {"estado": "sin_marco", "texto": "IFC de TR sin marco en eval/marcos"}
    tramos = {
        etiqueta: valor
        for etiqueta in revisiones
        if (valor := _tramos_del_modelo(lote / tag / etiqueta)) is not None
    }
    if not tramos:
        return {"estado": "sin_modelo", "texto": "IFC de TR, sin modelo nuestro con que comparar"}
    marco = json.loads(marco_path.read_text(encoding="utf-8"))
    inferior, superior = marco.get("z_tl_inferior_mm"), marco.get("z_tl_superior_mm")
    if inferior is None or superior is None:
        return {"estado": "sin_tangentes", "texto": "el marco no da las tangentes"}
    diferencias = {
        etiqueta: abs(valor - (superior - inferior)) for etiqueta, valor in tramos.items()
    }
    peor = max(diferencias.values())
    return {
        "estado": "medido",
        "tangentes_mm": diferencias,
        "texto": f"entre tangentes {peor:.0f} mm ({len(diferencias)}/{len(revisiones)} rev)",
    }


def resumen_equipo(filas: list[dict], cambios: dict) -> dict:
    """Cifras de la vía 1 de un equipo, con sus denominadores."""
    n = len(filas)
    diametro, n_diametro = _mediana(filas, "error_diametro")
    longitud, n_longitud = _mediana(filas, "error_longitud")
    elevacion, n_elevacion = _mediana(filas, "error_elevacion_mm")
    azimut, n_azimut = _mediana(filas, "error_azimut_deg")
    con_modelo = [f for f in filas if f["modelo"]]
    return {
        "revisiones": n,
        "con_modelo": len(con_modelo),
        "ifc_validos": sum(f["ifc_valido"] for f in filas),
        "tipo_ok": sum(f["tipo_ok"] for f in filas),
        "soporte_ok": sum(f["soporte_ok"] for f in filas),
        "error_diametro": {"mediana": diametro, "n": n_diametro},
        "error_longitud": {"mediana": longitud, "n": n_longitud},
        "marcas": {k: _suma(filas, f"marcas_{k}") for k in ("oro", "leidas", "acertadas")},
        "nps": {"ok": _suma(filas, "nps_ok"), "evaluables": _suma(filas, "nps_evaluables")},
        "rating": {
            "ok": _suma(filas, "rating_ok"),
            "evaluables": _suma(filas, "rating_evaluables"),
        },
        "colocadas": {
            "colocadas": sum(f["boquillas_colocadas"] or 0 for f in con_modelo),
            "leidas": sum(f["marcas_leidas"] for f in con_modelo),
        },
        "error_elevacion_mm": {"mediana": elevacion, "n": n_elevacion},
        "error_azimut_deg": {"mediana": azimut, "n": n_azimut},
        "piezas": {k: _suma(filas, f"piezas_{k}") for k in ("oro", "presentes")},
        "soldaduras": {
            k: _suma(filas, f"soldaduras_{k}")
            for k in ("oro", "encontradas", "leidas", "falsas", "sin_oro")
        },
        "cambios": cambios,
    }


def _carpeta_del_tag(datos: Path | None, tag: str) -> Path | None:
    """Carpeta del equipo, o la de sus documentos sueltos (`mechanical/BOMBA-GA1-Rev0.pdf`)."""
    if datos is None or not datos.exists():
        return None
    carpeta = next((p for p in datos.rglob(tag) if p.is_dir()), None)
    if carpeta is None:
        suelto = next((p for p in sorted(datos.rglob(f"{tag}[-_]*")) if p.is_file()), None)
        carpeta = suelto.parent if suelto is not None else None
    return carpeta


def _grupo(datos: Path | None, carpeta: Path | None) -> str | None:
    return carpeta.relative_to(datos).parts[0] if carpeta is not None and carpeta != datos else None


def _estados_del_lote(lote: Path) -> dict[str, list[dict]]:
    path = lote / "resumen.json"
    if not path.exists():
        return {}
    datos = json.loads(path.read_text(encoding="utf-8"))
    filas = datos.get("filas", datos) if isinstance(datos, dict) else datos
    por_tag: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        por_tag[fila["tag"]].append(fila)
    return por_tag


def tabla(
    lote: Path,
    carpeta_oro: Path,
    marcos: Path,
    datos: Path | None = None,
    commit: str | None = None,
) -> dict:
    lote = Path(lote)
    informe = bench_oro.evaluar(lote, carpeta_oro)
    por_tag: dict[str, list[dict]] = defaultdict(list)
    for fila in informe["filas"]:
        por_tag[fila["tag"]].append(fila)
    equipos = []
    for tag, filas in sorted(por_tag.items()):
        carpeta = _carpeta_del_tag(datos, tag)
        ifc_tr = carpeta is not None and any(carpeta.glob("*.ifc"))
        grupo = _grupo(datos, carpeta)
        equipos.append(
            {
                "tag": tag,
                "grupo": grupo,
                "set": carpeta.parent.name if carpeta is not None else None,
                "via_1": resumen_equipo(filas, informe["cambios"][tag]),
                "via_2": via_2(tag, [f["revision"] for f in filas], lote, marcos, ifc_tr),
            }
        )
    sin_oro = [
        {
            "tag": tag,
            "grupo": _grupo(datos, _carpeta_del_tag(datos, tag)),
            "estados": {str(f["revision"]): f["estado"] for f in filas},
        }
        for tag, filas in sorted(_estados_del_lote(lote).items())
        if tag not in por_tag
    ]
    return {
        "commit": commit,
        "lote": lote.name,
        "equipos": equipos,
        "agregado": informe["agregado"],
        "sin_oro": sin_oro,
    }


def _med(v: dict, clave: str, formato) -> str:
    return _con_n(formato(v[clave]["mediana"]), v[clave]["n"])


def _cambios(c: dict) -> str:
    falsos = "sin comparación" if c["falsos"] is None else f"{c['falsos']} falsos"
    if not c["evaluables"]:
        return f"el oro no anota cambios; {falsos}"
    return (
        f"{c['acertados']}/{c['evaluables']}, {c['a_revision']} a revisión, "
        f"{c['faltantes']} faltantes, {falsos}"
    )


def _fila_markdown(e: dict) -> str:
    v = e["via_1"]
    c, s = v["cambios"], v["soldaduras"]
    soldaduras = (
        f"{s['encontradas']}/{s['oro']}, {s['falsas']} falsas"
        if s["oro"] or s["leidas"] - s["sin_oro"]
        else (f"{s['sin_oro']} sin oro" if s["sin_oro"] else "—")
    )
    return (
        f"| {e['tag']} | {e['set'] or '—'} "
        f"| {v['con_modelo']}/{v['revisiones']} · {v['ifc_validos']}/{v['revisiones']} "
        f"| {v['tipo_ok']}/{v['revisiones']} · {v['soporte_ok']}/{v['revisiones']} "
        f"| {_med(v, 'error_diametro', bench_oro._err)} "
        f"| {_med(v, 'error_longitud', bench_oro._err)} "
        f"| {_fraccion(v['marcas']['acertadas'], v['marcas']['oro'])} "
        f"| {_fraccion(v['marcas']['acertadas'], v['marcas']['leidas'])} "
        f"| {_fraccion(v['nps']['ok'], v['nps']['evaluables'])} "
        f"| {_fraccion(v['rating']['ok'], v['rating']['evaluables'])} "
        f"| {_fraccion(v['colocadas']['colocadas'], v['colocadas']['leidas'])} "
        f"| {_med(v, 'error_elevacion_mm', bench_oro._mm)} "
        f"| {_med(v, 'error_azimut_deg', bench_oro._grados)} "
        f"| {_fraccion(v['piezas']['presentes'], v['piezas']['oro'])} "
        f"| {soldaduras} "
        f"| {_cambios(c)} "
        f"| {e['via_2']['texto']} |"
    )


def markdown(resultado: dict) -> str:
    cabecera = [
        "| Equipo | Set | Modelo · IFC | Tipo · soporte | Err. Ø | Err. L | Marcas | Precisión "
        "| NPS | Rating | Colocadas | Elevación | Azimut | Piezas | Soldaduras | Cambios rev1→rev2 "
        "| Vía 2 (IFC de TR) |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
        "| ---: | --- | --- | --- |",
    ]
    vessels = [e for e in resultado["equipos"] if e["grupo"] in (None, "vessels")]
    otros_con_oro = [e for e in resultado["equipos"] if e["grupo"] not in (None, "vessels")]
    a = resultado["agregado"]
    lineas = [
        "# Cifras por equipo, vía 1 y vía 2",
        "",
        f"Código: `{resultado['commit'] or 'sin hash'}`. Lote: `{resultado['lote']}`. "
        f"{a['revisiones']} revisiones de {len(resultado['equipos'])} equipos con oro.",
        "",
        "Entre paréntesis, las revisiones con medida. «Marcas» es el recall frente al oro y "
        "«Precisión», el acierto sobre lo leído. «Colocadas» son las boquillas con posición "
        "frente a las leídas en las revisiones con modelo.",
        "",
        "## `vessels/`, con oro de revisión exhaustiva",
        "",
        *cabecera,
        *[_fila_markdown(e) for e in vessels],
        "",
        f"Total: modelo {a['con_modelo']}/{a['revisiones']}, IFC válidos "
        f"{a['ifc_validos']}/{a['revisiones']}, marcas {a['marcas']['acertadas']}/"
        f"{a['marcas']['oro']}, NPS {a['nps']['ok']}/{a['nps']['evaluables']}, cambios "
        f"{a['cambios']['acertados']}/{a['cambios']['evaluables']} ({a['cambios']['a_revision']} "
        f"a revisión, {a['cambios']['faltantes']} faltantes, {a['cambios']['falsos']} falsos), "
        f"piezas {a['piezas']['presentes']}/{a['piezas']['oro']}, soldaduras "
        f"{a['soldaduras']['encontradas']}/{a['soldaduras']['oro']} con "
        f"{a['soldaduras']['falsas']} falsas.",
    ]
    if otros_con_oro:
        lineas += ["", "## Otros equipos con oro", "", *cabecera]
        lineas += [_fila_markdown(e) for e in otros_con_oro]
    lineas += ["", "## Resto del dataset, sin oro", ""]
    if resultado["sin_oro"]:
        lineas += ["| Equipo | Carpeta | Estado del lote por revisión |", "| --- | --- | --- |"]
        for e in resultado["sin_oro"]:
            estados = ", ".join(f"rev{r}: {s}" for r, s in sorted(e["estados"].items()))
            lineas.append(f"| {e['tag']} | {e['grupo'] or '—'} | {estados} |")
    else:
        lineas.append("Sin equipos fuera del oro en este lote.")
    return "\n".join(lineas) + "\n"


def _commit() -> str | None:
    try:
        salida = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return salida.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lote", type=Path, help="Carpeta de salida de `trazia lote`")
    parser.add_argument("--oro", type=Path, default=Path("eval/verdad"))
    parser.add_argument("--marcos", type=Path, default=Path("eval/marcos"))
    parser.add_argument("--datos", type=Path, help="Dataset, para separar vessels/ y ver los IFC")
    parser.add_argument("--commit", help="Hash del código del lote (por defecto, HEAD)")
    parser.add_argument("--salida", type=Path, default=Path("generated/a3"))
    args = parser.parse_args(argv)
    if not (args.lote / "resumen.json").exists():
        print(f"{args.lote}: no parece la salida de un lote", file=sys.stderr)
        return 1
    resultado = tabla(args.lote, args.oro, args.marcos, args.datos, args.commit or _commit())
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "dos_vias.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    texto = markdown(resultado)
    (args.salida / "dos_vias.md").write_text(texto, encoding="utf-8")
    sys.stdout.buffer.write(texto.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

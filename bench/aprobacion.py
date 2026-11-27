"""Qué acierta lo que se aprueba solo: precisión, riesgo-cobertura y calibración con el oro de TR.

    python -m bench.aprobacion <salida_del_lote> [eval/verdad] [--salida generated/aprobacion]

La API aprueba sola un campo (`trazia.api.auto_approval`) si es candidato, su confianza llega al
umbral, el valor está escrito en el original y no hay otra lectura que lo contradiga. Esa
confianza es, en los planos del reto, la puntuación fija de cada regla: no hay calibración
ajustada con datos reales. Este banco mide qué pasa con ella frente al oro manual
(`eval/verdad`):

1. **Etiquetas.** Cada campo trazado de `revision.json` que el oro permite juzgar queda como
   acierto o fallo:
   - campos del equipo con la misma ruta en el oro (`campos`). Los numéricos aciertan a
     ±1 unidad o ±0,5 %; los de texto, sin mayúsculas, espacios ni signos. Si el oro da una
     `base` (interior o exterior, T.L.-T.L. u otra cota), el campo no se juzga: lo mide
     `bench.oro` con su conversión de base;
   - de cada boquilla, el NPS y el rating (como en `bench.oro`). Una boquilla cuya marca no está
     en el oro cuenta como fallo en todos sus campos juzgables: es una boquilla que no existe.
   Lo que el oro no trae (`null`) no se juzga.
2. **Aprobación automática.** Precisión y cobertura del conjunto que se aprobaría solo con el
   umbral de la API (0,8) y con otros umbrales.
3. **Riesgo-cobertura.** Precisión de los N campos de mayor confianza, para N creciente.
4. **Calibración isotónica sin el equipo medido.** Se ajusta confianza → acierto con los demás
   equipos y se aplica al que queda fuera, uno cada vez. Se da el ECE antes y después.

Solo se escriben agregados (cuentas y porcentajes por equipo, umbral y tramo de confianza): ni
valores ni textos del plano. La salida va a `generated/`, fuera de Git.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from bench.oro import cargar_oro, marca, rating, revisiones_efectivas

UMBRAL_API = 0.8
UMBRALES = (0.6, 0.7, 0.8, 0.85, 0.9, 0.95)
TRAMOS = ((0.0, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 0.825), (0.825, 0.875), (0.875, 1.01))


def _numero(valor) -> float | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    return float(texto) if re.fullmatch(r"-?\d+(\.\d+)?", texto) else None


def _palabras(valor) -> list[str]:
    sin_tildes = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return re.findall(r"[0-9A-Z]+", sin_tildes.upper())


def coincide(prediccion, oro) -> bool:
    """Números a ±1 unidad o ±0,5 %. Textos por palabras, en cualquier orden: el modelo guarda
    códigos («ellipsoidal_2_1») y el oro, el texto del plano («2:1 ellipsoidal»). Un código de dos
    palabras o más acierta si todas están en el texto del oro."""
    a, b = _numero(prediccion), _numero(oro)
    if a is not None and b is not None:
        return abs(a - b) <= max(1.0, 0.005 * abs(b))
    p, o = _palabras(prediccion), _palabras(oro)
    if not p or not o:
        return False
    return sorted(p) == sorted(o) or (len(p) >= 2 and set(p) <= set(o))


def etiquetar(revision: dict, oro_rev: dict) -> list[dict]:
    """[{ruta, acierto, confianza, estado, grounded, alternativas}] de los campos juzgables."""
    from trazia.model import Revision, fields

    modelo = Revision.model_validate(revision)
    campos_oro = oro_rev.get("campos", {})
    boquillas_oro = {marca(k): v for k, v in oro_rev.get("boquillas", {}).items()}
    filas = []
    for ruta, campo in fields(modelo.equipment).items():
        partes = ruta.split(".")
        esperado, juzgable = None, False
        if partes[0] == "nozzles" and len(partes) >= 3:
            nombre = ".".join(partes[2:])
            if nombre not in ("size_nps", "rating"):
                continue
            boquilla = boquillas_oro.get(marca(partes[1]))
            if boquilla is None:
                filas.append(_fila(ruta, campo, False))  # marca que no existe en el plano
                continue
            esperado = boquilla.get(nombre)
            if nombre == "rating":
                esperado = rating(esperado)
                prediccion = rating(campo.value)
            else:
                prediccion = campo.value
            juzgable = esperado is not None
        elif ruta in campos_oro:
            entrada = campos_oro[ruta]
            if isinstance(entrada, dict):
                if entrada.get("base"):
                    continue  # depende de la base; lo mide bench.oro
                esperado = entrada.get("valor")
            else:
                esperado = entrada
            prediccion = campo.value
            juzgable = esperado is not None
        if juzgable:
            filas.append(_fila(ruta, campo, coincide(prediccion, esperado)))
    return filas


def _fila(ruta, campo, acierto: bool) -> dict:
    fuente = campo.source
    return {
        "ruta": ruta,
        "acierto": acierto,
        "confianza": float(fuente.confidence),
        "estado": campo.state,
        "grounded": fuente.grounded,
        "alternativas": bool(getattr(campo, "alternatives", None)),
        "canal": fuente.channel or "—",
    }


def aprobable(fila: dict, umbral: float) -> bool:
    """La misma regla que `trazia.api.auto_approval.aprobables`."""
    return (
        fila["estado"] == "candidate"
        and fila["confianza"] >= umbral
        and fila["grounded"] is True
        and not fila["alternativas"]
    )


def _precision(filas: list[dict]) -> dict:
    n = len(filas)
    aciertos = sum(f["acierto"] for f in filas)
    return {"n": n, "aciertos": aciertos, "precision": round(aciertos / n, 4) if n else None}


def _ece(pares: list[tuple[float, bool]]) -> float | None:
    if not pares:
        return None
    total, suma = len(pares), 0.0
    for bajo, alto in TRAMOS:
        tramo = [(p, y) for p, y in pares if bajo <= p < alto]
        if tramo:
            media = sum(p for p, _ in tramo) / len(tramo)
            acierto = sum(y for _, y in tramo) / len(tramo)
            suma += len(tramo) / total * abs(media - acierto)
    return round(suma, 4)


def _por_canal(filas: list[dict]) -> list[dict]:
    """Aciertos por canal de lectura y por tipo de campo, y cuántos se aprobarían solos."""
    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in filas:
        origen = "boquillas" if f["ruta"].startswith("nozzles.") else "equipo"
        grupos[(f["canal"], origen)].append(f)
    return [
        {
            "canal": canal,
            "origen": origen,
            **_precision(fs),
            "aprobables": _precision([f for f in fs if aprobable(f, UMBRAL_API)]),
        }
        for (canal, origen), fs in sorted(grupos.items())
    ]


def calibracion_sin_el_equipo(por_equipo: dict[str, list[dict]]) -> dict:
    """Isotónica confianza → acierto ajustada sin el equipo que se mide, uno cada vez."""
    from sklearn.isotonic import IsotonicRegression

    antes, despues = [], []
    for equipo, filas in por_equipo.items():
        resto = [f for otro, fs in por_equipo.items() if otro != equipo for f in fs]
        if not filas or len({f["acierto"] for f in resto}) < 2:
            continue
        ajuste = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        ajuste.fit([f["confianza"] for f in resto], [float(f["acierto"]) for f in resto])
        predichas = ajuste.predict([f["confianza"] for f in filas])
        for fila, p in zip(filas, predichas, strict=True):
            antes.append((fila["confianza"], fila["acierto"]))
            despues.append((float(p), fila["acierto"]))
    return {"n": len(antes), "ece_antes": _ece(antes), "ece_despues": _ece(despues)}


def evaluar(lote: Path, carpeta_oro: Path) -> dict:
    oro = cargar_oro(carpeta_oro)
    por_equipo: dict[str, list[dict]] = defaultdict(list)
    for tag, datos in sorted(oro.items()):
        for etiqueta, oro_rev in revisiones_efectivas(datos).items():
            path = lote / tag / etiqueta / "revision.json"
            if path.exists():
                revision = json.loads(path.read_text(encoding="utf-8"))
                por_equipo[tag].extend(etiquetar(revision, oro_rev))
    filas = [f for fs in por_equipo.values() for f in fs]
    ordenadas = sorted(filas, key=lambda f: -f["confianza"])
    cobertura = []
    for fraccion in (0.1, 0.25, 0.5, 0.75, 1.0):
        n = max(1, round(fraccion * len(ordenadas))) if ordenadas else 0
        cobertura.append({"cobertura": fraccion, **_precision(ordenadas[:n])})
    tramos = []
    for bajo, alto in TRAMOS:
        tramo = [f for f in filas if bajo <= f["confianza"] < alto]
        if tramo:
            media = sum(f["confianza"] for f in tramo) / len(tramo)
            tramos.append(
                {
                    "desde": bajo,
                    "hasta": min(alto, 1.0),
                    "confianza_media": round(media, 3),
                    **_precision(tramo),
                }
            )
    return {
        "lote": lote.name,
        "juzgados": _precision(filas),
        "por_equipo": {tag: _precision(fs) for tag, fs in por_equipo.items()},
        "por_origen": {
            "boquillas": _precision([f for f in filas if f["ruta"].startswith("nozzles.")]),
            "equipo": _precision([f for f in filas if not f["ruta"].startswith("nozzles.")]),
        },
        "aprobacion_automatica": {
            str(u): {
                **_precision([f for f in filas if aprobable(f, u)]),
                "cobertura": round(sum(aprobable(f, u) for f in filas) / len(filas), 4)
                if filas
                else None,
                "resto": _precision([f for f in filas if not aprobable(f, u)]),
            }
            for u in UMBRALES
        },
        "umbral_api": UMBRAL_API,
        "por_canal": _por_canal(filas),
        "grounded": {
            str(g): _precision([f for f in filas if f["grounded"] is g])
            for g in (True, False, None)
        },
        "tramos_de_confianza": tramos,
        "riesgo_cobertura": cobertura,
        "calibracion_sin_el_equipo": calibracion_sin_el_equipo(por_equipo),
    }


def _pct(bloque: dict) -> str:
    if not bloque["n"]:
        return "—"
    return f"{bloque['aciertos']}/{bloque['n']} ({100 * bloque['precision']:.1f} %)"


def markdown(r: dict) -> str:
    api = r["aprobacion_automatica"][str(r["umbral_api"])]
    lineas = [
        f"# Aprobación automática frente al oro de TR · lote `{r['lote']}`",
        "",
        f"Campos juzgables: {_pct(r['juzgados'])} aciertos. Boquillas (NPS y rating): "
        f"{_pct(r['por_origen']['boquillas'])}. "
        f"Campos del equipo: {_pct(r['por_origen']['equipo'])}.",
        "",
        f"**Con el umbral de la API ({r['umbral_api']}):** se aprobarían solos {api['n']} campos "
        f"({100 * (api['cobertura'] or 0):.1f} % de los juzgables), con {_pct(api)} aciertos. "
        f"El resto, que va a revisión: {_pct(api['resto'])}.",
        "",
        "| Umbral | Se aprueban solos | Cobertura | Precisión | Resto (a revisión) |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for umbral, b in r["aprobacion_automatica"].items():
        cobertura = f"{100 * b['cobertura']:.1f} %" if b["cobertura"] is not None else "—"
        lineas.append(f"| {umbral} | {b['n']} | {cobertura} | {_pct(b)} | {_pct(b['resto'])} |")
    lineas += [
        "",
        "| Canal | Campos | Aciertos | Se aprobarían solos |",
        "| --- | --- | ---: | ---: |",
    ]
    for c in r["por_canal"]:
        lineas.append(f"| {c['canal']} | {c['origen']} | {_pct(c)} | {_pct(c['aprobables'])} |")
    lineas += ["", "| Tramo de confianza | Media | Aciertos |", "| --- | ---: | ---: |"]
    for t in r["tramos_de_confianza"]:
        lineas.append(f"| {t['desde']:.2f}–{t['hasta']:.2f} | {t['confianza_media']} | {_pct(t)} |")
    lineas += ["", "| Los N de mayor confianza | Aciertos |", "| ---: | ---: |"]
    for c in r["riesgo_cobertura"]:
        lineas.append(f"| {int(100 * c['cobertura'])} % | {_pct(c)} |")
    cal = r["calibracion_sin_el_equipo"]
    lineas += [
        "",
        f"Calibración isotónica sin el equipo medido ({cal['n']} campos): ECE {cal['ece_antes']} "
        f"con la puntuación de la regla, {cal['ece_despues']} calibrada.",
        "",
        "| `grounded` | Aciertos |",
        "| --- | ---: |",
        *(f"| {g} | {_pct(b)} |" for g, b in r["grounded"].items()),
        "",
        "| Equipo | Aciertos |",
        "| --- | ---: |",
        *(f"| {tag} | {_pct(b)} |" for tag, b in r["por_equipo"].items()),
        "",
    ]
    return "\n".join(lineas)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lote", type=Path)
    parser.add_argument("oro", type=Path, nargs="?", default=Path("eval/verdad"))
    parser.add_argument("--salida", type=Path, default=Path("generated/aprobacion"))
    args = parser.parse_args(argv)
    resultado = evaluar(args.lote, args.oro)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "aprobacion.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    texto = markdown(resultado)
    (args.salida / "aprobacion.md").write_text(texto, encoding="utf-8")
    sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

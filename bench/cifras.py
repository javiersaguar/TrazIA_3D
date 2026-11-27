"""Cifras del evento para el pitch y el guion, sin copiarlas a mano.

En Databricks (notebook `04_todo` o a mano):

    from bench.cifras import cifras_evento
    cifras = cifras_evento(perfil, filas, evaluacion)       # solo agregados, sin tags ni rutas

En el portátil, con el `cifras_evento.json` que sale del notebook:

    uv run python -m bench.cifras aplicar cifras_evento.json [--minutos-revision 12]

escribe `pitch/cifras-evento.js` (registro de las cifras que citan los pitches) y
`generated/cifras_guion.md` con las frases de las marcas [CIFRA TR] de docs/GUION_DEMO.md ya
rellenas. Lo que no está medido sale como «sin medir» y la frase alternativa del guion, nunca
como un número.

La medida frente al oro (tabla A3 de `python -m bench.dos_vias`) se añade aparte, sin tocar el
lote:

    uv run python -m bench.cifras oro generated/a3/dos_vias.json

Y la precisión de la aprobación automática frente al mismo oro (`python -m bench.aprobacion`):

    uv run python -m bench.cifras aprobacion generated/aprobacion/aprobacion.json
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HORAS_PROYECTO = 4800  # 400 equipos × 4 revisiones × 3 h (enunciado, pág. 5)
REVISIONES_PROYECTO = 1600


def _fila(fila) -> dict:
    return fila if isinstance(fila, dict) else fila.__dict__


def cifras_evento(perfil=None, filas=None, evaluacion=None, *, dataset="real") -> dict:
    """Agregados que se pueden llevar al portátil y al repositorio (docs/FLUJO_IA.md)."""
    salida = {
        "version": 1,
        "fecha": date.today().isoformat(),
        "dataset": dataset,
        "datos": None,
        "lote": None,
        "evaluacion": None,
    }
    if perfil:
        clase = perfil["pdf"]["clase"]
        pdf = perfil["pdf"]["documentos"]
        escaneados = clase.get("escaneado", 0) + clase.get("mixto", 0)
        salida["datos"] = {
            "equipos": perfil["equipos"]["total"],
            "revisiones": sum(
                int(k) * v for k, v in perfil["equipos"]["revisiones_por_equipo"].items()
            ),
            "pdf": pdf,
            "escaneados": round(escaneados / pdf, 3) if pdf else None,
            "ifc_referencia": perfil["ifc"]["archivos"],
        }
    if filas:
        from trazia.lote import Fila, resumen_compartible

        lote = resumen_compartible([Fila(**_fila(f)) for f in filas])
        salida["lote"] = {
            "equipos": lote["equipos"],
            "revisiones": lote["revisiones"],
            "correctas": lote["estado"].get("ok", 0),
            "errores": lote["estado"].get("error", 0),
            "segundos_total": lote["segundos"]["total"],
            "segundos_mediana": lote["segundos"]["mediana"],
        }
    if evaluacion and evaluacion.get("equipos"):
        from .evaluar import resumen_compartible

        agregado = resumen_compartible(evaluacion)["agregado"]
        boquillas, superficie = agregado["boquillas"], agregado["superficie"]
        exclusion = [e for e in evaluacion["equipos"] if e.get("convencion")]
        salida["evaluacion"] = {
            "equipos": agregado["equipos_medidos"],
            "error_relativo_diametro": agregado["error_relativo_medio"]["diameter"],
            "error_relativo_virola": agregado["error_relativo_medio"]["height"],
            "boquillas_recall": boquillas["recall"],
            "boquillas_precision": boquillas["precision"],
            "error_posicion_mm": boquillas["error_posicion_medio_mm"],
            "error_azimut_deg": boquillas["error_azimut_medio_deg"],
            "chamfer_mm": superficie["chamfer_mm_medio"],
            "p95_mm": superficie["p95_mm_medio"],
            "convenio_por_exclusion": all(
                e["convencion"]["cifra"] == "exclusion_de_uno" for e in exclusion
            )
            and bool(exclusion),
        }
    return salida


def cifras_oro(dos_vias: dict) -> dict:
    """Agregados de la tabla A3 frente al oro: recuentos con su denominador, sin tags ni valores."""
    agregado, equipos = dos_vias["agregado"], dos_vias.get("equipos", [])
    medidos = [e["via_2"] for e in equipos if (e.get("via_2") or {}).get("estado") == "medido"]
    tangentes = [v for m in medidos for v in m.get("tangentes_mm", {}).values()]

    def par(clave: str, *campos: str) -> dict:
        return {c: agregado[clave][c] for c in campos}

    return {
        "commit": dos_vias.get("commit"),
        "equipos": len(equipos),
        "revisiones": agregado["revisiones"],
        "con_modelo": agregado["con_modelo"],
        "ifc_validos": agregado["ifc_validos"],
        "marcas": par("marcas", "acertadas", "oro"),
        "nps": par("nps", "ok", "evaluables"),
        "boquillas_colocadas": par("boquillas_colocadas", "colocadas", "leidas"),
        "cambios": par("cambios", "acertados", "evaluables", "falsos", "a_revision"),
        "soldaduras": par("soldaduras", "encontradas", "oro", "falsas"),
        "via_2": {
            "equipos": len(medidos),
            "error_tangentes_mm_max": max(tangentes) if tangentes else None,
        },
    }


def cifras_aprobacion(resultado: dict) -> dict:
    """Lo que la API aprobaría sola con su umbral, frente al oro: cuentas y denominadores."""
    umbral = resultado["umbral_api"]
    api = resultado["aprobacion_automatica"][str(umbral)]
    return {
        "lote": resultado.get("lote"),
        "umbral": umbral,
        "equipos": len(resultado["por_equipo"]),
        "juzgados": resultado["juzgados"]["n"],
        "aprobados_solos": api["n"],
        "aciertos": api["aciertos"],
        "resto": {"n": api["resto"]["n"], "aciertos": api["resto"]["aciertos"]},
    }


def _pct(valor, decimales=1):
    return "sin medir" if valor is None else f"{valor * 100:.{decimales}f}".replace(".", ",")


def _num(valor, decimales=0):
    if valor is None:
        return "sin medir"
    texto = f"{valor:,.{decimales}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return texto


def frases_guion(cifras: dict, minutos_revision: float | None = None) -> str:
    """Las frases con [CIFRA TR] de docs/GUION_DEMO.md, rellenas o con su alternativa."""
    datos, evaluacion = cifras.get("datos"), cifras.get("evaluacion")
    lineas = [
        f"# Cifras para el guion ({cifras['fecha']}, dataset {cifras['dataset']})",
        "",
        "Generado por `python -m bench.cifras aplicar`. No editar a mano: volver a generarlo.",
        "",
        "## 1:00–1:40 · Entran los documentos",
        "",
    ]
    if datos:
        lineas.append(
            f"«Con el dataset del reto hemos hecho lo mismo dentro de la plataforma, en lote: "
            f"{_num(datos['equipos'])} equipos y {_num(datos['revisiones'])} revisiones.»"
        )
    else:
        lineas.append("Sin perfil del dataset: se omite la frase de Databricks.")
    oro = cifras.get("oro")
    lineas += ["", "## Medido contra el oro", ""]
    if oro:
        cambios, soldaduras = oro["cambios"], oro["soldaduras"]
        lineas.append(
            f"«Medido contra un oro manual, elaborado independientemente del lector y en "
            f"revisión: en {_num(oro['revisiones'])} revisiones de {_num(oro['equipos'])} "
            f"equipos acertamos {_num(cambios['acertados'])} de {_num(cambios['evaluables'])} "
            f"cambios entre revisiones, con {_num(cambios['falsos'])} "
            f"{'falso' if cambios['falsos'] == 1 else 'falsos'}, y encontramos "
            f"{_num(soldaduras['encontradas'])} de {_num(soldaduras['oro'])} soldaduras.»"
        )
    else:
        lineas.append("Sin la tabla A3: no se dice ninguna cifra contra el oro.")
    lineas += ["", "## 4:50–5:30 · Medido contra los IFC de TR", ""]
    if evaluacion and evaluacion["equipos"]:
        recall = evaluacion["boquillas_recall"]
        de_diez = "sin medir" if recall is None else _num(recall * 10, 1)
        lineas.append(
            f"«En {_num(evaluacion['equipos'])} equipos, el diámetro tiene un error medio del "
            f"{_pct(evaluacion['error_relativo_diametro'])} % y encontramos {de_diez} de cada "
            "diez boquillas.»"
        )
        if not evaluacion["convenio_por_exclusion"]:
            lineas.append(
                "Aviso: la cifra usa el convenio ajustado en cada equipo (solo hay uno con "
                "referencia). Decirlo así o no citar el error de boquillas."
            )
        lineas.append(
            f"Rótulo: error de diámetro {_pct(evaluacion['error_relativo_diametro'])} % · "
            f"boquillas encontradas {_pct(recall, 0)} % · error de posición "
            f"{_num(evaluacion['error_posicion_mm'])} mm · Chamfer "
            f"{_num(evaluacion['chamfer_mm'])} mm · {evaluacion['equipos']} equipos"
        )
    else:
        lineas.append(
            "«No tenemos aún la cifra contra los modelos de TR; esto es lo que medimos con datos "
            "sintéticos y así lo mediremos con los vuestros.» (bloque de 20 s)"
        )
    lineas += ["", "## Impacto", ""]
    if minutos_revision:
        horas = REVISIONES_PROYECTO * minutos_revision / 60
        lineas.append(
            f"«En revisión asistida tardamos {_num(minutos_revision, 1)} minutos por equipo. Con "
            f"eso, el proyecto de 4.800 horas baja a {_num(horas)}.»"
        )
    else:
        lineas.append("Tiempo de revisión sin medir: no se dice la frase del ahorro.")
    return "\n".join(lineas) + "\n"


def leer_aplicadas(raiz: Path = RAIZ) -> dict | None:
    """Las cifras que lleva hoy `cifras-evento.js`, para añadirles algo sin rehacer el lote."""
    texto = (raiz / "pitch" / "cifras-evento.js").read_text(encoding="utf-8")
    cuerpo = texto.split("export const cifrasEvento = ", 1)[1].strip().removesuffix(";")
    return json.loads(cuerpo)


def aplicar_oro(dos_vias: dict, raiz: Path = RAIZ) -> list[Path]:
    """Añade la medida frente al oro a las cifras ya aplicadas, sin cambiar el lote."""
    cifras = leer_aplicadas(raiz)
    if not cifras:
        raise ValueError("cifras-evento.js no tiene cifras del evento: aplica antes el lote")
    minutos = cifras.pop("minutos_revision", None)
    return aplicar({**cifras, "oro": cifras_oro(dos_vias)}, raiz, minutos)


def aplicar_aprobacion(resultado: dict, raiz: Path = RAIZ) -> list[Path]:
    """Añade la precisión de la aprobación automática a las cifras ya aplicadas."""
    cifras = leer_aplicadas(raiz)
    if not cifras:
        raise ValueError("cifras-evento.js no tiene cifras del evento: aplica antes el lote")
    minutos = cifras.pop("minutos_revision", None)
    return aplicar({**cifras, "aprobacion": cifras_aprobacion(resultado)}, raiz, minutos)


def aplicar(cifras: dict, raiz: Path = RAIZ, minutos_revision: float | None = None) -> list[Path]:
    """Escribe el módulo del pitch y la hoja de frases del guion."""
    pitch = raiz / "pitch" / "cifras-evento.js"
    guion = raiz / "generated" / "cifras_guion.md"
    contenido = dict(cifras, minutos_revision=minutos_revision)
    pitch.write_text(
        "// Generado por `python -m bench.cifras aplicar`: no editar a mano.\n"
        "// Solo agregados del evento (docs/FLUJO_IA.md). null = sin cifras del evento.\n"
        f"export const cifrasEvento = {json.dumps(contenido, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
        newline="\n",
    )
    guion.parent.mkdir(parents=True, exist_ok=True)
    guion.write_text(frases_guion(cifras, minutos_revision), encoding="utf-8", newline="\n")
    return [pitch, guion]


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Cifras del evento para el pitch y el guion")
    sub = parser.add_subparsers(dest="orden", required=True)
    aplicar_ = sub.add_parser("aplicar", help="Escribir pitch y frases desde cifras_evento.json")
    aplicar_.add_argument("cifras", type=Path)
    aplicar_.add_argument("--minutos-revision", type=float, default=None)
    oro = sub.add_parser("oro", help="Añadir la tabla A3 (bench.dos_vias) a las cifras aplicadas")
    oro.add_argument("dos_vias", type=Path)
    aprobacion = sub.add_parser(
        "aprobacion", help="Añadir la precisión de la aprobación automática (bench.aprobacion)"
    )
    aprobacion.add_argument("resultado", type=Path)
    sub.add_parser("vaciar", help="Volver al pitch solo con cifras sintéticas")
    args = parser.parse_args(argv)
    if args.orden == "oro":
        for path in aplicar_oro(json.loads(args.dos_vias.read_text(encoding="utf-8"))):
            print(f"Escrito {path}")
        return 0
    if args.orden == "aprobacion":
        resultado = json.loads(args.resultado.read_text(encoding="utf-8"))
        for path in aplicar_aprobacion(resultado):
            print(f"Escrito {path}")
        return 0
    if args.orden == "vaciar":
        destino = RAIZ / "pitch" / "cifras-evento.js"
        destino.write_text(
            "// Generado por `python -m bench.cifras aplicar`: no editar a mano.\n"
            "// Solo agregados del evento (docs/FLUJO_IA.md). null = sin cifras del evento.\n"
            "export const cifrasEvento = null;\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"Sin cifras del evento en {destino}")
        return 0
    cifras = json.loads(args.cifras.read_text(encoding="utf-8"))
    for path in aplicar(cifras, minutos_revision=args.minutos_revision):
        print(f"Escrito {path}")
    print(frases_guion(cifras, args.minutos_revision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

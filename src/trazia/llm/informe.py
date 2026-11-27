"""Tabla de llamadas, tokens y coste por nivel a partir del registro del enrutador.

    uv run python -m trazia.llm                       # generated/registro_llm.jsonl
    uv run python -m trazia.llm otro/registro.jsonl --json

La columna «si todo fuera nivel 3» recalcula los mismos tokens con el modelo grande de la misma
familia. Es la comparación del pitch: lo que se ahorra frente a usar siempre el modelo grande.
Solo suma llamadas con precio conocido.
"""

import argparse
import json
import sys
from pathlib import Path

from .enrutador import MODELOS_AZURE_OPENAI, MODELOS_CLAUDE, _modelo, registro_path
from .precios import coste

GRANDE = {
    "azure-openai": lambda: _modelo("azure-openai", 3, MODELOS_AZURE_OPENAI),
    "azure-claude": lambda: _modelo("azure-claude", 3, MODELOS_CLAUDE),
}


def leer(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(linea) for linea in path.read_text(encoding="utf-8").splitlines() if linea]


def resumen_por_nivel(entradas: list[dict]) -> dict:
    niveles: dict[int, dict] = {}
    abstenciones = 0
    for e in entradas:
        if e.get("estado") != "ok":
            abstenciones += 1
            continue
        fila = niveles.setdefault(
            e["nivel"],
            {
                "llamadas": 0,
                "en_cache": 0,
                "respaldos": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "coste_eur": 0.0,
                "sin_precio": 0,
                "segundos": 0.0,
                "coste_si_nivel3_eur": 0.0,
                "proveedores": {},
            },
        )
        fila["llamadas"] += 1
        fila["en_cache"] += int(bool(e.get("cache")))
        fila["respaldos"] += int(bool(e.get("respaldo")))
        fila["proveedores"][e["proveedor"]] = fila["proveedores"].get(e["proveedor"], 0) + 1
        if e.get("cache"):
            continue
        fila["tokens_in"] += e.get("tokens_in") or 0
        fila["tokens_out"] += e.get("tokens_out") or 0
        fila["segundos"] += e.get("segundos") or 0.0
        if not e.get("coste_conocido", True):
            fila["sin_precio"] += 1
            continue
        fila["coste_eur"] += e.get("coste_eur") or 0.0
        grande = GRANDE.get(e.get("familia"))
        alternativa = coste(grande(), e.get("tokens_in"), e.get("tokens_out")) if grande else None
        fila["coste_si_nivel3_eur"] += (
            alternativa if alternativa is not None else e.get("coste_eur") or 0.0
        )
    return {"niveles": dict(sorted(niveles.items())), "abstenciones": abstenciones}


def _tabla(resumen: dict) -> str:
    cabecera = (
        "| Nivel | Llamadas | En caché | Respaldos | Tokens entrada | Tokens salida | Coste € "
        "| Sin precio | Si todo fuera nivel 3 € | Segundos |"
    )
    filas = [cabecera, "|" + " ---: |" * 10]
    for nivel, f in resumen["niveles"].items():
        filas.append(
            f"| {nivel} | {f['llamadas']} | {f['en_cache']} | {f['respaldos']} | "
            f"{f['tokens_in']} | {f['tokens_out']} | {f['coste_eur']:.4f} | {f['sin_precio']} | "
            f"{f['coste_si_nivel3_eur']:.4f} | {f['segundos']:.1f} |"
        )
    filas.append(f"\nAbstenciones (ningún proveedor respondió): {resumen['abstenciones']}")
    return "\n".join(filas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registro", nargs="?", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    resumen = resumen_por_nivel(leer(args.registro or registro_path()))
    if args.json:
        print(json.dumps(resumen, ensure_ascii=False, indent=1))
    else:
        print(_tabla(resumen))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Lee tablas e identificadores citados de GA vectoriales, sin usar la HDM."""

import argparse
import json
from pathlib import Path

from trazia.lectura.tablas import _valor_nps as _valor_nps
from trazia.lectura.tablas import expandir_marcas as expandir_marcas
from trazia.lectura.tablas import leer_pdf as leer_pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    resultado = leer_pdf(args.pdf)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

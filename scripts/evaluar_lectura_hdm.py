"""Prepara candidatos HDM para medirlos con python -m bench.oro."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from bench.oro import cargar_oro, revisiones_efectivas
from scripts.lectura_hdm import read_hdm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hdm", type=Path)
    parser.add_argument("oro", type=Path)
    parser.add_argument("lote", type=Path)
    args = parser.parse_args()
    readings = {}
    for tag, truth in cargar_oro(args.oro).items():
        for revision in revisiones_efectivas(truth):
            separate = args.hdm / f"HDM_{tag}_{revision}.pdf"
            path = separate if separate.is_file() else args.hdm / f"HDM_{tag}.pdf"
            if path not in readings:
                reading = read_hdm(path)
                candidates = [
                    {**asdict(candidate), "confidence_raw": candidate.confidence}
                    for candidate in reading.candidates
                ]
                readings[path] = candidates
                print(path.stem, len(reading.appearances), len(candidates), flush=True)
            target = args.lote / tag / revision / "candidatos.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(readings[path], ensure_ascii=False, indent=2), encoding="utf-8"
            )


if __name__ == "__main__":
    main()

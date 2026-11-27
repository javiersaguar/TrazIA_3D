"""Combina candidatos del GA y la HDM de una misma revisión sin perder sus citas."""

import argparse
import json
import math
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pdfplumber

from trazia.ingest import dataset_filename
from trazia.lectura.tablas import expandir_marcas, leer_pdf
from trazia.units import CANONICAL, UnitError, normalize

if __package__:
    from .lectura_hdm import read_hdm
else:
    from lectura_hdm import read_hdm


def _clave(documento):
    tag = str(documento.get("equipment_tag") or "").strip().upper()
    rev = str(documento.get("revision") or "").strip().lower()
    rev = re.sub(r"^rev[. _-]*", "", rev)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", tag) or not re.fullmatch(r"[0-9a-z]+", rev):
        raise ValueError("Cada entrada debe declarar equipment_tag y revision.")
    return tag, str(int(rev)) if rev.isdecimal() else rev


def _marca(texto):
    marcas = expandir_marcas(texto)
    if len(marcas) != 1:
        raise ValueError(f"La marca debe venir expandida antes de unir fuentes: {texto!r}.")
    return marcas[0]


def _ruta(path):
    prefijo, _, cola = path.partition(".")
    if prefijo != "nozzles":
        return path
    marca, _, campo = cola.partition(".")
    if not campo:
        raise ValueError(f"Ruta de boquilla sin campo: {path!r}.")
    return f"nozzles.{_marca(marca)}.{campo}"


def _equivalentes(a, b):
    x, y = a["value"], b["value"]
    u, v = a.get("unit") or "1", b.get("unit") or "1"
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        if u == v == "1" and a["path"].startswith("nozzles."):
            campo = a["path"].rsplit(".", 1)[-1]
            if campo == "schedule":
                return _schedule(x) == _schedule(y)
            if campo in {"facing", "flange_type"}:
                return re.sub(r"[.\s]", "", str(x).upper()) == re.sub(r"[.\s]", "", str(y).upper())
        return u == v and str(x).strip().casefold() == str(y).strip().casefold()
    if u == v:
        return math.isclose(x, y)
    for magnitud in CANONICAL:
        try:
            uno = normalize(f"{x} {u}", magnitud, decimal=".")
            otro = normalize(f"{y} {v}", magnitud, decimal=".")
        except UnitError:
            continue
        return (
            uno.unit == otro.unit
            and uno.pressure_basis == otro.pressure_basis
            and math.isclose(uno.value, otro.value)
        )
    return False


def _schedule(value):
    return re.sub(r"^(?:SCH(?:EDULE)?\.?\s*)", "", str(value).strip().upper())


def _unir_identificadores(ga, hdm):
    ids = deepcopy(ga.get("identifiers", {}))
    for marca, entrada in hdm.get("identifiers", {}).items():
        if entrada["kind"] != "nozzle":
            continue
        marca = _marca(marca)
        if marca in ids and ids[marca]["kind"] == "bom_item":
            ids[f"bom_item__{marca}"] = {"id": marca, **ids.pop(marca)}
        if marca not in ids:
            ids[marca] = deepcopy(entrada)
        else:
            citas = ids[marca]["appearances"]
            for cita in entrada["appearances"]:
                if cita not in citas:
                    citas.append(deepcopy(cita))
    return ids


def unir_ga_hdm(ga, hdm):
    """Conserva cada lectura y señala las rutas con valores distintos entre ambas fuentes."""
    if _clave(ga) != _clave(hdm):
        raise ValueError("GA y HDM deben pertenecer al mismo equipo y revisión.")

    grupos = defaultdict(lambda: ([], []))
    for i, documento in enumerate((ga, hdm)):
        for entrada in documento["candidates"]:
            candidato = deepcopy(entrada)
            candidato["path"] = _ruta(candidato["path"])
            grupos[candidato["path"]][i].append(candidato)

    candidatos = []
    conflictos = []
    for path, (lectura_ga, lectura_hdm) in grupos.items():
        todos = lectura_ga + lectura_hdm
        if any(not _equivalentes(a, b) for a in lectura_ga for b in lectura_hdm):
            conflictos.append(path)
            for candidato in todos:
                candidato["state"] = "conflict"
        candidatos.extend(todos)

    return {
        **ga,
        "identifiers": _unir_identificadores(ga, hdm),
        "candidates": candidatos,
        "conflicts": conflictos,
        "warnings": [*ga.get("warnings", []), *hdm.get("warnings", [])],
    }


def unir_pdf(ga_path: Path, hdm_path: Path) -> dict:
    ga = leer_pdf(ga_path)
    info = dataset_filename(hdm_path.name)
    if not info or info.kind != "HDM":
        raise ValueError("El nombre de la hoja debe seguir HDM_<equipo>[_rev<revisión>].pdf.")
    # Como en trazia lote, la hoja sin revisión es documentación común del equipo.
    meta = {"equipment_tag": info.tag, "revision": info.revision or ga.get("revision", "")}
    if _clave(ga) != _clave(meta):
        raise ValueError("GA y HDM deben pertenecer al mismo equipo y revisión.")
    raw = read_hdm(hdm_path)
    with pdfplumber.open(hdm_path) as pdf:
        tamanos = {p.page_number: (p.width, p.height) for p in pdf.pages}
    candidatos = []
    for lectura in raw.candidates:
        dato = asdict(lectura)
        source = lectura.source
        w, h = tamanos[source.page]
        x0, y0, x1, y1 = source.bbox
        dato["source"] = {
            "document_id": source.document_id,
            "page": source.page,
            "locator": source.text,
            "bbox": [x0 / w, y0 / h, x1 / w, y1 / h],
            "confidence": dato.pop("confidence"),
        }
        candidatos.append(dato)
    ids = {
        marca: {
            "kind": "nozzle",
            "appearances": [
                {
                    "document_id": cita.document_id,
                    "page": cita.page,
                    "bbox": cita.bbox,
                    "locator": cita.text,
                    "role": "hdm_table",
                }
                for cita in citas
            ],
        }
        for marca, citas in raw.appearances.items()
    }
    return unir_ga_hdm(
        ga,
        {
            **meta,
            "candidates": candidatos,
            "identifiers": ids,
            "warnings": [asdict(aviso) for aviso in raw.notices],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ga", type=Path)
    parser.add_argument("hdm", type=Path)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.ga.suffix.lower() == args.hdm.suffix.lower() == ".pdf":
            resultado = unir_pdf(args.ga, args.hdm)
        else:
            ga, hdm = (json.loads(p.read_text(encoding="utf-8")) for p in (args.ga, args.hdm))
            resultado = unir_ga_hdm(ga, hdm)
    except ValueError as exc:
        parser.error(str(exc))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

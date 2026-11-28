"""Revisiones de los GA mecánicos leídas a mano, sin pasar por el pipeline.

Cada ficha (JSON, fuera de Git porque cita valores del plano) describe una revisión de un GA de
bomba o compresor: componentes exteriores con su envolvente, toberas con su cara de brida y
dirección, atributos técnicos y clasificación normalizada (ISO 14224, API, IFC). El script la
convierte en una `Revision` del contrato 0.3, escribe la carpeta del lote
(`<TAG>/rev<N>/revision.json` + `modelo.ifc`) y valida el IFC.

    python scripts/mecanicos_manual.py FICHAS_DIR DATASET_DIR -o LOTE_DIR

Reglas de la lectura manual:
- Cota rotulada en el plano: estado `accepted`, canal `humano`, confianza 1.
- Medida a escala sobre el dibujo: estado `assumed`, regla `medido_a_escala`, confianza 0,6.
- Saliente de tobera no acotado: supuesto con regla `asumido.saliente_boquilla`.
- Valor marcado como preliminar en el plano (`*`): estado `candidate`, confianza 0,75 y la marca
  en la explicación, para que no se apruebe solo.
- Pieza interior que el GA no dibuja (rodete, rodamientos): supuesto con su propia regla
  (`asumido.*`) y una explicación de cómo se ha dimensionado.
- Con `--vistas`, cada campo de una pieza o tobera lleva el recuadro de la vista del plano de la
  que se ha leído (`Source.bbox`), para que el visor lo señale sobre el PDF.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from trazia.ifc import build_ifc, validate_ifc
from trazia.model import Revision

sys.path.insert(0, str(Path(__file__).parent))
from calcar_vista import Vista  # noqa: E402

# Vista preferida para situar una pieza en el plano cuando la ficha no indica otra.
ORDEN_VISTAS = ("alzado", "planta", "lateral")


class Vistas:
    """Vistas calibradas de un plano: llevan una caja del modelo (mm) a un recuadro de la página.

    El recuadro va normalizado a la página (0–1, origen arriba a la izquierda), que es lo que el
    contrato guarda en `Source.bbox` y lo que el visor del plano dibuja sobre el PDF.
    """

    def __init__(self, carpeta: Path | None, dataset: Path, pdf: str):
        self.vistas: dict[str, Vista] = {}
        self.pagina: dict[int, tuple[float, float]] = {}
        if not carpeta or not carpeta.is_dir():
            return
        for ruta in sorted(carpeta.glob("*.json"), key=lambda r: _rango_vista(r.stem)):
            cfg = json.loads(ruta.read_text(encoding="utf-8"))
            cfg["pdf"] = pdf
            self.vistas[ruta.stem] = Vista(cfg, dataset)
        if self.vistas:
            doc, _ = next(iter(self.vistas.values())).open()
            with doc:
                for n, page in enumerate(doc.pages, 1):
                    self.pagina[n] = (float(page.width), float(page.height))

    def _recuadro(self, nombre: str, lo, hi):
        vista = self.vistas[nombre]
        iu = "xyz".index(vista.cfg["u"]["axis"])
        iv = "xyz".index(vista.cfg["v"]["axis"])
        puntos = [vista.pdf(u, v) for u in (lo[iu], hi[iu]) for v in (lo[iv], hi[iv])]
        xs, tops = [p[0] for p in puntos], [p[1] for p in puntos]
        b = vista.bbox
        x0, x1 = max(min(xs), b[0]), min(max(xs), b[2])
        t0, t1 = max(min(tops), b[1]), min(max(tops), b[3])
        if x0 >= b[2] or x1 <= b[0] or t0 >= b[3] or t1 <= b[1]:
            return None
        if x1 - x0 < 3:
            x0, x1 = (x0 + x1) / 2 - 1.5, (x0 + x1) / 2 + 1.5
        if t1 - t0 < 3:
            t0, t1 = (t0 + t1) / 2 - 1.5, (t0 + t1) / 2 + 1.5
        ancho, alto = self.pagina[vista.page_no]
        return [
            round(max(0.0, x0 / ancho), 5),
            round(max(0.0, t0 / alto), 5),
            round(min(1.0, x1 / ancho), 5),
            round(min(1.0, t1 / alto), 5),
        ]

    def recuadros(self, lo, hi, preferida: str | None = None) -> dict:
        """Recuadro del nombre (vista preferida) y de cada eje (primera vista que lo muestra)."""
        if not self.vistas:
            return {}
        orden = [preferida] if preferida in self.vistas else []
        orden += [n for n in self.vistas if n not in orden]
        out, paginas = {}, {}
        for clave, ejes in (("name", None), ("x", "x"), ("y", "y"), ("z", "z")):
            for nombre in orden:
                cfg = self.vistas[nombre].cfg
                if ejes and ejes not in (cfg["u"]["axis"], cfg["v"]["axis"]):
                    continue
                caja = self._recuadro(nombre, lo, hi)
                if caja:
                    out[clave], paginas[clave] = caja, self.vistas[nombre].page_no
                    break
        # Las vistas pueden estar en láminas distintas: cada recuadro lleva su página.
        return {**out, "_paginas": paginas} if out else {}


def _rango_vista(nombre: str) -> tuple[int, str]:
    return (ORDEN_VISTAS.index(nombre) if nombre in ORDEN_VISTAS else len(ORDEN_VISTAS), nombre)


# Diámetro exterior de tubería por NPS (ASME B36.10M), mm.
NPS_OD = {
    "1/2": 21.3, "3/4": 26.7, "1": 33.4, "1-1/2": 48.3, "2": 60.3, "3": 88.9, "4": 114.3,
    "6": 168.3, "8": 219.1, "10": 273.1, "12": 323.9, "14": 355.6, "16": 406.4, "18": 457.0,
    "20": 508.0, "24": 610.0, "26": 660.0,
}  # fmt: skip


def fuente(doc: str, page: int, locator: str, medido: bool, bbox=None) -> dict:
    return {
        "document_id": doc,
        "page": page,
        "locator": locator,
        "confidence": 0.6 if medido else 1.0,
        "channel": "humano",
        **({"rule": "medido_a_escala"} if medido else {}),
        **({"bbox": bbox} if bbox else {}),
    }


def campo(
    value, unit, doc, page, locator, medido=False, explicacion=None, regla=None, bbox=None
) -> dict:
    src = fuente(doc, page, locator, medido, bbox)
    estado = "accepted"
    if medido or regla:
        estado = "assumed"
        src["rule"] = regla or "medido_a_escala"
        src["confidence"] = 0.6
    out = {"value": value, "unit": unit, "source": src, "state": estado}
    if explicacion:
        out["explanation"] = explicacion
    return out


def pagina_de(recuadros: dict, clave: str, page: int) -> int:
    return (recuadros or {}).get("_paginas", {}).get(clave, page)


def vector(xyz, doc, page, locator, medido=False, recuadros=None, regla=None, expl=None) -> dict:
    recuadros = recuadros or {}
    return {
        a: campo(
            float(v),
            "mm",
            doc,
            pagina_de(recuadros, a, page),
            locator,
            medido,
            expl,
            regla,
            bbox=recuadros.get(a),
        )
        for a, v in zip("xyz", xyz)
    }


def clasif(refs) -> list[dict]:
    return [{"system": s, "code": c, "name": n} for s, c, n in refs]


CROSS = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}


def envolvente_de_perfil(c: dict) -> tuple[list, list]:
    """Origen y tamaño de la envolvente de una revolución o una extrusión de la ficha."""
    k = "xyz".index(c["axis"])
    lo, hi = [0.0] * 3, [0.0] * 3
    if c["shape"] == "revolve":
        a = [p[0] for p in c["profile"]]
        r = max(p[1] for p in c["profile"])
        lo[k], hi[k] = min(a), max(a)
        for i, centro in zip(CROSS[c["axis"]], c["center"]):
            lo[i], hi[i] = centro - r, centro + r
    else:
        otros = [i for i in range(3) if i != k]
        lo[k], hi[k] = c["range"]
        for n, i in enumerate(otros):
            vals = [p[n] for p in c["profile"]]
            lo[i], hi[i] = min(vals), max(vals)
    return lo, [h - lo_ for h, lo_ in zip(hi, lo)]


def componente(c: dict, doc: str, vistas: Vistas) -> dict:
    medido = c.get("medido", False)
    loc = c["locator"]
    if c.get("shape") in ("revolve", "extrude"):
        c = {**c}
        c["origin"], c["size"] = envolvente_de_perfil(c)
    hi = [o + d for o, d in zip(c["origin"], c["size"])]
    rec = vistas.recuadros(c["origin"], hi, c.get("vista"))
    # Pieza interior que el GA no dibuja: se sitúa por regla y lo dice su explicación.
    posicion = (doc, c["page"], loc, medido, rec, c.get("regla"), c.get("explicacion"))
    pieza = {
        "id": c["id"],
        "name": campo(
            c["name"], "1", doc, pagina_de(rec, "name", c["page"]), loc, bbox=rec.get("name")
        ),
        "envelope": {
            "origin": vector(c["origin"], *posicion),
            "size": vector(c["size"], *posicion),
        },
    }
    for k in ("shape", "axis", "ifc_class", "predefined_type", "object_type"):
        if c.get(k):
            pieza[k] = c[k]
    if c.get("profile"):
        pieza["profile"] = [tuple(float(v) for v in p) for p in c["profile"]]
    if c.get("classification"):
        pieza["classification"] = clasif(c["classification"])
    return pieza


def tobera(n: dict, doc: str, vistas: Vistas) -> dict:
    medido = n.get("medido", False)
    loc = n["locator"]
    pagina = n["page"]
    hold = n["nps"] not in NPS_OD
    # Tamaño HOLD (sin fijar en la tabla de puntos de conexión): OD provisional de la ficha.
    od = float(n.get("od_provisional", 60.3)) if hold else NPS_OD[n["nps"]]
    saliente = n.get("projection", 150.0)
    d = n["dir"]
    norma = sum(v * v for v in d) ** 0.5
    d = [v / norma for v in d]
    # La ficha da la cara de brida; el contrato sitúa la base de la tobera y su dirección.
    base = [p - saliente * v for p, v in zip(n["face"], d)]
    # Recuadro en el plano: el tramo base→cara con la brida (unas dos veces el OD) alrededor.
    ancho = [0.0 if abs(v) > 0.5 else od for v in d]
    lo = [min(b, f) - w for b, f, w in zip(base, n["face"], ancho)]
    hi = [max(b, f) + w for b, f, w in zip(base, n["face"], ancho)]
    rec = vistas.recuadros(lo, hi, n.get("vista"))
    caja = rec.get("name")
    pagina_caja = pagina_de(rec, "name", pagina)
    pos = vector(base, doc, pagina, loc, medido, rec)
    if n.get("preliminar"):
        for eje in pos.values():
            eje["state"] = "candidate"
            eje["source"]["confidence"] = 0.75
            eje["explanation"] = "Coordenada marcada como preliminar (*) en el plano."
    expl = n.get("note")
    return {
        "id": n["id"],
        "diameter": campo(
            od,
            "mm",
            doc,
            pagina_caja,
            loc,
            regla="asumido.od_tamano_hold" if hold else "asumido.od_tuberia_b36_10",
            explicacion=(
                f"Tamaño {n['nps']} en el plano: se dibuja con un OD provisional de {od:g} mm."
                if hold
                else f"OD de tubería NPS {n['nps']} según ASME B36.10M."
            ),
            bbox=caja,
        ),
        "projection": campo(
            saliente,
            "mm",
            doc,
            pagina_caja,
            loc,
            regla="asumido.saliente_boquilla",
            explicacion="Saliente no acotado en el GA; la cara de brida sí está situada.",
            bbox=caja,
        ),
        "elevation": {**pos["z"]},
        "azimuth": campo(
            0.0, "deg", doc, pagina_caja, loc, regla="asumido.azimut_por_direccion", bbox=caja
        ),
        "position": pos,
        "direction": {
            a: {
                "value": float(v),
                "unit": "1",
                "source": fuente(doc, pagina_caja, loc, False, caja),
                "state": "accepted",
            }
            for a, v in zip("xyz", d)
        },
        "service": campo(n["service"], "1", doc, pagina_caja, loc, explicacion=expl, bbox=caja),
        "rating": campo(n["rating"], "1", doc, pagina_caja, loc, bbox=caja),
        "size_nps": campo(n["nps"], "in", doc, pagina_caja, loc, bbox=caja),
        **(
            {"flange_standard": campo("B16.5", "1", doc, pagina_caja, loc, bbox=caja)}
            if n.get("b16_5", True) and not hold
            else {}
        ),
    }


def revision(f: dict, dataset: Path, vistas_dir: Path | None = None, clave: str = "") -> Revision:
    doc = f["document"]
    original = next(
        (p for p in (dataset / "mechanical" / doc["filename"],) if p.exists()), None
    ) or next(dataset.rglob(doc["filename"]))
    sha = hashlib.sha256(original.read_bytes()).hexdigest()
    did = doc["id"]
    carpeta = None
    if vistas_dir:
        nombres = (f.get("vistas") or clave, f["tag"])
        carpeta = next((vistas_dir / n for n in nombres if (vistas_dir / n).is_dir()), None)
    vistas = Vistas(carpeta, dataset, doc["filename"])
    piezas = [componente(c, did, vistas) for c in f["components"]]
    cajas = [
        envolvente_de_perfil(c)
        if c.get("shape") in ("revolve", "extrude")
        else (c["origin"], c["size"])
        for c in f["components"]
    ]
    lo = [min(o[i] for o, _ in cajas) for i in range(3)]
    hi = [max(o[i] + s[i] for o, s in cajas) for i in range(3)]
    env_loc = "Envolvente de todos los componentes leídos a mano"
    equipo = {
        "id": f["equipment_id"],
        "tag": campo(f["tag"], "1", did, f["tag_page"], f["tag_locator"]),
        "kind": f["kind"],
        "lod": 1,
        "support": "baseplate",
        "envelope": {
            "origin": vector(lo, did, 1, env_loc),
            "size": vector([h - lo_ for h, lo_ in zip(hi, lo)], did, 1, env_loc),
        },
        "components": piezas,
        "classification": clasif(f["classification"]),
        **({"predefined_type": f["predefined_type"]} if f.get("predefined_type") else {}),
        "attributes": {
            k: campo(v[0], v[1], did, v[2], v[3], explicacion=v[4] if len(v) > 4 else None)
            for k, v in f["attributes"].items()
        },
        "nozzles": [tobera(n, did, vistas) for n in f["nozzles"]],
    }
    return Revision.model_validate(
        {
            "project_id": f.get("project_id", "INDESIAHACK"),
            "revision": f["revision"],
            "dataset": "real",
            "documents": [
                {
                    "id": did,
                    "filename": doc["filename"],
                    "revision": f["revision"],
                    "sha256": sha,
                    "page_count": doc["page_count"],
                }
            ],
            "equipment": equipo,
            "run": {
                "strategy": "lectura_manual",
                "providers": [],
                "seconds": 0.0,
                "cost_eur": 0.0,
                "external_calls": 0,
            },
            "unplaced_nozzles": f.get("unplaced", []),
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fichas", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("-o", "--salida", type=Path, required=True)
    parser.add_argument("--solo", default="*", help="Patrón de las fichas a procesar")
    parser.add_argument(
        "--vistas", type=Path, help="Vistas calibradas: una subcarpeta por ficha o por tag"
    )
    args = parser.parse_args()
    resumen = []
    for ruta in sorted(args.fichas.glob(f"{args.solo}.json")):
        f = json.loads(ruta.read_text(encoding="utf-8"))
        rev = revision(f, args.dataset, args.vistas, ruta.stem)
        carpeta = args.salida / f["tag"] / f"rev{f['revision']}"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "revision.json").write_text(rev.model_dump_json(indent=2), encoding="utf-8")
        modelo = build_ifc(rev)
        modelo.write(str(carpeta / "modelo.ifc"))
        problemas = validate_ifc(modelo)
        resumen.append(
            {
                "tag": f["tag"],
                "revision": f["revision"],
                "componentes": len(rev.equipment.components or []),
                "boquillas": len(rev.equipment.nozzles),
                "ifc_valido": not problemas,
                "problemas": [str(p) for p in problemas][:5],
            }
        )
        print(json.dumps(resumen[-1], ensure_ascii=False))
    (args.salida / "resumen_manual.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

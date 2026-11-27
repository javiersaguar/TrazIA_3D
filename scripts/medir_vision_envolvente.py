"""Mide el aporte de visión a las cotas que no lee el GA vectorial."""

import argparse
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from trazia.extraction import Candidate
from trazia.ingest import ingest_bytes
from trazia.lectura.tablas import leer_pdf
from trazia.model import Source
from trazia.reconcile.grounding import is_grounded
from trazia.units import UnitError, normalize
from trazia.vision.base import PolicyError, VisionError
from trazia.vision.prompts import CAMPOS
from trazia.vision.providers import get_provider
from trazia.vision.reader import render_page

from .probar_azure import cargar_env


def medir(plano, campos, *, pagina=1, region=(0, 0, 1, 1), vision=False):
    inicio = perf_counter()
    vector = leer_pdf(plano)
    leidos = {
        c["path"]: c for c in vector["candidates"] if c.get("state") not in {"abstained", "assumed"}
    }
    faltantes = sorted(set(campos) - leidos.keys())
    informe = {
        "cpu": {
            "fields": {k: leidos[k] for k in sorted(set(campos) & leidos.keys())},
            "missing": faltantes,
            "seconds": perf_counter() - inicio,
            "external_cost_eur": 0,
        },
        "vision": {"status": "not_run", "cost_eur": None, "fields": [], "rejected": 0},
    }
    if not vision or not faltantes:
        return informe
    resultado = informe["vision"]
    inicio = perf_counter()
    try:
        data = plano.read_bytes()
        doc = ingest_bytes(data, plano.name, "GA", vector.get("revision", "sin-revision"))
        image = render_page(data, pagina)
        x0, y0, x1, y1 = region
        image = image.crop(
            tuple(round(v * n) for v, n in zip(region, (*image.size,) * 2, strict=True))
        )
        image.thumbnail((1500, 1500))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        schema = deepcopy(CAMPOS.schema)
        field = schema["properties"]["fields"]["items"]["properties"]["field"]
        field["enum"] = faltantes
        provider = get_provider("azure-openai", dataset="real")
        lectura = provider.read(
            stream.getvalue(),
            "campos",
            schema,
            page_ref=f"{hashlib.sha256(data).hexdigest()}#p{pagina}",
        )
        resultado.update(
            status="ok",
            tokens_in=lectura.tokens_in,
            tokens_out=lectura.tokens_out,
            cost_eur=lectura.cost_eur if lectura.cost_eur > 0 else None,
            cache_hit=lectura.cached,
        )
        for lectura_campo in lectura.data["fields"]:
            path = lectura_campo["field"]
            try:
                if path not in faltantes:
                    raise ValueError("Ruta fuera del conjunto de huecos")
                medida = normalize(f"{lectura_campo['value']} {lectura_campo['unit']}", "length")
                a, b, c, d = lectura_campo["bbox"]
                candidate = Candidate(
                    path=path,
                    value=medida.value,
                    unit=medida.unit,
                    source=Source(
                        document_id="GA",
                        page=pagina,
                        bbox=(
                            x0 + a * (x1 - x0),
                            y0 + b * (y1 - y0),
                            x0 + c * (x1 - x0),
                            y0 + d * (y1 - y0),
                        ),
                        locator=lectura_campo["text"],
                        confidence=0.6,
                    ),
                    channel="vision",
                )
                if is_grounded(candidate, doc.lines) is not True:
                    raise ValueError("La caja carece de respaldo vectorial")
            except (ValueError, KeyError, UnitError):
                resultado["rejected"] += 1
            else:
                resultado["fields"].append(candidate.model_dump(mode="json"))
    except (VisionError, PolicyError) as exc:
        resultado.update(status="unavailable", error=str(exc))
    resultado["seconds"] = perf_counter() - inicio
    return informe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ga", type=Path)
    parser.add_argument("--campo", required=True, action="append")
    parser.add_argument("--pagina", type=int, default=1)
    parser.add_argument("--region", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--env", type=Path)
    parser.add_argument("--salida", required=True, type=Path)
    args = parser.parse_args()
    region = args.region or (0, 0, 1, 1)
    x0, y0, x1, y1 = region
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 and args.pagina >= 1):
        parser.error("Indica una página positiva y una región normalizada.")
    if args.env:
        cargar_env(args.env)
    informe = medir(args.ga, args.campo, pagina=args.pagina, region=region, vision=args.vision)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

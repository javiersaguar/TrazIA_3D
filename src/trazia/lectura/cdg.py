"""Cota del centro de gravedad rotulada en el alzado de un GA vertical.

Forma reconocida: una línea «EL.+10861» justo encima de «C.D.G. / C.O.G.» y de la condición
(«EMPTY»/«VACIO» u «OPERATING»/«OPERACION»). Sin condición, la cota se toma como la del equipo
vacío solo si es la única del plano.
"""

import io
import re

import pdfplumber

_EL = re.compile(r"^EL\.?\s*([+\-−])\s*(\d{1,6}(?:[.,]\d+)?)$", re.I)
_COG = re.compile(r"^(?:C\.?\s*D\.?\s*G\.?|C\.?\s*O\.?\s*G\.?)$", re.I)
_VACIO = re.compile(r"^\(?(?:EMPTY|VAC[IÍ]O)\)?$", re.I)
_OPERACION = re.compile(r"^\(?(?:OPERATING|OPERATION|OPERACI[OÓ]N)\)?$", re.I)


def _cy(p):
    return (p["top"] + p["bottom"]) / 2


def leer(pdf: bytes, documento: str) -> list[dict]:
    lecturas = {}
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
            for cota in palabras:
                dato = _EL.fullmatch(cota["text"])
                if not dato:
                    continue
                debajo = [
                    p
                    for p in palabras
                    if 0 < _cy(p) - _cy(cota) < 30 and -10 < p["x0"] - cota["x0"] < 90
                ]
                if not any(_COG.fullmatch(p["text"]) for p in debajo if _cy(p) - _cy(cota) < 16):
                    continue
                if any(_OPERACION.fullmatch(p["text"]) for p in debajo):
                    condicion = "operating"
                elif any(_VACIO.fullmatch(p["text"]) for p in debajo):
                    condicion = "empty"
                else:
                    condicion = None
                valor = float(dato[2].replace(",", "."))
                if dato[1] != "+":
                    valor = -valor
                caja = (
                    min(p["x0"] for p in [cota, *debajo]),
                    cota["top"],
                    max(p["x1"] for p in [cota, *debajo]),
                    max(p["bottom"] for p in [cota, *debajo]),
                )
                texto = " ".join(
                    p["text"] for p in sorted([cota, *debajo], key=lambda p: (_cy(p), p["x0"]))
                )
                lecturas.setdefault(condicion, []).append((valor, page, caja, texto))
            page.close()
    salida = []
    vacio = lecturas.get("empty") or (
        lecturas.get(None) if len(lecturas.get(None, [])) == 1 and "empty" not in lecturas else None
    )
    for ruta, datos in (
        ("attributes.cog_elevation", vacio),
        ("attributes.cog_elevation_operating", lecturas.get("operating")),
    ):
        if not datos or len({d[0] for d in datos}) != 1:
            continue
        valor, page, (x0, y0, x1, y1), texto = datos[0]
        salida.append(
            {
                "path": ruta,
                "value": valor,
                "unit": "mm",
                "source": {
                    "document_id": documento,
                    "page": page.page_number,
                    "bbox": [x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height],
                    "locator": texto,
                    "text_original": texto,
                    "confidence": 0.85,
                    "rule": "ga.cdg_elevacion",
                },
                "channel": "cota",
                "explanation": "Cota del centro de gravedad rotulada en el alzado"
                + (" (equipo en operación)." if ruta.endswith("operating") else " (equipo vacío)."),
            }
        )
    return salida

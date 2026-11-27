"""Tabla DESIGN DATA del GA: los datos de proceso de cada revisión del plano.

La hoja de datos es una para todas las revisiones; la tabla del GA es la de esa revisión. Solo se
leen filas con etiqueta, unidad y un único valor numérico al empezar («MAWP Kgf/cm² 9.488»,
«OPERATION PRESSURE Kgf/cm² (BAR) 3.9 (3.8)»). Las filas con dos valores, como «-10 / 100»
o «8 / FV», quedan fuera.
"""

import io
import re

import pdfplumber
from pdfplumber.utils import cluster_objects

from .tablas import _texto_caja

_NUMERO = r"(\d+(?:[.,]\d+)?)"
_PRESION = r"KGF?\s*/\s*CM[2²](?:\s*\((?:BAR|G)\))?|BAR(?:\s*\(?G\)?)?|MPA|KPA"
_FILAS = (
    ("mawp", rf"MAWP\s+(?P<u>{_PRESION})", "pressure"),
    ("operating_pressure", rf"OPERAT(?:ION|ING)\s+PRESSURE\s+(?P<u>{_PRESION})", "pressure"),
    ("operating_temperature", r"OPERAT(?:ION|ING)\s+TEMPERATURE\s+(?P<u>[ºº°]\s*C)", "temperature"),
    (
        "hydrotest_pressure",
        rf"HYDROSTATIC\s+TEST\s+PRESSURE(?:\s+SHOP\s*/\s*FIELD)?\s+(?P<u>{_PRESION})",
        "pressure",
    ),
    ("corrosion_allowance", r"CORROSION\s+ALLOWANCE\s+(?P<u>MM)", "length"),
)
_PATRONES = tuple(
    (campo, re.compile(rf"(?:^|\s){patron}\s+{_NUMERO}(?P<resto>.*)$", re.I), tipo)
    for campo, patron, tipo in _FILAS
)
# Tras el valor solo se admite otro igual («11.44 / 11.44»), un paréntesis o texto que no sea
# un segundo número: «-10 / 100» y «8 / FV» no son un valor único.
_SEGUNDO = re.compile(rf"^\s*/\s*{_NUMERO}")


def _unidad(texto, tipo):
    if tipo == "pressure":
        texto = texto.upper()
        if texto.startswith("KG"):
            return "kgf/cm2"
        return texto.split()[0].lower()
    return {"temperature": "C", "length": "mm"}[tipo]


_PERNOS = (
    re.compile(r"(?:^|\s)(\d{1,3})\s*[xX]\s*(M\d{2})\s+ANCHORS?(?!\w)", re.I),
    re.compile(r"(?:^|\s)(\d{1,3})\s+ANCHOR\s+BOLTS\s+(M\d{2})(?!\w)", re.I),
)


def _cita(documento, page, caja, texto):
    x0, y0, x1, y1 = caja
    return {
        "document_id": documento,
        "page": page.page_number,
        "bbox": [x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height],
        "locator": texto,
        "text_original": texto,
        "confidence": 0.85,
        "rule": "ga.datos_diseno",
    }


def leer(pdf: bytes, documento: str) -> list[dict]:
    salida = {}
    pernos = {}
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
            for fila in cluster_objects(palabras, "top", 2):
                grupo = sorted(fila, key=lambda p: p["x0"])
                texto, caja = _texto_caja(grupo)
                for patron in _PERNOS:
                    for dato in patron.finditer(texto):
                        valor = f"{int(dato[1])} x {dato[2].upper()}"
                        pernos.setdefault(valor, (page, caja, texto))
            if not any(p["text"].upper() == "DESIGN" for p in palabras):
                page.close()
                continue
            for fila in cluster_objects(palabras, "top", 2):
                grupo = sorted(fila, key=lambda p: p["x0"])
                texto, (x0, y0, x1, y1) = _texto_caja(grupo)
                for campo, patron, tipo in _PATRONES:
                    if campo in salida or not (dato := patron.search(texto)):
                        continue
                    valor = float(dato[2].replace(",", "."))
                    if (segundo := _SEGUNDO.match(dato["resto"])) and float(
                        segundo[1].replace(",", ".")
                    ) != valor:
                        continue
                    salida[campo] = {
                        "path": f"attributes.{campo}",
                        "value": valor,
                        "unit": _unidad(dato["u"], tipo),
                        "unit_original": dato["u"],
                        "source": {
                            "document_id": documento,
                            "page": page.page_number,
                            "bbox": [
                                x0 / page.width,
                                y0 / page.height,
                                x1 / page.width,
                                y1 / page.height,
                            ],
                            "locator": texto,
                            "text_original": texto,
                            "confidence": 0.85,
                            "rule": "ga.datos_diseno",
                        },
                        "channel": "tabla",
                        "explanation": "Fila de la tabla DESIGN DATA del GA de esta revisión.",
                    }
            page.close()
        if len(pernos) == 1:
            ((valor, (page, caja, texto)),) = pernos.items()
            salida["anchor_bolts"] = {
                "path": "attributes.anchor_bolts",
                "value": valor,
                "unit": "1",
                "source": {**_cita(documento, page, caja, texto), "rule": "ga.pernos_anclaje"},
                "channel": "texto",
                "explanation": "Número y métrica de los pernos de anclaje rotulados en el GA.",
            }
    return list(salida.values())

"""Cotas generales escritas en texto: diámetro, longitud entre tangentes, tanque y faldón.

Las reglas de `envolvente` y `columna` leen la vista acotada de un formato de plano concreto.
Muchos planos y hojas de datos, además, escriben las cotas principales en una frase:

- «SIZE OF VESSEL MM 4700 X 14100 (I.D. X TL-TL)» en el cajetín;
- «ID Ø2950 x 13mm» y «11800 TL. to TL.» en el alzado;
- «Shell ID 1250 mm» y «Length between tangents 29460 mm» en la hoja de datos;
- «tank ø20,0m x tank 23,4m» bajo «Inside diameter / Cyl. height»;
- «34600 T.T.L TO B.T.L.» y «I.D. Ø2592» girado junto a la virola.

Este lector solo propone un valor si aparece una vez (o siempre con el mismo valor) en el
documento, y deja como cita la línea y su caja. No sustituye a las reglas de vista: `leer` de
`lectura` solo añade las rutas que ninguna otra regla ha dado.
"""

import io
import re

import pdfplumber
from pdfplumber.utils import cluster_objects

from .envolvente import rotados

_NUM = r"\d{3,6}(?:[.,]\d+)?"
_M = r"\d{1,3}(?:[.,]\d{1,3})?"
CONFIANZA = 0.8


def _n(texto: str) -> float:
    return float(texto.replace(",", "."))


# (clave neutra, patrón, factor a mm, regla, explicación)
_PATRONES = [
    (
        ("diametro", "longitud"),
        re.compile(
            rf"SIZE OF VESSEL\s*MM\s*({_NUM})\s*[X×]\s*({_NUM})\s*"
            r"\(\s*I\.?D\.?\s*[X×]\s*T\.?L\.?\s*-?\s*T\.?L",
            re.I,
        ),
        1,
        "texto.tamano_recipiente_id_x_tl",
        "Tamaño del recipiente escrito como diámetro interior × longitud entre tangentes.",
    ),
    (
        ("diametro",),
        re.compile(rf"\bShell\s+ID\b(?:\s*\d{{1,2}}\))?\D{{0,6}}({_NUM})\s*mm", re.I),
        1,
        "texto.hoja_diametro_interior",
        "Diámetro interior de la virola en la hoja de datos.",
    ),
    (
        ("longitud",),
        re.compile(rf"Length between tangents(?:\s*\d{{1,2}}\))?\D{{0,6}}({_NUM})\s*mm", re.I),
        1,
        "texto.hoja_longitud_tangentes",
        "Longitud entre tangentes en la hoja de datos.",
    ),
    (
        ("diametro",),
        re.compile(rf"(?<![A-Z])I\.?D\.?\s*[Ø⌀O]\s*({_NUM})\s*[X×]\s*\d+\s*mm", re.I),
        1,
        "texto.virola_id_por_espesor",
        "Virola rotulada como diámetro interior × espesor.",
    ),
    (
        ("longitud",),
        re.compile(rf"(?<![\d+])({_NUM})\s*\(?\s*T\.?\s?L\.?\s*TO\s*T\.?\s?L\b", re.I),
        1,
        "texto.cota_tl_a_tl",
        "Cota entre líneas de tangencia.",
    ),
    (
        ("longitud",),
        re.compile(rf"(?<![\d+])({_NUM})\s*T\.T\.L\.?\s*(?:TO|A)\s*B\.T\.L", re.I),
        1,
        "texto.cota_ttl_a_btl",
        "Distancia de la tangente superior a la inferior.",
    ),
    (
        ("diametro", "altura"),
        re.compile(rf"tank\s*[øØ⌀]\s*({_M})\s*m\s*[x×]\s*tank\s*({_M})\s*m", re.I),
        1000,
        "texto.tanque_diametro_por_altura",
        "Diámetro interior × altura de virola del tanque en el cuadro de datos.",
    ),
    (
        ("tl_desde_rasante",),
        re.compile(rf"bottom\s+TL\s+is\s+({_NUM})\s*mm\s+from\s+grade", re.I),
        1,
        "texto.tl_inferior_desde_rasante",
        "Altura de la tangente inferior sobre la rasante, escrita en la hoja de datos.",
    ),
]
_FONDO_2_1 = re.compile(
    r"2\s*:\s*1\s*ELLIP|ELL?IPSOIDAL\s+HEAD\s+2\s*:\s*1|ELIPSOIDAL\s+2\s*:\s*1", re.I
)
_TECHO_CONO = re.compile(r"\bCone\s+roof\s+YES\b", re.I)
_TECHO_CUPULA = re.compile(r"\bDome\s+roof\s+YES\b", re.I)
_TECHO_PLANO = re.compile(r"\bFIXED ROOF TANK\b", re.I)
_ID_GIRADO = re.compile(rf"^I\.?D\.?\s*[Ø⌀O]\s*({_NUM})$", re.I)


def _lineas(page):
    """Líneas de pdfplumber y, además, filas de palabras a la misma altura.

    Las filas recogen celdas de tabla que pdfplumber parte en líneas distintas («tank ø20,0m x
    tank» y «23,4m») o marcas en otra columna («Cone roof» y su «YES»).
    """
    for linea in page.extract_text_lines():
        yield linea["text"], (linea["x0"], linea["top"], linea["x1"], linea["bottom"])
    palabras = [p for p in page.extract_words(x_tolerance=1.5, y_tolerance=2) if p["upright"]]
    for fila in cluster_objects(palabras, "top", 3):
        fila.sort(key=lambda p: p["x0"])
        yield (
            " ".join(p["text"] for p in fila),
            (
                min(p["x0"] for p in fila),
                min(p["top"] for p in fila),
                max(p["x1"] for p in fila),
                max(p["bottom"] for p in fila),
            ),
        )


def _cita(page, documento, caja, texto, regla, confianza=CONFIANZA):
    x0, y0, x1, y1 = caja
    return {
        "document_id": documento,
        "page": page.page_number,
        "bbox": [x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height],
        "locator": texto[:120],
        "text_original": texto[:200],
        "confidence": confianza,
        "rule": regla,
    }


def _rutas(tipo: str | None) -> dict[str, str]:
    if tipo == "horizontal_vessel":
        return {"diametro": "horizontal.diameter", "longitud": "horizontal.length"}
    if tipo == "tank":
        return {"diametro": "tank.diameter", "altura": "tank.height"}
    return {"diametro": "diameter", "longitud": "height"}


def leer(pdf: bytes, documento: str, tipo: str | None) -> list[dict]:
    """Candidatos de cota general del documento, solo con valor único por clave."""
    hallados: dict[str, dict] = {}
    repetidos: set[str] = set()
    fondo = techo = None
    rutas = _rutas(tipo)

    def apuntar(clave, valor, page, caja, texto, regla, explicacion):
        previo = hallados.get(clave)
        if previo is not None and previo["value"] != valor:
            repetidos.add(clave)
            return
        if previo is None:
            hallados[clave] = {
                "value": valor,
                "source": _cita(page, documento, caja, texto, regla),
                "explanation": explicacion,
            }

    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            lineas = list(_lineas(page))
            for texto, caja in lineas:
                for claves, patron, factor, regla, explicacion in _PATRONES:
                    for dato in patron.finditer(texto):
                        for i, clave in enumerate(claves, start=1):
                            apuntar(
                                clave,
                                round(_n(dato[i]) * factor, 1),
                                page,
                                caja,
                                dato[0],
                                regla,
                                explicacion,
                            )
                if fondo is None and _FONDO_2_1.search(texto):
                    fondo = _cita(page, documento, caja, texto, "texto.fondo_elipsoidal_2_1")
                if techo is None and (
                    _TECHO_CONO.search(texto)
                    or _TECHO_CUPULA.search(texto)
                    or _TECHO_PLANO.search(texto)
                ):
                    valor = (
                        "conical"
                        if _TECHO_CONO.search(texto)
                        else "domed"
                        if _TECHO_CUPULA.search(texto)
                        else "flat"
                    )
                    techo = (valor, _cita(page, documento, caja, texto, "texto.tipo_techo_marcado"))
            if tipo != "horizontal_vessel" and tipo != "tank":
                for texto, caja in rotados(page):
                    if dato := _ID_GIRADO.match(texto.strip()):
                        apuntar(
                            "diametro",
                            _n(dato[1]),
                            page,
                            caja,
                            texto,
                            "texto.columna_id_girado",
                            "Diámetro interior rotulado en vertical junto a la virola.",
                        )
            page.close()

    salida = []
    for clave, dato in hallados.items():
        if clave in repetidos:
            continue
        if clave == "tl_desde_rasante":
            salida.append(
                {
                    "path": "skirt_height",
                    "unit": "mm",
                    "channel": "cota",
                    "state": "assumed",
                    **dato,
                    "explanation": dato["explanation"]
                    + " Se supone que el faldón apoya en la rasante: altura del faldón igual a esa"
                    " cota. A verificar con el plano del faldón.",
                }
            )
            continue
        ruta = rutas.get(clave)
        if ruta is None:
            continue
        salida.append({"path": ruta, "unit": "mm", "channel": "cota", **dato})
        if clave == "diametro" and tipo != "tank":
            salida.append(
                {
                    "path": "attributes.diameter_basis",
                    "value": "inside",
                    "unit": "1",
                    "channel": "cota",
                    "source": dato["source"],
                    "explanation": "El rótulo da el diámetro interior.",
                }
            )
    if fondo is not None and tipo != "tank":
        salida.append(
            {
                "path": "attributes.head_type",
                "value": "ellipsoidal_2_1",
                "unit": "1",
                "channel": "cota",
                "source": fondo,
                "explanation": "Fondo elipsoidal 2:1 rotulado en el documento.",
            }
        )
    if techo is not None and tipo == "tank":
        valor, cita = techo
        salida.append(
            {
                "path": "tank.roof",
                "value": valor,
                "unit": "1",
                "channel": "cota",
                "source": cita,
                "explanation": (
                    "Techo fijo citado en el plano."
                    if valor == "flat"
                    else "Tipo de techo marcado con «YES» en la hoja de datos."
                ),
            }
        )
    return salida

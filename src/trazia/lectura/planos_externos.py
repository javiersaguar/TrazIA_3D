"""Planos y hojas de datos de otros fabricantes: unidades imperiales y rótulos de cajetín.

Los GA del reto vienen en milímetros y con el formato de TR. Un plano de otro fabricante
cambia la forma de escribir lo mismo, y aquí se leen las variantes más comunes:

- cotas en pies y pulgadas («5'-6" ID», «24'-0" T/T», «4'-11 29/64" [1510]», con los
  milímetros entre corchetes cuando el plano los da);
- tamaño en el título («36" OD x 120" S/S», «(D=1510-H=2438)»);
- tipología en el título («HORIZONTAL SEPARATOR») y apoyos («SUPPORT LEGS»);
- tabla de boquillas con marcas de una letra («MK. NO. SIZE RTG. FCG. SERVICE» y filas
  «W 1 6" 600# RF Vapor Outlet»), también tras el OCR;
- el tag en «ITEM NO.: D-506».

Igual que `cotas_generales`, cada clave solo se propone con un valor único en el documento y
`lectura.leer` solo añade rutas que ninguna regla del formato del reto ha dado.
"""

import io
import re
from fractions import Fraction

import pdfplumber

from ..extractors.units import NPS_OUTSIDE_DIAMETER_MM
from .envolvente import rotados
from .tablas import expandir_marcas
from .tipologia import normalizar

CONFIANZA = 0.7
PULGADA = 25.4

_COMILLAS = str.maketrans({"″": '"', "”": '"', "“": '"', "�": '"', "’": "'", "′": "'", "*": '"'})
# 5'-6", 24'-0", 4'-11 29/64", 7'-2 9/64"
# El OCR suele leer la comilla de pulgadas como «°» detrás de una cota en pies.
_PIES = r"(\d{1,3})\s*'\s*-?\s*(\d{1,2})(?:\s+(\d{1,2})\s*/\s*(\d{1,3}))?\s*[\"°]?"
_MM_CORCHETE = r"\s*\[\s*(\d{3,6})\s*\]"
_BASE = r"([I1l]\.?\s?D\.?|O\.?\s?D\.?)"  # «1D»: el OCR confunde la I con un 1


def _pies(dato, inicio=1) -> float | None:
    pies, pulgadas, numerador, denominador = dato.groups()[inicio - 1 : inicio + 3]
    total = int(pies) * 12 + int(pulgadas)
    if numerador and denominador and int(denominador):
        total += Fraction(int(numerador), int(denominador))
    if int(pulgadas) >= 12:
        return None
    return round(float(total) * PULGADA, 1)


def _base(texto: str) -> str:
    return "outside" if texto.upper().lstrip().startswith("O") else "inside"


# (clave, patrón, lector → valores por clave, regla, explicación)
def _diametro_y_largo(dato):
    return {
        "diametro": round(float(dato[1]) * PULGADA, 1),
        "base": _base(dato[2]),
        "longitud": round(float(dato[3]) * PULGADA, 1),
    }


_PATRONES = [
    (
        re.compile(
            r"(\d{2,3}(?:\.\d+)?)\s*\"\s*" + _BASE + r"\s*[X×]\s*(\d{2,4}(?:\.\d+)?)\s*\"\s*"
            r"(?:S\s*/\s*S|T\s*/\s*T|T\.?L\.?\s*-?\s*T\.?L\.?|SEAM)",
            re.I,
        ),
        _diametro_y_largo,
        "texto.imperial_diametro_por_longitud",
        "Tamaño del recipiente en el título: diámetro × longitud entre costuras o tangentes, en "
        "pulgadas.",
    ),
    (
        re.compile(r"\(?\s*D\s*=\s*(\d{3,5})\s*[-–,;]?\s*H\s*=\s*(\d{3,5})\s*\)?", re.I),
        lambda dato: {"diametro": float(dato[1]), "longitud": float(dato[2])},
        "texto.titulo_d_h",
        "Diámetro y altura entre tangentes del título del plano, en milímetros.",
    ),
    (
        re.compile(_BASE + r"\s*" + _PIES + _MM_CORCHETE, re.I),
        lambda dato: {"diametro": float(dato[6]), "base": _base(dato[1])},
        "texto.diametro_pies_con_mm",
        "Diámetro acotado en pies y pulgadas con su equivalente en milímetros entre corchetes.",
    ),
    (
        re.compile(r"-?\s*" + _PIES + r"\s*-?\s*" + _BASE + r"(?![A-Z])", re.I),
        lambda dato: {"diametro": _pies(dato), "base": _base(dato[5])},
        "texto.diametro_pies",
        "Diámetro acotado en pies y pulgadas.",
    ),
    (
        re.compile(_PIES + r"\s*\(?\s*(?:T\s*/\s*T|T\.?L\.?\s*(?:TO|-)\s*T\.?L\.?)", re.I),
        lambda dato: {"longitud": _pies(dato)},
        "texto.longitud_pies_tl",
        "Longitud entre tangentes acotada en pies y pulgadas.",
    ),
]

_HORIZONTAL = re.compile(
    r"\bHORIZONTAL\s+(?:SEPARATOR|DRUM|ACCUMULATOR|KNOCK\s*-?\s*OUT\s+DRUM|SURGE\s+DRUM)\b"
)
_VERTICAL = re.compile(
    r"\bVERTICAL\s+(?:SEPARATOR|DRUM|ACCUMULATOR|KNOCK\s*-?\s*OUT\s+DRUM|SURGE\s+DRUM)\b"
)
# Tolerante al OCR: «SJPPORT LEGS», «SUPPORT LEGSPADPLATE».
_PATAS = re.compile(r"S.?PPORT\s+LEGS?|LEG\s+S.?PPORTS?")
_FALDON = re.compile(r"SKIRT\s+(?:HEIGHT|DETAIL|BASE\s+RING|O\.?\s?D|ACCESS|OPENING)")
_ITEM = re.compile(r"\bITEM\s+NO\.?\s*[:#]?\s*([A-Z]{1,4}-?\d{2,5}[A-Z]?)\b")

# Tabla de boquillas de otros formatos.
_CABECERA = re.compile(
    r"\b(?:MK|MARK|NOZZLE|POS)\b.*\bSIZE\b.*\b(?:RTG|RATING|CLASS)\b"
    r"|\b(?:MK|MARK)\b.*\bNO\b.*\bSIZE",
    re.I,
)
_FILA = re.compile(
    r"^(?P<marca>[A-Z]{1,3}\d{0,3}[A-Z]?(?:\s*/\s*[A-Z]{0,3}\d{1,3}[A-Z]?)*)\s+"
    r"(?:(?P<cantidad>\d{1,2})\s+)?"
    r"(?P<tamano>\d{1,2}(?:\s+\d/\d|/\d|\.\d+)?)\s*[\"°]\s+"  # el OCR lee " como °
    r"(?:(?:CLASS|CL\.?)\s*(?P<clase_pre>\d{3,4})|(?P<clase>\d{3,4})\s*#)\s*"
    r"(?P<cara>RF|RTJ|FF|SO-RF|WN-RF|RFWN|RFLWN)?\s*(?P<servicio>[A-Z][A-Z /().-]{2,40})?$",
    re.I,
)


def _lineas(page):
    """(texto, caja, caracteres): filas horizontales con sus letras y rótulos girados."""
    for linea in page.extract_text_lines(return_chars=True):
        texto = linea["text"].translate(_COMILLAS)
        yield texto, (linea["x0"], linea["top"], linea["x1"], linea["bottom"]), linea["chars"]
    for texto, caja in rotados(page):
        yield texto.translate(_COMILLAS), caja, None


def _tramo(caja, texto, dato, letras):
    """Caja del fragmento citado dentro de una fila: una fila puede cruzar media lámina.

    Se alinea cada letra con su posición en el texto de la fila (pdfplumber añade espacios
    que no son letras) y se toma la caja de las letras del fragmento.
    """
    if not letras:
        return caja
    desde, posiciones = 0, []
    for letra in letras:
        simbolo = letra["text"].translate(_COMILLAS)
        posicion = texto.find(simbolo, desde)
        if posicion < 0:
            break
        posiciones.append((posicion, letra))
        desde = posicion + len(simbolo)
    dentro = [letra for posicion, letra in posiciones if dato.start() <= posicion < dato.end()]
    if not dentro:
        return caja
    return (
        min(letra["x0"] for letra in dentro),
        min(letra["top"] for letra in dentro),
        max(letra["x1"] for letra in dentro),
        max(letra["bottom"] for letra in dentro),
    )


def _cita(page, documento, caja, texto, regla, confianza=CONFIANZA):
    x0, y0, x1, y1 = caja
    return {
        "document_id": documento,
        "page": page.page_number,
        "bbox": [
            max(0.0, x0 / page.width),
            max(0.0, y0 / page.height),
            min(1.0, x1 / page.width),
            min(1.0, y1 / page.height),
        ],
        "locator": texto[:120],
        "text_original": texto[:200],
        "confidence": confianza,
        "rule": regla,
    }


def _rutas(tipo):
    if tipo == "horizontal_vessel":
        return {"diametro": "horizontal.diameter", "longitud": "horizontal.length"}
    return {"diametro": "diameter", "longitud": "height"}


def _boquillas(page, documento, lineas):
    """Filas de boquillas debajo de una cabecera reconocible, en la misma columna."""
    salida = []
    filas = sorted(((t, c) for t, c, _ in lineas), key=lambda par: (par[1][1], par[1][0]))
    cabeceras = [(t, c) for t, c in filas if _CABECERA.search(normalizar(t))]
    for _, cabecera in cabeceras:
        izquierda = cabecera[0] - 0.02 * page.width
        for texto, caja in filas:
            if caja[1] <= cabecera[3] or abs(caja[0] - cabecera[0]) > 0.04 * page.width:
                continue
            if caja[1] - cabecera[3] > 0.5 * page.height or caja[0] < izquierda - page.width:
                break
            dato = _FILA.match(texto.strip())
            if not dato:
                continue
            cantidad = int(dato["cantidad"]) if dato["cantidad"] else None
            marca = re.sub(r"\s+", "", dato["marca"].upper())
            marcas = (
                [marca]
                if re.fullmatch(r"[A-Z]{1,3}\d{0,3}[A-Z]?", marca) and cantidad in (None, 1)
                else expandir_marcas(marca, cantidad)
            )
            if not marcas:
                continue
            tamano = float(sum(Fraction(p) for p in dato["tamano"].split()))
            clase = dato["clase"] or dato["clase_pre"]
            cita = _cita(page, documento, caja, texto, "texto.tabla_boquillas_otro_formato")
            for m in marcas:
                ruta = f"nozzles.{m}."
                salida.append(
                    {
                        "path": ruta + "size_nps",
                        "value": tamano,
                        "unit": "in",
                        "source": cita,
                        "channel": "tabla",
                    }
                )
                if (exterior := NPS_OUTSIDE_DIAMETER_MM.get(tamano)) is not None:
                    salida.append(
                        {
                            "path": ruta + "diameter",
                            "value": exterior,
                            "unit": "mm",
                            "source": cita,
                            "explanation": "Diámetro exterior según ASME B36.10",
                        }
                    )
                salida.append(
                    {"path": ruta + "rating", "value": f"{clase}#", "unit": "1", "source": cita}
                )
                if dato["cara"]:
                    salida.append(
                        {
                            "path": ruta + "facing",
                            "value": dato["cara"].upper(),
                            "unit": "1",
                            "source": cita,
                        }
                    )
                if dato["servicio"]:
                    salida.append(
                        {
                            "path": ruta + "service",
                            "value": dato["servicio"].strip(),
                            "unit": "1",
                            "source": cita,
                        }
                    )
    return salida


def leer(pdf: bytes, documento: str, tipo: str | None) -> list[dict]:
    """Candidatos de los formatos de otros fabricantes, con valor único por clave."""
    hallados: dict[str, dict] = {}
    repetidos: set[str] = set()
    boquillas = []
    marcas_tipo: dict[str, tuple] = {}

    def apuntar(clave, valor, cita, explicacion):
        if valor is None:
            return
        previo = hallados.get(clave)
        if previo is not None and previo["value"] != valor:
            repetidos.add(clave)
        elif previo is None:
            hallados[clave] = {"value": valor, "source": cita, "explanation": explicacion}

    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            lineas = list(_lineas(page))
            for texto, caja, letras in lineas:
                canon = normalizar(texto)
                for patron, lector, regla, explicacion in _PATRONES:
                    for dato in patron.finditer(texto):
                        tramo = _tramo(caja, texto, dato, letras)
                        cita = _cita(page, documento, tramo, dato[0], regla)
                        for clave, valor in lector(dato).items():
                            apuntar(clave, valor, cita, explicacion)
                for clave, patron in (
                    ("horizontal", _HORIZONTAL),
                    ("vertical", _VERTICAL),
                    ("patas", _PATAS),
                    ("faldon", _FALDON),
                ):
                    if clave not in marcas_tipo and patron.search(canon):
                        marcas_tipo[clave] = _cita(page, documento, caja, texto, f"texto.{clave}")
                if dato := _ITEM.search(canon):
                    apuntar(
                        "tag",
                        dato[1],
                        _cita(page, documento, caja, texto, "texto.item_no"),
                        "Tag del equipo en el campo «ITEM NO.».",
                    )
            boquillas.extend(_boquillas(page, documento, lineas))
            page.close()

    salida = []
    if "horizontal" in marcas_tipo and "vertical" not in marcas_tipo:
        tipo = tipo or "horizontal_vessel"
        salida.append(
            {
                "path": "attributes.equipment_type",
                "value": "horizontal_vessel",
                "unit": "1",
                "source": marcas_tipo["horizontal"],
                "explanation": "Tipología escrita en el título del plano.",
            }
        )
    elif "vertical" in marcas_tipo and "horizontal" not in marcas_tipo:
        salida.append(
            {
                "path": "attributes.equipment_type",
                "value": "vertical_vessel",
                "unit": "1",
                "source": marcas_tipo["vertical"],
                "explanation": "Tipología escrita en el título del plano.",
            }
        )
    if tipo != "horizontal_vessel":
        for clave, valor in (("patas", "legs"), ("faldon", "skirt")):
            otra = "faldon" if clave == "patas" else "patas"
            if clave in marcas_tipo and otra not in marcas_tipo:
                salida.append(
                    {
                        "path": "attributes.support",
                        "value": valor,
                        "unit": "1",
                        "source": marcas_tipo[clave],
                        "explanation": "Tipo de apoyo rotulado en el plano.",
                    }
                )
    rutas = _rutas(tipo)
    for clave, dato in hallados.items():
        if clave in repetidos:
            continue
        if clave == "tag":
            salida.append({"path": "tag", "unit": "1", **dato})
        elif clave == "base":
            if "diametro" in hallados and "diametro" not in repetidos:
                salida.append({"path": "attributes.diameter_basis", "unit": "1", **dato})
        elif clave in rutas:
            salida.append({"path": rutas[clave], "unit": "mm", "channel": "cota", **dato})
    vistos = set()
    for dato in boquillas:
        if dato["path"] not in vistos:
            vistos.add(dato["path"])
            salida.append(dato)
    return salida

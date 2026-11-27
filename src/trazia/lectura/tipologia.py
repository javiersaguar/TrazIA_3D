"""Indicios de familia, soporte y masas que se pueden citar en un GA."""

import re
import unicodedata

from trazia.units import UnitError, normalize

_TIPOS = (
    ("pump", r"^(?:(?:CENTRIFUGAL|RECIPROCATING|SCREW)\s+PUMP|BOMBA\s+CENTRIFUGA)(?:\s|$)", 100),
    (
        "compressor",
        r"^(?:(?:CENTRIFUGAL|RECIPROCATING|SCREW)\s+COMPRESSOR|COMPRESOR\s+CENTRIFUGO)(?:\s|$)",
        100,
    ),
    (
        "heat_exchanger",
        r"^(?:(?:SHELL.AND.TUBE\s+)?HEAT EXCHANGER|INTERCAMBIADOR DE CALOR)(?:\s|$)",
        100,
    ),
    ("air_cooler", r"^(?:AIR COOLER|AEROENFRIADOR)(?:\s|$)", 100),
    ("fan", r"^(?:AXIAL FAN|CENTRIFUGAL FAN|VENTILADOR AXIAL)(?:\s|$)", 100),
    ("agitator", r"^(?:MECHANICAL AGITATOR|AGITADOR MECANICO)(?:\s|$)", 100),
    ("filter", r"^(?:FILTER SKID|FILTRO PRENSA)(?:\s|$)", 100),
    (
        "horizontal_vessel",
        r"\b(?:HORIZONTAL VESSEL|RECIPIENTE HORIZONTAL|VESSEL POSTURE\s*[:=-]?\s*HORIZONTAL)\b",
        95,
    ),
    ("vertical_vessel", r"\b(?:VERTICAL VESSEL|RECIPIENTE VERTICAL)\b", 95),
    (
        "column",
        r"\b(?:STRIPPER|FRACTIONATOR|DEBUTANI[ZS]ER|(?:AMINE\s+)?ABSORBER|"
        r"(?:WASH|DISTILLATION|ABSORPTION) TOWER|COLUMNA DE (?:DESTILACION|ABSORCION))\b",
        98,
    ),
    ("column", r"\b(?:ACROSS THE COLUMN|TRAY\s*#?\d+|\d+(?:ST|ND|RD|TH) TRAY)\b", 87),
    ("tank", r"\b(?:API\s*650|FLOATING ROOF|GENERAL VIEW TANK|FIXED ROOF TANK)\b", 98),
    ("tank", r"\b(?:TANK (?:INSIDE|SHELL|ROOF|FOUNDATION)|TANQUE DE ALMACENAMIENTO)\b", 88),
    # Equipos rotativos: sus normas no salen en el plano de un recipiente. Prioridad por debajo de
    # cualquier indicio de recipiente, para que una nota suelta no cambie la familia.
    (
        "pump",
        r"\bAPI\s*(?:610|674|675|676|682|685)\b|\b(?:CENTRIFUGAL|IN-?LINE) PUMP\b|"
        r"\bBOMBA CENTRIFUGA\b",
        80,
    ),
    (
        "compressor",
        r"\bAPI\s*(?:617|618|619)\b|\b(?:CENTRIFUGAL|RECIPROCATING|SCREW) COMPRESSOR\b",
        80,
    ),
)

_EQUIPOS_FUERA_DE_ALCANCE = {
    "PUMP": "pump",
    "BOMBA": "pump",
    "COMPRESSOR": "compressor",
    "COMPRESOR": "compressor",
    "HEAT EXCHANGER": "heat_exchanger",
    "INTERCAMBIADOR": "heat_exchanger",
    "FILTER": "filter",
    "FILTRO": "filter",
    "FAN": "fan",
    "VENTILADOR": "fan",
}

_SOPORTES = (
    ("saddles", r"\b(?:FIXED|SLIDING) SADDLES?\b|^\(?SADDLE(?:S|\s+C/C)?\)?$", 94),
    ("saddles", r"^\s*(?:DETAIL )?(?:SADDLE SUPPORTS?|SILLETAS?|CUNAS?)\b", 86),
    (
        "legs",
        r'\b(?:DETAIL\s+"?LEGS?"?|SUPPORT LEGS|DETALLE\s+"?PATAS?"?|ONE LEG AT BASE)\b',
        94,
    ),
    ("skirt", r"^\s*(?:DETAIL\s+)?(?:SKIRTS?|FALDON)(?:\b|O\.?\s*D\.?)", 90),
    ("skirt", r"\b(?:ANILLO FALDON|BASE RING OF THE SKIRT|CORROSION FALDON)\b", 84),
    ("none", r"\b(?:TOP EDGE OF TANK FOUNDATION|TANK BOTTOM (?:ON|AT) FOUNDATION)\b", 90),
)

_MASAS = {
    "EMPTY": "empty",
    "VACIO": "empty",
    "OPERATING": "operating",
    "OPERACION": "operating",
    "FIELD HYDROTEST": "test",
    "HYDROTEST": "test",
    "PRUEBA HIDROSTATICA": "test",
    "TRANSPORTATION": "transport",
    "TRANSPORT": "transport",
    "TRANSPORTE": "transport",
    "FABRICATION": "fabrication",
}
_UNIDAD = r"(?P<unidad>kgs?\.?|t|lbs?)"
_PESO = r"WEIG(?:HT|TH)"  # «Weigth» aparece así en algún GA real
_VALOR = r"([0-9]+(?:[.,][0-9]+)?)"
_MASA_SIMPLE = re.compile(
    rf"(?<!\w)(?P<clase>{'|'.join(_MASAS)})\s+{_PESO}\s*"
    rf"[:=]?\s*\(?{_UNIDAD}\)?\s*[:=]?\s*(?P<valor>{_VALOR})\b",
    re.I,
)
# Fila sin unidad: solo cuenta si la página tiene «WEIGHT TABLE (Kgs.)» o «TABLA DE PESOS (kg)».
_MASA_SIN_UNIDAD = re.compile(
    rf"(?<!\w)(?P<clase>{'|'.join(_MASAS)})\s+{_PESO}\s*[:=]?\s*(?P<valor>[0-9]+(?:[.,][0-9]+)?)"
    r"(?![0-9.,]|\s*(?:KG|T\b|LB|%|/))",
    re.I,
)
_TABLA_KG = re.compile(r"\b(?:WEIGHT TABLE|TABLA DE PESOS)\s*\(\s*KGS?\.?\s*\)", re.I)
_MASAS_ES = {
    "FABRICADO": "fabrication",
    "EN VACIO": "empty",
    "VACIO": "empty",
    "EN OPERACION": "operating",
    "OPERACION": "operating",
    "PRUEBA HIDRAULICA": "test",
    "PRUEBA HIDROSTATICA": "test",
    "TRANSPORTE": "transport",
}
_MASA_ES = re.compile(
    rf"\bPESO\s+(?:DE\s+)?(?P<clase>{'|'.join(_MASAS_ES)})(?:\s+(?:TALLER|CAMPO|OBRA))?\s*"
    rf"[:=]?\s*(?P<valor>[0-9]+(?:[.,][0-9]+)?)\s*(?P<unidad>KG|T)\b"
)
_MASA_TRIPLE = re.compile(
    rf"\bWEIGHT EMPTY\s*/\s*OPERATION\s*/\s*FULL\s*"
    rf"\(?{_UNIDAD}\)?\s*{_VALOR}\s*/\s*{_VALOR}\s*/\s*{_VALOR}\b",
    re.I,
)


def normalizar(texto):
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto.upper()) if not unicodedata.combining(c)
    )


def indicios_tipologia(lineas, filas):
    """Devuelve candidatos y prioridad a partir de texto con caja en puntos PDF."""
    for texto, caja in lineas:
        canon = normalizar(texto)
        declarado = re.fullmatch(r"(?:EQUIPMENT TYPE|TIPO DE EQUIPO)\s*[:=]\s*(.+)", canon)
        if declarado and (tipo := _EQUIPOS_FUERA_DE_ALCANCE.get(declarado[1])):
            yield "equipment_type", tipo, 100, texto, caja
        for campo, reglas in (("equipment_type", _TIPOS), ("support", _SOPORTES)):
            for valor, patron, prioridad in reglas:
                if re.search(patron, canon):
                    yield campo, valor, prioridad, texto, caja

    # VESSEL POSTURE y el valor suelen estar en celdas separadas de la misma fila.
    for texto, caja in filas:
        canon = normalizar(texto)
        postura = re.search(r"\bVESSEL POSTURE\s*[:=-]?\s*(HORIZONTAL|VERTICAL)\b", canon)
        if postura:
            yield "equipment_type", f"{postura[1].lower()}_vessel", 96, texto, caja


def masas_ga(filas):
    filas = list(filas)
    tabla_kg = any(_TABLA_KG.search(texto) for texto, _ in filas)
    for texto, caja in filas:
        if triple := _MASA_TRIPLE.search(texto):
            for campo, valor in zip(
                ("empty", "operating", "full"), triple.groups()[1:], strict=True
            ):
                yield from _masa(campo, valor, triple["unidad"], triple[0], caja)
        for dato in _MASA_SIMPLE.finditer(texto):
            yield from _masa(
                _MASAS[dato["clase"].upper()], dato["valor"], dato["unidad"], dato[0], caja
            )
        if tabla_kg and not _MASA_SIMPLE.search(texto):
            for dato in _MASA_SIN_UNIDAD.finditer(texto):
                yield from _masa(_MASAS[dato["clase"].upper()], dato["valor"], "kg", dato[0], caja)
        canon = normalizar(texto)
        for dato in _MASA_ES.finditer(canon):
            # La cita es el texto tal cual está en el plano, con sus tildes.
            cita = texto[dato.start() : dato.end()] if len(canon) == len(texto) else texto
            clase = _MASAS_ES[dato["clase"]]
            yield from _masa(clase, dato["valor"], dato["unidad"], cita, caja)


def _masa(campo, valor, unidad, texto, caja):
    unidad = unidad.lower().rstrip(".")
    unidad = "kg" if unidad == "kgs" else unidad
    try:
        kg = normalize(f"{valor} {unidad}", "mass").value
    except UnitError:
        return
    yield f"attributes.weight_{campo}", kg, texto, caja

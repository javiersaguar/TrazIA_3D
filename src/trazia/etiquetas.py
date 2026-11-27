"""Nombre legible de cada campo del contrato, el mismo de `web/src/lib/field-labels.ts`.

Norma: frase en español con mayúscula inicial. Un campo de una pieza repetida se nombra
«Pieza marca · magnitud» («Boquilla M1 · Elevación», «Virola V03 · Espesor»). Una ruta que no
está en la tabla se nombra a partir de sus partes, nunca en bruto.
"""

import re

DIRECTOS = {
    "tag": "Tag del equipo",
    "diameter": "Diámetro de la virola",
    "height": "Longitud entre tangentes",
    "head_depth": "Profundidad del fondo",
    "skirt_height": "Altura del faldón",
    "skirt_thickness": "Espesor del faldón",
    "legs.height": "Altura de las patas",
    "legs.count": "Número de patas",
    "horizontal.diameter": "Diámetro de la virola",
    "horizontal.length": "Longitud entre tangentes",
    "horizontal.head_depth": "Profundidad del fondo",
    "horizontal.support_height": "Altura de la silleta al eje",
    "horizontal.saddle_width": "Ancho de silleta",
    "horizontal.saddle_span": "Ancho transversal de silleta",
    "tank.diameter": "Diámetro del tanque",
    "tank.height": "Altura de la envolvente del tanque",
    "tank.roof": "Tipo de techo",
    "tank.roof_height": "Flecha del techo",
}

MAGNITUDES = {
    "azimuth": "Orientación",
    "bearing": "Rumbo",
    "code": "Código",
    "count": "Número",
    "development": "Desarrollo",
    "diameter": "Diámetro",
    "elevation": "Elevación",
    "elevation_mm": "Elevación",
    "facing": "Cara de brida",
    "flange_type": "Tipo de brida",
    "height": "Altura",
    "joins": "Piezas que une",
    "kind": "Tipo",
    "material": "Material",
    "order": "Orden de abajo arriba",
    "projection": "Proyección",
    "projection_basis": "Referencia de la proyección",
    "rating": "Clase de brida",
    "schedule": "Schedule",
    "service": "Servicio",
    "size_nps": "Tamaño nominal",
    "station": "Posición",
    "thickness": "Espesor",
    "value": "Valor",
}

ATRIBUTOS = {
    "anchor_bolts": "Pernos de anclaje",
    "body_flange_thickness": "Espesor de la brida de cuerpo",
    "capacity": "Capacidad",
    "capacity_working": "Capacidad de trabajo",
    "cog_elevation": "Elevación del centro de gravedad",
    "column_head_depth_bottom": "Profundidad del fondo inferior",
    "column_head_depth_top": "Profundidad del fondo superior",
    "cog_elevation_operating": "Elevación del centro de gravedad en operación",
    "corrosion_allowance": "Sobreespesor de corrosión",
    "design_pressure": "Presión de diseño",
    "design_temperature": "Temperatura de diseño",
    "diameter_basis": "Referencia del diámetro",
    "equipment_type": "Tipo de equipo",
    "head_straight_flange": "Faldilla recta del fondo",
    "head_type": "Tipo de fondo",
    "heads_thickness": "Espesor de los fondos",
    "height_to_flange": "Altura de tangente a cara de brida",
    "hydrotest_pressure": "Presión de prueba hidráulica",
    "insulation": "Aislamiento",
    "insulation_thickness": "Espesor del aislamiento",
    "material": "Material",
    "material_body_flange": "Material de la brida de cuerpo",
    "material_heads": "Material de los fondos",
    "material_nozzle_flanges": "Material de las bridas de boquilla",
    "material_shell": "Material de la virola",
    "material_skirt": "Material del faldón",
    "mawp": "Presión máxima admisible (MAWP)",
    "mdmt": "Temperatura mínima de diseño (MDMT)",
    "operating_pressure": "Presión de operación",
    "operating_temperature": "Temperatura de operación",
    "operating_weight": "Peso en operación",
    "pwht": "Tratamiento térmico postsoldadura",
    "saddle_width_fixed": "Ancho de la silleta fija",
    "saddle_width_sliding": "Ancho de la silleta deslizante",
    "shell_height": "Altura de la virola",
    "shell_thickness": "Espesor de la virola",
    "shell_thicknesses": "Espesores de virola",
    "skirt_diameter": "Diámetro del faldón",
    "skirt_thickness": "Espesor del faldón",
    "support": "Tipo de soporte",
    "support_height_basis": "Referencia de la altura de silleta",
    "upper_closure": "Cierre superior",
    "weight_empty": "Peso en vacío",
    "weight_fabrication": "Peso de fabricación",
    "weight_full": "Peso lleno de agua",
    "weight_operating": "Peso en operación",
    "weight_test": "Peso en prueba",
    "weight_transport": "Peso de transporte",
}

_PIEZAS = (
    (re.compile(r"^nozzles\.([^.]+)\.(.+)$"), lambda m: f"Boquilla {m}"),
    (
        re.compile(r"^welds\.([^.]+)\.(.+)$"),
        lambda m: "Soldadura " + m.removeprefix("W:").replace("|", " – "),
    ),
    (re.compile(r"^shell\.courses\.([^.]+)\.(.+)$"), lambda m: f"Virola {m}"),
    (re.compile(r"^column\.sections\.([^.]+)\.(.+)$"), lambda m: f"Tramo de columna {m}"),
    (re.compile(r"^tank\.courses\.([^.]+)\.(.+)$"), lambda m: f"Virola {m} del tanque"),
)


def _humano(texto: str) -> str:
    limpio = re.sub(r"[_-]+", " ", texto).strip()
    return limpio[:1].upper() + limpio[1:] if limpio else texto


def _magnitud(clave: str) -> str:
    return MAGNITUDES.get(clave) or _humano(clave)


def etiqueta(path: str) -> str:
    if path in DIRECTOS:
        return DIRECTOS[path]
    if path.startswith("attributes."):
        clave = path.removeprefix("attributes.")
        return ATRIBUTOS.get(clave) or _humano(clave)
    if dato := re.fullmatch(r"horizontal\.saddle_positions\.(\d+)", path):
        return f"Silleta {int(dato[1]) + 1} · Posición"
    if dato := re.fullmatch(r"envelope\.(origin|size)\.([xyz])", path):
        return f"{'Origen' if dato[1] == 'origin' else 'Dimensión'} {dato[2].upper()}"
    for patron, pieza in _PIEZAS:
        if dato := patron.match(path):
            return f"{pieza(dato[1])} · {_magnitud(dato[2].split('.')[-1])}"
    partes = path.split(".")
    if len(partes) > 1:
        return f"{_humano(partes[0])} · {_magnitud(partes[-1])}"
    return _magnitud(path)

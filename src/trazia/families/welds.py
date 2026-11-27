"""Geometría de las uniones soldadas para el IFC (M5, plan 7.5).

Cada soldadura es un anillo fino: a la cota de la costura en una circunferencial y en la
intersección con la virola en una de boquilla. Una longitudinal es un tramo a lo largo de la
generatriz. Si los datos no fijan la posición, no hay geometría: la soldadura sigue en el IFC,
sin representación, para que el JSON y el IFC tengan las mismas.
"""

import math

from ..model import Equipment, Weld
from . import Solid, nozzle_frame

ANCHO_MM = 20.0  # ancho del cordón dibujado a lo largo del eje de la pieza
ESPESOR_MM = 8.0  # cuánto sobresale de la superficie, para que se vea sobre la virola


def _diametro_en(equipment: Equipment, cota: float) -> float | None:
    """Diámetro exterior a `cota` mm desde la T.L. inferior, o None si no se conoce."""
    if equipment.lod == 1:
        return None
    if equipment.horizontal is not None:
        return equipment.horizontal.diameter.value
    if equipment.tank is not None:
        return equipment.tank.diameter.value
    if equipment.column is not None:
        z = 0.0
        for section in equipment.column.sections:
            z += section.height.value
            if cota <= z + 1e-6:
                return (section.top_diameter or section.diameter).value
        return equipment.column.sections[-1].diameter.value
    return equipment.diameter.value if equipment.diameter else None


def _base(equipment: Equipment) -> float:
    """Cota en mm de la T.L. inferior sobre el suelo (verticales, columnas y tanques)."""
    if equipment.tank is not None:
        return 0.0
    return equipment.shell_bottom


def weld_solid(equipment: Equipment, weld: Weld) -> Solid | None:
    kind = weld.kind.value
    if kind == "nozzle":
        nozzle = next((n for n in equipment.nozzles if n.id in weld.joins), None)
        if nozzle is None:
            return None
        origin, direction = nozzle_frame(equipment, nozzle)
        return Solid(
            "cylinder",
            origin=tuple(o - d * ANCHO_MM / 2000 for o, d in zip(origin, direction, strict=True)),
            direction=direction,
            diameter=nozzle.diameter.value + 2 * ESPESOR_MM,
            length=ANCHO_MM,
            thickness=ESPESOR_MM,
        )
    if weld.elevation is None:
        return None
    cota = weld.elevation.value
    diametro = _diametro_en(equipment, cota)
    if diametro is None:
        return None
    exterior = diametro + 2 * ESPESOR_MM
    if equipment.horizontal is not None:
        p = equipment.horizontal
        centro = (p.support_height.value + p.diameter.value / 2) / 1000
        if kind == "circumferential":
            return Solid(
                "cylinder",
                origin=((cota - ANCHO_MM / 2) / 1000, 0.0, centro),
                direction=(1.0, 0.0, 0.0),
                diameter=exterior,
                length=ANCHO_MM,
                thickness=ESPESOR_MM,
            )
        return None
    z = (_base(equipment) + cota) / 1000
    if kind == "circumferential":
        return Solid(
            "cylinder",
            origin=(0.0, 0.0, z - ANCHO_MM / 2000),
            diameter=exterior,
            length=ANCHO_MM,
            thickness=ESPESOR_MM,
        )
    if kind == "longitudinal" and weld.azimuth is not None and equipment.height is not None:
        angulo = math.radians(weld.azimuth.value)
        radio = (diametro / 2 + ESPESOR_MM / 2) / 1000
        lado = ANCHO_MM / 1000
        return Solid(
            "box",
            origin=(
                radio * math.cos(angulo) - lado / 2,
                radio * math.sin(angulo) - lado / 2,
                _base(equipment) / 1000,
            ),
            size=(lado, lado, equipment.height.value / 1000),
        )
    return None

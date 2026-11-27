"""Colocación radial en los tramos cilíndricos de equipos verticales."""

import math

from ..model import nozzle_misfit
from .geometry import derived_field


def _number(field, unit):
    return field["unit"] == unit and isinstance(field["value"], int | float)


def _cited_reference(reference, reading, allowed):
    return (
        reference is not None
        and reference["state"] not in ("abstained", "conflict")
        and reference["value"] in allowed
        and reference["source"]["document_id"] == reading["source"]["document_id"]
    )


def radial_shell_nozzle(equipment, nozzle, references):
    elevation, azimuth, diameter, projection = (
        nozzle[key] for key in ("elevation", "azimuth", "diameter", "projection")
    )
    level = references.get("elevation_ref")
    basis = references.get("projection_basis")
    if (
        not _cited_reference(level, elevation, ("grade", "lower_tl"))
        or not _cited_reference(basis, projection, ("axis", "shell"))
        or references.get("nozzle_type", {}).get("value", "radial") != "radial"
        or any(
            references.get(key, {}).get("value", 0) != 0
            for key in ("offset_lateral", "offset_lateral_mm")
        )
        or not _number(azimuth, "deg")
        or not 0 <= azimuth["value"] < 360
        or not all(_number(field, "mm") for field in (elevation, diameter, projection))
        or diameter["value"] <= 0
    ):
        return None

    support_height = equipment.get("skirt_height") or equipment.get("legs", {}).get("height")
    if support_height is not None and not _number(support_height, "mm"):
        return None
    bottom = support_height["value"] if support_height is not None else 0
    if level["value"] == "lower_tl":
        elevation = derived_field(
            elevation["value"] + bottom,
            "mm",
            "virola.cota_desde_tangente",
            "Cota desde tangente inferior más altura de apoyo.",
            elevation,
            level,
            *((support_height,) if support_height is not None else ()),
        )
    z = elevation["value"]
    sections = (
        equipment["column"]["sections"]
        if "column" in equipment
        else [equipment.get("tank", equipment)]
    )
    for section in sections:
        height, outer = section["height"], section["diameter"]
        top = section.get("top_diameter", outer)
        if not all(_number(field, "mm") for field in (height, outer, top)):
            return None
        if (
            top["value"] == outer["value"]
            and nozzle_misfit(diameter["value"], z, outer["value"], bottom, height["value"]) is None
        ):
            return _place(nozzle, elevation, azimuth, projection, basis, outer)
        bottom += height["value"]
    return None


def _place(nozzle, elevation, azimuth, projection, basis, outer):
    radius = outer["value"] / 2
    if basis["value"] == "axis":
        projection = derived_field(
            projection["value"] - radius,
            "mm",
            "virola.proyeccion_desde_eje",
            "Proyección desde el eje menos el radio exterior.",
            projection,
            basis,
            outer,
        )
    if projection["value"] <= 0:
        return None
    angle = math.radians(azimuth["value"])
    x, y = math.cos(angle), math.sin(angle)
    rule = "virola.boquilla_radial"
    orientation = "Azimut interno desde +X en sentido antihorario visto desde +Z."
    return {
        **nozzle,
        "nozzle_type": "radial",
        "elevation": elevation,
        "projection": projection,
        "position": {
            "x": derived_field(radius * x, "mm", rule, orientation, azimuth, outer),
            "y": derived_field(radius * y, "mm", rule, orientation, azimuth, outer),
            "z": elevation.copy(),
        },
        "direction": {
            axis: derived_field(value, "1", rule, orientation, azimuth)
            for axis, value in zip("xyz", (x, y, 0), strict=True)
        },
    }

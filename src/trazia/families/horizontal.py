"""Coordenadas y cotas trazadas de recipientes horizontales."""

import json
import math

from ..model import HorizontalParameters
from .geometry import derived_field as _derived
from .geometry import outer_diameter


def normalized_dimensions(dimensions, attributes):
    """Convierte a diámetro exterior y altura del suelo a la cara inferior de la virola."""
    dimensions["diameter"] = outer_diameter(dimensions["diameter"], attributes, "horizontal")

    height_basis = attributes.get("support_height_basis", {}).get("value", "shell_bottom")
    if height_basis == "axis":
        height = dimensions["support_height"]
        diameter = dimensions["diameter"]
        if not isinstance(height["value"], int | float) or height["unit"] != "mm":
            raise ValueError("La altura del eje debe ser numérica en mm")
        if not isinstance(diameter["value"], int | float) or diameter["unit"] != "mm":
            raise ValueError("El diámetro exterior debe ser numérico en mm")
        dimensions["support_height"] = _derived(
            height["value"] - diameter["value"] / 2,
            "mm",
            "horizontal.apoyo_desde_eje",
            "Cota al eje menos el radio exterior.",
            height,
            diameter,
            attributes["support_height_basis"],
        )
    elif height_basis != "shell_bottom":
        raise ValueError("No se conoce la referencia de la altura de apoyo horizontal")
    return HorizontalParameters.model_validate_json(json.dumps(dimensions))


def saddle_profile_dimensions(equipment, index):
    """Las dimensiones de la base y de cada silleta pueden diferir de las del asiento."""
    geometry = equipment.horizontal
    width = equipment.attributes.get(f"saddle_width_{index}")
    span = equipment.attributes.get("saddle_base_span")
    width = width if width is not None and width.state != "abstained" else geometry.saddle_width
    span = span if span is not None and span.state != "abstained" else geometry.saddle_span
    for field in (width, span):
        if field.unit != "mm" or not isinstance(field.value, int | float) or field.value <= 0:
            raise ValueError("La base de la silleta necesita cotas positivas en mm")
    return width, span


def radial_nozzle(geometry, nozzle, references):
    """Coloca una boquilla de virola radial o vertical con desplazamiento acotado."""
    station, angle, projection, diameter = (
        nozzle[key] for key in ("station", "azimuth", "projection", "diameter")
    )
    basis = references.get("projection_basis")
    if (
        basis is None
        or basis["state"] == "abstained"
        or basis["source"]["document_id"] != projection["source"]["document_id"]
        or basis["value"] not in ("axis", "shell", "horizontal_ref")
        or references.get("nozzle_type", {}).get("value", "radial") != "radial"
        or references.get("offset_lateral", {}).get("value", 0) != 0
    ):
        return None
    fields = ((station, "mm"), (angle, "deg"), (projection, "mm"), (diameter, "mm"))
    if any(
        field["unit"] != unit or not isinstance(field["value"], int | float)
        for field, unit in fields
    ):
        return None

    x, azimuth, projection_mm, diameter_mm = (field["value"] for field, _ in fields)
    vessel_diameter = geometry.diameter.value
    radius = vessel_diameter / 2
    nozzle_radius = diameter_mm / 2
    if not (
        0 <= azimuth < 360
        and 0 < diameter_mm < vessel_diameter
        and nozzle_radius <= x <= geometry.length.value - nozzle_radius
    ):
        return None
    lateral = references.get("offset_lateral_mm")
    offset = lateral["value"] if lateral else 0
    if not isinstance(offset, int | float):
        return None
    if offset and (
        lateral["unit"] != "mm"
        or lateral["state"] in ("abstained", "conflict")
        or lateral["source"].get("rule") != "horizontal.desplazamiento_en_seccion"
        or lateral["source"]["document_id"] != angle["source"]["document_id"]
        or azimuth not in (0, 180)
        or abs(offset) + nozzle_radius >= radius
    ):
        return None
    distancia_a_virola = math.sqrt(radius**2 - offset**2)
    axis_projection = basis["value"] != "shell"
    if axis_projection:
        projection_mm -= distancia_a_virola
    datum = references.get("projection_datum_offset")
    if basis["value"] == "horizontal_ref":
        if (
            datum is None
            or datum["source"]["document_id"] != basis["source"]["document_id"]
            or datum["state"] in ("abstained", "conflict")
            or datum["unit"] != "mm"
            or not isinstance(datum["value"], int | float)
            or azimuth not in (0, 180)
        ):
            return None
        projection_mm += (1 if azimuth == 0 else -1) * datum["value"]
    if projection_mm <= 0:
        return None

    radial_y, radial_z = math.sin(math.radians(azimuth)), math.cos(math.radians(azimuth))
    center = geometry.support_height.value + radius
    diameter_trace = geometry.diameter.model_dump(mode="json")
    support_trace = geometry.support_height.model_dump(mode="json")
    rule = "horizontal.boquilla_radial"
    orientation = "Ángulo de cabezal: 0° hacia +Z y 90° hacia +Y."
    elevation = _derived(
        center + distancia_a_virola * radial_z,
        "mm",
        rule,
        "Cota del eje más la componente vertical radial.",
        angle,
        diameter_trace,
        support_trace,
        *([lateral] if offset else []),
    )
    if basis["value"] == "horizontal_ref":
        projection = _derived(
            projection_mm,
            "mm",
            "horizontal.proyeccion_desde_linea_horizontal",
            "Distancia a la brida desde la línea horizontal, corregida por el desnivel local "
            "del eje y la cara exterior de la virola.",
            projection,
            basis,
            datum,
            angle,
            diameter_trace,
            *([lateral] if offset else []),
        )
    elif axis_projection:
        projection = _derived(
            projection_mm,
            "mm",
            "horizontal.proyeccion_desde_eje",
            "Proyección desde el eje menos la distancia hasta la cara exterior de la virola.",
            projection,
            basis,
            diameter_trace,
            *([lateral] if offset else []),
        )
    elif basis["state"] in ("assumed", "conflict"):
        projection = _derived(
            projection_mm,
            "mm",
            "horizontal.proyeccion_desde_virola",
            "La proyección se mide desde la cara exterior de la virola.",
            projection,
            basis,
        )
    result = {key: value for key, value in nozzle.items() if key != "station"}
    result.update(
        stable_id=nozzle["id"],
        nozzle_type=("top" if azimuth == 0 else "bottom") if offset else "radial",
        projection=projection,
        elevation=elevation,
        position={
            "x": station,
            "y": lateral
            if offset
            else _derived(radius * radial_y, "mm", rule, orientation, angle, diameter_trace),
            "z": elevation.copy(),
        },
        direction={
            axis: _derived(value, "1", rule, orientation, angle)
            for axis, value in zip("xyz", (0.0, radial_y, radial_z), strict=True)
        },
    )
    return result

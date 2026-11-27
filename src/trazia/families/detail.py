"""Detalle derivado para demostraciones sintéticas; no es un dimensionado mecánico.

Bridas: tablas ASME B16.5 y B16.47 (series A y B) de catálogos públicos, citadas por fila en
bridas_asme.json. No se extrapolan DN ni clases. El diámetro de boquilla es el nominal del
contrato; el bore y el resto de proporciones son representaciones, no selección de schedule.
"""

import math
from dataclasses import replace

from . import Part, Solid, nozzle_frame
from .bridas import (
    STANDARD_NAMES,
    FlangeDims,
    Resolution,
    nps_from_dn,
    parse_class,
    parse_nps,
    parse_standard,
    resolve,
)


def flange_pattern(dn, rating, standard=None, nps=None) -> FlangeDims | None:
    """Solo coincidencia exacta. Una clase no reconocida nunca se convierte a 150."""
    return resolve(nps if nps is not None else nps_from_dn(dn), parse_class(rating), standard).dims


def basis(direction):
    seed = (0.0, 0.0, 1.0) if abs(direction[2]) < 0.9 else (1.0, 0.0, 0.0)
    dot = sum(a * b for a, b in zip(seed, direction))
    x = tuple(a - dot * b for a, b in zip(seed, direction))
    length = math.sqrt(sum(v * v for v in x))
    x = tuple(v / length for v in x)
    y = (
        direction[1] * x[2] - direction[2] * x[1],
        direction[2] * x[0] - direction[0] * x[2],
        direction[0] * x[1] - direction[1] * x[0],
    )
    return x, y


def offset(point, direction, distance):
    return tuple(p + d * distance for p, d in zip(point, direction))


def bolt_holes(pattern: FlangeDims):
    return tuple(
        (
            pattern.pitch / 2000 * math.cos(2 * math.pi * (i + 0.5) / pattern.count),
            pattern.pitch / 2000 * math.sin(2 * math.pi * (i + 0.5) / pattern.count),
            pattern.hole / 2000,
        )
        for i in range(pattern.count)
    )


def derived(identifier, solids, *, parent, kind, properties=None):
    return Part(
        identifier,
        f"derived/{identifier}",
        tuple(solids),
        object_type=kind,
        parent_id=parent,
        properties={
            "Origen": "derivado_de_norma",
            "LeidoDelPlano": False,
            "RequiereVerificacion": True,
            "Alcance": "Patrón normativo cuando se indica Norma; resto paramétrico ilustrativo",
            **(properties or {}),
        },
    )


def norm_properties(dims: FlangeDims, *, assumed, standard_origin=""):
    return {
        "Norma": STANDARD_NAMES[dims.standard],
        "FuenteTabla": dims.source_url,
        "Clase": dims.pressure_class,
        "ClaseOrigen": "supuesto_visual" if assumed else "campo_trazado",
        "NormaOrigen": standard_origin or "deducida_por_tamano",
        "NPS": dims.nps,
        "Designacion": dims.label,
        "DiametroExterior_mm": dims.outside,
        "PCD_mm": dims.pitch,
        "NumeroTaladros": dims.count,
        "Taladro_mm": dims.hole,
    }


def bolt_parts(identifier, parent, dims, origin, direction, grip):
    """Espárragos en los taladros de la brida; envolventes ilustrativas, sin rosca."""
    result = []
    x, y = basis(direction)
    for i, (hx, hy, _) in enumerate(bolt_holes(dims)):
        point = tuple(p + hx * a + hy * b for p, a, b in zip(origin, x, y))
        shaft = Solid(
            "cylinder",
            origin=offset(point, direction, -0.006),
            direction=direction,
            diameter=dims.bolt,
            length=grip + 18,
        )
        head = Solid(
            "cylinder",
            origin=offset(point, direction, grip / 1000),
            direction=direction,
            diameter=dims.bolt * 1.6,
            length=dims.bolt * 0.65,
        )
        result.append(
            derived(
                f"{identifier}/bolt-{i + 1:02}",
                [shaft, head],
                parent=parent,
                kind="BOLT",
                properties={
                    "Norma": STANDARD_NAMES[dims.standard],
                    "FuenteTabla": dims.source_url,
                    "DiametroNominal_mm": round(dims.bolt, 3),
                    "Cabeza": "envolvente cilíndrica ilustrativa, sin rosca",
                    "Regla": "Perno 1/8 in menor que el taladro",
                },
            )
        )
    return result


def flange_parts(
    identifier,
    parent,
    dn,
    rating,
    origin,
    direction,
    *,
    assumed=False,
    blind=False,
    paired=False,
    dimensions=None,
    standard=None,
):
    """Placa taladrada de la brida y sus pernos. 'origin' es la cara trasera de la placa."""
    pattern = flange_pattern(dn, rating, standard)
    if pattern is None or pattern.thickness is None:
        return []
    outside, thickness = dimensions or (pattern.outside, pattern.thickness)
    if outside <= pattern.pitch + pattern.hole or outside <= dn or thickness <= 0:
        return []
    metadata = {
        **norm_properties(pattern, assumed=assumed),
        "DimensionesNormadas": "C,n,h; D y t leídos"
        if dimensions
        else "D,t,C,n,h; no rating presión/temperatura",
    }
    plate = Solid(
        "drilled",
        origin=origin,
        direction=direction,
        diameter=outside,
        length=thickness,
        thickness=None if blind else (outside - dn) / 2,
        holes=bolt_holes(pattern),
    )
    result = [
        derived(f"{identifier}/flange", [plate], parent=parent, kind="FLANGE", properties=metadata)
    ]
    grip = thickness * (2 if paired else 1) + (8 if paired else 0)
    return result + bolt_parts(identifier, parent, pattern, origin, direction, grip)


def weld_neck_parts(
    identifier,
    parent,
    dn,
    dims: FlangeDims,
    origin,
    direction,
    projection,
    *,
    assumed,
    standard_origin,
):
    """Brida de cuello soldado: cuello cónico, placa taladrada y cara realzada (RF).

    La cara realzada queda en el extremo de la proyección (plano de junta). El cuello baja
    hacia la envolvente la longitud de la tabla, recortado si la proyección es menor.
    """
    rf_h = dims.raised_face_height
    t = dims.thickness
    face = projection - rf_h  # mm desde la envolvente hasta la cara delantera de la placa
    back = face - t
    if back <= 0 or dims.outside <= dims.pitch + dims.hole or dims.outside <= dn:
        return []
    neck = dims.hub_length - t - rf_h
    start = max(0.0, back - neck)
    r_bevel, r_base = dims.hub_bevel / 2, dims.hub_base / 2
    r_start = r_base + (r_bevel - r_base) * (back - start) / neck if neck > 0 else r_base
    r_in = min(dn, dims.hub_bevel) / 2 * 0.92
    length = back - start
    solids = []
    if length > 0.5:
        solids.append(
            Solid(
                "revolved",
                origin=offset(origin, direction, start / 1000),
                direction=direction,
                points=tuple(
                    (r / 1000, z / 1000)
                    for r, z in ((r_in, 0.0), (r_start, 0.0), (r_base, length), (r_in, length))
                ),
            )
        )
    plate = Solid(
        "drilled",
        origin=offset(origin, direction, back / 1000),
        direction=direction,
        diameter=dims.outside,
        length=t,
        thickness=(dims.outside - dn) / 2,
        holes=bolt_holes(dims),
    )
    raised = Solid(
        "cylinder",
        origin=offset(origin, direction, face / 1000),
        direction=direction,
        diameter=dims.raised_face,
        length=rf_h,
        thickness=(dims.raised_face - dn) / 2,
    )
    properties = {
        **norm_properties(dims, assumed=assumed, standard_origin=standard_origin),
        "Tipo": "WN",
        "Cara": "RF",
        "CaraRealzada_mm": dims.raised_face,
        "AlturaCara_mm": rf_h,
        "Espesor_mm": t,
        "LongitudCuello_mm": dims.hub_length,
        "CuelloRecortado": back < neck,
        "DimensionesNormadas": "D,t,R,X,Y,A,C,n,h; no rating presión/temperatura",
    }
    flange = derived(
        f"{identifier}/flange",
        [plate, *solids, raised],
        parent=parent,
        kind="FLANGE",
        properties=properties,
    )
    bolts = bolt_parts(
        identifier, parent, dims, offset(origin, direction, back / 1000), direction, t + rf_h
    )
    return [flange, *bolts]


def nozzle_resolution(nozzle, *, assume_class=False) -> tuple[Resolution, bool]:
    """Norma, clase y tamaño de la brida de una tobera; indica también si la clase se supone."""
    nps = parse_nps(nozzle.size_nps.value) if nozzle.size_nps else None
    if nps is None:
        nps = nps_from_dn(nozzle.diameter.value)
    assumed = nozzle.rating is None
    if assumed and not assume_class:
        return Resolution(None, None, "", "sin clase de brida trazada"), assumed
    pressure_class = 150 if assumed else parse_class(nozzle.rating.value)
    standard, origin = None, ""
    if nozzle.flange_standard is not None:
        text = str(nozzle.flange_standard.value)
        standard = parse_standard(text) or text.replace(" ", "").upper()
        origin = "campo_trazado"
        if standard not in STANDARD_NAMES:
            return Resolution(None, None, "", f"norma no reconocida: {text}"), assumed
    elif nozzle.rating is not None and (cited := parse_standard(nozzle.rating.value)):
        standard, origin = cited, "campo_trazado"
    result = resolve(nps, pressure_class, standard)
    if result.dims is not None and not result.dims.complete:
        return replace(result, dims=None, reason="la tabla no trae espesor ni cuello"), assumed
    return replace(result, origin=origin or result.origin), assumed


def standard_flanges(equipment, source, *, assume_class=False):
    """Bridas de cuello soldado de las toberas sin brida explícita. Devuelve piezas y motivos."""
    result = list(source)
    missing = {}
    for nozzle in equipment.nozzles:
        if nozzle.flange is not None:
            continue
        resolution, assumed = nozzle_resolution(nozzle, assume_class=assume_class)
        if resolution.dims is None:
            missing[nozzle.id] = resolution.reason
            continue
        origin, direction = nozzle_frame(equipment, nozzle)
        items = weld_neck_parts(
            f"nozzle-{nozzle.stable_id or nozzle.id}",
            nozzle.id,
            nozzle.diameter.value,
            resolution.dims,
            origin,
            direction,
            nozzle.projection.value,
            assumed=assumed,
            standard_origin=resolution.origin,
        )
        if not items:
            missing[nozzle.id] = "la proyección no deja sitio a la brida"
        result.extend(items)
    return result, missing


def enrich_parts(equipment, source):
    """El llamador habilita explícitamente estos supuestos visuales (API sintética o demo).

    IDs derivados del identificador estable del elemento, sin revisión, índice global ni cotas.
    """
    if equipment.kind != "vertical_vessel" or equipment.lod < 2:
        return source
    result = []
    radius = equipment.diameter.value / 2000
    skirt = equipment.skirt_height.value / 1000 if equipment.skirt_height else 0
    # Aberturas opuestas en el faldón, conservando su producto/GUID original.
    width, height = min(0.48, radius * 0.55), min(0.65, skirt * 0.65)
    for part in source:
        if part.id == "skirt" and height > 0.05:
            cuts = (
                ((-width / 2, -radius - 0.05, 0.08), (width, 2 * radius + 0.1, height)),
                ((-radius - 0.05, -width / 2, 0.08), (2 * radius + 0.1, width, height)),
            )
            part = replace(
                part,
                solids=(replace(part.solids[0], cutouts=cuts),),
                properties={
                    "Origen": "derivado_de_norma",
                    "LeidoDelPlano": False,
                    "RequiereVerificacion": True,
                    "Alcance": "Aberturas de proporción ilustrativa; no dimensionado de soporte",
                },
            )
        result.append(part)
    for nozzle in equipment.nozzles:
        if not nozzle.flange:
            continue
        origin, direction = nozzle_frame(equipment, nozzle)
        rating = nozzle.rating.value if nozzle.rating else 150
        dimensions = (nozzle.flange.outer_diameter.value, nozzle.flange.thickness.value)
        end = offset(origin, direction, (nozzle.projection.value - dimensions[1]) / 1000)
        items = flange_parts(
            f"nozzle-{nozzle.stable_id or nozzle.id}",
            nozzle.id,
            nozzle.diameter.value,
            rating,
            end,
            direction,
            assumed=nozzle.rating is None,
            dimensions=dimensions,
        )
        if items:
            # El OD, el espesor y el GUID explícitos se conservan; solo se deriva el taladrado.
            old_id = f"{nozzle.id}/flange"
            result = [
                replace(
                    part,
                    solids=items[0].solids,
                    parent_id=nozzle.id,
                    properties=items[0].properties,
                )
                if part.id == old_id
                else part
                for part in result
            ]
            result.extend(items[1:])
    result, _ = standard_flanges(equipment, result, assume_class=True)
    # Boca de hombre y pescante: ubicación/proporciones de demostración, no evidencia nueva.
    dn = 500 if radius >= 0.6 else 100
    mw_z = min(equipment.shell_bottom / 1000 + 0.85, equipment.total_height / 1000 - 0.5)
    origin, direction = (0.0, -radius, mw_z), (0.0, -1.0, 0.0)
    neck = Solid(
        "cylinder", origin=origin, direction=direction, diameter=dn, length=260, thickness=12
    )
    result.append(
        derived(
            "manway/neck",
            [neck],
            parent="shell",
            kind="MANWAY",
            properties={"Regla": "DN y proyección ilustrativos, no leídos del plano"},
        )
    )
    face = offset(origin, direction, 0.26)
    result.extend(
        flange_parts("manway", "shell", dn, 150, face, direction, assumed=True, paired=True)
    )
    pattern = flange_pattern(dn, 150)
    cover = Solid(
        "drilled",
        origin=offset(face, direction, pattern.thickness / 1000 + 0.008),
        direction=direction,
        diameter=pattern.outside,
        length=pattern.thickness,
        holes=bolt_holes(pattern),
    )
    result.append(derived("manway/cover", [cover], parent="shell", kind="MANWAY_COVER"))
    result.append(
        derived(
            "manway/davit",
            [
                Solid(
                    "cylinder", origin=(0.42, -radius - 0.25, mw_z - 0.25), diameter=35, length=800
                ),
                Solid(
                    "cylinder",
                    origin=(0.42, -radius - 0.25, mw_z + 0.55),
                    direction=(-1.0, 0.0, 0.0),
                    diameter=35,
                    length=420,
                ),
            ],
            parent="shell",
            kind="DAVIT",
        )
    )
    # Orejetas taladradas; se mantienen por debajo de la cota superior original.
    z = (
        equipment.shell_bottom / 1000
        + equipment.height.value / 1000
        + equipment.head_depth.value * 0.6 / 1000
    )
    for i, sign in enumerate((-1, 1), 1):
        point = (sign * radius * 0.9, -0.045, z)
        eye = Solid(
            "drilled",
            origin=point,
            direction=(0.0, -1.0, 0.0),
            diameter=240,
            thickness=75,
            length=70,
        )
        pad = Solid("box", origin=(point[0] - 0.12, -0.115, z - 0.22), size=(0.24, 0.07, 0.22))
        result.append(
            derived(
                f"lug-{i}",
                [eye, pad],
                parent="top_head",
                kind="LIFTING_LUG",
                properties={"Regla": "Proporción ilustrativa, sin cálculo de izado"},
            )
        )
    count = 12
    pitch = radius + 0.065
    holes = tuple(
        (
            pitch * math.cos(2 * math.pi * i / count),
            pitch * math.sin(2 * math.pi * i / count),
            0.015,
        )
        for i in range(count)
    )
    ring = Solid(
        "drilled", diameter=(radius + 0.14) * 2000, thickness=0.22 * 1000, length=35, holes=holes
    )
    result.append(
        derived(
            "base/ring",
            [ring],
            parent="skirt",
            kind="BASE_RING",
            properties={"Regla": "Proporción ilustrativa, no verificación civil"},
        )
    )
    for i, (x, y, _) in enumerate(holes, 1):
        result.append(
            derived(
                f"base/anchor-{i:02}",
                [
                    Solid("cylinder", origin=(x, y, 0.0), diameter=24, length=110),
                    Solid("cylinder", origin=(x, y, 0.035), diameter=40, length=18),
                ],
                parent="skirt",
                kind="ANCHOR_BOLT",
                properties={"Regla": "Anclaje ilustrativo, sin rosca"},
            )
        )
    return result

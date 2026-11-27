"""Comprobaciones internas IFC/contrato; no certifican fidelidad frente a un plano real."""

import json
import math

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np

from ..ifc import stable_guid, validate_ifc
from ..model import fields
from .horizontal import saddle_profile_dimensions


def expected_bounds(equipment):
    """Envolventes analíticas independientes de la malla exportada, en metros."""
    e = equipment
    if e.lod == 1:
        origin = [getattr(e.envelope.origin, a).value / 1000 for a in "xyz"]
        size = [getattr(e.envelope.size, a).value / 1000 for a in "xyz"]
        return {"shell": [origin, [a + b for a, b in zip(origin, size)]]}
    if e.kind == "vertical_vessel":
        r, z, h, d = (
            e.diameter.value / 2000,
            e.shell_bottom / 1000,
            e.height.value / 1000,
            e.head_depth.value / 1000,
        )
        bounds = {
            "shell": [[-r, -r, z], [r, r, z + h]],
            "bottom_head": [[-r, -r, z - d], [r, r, z]],
            "top_head": [[-r, -r, z + h], [r, r, z + h + d]],
        }
        if e.skirt_height is not None:
            bounds["skirt"] = [[-r, -r, 0], [r, r, z]]
        return bounds
    if e.kind == "horizontal_vessel":
        p = e.horizontal
        r, h, length, d = (
            p.diameter.value / 2000,
            p.support_height.value / 1000,
            p.length.value / 1000,
            p.head_depth.value / 1000,
        )
        bounds = {
            "shell": [[0, -r, h], [length, r, h + 2 * r]],
            "bottom_head": [[-d, -r, h], [0, r, h + 2 * r]],
            "top_head": [[length, -r, h], [length + d, r, h + 2 * r]],
        }
        half_span = p.saddle_span.value / 2000
        seat_edge = h + r - math.sqrt(r**2 - half_span**2)
        for index, station in enumerate(p.saddle_positions, start=1):
            x = station.value / 1000
            width, base = saddle_profile_dimensions(e, index)
            half_width = width.value / 2000
            half_base = max(half_span, base.value / 2000)
            bounds[f"saddle-{index}"] = [
                [x - half_width, -half_base, 0],
                [x + half_width, half_base, seat_edge],
            ]
        return bounds
    if e.kind == "column":
        result, z = {}, e.shell_bottom / 1000
        if e.effective_support == "skirt":
            r = e.attributes["skirt_diameter"].value / 2000
            top = e.attributes.get("skirt_top_diameter")
            if top is not None and top.state != "abstained":
                r = max(r, top.value / 2000)
            result["skirt"] = [[-r, -r, 0], [r, r, z]]
        bottom = z
        for i, section in enumerate(e.column.sections):
            r = max(section.diameter.value, (section.top_diameter or section.diameter).value) / 2000
            h = section.height.value / 1000
            result["shell" if i == 0 else f"section-{section.id}"] = [[-r, -r, z], [r, r, z + h]]
            z += h
        first, last = e.column.sections[0], e.column.sections[-1]
        for side, diameter in (
            ("bottom", first.diameter),
            ("top", last.top_diameter or last.diameter),
        ):
            depth = e.attributes.get(f"column_head_depth_{side}")
            if depth is not None and depth.state != "abstained":
                r, h = diameter.value / 2000, depth.value / 1000
                base, top = (bottom - h, bottom) if side == "bottom" else (z, z + h)
                result[f"{side}_head"] = [[-r, -r, base], [r, r, top]]
        return result
    if e.kind == "tank":
        p = e.tank
        r, h = p.diameter.value / 2000, p.height.value / 1000
        result = {"shell": [[-r, -r, 0], [r, r, h]]}
        if p.roof in ("conical", "domed"):
            result["roof"] = [[-r, -r, h], [r, r, h + p.roof_height.value / 1000]]
        return result
    raise ValueError("Familia sin envolvente analítica de auditoría")


def audit_ifc(revision, model, *, tolerance_m=0.002):
    """Reabre STEP y contrasta unidades, cotas, puertos, GUID y propiedades con el contrato."""
    if not 0 < tolerance_m <= 0.01:
        raise ValueError("La tolerancia debe estar entre 0 y 0,01 m")
    model = ifcopenshell.file.from_string(model.to_string())
    issues = []

    def check(condition, code, detail):
        if not condition:
            issues.append({"code": code, "detail": detail})

    schema_issues = validate_ifc(model)
    check(not schema_issues, "schema", f"{len(schema_issues)} incidencias estructurales/EXPRESS")
    check(
        ifcopenshell.util.unit.get_project_unit(model, "LENGTHUNIT") is not None,
        "units",
        "El proyecto debe declarar explícitamente la unidad de longitud",
    )
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)
    check(
        abs(unit_scale - 1) < 1e-12, "units", "El exportador debe declarar longitud IFC en metros"
    )
    guids = [r.GlobalId for r in model.by_type("IfcRoot")]
    check(len(guids) == len(set(guids)), "guid_unique", "GUID repetido")
    wanted = expected_bounds(revision.equipment)
    actual = {}
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    for product in model.by_type("IfcElement"):
        ps = ifcopenshell.util.element.get_psets(product)
        identity = ps.get("TrazIA_Identity", {})
        component = identity.get("ComponentId")
        if not component:
            continue
        check(component not in actual, "component_unique", component)
        trace = ps.get("TrazIA_Traceability", {})
        for key, value in {
            "Revision": revision.revision,
            "Dataset": revision.dataset,
            "Draft": True,
            "LOD": revision.equipment.lod,
            "InputSHA256": revision.fingerprint(),
        }.items():
            check(trace.get(key) == value, "traceability", f"{component}.{key}")
        check(identity.get("EquipmentId") == revision.equipment.id, "equipment_identity", component)
        if component == "shell":
            try:
                decoded = json.loads(trace.get("FieldsJSON", ""))
                expected_fields = {
                    k: v.model_dump(mode="json") for k, v in fields(revision.equipment).items()
                }
                check(decoded == expected_fields, "fields_roundtrip", component)
            except (ValueError, TypeError):
                check(False, "fields_roundtrip", "FieldsJSON no legible")
            for key, value in {
                "Revision": revision.revision,
                "Dataset": revision.dataset,
                "Draft": True,
                "InputSHA256": revision.fingerprint(),
            }.items():
                check(ps.get("TrazIA_Provenance", {}).get(key) == value, "provenance", key)
            for key, value in revision.equipment.attributes.items():
                check(
                    ps.get("TrazIA_Technical", {}).get(key) == f"{value.value} {value.unit}",
                    "technical_property",
                    key,
                )
        try:
            shape = ifcopenshell.geom.create_shape(settings, product)
            vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
            check(bool(len(vertices)) and bool(np.isfinite(vertices).all()), "mesh", component)
            bounds = [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()]
            actual[component] = {
                "guid": product.GlobalId,
                "bbox_m": bounds,
                "vertices": len(vertices),
                "triangles": len(shape.geometry.faces) // 3,
            }
            if component in wanted:
                error = float(np.max(np.abs(np.array(bounds) - np.array(wanted[component]))))
                check(error <= tolerance_m, "dimensions", f"{component}: error {error} m")
                actual[component]["max_bbox_error_m"] = error
        except (RuntimeError, ValueError) as exc:
            actual[component] = {"guid": product.GlobalId, "error": str(exc)}
            check(False, "geometry_unreadable", component)
        if component.startswith(("lug-", "base/", "manhole/")) or "/bolt-" in component:
            check(
                ps.get("Pset_TrazIA", {}).get("Origen") == "derivado_de_norma",
                "derived_provenance",
                component,
            )
    for component in wanted:
        check(component in actual, "missing_component", component)
    legs = revision.equipment.legs
    if revision.equipment.lod >= 2 and legs is not None:
        for index in range(1, legs.count.value + 1):
            component = f"leg-{index}"
            bounds = actual.get(component, {}).get("bbox_m")
            check(bounds is not None, "missing_component", component)
            if bounds is not None:
                z_min, z_max = (point[2] for point in bounds)
                error = max(abs(z_min), abs(z_max - legs.height.value / 1000))
                check(error <= tolerance_m, "dimensions", f"{component}: error {error} m")
        check(
            sum(component.startswith("leg-") for component in actual) == legs.count.value,
            "leg_count",
            "Número de patas",
        )
    ports = []
    all_ports = {p.GlobalId: p for p in model.by_type("IfcDistributionPort")}
    equipment = revision.equipment
    for nozzle in equipment.nozzles:
        name = f"{equipment.tag.value}/{nozzle.id}/port"
        key = (
            f"{revision.project_id}/equipment/{equipment.id}/nozzle/{nozzle.stable_id or nozzle.id}"
        )
        port = all_ports.get(stable_guid(f"{key}/port"))
        check(port is not None, "missing_port", name)
        if port is None:
            continue
        check(port.Name == name, "port_name", name)
        if nozzle.position:
            origin = np.array([getattr(nozzle.position, a).value / 1000 for a in "xyz"])
            direction = np.array([getattr(nozzle.direction, a).value for a in "xyz"])
            direction = direction / np.linalg.norm(direction)
        else:
            angle = math.radians(nozzle.azimuth.value)
            direction = np.array([math.cos(angle), math.sin(angle), 0])
            origin = direction * revision.equipment.diameter.value / 2000
            origin[2] = nozzle.elevation.value / 1000
        face = origin + direction * nozzle.projection.value / 1000
        placement = ifcopenshell.util.placement.get_local_placement(port.ObjectPlacement)
        check(bool(np.allclose(placement[:3, 3], face, atol=1e-6, rtol=0)), "port_position", name)
        check(
            bool(np.allclose(placement[:3, 2], direction, atol=1e-6, rtol=0)),
            "port_direction",
            name,
        )
        ports.append(
            {
                "name": name,
                "position_m": placement[:3, 3].tolist(),
                "direction": placement[:3, 2].tolist(),
            }
        )
    check(len(all_ports) == len(revision.equipment.nozzles), "port_count", "Número de puertos")
    return {
        "valid": not issues,
        "issues": issues,
        "schema": model.schema,
        "synthetic": revision.dataset == "synthetic",
        "draft": True,
        "tolerance_m": tolerance_m,
        "unit_scale_to_m": unit_scale,
        "components": actual,
        "ports": ports,
        "source_sha256": revision.fingerprint(),
        "bimvision_measured": False,
        "tr_reference_available": False,
        "scope": "Conformidad interna del contrato; sin certificar extracción ni cálculo mecánico",
    }

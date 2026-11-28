import json
import math
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.classification
import ifcopenshell.api.context
import ifcopenshell.api.owner
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.api.type
import ifcopenshell.api.unit
import ifcopenshell.guid

from .families import Solid, parts
from .families.detail import enrich_parts, standard_flanges
from .families.geometry import head_mesh  # API histórica usada en pruebas geométricas.
from .families.ifc_metadata import enrich, initialize_owner
from .model import Revision, fields

__all__ = ["build_ifc", "export_ifc", "head_mesh", "stable_guid"]
_VALIDATION_LOCK = Lock()


def stable_guid(key: str) -> str:
    return ifcopenshell.guid.compress(uuid5(NAMESPACE_URL, f"trazia:{key}").hex)


def build_ifc(
    revision: Revision,
    *,
    draft: bool = True,
    schema: Literal["IFC4", "IFC4X3", "IFC2X3"] = "IFC4",
    details: bool = False,
    plant_north_deg: float | None = None,
) -> ifcopenshell.file:
    revision = Revision.model_validate_json(revision.model_dump_json())
    pending = revision.pending_review()
    if pending and not draft:
        raise ValueError(
            "Hay campos sin revisar: " + ", ".join(pending) + ". Use --draft para borrador."
        )
    if not draft and revision.approval is None:
        raise ValueError("Falta aprobación humana de esta revisión. Use --draft para borrador.")
    if schema not in ("IFC4", "IFC4X3", "IFC2X3"):
        raise ValueError("Esquema IFC no soportado")
    model = ifcopenshell.file(schema=schema)
    initialize_owner(model)
    base = revision.project_id

    def root(ifc_class, name, key, **kwargs):
        entity = ifcopenshell.api.root.create_entity(
            model, ifc_class=ifc_class, name=name, **kwargs
        )
        entity.GlobalId = stable_guid(f"{base}/{key}")
        return entity

    project = root("IfcProject", revision.project_id, "project")
    units = [
        ifcopenshell.api.unit.add_si_unit(model, unit_type=t)
        for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")
    ]
    assignment = ifcopenshell.api.unit.assign_unit(model, units=units)
    assignment.Units = tuple(units)  # la API las guarda en un conjunto y el orden variaba
    context = ifcopenshell.api.context.add_context(model, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )
    site = root("IfcSite", revision.project_id, "site")
    building = root("IfcBuilding", "Unidad de proceso", "building")
    storey = root("IfcBuildingStorey", "Equipos", "storey")
    for parent, child, nombre in (
        (project, site, "site"),
        (site, building, "building"),
        (building, storey, "storey"),
    ):
        relacion = ifcopenshell.api.aggregate.assign_object(
            model, products=[child], relating_object=parent
        )
        relacion.GlobalId = stable_guid(f"{base}/{nombre}/aggregates")

    def axis(origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)):
        # Elegir una referencia perpendicular también para boquillas inclinadas.
        seed = (0.0, 0.0, 1.0) if abs(direction[2]) < 0.9 else (1.0, 0.0, 0.0)
        dot = sum(a * b for a, b in zip(seed, direction))
        reference = tuple(a - dot * b for a, b in zip(seed, direction))
        return model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=origin),
            Axis=model.create_entity("IfcDirection", DirectionRatios=direction),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=reference),
        )

    def swept(profile, depth):
        return model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=axis(),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=depth,
        )

    def circle(radius, center=(0.0, 0.0)):
        return model.create_entity(
            "IfcCircle",
            Radius=radius,
            Position=model.create_entity(
                "IfcAxis2Placement2D",
                Location=model.create_entity("IfcCartesianPoint", Coordinates=center),
            ),
        )

    def solid_item(solid: Solid):
        if solid.kind == "drilled":
            inner = (
                [circle(solid.diameter / 2000 - solid.thickness / 1000)] if solid.thickness else []
            )
            inner += [circle(radius, (x, y)) for x, y, radius in solid.holes]
            profile = model.create_entity(
                "IfcArbitraryProfileDefWithVoids",
                ProfileType="AREA",
                OuterCurve=circle(solid.diameter / 2000),
                InnerCurves=inner,
            )
            return swept(profile, solid.length / 1000), "SweptSolid"
        if solid.kind == "mesh":
            if schema == "IFC2X3":
                points = [
                    model.create_entity("IfcCartesianPoint", Coordinates=v) for v in solid.vertices
                ]
                faces = []
                for triangle in solid.triangles:
                    loop = model.create_entity(
                        "IfcPolyLoop", Polygon=[points[i - 1] for i in triangle]
                    )
                    bound = model.create_entity("IfcFaceOuterBound", Bound=loop, Orientation=True)
                    faces.append(model.create_entity("IfcFace", Bounds=[bound]))
                shell = model.create_entity("IfcClosedShell", CfsFaces=faces)
                return model.create_entity("IfcFacetedBrep", Outer=shell), "Brep"
            return model.create_entity(
                "IfcTriangulatedFaceSet",
                Coordinates=model.create_entity(
                    "IfcCartesianPointList3D", CoordList=solid.vertices
                ),
                Closed=True,
                CoordIndex=solid.triangles,
            ), "Tessellation"
        if solid.kind == "cylinder":
            args = {"ProfileType": "AREA", "Radius": solid.diameter / 2000}
            if schema == "IFC2X3":
                args["Position"] = model.create_entity(
                    "IfcAxis2Placement2D",
                    Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0)),
                )
            if solid.thickness:
                args["WallThickness"] = solid.thickness / 1000
            profile = model.create_entity(
                "IfcCircleHollowProfileDef" if solid.thickness else "IfcCircleProfileDef", **args
            )
            item = swept(profile, solid.length / 1000)
            for origin, size in solid.cutouts:
                x, y, z = size
                rectangle = model.create_entity(
                    "IfcRectangleProfileDef",
                    ProfileType="AREA",
                    XDim=x,
                    YDim=y,
                    Position=model.create_entity(
                        "IfcAxis2Placement2D",
                        Location=model.create_entity(
                            "IfcCartesianPoint", Coordinates=(x / 2, y / 2)
                        ),
                    ),
                )
                cutter = swept(rectangle, z)
                cutter.Position = axis(origin)
                item = model.create_entity(
                    "IfcBooleanResult",
                    Operator="DIFFERENCE",
                    FirstOperand=item,
                    SecondOperand=cutter,
                )
            return item, "CSG" if solid.cutouts else "SweptSolid"
        if solid.kind == "box":
            x, y, z = solid.size
            profile = model.create_entity(
                "IfcRectangleProfileDef",
                ProfileType="AREA",
                XDim=x,
                YDim=y,
                Position=model.create_entity(
                    "IfcAxis2Placement2D",
                    Location=model.create_entity("IfcCartesianPoint", Coordinates=(x / 2, y / 2)),
                ),
            )
            return swept(profile, z), "SweptSolid"
        if solid.kind == "profile":
            # El eje X global es la extrusión; X/Y locales son Y/Z globales.
            polyline = model.create_entity(
                "IfcPolyline",
                Points=[
                    model.create_entity("IfcCartesianPoint", Coordinates=p)
                    for p in (*solid.points, solid.points[0])
                ],
            )
            profile = model.create_entity(
                "IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline
            )
            return swept(profile, solid.length / 1000), "SweptSolid"
        if solid.kind == "revolved":
            # Perfil (radio, avance) en el plano XY local, girado alrededor del eje Y local.
            polyline = model.create_entity(
                "IfcPolyline",
                Points=[
                    model.create_entity("IfcCartesianPoint", Coordinates=p)
                    for p in (*solid.points, solid.points[0])
                ],
            )
            profile = model.create_entity(
                "IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline
            )
            return model.create_entity(
                "IfcRevolvedAreaSolid",
                SweptArea=profile,
                # Eje local Y = eje del sólido; en el marco con Z = eje, X sigue siendo X.
                Position=model.create_entity(
                    "IfcAxis2Placement3D",
                    Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
                    Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0)),
                    RefDirection=model.create_entity(
                        "IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)
                    ),
                ),
                Axis=model.create_entity(
                    "IfcAxis1Placement",
                    Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
                    Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
                ),
                Angle=2 * math.pi,
            ), "SweptSolid"
        raise ValueError(f"Sólido desconocido: {solid.kind}")

    def revolved_axis(origin, direction):
        """Marco absoluto con Y local = eje del sólido de revolución."""
        frame = axis(origin, direction)
        x = frame.RefDirection.DirectionRatios
        d = direction
        z = (x[1] * d[2] - x[2] * d[1], x[2] * d[0] - x[0] * d[2], x[0] * d[1] - x[1] * d[0])
        frame.Axis = model.create_entity("IfcDirection", DirectionRatios=z)
        return frame

    def represent(product, solids):
        items = []
        for solid in solids:
            item, kind = solid_item(solid)
            if len(solids) == 1:
                placement = axis(solid.origin, solid.direction)
                if solid.kind == "profile":
                    placement.RefDirection = model.create_entity(
                        "IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)
                    )
                product.ObjectPlacement = model.create_entity(
                    "IfcLocalPlacement", RelativePlacement=placement
                )
            elif solid.kind == "revolved":
                item.Position = revolved_axis(solid.origin, solid.direction)
            else:
                item.Position = axis(solid.origin, solid.direction)
            items.append(item)
        if len(solids) > 1:
            product.ObjectPlacement = model.create_entity(
                "IfcLocalPlacement", RelativePlacement=axis()
            )
        representation = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body,
            RepresentationIdentifier="Body",
            RepresentationType=kind,
            Items=items,
        )
        product.Representation = model.create_entity(
            "IfcProductDefinitionShape", Representations=[representation]
        )

    def pset(product, name, properties):
        p = ifcopenshell.api.pset.add_pset(model, product=product, name=name)
        ifcopenshell.api.pset.edit_pset(model, pset=p, properties=properties)
        # Mismos datos, mismo IFC: el conjunto y su relación toman el GUID del producto y del
        # nombre, como las piezas. Así un visor BIM no ve cambios donde no los hay.
        p.GlobalId = stable_guid(f"{base}/{product.GlobalId}/pset/{name}")
        for relacion in model.get_inverse(p):
            if relacion.is_a("IfcRelDefinesByProperties"):
                relacion.GlobalId = stable_guid(f"{base}/{product.GlobalId}/pset/{name}/rel")

    from .reference import metadata

    reference = metadata(plant_north_deg)
    if revision.equipment.kind == "horizontal_vessel":
        reference.update(
            StationOrigin="Tangente izquierda de la virola · X = 0",
            StationDirection="+X hacia la tangente derecha",
            NozzleAzimuthZero="+Z",
            NozzleAzimuth90="+Y",
        )
    pset(storey, "TrazIA_ReferenceFrame", reference)
    if plant_north_deg is not None:
        angle = math.radians(plant_north_deg)
        context.TrueNorth = model.create_entity(
            "IfcDirection", DirectionRatios=(math.cos(angle), math.sin(angle))
        )

    equipment = revision.equipment
    key = f"equipment/{equipment.id}"
    tag = equipment.tag.value
    classes = {
        "pump": "IfcPump",
        "compressor": "IfcCompressor",
        "generic": "IfcBuildingElementProxy",
    }
    main_class = classes.get(equipment.kind, "IfcTank")
    semantic_class = main_class
    if schema == "IFC2X3":
        main_class = {
            "IfcTank": "IfcFlowStorageDevice",
            "IfcPump": "IfcFlowMovingDevice",
            "IfcCompressor": "IfcFlowMovingDevice",
        }.get(main_class, main_class)
    main_type = (
        "PRESSUREVESSEL"
        if semantic_class == "IfcTank" and equipment.kind != "tank"
        else "NOTDEFINED"
    )
    if equipment.predefined_type and schema != "IFC2X3":
        main_type = equipment.predefined_type
    vessel = root(main_class, tag, key, predefined_type=main_type)
    vessel.Tag = tag
    pset(vessel, "TrazIA_ReferenceFrame", reference)
    if schema == "IFC2X3" and semantic_class != "IfcBuildingElementProxy":
        element_type = root(
            semantic_class + "Type",
            f"{tag}/type",
            f"{key}/type",
            predefined_type="PRESSUREVESSEL"
            if semantic_class == "IfcTank" and equipment.kind != "tank"
            else "NOTDEFINED",
        )
        tipo = ifcopenshell.api.type.assign_type(
            model, related_objects=[vessel], relating_type=element_type
        )
        tipo.GlobalId = stable_guid(f"{base}/{key}/type/rel")
    products = []
    traced = fields(equipment)
    components = parts(equipment)
    assumed_style = None
    # El detalle visual requiere una petición explícita. El núcleo y el bench conservan
    # su LOD y no incorporan por defecto piezas que no aparecen en los campos de entrada.
    # Las toberas con clase y tamaño trazados llevan su brida normalizada en cualquier
    # conjunto de datos. Solo el detalle sintético supone clase 150 donde falta.
    assume = details and equipment.kind == "vertical_vessel" and equipment.lod >= 2
    if details:
        components = enrich_parts(equipment, components)
    if not assume:
        components, _ = standard_flanges(equipment, components)
    _, missing = standard_flanges(equipment, [], assume_class=assume)
    if assume or missing or any(p.object_type == "FLANGE" for p in components):
        pset(
            vessel,
            "Pset_TrazIA",
            {
                "PoliticaDetalle": "Detalle visual sintético; requiere verificación mecánica"
                if details
                else "Bridas derivadas de ASME B16.5/B16.47 con clase y tamaño trazados",
                "ClaseSinRating": "150, supuesto visual explícito en cada brida"
                if assume
                else "sin suponer: la tobera sin clase queda sin brida",
                "BridasSinTablaJSON": json.dumps(sorted(missing)),
                "BridasSinTablaMotivoJSON": json.dumps(missing, ensure_ascii=False),
                "VersionDetalle": "frontend-2.7-bridas-asme",
            },
        )
    for index, part in enumerate(components):
        component_class = part.ifc_class
        if schema == "IFC2X3":
            component_class = IFC2X3_CLASSES.get(component_class, component_class)
        extra = (
            {"predefined_type": part.predefined_type}
            if part.predefined_type and schema != "IFC2X3"
            else {}
        )
        product = (
            vessel
            if index == 0
            else root(component_class, f"{tag}/{part.id}", f"{key}/{part.guid_key}", **extra)
        )
        if part.description:
            product.Description = part.description
        if (
            index > 0
            and schema == "IFC2X3"
            and part.ifc_class in ("IfcPipeSegment", "IfcPipeFitting")
        ):
            component_type = root(
                part.ifc_class + "Type",
                f"{tag}/{part.id}/type",
                f"{key}/{part.guid_key}/type",
                predefined_type="RIGIDSEGMENT" if part.ifc_class == "IfcPipeSegment" else "FLANGE",
            )
            tipo = ifcopenshell.api.type.assign_type(
                model, related_objects=[product], relating_type=component_type
            )
            tipo.GlobalId = stable_guid(f"{base}/{key}/{part.guid_key}/type/rel")
        if index > 0:
            product.Tag = part.id
            product.ObjectType = part.object_type
        represent(product, part.solids)
        pset(
            product,
            "TrazIA_Identity",
            {
                "ComponentId": part.id,
                "EquipmentId": equipment.id,
                "ParentComponentId": part.parent_id or "",
            },
        )
        if part.properties:
            pset(product, "Pset_TrazIA", part.properties)
        if part.properties.get("Estado") == "assumed":
            if assumed_style is None:
                assumed_style = ifcopenshell.api.style.add_style(model, name="Geometría supuesta")
                ifcopenshell.api.style.add_surface_style(
                    model,
                    style=assumed_style,
                    ifc_class="IfcSurfaceStyleShading",
                    attributes={"SurfaceColour": {"Red": 0.95, "Green": 0.58, "Blue": 0.18}},
                )
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=product.Representation.Representations[0],
                styles=[assumed_style],
            )
        prefix = f"nozzles.{part.parent_id or part.id}."
        # Cada pieza de un skid lleva solo sus campos: copiar los de todas multiplica el IFC.
        propia = f"components.{part.parent_id or part.id}."
        local_fields = (
            traced
            if index == 0
            else {
                k: v
                for k, v in traced.items()
                if k.startswith((prefix, propia)) or not k.startswith(("nozzles.", "components."))
            }
        )
        pset(
            product,
            "TrazIA_Traceability",
            {
                "Revision": revision.revision,
                "Dataset": revision.dataset,
                "Draft": draft,
                "LOD": equipment.lod,
                "Family": equipment.kind,
                "EquipmentId": equipment.id,
                "LengthUnitInput": "mm",
                "InputSHA256": revision.fingerprint(),
                "FieldsJSON": json.dumps(
                    {k: v.model_dump(mode="json") for k, v in local_fields.items()},
                    ensure_ascii=False,
                ),
            },
        )
        products.append(product)
    fasteners = _welds(
        model, revision, components, products, root, represent, pset, key, tag, schema
    )
    contenido = ifcopenshell.api.spatial.assign_container(
        model, products=[vessel], relating_structure=storey
    )
    contenido.GlobalId = stable_guid(f"{base}/{key}/containment")
    if len(products) + len(fasteners) > 1:
        # De una en una y en el orden de la revisión: la API recoloca las piezas recorriendo un
        # conjunto, y con todas a la vez el orden de las entidades cambiaba entre ejecuciones.
        piezas = [*products[1:], *fasteners]
        for pieza in piezas:
            aggregation = ifcopenshell.api.aggregate.assign_object(
                model, products=[pieza], relating_object=vessel
            )
        aggregation.GlobalId = stable_guid(f"{base}/{key}/components")
        orden = {pieza.id(): i for i, pieza in enumerate(piezas)}
        aggregation.RelatedObjects = tuple(
            sorted(
                aggregation.RelatedObjects,
                key=lambda e: (orden.get(e.id(), len(orden)), e.GlobalId),
            )
        )
    pset(
        vessel,
        "TrazIA_Traceability",
        {
            "ApprovalJSON": revision.approval.model_dump_json() if revision.approval else "",
            "DocumentsJSON": json.dumps(
                [d.model_dump() for d in revision.documents], ensure_ascii=False
            ),
        },
    )
    if equipment.attributes:
        pset(
            vessel,
            "TrazIA_Technical",
            {k: f"{v.value} {v.unit}" for k, v in equipment.attributes.items()},
        )
    _classify(model, equipment, components, products, base, key)
    enrich(model, revision, products, draft=draft, pset=pset, axis=axis, guid=stable_guid)
    return model


# IFC2X3 no tiene las clases de equipo de IFC4: se usan sus supertipos de distribución.
IFC2X3_CLASSES = {
    "IfcPipeSegment": "IfcFlowSegment",
    "IfcPipeFitting": "IfcFlowFitting",
    "IfcPump": "IfcFlowMovingDevice",
    "IfcCompressor": "IfcFlowMovingDevice",
    "IfcElectricMotor": "IfcEnergyConversionDevice",
    "IfcHeatExchanger": "IfcEnergyConversionDevice",
    "IfcUnitaryEquipment": "IfcEnergyConversionDevice",
    "IfcTank": "IfcFlowStorageDevice",
    "IfcFilter": "IfcFlowTreatmentDevice",
    "IfcElectricDistributionBoard": "IfcFlowController",
    "IfcJunctionBox": "IfcFlowFitting",
    "IfcValve": "IfcFlowController",
    "IfcSensor": "IfcDistributionControlElement",
}


def _classify(model, equipment, components, products, base, key):
    """Referencias de clasificación (ISO 14224, API, IFC…) del equipo y de sus piezas.

    Un `IfcClassification` por sistema y un `IfcClassificationReference` por código, con GUID
    estable: el mismo equipo da el mismo IFC.
    """
    pares = [(products[0], tuple(equipment.classification or ()))]
    pares += [
        (product, part.classification)
        for part, product in zip(components[1:], products[1:], strict=True)
        if part.classification
    ]
    sistemas, referencias = {}, {}
    for product, refs in pares:
        for ref in refs:
            if ref.system not in sistemas:
                sistemas[ref.system] = ifcopenshell.api.classification.add_classification(
                    model, classification=ref.system
                )
            clave = (ref.system, ref.code)
            if clave not in referencias:
                referencias[clave] = ifcopenshell.api.classification.add_reference(
                    model,
                    products=[product],
                    identification=ref.code,
                    name=ref.name,
                    classification=sistemas[ref.system],
                )
                rel = next(
                    r
                    for r in model.get_inverse(referencias[clave])
                    if r.is_a("IfcRelAssociatesClassification")
                )
                rel.GlobalId = stable_guid(f"{base}/{key}/class/{ref.system}/{ref.code}")
            else:
                ifcopenshell.api.classification.add_reference(
                    model, products=[product], reference=referencias[clave]
                )


# Nombre de pieza en `welds[].joins` → id de la pieza del IFC. Las virolas, tramos y anillos de
# tanque forman parte de la envolvente («shell»), que es el propio equipo.
WELD_PIECES = {
    "SHELL": "shell",
    "TANK": "shell",
    "HEAD_BOTTOM": "bottom_head",
    "HEAD_LEFT": "bottom_head",
    "HEAD_TOP": "top_head",
    "HEAD_RIGHT": "top_head",
    "SKIRT": "skirt",
    "ROOF": "roof",
}
WELD_COLOUR = {"Red": 0.62, "Green": 0.25, "Blue": 0.78}  # distinto del de geometría supuesta


def _welds(model, revision, components, products, root, represent, pset, key, tag, schema):
    """Un `IfcFastener` (WELD) por soldadura, unido a las dos piezas que une (M5, plan 7.5)."""
    from .families.welds import weld_solid

    if not revision.welds:
        return []
    by_part = {part.id.upper(): product for part, product in zip(components, products, strict=True)}

    def piece(name):
        upper = name.upper()
        if upper in WELD_PIECES:
            return by_part.get(WELD_PIECES[upper].upper())
        if upper in by_part:
            return by_part[upper]
        # Virolas (V01), tramos (1-2) y anillos (C3) son parte de la envolvente.
        return products[0] if upper != "BOTTOM" else None

    style = None
    fasteners = []
    for weld in revision.welds:
        options = {"predefined_type": "WELD"} if schema != "IFC2X3" else {}
        fastener = root("IfcFastener", f"{tag}/{weld.id}", f"{key}/weld/{weld.id}", **options)
        fastener.Tag = weld.id
        solid = weld_solid(revision.equipment, weld)
        if solid is not None:
            represent(fastener, [solid])
            if style is None:
                style = ifcopenshell.api.style.add_style(model, name="Soldadura")
                ifcopenshell.api.style.add_surface_style(
                    model,
                    style=style,
                    ifc_class="IfcSurfaceStyleShading",
                    attributes={"SurfaceColour": WELD_COLOUR},
                )
            ifcopenshell.api.style.assign_representation_styles(
                model,
                shape_representation=fastener.Representation.Representations[0],
                styles=[style],
            )
        traced = weld.traced()
        rules = sorted({f.source.rule for f in traced.values() if f.source.rule})
        pset(
            fastener,
            "TrazIA_Soldadura",
            {
                "Tipo": weld.kind.value,
                "Une": "|".join(weld.joins),
                "Estado": weld.kind.state,
                "Regla": ", ".join(rules),
                "Tamano": str(weld.size.value) if weld.size else "",
                "Nota": str(weld.note.value) if weld.note else "",
                "CotaDesdeTL_mm": weld.elevation.value if weld.elevation else -1.0,
                "SinGeometria": solid is None,
                "RequiereVerificacion": weld.kind.state not in ("accepted", "corrected"),
                "CitasJSON": json.dumps(
                    {path: field.source.model_dump(mode="json") for path, field in traced.items()},
                    ensure_ascii=False,
                ),
            },
        )
        first, second = (piece(name) for name in weld.joins)
        if first is not None and second is not None and first != second:
            model.create_entity(
                "IfcRelConnectsWithRealizingElements",
                GlobalId=stable_guid(f"{revision.project_id}/{key}/weld/{weld.id}/rel"),
                Name=weld.id,
                RelatingElement=first,
                RelatedElement=second,
                RealizingElements=[fastener],
                ConnectionType="WELD",
            )
        fasteners.append(fastener)
    return fasteners


def export_ifc(
    revision: Revision,
    destination: Path,
    *,
    draft: bool = False,
    schema: Literal["IFC4", "IFC4X3", "IFC2X3"] = "IFC4",
) -> Path:
    model = build_ifc(revision, draft=draft, schema=schema)
    destination.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(destination))
    return destination


def validate_ifc(model_or_path, *, express_rules=True) -> list[dict]:
    """Errores estructurales/EXPRESS; no certifica exactitud frente al plano."""
    import ifcopenshell.validate

    logger = ifcopenshell.validate.json_logger()
    # IfcOpenShell cambia temporalmente use_attribute_value_derived en todo el proceso.
    with _VALIDATION_LOCK:
        ifcopenshell.validate.validate(model_or_path, logger, express_rules=express_rules)
    return [{"level": s["level"], "message": s["message"]} for s in logger.statements]

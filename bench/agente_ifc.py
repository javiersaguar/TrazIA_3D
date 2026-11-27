"""Ensayo IFC con Sonnet y el motor paramétrico sobre cotas sintéticas idénticas."""

import argparse
import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from bench.evaluar import distancias, superficie
from bench.modelos_pitch import MODELS, Case, client, load_azure_environment, query
from trazia.families.geometry import head_mesh
from trazia.ifc import build_ifc, stable_guid, validate_ifc
from trazia.model import Revision, load_revision
from trazia.vision.base import VisionError
from trazia.vision.policy import guard_and_log

SONNET = "claude-sonnet-5-5"
TOLERANCE_MM = 2.0
ROOT = Path(__file__).resolve().parents[1]
Vec = tuple[float, float, float]
SHAPE_RULES = {
    "cylinder": {"diameter", "length"},
    "ring": {"diameter", "length", "wall"},
    "dome": {"diameter", "depth"},
    "profile": {"points", "length"},
}
INSTRUCTIONS = """Diseña un IFC preliminar para un equipo SINTÉTICO. Responde solo JSON
{"parts":[{"id":"...", "kind":"...", "base":[x,y,z], "axis":[x,y,z], ...}]}.
Todas las cotas y coordenadas en milímetros. Un sólido por ID requerido. No agregues piezas
sin datos. cylinder: diameter y length desde base en axis; ring: además wall radial hacia
dentro; dome: medio elipsoide desde el centro de su cara plana, diameter y depth en axis;
profile: points [[u,v],...] de polígono cerrado implícito en la base, y length de extrusión.
Para el perfil con extrusión +X, u=+Y y v=+Z. Los vectores axis son unitarios.
El marco se mantiene. Para el equipo vertical, azimut 0° es +X y 90° es +Y. Si no se
especifica posición para una boquilla vertical, su origen está en el radio de la virola
a su elevación desde el suelo. Para silletas, interpreta el dato de estación X como centro,
la base está en Z=0 y la cara superior sigue por debajo el círculo de la virola. Usa 13 a
17 puntos en ese arco para aproximar la curvatura. Mantén exactas cotas, referencias e IDs.
"""


class Primitive(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    kind: Literal["cylinder", "ring", "dome", "profile"]
    base: Vec
    axis: Vec
    diameter: float | None = Field(default=None, gt=0, le=40_000)
    length: float | None = Field(default=None, gt=0, le=60_000)
    wall: float | None = Field(default=None, gt=0, le=20_000)
    depth: float | None = Field(default=None, gt=0, le=40_000)
    points: list[tuple[float, float]] | None = Field(default=None, min_length=3, max_length=40)

    @model_validator(mode="after")
    def supported(self):
        keys = {
            key
            for key in ("diameter", "length", "wall", "depth", "points")
            if getattr(self, key) is not None
        }
        if keys != SHAPE_RULES[self.kind]:
            raise ValueError("Atributos incompatibles con la primitiva")
        if not 0.98 <= math.hypot(*self.axis) <= 1.02:
            raise ValueError("El eje debe ser unitario")
        if max(map(abs, self.base)) > 80_000 or any(
            abs(value) > 40_000 for point in self.points or () for value in point
        ):
            raise ValueError("Coordenadas fuera del banco de pruebas")
        if self.wall is not None and self.wall * 2 >= self.diameter:
            raise ValueError("El espesor anula el hueco del perfil")
        return self


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parts: list[Primitive] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique(self):
        if len({part.id for part in self.parts}) != len(self.parts):
            raise ValueError("IDs repetidos")
        return self


def horizontal(diameter, length, support, nozzle_ids):
    revision = json.loads((ROOT / "examples/vessel_rev_a.json").read_text(encoding="utf-8"))
    equipment = revision["equipment"]
    source = equipment["height"]["source"]

    def value(number, unit="mm"):
        return {"value": number, "unit": unit, "source": source}

    equipment.update(
        kind="horizontal_vessel",
        support="saddles",
        id=f"sintetico-h{diameter}",
        tag={**equipment["tag"], "value": f"ENSAYO-H{diameter}"},
        diameter=None,
        height=None,
        head_depth=None,
        skirt_height=None,
        skirt_thickness=None,
        attributes={},
        nozzles=[],
        horizontal={
            "diameter": value(diameter),
            "length": value(length),
            "head_depth": value(diameter / 4),
            "support_height": value(support),
            "saddle_width": value(350),
            "saddle_span": value(diameter * 0.7),
            "saddle_positions": [value(900), value(length - 1100)],
        },
    )
    for index, identity in enumerate(nozzle_ids, 1):
        x = index * length / 5
        axis = (0, 0, 1) if index % 2 else (0, -1, 0)
        position = (x, axis[1] * diameter / 2, support + diameter / 2 * (1 + axis[2]))
        equipment["nozzles"].append(
            {
                "id": identity,
                "diameter": value(80 + index * 20),
                "projection": value(220 + index * 15),
                "elevation": value(position[2]),
                "azimuth": value(0, "deg"),
                "position": dict(zip("xyz", map(value, position))),
                "direction": {key: value(av, "1") for key, av in zip("xyz", axis)},
            }
        )
    return Revision.model_validate(revision)


def synthetic_example(name):
    revision = load_revision(ROOT / "examples" / f"vessel_rev_{name}.json")
    if revision.dataset != "synthetic":
        raise ValueError("El banco solo usa ejemplos sintéticos")
    return revision


def dimensions(revision, ids):
    eq = revision.equipment

    def get(field):
        return field.value

    if eq.horizontal:
        h = eq.horizontal
        shell = {
            key: get(getattr(h, key))
            for key in (
                "diameter",
                "length",
                "head_depth",
                "support_height",
                "saddle_width",
                "saddle_span",
            )
        }
        shell.update(
            saddle_positions=list(map(get, h.saddle_positions)),
            axes="Virola +X desde X=0. Su eje está en Y=0 y Z=altura del soporte más radio.",
        )
    else:
        shell = {
            "diameter": get(eq.diameter),
            "length": get(eq.height),
            "head_depth": get(eq.head_depth),
            "skirt_height": get(eq.skirt_height),
            "skirt_wall": get(eq.skirt_thickness),
            "axes": "Virola +Z. Su tangente inferior es la altura del faldón desde suelo (Z=0).",
        }
    nozzles = []
    for n in eq.nozzles:
        entry = {
            "id": n.id,
            "diameter": get(n.diameter),
            "length": get(n.projection),
            "elevation": get(n.elevation),
            "azimuth_deg": get(n.azimuth),
        }
        if n.position is not None:
            entry.update(
                base=[get(getattr(n.position, key)) for key in "xyz"],
                axis=[get(getattr(n.direction, key)) for key in "xyz"],
            )
        nozzles.append(entry)
    return {"kind": eq.kind, "envelope": shell, "nozzles": nozzles, "required_parts": sorted(ids)}


def export_recipe(recipe: Recipe, name: str) -> ifcopenshell.file:
    """Convierte primitivas tipadas a IFC4. El adaptador desconoce las familias de equipo."""
    model = ifcopenshell.file(schema="IFC4")
    root = ifcopenshell.api.root.create_entity
    project = root(model, ifc_class="IfcProject", name=f"ENSAYO SINTÉTICO DRAFT · {name}")
    metre = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[metre])
    context = ifcopenshell.api.context.add_context(model, context_type="Model")
    context = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )
    site = root(model, ifc_class="IfcSite", name="Ensayo local")
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)

    for part in recipe.parts:
        z = np.asarray(part.axis)
        z = z / np.linalg.norm(z)
        seed = np.array([0.0, 1.0, 0.0] if abs(z[0]) > 0.9 else [1.0, 0.0, 0.0])
        x = seed - (seed @ z) * z
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        origin = np.asarray(part.base) / 1000
        ref = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", tuple(origin.tolist())),
            Axis=model.create_entity("IfcDirection", tuple(z.tolist())),
            RefDirection=model.create_entity("IfcDirection", tuple(x.tolist())),
        )
        if part.kind == "dome":
            verts, triangles = head_mesh(part.diameter / 2_000, part.depth / 1000, 0, 1)
            coords = np.asarray(verts) @ np.stack([x, y, z]) + origin
            solid = model.create_entity(
                "IfcTriangulatedFaceSet",
                Coordinates=model.create_entity("IfcCartesianPointList3D", coords.tolist()),
                Closed=True,
                CoordIndex=triangles,
            )
        else:
            if part.kind == "ring":
                profile = model.create_entity(
                    "IfcCircleHollowProfileDef",
                    ProfileType="AREA",
                    Radius=part.diameter / 2000,
                    WallThickness=part.wall / 1000,
                )
            elif part.kind == "profile":
                curve = model.create_entity(
                    "IfcPolyline",
                    [
                        model.create_entity("IfcCartesianPoint", (u / 1000, v / 1000))
                        for u, v in [*part.points, part.points[0]]
                    ],
                )
                profile = model.create_entity("IfcArbitraryClosedProfileDef", "AREA", None, curve)
            else:
                profile = model.create_entity(
                    "IfcCircleProfileDef", ProfileType="AREA", Radius=part.diameter / 2000
                )
            solid = model.create_entity(
                "IfcExtrudedAreaSolid",
                SweptArea=profile,
                Position=ref,
                ExtrudedDirection=model.create_entity("IfcDirection", (0.0, 0.0, 1.0)),
                Depth=part.length / 1000,
            )
        product = root(model, ifc_class="IfcBuildingElementProxy", name=part.id)
        product.GlobalId = stable_guid(f"bench-agente-ifc/{name}/{part.id}")
        product.ObjectPlacement = model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0, 0.0)),
            ),
        )
        representation = model.create_entity(
            "IfcShapeRepresentation",
            context,
            "Body",
            "Tessellation" if part.kind == "dome" else "SweptSolid",
            [solid],
        )
        ifcopenshell.api.geometry.assign_representation(
            model, product=product, representation=representation
        )
        ifcopenshell.api.spatial.assign_container(
            model, products=[product], relating_structure=site
        )
        pset = ifcopenshell.api.pset.add_pset(model, product=product, name="TrazIA_Ensayo")
        ifcopenshell.api.pset.edit_pset(
            model, pset=pset, properties={"Dataset": "synthetic", "Draft": True, "Origin": SONNET}
        )
    return model


def piece_bounds(model, *, reference=False):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    bounds = {}
    for element in model.by_type("IfcElement"):
        if not element.Representation:
            continue
        name = element.Name
        if reference:
            identity = ifcopenshell.util.element.get_pset(element, "TrazIA_Identity") or {}
            name = identity.get("ComponentId")
        if not name:
            continue
        shape = ifcopenshell.geom.create_shape(settings, element)
        vertices = np.asarray(shape.geometry.verts).reshape(-1, 3) * 1000
        bounds[name] = np.stack([vertices.min(0), vertices.max(0)])
    return bounds


def compare(model, expected, reference):
    model_bounds = piece_bounds(model)
    common = expected.keys() & model_bounds.keys()
    differences = {
        key: float(np.abs(expected[key] - model_bounds[key]).max()) for key in sorted(common)
    }
    verts, faces, unreadable = superficie(model)
    distance = distancias((verts, faces), reference, muestras=384) if len(verts) else {}
    return {
        "matched": len(common),
        "within_2mm": sum(value <= TOLERANCE_MM for value in differences.values()),
        "missing": sorted(expected.keys() - model_bounds.keys()),
        "extra": sorted(model_bounds.keys() - expected.keys()),
        "bbox_errors_mm": differences,
        "p95_surface_mm": distance.get("p95_mm"),
        "unreadable": unreadable,
    }


def read_recipe(pair, name, spec, feedback=None):
    prompt = INSTRUCTIONS + "\nCotas verificadas:\n" + json.dumps(spec, ensure_ascii=False)
    if feedback is not None:
        prompt += (
            "\nRevisa tu receta con este resultado de la auditoría y devuelve completa:\n"
            + json.dumps(feedback, ensure_ascii=False)
        )
    guard_and_log(
        pair[0].name,
        external=True,
        dataset="synthetic",
        document_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        page_ref=f"ensayo-ifc/{name}",
    )
    data, tokens = query(*pair, Case(name, "geometry", prompt, {}), max_tokens=4096)
    usd = None
    if all(isinstance(token, int) for token in tokens):
        _, input_rate, output_rate = MODELS[SONNET]
        usd = (tokens[0] * input_rate + tokens[1] * output_rate) / 1e6
    return data, usd


def evaluate(name, revision, pair, output, repair):
    folder = output / name
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    baseline = build_ifc(revision, draft=True)
    baseline.write(str(folder / "motor.ifc"))
    baseline = ifcopenshell.open(str(folder / "motor.ifc"))
    issues = len(validate_ifc(baseline))
    baseline_seconds = time.perf_counter() - start
    bounds = piece_bounds(baseline, reference=True)
    reference = superficie(baseline)[:2]
    spec = dimensions(revision, bounds)
    result = {
        "case": name,
        "parts": len(bounds),
        "engine": {"schema_issues": issues, "seconds": baseline_seconds},
        "attempts": [],
    }
    feedback = None
    for turn in range(2 if repair else 1):
        start = time.perf_counter()
        raw, observation = {}, {"usd": None}
        try:
            raw, observation["usd"] = read_recipe(pair, name, spec, feedback)
            recipe = Recipe.model_validate(raw)
            model = export_recipe(recipe, revision.equipment.tag.value)
            file = folder / f"agente-{turn + 1}-DRAFT.ifc"
            model.write(str(file))
            model = ifcopenshell.open(str(file))
            observation.update(
                schema_issues=len(validate_ifc(model)), seconds=time.perf_counter() - start
            )
            observation.update(compare(model, bounds, reference))
        except ValidationError as exc:
            observation.update(
                error="receta_invalida",
                seconds=time.perf_counter() - start,
                details=[
                    {"path": list(item["loc"]), "message": item["msg"]}
                    for item in exc.errors(include_input=False, include_context=False)
                ][:10],
            )
        except (ValueError, RuntimeError, VisionError) as exc:
            observation.update(error=type(exc).__name__, seconds=time.perf_counter() - start)
        result["attempts"].append(observation)
        (folder / f"receta-{turn + 1}.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
        if (
            observation.get("within_2mm") == len(bounds)
            and not observation.get("schema_issues")
            and not observation.get("extra")
        ):
            break
        feedback = {"previous": raw, "checks": observation}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--salida", type=Path, default=Path("generated/bench/agente-ifc"))
    parser.add_argument("--sin-reparacion", action="store_true")
    args = parser.parse_args()
    load_azure_environment(args.env)
    pair = client(SONNET)
    cases = {
        "V101-A": synthetic_example("a"),
        "V101-B": synthetic_example("b"),
        "H1800": horizontal(1800, 5200, 710, ["N1", "D2"]),
        "H2310": horizontal(2310, 6410, 835, ["P1", "L2", "S3"]),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {
            name: pool.submit(evaluate, name, rev, pair, args.salida, not args.sin_reparacion)
            for name, rev in cases.items()
        }
        results = []
        for name, task in pending.items():
            report = task.result()
            results.append(report)
            print(name, json.dumps(report), flush=True)
    (args.salida / "comparativa.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

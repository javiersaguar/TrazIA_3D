"""Baseline explícito de etiquetas; no interpreta vistas ni sustituye a un extractor de visión."""

import json
import re
from typing import Literal, Protocol, get_args

from pydantic import Field

from .families.column import sections_from_candidates
from .families.geometry import derived_field, outer_diameter
from .families.horizontal import normalized_dimensions, radial_nozzle
from .families.upright import radial_shell_nozzle
from .ingest import Bundle
from .model import (
    LOD1_REQUIREMENTS,
    LOD2_REQUIREMENTS,
    Channel,
    Equipment,
    FieldState,
    Model,
    Revision,
    Source,
    nozzle_misfit,
)
from .units import normalize

CHANNELS = set(get_args(Channel))
EQUIPMENT_KINDS = set(get_args(Equipment.model_fields["kind"].annotation))


class Interval(Model):
    """Intervalo conforme de un valor numérico (contrato 0.3, DEC-12)."""

    low: float
    high: float
    level: float = Field(gt=0, lt=1)
    method: Literal["conformal"] = "conformal"


class Alternative(Model):
    """Otro valor candidato para el mismo campo, con su evidencia."""

    value: float | str
    unit: str
    source: Source
    channel: str | None = None


class Candidate(Model):
    path: str
    value: float | str
    unit: str
    source: Source
    # Procedencia ampliada (contrato 0.3). Todo opcional: los extractores antiguos no lo rellenan.
    channel: str | None = None
    strategy: str | None = None
    model: str | None = None
    prompt_sha256: str | None = None
    grounded: bool | None = None
    confidence_raw: float | None = None
    text_original: str | None = None
    unit_original: str | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    interval: Interval | None = None
    explanation: str | None = None
    # Solo la etapa `calibrate` lo fija ("abstained"); si no, el campo nace como "candidate".
    state: FieldState | None = None


class Extractor(Protocol):
    def extract(self, bundles: list[Bundle]) -> list[Candidate]: ...


NUMBER = r"-?\d+(?:\.\d+)?"
LENGTH = {"mm": 1, "cm": 10, "m": 1000, "in": 25.4}
LABELS = {
    "diameter": ("DIAMETER", "OUTSIDE DIAMETER", "DIAMETRO EXTERIOR"),
    "height": ("HEIGHT", "TANGENT LENGTH", "LONGITUD DE VIROLA"),
    "head_depth": ("HEAD_DEPTH", "HEAD DEPTH", "PROFUNDIDAD DE FONDO"),
    "skirt_height": ("SKIRT_HEIGHT", "SKIRT HEIGHT", "ALTURA DE FALDON"),
    "skirt_thickness": ("SKIRT_THICKNESS", "SKIRT THICKNESS", "ESPESOR DE FALDON"),
    **{
        f"envelope.{part}.{axis}": (f"ENVELOPE_{part.upper()}_{axis.upper()}",)
        for part in ("origin", "size")
        for axis in "xyz"
    },
}


class LabelExtractor:
    def extract(self, bundles: list[Bundle]) -> list[Candidate]:
        result = []
        for bundle in bundles:
            for line in bundle.lines:
                text = line.text.strip()
                tag = re.fullmatch(r"TAG\s*[:=]\s*([A-Za-z0-9_-]+)", text, re.I)
                if tag:
                    result.append(Candidate(path="tag", value=tag[1], unit="1", source=line.source))
                for path, aliases in LABELS.items():
                    labels = "|".join(re.escape(a) for a in aliases)
                    match = re.fullmatch(
                        rf"(?:{labels})\s*[:=]\s*({NUMBER})\s*(mm|cm|m|in)", text, re.I
                    )
                    if match:
                        result.append(
                            Candidate(
                                path=path,
                                value=normalize(
                                    f"{match[1]} {match[2]}", "length", decimal="."
                                ).value,
                                unit_original=match[2],
                                text_original=match[0],
                                unit="mm",
                                source=line.source,
                            )
                        )
                nozzle = re.fullmatch(r"NOZZLE\s+([A-Za-z0-9_-]+)\s*:\s*(.+)", text, re.I)
                if nozzle:
                    for pair in nozzle[2].split(";"):
                        match = re.fullmatch(
                            rf"\s*(DIAMETER|PROJECTION|ELEVATION|AZIMUTH)\s*=\s*({NUMBER})\s*(mm|cm|m|in|deg)\s*",
                            pair,
                            re.I,
                        )
                        if not match:
                            continue
                        key, value, unit = match[1].lower(), float(match[2]), match[3].lower()
                        if (key == "azimuth") != (unit == "deg"):
                            continue
                        result.append(
                            Candidate(
                                path=f"nozzles.{nozzle[1]}.{key}",
                                value=normalize(
                                    f"{value} {unit}",
                                    "angle" if unit == "deg" else "length",
                                    decimal=".",
                                ).value,
                                unit_original=match[3],
                                text_original=match[0],
                                unit="deg" if unit == "deg" else "mm",
                                source=line.source,
                            )
                        )
                attribute = re.fullmatch(
                    rf"(DESIGN_PRESSURE|DESIGN_TEMPERATURE|OPERATING_WEIGHT)\s*[:=]\s*({NUMBER})\s*(bar|kPa|MPa|C|kg)",
                    text,
                    re.I,
                )
                if attribute:
                    expected = {
                        "design_pressure": {"bar", "kpa", "mpa"},
                        "design_temperature": {"c"},
                        "operating_weight": {"kg"},
                    }
                    key = attribute[1].lower()
                    unit = attribute[3]
                    if unit.lower() in expected[key]:
                        result.append(
                            Candidate(
                                path=f"attributes.{key}",
                                value=normalize(
                                    f"{attribute[2]} {unit}",
                                    {
                                        "design_pressure": "pressure",
                                        "design_temperature": "temperature",
                                        "operating_weight": "mass",
                                    }[key],
                                    decimal=".",
                                ).value,
                                unit={
                                    "design_pressure": "bar",
                                    "design_temperature": "C",
                                    "operating_weight": "kg",
                                }[key],
                                unit_original=unit,
                                text_original=attribute[0],
                                source=line.source,
                            )
                        )
                material = re.fullmatch(r"MATERIAL\s*[:=]\s*(.+)", text, re.I)
                if material:
                    result.append(
                        Candidate(
                            path="attributes.material",
                            value=material[1],
                            unit="1",
                            source=line.source,
                        )
                    )
        return result


def _traced_source(source: Source, reading: "Candidate | Alternative") -> dict:
    """Evidencia del contrato 0.3: completa la procedencia con lo que trae la lectura."""
    data = source.model_dump(mode="json")
    data["reviewed"] = False
    if data.get("confidence_raw") is None:
        data["confidence_raw"] = source.confidence
    if data.get("channel") is None and reading.channel in CHANNELS:
        data["channel"] = reading.channel
    if isinstance(reading, Candidate):
        for key in ("strategy", "model", "grounded", "text_original", "unit_original"):
            if data.get(key) is None:
                data[key] = getattr(reading, key)
    return data


def _misfit(equipment: dict, nozzle: dict) -> str | None:
    support_height = (
        equipment["legs"]["height"]
        if equipment.get("support") == "legs"
        else equipment["skirt_height"]
    )
    values = [
        nozzle["diameter"]["value"],
        nozzle["elevation"]["value"],
        equipment["diameter"]["value"],
        support_height["value"],
        equipment["height"]["value"],
    ]
    if not all(isinstance(v, int | float) for v in values):
        return None  # lo rechaza el contrato, con su propio mensaje
    return nozzle_misfit(*values)


class MissingDataError(ValueError):
    """Faltan campos para ensamblar la revisión."""


def _traced_value(candidate: Candidate) -> dict:
    return {
        "value": candidate.value,
        "unit": candidate.unit or "1",
        "source": _traced_source(candidate.source, candidate),
        "state": candidate.state or "candidate",
        "interval": candidate.interval.model_dump(mode="json") if candidate.interval else None,
        "alternatives": [
            {"value": a.value, "unit": a.unit or "1", "source": _traced_source(a.source, a)}
            for a in candidate.alternatives
        ],
        "explanation": candidate.explanation,
    }


def _boquillas_envolvente(nozzles, equipment, warnings):
    """Cada tobera de un mecánico se valida sola: la que no cabe no tumba el equipo."""
    from .model import Nozzle

    placed = []
    excluded = set()
    env = equipment.get("envelope") or {}
    origin = {axis: (env.get("origin") or {}).get(axis, {}).get("value", 0) for axis in "xyz"}
    limit = {axis: (env.get("size") or {}).get(axis, {}).get("value") for axis in "xyz"}
    for nid, data in nozzles.items():
        try:
            nozzle = Nozzle.model_validate(data)
        except Exception:
            excluded.add(nid)
            continue
        if nozzle.position is None:
            excluded.add(nid)
            continue
        projection = nozzle.projection.value
        inside = True
        for axis in "xyz":
            lo = origin[axis] if isinstance(origin[axis], int | float) else 0
            hi = limit[axis]
            value = getattr(nozzle.position, axis).value
            extra = projection if axis == "z" else nozzle.diameter.value
            if not isinstance(hi, int | float) or not lo - extra <= value <= lo + hi + extra:
                inside = False
        if not inside:
            excluded.add(nid)
            continue
        placed.append(nozzle.model_dump(mode="json", exclude_none=True))
    if warnings is not None and excluded:
        warnings.append(
            "Boquillas de la envolvente fuera del modelo: " + ", ".join(sorted(excluded))
        )
    return placed, excluded


def _piezas_envolvente(skid, warnings):
    from .model import SkidPart

    piezas = []
    fallos = []
    for cid, data in skid.items():
        try:
            pieza = SkidPart.model_validate(data)
        except Exception:
            fallos.append(cid)
            continue
        piezas.append(pieza.model_dump(mode="json", exclude_none=True))
    if warnings is not None and fallos:
        warnings.append("Componentes exteriores fuera del modelo: " + ", ".join(sorted(fallos)))
    return piezas


def assemble(
    bundles: list[Bundle],
    candidates: list[Candidate],
    *,
    project_id: str,
    equipment_id: str,
    revision: str,
    dataset: str = "real",
    warnings: list[str] | None = None,
    preview_abstentions: bool = False,
    preliminary: bool = False,
) -> Revision:
    """Ensambla la revisión DRAFT desde los candidatos elegidos.

    Con `preliminary`, un dato obligatorio que falta no corta el proceso: nace como marcador
    `assumed` con regla `preliminar.*` (ver `families.preliminares`) y queda pendiente de revisión.
    Sin él, la falta lanza `MissingDataError`.
    """
    preview_abstentions = preview_abstentions and dataset == "synthetic"

    def available(candidate):
        return candidate is not None and (preview_abstentions or candidate.state != "abstained")

    chosen = {}
    for candidate in candidates:
        previous = chosen.get(candidate.path)
        if previous and (previous.value, previous.unit) != (candidate.value, candidate.unit):
            raise ValueError(f"Conflicto en {candidate.path}: seleccione la evidencia correcta")
        chosen.setdefault(candidate.path, candidate)
    from .lectura.ensamblar import completar

    for note in completar(chosen):
        if warnings is not None:
            warnings.append(f"Ensamblado: {note}.")
    from .families import preliminares

    added = []
    if preliminary and not available(chosen.get("attributes.equipment_type")):
        if (supuesto := preliminares.tipo_por_nombre(chosen, bundles)) is not None:
            chosen["attributes.equipment_type"] = supuesto
            added.append(supuesto.path)
    declared_support = chosen.get("attributes.support")
    declared_kind = chosen.get("attributes.equipment_type")
    kind = declared_kind.value if available(declared_kind) else None
    envelope = kind in ("pump", "compressor", "generic") or any(
        path.startswith("envelope.") for path in chosen
    )
    support = declared_support.value if available(declared_support) else None
    horizontal = not envelope and (
        kind == "horizontal_vessel"
        if kind is not None
        else support == "saddles" or any(path.startswith("horizontal.") for path in chosen)
    )
    column = not envelope and kind == "column"
    tank = not envelope and (
        kind == "tank"
        or (kind is None and any(path in ("tank.diameter", "tank.height") for path in chosen))
    )
    legs = not (envelope or horizontal or column or tank) and (
        support == "legs"
        if support is not None
        else any(path.startswith("legs.") for path in chosen)
    )
    family = ("vertical_vessel", "legs" if legs else "skirt")
    if horizontal:
        family = ("horizontal_vessel", "saddles")
    elif column:
        family = ("column", support or ("skirt" if "skirt_height" in chosen else "none"))
    elif tank:
        family = ("tank", support or "none")
    if not envelope and family not in LOD2_REQUIREMENTS:
        raise MissingDataError(f"Soporte pendiente de modelar: {family[1]} para {family[0]}")
    geometry = LOD1_REQUIREMENTS if envelope else LOD2_REQUIREMENTS[family]
    required = ("tag", *(path for path in geometry if path != "column.sections"))
    if column and family[1] == "skirt":
        required += ("skirt_thickness", "attributes.skirt_diameter")
    if preliminary and not envelope and family == ("vertical_vessel", "skirt"):
        required += ("skirt_thickness",)  # el IFC del faldón la exige con fuente trazable
    roof = chosen.get("tank.roof")
    if tank and roof and roof.value == "flat" and "tank.roof_height" not in chosen:
        required = tuple(path for path in required if path != "tank.roof_height")
    basis = chosen.get("attributes.diameter_basis")
    if not (column or envelope) and basis is not None:
        required += ("attributes.diameter_basis",)
    if horizontal and "attributes.support_height_basis" in chosen:
        required += ("attributes.support_height_basis",)
    missing = [key for key in required if not available(chosen.get(key))]

    def column_sections():
        values = {path: _traced_value(candidate) for path, candidate in chosen.items()}
        return sections_from_candidates(values, preview_abstentions=preview_abstentions)

    sections = column_sections() if column else None
    if column and sections is None:
        missing.append("column.sections (diámetros, alturas y orden de abajo arriba)")
    if missing and preliminary:
        added += preliminares.completar(
            chosen, missing, family=family, kind=kind, envelope=envelope, bundles=bundles
        )
        missing = [key for key in required if not available(chosen.get(key))]
        sections = column_sections() if column else None
        if column and sections is None:
            missing.append("column.sections (diámetros, alturas y orden de abajo arriba)")
    if added and warnings is not None:
        warnings.append(preliminares.AVISO + ", ".join(added) + ".")
    values = {path: _traced_value(candidate) for path, candidate in chosen.items()}
    if missing:
        raise MissingDataError("Faltan datos explícitos: " + ", ".join(missing))
    equipment = {"id": equipment_id, "kind": family[0], "attributes": {}, "nozzles": []}
    if horizontal:
        equipment.update(support="saddles", horizontal={"saddle_positions": [None, None]})
    if legs:
        equipment.update(support="legs", legs={})
    if column:
        equipment.update(support=family[1], column={"sections": sections})
    if tank:
        equipment.update(support="none", tank={})
    if envelope:
        equipment.update(
            kind=kind if isinstance(kind, str) and kind in EQUIPMENT_KINDS else "generic",
            lod=1,
            envelope={"origin": {}, "size": {}},
        )
    nozzles = {}
    skid = {}
    azimuths = {}
    nozzle_references = {}
    nozzle_fields = {"diameter", "projection", "azimuth", "service", "rating", "size_nps"}
    nozzle_fields.add("station" if horizontal else "elevation")
    for path, value in values.items():
        candidate = chosen[path]
        if envelope and path in LOD1_REQUIREMENTS:
            _, part, axis = path.split(".")
            equipment["envelope"][part][axis] = value
        elif envelope and path.startswith("nozzles.") and len(parts := path.split(".", 2)) == 3:
            nozzle = nozzles.setdefault(parts[1], {"id": parts[1]})
            key = parts[2]
            if "." in key:
                group, axis = key.split(".", 1)
                if group in ("position", "direction"):
                    nozzle.setdefault(group, {})[axis] = value
            elif key in {
                "diameter",
                "projection",
                "azimuth",
                "elevation",
                "service",
                "rating",
                "size_nps",
            }:
                nozzle[key] = value
        elif envelope and path.startswith("components.") and len(parts := path.split(".", 2)) == 3:
            pieza = skid.setdefault(parts[1], {"id": parts[1]})
            rest = parts[2]
            if rest == "name":
                pieza["name"] = value
            elif rest.startswith("envelope."):
                _, part, axis = rest.split(".")
                pieza.setdefault("envelope", {"origin": {}, "size": {}})[part][axis] = value
        elif path.startswith("nozzles."):
            _, nozzle_id, key = path.split(".", 2)
            nozzle = nozzles.setdefault(nozzle_id, {"id": nozzle_id})
            if key in nozzle_fields:
                if available(candidate):
                    nozzle[key] = value
            elif key in {
                "projection_basis",
                "projection_datum_offset",
                "elevation_ref",
                "nozzle_type",
                "offset_lateral",
                "offset_lateral_mm",
            }:
                nozzle_references.setdefault(nozzle_id, {})[key] = value
        elif path.startswith("attributes."):
            equipment["attributes"][path.split(".", 1)[1]] = value
        elif legs and path in ("legs.count", "legs.height", "legs.section"):
            if available(candidate):
                if (
                    path == "legs.count"
                    and isinstance(candidate.value, float)
                    and candidate.value.is_integer()
                ):
                    value["value"] = int(candidate.value)
                equipment["legs"][path.split(".")[1]] = value
        elif legs and (match := re.fullmatch(r"legs\.azimuths\.(\d+)", path)):
            if available(candidate):
                azimuths[int(match[1])] = value
        elif horizontal and path.startswith("horizontal.") and path in required:
            _, param, *index = path.split(".")
            if index:
                equipment["horizontal"][param][int(index[0])] = value
            else:
                equipment["horizontal"][param] = value
        elif tank and path in ("tank.diameter", "tank.height", "tank.roof", "tank.roof_height"):
            key = path.split(".")[1]
            equipment["tank"][key] = value["value"] if key == "roof" else value
            if key == "roof":
                equipment["tank"]["roof_evidence"] = value
        elif (
            path == "tag"
            or path in required
            or (family == ("vertical_vessel", "skirt") and path == "skirt_thickness")
            # Diámetro y altura entre tangentes de una columna: datos citados del conjunto,
            # además de los tramos que dan la geometría.
            or (column and path in ("diameter", "height") and available(candidate))
        ):
            equipment[path] = value
    if tank:
        if roof.value == "flat" and "roof_height" not in equipment["tank"]:
            equipment["tank"]["roof_height"] = derived_field(
                0,
                "mm",
                "tank.altura_techo_plano",
                "El techo plano no tiene flecha.",
                values["tank.roof"],
            )
        equipment["tank"]["diameter"] = outer_diameter(
            equipment["tank"]["diameter"], equipment["attributes"], "tank"
        )
    elif not (column or horizontal or envelope):
        equipment["diameter"] = outer_diameter(
            equipment["diameter"], equipment["attributes"], "vertical"
        )
    if azimuths:
        count = equipment["legs"]["count"]["value"]
        if set(azimuths) == set(range(len(azimuths))) and len(azimuths) == count:
            equipment["legs"]["azimuths"] = [azimuths[i] for i in range(len(azimuths))]
        elif warnings is not None:
            warnings.append("Azimuts de patas pendientes: falta la lista completa.")
    for bundle in bundles:
        if schedule := bundle.document.nozzle_schedule:
            for mark in schedule.rows:
                nozzles.setdefault(mark, {"id": mark})
    # Una boquilla sin alguno de sus cuatro datos no se puede colocar en 3D: queda fuera del
    # modelo, pero sus valores siguen como candidatos para la revisión humana.
    complete = nozzle_fields - {"service", "rating", "size_nps"}
    incomplete = {n for n, data in nozzles.items() if not complete <= data.keys()}
    unplaced_reasons = {}
    if incomplete and not envelope and warnings is not None:
        warnings.append(
            "Boquillas incompletas fuera del modelo (faltan datos): "
            + ", ".join(sorted(incomplete))
        )
    if horizontal:
        geometry = normalized_dimensions(equipment["horizontal"], equipment["attributes"])
        assembled = {
            n: radial_nozzle(geometry, data, nozzle_references.get(n, {}))
            for n, data in nozzles.items()
            if n not in incomplete
        }
        misplaced = {n for n, nozzle in assembled.items() if nozzle is None}
        if misplaced and warnings is not None:
            warnings.append(
                "Boquillas horizontales pendientes de referencia o geometría radial: "
                + ", ".join(sorted(misplaced))
            )
        equipment["nozzles"] = [nozzle for nozzle in assembled.values() if nozzle is not None]
        excluded = incomplete | misplaced
        labels = {
            "station": "Estación desde la tangente izquierda",
            "azimuth": "Dirección de montaje y, si va descentrada, desplazamiento",
            "projection": "Distancia hasta la cara de la brida",
            "diameter": "Diámetro exterior",
        }
        for mark in sorted(excluded):
            unplaced_reasons[mark] = [
                label for field, label in labels.items() if field not in nozzles[mark]
            ]
            if mark in misplaced:
                basis = nozzle_references.get(mark, {}).get("projection_basis", {})
                reason = (
                    "Referencia de la cota de proyección"
                    if basis.get("value") in (None, "desconocida")
                    or basis.get("state") == "abstained"
                    else "Encaje de la boquilla en la geometría de la virola"
                )
                unplaced_reasons[mark].append(reason)
    elif column or tank:
        placed = {
            n: radial_shell_nozzle(equipment, nozzle, _tangent_reference(nozzle, nozzle_references))
            for n, nozzle in nozzles.items()
            if n not in incomplete
        }
        equipment["nozzles"] = [nozzle for nozzle in placed.values() if nozzle is not None]
        misplaced = {n for n, nozzle in placed.items() if nozzle is None}
        if warnings is not None and misplaced:
            warnings.append(
                "Boquillas pendientes de referencias o geometría radial: "
                + ", ".join(sorted(misplaced))
            )
        excluded = incomplete | misplaced
    elif envelope:
        equipment["nozzles"], excluded = _boquillas_envolvente(nozzles, equipment, warnings)
        piezas = _piezas_envolvente(skid, warnings)
        if piezas:
            equipment["components"] = piezas
    else:
        equipment["nozzles"], excluded = _vertical_nozzles(
            equipment, nozzles, nozzle_references, incomplete, warnings
        )
    content = {
        "schema_version": "0.3",
        "approval": None,
        "project_id": project_id,
        "revision": revision,
        "dataset": dataset,
        "documents": [b.document.model_dump(mode="json") for b in bundles],
        "equipment": equipment,
        "unplaced_nozzles": sorted(excluded),
        "unplaced_nozzle_reasons": unplaced_reasons,
        "welds": _welds(values, available, chosen, warnings),
    }
    return Revision.model_validate_json(json.dumps(content))


WELD_FIELDS = {
    "elevation_mm": "elevation",
    "azimuth_deg": "azimuth",
    "size": "size",
    "note": "note",
}


def _welds(values, available, chosen, warnings) -> list[dict]:
    """Lista `welds` de la revisión desde los candidatos `welds.<ID>.<campo>` (plan 7.5).

    Una unión deducida por una regla `soldadura.*` no tiene aún la línea de la costura leída:
    nace `assumed` con su regla. Una unión sin `kind` o sin las dos piezas que une no entra.
    """
    grouped: dict[str, dict[str, str]] = {}
    for path in values:
        if path.startswith("welds."):
            weld_id, _, name = path.removeprefix("welds.").rpartition(".")
            grouped.setdefault(weld_id, {})[name] = path

    def traced(path):
        field = dict(values[path])
        if field["state"] == "candidate" and (field["source"].get("rule") or "").startswith(
            "soldadura."
        ):
            field["state"] = "assumed"
        return field

    welds, skipped = [], []
    for weld_id, paths in sorted(grouped.items()):
        kind, joins = paths.get("kind"), paths.get("joins")
        if not (kind and joins and available(chosen[kind]) and available(chosen[joins])):
            skipped.append(weld_id)
            continue
        pieces = str(values[joins]["value"]).split("|")
        if len(pieces) != 2:
            skipped.append(weld_id)
            continue
        weld = {"id": weld_id, "kind": traced(kind), "joins": pieces}
        for name, key in WELD_FIELDS.items():
            if name in paths and available(chosen[paths[name]]):
                weld[key] = traced(paths[name])
                if key == "azimuth":
                    weld[key]["unit"] = "deg"
        welds.append(weld)
    if skipped and warnings is not None:
        warnings.append("Soldaduras incompletas fuera de la revisión: " + ", ".join(skipped))
    return welds


def _tangent_reference(nozzle, references):
    """Una cota leída desde la tangente inferior lleva esa referencia citada por su regla."""
    refs = references.get(nozzle["id"], {})
    elevation = nozzle.get("elevation")
    if (
        elevation is not None
        and "elevation_ref" not in refs
        and elevation["source"].get("rule") == "vertical.elevacion_tangente"
    ):
        refs = {**refs, "elevation_ref": {**elevation, "value": "lower_tl", "unit": "1"}}
    return refs


def _vertical_nozzles(equipment, nozzles, references, incomplete, warnings):
    placed = []
    unsupported_references = set()
    misfits = set()
    for nozzle_id, data in nozzles.items():
        if nozzle_id in incomplete:
            continue
        refs = references.get(nozzle_id, {})
        elevation = data["elevation"]
        if (
            "elevation_ref" not in refs
            and elevation["source"].get("rule") == "vertical.elevacion_tangente"
        ):
            refs = {**refs, "elevation_ref": {**elevation, "value": "lower_tl", "unit": "1"}}
        if (
            refs.get("projection_basis", {}).get("value", "shell") != "shell"
            or refs.get("elevation_ref", {}).get("value", "grade") != "grade"
            or refs.get("nozzle_type", {}).get("value", "radial") != "radial"
            or any(
                refs.get(key, {}).get("value", 0) != 0
                for key in ("offset_lateral", "offset_lateral_mm")
            )
        ):
            if (converted := radial_shell_nozzle(equipment, data, refs)) is None:
                unsupported_references.add(nozzle_id)
            else:
                placed.append(converted)
        elif _misfit(equipment, data) is not None:
            misfits.add(nozzle_id)
        else:
            placed.append(data)
    if unsupported_references and warnings is not None:
        warnings.append(
            "Boquillas pendientes de convertir al sistema del equipo: "
            + ", ".join(sorted(unsupported_references))
        )
    if misfits and warnings is not None:
        warnings.append(
            "Boquillas fuera del modelo (no caben en la virola): " + ", ".join(sorted(misfits))
        )
    excluded = {*incomplete, *unsupported_references, *misfits}
    return placed, excluded

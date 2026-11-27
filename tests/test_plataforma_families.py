import copy
import hashlib
import json

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.validate
import numpy as np
import pytest
from pydantic import ValidationError

from trazia.extraction import Candidate, MissingDataError, assemble
from trazia.families.audit import audit_ifc
from trazia.ifc import build_ifc
from trazia.ingest import Bundle
from trazia.model import Revision, fields
from trazia.revisions import compare
from trazia.viewer import meshes_from_ifc


def traced(value, unit="mm"):
    return {
        "value": value,
        "unit": unit,
        "source": {
            "document_id": "FAMILY-TEST",
            "page": 1,
            "locator": "Parámetro sintético de prueba",
            "confidence": 1.0,
        },
    }


def vector(x, y, z, unit="mm"):
    return {axis: traced(value, unit) for axis, value in zip("xyz", (x, y, z))}


def family_data(kind, lod=2):
    equipment = {
        "id": "test-001",
        "tag": traced("T-001", "1"),
        "kind": kind,
        "lod": lod,
        "nozzles": [],
    }
    if lod == 1:
        equipment["envelope"] = {"origin": vector(-1000, 500, 0), "size": vector(2000, 3000, 4000)}
    elif kind == "horizontal_vessel":
        equipment["horizontal"] = {
            key: traced(value)
            for key, value in {
                "diameter": 2000,
                "length": 6000,
                "head_depth": 500,
                "support_height": 800,
                "saddle_width": 400,
                "saddle_span": 1400,
            }.items()
        }
        equipment["horizontal"]["saddle_positions"] = [traced(1200), traced(4800)]
    elif kind == "column":
        equipment["column"] = {
            "sections": [
                {"id": "lower", "diameter": traced(2000), "height": traced(3000)},
                {
                    "id": "transition",
                    "diameter": traced(2000),
                    "top_diameter": traced(1200),
                    "height": traced(1000),
                },
                {"id": "upper", "diameter": traced(1200), "height": traced(4000)},
            ]
        }
    elif kind == "tank":
        equipment["tank"] = {
            "diameter": traced(6000),
            "height": traced(7000),
            "roof": "conical",
            "roof_height": traced(1000),
        }
    return {
        "schema_version": "0.3",
        "project_id": "FAMILY-TEST",
        "revision": "A",
        "dataset": "synthetic",
        "documents": [
            {
                "id": "FAMILY-TEST",
                "filename": "synthetic-fixture.txt",
                "revision": "A",
                "sha256": hashlib.sha256(b"synthetic-family-parameters").hexdigest(),
                "page_count": 1,
            }
        ],
        "equipment": equipment,
    }


def validate(data):
    return Revision.model_validate_json(json.dumps(data))


def assemble_family(kind, readings):
    data = validate(family_data(kind, lod=1))
    source = data.equipment.tag.source
    candidates = [
        Candidate(path=path, value=value, unit=unit, source=source)
        for path, value, unit in [
            ("tag", "T-001", "1"),
            ("attributes.equipment_type", kind, "1"),
            *readings,
        ]
    ]
    return assemble(
        [Bundle(document=data.documents[0], media_type="text", lines=[])],
        candidates,
        project_id="FAMILY-TEST",
        equipment_id="test-001",
        revision="A",
        dataset="synthetic",
    )


def test_assemble_column_with_ordered_sections_skirt_and_radial_port():
    readings = [
        ("attributes.support", "skirt", "1"),
        ("attributes.skirt_diameter", 2100, "mm"),
        ("skirt_height", 700, "mm"),
        ("skirt_thickness", 25, "mm"),
        ("column.sections.V02.order", 3, "1"),
        ("column.sections.V02.diameter", 1200, "mm"),
        ("shell.courses.V02.height", 4000, "mm"),
        ("column.sections.V01.order", 1, "1"),
        ("column.sections.V01.diameter", 2000, "mm"),
        ("shell.courses.V01.height", 3000, "mm"),
        ("column.sections.V12.height", 600, "mm"),
        ("shell.courses.V13.height", 600, "mm"),
        ("column.sections.transition.order", 2, "1"),
        ("column.sections.transition.diameter", 2000, "mm"),
        ("column.sections.transition.top_diameter", 1200, "mm"),
        ("column.sections.transition.height", 1000, "mm"),
        ("nozzles.N1.diameter", 100, "mm"),
        ("nozzles.N1.projection", 1300, "mm"),
        ("nozzles.N1.projection_basis", "axis", "1"),
        ("nozzles.N1.elevation", 1000, "mm"),
        ("nozzles.N1.elevation_ref", "lower_tl", "1"),
        ("nozzles.N1.azimuth", 90, "deg"),
    ]
    invalid_route = "column.sections.V12.height"
    with pytest.raises(MissingDataError, match="column.sections"):
        assemble_family("column", readings)
    readings = [reading for reading in readings if reading[0] != invalid_route]
    revision = assemble_family("column", readings)
    equipment = revision.equipment
    assert [section.id for section in equipment.column.sections] == ["V01", "transition", "V02"]
    assert fields(equipment)["column.sections.V02.order"].value == 3
    nozzle = equipment.nozzles[0]
    assert nozzle.projection.value == 300
    assert nozzle.elevation.value == 1700
    model = build_ifc(revision)
    report = audit_ifc(revision, model)
    assert report["valid"], report["issues"]
    assert report["components"]["skirt"]["bbox_m"][1][2] == pytest.approx(0.7)
    assert report["ports"][0]["position_m"] == pytest.approx([0, 1.3, 1.7])
    after = assemble_family(
        "column",
        [
            (path, 4100 if path == "shell.courses.V02.height" else value, unit)
            for path, value, unit in readings
        ],
    )
    delta = compare(revision, after)["por_id"]
    assert delta["altas"] == delta["bajas"] == []
    assert delta["cambiados"]["V02"]["height"] == [4000, 4100]
    assert len(delta["cambiados"]["V02"]["citas_por_campo"]["height"]) == 2


def test_ifc_of_tapered_skirt_and_column_heads_carries_their_own_bounds():
    revision = assemble_family(
        "column",
        [
            ("attributes.support", "skirt", "1"),
            ("attributes.skirt_diameter", 2100, "mm"),
            ("attributes.skirt_top_diameter", 1600, "mm"),
            ("attributes.column_head_depth_bottom", 380, "mm"),
            ("attributes.column_head_depth_top", 400, "mm"),
            ("skirt_height", 700, "mm"),
            ("skirt_thickness", 25, "mm"),
            ("column.sections.body.diameter", 1600, "mm"),
            ("column.sections.body.height", 6000, "mm"),
        ],
    )
    report = audit_ifc(revision, build_ifc(revision))
    assert report["valid"], report["issues"]
    assert report["components"]["skirt"]["bbox_m"][1] == pytest.approx([1.05, 1.05, 0.7])
    assert report["components"]["top_head"]["bbox_m"][1][2] == pytest.approx(7.1)
    assert report["components"]["bottom_head"]["bbox_m"][0][2] == pytest.approx(0.32)


@pytest.mark.parametrize("roof, height", [("flat", 0), ("domed", 1000)])
def test_assemble_tank_with_traced_roof_and_exterior_diameter(roof, height):
    readings = [
        ("tank.diameter", 6000, "mm"),
        ("tank.height", 7000, "mm"),
        ("tank.roof", roof, "1"),
        ("attributes.diameter_basis", "inside", "1"),
        ("attributes.shell_thickness", 20, "mm"),
    ]
    if height:
        # Sin flecha leída, la cúpula sale de la regla con radio igual al diámetro, como supuesta.
        supuesto = assemble_family("tank", readings).equipment.tank.roof_height
        assert supuesto.value == round(6000 * (1 - 3**0.5 / 2))
        assert supuesto.state == "assumed"
        assert supuesto.source.rule == "tank.flecha_cupula_radio_d"
        readings += [("tank.roof_height", height, "mm")]
    revision = assemble_family("tank", readings)
    tank = revision.equipment.tank
    assert tank.roof_evidence.value == roof
    assert tank.roof_height.value == height
    assert tank.diameter.value == 6040
    report = audit_ifc(revision, build_ifc(revision))
    assert report["valid"], report["issues"]
    if height:
        after = assemble_family(
            "tank",
            [
                (path, "flat" if path == "tank.roof" else value, unit)
                for path, value, unit in readings
                if path != "tank.roof_height"
            ],
        )
        changes = compare(revision, after)["changes"]
        roof_changes = [
            change for change in changes if change["path"] in ("tank.roof", "tank.roof_evidence")
        ]
        assert [change["path"] for change in roof_changes] == ["tank.roof"]
        assert roof_changes[0]["before_source"]["document_id"] == "FAMILY-TEST"
        assert roof_changes[0]["after_source"]["document_id"] == "FAMILY-TEST"


def test_lod_one_preserves_family_and_unplaced_nozzles():
    readings = [
        (f"envelope.{part}.{axis}", value, "mm")
        for part, value in (("origin", 0), ("size", 1000))
        for axis in "xyz"
    ]
    revision = assemble_family("column", [*readings, ("nozzles.N1.diameter", 100, "mm")])
    assert revision.equipment.kind == "column"
    assert revision.equipment.lod == 1
    assert revision.unplaced_nozzles == ["N1"]
    report = audit_ifc(revision, build_ifc(revision))
    assert report["valid"], report["issues"]


def test_vertical_vessel_converts_an_inside_diameter_with_its_thickness():
    readings = [
        ("diameter", 2000, "mm"),
        ("height", 3000, "mm"),
        ("head_depth", 400, "mm"),
        ("skirt_height", 700, "mm"),
        ("skirt_thickness", 16, "mm"),
        ("attributes.diameter_basis", "inside", "1"),
        ("nozzles.N1.diameter", 100, "mm"),
        ("nozzles.N1.projection", 1300, "mm"),
        ("nozzles.N1.projection_basis", "axis", "1"),
        ("nozzles.N1.elevation", 1000, "mm"),
        ("nozzles.N1.elevation_ref", "lower_tl", "1"),
        ("nozzles.N1.azimuth", 90, "deg"),
    ]
    supuesto = assemble_family("vertical_vessel", readings)
    assert supuesto.equipment.diameter.value == 2000
    assert supuesto.equipment.diameter.state == "assumed"
    assert supuesto.equipment.diameter.source.rule == "vertical.diametro_interior_sin_espesor"
    revision = assemble_family(
        "vertical_vessel", [*readings, ("attributes.shell_thickness", 20, "mm")]
    )
    assert revision.equipment.diameter.value == 2040
    assert revision.equipment.diameter.source.rule == "vertical.diametro_exterior"
    assert revision.equipment.nozzles[0].projection.value == 280
    assert revision.equipment.nozzles[0].elevation.value == 1700
    report = audit_ifc(revision, build_ifc(revision))
    assert report["valid"], report["issues"]
    assert report["ports"][0]["position_m"] == pytest.approx([0, 1.3, 1.7])


def test_assemble_horizontal_vessel_with_traced_radial_nozzles():
    revision = validate(family_data("horizontal_vessel"))
    bundle = Bundle(document=revision.documents[0], media_type="pdf")
    readings = []
    for path, field in fields(revision.equipment).items():
        value = {"horizontal.diameter": 1960, "horizontal.support_height": 1800}.get(
            path, field.value
        )
        readings.append(Candidate(path=path, value=value, unit=field.unit, source=field.source))
    for path, value, unit in (
        ("attributes.equipment_type", "horizontal_vessel", "1"),
        ("attributes.support", "saddles", "1"),
        ("attributes.diameter_basis", "inside", "1"),
        ("attributes.shell_thickness", 20, "mm"),
        ("attributes.support_height_basis", "axis", "1"),
    ):
        readings.append(
            Candidate(path=path, value=value, unit=unit, source=revision.equipment.tag.source)
        )
    for mark, station, angle, projection, basis in (
        ("N1", 900, 0, 1300, "axis"),
        ("N2", 1500, 90, 300, "shell"),
        ("N3", 4500, 180, 1300, "axis"),
        ("NO-BASE", 2100, 0, 1300, None),
        ("NO-LENGTH", 2200, 0, 1000, "axis"),
        ("ON-HEAD", 6000, 0, 1300, "axis"),
    ):
        for field, value, unit in (
            ("diameter", 100, "mm"),
            ("station", station, "mm"),
            ("azimuth", angle, "deg"),
            ("projection", projection, "mm"),
            ("projection_basis", basis, "1"),
        ):
            if value is not None:
                readings.append(
                    Candidate(
                        path=f"nozzles.{mark}.{field}",
                        value=value,
                        unit=unit,
                        source=revision.equipment.tag.source,
                    )
                )
    arguments = dict(project_id="FAMILY-TEST", equipment_id="V", revision="A", dataset="synthetic")
    warnings = []
    output = assemble([bundle], readings, warnings=warnings, **arguments)
    geometry = output.equipment.horizontal
    assert geometry.diameter.value == 2000
    assert geometry.support_height.value == 800
    assert output.unplaced_nozzles == ["NO-BASE", "NO-LENGTH", "ON-HEAD"]
    assert any("NO-BASE" in warning for warning in warnings)
    model = build_ifc(output)
    report = audit_ifc(output, model)
    assert report["valid"], report["issues"]
    assert report["components"]["saddle-1"]["bbox_m"][0][0] == pytest.approx(1)
    assert report["components"]["saddle-2"]["bbox_m"][1][0] == pytest.approx(5)
    for nozzle, xyz, direction, port in zip(
        output.equipment.nozzles,
        ((900, 0, 2800), (1500, 1000, 1800), (4500, 0, 800)),
        ((0, 0, 1), (0, 1, 0), (0, 0, -1)),
        report["ports"],
        strict=True,
    ):
        assert nozzle.stable_id == nozzle.id
        assert nozzle.projection.value == 300
        assert [getattr(nozzle.position, axis).value for axis in "xyz"] == pytest.approx(xyz)
        assert port["direction"] == pytest.approx(direction)
        assert nozzle.position.x.source == revision.equipment.tag.source.model_copy(
            update={"confidence_raw": 1.0}
        )
    properties = ifcopenshell.util.element.get_psets(model.by_type("IfcTank")[0])
    assert properties["TrazIA_ReferenceFrame"]["NozzleAzimuth90"] == "+Y"
    partial = [reading for reading in readings if reading.path != "horizontal.saddle_width"]
    sin_ancho = assemble([bundle], partial, **arguments)
    # Sin ancho de silleta acotado se supone el 10 % del diámetro, marcado para revisión.
    assert sin_ancho.equipment.horizontal.saddle_width.value == 200
    assert sin_ancho.equipment.horizontal.saddle_width.state == "assumed"
    sin_espesor = [r for r in readings if r.path != "attributes.shell_thickness"]
    supuesto = assemble([bundle], sin_espesor, **arguments)
    assert supuesto.equipment.horizontal.diameter.state == "assumed"


def test_saddles_keep_independent_widths_and_a_separate_base_span():
    baseline = validate(family_data("horizontal_vessel"))
    source = baseline.equipment.tag.source
    values = {
        "saddle_width_1": 500,
        "saddle_width_2": 700,
        "saddle_base_span": 2300,
    }
    from trazia.model import Attribute

    revision = baseline.model_copy(
        update={
            "equipment": baseline.equipment.model_copy(
                update={
                    "attributes": {
                        name: Attribute(value=value, unit="mm", source=source)
                        for name, value in values.items()
                    },
                }
            )
        }
    )
    report = audit_ifc(revision, build_ifc(revision))
    assert report["valid"], report["issues"]
    for index, width in enumerate((0.5, 0.7), start=1):
        lo, hi = report["components"][f"saddle-{index}"]["bbox_m"]
        assert hi[0] - lo[0] == pytest.approx(width)
        assert hi[1] - lo[1] == pytest.approx(2.3)


def assert_valid(model):
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger, express_rules=True)
    assert not logger.statements, logger.statements


@pytest.mark.parametrize(
    "kind",
    ["vertical_vessel", "horizontal_vessel", "column", "tank", "pump", "compressor", "generic"],
)
def test_level_one_all_kinds_roundtrip_bounds_and_trace(kind):
    revision = validate(family_data(kind, 1))
    model = build_ifc(revision)
    assert_valid(model)
    meshes = meshes_from_ifc(model.to_string())
    assert len(meshes) == 1
    points = np.asarray(meshes[0]["vertices"]).reshape(-1, 3)
    assert points.min(axis=0) == pytest.approx([-1, 0.5, 0])
    assert points.max(axis=0) == pytest.approx([1, 3.5, 4])
    product = model.by_guid(meshes[0]["guid"])
    trace = ifcopenshell.util.element.get_psets(product)["TrazIA_Traceability"]
    assert trace["LOD"] == 1 and trace["Family"] == kind and trace["Draft"]
    assert len(json.loads(trace["FieldsJSON"])) == 7


@pytest.mark.parametrize(
    "kind,bounds,products",
    [
        ("horizontal_vessel", ([-0.5, -1, 0], [6.5, 1, 2.8]), 5),
        ("column", ([-1, -1, 0], [1, 1, 8]), 3),
        ("tank", ([-3, -3, 0], [3, 3, 8]), 2),
    ],
)
def test_parametric_families_shapes_ids_trace(kind, bounds, products):
    revision = validate(family_data(kind))
    model = build_ifc(revision)
    assert_valid(model)
    meshes = meshes_from_ifc(model.to_string())
    assert len(meshes) == products
    points = np.concatenate([np.asarray(m["vertices"]).reshape(-1, 3) for m in meshes])
    assert points.min(axis=0) == pytest.approx(bounds[0], abs=0.002)
    assert points.max(axis=0) == pytest.approx(bounds[1], abs=0.002)
    assert revision.equipment.total_height / 1000 == pytest.approx(bounds[1][2])
    revision.revision = "B"
    assert {m["name"]: m["guid"] for m in meshes} == {
        m["name"]: m["guid"] for m in meshes_from_ifc(build_ifc(revision).to_string())
    }
    for product in model.by_type("IfcElement"):
        trace = ifcopenshell.util.element.get_psets(product)["TrazIA_Traceability"]
        assert trace["LOD"] == 2
    if kind == "column":
        assert "column.sections.transition.top_diameter" in fields(revision.equipment)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "negative", "saddles", "gap", "level3", "pump2", "port", "zero_direction"],
)
def test_reject_missing_or_inconsistent_family_evidence(mutation):
    data = family_data("horizontal_vessel")
    eq = data["equipment"]
    if mutation == "missing":
        del eq["horizontal"]
    if mutation == "negative":
        eq["horizontal"]["length"]["value"] = -1
    if mutation == "saddles":
        eq["horizontal"]["saddle_positions"][1]["value"] = 6100
    if mutation == "gap":
        data = family_data("column")
        data["equipment"]["column"]["sections"][1]["diameter"]["value"] = 1500
    if mutation == "level3":
        eq["lod"] = 3
    if mutation == "pump2":
        data = family_data("pump")
    if mutation in ("port", "zero_direction"):
        nozzle = {
            "id": "N1",
            "diameter": traced(100),
            "projection": traced(300),
            "elevation": traced(2000),
            "azimuth": traced(0, "deg"),
        }
        if mutation == "zero_direction":
            nozzle.update(position=vector(1000, 0, 2000), direction=vector(0, 0, 0, "1"))
        eq["nozzles"] = [nozzle]
    with pytest.raises(ValidationError):
        validate(data)


def test_level_three_flange_platform_ladder_and_nonradial_nozzle():
    data = family_data("tank", 3)
    eq = data["equipment"]
    eq["nozzles"] = [
        {
            "id": "N1",
            "diameter": traced(100),
            "projection": traced(300),
            "elevation": traced(8000),
            "azimuth": traced(0, "deg"),
            "position": vector(0, 0, 8000),
            "direction": vector(0, 0, 1, "1"),
            "nozzle_type": "top",
            "rating": traced("150", "1"),
            "flange": {"outer_diameter": traced(230), "thickness": traced(25)},
        }
    ]
    eq["platforms"] = [
        {"id": "P1", "origin": vector(3000, -1000, 6000), "size": vector(1000, 2000, 100)}
    ]
    eq["ladders"] = [
        {
            "id": "L1",
            "origin": vector(4000, 0, 0),
            "width": traced(500),
            "height": traced(6000),
            "rail_diameter": traced(30),
            "rung_spacing": traced(300),
        }
    ]
    revision = validate(data)
    assert "nozzles.N1.direction.z" in fields(revision.equipment)
    assert "platforms.P1.size.z" in fields(revision.equipment)
    model = build_ifc(revision)
    assert_valid(model)
    meshes = meshes_from_ifc(model.to_string())
    assert len(meshes) == 6
    assert all(m["faces"] for m in meshes)
    # Los campos de detalles también bloquean la aprobación.
    assert "nozzles.N1.flange.thickness" in revision.pending_review()
    new = copy.deepcopy(data)
    new["equipment"]["nozzles"][0]["direction"]["x"]["value"] = 1
    assert validate(new).fingerprint() != revision.fingerprint()


def test_horizontal_rules_complete_saddle_width_and_axis_basis():
    data = validate(family_data("horizontal_vessel", lod=1))
    source = data.equipment.tag.source

    def reading(path, value, unit="mm", rule=None, state=None):
        cited = source.model_copy(update={"rule": rule}) if rule else source
        return Candidate(path=path, value=value, unit=unit, source=cited, state=state)

    candidates = [
        reading("tag", "T-001", "1"),
        reading("attributes.equipment_type", "horizontal_vessel", "1"),
        reading("attributes.support", "saddles", "1"),
        reading("horizontal.diameter", 1900),
        reading("attributes.diameter_basis", "inside", "1"),
        reading("horizontal.length", 5700),
        reading("horizontal.head_depth", 475, rule="ga.fondo_elipsoidal_2_a_1", state="assumed"),
        reading("horizontal.support_height", 1620, rule="ga.silleta_base_a_eje"),
        reading("horizontal.saddle_span", 1754),
        reading("horizontal.saddle_positions.0", 750),
        reading("horizontal.saddle_positions.1", 4950),
        reading("attributes.saddle_width_fixed", 230),
    ]
    warnings = []
    revision = assemble(
        [Bundle(document=data.documents[0], media_type="text", lines=[])],
        candidates,
        project_id="FAMILY-TEST",
        equipment_id="test-001",
        revision="A",
        dataset="synthetic",
        warnings=warnings,
    )
    horizontal = revision.equipment.horizontal
    # La cota de la silleta llega al eje: la cara inferior de la virola queda un radio más abajo.
    assert horizontal.support_height.value == 1620 - 1900 / 2
    assert horizontal.saddle_width.value == 230
    assert horizontal.saddle_width.state == "assumed"
    assert horizontal.saddle_width.source.rule == "horizontal.ancho_silleta_como_la_fija"
    # Sin espesor leído, el diámetro interior se modela tal cual y queda como supuesto.
    assert horizontal.diameter.value == 1900
    assert horizontal.diameter.state == "assumed"
    assert any("horizontal.saddle_width por regla" in w for w in warnings)
    model = build_ifc(revision)
    assert audit_ifc(revision, model)["valid"]
    reglas = {
        regla
        for element in model.by_type("IfcElement")
        if (props := ifcopenshell.util.element.get_psets(element).get("Pset_TrazIA", {}))
        and props.get("Estado") == "assumed"
        for regla in props["Regla"].split(", ")
    }
    assert "horizontal.ancho_silleta_como_la_fija" in reglas


def test_tank_rules_take_the_bottom_course_thickness():
    revision = assemble_family(
        "tank",
        [
            ("tank.diameter", 20270, "mm"),
            ("tank.height", 22000, "mm"),
            ("tank.roof", "flat", "1"),
            ("attributes.diameter_basis", "inside", "1"),
            ("tank.courses.1.thickness", 14, "mm"),
            ("tank.courses.2.thickness", 12, "mm"),
        ],
    )
    tank = revision.equipment.tank
    assert tank.diameter.value == 20270 + 2 * 14
    assert tank.diameter.state != "assumed"
    assert revision.equipment.attributes["shell_thickness"].source.rule == "tank.espesor_virola_1"


def test_el_diametro_exterior_que_solo_sigue_al_espesor_no_es_cambio():
    lecturas = [
        ("tank.diameter", 20270, "mm"),
        ("tank.height", 22000, "mm"),
        ("tank.roof", "flat", "1"),
        ("attributes.diameter_basis", "inside", "1"),
    ]
    antes = assemble_family("tank", [*lecturas, ("tank.courses.1.thickness", 14, "mm")])
    despues = assemble_family("tank", [*lecturas, ("tank.courses.1.thickness", 13, "mm")])
    informe = compare(antes, despues)
    rutas = {c["path"] for c in informe["changes"]}
    assert "tank.diameter" not in rutas
    assert "attributes.shell_thickness" in rutas
    derivados = [c for c in informe["derivados"] if c["path"] == "tank.diameter"]
    assert len(derivados) == 1
    assert derivados[0]["before"]["value"] == 20298
    assert derivados[0]["after"]["value"] == 20296
    assert derivados[0]["motivo"] == "diametro_derivado_del_espesor"


def _vertical_with_welds(extra=()):
    readings = [
        ("diameter", 2000, "mm"),
        ("height", 3000, "mm"),
        ("head_depth", 400, "mm"),
        ("skirt_height", 700, "mm"),
        ("skirt_thickness", 16, "mm"),
        ("nozzles.N1.diameter", 100, "mm"),
        ("nozzles.N1.projection", 300, "mm"),
        ("nozzles.N1.elevation", 1700, "mm"),
        ("nozzles.N1.azimuth", 90, "deg"),
        ("welds.W:SHELL|HEAD_BOTTOM.kind", "circumferential", "1"),
        ("welds.W:SHELL|HEAD_BOTTOM.joins", "SHELL|HEAD_BOTTOM", "1"),
        ("welds.W:SHELL|HEAD_BOTTOM.elevation_mm", 0, "mm"),
        ("welds.W:N1|SHELL.kind", "nozzle", "1"),
        ("welds.W:N1|SHELL.joins", "N1|SHELL", "1"),
        ("welds.W:V01|V02.kind", "circumferential", "1"),
        ("welds.W:V01|V02.joins", "V01|V02", "1"),
        ("welds.W:X.kind", "circumferential", "1"),  # sin `joins`: no entra
        *extra,
    ]
    return assemble_family("vertical_vessel", readings)


def test_welds_reach_the_revision_and_the_ifc_with_the_same_count():
    revision = _vertical_with_welds()
    assert [w.id for w in revision.welds] == ["W:N1|SHELL", "W:SHELL|HEAD_BOTTOM", "W:V01|V02"]
    assert revision.welds[1].elevation.value == 0
    model = build_ifc(revision)
    assert_valid(model)
    fasteners = {f.Tag: f for f in model.by_type("IfcFastener")}
    assert set(fasteners) == {w.id for w in revision.welds}
    assert all(f.PredefinedType == "WELD" for f in fasteners.values())
    # Sin cota, la virola–virola no tiene geometría pero sigue en el IFC.
    assert fasteners["W:V01|V02"].Representation is None
    assert fasteners["W:SHELL|HEAD_BOTTOM"].Representation is not None
    props = ifcopenshell.util.element.get_psets(fasteners["W:N1|SHELL"])["TrazIA_Soldadura"]
    assert props["Tipo"] == "nozzle" and props["Une"] == "N1|SHELL"
    assert props["SinGeometria"] is False
    relations = {
        r.Name: (r.RelatingElement.Tag, r.RelatedElement.Tag)
        for r in model.by_type("IfcRelConnectsWithRealizingElements")
    }
    assert relations == {
        "W:N1|SHELL": ("N1", "T-001"),
        "W:SHELL|HEAD_BOTTOM": ("T-001", "bottom_head"),
    }
    # La circunferencial rodea la virola a la cota de la T.L. inferior (faldón de 700 mm).
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    shape = ifcopenshell.geom.create_shape(settings, fasteners["W:SHELL|HEAD_BOTTOM"])
    verts = np.array(shape.geometry.verts).reshape(-1, 3)
    assert verts[:, 2].min() == pytest.approx(0.69) and verts[:, 2].max() == pytest.approx(0.71)
    assert verts[:, 0].max() == pytest.approx(1.008, abs=1e-3)


def test_welds_keep_their_guid_and_stay_out_of_the_fingerprint():
    first = _vertical_with_welds()
    second = _vertical_with_welds(
        (
            ("welds.W:V01|V02.elevation_mm", 1500, "mm"),
            ("welds.W:A|B.kind", "attachment", "1"),
            ("welds.W:A|B.joins", "A|B", "1"),
        )
    )
    assert first.fingerprint() == second.fingerprint()
    guids = [
        {f.Tag: f.GlobalId for f in build_ifc(r).by_type("IfcFastener")} for r in (first, second)
    ]
    assert all(guids[1][weld] == guid for weld, guid in guids[0].items())
    assert guids[1]["W:V01|V02"] == guids[0]["W:V01|V02"]


def test_deduced_welds_are_assumed_with_their_rule():
    data = validate(family_data("vertical_vessel", lod=1))
    source = data.equipment.tag.source.model_copy(update={"rule": "soldadura.virola_fondo"})
    revision = _vertical_with_welds()
    candidates = [
        Candidate(
            path="welds.W:SHELL|HEAD_TOP.kind", value="circumferential", unit="1", source=source
        ),
        Candidate(
            path="welds.W:SHELL|HEAD_TOP.joins", value="SHELL|HEAD_TOP", unit="1", source=source
        ),
    ]
    from trazia.extraction import _welds

    values = {c.path: {**c.model_dump(mode="json"), "state": "candidate"} for c in candidates}
    welds = _welds(values, lambda c: c is not None, {c.path: c for c in candidates}, None)
    assert welds[0]["kind"]["state"] == "assumed"
    assert revision.welds[0].kind.state == "candidate"

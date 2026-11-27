import copy
import math
from pathlib import Path

import ifcopenshell.util.element
import pytest
from pydantic import ValidationError
from test_plataforma_families import family_data, traced, validate

from trazia.extraction import Candidate, MissingDataError, assemble
from trazia.families.audit import audit_ifc
from trazia.ifc import build_ifc, validate_ifc
from trazia.ingest import Bundle
from trazia.model import (
    Attribute,
    NozzleSchedule,
    NozzleScheduleRow,
    Source,
    fields,
    load_revision,
    missing_fields,
)
from trazia.revisions import compare, markdown_report

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("nombres_libres", [False, True])
def test_diff_usa_filas_citadas_de_boquillas_pendientes(nombres_libres):
    before = load_revision(EXAMPLES / "vessel_rev_a.json")
    before.approval = None
    after = before.model_copy(deep=True, update={"revision": "B"})
    before.unplaced_nozzles, after.unplaced_nozzles = ["R7", "R8"], ["R8", "R9"]

    def inventory(revision, rows, number):
        ga = next(document for document in revision.documents if document.filename.endswith(".pdf"))
        ga.filename = f"plano_{number}.pdf" if nombres_libres else f"GAD_FIXTURE_rev{number}.pdf"

        def source(locator):
            return Source(
                document_id=ga.id,
                page=1,
                bbox=(0.1, 0.2, 0.8, 0.9),
                locator=locator,
                confidence=0.9,
            )

        ga.nozzle_schedule = NozzleSchedule(
            source=source("MARK SIZE PROJECTION"),
            complete=True,
            rows={
                mark: NozzleScheduleRow(
                    source=source(f"{mark} {projection}"),
                    fields={
                        "projection": Attribute(
                            value=projection, unit="mm", source=source(str(projection))
                        ),
                        "projection_basis": Attribute(
                            value="shell", unit="1", source=source("Measured from shell")
                        ),
                        "schedule": Attribute(
                            value="SCH 40" if number == 1 else "THK: 9.15",
                            unit="1",
                            source=source(f"{mark} schedule rev{number}"),
                        ),
                    },
                )
                for mark, projection in rows.items()
            },
        )
        return ga

    inventory(before, {"R7": 280, "R8": 120}, 1)
    ga = inventory(after, {"R8": 170, "R9": 290}, 2)
    before = type(before).model_validate_json(before.model_dump_json())
    result = compare(before, type(after).model_validate_json(after.model_dump_json()))
    grouped = result["por_id"]
    assert grouped["bajas"] == ["R7"] and grouped["altas"] == ["R9"]
    assert grouped["cambiados"]["R8"]["projection"] == [120, 170]
    assert "schedule" not in grouped["cambiados"]["R8"]
    review = result["revisar"]
    assert [(c["path"], c["motivo"]) for c in review] == [
        ("nozzles.R8.schedule", "notacion_de_espesor")
    ]
    assert all(review[0][side]["bbox"] for side in ("before_source", "after_source"))
    assert [s["locator"] for s in grouped["cambiados"]["R8"]["citas_por_campo"]["projection"]] == [
        "120",
        "170",
    ]
    assert grouped["citas_altas_bajas"]["R7"]["antes"]["locator"] == "R7 280"
    assert grouped["citas_altas_bajas"]["R7"]["despues"]["locator"] == "MARK SIZE PROJECTION"
    assert all(
        not c["affects_geometry"] and c["category"] == "documentary" for c in result["changes"]
    )

    ga.nozzle_schedule.complete = False
    partial = compare(before, after)["por_id"]
    assert partial["bajas"] == partial["altas"] == []
    assert partial["cambiados"]["R8"]["projection"] == [120, 170]

    ga.nozzle_schedule = None
    legacy = compare(before, after)["por_id"]
    assert legacy["bajas"] == legacy["altas"] == [] and legacy["cambiados"] == {}


def test_atributo_con_lectura_en_una_sola_revision_real_queda_en_revision():
    before = load_revision(EXAMPLES / "vessel_rev_a.json")
    before.approval = None
    before.dataset = "real"
    after = before.model_copy(deep=True, update={"revision": "B"})
    after.equipment.attributes["weight_probe"] = Attribute(
        value=125, unit="kg", source=after.equipment.tag.source
    )
    diff = compare(before, after)
    assert not diff["changes"] and not diff["por_id"]["sin_marca"]
    pending = diff["revisar"]
    assert [(c["path"], c["motivo"]) for c in pending] == [
        ("attributes.weight_probe", "atributo_sin_lectura_en_ambas_revisiones")
    ]
    assert pending[0]["after_source"]["document_id"] == after.equipment.tag.source.document_id


def supported(kind, support, lod):
    data = family_data(kind, lod)
    equipment = data["equipment"]
    equipment["support"] = support
    if kind == "vertical_vessel":
        equipment.update(diameter=traced(1300), height=traced(3200), head_depth=traced(300))
    if support == "skirt":
        equipment["skirt_height"] = traced(950)
    if support == "legs":
        equipment["legs"] = {"count": traced(3, "1"), "height": traced(780)}
    return data


@pytest.mark.parametrize(
    ("kind", "support", "lod", "key", "missing"),
    [
        ("vertical_vessel", "skirt", 2, "skirt_height", "skirt_height"),
        ("vertical_vessel", "legs", 2, "legs", "legs.count, legs.height"),
        ("horizontal_vessel", "saddles", 2, "horizontal", "horizontal.diameter"),
        ("column", "none", 2, "column", "column.sections"),
        ("column", "skirt", 2, "skirt_height", "skirt_height"),
        ("tank", "none", 2, "tank", "tank.diameter"),
        ("pump", None, 1, "envelope", "envelope.origin.x"),
        ("compressor", None, 1, "envelope", "envelope.origin.x"),
        ("generic", None, 1, "envelope", "envelope.origin.x"),
    ],
)
def test_required_parameters_by_family(kind, support, lod, key, missing):
    data = supported(kind, support, lod)
    equipment = validate(data).equipment
    assert missing_fields(equipment) == []
    partial = equipment.model_copy(update={key: None})
    assert ", ".join(missing_fields(partial)).startswith(missing)
    del data["equipment"][key]
    with pytest.raises(
        ValidationError, match="Faltan campos de geometría: " + missing.replace(".", r"\.")
    ):
        validate(data)


@pytest.mark.parametrize("kind", ["pump", "compressor", "generic"])
def test_mechanical_and_generic_require_lod_one(kind):
    with pytest.raises(ValidationError, match="envolvente de nivel 1"):
        validate(family_data(kind, 2))


@pytest.mark.parametrize("skirt_field", ["skirt_height", "skirt_thickness"])
def test_skirt_fields_are_incompatible_with_legs(skirt_field):
    data = supported("vertical_vessel", "legs", 2)
    assert validate(data).equipment.shell_bottom == 780
    data["equipment"][skirt_field] = traced(50)
    with pytest.raises(ValidationError, match="requieren soporte skirt"):
        validate(data)


def test_leg_parameters_are_incompatible_with_skirt():
    data = supported("vertical_vessel", "skirt", 2)
    data["equipment"]["legs"] = {"count": traced(3, "1"), "height": traced(780)}
    with pytest.raises(ValidationError, match="legs requiere soporte legs"):
        validate(data)


def test_ifc_rejects_pending_column_skirt():
    revision = validate(supported("column", "skirt", 2))
    assert revision.equipment.shell_bottom > 0
    with pytest.raises(ValueError, match="faldón de columna requiere diámetro y espesor"):
        build_ifc(revision)


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3", "IFC2X3"])
def test_vertical_legs_ifc(schema):
    revision = validate(supported("vertical_vessel", "legs", 2))
    model = build_ifc(revision, schema=schema)
    report = audit_ifc(revision, model)
    assert report["valid"], report["issues"]
    legs = [
        element for element in model.by_type("IfcElement") if element.ObjectType == "LEG_SUPPORT"
    ]
    new_revision = revision.model_copy(update={"revision": "B"})
    assert {leg.GlobalId for leg in legs} == {
        element.GlobalId
        for element in build_ifc(new_revision, schema=schema).by_type("IfcElement")
        if element.ObjectType == "LEG_SUPPORT"
    }
    assert len(legs) == 3
    for leg in legs:
        properties = ifcopenshell.util.element.get_psets(leg)["Pset_TrazIA"]
        assert properties["Estado"] == "assumed"
        assert properties["AzimutSupuesto"] is True
        assert leg.Representation.Representations[0].Items[0].StyledByItem
    assert not any(element.Name.endswith("/skirt") for element in model.by_type("IfcElement"))
    assert not validate_ifc(build_ifc(revision, schema=schema, details=True))


def test_assemble_vertical_legs_from_traced_candidates():
    revision = validate(supported("vertical_vessel", "legs", 2))
    bundle = Bundle(document=revision.documents[0], media_type="pdf")
    readings = [
        Candidate(path=path, value=value.value, unit=value.unit, source=value.source)
        for path, value in fields(revision.equipment).items()
    ]
    source = revision.equipment.tag.source
    readings.append(Candidate(path="attributes.support", value="legs", unit="", source=source))
    readings.extend(
        Candidate(path=f"legs.azimuths.{i}", value=angle, unit="deg", source=source)
        for i, angle in enumerate((30, 150, 270))
    )
    readings.append(Candidate(path="nozzles.N1.size_nps", value=2, unit="in", source=source))
    assembled = assemble(
        [bundle], readings, project_id="FAMILY-TEST", equipment_id="V", revision="A"
    )
    assert assembled.unplaced_nozzles == ["N1"]
    assert assembled.equipment.effective_support == "legs"
    assert [angle.value for angle in assembled.equipment.legs.azimuths] == [30, 150, 270]
    model = build_ifc(assembled)
    leg = next(element for element in model.by_type("IfcElement") if element.Tag == "leg-1")
    x, y, _ = leg.ObjectPlacement.RelativePlacement.Location.Coordinates
    assert math.degrees(math.atan2(y, x)) == pytest.approx(30)
    assert not ifcopenshell.util.element.get_psets(leg)["Pset_TrazIA"]["AzimutSupuesto"]
    assert not validate_ifc(model)

    readings = [reading for reading in readings if reading.path != "legs.height"]
    with pytest.raises(MissingDataError, match=r"Faltan datos explícitos: legs\.height"):
        assemble([bundle], readings, project_id="FAMILY-TEST", equipment_id="V", revision="A")


def test_ifc_needs_traced_thickness_for_a_vertical_skirt():
    data = supported("vertical_vessel", "skirt", 2)
    revision = validate(data)
    assert revision.equipment.skirt_thickness is None
    with pytest.raises(ValueError, match="skirt_thickness con fuente trazable"):
        build_ifc(revision)
    data["equipment"]["skirt_thickness"] = traced(16)
    assert any(
        part.Name.endswith("skirt") for part in build_ifc(validate(data)).by_type("IfcElement")
    )


def test_assumed_requires_a_valid_rule():
    data = supported("vertical_vessel", "skirt", 2)
    thickness = traced(16)
    thickness["state"] = "assumed"
    data["equipment"]["skirt_thickness"] = thickness
    with pytest.raises(ValidationError, match="assumed requiere source.rule"):
        validate(data)
    thickness["source"]["rule"] = "REGLA NO VÁLIDA"
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        validate(data)


def test_inferred_region_without_a_word_cannot_be_grounded():
    source = traced(20)["source"]
    source.update(
        inferred_region={"page": 1, "bbox": (0.1, 0.1, 0.5, 0.4), "view": "plan"},
        grounded=True,
    )
    with pytest.raises(ValidationError, match="sin bbox de palabra no admite grounded=True"):
        Source.model_validate(source)
    source["bbox"] = (0.2, 0.2, 0.21, 0.21)
    assert Source.model_validate(source).grounded


def test_inferred_region_page_must_exist():
    data = supported("vertical_vessel", "skirt", 2)
    data["equipment"]["diameter"]["source"]["inferred_region"] = {
        "page": 2,
        "bbox": [0.1, 0.1, 0.5, 0.4],
    }
    with pytest.raises(ValidationError, match="página de inferred_region fuera del documento"):
        validate(data)
    del data["documents"][0]["page_count"]
    with pytest.raises(ValidationError, match="página de inferred_region fuera del documento"):
        validate(data)


def sheet(page=1, size="A3"):
    return {
        "page": page,
        "size": size,
        "rotation": 90,
        "text_layer": "strokes",
        "views": [{"kind": "nozzle_table", "bbox": [0.1, 0.1, 0.5, 0.4]}],
    }


@pytest.mark.parametrize(
    ("entries", "error"),
    [
        ([sheet(2)], "página fuera de page_count"),
        ([sheet(), sheet()], "páginas repetidas"),
        ([{**sheet(), "views": [{"kind": "detail", "bbox": [0.5, 0.1, 0.1, 0.4]}]}], "bbox"),
    ],
)
def test_sheet_map_rejects_invalid_entries(entries, error):
    data = family_data("generic", 1)
    data["documents"][0]["sheet_map"] = entries
    with pytest.raises(ValidationError, match=error):
        validate(data)


def test_identifiers_require_a_document_from_the_revision():
    data = family_data("generic", 1)
    drawing_number = traced("SP-001", "1")
    drawing_number["source"]["document_id"] = "UNKNOWN"
    data["identifiers"] = {"drawing_number": drawing_number}
    with pytest.raises(
        ValidationError, match="identifiers.drawing_number: referencia .* desconocido"
    ):
        validate(data)


def test_printed_revision_is_informative_in_diffs():
    data = family_data("generic", 1)
    data["revision"] = "rev1"
    data["identifiers"] = {"drawing_revision": traced("2", "1")}
    before = validate(data)
    other = copy.deepcopy(data)
    other["revision"] = "rev2"
    other["identifiers"]["drawing_revision"]["value"] = "3"
    after = validate(other)
    report = compare(before, after)
    assert (report["from_revision"], report["to_revision"]) == ("rev1", "rev2")
    assert report["drawing_revision"] == {"before": "2", "after": "3"}
    assert report["changes"] == []
    markdown = markdown_report(before, after, report)
    assert "Revisión rev1 → rev2" in markdown and "cajetín 2 → 3" in markdown


@pytest.mark.parametrize(
    ("filename", "fingerprint"),
    [
        ("vessel_rev_a.json", "acba27d143612b1e5c45b1c082efc98297289d006b8d59bef5a3d01efb5f7319"),
        ("vessel_rev_b.json", "353a20673af5900cae47107222dbdf46c1718408bccff86527900f3f6a357f05"),
    ],
)
def test_existing_example_retains_fingerprint(filename, fingerprint):
    revision = load_revision(EXAMPLES / filename)
    assert revision.schema_version == "0.3" and revision.fingerprint() == fingerprint
    serialized = revision.model_dump(mode="json")
    assert "identifiers" not in serialized
    assert "sheet_map" not in serialized["documents"][0]
    assert "legs" not in serialized["equipment"]
    source = serialized["equipment"]["tag"]["source"]
    assert "inferred_region" not in source and "rule" not in source


def test_new_fields_roundtrip_with_provenance():
    data = supported("vertical_vessel", "legs", 2)
    data["identifiers"] = {
        "drawing_number": traced("SP-001", "1"),
        "drawing_revision": traced("R", "1"),
        "project_number": traced("P-006", "1"),
    }
    data["documents"][0].update(
        page_count=2,
        sheet_map=[
            sheet(),
            {**sheet(2, {"width_mm": 420, "height_mm": 300}), "text_layer": "text"},
        ],
    )
    legs = data["equipment"]["legs"]
    legs["section"] = traced("Perfil de ensayo", "1")
    legs["azimuths"] = [traced(angle, "deg") for angle in (30, 150, 270)]
    legs["height"]["state"] = "assumed"
    legs["height"]["source"]["rule"] = "asumido.cota_de_prueba"
    source = legs["azimuths"][0]["source"]
    del source["page"]
    source["inferred_region"] = {"page": 2, "bbox": [0.2, 0.3, 0.6, 0.7], "view": "plan"}

    revision = validate(data)
    serialized = revision.model_dump(mode="json")
    assert validate(serialized) == revision
    assert set(serialized["identifiers"]) == set(data["identifiers"])
    assert serialized["documents"][0]["sheet_map"] == data["documents"][0]["sheet_map"]
    assert {"legs.count", "legs.height", "legs.section", "legs.azimuths.0"} <= fields(
        revision.equipment
    ).keys()
    assert "identifiers.drawing_number" in revision.pending_review()
    assert revision.equipment.legs.azimuths[0].source.inferred_region.view == "plan"
    assert revision.equipment.legs.height.source.rule == "asumido.cota_de_prueba"

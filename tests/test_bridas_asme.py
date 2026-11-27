"""Bridas ASME B16.5 / B16.47 A y B: identificación, tabla y geometría de cuello soldado."""

import re
from pathlib import Path

import ifcopenshell.util.element
import numpy as np
import pytest

from trazia.families.bridas import (
    parse_class,
    parse_nps,
    parse_standard,
    resolve,
    table,
)
from trazia.ifc import build_ifc, validate_ifc
from trazia.model import Attribute, load_revision
from trazia.viewer import meshes_from_ifc

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
REFERENCE = ROOT / "data/Dataset-tecnicasreunidas/vessels/SET-A/BF-C-0003/BF-C-0003.ifc"


@pytest.mark.parametrize(
    ("text", "standard"),
    [
        ("S/ASME B16.5", "B16.5"),
        ("ASTM ANSI B16.5 Typ TR", "B16.5"),
        ("ASME B-16.47 Serie A", "B16.47A"),
        ("B16.47 SER. B", "B16.47B"),
        ("ASME B16.47-B", "B16.47B"),
        ("MSS SP-44", "B16.47A"),
        ("API 605", "B16.47B"),
        ("ASME B16.47", None),  # sin serie no se elige
        ("EN 1092-1", None),
    ],
)
def test_standard_is_read_from_drawing_text(text, standard):
    assert parse_standard(text) == standard


def test_class_and_size_parsing():
    assert [parse_class(v) for v in ("300", "300#", "300 LB", "CL 600", "Class 900")] == [
        300,
        300,
        300,
        600,
        900,
    ]
    assert parse_class("PN16") is None
    assert [parse_nps(v) for v in ('12"', "1-1/2", "1.1/2", "3/4", "36")] == [
        12,
        1.5,
        1.5,
        0.75,
        36,
    ]


def test_b1647_series_are_never_guessed_and_differ():
    missing = resolve(30, 150, None)
    assert missing.dims is None and "serie" in missing.reason
    a = resolve(30, 150, "B16.47A").dims
    b = resolve(30, 150, "B16.47B").dims
    assert a.outside != b.outside and a.count != b.count
    assert resolve(12, 300, "B16.47A").dims is None  # B16.47 empieza en 26"
    assert resolve(30, 300, "B16.5").dims is None  # B16.5 acaba en 24"
    assert resolve(30, 2500, "B16.47A").dims is None  # clase que la norma no define


def test_table_rows_are_coherent():
    for dims in table().values():
        assert dims.outside > dims.pitch + dims.hole / 2 > 0
        assert dims.count % 4 == 0
        if dims.complete:
            assert dims.outside > dims.raised_face > dims.hub_bevel
            assert dims.hub_base >= dims.hub_bevel
            assert dims.hub_length > dims.thickness


def _with_rating(revision, rating, size=None, standard=None):
    for nozzle in revision.equipment.nozzles:
        src = nozzle.diameter.source
        nozzle.rating = Attribute(value=rating, unit="1", source=src)
        if size is not None:
            nozzle.size_nps = Attribute(value=size, unit="in", source=src)
        if standard is not None:
            nozzle.flange_standard = Attribute(value=standard, unit="1", source=src)
    return revision


@pytest.mark.parametrize("schema", ["IFC4", "IFC2X3"])
def test_real_dataset_gets_weld_neck_flange_only_from_traced_class(schema):
    revision = load_revision(EXAMPLES / "vessel_rev_a.json")
    revision.dataset = "real"
    assert not [p for p in build_ifc(revision).by_type("IfcElement") if "flange" in p.Name]
    model = build_ifc(_with_rating(revision, "300#"), schema=schema)
    assert not validate_ifc(model)
    flange = next(p for p in model.by_type("IfcElement") if p.Name == "V-101/nozzle-N1/flange")
    items = flange.Representation.Representations[0].Items
    assert [i.is_a() for i in items] == [
        "IfcExtrudedAreaSolid",
        "IfcRevolvedAreaSolid",
        "IfcExtrudedAreaSolid",
    ]
    props = ifcopenshell.util.element.get_psets(flange)["Pset_TrazIA"]
    assert props["Designacion"] == 'BRIDA WN RF 8" 300# S/ASME B16.5'
    assert props["ClaseOrigen"] == "campo_trazado"
    assert props["NormaOrigen"] == "deducida_por_tamano"
    assert props["NumeroTaladros"] == 12
    mesh = next(m for m in meshes_from_ifc(model.to_string()) if m["name"] == flange.Name)
    vertices = np.asarray(mesh["vertices"]).reshape(-1, 3)
    # Brida de 381 mm, centrada en el eje de la tobera (cuello girado 360°).
    assert vertices[:, 1].max() == pytest.approx(0.1905, abs=2e-3)
    assert vertices[:, 1].min() == pytest.approx(-0.1905, abs=2e-3)


def test_large_nozzle_needs_series_and_reports_why():
    revision = load_revision(EXAMPLES / "vessel_rev_a.json")
    revision.dataset = "real"
    model = build_ifc(_with_rating(revision, "150", size='30"'))
    names = {p.Name for p in model.by_type("IfcElement")}
    assert "V-101/nozzle-N1/flange" not in names
    vessel = next(p for p in model.by_type("IfcTank"))
    reasons = ifcopenshell.util.element.get_psets(vessel)["Pset_TrazIA"]["BridasSinTablaMotivoJSON"]
    assert "falta la serie" in reasons

    model = build_ifc(_with_rating(revision, "150", size='30"', standard="B16.47 Series B"))
    flange = next(p for p in model.by_type("IfcElement") if p.Name == "V-101/nozzle-N1/flange")
    props = ifcopenshell.util.element.get_psets(flange)["Pset_TrazIA"]
    assert props["Norma"] == "ASME B16.47 Serie B" and props["NumeroTaladros"] == 44
    assert props["NormaOrigen"] == "campo_trazado"


@pytest.mark.skipif(not REFERENCE.exists(), reason="dataset del evento no disponible")
def test_reference_ifc_flange_designations_resolve_in_table():
    """Cada «BRIDA WN|LWN RF n" ... clase# S/ASME B16.5» del IFC de referencia tiene fila."""
    text = REFERENCE.read_text(encoding="utf-8", errors="ignore")
    found = set(re.findall(r"BRIDA L?WN RF ([\d./-]+)\"[^']*?(\d+)# S/ASME (B16\.5)", text))
    assert found
    for size, rating, standard in found:
        dims = resolve(parse_nps(size), int(rating), standard).dims
        assert dims is not None and dims.complete, (size, rating)

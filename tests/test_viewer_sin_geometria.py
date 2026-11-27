"""El BCF y el visor ignoran elementos IFC sin geometría propia (datos sintéticos)."""

from pathlib import Path

import ifcopenshell.api.root

from trazia.ifc import build_ifc
from trazia.model import load_revision
from trazia.viewer import meshes_from_ifc

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_elemento_sin_representacion_no_rompe_las_mallas():
    revision = load_revision(EXAMPLES / "vessel_rev_a.json")
    model = build_ifc(revision)
    antes = len(meshes_from_ifc(model.to_string()))
    ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingElementProxy", name="Sin malla"
    )
    assert len(meshes_from_ifc(model.to_string())) == antes

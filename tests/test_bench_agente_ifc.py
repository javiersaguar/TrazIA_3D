"""El banco serializa las primitivas previstas y rechaza geometría fuera de contrato."""

import numpy as np
import pytest
from pydantic import ValidationError

from bench.agente_ifc import Recipe, export_recipe, piece_bounds
from trazia.ifc import validate_ifc


def part(**changes):
    return {
        "id": "N1",
        "kind": "cylinder",
        "base": (1000, 0, 1850),
        "axis": (1, 0, 0),
        "diameter": 240,
        "length": 300,
        **changes,
    }


def test_export_experimental_keeps_mm_and_axis_in_reopened_ifc(tmp_path):
    recipe = Recipe.model_validate({"parts": [part()]})
    model = export_recipe(recipe, "prueba")
    output = tmp_path / "test-DRAFT.ifc"
    model.write(str(output))
    import ifcopenshell

    reopened = ifcopenshell.open(str(output))
    assert not validate_ifc(reopened)
    bounds = piece_bounds(reopened)["N1"]
    np.testing.assert_allclose(bounds, [[1000, -120, 1730], [1300, 120, 1970]], atol=0.5)
    rebuilt = export_recipe(recipe, "prueba")
    assert reopened.by_type("IfcElement")[0].GlobalId == rebuilt.by_type("IfcElement")[0].GlobalId


@pytest.mark.parametrize(
    "parts",
    [
        [part(axis=(0, 0, 0))],
        [part(kind="ring", wall=125)],
        [part(), part()],
        [part(kind="script")],
    ],
)
def test_recipe_rejects_bad_parts(parts):
    with pytest.raises(ValidationError):
        Recipe.model_validate({"parts": parts})

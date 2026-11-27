"""El tamaño nominal (NPS) leído de la tabla viaja con la boquilla al JSON y al IFC.

Datos sintéticos de `examples/` (V-101): no hay nada de TR.
"""

from pathlib import Path

import ifcopenshell.util.element

from trazia.extraction import LabelExtractor, assemble
from trazia.ifc import build_ifc
from trazia.ingest import ingest_bytes
from trazia.model import fields, load_revision

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _borrador(con_nps: bool):
    revision = load_revision(EXAMPLES / "vessel_rev_a.json")
    document = next(d for d in revision.documents if d.id == "GA-V101")
    bundle = ingest_bytes(
        (EXAMPLES / "documents" / document.filename).read_bytes(), "drawing.pdf", "GA-V101", "A"
    )
    candidates = LabelExtractor().extract([bundle])
    if con_nps:
        base = next(c for c in candidates if c.path == "nozzles.N1.diameter")
        candidates.append(
            base.model_copy(update={"path": "nozzles.N1.size_nps", "value": 4.0, "unit": "in"})
        )
    return assemble([bundle], candidates, project_id="DEMO", equipment_id="V101", revision="A")


def test_la_boquilla_conserva_su_nps_citado_en_el_json_y_el_ifc():
    borrador = _borrador(con_nps=True)
    n1 = next(n for n in borrador.equipment.nozzles if n.id == "N1")
    assert n1.size_nps is not None
    assert (n1.size_nps.value, n1.size_nps.unit) == (4.0, "in")
    assert n1.size_nps.source.document_id == "GA-V101"
    assert "nozzles.N1.size_nps" in fields(borrador.equipment)

    modelo = build_ifc(borrador, draft=True)
    boquilla = next(
        p
        for p in modelo.by_type("IfcProduct")
        if (ifcopenshell.util.element.get_pset(p, "Pset_PipeSegmentTypeCommon") or {}).get(
            "Reference"
        )
        == "N1"
    )
    assert ifcopenshell.util.element.get_pset(boquilla, "TrazIA_Provenance")["SizeNPS"] == "4.0"


def test_sin_nps_la_boquilla_se_coloca_igual():
    borrador = _borrador(con_nps=False)
    n1 = next(n for n in borrador.equipment.nozzles if n.id == "N1")
    assert n1.size_nps is None

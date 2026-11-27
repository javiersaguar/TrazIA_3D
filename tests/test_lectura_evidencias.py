import json
from pathlib import Path

import pytest

from trazia.extraction import Candidate
from trazia.ingest import ingest_bytes
from trazia.lectura.evidencias import cargar, incorporar
from trazia.model import Source

ORIGINAL = Path(__file__).parents[1] / "examples/documents/GAD_V-101_revA.pdf"


def test_incorpora_cotas_solo_para_el_original_cotejado(tmp_path):
    bundle = ingest_bytes(ORIGINAL.read_bytes(), ORIGINAL.name, "GA-A", "A")
    previous = Candidate(
        path="diameter",
        value=1900,
        unit="mm",
        source=Source(document_id="GA-A", page=1, locator="Lectura inicial", confidence=0.8),
    )
    field = {
        "path": "diameter",
        "value": 2000,
        "unit": "mm",
        "page": 1,
        "bbox": [0.1, 0.1, 0.2, 0.2],
        "text": "Ø 2000",
        "explanation": "Cota cotejada en alzado.",
        "state": "assumed",
        "channel": "geometria",
    }
    path = tmp_path / "evidencias.json"
    path.write_text(json.dumps({bundle.document.sha256: [field]}), encoding="utf-8")
    evidence = cargar(path)
    [found] = incorporar([bundle], [previous], evidence)
    assert found.value == 2000 and found.state == "assumed"
    assert found.source.rule == "ga.cotejo_local" and found.source.bbox == (0.1, 0.1, 0.2, 0.2)
    assert found.alternatives[0].value == 1900
    assert found.source.reviewed is False
    different = bundle.model_copy(
        update={"document": bundle.document.model_copy(update={"sha256": "0" * 64})}
    )
    assert incorporar([different], [previous], evidence) == [previous]
    field["page"] = 2
    path.write_text(json.dumps({bundle.document.sha256: [field]}), encoding="utf-8")
    with pytest.raises(ValueError, match="página cotejada"):
        incorporar([bundle], [previous], cargar(path))

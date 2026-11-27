"""El trabajo pasa al pipeline la estrategia elegida en la web (datos sintéticos)."""

import pytest

from trazia.api import jobs
from trazia.pipeline import PipelineResult
from trazia.store import Store


@pytest.mark.parametrize(
    ("elegida", "esperada"), [("lectura", None), ("d_hibrido", "d_hibrido"), ("otra", None)]
)
def test_estrategia_del_trabajo(tmp_path, monkeypatch, elegida, esperada):
    recibidas = []

    def falso(documents, **kwargs):
        recibidas.append(kwargs["strategy"])
        return PipelineResult(None, [], [], "sin datos", None)

    monkeypatch.setattr(jobs, "process", falso)
    request = {
        "documents": [],
        "project_id": "EJ",
        "equipment_id": "ej-1",
        "revision": "1",
        "providers": [],
        "dataset": "synthetic",
        "strategy": elegida,
    }
    jobs.execute_pipeline(Store(tmp_path), "trabajo", request)
    assert recibidas == [esperada]

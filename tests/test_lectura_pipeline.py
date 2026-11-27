"""Interfaz `trazia.pipeline.process` (contrato con el Agente Plataforma)."""

from pathlib import Path

from trazia import lectura, pipeline
from trazia.extraction import Candidate, LabelExtractor
from trazia.model import Source
from trazia.pipeline import InputDocument, process
from trazia.reconcile import resolve

DOCS = Path(__file__).resolve().parents[1] / "examples" / "documents"


def demo_documents(rev: str = "A") -> list[InputDocument]:
    return [
        InputDocument(
            f"GAD_V-101_rev{rev}.pdf", (DOCS / f"GAD_V-101_rev{rev}.pdf").read_bytes(), "GA-V101"
        ),
        InputDocument(
            f"HDM_V-101_rev{rev}.xlsx", (DOCS / f"HDM_V-101_rev{rev}.xlsx").read_bytes(), "HDM-V101"
        ),
    ]


def test_empty_reader_preserves_ingestion_and_returns_missing_data():
    events = []
    result = process(
        demo_documents(),
        project_id="P",
        equipment_id="v-101",
        revision="A",
        on_event=events.append,
        reader=lambda *_args, **_options: [],
    )
    assert result.revision is None and result.missing_data
    assert result.error.startswith("Faltan datos explícitos:")
    [tag] = result.candidates
    assert tag.path == "tag" and tag.value == "V-101" and tag.channel == "nombre_archivo"
    assert tag.source.bbox is None and tag.source.locator.startswith(pipeline.FILENAME_LOCATOR)
    assert [e.status for e in events if e.stage == "ingest"] == ["ok", "ok"]
    assert result.run.strategy == "lectura"
    assert result.run.external_calls == 0 and result.run.cost_eur == 0.0


def test_process_builds_a_draft_with_candidates_from_the_reader(monkeypatch):
    def leer(bundles, **kwargs):
        return [c for c in LabelExtractor().extract(bundles) if c.path != "tag"]

    monkeypatch.setattr(lectura, "leer", leer)
    events = []
    result = process(
        demo_documents(),
        project_id="P",
        equipment_id="v-101",
        revision="A",
        on_event=events.append,
    )
    assert result.error is None, result.error
    assert result.revision is not None and result.revision.approval is None
    tag = result.revision.equipment.tag
    assert tag.value == "V-101" and tag.source.locator.startswith(pipeline.FILENAME_LOCATOR)
    assert result.revision.pending_review()
    assert {"ingest", "classify", "extract", "reconcile", "family", "ifc", "validate"} <= {
        e.stage for e in events
    }


def test_document_tag_keeps_priority_over_the_filename(monkeypatch):
    monkeypatch.setattr(lectura, "leer", lambda bundles, **_: LabelExtractor().extract(bundles))
    documents = [
        InputDocument(d.filename.replace("V-101", "X-999"), d.data, d.document_id)
        for d in demo_documents()
    ]
    result = process(documents, project_id="P", equipment_id="v-101", revision="A")
    assert result.error is None, result.error
    assert result.revision.equipment.tag.value == "V-101"


def test_bad_inputs_return_errors_instead_of_raising():
    result = process(
        [InputDocument("GAD_X_rev1.pdf", b"no es un pdf", "GA-X")],
        project_id="P",
        equipment_id="e",
        revision="1",
    )
    assert result.revision is None and result.error and not result.missing_data


def test_conflicting_readings_are_flagged_not_silently_chosen():
    def cand(value, confidence, channel):
        source = Source(document_id="GA", page=1, locator="t", confidence=confidence)
        return Candidate(path="diameter", value=value, unit="mm", source=source, channel=channel)

    resolution = resolve(
        [cand(2000.0, 0.9, "tabla"), cand(2100.0, 0.6, "cota"), cand(2000.0, 0.7, "texto")]
    )
    [chosen] = resolution.chosen
    assert chosen.value == 2000.0
    assert chosen.state == "conflict"
    assert resolution.conflicts == ["diameter"]
    assert [a.value for a in chosen.alternatives] == [2100.0]
    assert "lecturas distintas" in chosen.explanation

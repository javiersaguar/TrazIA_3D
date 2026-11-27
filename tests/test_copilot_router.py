"""Router del Copiloto: charla, ayuda y producto, y lecturas nuevas de la revisión."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from trazia.copilot import cloud, knowledge, router
from trazia.copilot.grounded import ask
from trazia.copilot.models import CopilotAnswer
from trazia.copilot.tools import ReadTools, stems
from trazia.model import Approval, Revision

ROOT = Path(__file__).resolve().parents[1]
BASE = Revision.model_validate_json((ROOT / "examples/vessel_rev_b.json").read_text("utf-8"))
PREVIOUS = Revision.model_validate_json((ROOT / "examples/vessel_rev_a.json").read_text("utf-8"))
FILES = {d.sha256: ROOT / "examples" / "documents" / d.filename for d in BASE.documents}


def consult(question, **options):
    return asyncio.run(
        ask(
            BASE,
            question,
            revision_id=f"TEST:{uuid4()}:B",
            revision_version=1,
            previous=PREVIOUS,
            read_document=lambda digest: FILES[digest].read_bytes(),
            **options,
        )
    )


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(cloud, "available", lambda _dataset: False)
    monkeypatch.setattr(cloud, "structured", lambda *a, **k: pytest.fail("Sin modelo"))


@pytest.mark.parametrize(
    "question,intent",
    [
        ("¿recibes mis mensajes?", "charla"),
        ("hola", "charla"),
        ("gracias", "charla"),
        ("¿qué puedes hacer?", "charla"),
        ("¿cómo apruebo una revisión?", "ayuda"),
        ("¿cómo subo planos nuevos?", "ayuda"),
        ("¿cómo funciona la estrategia D?", "producto"),
        ("¿qué pasa si la IA se inventa una cota?", "producto"),
        ("¿cuál es la elevación de N3?", "datos"),
        ("¿qué documentos tiene?", "datos"),
    ],
)
def test_classify(question, intent):
    assert router.classify(question) == intent


def test_small_talk_answers_without_sources_or_figures(offline):
    answer = consult("¿recibes mis mensajes?")
    assert answer.mode == "conversation" and not answer.abstained
    assert answer.citations == [] and answer.statements[0].citations == []
    assert "V-101" in answer.statements[0].text


def test_small_talk_from_the_model_cannot_add_figures(monkeypatch):
    monkeypatch.setattr(cloud, "available", lambda _dataset: True)
    monkeypatch.setattr(cloud, "provider", lambda _dataset: "fixture")
    monkeypatch.setattr(
        cloud, "structured", lambda *a, **k: ({"answer": "El diámetro es 2000 mm."}, {})
    )
    answer = consult("hola")
    assert "2000" not in answer.statements[0].text
    assert answer.mode == "conversation"


def test_small_talk_uses_the_model_reply_when_it_adds_no_data(monkeypatch):
    monkeypatch.setattr(cloud, "available", lambda _dataset: True)
    monkeypatch.setattr(cloud, "provider", lambda _dataset: "fixture")
    monkeypatch.setattr(
        cloud, "structured", lambda *a, **k: ({"answer": "Sí, te leo. ¿Qué quieres revisar?"}, {})
    )
    answer = consult("¿me oyes?")
    assert answer.statements[0].text == "Sí, te leo. ¿Qué quieres revisar?"
    assert answer.run.external_calls == 1


def test_help_question_cites_the_user_guide(offline):
    answer = consult("¿cómo subo planos nuevos?")
    assert not answer.abstained and answer.mode == "evidence"
    assert answer.citations[0].kind == "doc"
    assert answer.citations[0].path == "docs/AYUDA_APP.md"
    assert "Subir planos" in answer.statements[0].text


def test_product_question_is_not_answered_with_unrelated_fields(offline):
    answer = consult("¿qué pasa si la IA se inventa una cota?")
    assert answer.citations and all(c.kind == "doc" for c in answer.citations)


def test_docs_reply_with_figures_not_in_the_sources_falls_back_to_the_text(monkeypatch):
    monkeypatch.setattr(cloud, "available", lambda _dataset: True)
    monkeypatch.setattr(cloud, "provider", lambda _dataset: "fixture")

    def invented(_system, context, *_a, **_k):
        first = context["fragmentos"][0]["id"]
        return {"answer": "Se aprueba en 37 segundos.", "ids": [first]}, {}

    monkeypatch.setattr(cloud, "structured", invented)
    answer = consult("¿cómo apruebo una revisión?")
    assert "37" not in answer.statements[0].text
    assert answer.citations[0].kind == "doc"


def test_nozzle_questions_keep_the_field_path(offline):
    answer = consult("¿cuál es la elevación de N3?")
    assert answer.citations[0].kind == "field"
    assert "3700 mm" in answer.statements[0].text


def test_status_documents_and_project_index(offline):
    status = consult("¿está aprobada esta revisión?")
    assert status.citations[0].kind == "status"
    assert "sin aprobar" in status.statements[0].text
    documents = consult("¿qué documentos tiene?")
    assert "GAD_V-101_revB.pdf" in documents.statements[0].text
    project = consult("¿qué equipos hay en el proyecto?", project={"V-101": ["A", "B"]})
    assert "V-101 (rev. A, B)" in project.statements[0].text


def test_status_reports_a_stale_approval():
    approval = Approval(
        reviewer="Revisora", timestamp="2026-11-20T10:00:00+00:00", input_sha256="0" * 64
    )
    # Sin validar de nuevo: basta con que la huella aprobada no coincida con la actual.
    revision = BASE.model_copy(update={"approval": approval})
    text = ReadTools(revision, lambda _d: b"").read_status()["text"]
    assert "ya no vale" in text


def test_search_documents_reads_the_verified_original():
    tools = ReadTools(BASE, lambda digest: FILES[digest].read_bytes())
    hits = tools.search_documents("¿hay algo sobre vendor fixture?")["hits"]
    assert hits and hits[0]["filename"] == "GAD_V-101_revB.pdf" and hits[0]["page"] == 1
    citation = tools.citations[hits[0]["citation_id"]]
    assert citation.original_verified and citation.kind == "evidence"
    tampered = ReadTools(BASE, lambda _digest: b"otro contenido")
    assert tampered.search_documents("vendor fixture")["hits"] == []


def test_unknown_data_question_abstains_with_a_suggestion(offline):
    answer = consult("¿cuál es el color de la pintura del rótulo?")
    assert answer.abstained and "elevación de N3" in answer.reason


def test_knowledge_search_prefers_the_matching_guide_section():
    hits = knowledge.search("¿cómo apruebo una revisión?", prefer="docs/AYUDA_APP.md")
    assert hits[0].section.source == "docs/AYUDA_APP.md"
    assert "Aprobar" in hits[0].section.title


def test_stems_join_conjugations():
    assert stems("dicto") == stems("dictar")
    assert stems("apruebo") == stems("aprobación")


def test_evidence_answers_must_cite_every_statement():
    with pytest.raises(ValueError):
        CopilotAnswer.model_validate(
            {
                "abstained": False,
                "statements": [{"text": "Sin cita", "citations": []}],
                "proposals": [],
                "citations": [],
                "model": "x",
                "revision_id": "r",
                "revision_version": 1,
                "input_sha256": "0" * 64,
                "prompt_sha256": "0" * 64,
                "tools_used": [],
                "run": {"strategy": "x", "providers": [], "seconds": 0},
            }
        )

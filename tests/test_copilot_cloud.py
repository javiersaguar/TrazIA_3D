import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trazia.api import create_app
from trazia.copilot import cloud
from trazia.copilot.grounded import fact, respond
from trazia.design.intent import interpret, model_provider
from trazia.model import Revision
from trazia.store import RevisionRecord

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(root=ROOT, data_root=tmp_path)) as client:
        yield client


def test_model_only_selects_existing_ids_and_server_renders_facts(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "example")
    source = fact("id", "diameter", "Diámetro", "Diámetro: 2000 mm.")

    def fake(system, context, schema, **_):
        assert schema["properties"]["ids"]["items"]["enum"] == [source.citation.id]
        return {"ids": [source.citation.id], "answer": "9999 mm"}, {"prompt_tokens": 15}

    monkeypatch.setattr(cloud, "structured", fake)
    args = dict(identity="id", version=1, fingerprint="hash", dataset="synthetic")
    answer = asyncio.run(respond([source], "¿Diámetro?", **args))
    assert answer.statements[0].text == "Diámetro: 2000 mm."
    assert answer.run.external_calls == 1

    monkeypatch.setattr(cloud, "structured", lambda *a, **k: ({"ids": ["inventada"]}, {}))
    answer = asyncio.run(respond([source], "¿Diámetro?", **args))
    assert answer.abstained and not answer.statements and not answer.citations


def test_real_context_never_calls_groq_even_with_external_permission(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "example")
    monkeypatch.setenv("TRAZIA_EXTERNAL_PROVIDERS", "allow")
    monkeypatch.setenv("TRAZIA_EXTERNAL_AUTH", "prueba configurada")
    monkeypatch.setattr(cloud, "structured", lambda *a, **k: pytest.fail("Llamada externa"))
    source = fact("id", "diameter", "Diámetro", "Diámetro: 2000 mm.")
    answer = asyncio.run(
        respond(
            [source], "¿Diámetro?", identity="id", version=1, fingerprint="hash", dataset="real"
        )
    )
    assert answer.run.external_calls == 0
    assert answer.statements[0].citations == [source.citation.id]


def test_project_contexts_and_process_drafts_are_scoped(api):
    scopes = api.get("/copiloto/contexts").json()
    assert {item["kind"] for item in scopes} >= {"revision", "process", "project"}
    marine = {"kind": "process", "id": "plataforma-marina", "revision": "B"}
    result = api.post("/copiloto/project", json={**marine, "question": "¿Ancho de V-110?"})
    assert result.status_code == 200
    assert "ancho 4.1 m" in result.json()["statements"][0]["text"]
    unknown = api.post("/copiloto/project", json={**marine, "question": "¿Ancho de V-999?"})
    assert unknown.json()["abstained"]

    def prepare(text):
        return api.post(
            "/copiloto/process-drafts", json={"project_id": marine["id"], "text": text}
        ).json()

    assert prepare("Cambia el ancho de V-110 a 400 cm")["adjustments"] == [
        {"tag": "V-110", "field": "width", "value": 4.0}
    ]
    assert not prepare("Aumenta el ancho de V-110 en 4 m")["adjustments"]
    assert not prepare("Cambia el ancho de V-110 a 400 m")["adjustments"]
    assert not prepare("No cambies el ancho de V-110 a 4 m")["adjustments"]


def test_cloud_intent_only_resolves_the_parameter(api, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "example")
    from sqlmodel import Session, select

    with Session(api.app.state.store.engine) as session:
        stored = session.exec(select(RevisionRecord).where(RevisionRecord.revision == "B")).first()
        revision = Revision.model_validate_json(stored.payload)
    monkeypatch.setattr(
        cloud, "structured", lambda *a, **k: ({"target": "diameter", "value": 9999}, {})
    )
    text = "Fija la luz interior de la virola a 2100 mm"
    draft = interpret(revision, text, provider=model_provider)
    assert draft["operations"] == [
        {"id": "op-1", "target": "diameter", "value": "2100", "unit": "mm"}
    ]
    assert draft["applied"] is False
    assert not interpret(revision, "No cambies el diámetro a 2100 mm", provider=model_provider)[
        "operations"
    ]

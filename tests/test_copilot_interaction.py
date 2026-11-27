"""Regresiones de conversación y comandos del Copiloto, con modelos sintéticos."""

import asyncio
from uuid import uuid4

import pytest
from test_edicion_asistida import BASE, ROOT, run
from test_plataforma_families import family_data, traced, vector

from trazia.copilot import cloud
from trazia.copilot.grounded import ask
from trazia.design.intent import interpret
from trazia.ifc import build_ifc, validate_ifc
from trazia.model import Revision, fields


def fixture(family):
    if family == "vertical_vessel":
        return BASE
    data = family_data(family, lod=1 if family in ("pump", "compressor") else 2)
    if family == "column":
        data["equipment"]["column"]["sections"][-1]["id"] = "V11"
    return Revision.model_validate(data)


@pytest.mark.parametrize(
    "family,text,target,expected",
    [
        ("vertical_vessel", "Cambia el diámetro de la virola a 2,15 metros", "diameter", 2150),
        ("vertical_vessel", "Sube N3 en veinte centímetros", "nozzles.N3.elevation", 3900),
        ("vertical_vessel", "Gira N3 a noventa grados", "nozzles.N3.azimuth", 90),
        ("vertical_vessel", "Cambia la proyección de N1 a 35 cm", "nozzles.N1.projection", 350),
        ("horizontal_vessel", "Alarga la virola a 6,2 m", "horizontal.length", 6200),
        (
            "horizontal_vessel",
            "Sube la altura del soporte a 810 mm",
            "horizontal.support_height",
            810,
        ),
        (
            "horizontal_vessel",
            "Pon la silleta 2 a 4,9 metros",
            "horizontal.saddle_positions.1",
            4900,
        ),
        (
            "column",
            "Fija el tramo V11 a 4200 mm de altura",
            "column.sections.V11.height",
            4200,
        ),
        ("tank", "Deja la altura del techo a 1,1 m", "tank.roof_height", 1100),
        (
            "tank",
            "Cambia el diámetro del tanque a seis mil trescientos milímetros",
            "tank.diameter",
            6300,
        ),
        ("pump", "Cambia el ancho a tres coma cuatro metros", "envelope.size.y", 3400),
        ("compressor", "Alarga la envolvente a 2,25 m", "envelope.size.x", 2250),
        ("compressor", "Cambia el origen X a -1,2 metros", "envelope.origin.x", -1200),
        (
            "compressor",
            "Cambia el origen X a menos uno coma dos metros",
            "envelope.origin.x",
            -1200,
        ),
    ],
)
def test_commands_across_families_produce_valid_ifc(family, text, target, expected):
    revision = fixture(family)
    before = revision.fingerprint()
    draft = interpret(revision, text)
    assert not draft["clarifications"] and not draft["rejected"], draft
    assert draft["operations"][0]["target"] == target
    proposal, _ = run(draft["operations"], base=revision)
    assert proposal.status == "ready", proposal.issues
    assert fields(proposal.candidate.equipment)[target].value == pytest.approx(expected)
    assert revision.fingerprint() == before and proposal.candidate.approval is None
    assert not validate_ifc(build_ifc(proposal.candidate, draft=True), express_rules=False)


def horizontal():
    data = family_data("horizontal_vessel")
    data["unplaced_nozzles"] = ["N4"]
    data["equipment"]["nozzles"] = [
        dict(
            id="K3A",
            diameter=traced(120),
            elevation=traced(2800),
            azimuth=traced(0, "deg"),
            projection=traced(180),
            position=vector(1500, 0, 2800),
            direction=vector(0, 0, 1, "1"),
        )
    ]
    return Revision.model_validate(data)


@pytest.mark.parametrize("direction,sign", [("+Y", 1), ("-Y", -1)])
def test_horizontal_nozzle_requires_side_and_stays_on_shell(direction, sign):
    revision = horizontal()
    path = "nozzles.K3A.elevation"
    text = "Quiero que la boquilla de elevación sea de 2300mm, cámbiala"
    initial = interpret(
        revision,
        text,
        selected_path=path,
        provider=lambda *_: pytest.fail("El modelo no decide el lado de la virola"),
    )
    assert not initial["operations"]
    assert initial["clarifications"][0]["options"] == ["lado +Y", "lado -Y"]
    draft = interpret(revision, f"{text} (lado {direction})", selected_path=path)
    assert len(draft["operations"]) == 4 and not draft["clarifications"], draft
    checked, _ = run(draft["operations"], base=revision)
    assert checked.status == "ready", checked.issues
    nozzle = checked.candidate.equipment.nozzles[0]
    assert nozzle.position.x.value == 1500 and nozzle.elevation.value == 2300
    assert sign * nozzle.position.y.value > 0 and sign * nozzle.direction.y.value > 0
    assert checked.candidate.unplaced_nozzles == ["N4"] and checked.candidate.approval is None
    assert any(
        issue["code"] == "unplaced" and issue["severity"] == "warning" for issue in checked.issues
    )
    assert not validate_ifc(build_ifc(checked.candidate, draft=True), express_rules=False)


@pytest.mark.parametrize(
    "text",
    [
        "No cambies el diámetro a 2000 mm",
        "Aprueba y aplica el cambio de la boquilla N1",
        "Cambia la proyección de la boquilla N99 a 220 mm",
        "Cambia el diámetro de BF-V-0016 a 3200 mm",
        "Cambia la altura a 3000 mm",
        "Pon la boquilla seleccionada a 2000",
        "Cambia el diámetro a 2100 mm o 2200 mm",
    ],
)
def test_unclear_forbidden_or_foreign_requests_do_not_prepare_an_edit(text):
    result = interpret(BASE, text)
    assert not result["operations"] and not result["part_changes"]
    assert result["clarifications"] or result["rejected"]


def test_copilot_uses_selected_source_even_when_cloud_abstains(monkeypatch):
    monkeypatch.setattr(cloud, "available", lambda _dataset: True)
    monkeypatch.setattr(
        cloud, "structured", lambda *a, **k: pytest.fail("La fuente es determinista")
    )
    by_hash = {d.sha256: (ROOT / "examples" / "documents" / d.filename) for d in BASE.documents}
    answer = asyncio.run(
        ask(
            BASE,
            "¿De dónde sale el valor seleccionado?",
            revision_id=f"TEST:{uuid4()}:B",
            revision_version=1,
            path="nozzles.N1.elevation",
            read_document=lambda digest: by_hash[digest].read_bytes(),
        )
    )
    assert not answer.abstained and answer.run.external_calls == 0
    assert answer.citations[0].path == "nozzles.N1.elevation"
    assert answer.citations[0].filename and answer.citations[0].page
    assert "mm" in answer.statements[0].text


@pytest.mark.parametrize(
    "family,path,value",
    [
        ("horizontal_vessel", "horizontal.saddle_positions.0", 1200),
        ("column", "column.sections.V11.height", 4000),
        ("tank", "tank.roof_height", 1000),
        ("pump", "envelope.size.y", 3000),
        ("compressor", "envelope.origin.x", -1000),
    ],
)
def test_selected_measurement_retains_its_value_and_reference(family, path, value):
    revision = fixture(family)
    answer = asyncio.run(
        ask(
            revision,
            "¿Cuánto mide el campo seleccionado?",
            revision_id=f"TEST:{family}:A",
            revision_version=1,
            path=path,
            read_document=lambda _: b"synthetic-family-parameters",
        )
    )
    assert not answer.abstained and answer.run.external_calls == 0
    assert answer.citations[0].path == path and answer.citations[0].page == 1
    assert answer.citations[0].filename == "synthetic-fixture.txt"
    assert f"{value} mm" in answer.statements[0].text


@pytest.mark.parametrize(
    "command,identity,present",
    [
        (
            "Copiloto, añade boquilla N5 diámetro cien milímetros proyección veinte "
            "centímetros elevación cuatro mil quinientos milímetros azimut cuarenta y cinco grados",
            "N5",
            True,
        ),
        ("Por favor, quita la boquilla N4", "N4", False),
    ],
)
def test_add_and_remove_parts_from_spoken_orders(command, identity, present):
    previous = BASE.fingerprint()
    draft = interpret(
        BASE, command, provider=lambda *_: pytest.fail("La orden explícita se resuelve localmente")
    )
    assert not draft["clarifications"] and not draft["rejected"], draft
    assert len(draft["part_changes"]) == 1
    proposal, _ = run([], part_changes=draft["part_changes"])
    assert proposal.status == "ready", proposal.issues
    assert (identity in {nozzle.id for nozzle in proposal.candidate.equipment.nozzles}) == present
    assert BASE.fingerprint() == previous and proposal.candidate.approval is None
    assert not validate_ifc(build_ifc(proposal.candidate, draft=True), express_rules=False)


def test_copilot_requests_another_context_without_exposing_its_data():
    answer = asyncio.run(
        ask(
            BASE,
            "¿De dónde sale la elevación de N1 del 80V01?",
            revision_id="TEST",
            revision_version=1,
            path="nozzles.N1.elevation",
            read_document=lambda _: pytest.fail("No debe leer otro contexto"),
        )
    )
    assert answer.abstained and not answer.citations and "80V01" in answer.reason


def test_active_api_resolves_voice_transcript_with_selected_context(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from trazia.api import create_app
    from trazia.copilot import voice

    async def transcribe(audio, media_type):
        assert audio.startswith(b"OggS") and media_type == "audio/ogg"
        return "Quiero que el diámetro sea de dos coma quince metros, cámbialo"

    monkeypatch.setattr(voice, "free_key", lambda: "prueba")
    monkeypatch.setattr(voice, "transcribe", transcribe)
    monkeypatch.setenv("TRAZIA_EXTERNAL_PROVIDERS", "deny")
    monkeypatch.delenv("TRAZIA_OFFLINE", raising=False)
    with TestClient(create_app(root=ROOT, data_root=tmp_path)) as client:
        reply = client.post(
            "/copiloto/voice",
            params={"kind": "revision", "identity": "B"},
            files={"file": ("clip.ogg", b"OggS-synthetic-test", "audio/ogg")},
        )
        assert reply.status_code == 200, reply.text
        ask = client.post(
            "/copiloto",
            json={
                "revision_id": "B",
                "path": "diameter",
                "question": "¿De dónde sale el valor seleccionado?",
            },
        ).json()
        assert not ask["abstained"] and ask["citations"][0]["path"] == "diameter"
        answer = client.post(
            "/copiloto/design-proposals",
            json={
                "revision_id": "B",
                "text": reply.json()["text"],
                "selected_path": "diameter",
            },
        )
        assert answer.status_code == 200, answer.text
        draft = answer.json()
        assert draft["applied"] is False and not draft["clarifications"]
        assert draft["operations"][0]["target"] == "diameter"
        assert draft["operations"][0]["value"] == "2,15"
        base = client.get("/revisions/B").json()
        assert base["equipment"]["diameter"]["value"] == BASE.equipment.diameter.value


def test_active_api_understands_spoken_units_in_a_process_project(tmp_path):
    from fastapi.testclient import TestClient

    from trazia.api import create_app

    with TestClient(create_app(root=ROOT, data_root=tmp_path)) as client:
        reply = client.post(
            "/copiloto/process-drafts",
            json={
                "project_id": "plataforma-marina",
                "text": "Quiero que el ancho de V-110 sea de cuatro metros",
            },
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["adjustments"] == [{"tag": "V-110", "field": "width", "value": 4.0}]

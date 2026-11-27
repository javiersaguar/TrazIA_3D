import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from trazia.api import create_app
from trazia.copilot import voice
from trazia.store import RevisionRecord

ROOT = Path(__file__).resolve().parents[1]
REVISION = "DEMO-PLANT:vessel-001:A"
CLIP = b"\x1a\x45\xdf\xa3audio-sintetico-de-prueba"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAZIA_WARMUP", "0")
    monkeypatch.setenv("TRAZIA_EXTERNAL_PROVIDERS", "synthetic_only")
    monkeypatch.setenv("TRAZIA_VOICE_GROQ_FREE", "1")
    monkeypatch.setenv("GROQ_VOICE_FREE_API_KEY", "clave-ficticia-free")
    monkeypatch.setenv("GROQ_API_KEY", "clave-ficticia-texto")
    monkeypatch.delenv("TRAZIA_OFFLINE", raising=False)
    monkeypatch.setenv("TRAZIA_REGISTRO_ENVIOS", str(tmp_path / "envios.jsonl"))
    with TestClient(create_app(root=ROOT, data_root=tmp_path)) as client:
        yield client


def endpoint(kind="revision", identity=REVISION):
    return f"/copiloto/voice?kind={kind}&identity={identity}"


def post(client, path=None, clip=CLIP, content_type="audio/webm"):
    return client.post(path or endpoint(), files={"file": ("dictado", clip, content_type)})


def mock_groq(monkeypatch, status=200, payload=None):
    requests = []
    original = voice.transcribe

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=payload or {"text": " ¿Cuál es el diámetro? "})

    async def transcribe(audio, content_type):
        return await original(audio, content_type, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(voice, "transcribe", transcribe)
    return requests


def test_dictation_sends_only_audio_and_audits_its_hash(client, monkeypatch, tmp_path):
    requests = mock_groq(monkeypatch)
    assert client.get(endpoint()).json() == {"available": True}
    response = post(client, content_type="audio/webm;codecs=opus")
    assert response.status_code == 200
    assert response.json() == {"text": "¿Cuál es el diámetro?"}
    (request,) = requests
    assert str(request.url) == voice.URL
    assert request.headers["Authorization"] == "Bearer clave-ficticia-free"
    assert b"whisper-large-v3-turbo" in request.content
    assert b"dictado.webm" in request.content
    assert CLIP in request.content
    assert REVISION.encode() not in request.content
    audit = (tmp_path / "envios.jsonl").read_text()
    assert json.loads(audit)["dataset"] == "synthetic"
    assert CLIP.decode("latin1") not in audit
    assert "diámetro" not in audit


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("TRAZIA_VOICE_GROQ_FREE", "0"),
        ("GROQ_VOICE_FREE_API_KEY", ""),
        ("GROQ_VOICE_FREE_API_KEY", "clave-ficticia-texto"),
        ("TRAZIA_OFFLINE", "1"),
        ("TRAZIA_EXTERNAL_PROVIDERS", "deny"),
    ],
)
def test_without_verified_free_configuration_no_audio_leaves(client, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    requests = mock_groq(monkeypatch)
    assert client.get(endpoint()).json() == {"available": False}
    assert post(client).status_code == 503
    assert not requests


def test_real_or_unknown_scope_never_sends(client, monkeypatch):
    requests = mock_groq(monkeypatch)
    with Session(client.app.state.store.engine) as session:
        record = session.get(RevisionRecord, REVISION)
        payload = json.loads(record.payload)
        payload["dataset"] = "real"
        record.payload = json.dumps(payload)
        session.add(record)
        session.commit()

    for path in [
        endpoint(),
        endpoint("catalogue"),
        endpoint("project"),
        endpoint("process", "missing"),
    ]:
        assert client.get(path).json() == {"available": False}
        assert post(client, path).status_code == 403
    assert not requests


def test_invalid_or_oversized_audio_is_rejected(client, monkeypatch):
    requests = mock_groq(monkeypatch)
    assert post(client, clip=b"").status_code == 422
    assert post(client, content_type="application/pdf").status_code == 415
    assert post(client, clip=CLIP + b"0" * voice.MAX_AUDIO_BYTES).status_code == 413
    assert post(client, clip=CLIP + b"0" * (voice.MAX_AUDIO_BYTES + 8192)).status_code == 413
    assert not requests


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [(429, {}, 429), (402, {}, 502), (200, {"text": "  "}, 422)],
)
def test_error_is_recoverable_without_retries(client, monkeypatch, status, payload, expected):
    requests = mock_groq(monkeypatch, status=status, payload=payload)
    assert post(client).status_code == expected
    assert len(requests) == 1

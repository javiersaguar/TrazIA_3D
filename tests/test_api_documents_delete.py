"""Borrado de documentos subidos sin romper revisiones ni la verificación por SHA-256."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from trazia.api import create_app
from trazia.store import JobRecord

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_root=tmp_path, root=ROOT)) as client:
        yield client


def key():
    return {"Idempotency-Key": str(uuid4())}


def upload(client, content: bytes, name="plano.pdf"):
    response = client.post(
        "/documents", files={"file": (name, content, "application/pdf")}, headers=key()
    )
    assert response.status_code == 201, response.text
    return response.json()


def blob(client, sha):
    return client.app.state.store.blobs / sha[:2] / sha


def test_borra_un_documento_subido_y_su_original(client):
    document = upload(client, b"%PDF-1.4 borrador sin citar")
    listed = {row["id"]: row for row in client.get("/documents").json()}
    assert listed[document["id"]]["uploaded"] is True
    assert listed[document["id"]]["cited_by"] == []
    assert blob(client, document["sha256"]).exists()

    headers = key()
    response = client.delete(f"/documents/{document['id']}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["blob_removed"] is True
    assert not blob(client, document["sha256"]).exists()
    assert document["id"] not in {row["id"] for row in client.get("/documents").json()}
    # La misma clave repite la respuesta sin volver a ejecutar el borrado.
    assert client.delete(f"/documents/{document['id']}", headers=headers).status_code == 200


def test_conserva_el_original_compartido_por_otro_documento(client):
    content = b"%PDF-1.4 mismo contenido"
    first, second = upload(client, content), upload(client, content, "copia.pdf")
    assert first["sha256"] == second["sha256"] == hashlib.sha256(content).hexdigest()
    response = client.delete(f"/documents/{first['id']}", headers=key())
    assert response.status_code == 200 and response.json()["blob_removed"] is False
    assert blob(client, second["sha256"]).exists()


def test_requiere_clave_y_responde_404(client):
    assert client.delete("/documents/no-existe").status_code == 428
    response = client.delete("/documents/no-existe", headers=key())
    assert response.status_code == 404
    assert response.json()["detail"] == "No existe ese documento"


def test_rechaza_borrar_un_documento_citado_por_una_revision(client):
    cited = next(row for row in client.get("/documents").json() if row["cited_by"])
    assert cited["uploaded"] is False
    response = client.delete(f"/documents/{cited['id']}", headers=key())
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "lo cita la revisión guardada" in detail and cited["filename"] in detail
    assert cited["id"] in {row["id"] for row in client.get("/documents").json()}
    assert blob(client, cited["sha256"]).exists()
    # Una copia subida del mismo original tampoco se borra: la revisión cita ese SHA-256.
    path = ROOT / "examples" / "documents" / cited["filename"]
    copy = upload(client, path.read_bytes(), cited["filename"])
    assert client.delete(f"/documents/{copy['id']}", headers=key()).status_code == 409


def test_rechaza_borrar_un_documento_de_un_trabajo_en_curso(client):
    document = upload(client, b"%PDF-1.4 en cola")
    with Session(client.app.state.store.engine) as session:
        session.add(
            JobRecord(
                id=str(uuid4()),
                tag="V-900",
                status="running",
                request_json=json.dumps({"documents": [document["id"]]}),
            )
        )
        session.commit()
    listed = {row["id"]: row for row in client.get("/documents").json()}
    assert listed[document["id"]]["active_jobs"]
    response = client.delete(f"/documents/{document['id']}", headers=key())
    assert response.status_code == 409
    assert "trabajo en curso" in response.json()["detail"]

"""Borrado de revisiones guardadas: solo borradores y sin romper derivaciones."""

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from trazia.api import create_app
from trazia.store import AuditRecord, ChangeProposalRecord, JobRecord, RevisionRecord

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_root=tmp_path, root=ROOT)) as client:
        yield client


def revision_b(client):
    response = client.get("/equipment/V-101/revisions/B")
    return response.json(), response.headers["etag"]


def identity_of(client, label):
    with Session(client.app.state.store.engine) as session:
        return session.exec(select(RevisionRecord.id).where(RevisionRecord.revision == label)).one()


def delete(client, identity, etag):
    return client.delete(
        f"/revisions/{identity}", headers={"If-Match": etag, "Idempotency-Key": str(uuid4())}
    )


def test_borra_un_borrador_con_su_auditoria_y_libera_sus_originales(client):
    _, etag = revision_b(client)
    identity = identity_of(client, "B")
    with Session(client.app.state.store.engine) as session:
        session.add(
            AuditRecord(
                revision_id=identity, path="x", actor="ana", before_json="1", after_json="2"
            )
        )
        session.commit()
    only_b = [row["id"] for row in client.get("/documents").json() if row["cited_by"] == [identity]]
    assert only_b
    assert delete(client, identity, '"99"').status_code == 412
    assert client.delete(f"/revisions/{identity}", headers={"If-Match": etag}).status_code == 428
    response = delete(client, identity, etag)
    assert response.status_code == 200, response.text
    assert response.json()["removed"]["audit"] == 1
    assert client.get(f"/revisions/{identity}").status_code == 404
    assert client.get("/equipment").json()[0]["revisions"] == ["A"]
    # Los originales que solo citaba B quedan libres para borrarse.
    for document in only_b:
        response = client.delete(f"/documents/{document}", headers={"Idempotency-Key": "k"})
        assert response.status_code == 200, response.text
    assert delete(client, identity, etag).status_code == 404


def test_no_borra_una_revision_aprobada(client):
    identity = identity_of(client, "B")
    with Session(client.app.state.store.engine) as session:
        record = session.get(RevisionRecord, identity)
        payload = json.loads(record.payload)
        payload["approval"] = {"reviewer": "Ana", "timestamp": "2026-11-26T10:00:00+00:00"}
        record.payload = json.dumps(payload)
        session.add(record)
        session.commit()
        etag = f'"{record.version}"'
    response = delete(client, identity, etag)
    assert response.status_code == 409
    assert "aprobada" in response.json()["detail"]


def test_no_borra_una_revision_con_trabajo_activo(client):
    _, etag = revision_b(client)
    identity = identity_of(client, "B")
    with Session(client.app.state.store.engine) as session:
        session.add(
            JobRecord(
                id="job-1",
                tag="V-101",
                status="queued",
                request_json=json.dumps({"previous_id": identity, "documents": []}),
            )
        )
        session.commit()
    response = delete(client, identity, etag)
    assert response.status_code == 409 and "trabajo en curso job-1" in response.json()["detail"]


def test_no_borra_la_base_de_un_cambio_de_diseno_aplicado(client):
    _, etag = revision_b(client)
    base, derived = identity_of(client, "A"), identity_of(client, "B")
    with Session(client.app.state.store.engine) as session:
        session.add(
            ChangeProposalRecord(
                id="p-1",
                revision_id=base,
                base_version=1,
                base_sha256="0" * 64,
                status="applied",
                actor="ana",
                input_json="{}",
                evaluation_json="{}",
                content_json="{}",
                proposal_sha256="0" * 64,
                target_label="B",
                applied_revision_id=derived,
                expires_at=time.time() + 60,
            )
        )
        session.commit()
    base_etag = client.get(f"/revisions/{base}").headers["etag"]
    response = delete(client, base, base_etag)
    assert response.status_code == 409 and derived in response.json()["detail"]
    response = delete(client, derived, etag)
    assert response.status_code == 409 and "reversión" in response.json()["detail"]

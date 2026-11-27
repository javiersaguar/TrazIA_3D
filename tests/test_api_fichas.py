"""Fichas de equipo: subidas que se suman a la ficha existente, borrado completo y retirada.

Datos sintéticos de la demo (V-101) y copias suyas en otros proyectos para simular homónimos.
"""

import json
import secrets
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from trazia.api import create_app
from trazia.store import JobRecord, RevisionRecord

ROOT = Path(__file__).resolve().parents[1]
DEMO = ("DEMO-PLANT", "vessel-001")


def app_client(tmp_path):
    return TestClient(create_app(data_root=tmp_path, root=ROOT))


@pytest.fixture
def client(tmp_path):
    with app_client(tmp_path) as client:
        yield client


def key():
    return {"Idempotency-Key": str(uuid4())}


def homonym(client, project="OTRO", tag=" v-101 ", equipment_id="v-101-otro"):
    """Copia la Rev A de la demo en otro proyecto, con el mismo código escrito distinto."""
    with Session(client.app.state.store.engine) as session:
        source = session.exec(select(RevisionRecord).where(RevisionRecord.revision == "A")).first()
        payload = json.loads(source.payload)
        payload["project_id"] = project
        payload["equipment"]["id"] = equipment_id
        payload["equipment"]["tag"]["value"] = tag.strip()
        session.add(
            RevisionRecord(
                id=f"{project}:{equipment_id}:A",
                project_id=project,
                equipment_id=equipment_id,
                tag=tag.strip(),
                revision="A",
                payload=json.dumps(payload),
            )
        )
        session.commit()


def fichas(client):
    return {(row["project_id"], row["equipment_id"]) for row in client.get("/equipment").json()}


def test_busca_la_ficha_por_codigo_sin_mayusculas_ni_espacios(client):
    homonym(client)
    found = client.get("/equipment/match", params={"tag": "  v-101 "}).json()
    assert [(f["project_id"], f["equipment_id"]) for f in found] == [
        ("DEMO-PLANT", "vessel-001"),
        ("OTRO", "v-101-otro"),
    ]
    demo = found[0]
    assert [r["label"] for r in demo["revisions"]] == ["A", "B"]
    assert all(len(d["sha256"]) == 64 for r in demo["revisions"] for d in r["documents"])
    only = client.get("/equipment/match", params={"tag": "V-101", "project_id": "OTRO"}).json()
    assert [f["project_id"] for f in only] == ["OTRO"]
    assert client.get("/equipment/match", params={"tag": "X-1"}).json() == []


def test_borra_una_ficha_homonima_sin_tocar_la_otra_y_no_vuelve_al_reiniciar(tmp_path):
    with app_client(tmp_path) as client:
        homonym(client)
        response = client.delete("/equipment/DEMO-PLANT/vessel-001", headers=key())
        assert response.status_code == 200, response.text
        assert response.json()["revisions"] == ["A", "B"]
        assert fichas(client) == {("OTRO", "v-101-otro")}
        assert client.delete("/equipment/DEMO-PLANT/vessel-001", headers=key()).status_code == 404
        assert client.delete("/equipment/OTRO/v-101-otro").status_code == 428
    # La siembra de la demo respeta el borrado.
    with app_client(tmp_path) as client:
        assert fichas(client) == {("OTRO", "v-101-otro")}


def test_una_ficha_protegida_no_se_borra_y_se_puede_retirar(tmp_path):
    with app_client(tmp_path) as client:
        homonym(client)
        with Session(client.app.state.store.engine) as session:
            request = {"project_id": "OTRO", "equipment_id": "v-101-otro", "revision": "A"}
            session.add(JobRecord(id="job-1", tag="V-101", request_json=json.dumps(request)))
            session.commit()
        response = client.delete("/equipment/OTRO/v-101-otro", headers=key())
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "Rev A" in detail and "trabajo en curso" in detail and "retirarla" in detail
        assert ("OTRO", "v-101-otro") in fichas(client)
        body = {"project_id": "OTRO", "equipment_id": "v-101-otro", "tag": "V-101"}
        assert client.post("/equipment/retire", json=body, headers=key()).status_code == 200
        assert fichas(client) == {DEMO}
        assert [f["project_id"] for f in client.get("/equipment/match?tag=V-101").json()] == [
            "DEMO-PLANT"
        ]
        # El historial se conserva: la revisión sigue accesible por su ID estable.
        assert client.get("/revisions/OTRO:v-101-otro:A").status_code == 200
    with app_client(tmp_path) as client:
        assert fichas(client) == {DEMO}


def test_una_revision_borrada_de_la_demo_no_vuelve_al_reiniciar(tmp_path):
    with app_client(tmp_path) as client:
        identity = "DEMO-PLANT:vessel-001:B"
        etag = client.get(f"/revisions/{identity}").headers["etag"]
        headers = {"If-Match": etag, **key()}
        assert client.delete(f"/revisions/{identity}", headers=headers).status_code == 200
    with app_client(tmp_path) as client:
        assert client.get("/equipment").json()[0]["revisions"] == ["A"]


def test_solo_un_administrador_borra_o_retira_fichas(monkeypatch, tmp_path):
    secret = secrets.token_hex(12)
    monkeypatch.setenv("TRAZIA_AUTH", "1")
    monkeypatch.setenv("TRAZIA_AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("TRAZIA_ADMIN_PASSWORD", secret)
    monkeypatch.setenv("TRAZIA_USUARIOS", "revisor")
    with app_client(tmp_path) as client:
        body = {"project_id": "DEMO-PLANT", "equipment_id": "vessel-001", "tag": "V-101"}
        client.post("/auth/guest")
        assert client.delete("/equipment/DEMO-PLANT/vessel-001", headers=key()).status_code == 403
        client.post("/auth/logout")
        client.post("/auth/login", json={"username": "revisor", "password": secret})
        assert client.delete("/equipment/DEMO-PLANT/vessel-001", headers=key()).status_code == 403
        assert client.post("/equipment/retire", json=body, headers=key()).status_code == 403
        client.post("/auth/logout")
        client.post("/auth/login", json={"username": "miguel.vera", "password": secret})
        assert client.delete("/equipment/DEMO-PLANT/vessel-001", headers=key()).status_code == 200

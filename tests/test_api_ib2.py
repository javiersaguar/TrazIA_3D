import json
from io import BytesIO
from pathlib import Path

import ifcopenshell
import pytest
from reportlab.pdfgen.canvas import Canvas

from trazia.ifc import validate_ifc
from trazia.model import Revision
from trazia.review import approve

TestClient = pytest.importorskip("fastapi.testclient").TestClient
sqlmodel = pytest.importorskip("sqlmodel")

from trazia.api import create_app  # noqa: E402
from trazia.queue import ProcessQueue  # noqa: E402
from trazia.store import (  # noqa: E402
    AuditRecord,
    DocumentRecord,
    EventRecord,
    IdempotencyRecord,
    JobCacheRecord,
    JobRecord,
    RevisionRecord,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/documents"


def _headers(key, **headers):
    return {"Idempotency-Key": key, **headers}


def _upload_originals(client, revision):
    inputs = {}
    for prefix, suffix in (("GAD", "pdf"), ("HDM", "xlsx")):
        name = f"{prefix}_V-101_rev{revision}.{suffix}"
        response = client.post(
            "/documents",
            files={"file": (name, (EXAMPLES / name).read_bytes())},
            data={"revision": revision, "document_id": prefix},
            headers=_headers(name),
        )
        assert response.status_code == 201, response.text
        inputs[prefix] = response.json()["id"]
    return list(inputs.values())


def _submit(client, revision, previous=None):
    config = {
        "project_id": "DEMO",
        "equipment_id": "vessel-101",
        "revision": revision,
        "documents": _upload_originals(client, revision),
        "previous_id": previous,
    }
    endpoint = "/equipment/V-101/jobs" if previous is None else "/jobs"
    if previous is not None:
        config["tag"] = "V-101"
    headers = _headers(f"job-{revision}")
    job = client.post(endpoint, json=config, headers=headers)
    assert job.status_code == 202, job.text
    identity = job.json()["job_id"]
    assert client.post(endpoint, json=config, headers=headers).json()["job_id"] == identity
    events = client.get(f"/jobs/{identity}/events")
    assert events.status_code == 200
    assert "event: stage" in events.text and '"stage":"ingest"' in events.text
    assert 'event: complete\ndata: {"status": "done"}' in events.text, events.text
    result = client.get(f"/jobs/{identity}").json()
    assert result["status"] == "done", result
    # Cada etapa guarda cuánto ha durado: Métricas lo reparte en tramos.
    with sqlmodel.Session(client.app.state.store.engine) as session:
        etapas = session.exec(
            sqlmodel.select(EventRecord).where(
                EventRecord.job_id == identity, EventRecord.stage != "job"
            )
        ).all()
    assert etapas and all(e.duration_seconds is not None for e in etapas)
    return result["revision_id"]


def test_recorrido_ib2_dos_revisiones_desde_originales(tmp_path, monkeypatch):
    monkeypatch.delenv("TRAZIA_OFFLINE", raising=False)
    with TestClient(create_app(data_root=tmp_path, root=ROOT, seed=False)) as client:
        assert client.get("/health").json()["queue"] == "process"
        assert client.get("/reference-system").status_code == 200
        before = _submit(client, "A")
        after = _submit(client, "B", previous=before)
        routes = client.get("/openapi.json").json()["paths"]
        assert set(routes).isdisjoint({"/plant", "/bench", "/estudio"})
        assert "/review-sessions" in routes

        listed = client.get("/equipment").json()
        assert listed[0]["tag"] == "V-101"
        assert set(listed[0]["revisions"]) == {"A", "B"}
        revision = client.get("/equipment/V-101/revisions/A", params={"project_id": "DEMO"})
        assert revision.status_code == 200
        assert revision.json()["approval"] is None
        fields = client.get(f"/revisions/{before}/fields").json()
        evidence = fields["diameter"]["source"]
        assert evidence["document_id"] == "GAD" and evidence["page"] == 1
        assert len(evidence["bbox"]) == 4
        original = client.get(f"/revisions/{before}/documents/GAD")
        assert original.content == (EXAMPLES / "GAD_V-101_revA.pdf").read_bytes()
        assert client.get(f"/revisions/{before}/validation").status_code == 200
        assert client.get(f"/revisions/{before}/ifc").status_code == 409
        draft = client.get(f"/revisions/{before}/ifc", params={"draft": "true"})
        assert draft.status_code == 200
        assert validate_ifc(ifcopenshell.file.from_string(draft.content.decode())) == []

        delta = client.get("/diff", params={"from": before, "to": after})
        assert delta.status_code == 200, delta.text
        grouped = delta.json()["por_id"]
        assert "N4" in grouped["altas"]
        assert "N3" in grouped["cambiados"]
        assert grouped["cambiados"]["N3"]["citas"]
        assert any(item["path"] == "height" for item in grouped["sin_marca"])
        assert client.get("/diff/bcf", params={"from": before, "to": after}).content[:2] == b"PK"

        update = client.patch(
            f"/revisions/{before}/fields/diameter",
            json={"state": "accepted", "actor": "Iria"},
            headers=_headers("edit", **{"If-Match": revision.headers["ETag"]}),
        )
        assert update.status_code == 200, update.text
        audit = client.get(f"/revisions/{before}/audit").json()["actions"]
        assert [action["path"] for action in audit] == ["diameter"]
        undo = client.post(
            f"/revisions/{before}/audit/{audit[0]['id']}/undo",
            json={"actor": "Iria"},
            headers=_headers("undo", **{"If-Match": update.headers["ETag"]}),
        )
        assert (
            undo.status_code == 200 and undo.json()["equipment"]["diameter"]["state"] == "candidate"
        )


def test_serializa_identificadores_y_mapa_de_la_lamina(tmp_path):
    with TestClient(create_app(data_root=tmp_path, root=ROOT)) as client:
        with sqlmodel.Session(client.app.state.store.engine) as session:
            record = session.exec(
                sqlmodel.select(RevisionRecord).where(RevisionRecord.revision == "A")
            ).one()
            data = json.loads(record.payload)
            data["identifiers"] = {"drawing_number": data["equipment"]["tag"]}
            drawing = next(item for item in data["documents"] if item["filename"].endswith(".pdf"))
            drawing["sheet_map"] = [
                {"page": 1, "size": "A4", "rotation": 0, "text_layer": "text", "views": []}
            ]
            record.payload = Revision.model_validate_json(json.dumps(data)).model_dump_json()
            session.add(record)
            session.commit()
        response = client.get("/revisions/A")
        assert response.status_code == 200
        assert response.json()["identifiers"]["drawing_number"]["value"] == "V-101"
        assert any(
            item.get("sheet_map") == drawing["sheet_map"] for item in response.json()["documents"]
        )
        fields = client.get("/revisions/A/fields").json()
        assert (
            fields["identifiers.drawing_number"]["source"]["document_id"]
            == (data["equipment"]["tag"]["source"]["document_id"])
        )


def test_valida_la_revision_en_las_tres_entradas(tmp_path, monkeypatch):
    async def keep_queued(self, job_id):
        pass

    monkeypatch.setattr(ProcessQueue, "enqueue", keep_queued)
    with TestClient(create_app(data_root=tmp_path, root=ROOT, seed=False)) as client:
        documents = _upload_originals(client, "A")
        files = {"file": ("test.pdf", b"prueba de revision")}
        for label in (
            "",
            " ",
            " A",
            "A ",
            ".",
            "..",
            "A:B",
            "A/B",
            "A\\B",
            "A\x00B",
            "A\u202eB",
            "A" * 51,
        ):
            upload = client.post(
                "/documents", files=files, data={"revision": label}, headers=_headers("bad-upload")
            )
            assert upload.status_code == 422, (label, upload.text)
            for endpoint, extra in (("/jobs", {"tag": "P/V-101"}), ("/equipment/V-101/jobs", {})):
                result = client.post(
                    endpoint,
                    json={"revision": label, "documents": documents, **extra},
                    headers=_headers("bad-job"),
                )
                assert (
                    result.status_code == 422 and result.json()["issues"][0]["path"] == "revision"
                )
        upload = client.post("/documents", files=files, headers=_headers("default-upload"))
        assert upload.status_code == 201 and upload.json()["revision"] == "A"
        without_label = client.post(
            "/jobs", json={"tag": "P/V-101", "documents": documents}, headers=_headers("no-label")
        )
        assert without_label.status_code == 422
        for endpoint, config in (
            ("/equipment/V-101/jobs", {"equipment_id": "one"}),
            ("/jobs", {"tag": "P/V-101", "revision": "Revisión 00-B", "equipment_id": "two"}),
        ):
            result = client.post(
                endpoint, json={"documents": documents, **config}, headers=_headers("valid-job")
            )
            assert result.status_code == 202, result.text


def test_valida_revision_persistida_y_expone_impedimentos_de_revision(tmp_path):
    with TestClient(create_app(data_root=tmp_path, root=ROOT)) as client:
        with sqlmodel.Session(client.app.state.store.engine) as session:
            record = session.exec(
                sqlmodel.select(RevisionRecord).where(RevisionRecord.revision == "A")
            ).one()
            data = json.loads(record.payload)
            data["unplaced_nozzles"] = ["N42"]
            data["equipment"]["diameter"]["state"] = "assumed"
            data["equipment"]["diameter"]["source"]["rule"] = "prueba.hipotesis"
            record.payload = Revision.model_validate(data).model_dump_json()
            session.commit()
        diagnostics = client.get("/revisions/A/validation").json()
        assert {(i["path"], i["code"]) for i in diagnostics["issues"]} >= {
            ("diameter", "assumed"),
            ("nozzles.N42", "unplaced_nozzle"),
        }

        for payload in (
            '{"contrato":"incompleto"}',
            Revision.model_validate({**data, "revision": "ZZ"}).model_dump_json(),
        ):
            with sqlmodel.Session(client.app.state.store.engine) as session:
                record = session.exec(
                    sqlmodel.select(RevisionRecord).where(RevisionRecord.revision == "A")
                ).one()
                record.payload = payload
                session.commit()
            for endpoint in (
                "/equipment/V-101/revisions/A",
                "/revisions/A",
                "/revisions/A/fields",
                "/revisions/A/validation",
                "/revisions/A/ifc?draft=true",
            ):
                response = client.get(endpoint)
                assert response.status_code == 409 and "revisión" in response.json()["detail"]


def test_frena_trabajos_duplicados_y_permite_reintentar_tras_cancelar(tmp_path, monkeypatch):
    async def keep_queued(self, job_id):
        pass

    monkeypatch.setattr(ProcessQueue, "enqueue", keep_queued)
    with TestClient(create_app(data_root=tmp_path, root=ROOT, seed=False)) as client:
        config = {"documents": _upload_originals(client, "A"), "revision": "A", "tag": "V-101"}
        first = client.post("/jobs", json=config, headers=_headers("initial"))
        assert first.status_code == 202
        identity = first.json()["job_id"]
        duplicate = client.post("/jobs", json=config, headers=_headers("second-key"))
        assert duplicate.status_code == 409 and "trabajo activo" in duplicate.json()["detail"]
        cancelled = client.post(f"/jobs/{identity}/cancel", headers=_headers("cancel"))
        assert cancelled.json()["status"] == "cancelled"
        assert client.get(f"/jobs/{identity}").json()["lease_until"] is None
        assert '"status": "cancelled"' in client.get(f"/jobs/{identity}/events").text
        assert client.post("/jobs", json=config, headers=_headers("retry")).status_code == 202


def test_original_ausente_o_corrupto_da_respuestas_controladas(tmp_path):
    with TestClient(create_app(data_root=tmp_path, root=ROOT)) as client:
        data = client.get("/revisions/A").json()
        original = next(item for item in data["documents"] if item["filename"].endswith(".pdf"))
        route = f"/revisions/A/documents/{original['id']}"
        digest = original["sha256"]
        blob = tmp_path / "store" / digest[:2] / digest
        with sqlmodel.Session(client.app.state.store.engine) as session:
            record = session.exec(
                sqlmodel.select(RevisionRecord).where(RevisionRecord.revision == "A")
            ).one()
            model = Revision.model_validate_json(record.payload)
            for field in model.traced_fields().values():
                field.state = "accepted"
            originals = {d.id: client.app.state.store.read(d.sha256) for d in model.documents}
            record.payload = approve(model, "Iria", originals).model_dump_json()
            session.add(record)
            session.commit()
        blob.unlink()
        assert client.get(route).status_code == 404
        assert client.get("/revisions/A/ifc").status_code == 404
        assert client.get("/diff", params={"layers": "true"}).status_code == 404
        blob.write_bytes(b"alterado")
        assert client.get(route).status_code == 409


def test_cache_offline_actualiza_la_revision_documental(tmp_path, monkeypatch):
    monkeypatch.delenv("TRAZIA_OFFLINE", raising=False)
    with TestClient(create_app(data_root=tmp_path, root=ROOT, seed=False)) as client:
        _submit(client, "A")
        originals = _upload_originals(client, "A")
        monkeypatch.setenv("TRAZIA_OFFLINE", "1")
        response = client.post(
            "/jobs",
            json={
                "documents": originals,
                "project_id": "DEMO",
                "equipment_id": "vessel-101",
                "revision": "C",
                "tag": "V-101",
            },
            headers=_headers("offline"),
        )
        assert response.status_code == 202, response.text
        path = f"/jobs/{response.json()['job_id']}"
        assert '"status": "done"' in client.get(f"{path}/events").text
        job = client.get(path).json()
        assert job["cache_hit"]
        restored = client.get(f"/revisions/{job['revision_id']}").json()
        assert restored["revision"] == "C"
        assert {doc["revision"] for doc in restored["documents"]} == {"C"}


def test_trabajo_incompleto_exhibe_candidatos_citados(tmp_path, monkeypatch):
    monkeypatch.delenv("TRAZIA_OFFLINE", raising=False)
    pdf = BytesIO()
    page = Canvas(pdf)
    page.drawString(36, 750, "DESIGN SPECIFICATION")
    page.drawString(36, 725, "1 Design Pressure: 9 bar")
    page.save()
    with TestClient(create_app(data_root=tmp_path, root=ROOT, seed=False)) as client:
        uploaded = client.post(
            "/documents",
            files={"file": ("HDM_V-123.pdf", pdf.getvalue())},
            data={"document_id": "HDM", "revision": "1"},
            headers=_headers("partial-original"),
        )
        assert uploaded.status_code == 201
        job = client.post(
            "/jobs",
            json={
                "documents": [uploaded.json()["id"]],
                "tag": "V-123",
                "revision": "1",
                "dataset": "real",
            },
            headers=_headers("partial"),
        )
        assert job.status_code == 202, job.text
        path = f"/jobs/{job.json()['job_id']}"
        # Con datos obligatorios ausentes el trabajo ya no se corta: termina en un DRAFT con
        # valores preliminares marcados, y lo leído conserva su cita.
        assert '"status": "error"' not in client.get(f"{path}/events").text
        summary = client.get(path).json()
        assert summary["status"] == "done" and summary["revision_id"]
        assert any(w.startswith("Valores preliminares") for w in summary["warnings"])
        revision = client.get(f"/revisions/{summary['revision_id']}").json()
        equipment = revision["equipment"]
        assert equipment["diameter"]["state"] == "assumed"
        assert equipment["diameter"]["source"]["rule"].startswith("preliminar.")
        pressure = equipment["attributes"]["design_pressure"]
        assert pressure["value"] == 9 and pressure["source"]["document_id"] == "HDM"
        assert pressure["source"]["page"] == 1 and pressure["source"]["bbox"]


def test_migra_almacen_sqlite_de_ib2_sin_perder_documentos(tmp_path):
    url = f"sqlite:///{(tmp_path / 'trazia.sqlite3').as_posix()}"
    engine = sqlmodel.create_engine(url)
    legacy = (
        AuditRecord,
        DocumentRecord,
        EventRecord,
        IdempotencyRecord,
        JobCacheRecord,
        JobRecord,
        RevisionRecord,
    )
    sqlmodel.SQLModel.metadata.create_all(engine, tables=[model.__table__ for model in legacy])
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE events DROP COLUMN duration_seconds")
    original = b"documento de prueba"
    with sqlmodel.Session(engine) as session:
        session.add(
            DocumentRecord(
                id="previo",
                document_id="GA",
                filename="GAD_DEMO.pdf",
                revision="A",
                sha256="0" * 64,
                size=len(original),
            )
        )
        session.commit()
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE documents DROP COLUMN kind")
        conn.exec_driver_sql("ALTER TABLE documents DROP COLUMN equipment_tag")
    engine.dispose()
    for _ in range(2):
        with TestClient(create_app(data_root=tmp_path, root=ROOT, seed=False)) as client:
            assert client.get("/health").status_code == 200
            with sqlmodel.Session(client.app.state.store.engine) as session:
                documento = session.get(DocumentRecord, "previo")
                assert documento.size == len(original)
                assert documento.kind is None and documento.equipment_tag is None
                query = sqlmodel.text("SELECT version_num FROM alembic_version")
                assert session.exec(query).one()[0] == "0012"

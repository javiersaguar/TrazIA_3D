"""Un plano al que le faltan datos obligatorios llega a modelo DRAFT con valores preliminares."""

from pathlib import Path

import pytest

from trazia.families.preliminares import AVISO, es_preliminar
from trazia.ifc import build_ifc, validate_ifc
from trazia.model import fields
from trazia.pipeline import InputDocument, process
from trazia.review import approve

DOCS = Path(__file__).resolve().parents[1] / "examples" / "documents"


def documentos(nombre="GAD_V-101_revA.pdf"):
    data = (DOCS / "GAD_V-101_revA.pdf").read_bytes()
    return [InputDocument(nombre, data, "GA-V101")], {"GA-V101": data}


def procesar(nombre="GAD_V-101_revA.pdf", **options):
    docs, originales = documentos(nombre)
    result = process(
        docs,
        project_id="P",
        equipment_id="v-101",
        revision="A",
        reader=lambda *_args, **_options: [],
        **options,
    )
    return result, originales


def test_sin_preliminares_se_sigue_cortando():
    result, _ = procesar()
    assert result.revision is None and result.missing_data


def test_plano_sin_diametro_ni_altura_da_un_draft_con_preliminares():
    result, originales = procesar(preliminary=True)
    assert result.error is None, result.error
    revision = result.revision
    assert revision.approval is None
    equipo = revision.equipment
    assert (equipo.kind, equipo.effective_support) == ("vertical_vessel", "skirt")
    for path in ("diameter", "height", "head_depth", "skirt_height"):
        campo = getattr(equipo, path)
        assert campo.state == "assumed" and es_preliminar(campo)
        assert campo.source.rule.startswith("preliminar.")
        assert campo.source.confidence <= 0.1 and campo.source.grounded is False
        assert "Falta en el plano" in campo.explanation
    # Proporciones habituales: L/D = 3 y fondo 2:1 a partir del diámetro preliminar.
    assert equipo.height.value == 3 * equipo.diameter.value
    assert equipo.head_depth.value == equipo.diameter.value / 4
    [aviso] = [w for w in result.warnings if w.startswith(AVISO)]
    assert "diameter" in aviso and "skirt_height" in aviso
    # El tag sí sale del nombre del archivo: no es preliminar.
    assert not es_preliminar(equipo.tag)
    assert not validate_ifc(build_ifc(revision))
    with pytest.raises(ValueError, match="valores preliminares"):
        approve(revision, "Revisora", originales)


def test_la_correccion_humana_desbloquea_la_aprobacion():
    result, originales = procesar(preliminary=True)
    revision = result.revision
    for campo in fields(revision.equipment).values():
        if campo.state == "assumed":
            campo.state = "corrected"
    assert not [p for p, f in fields(revision.equipment).items() if es_preliminar(f)]
    # Sin boquillas leídas, la aprobación sigue pidiendo otras cosas, pero ya no los preliminares.
    with pytest.raises(ValueError) as error:
        approve(revision, "Revisora", originales)
    assert "preliminares" not in str(error.value)


def test_aceptar_sin_corregir_no_vale():
    result, originales = procesar(preliminary=True)
    revision = result.revision
    for campo in fields(revision.equipment).values():
        campo.state = "accepted"
    with pytest.raises(ValueError, match="valores preliminares"):
        approve(revision, "Revisora", originales)


def test_una_bomba_sin_datos_sale_como_envolvente_preliminar():
    result, _ = procesar("BOMBA-GA1-Rev0.pdf", preliminary=True)
    assert result.error is None, result.error
    equipo = result.revision.equipment
    assert (equipo.kind, equipo.lod) == ("pump", 1)
    tipo = equipo.attributes["equipment_type"]
    assert tipo.value == "pump" and es_preliminar(tipo)
    assert equipo.envelope.size.x.value > 0 and es_preliminar(equipo.envelope.size.x)
    assert not validate_ifc(build_ifc(result.revision))


def test_la_api_termina_el_trabajo_y_no_deja_aceptar_un_preliminar(tmp_path, monkeypatch):
    import time
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from sqlmodel import Session, select

    from trazia import lectura
    from trazia.api import create_app, jobs
    from trazia.store import DocumentRecord

    monkeypatch.setenv("TRAZIA_OFFLINE", "0")
    monkeypatch.setattr(lectura, "leer", lambda *_args, **_options: [])
    root = Path(__file__).resolve().parents[1]
    with TestClient(create_app(root=root, data_root=tmp_path)) as client:
        with Session(client.app.state.store.engine) as session:
            docs = session.exec(select(DocumentRecord).where(DocumentRecord.revision == "A"))
            ids = [d.id for d in docs if d.filename.lower().endswith(".pdf")]
        response = client.post(
            "/equipment/V-101/jobs",
            json={"documents": ids, "revision": "PRELIMINAR"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 202, response.text
        identity, until = response.json()["job_id"], time.monotonic() + 30
        while (job := client.get(f"/jobs/{identity}").json())["status"] not in jobs.TERMINAL:
            assert time.monotonic() < until, "El trabajo no termina"
            time.sleep(0.01)
        assert job["status"] == "done", job
        assert any(w.startswith(AVISO) for w in job["warnings"])
        revision_id = job["revision_id"]
        revision = client.get(f"/revisions/{revision_id}")
        assert revision.json()["equipment"]["diameter"]["state"] == "assumed"
        ifc = client.get(f"/revisions/{revision_id}/ifc", params={"draft": True})
        assert ifc.status_code == 200 and ifc.content.startswith(b"ISO-10303-21")
        issues = client.get(f"/revisions/{revision_id}/validation").json()["issues"]
        codes = {i["code"] for i in issues}
        assert "preliminary" in codes
        accept = client.patch(
            f"/revisions/{revision_id}/fields/diameter",
            json={"state": "accepted", "actor": "Revisora"},
            headers={"Idempotency-Key": str(uuid4()), "If-Match": revision.headers["etag"]},
        )
        assert accept.status_code == 422 and "preliminar" in accept.json()["detail"]

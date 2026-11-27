"""Roles de la web (admin, usuario, invitado), perfil y carga de un lote, con datos sintéticos."""

import json
import secrets
import shutil
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session

from trazia.api.accounts import ADMINS, sync_local_owner_password
from trazia.api.app import create_app
from trazia.store import AuditRecord, EventRecord, JobRecord

ROOT = Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@pytest.fixture()
def settings(monkeypatch, tmp_path):
    secret = secrets.token_hex(12)
    monkeypatch.setenv("TRAZIA_AUTH", "1")
    monkeypatch.setenv("TRAZIA_AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("TRAZIA_ADMIN_PASSWORD", secret)
    monkeypatch.setenv("TRAZIA_USUARIOS", "revisor")
    monkeypatch.setenv("TRAZIA_CORS_ORIGINS", "http://localhost:3120")
    return tmp_path, secret


@pytest.fixture()
def fotos_equipo(monkeypatch, tmp_path):
    carpeta = tmp_path / "fotos-de-prueba"
    carpeta.mkdir()
    foto = Image.new("RGB", (1, 1), "blue")
    for username in ADMINS:
        foto.save(carpeta / f"{username}.jpg")
    monkeypatch.setattr("trazia.api.accounts.TEAM_PHOTOS", carpeta)


def _login(client, user, secret):
    return client.post("/auth/login", json={"username": user, "password": secret})


def test_usuario_entra_pero_no_llega_a_admin_y_el_invitado_no_ve_revisiones(settings):
    tmp, secret = settings
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        sesion = _login(client, "revisor", secret).json()
        assert sesion["role"] == "usuario" and sesion["name"] == "Revisor de TR"
        assert client.get("/equipment").status_code == 200
        assert client.get("/admin/metricas").status_code == 403
        client.post("/auth/logout")
        assert _login(client, "javier.saguar", secret).json()["name"] == "Javier Saguar"
        assert client.get("/admin/metricas").status_code != 403
        client.post("/auth/logout")
        assert client.post("/auth/guest").json()["role"] == "guest"
        assert client.get("/equipment").status_code == 403


def test_foto_de_perfil(settings):
    tmp, secret = settings
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        _login(client, "revisor", secret)
        assert (
            client.put("/auth/avatar", files={"file": ("a.txt", b"x", "text/plain")}).status_code
            == 415
        )
        perfil = client.put("/auth/avatar", files={"file": ("a.png", PNG, "image/png")}).json()
        assert perfil["avatar"].startswith("/auth/avatar/revisor")
        assert client.get("/auth/avatar/revisor").content == PNG
        assert client.get("/auth/session").json()["avatar"] == perfil["avatar"]


@pytest.mark.parametrize("acceso", ["miguel.vera", "revisor", "invitado"])
@pytest.mark.usefixtures("fotos_equipo")
def test_cada_sesion_ve_las_fotos_del_equipo(settings, acceso):
    tmp, secret = settings
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        perfil = (
            client.post("/auth/guest") if acceso == "invitado" else _login(client, acceso, secret)
        ).json()
        fotos = {p["username"]: p["avatar"] for p in perfil["profiles"]}
        assert set(ADMINS) <= set(fotos)
        for username in ADMINS:
            assert fotos[username].startswith(f"/auth/avatar/{username}?v=")
            foto = client.get(fotos[username])
            assert foto.status_code == 200
            assert foto.headers["content-type"] == "image/jpeg"
        if acceso == "miguel.vera":
            assert perfil["avatar"] == fotos["miguel.vera"]


@pytest.mark.usefixtures("fotos_equipo")
def test_la_foto_subida_sustituye_a_la_del_equipo(settings):
    tmp, secret = settings
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        _login(client, "javier.saguar", secret)
        assert client.get("/auth/avatar/javier.saguar").content != PNG
        client.put("/auth/avatar", files={"file": ("perfil.png", PNG, "image/png")})
        assert client.get("/auth/avatar/javier.saguar").content == PNG
        assert client.get("/auth/avatar/nadie").status_code == 404


@pytest.mark.parametrize("username", ADMINS)
def test_el_equipo_puede_probar_ambos_roles_en_una_sola_sesion(settings, username):
    tmp, secret = settings
    app = create_app(data_root=tmp / "data", seed=False)
    with TestClient(app) as client, closing(TestClient(app)) as independent:
        profile = _login(client, username, secret).json()
        assert profile["can_switch_role"] is True
        assert {member["username"] for member in profile["team"]} == set(ADMINS)
        assert _login(independent, username, secret).json()["role"] == "admin"
        path = "/auth/session/role"

        assert client.put(path, json={"role": "usuario"}).status_code == 204
        assert client.get("/auth/session").json()["role"] == "usuario"
        assert client.get("/auth/session").json()["can_switch_role"] is True
        assert client.get("/admin/metricas").status_code == 403
        assert client.get("/equipment").status_code == 200
        assert independent.get("/admin/metricas").status_code == 200

        assert client.put(path, json={"role": "admin"}).status_code == 204
        assert client.get("/auth/session").json()["role"] == "admin"
        assert client.get("/admin/metricas").status_code == 200
        assert client.put(path, json={"role": "guest"}).status_code == 422
        assert (
            client.put(
                path, json={"role": "usuario"}, headers={"Origin": "https://ejemplo.invalid"}
            ).status_code
            == 403
        )


@pytest.mark.parametrize("username", ["revisor", "invitado"])
def test_el_resto_de_cuentas_no_puede_cambiar_el_rol(settings, username):
    tmp, secret = settings
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        path = "/auth/session/role"
        assert client.put(path, json={"role": "admin"}).status_code == 401
        login = (
            client.post("/auth/guest")
            if username == "invitado"
            else _login(client, username, secret)
        )
        assert login.json()["can_switch_role"] is False
        assert login.json()["team"] == []
        assert client.put(path, json={"role": "admin"}).status_code == 403
        assert client.get("/auth/session").json()["role"] == login.json()["role"]


@pytest.mark.usefixtures("fotos_equipo")
def test_el_cambio_de_cuenta_pide_su_password_y_conserva_la_foto(settings):
    tmp, secret = settings
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        _login(client, "iria.lozano", secret)
        uploaded = client.put("/auth/avatar", files={"file": ("perfil.png", PNG, "image/png")})
        assert uploaded.json()["avatar"].startswith("/auth/avatar/iria.lozano")
        previous = client.cookies.get("trazia_session")
        assert _login(client, "miguel.vera", "incorrecta").status_code == 401
        assert client.get("/auth/session").json()["username"] == "iria.lozano"

        miguel = _login(client, "miguel.vera", secret).json()
        assert miguel["username"] == "miguel.vera"
        # Sin foto subida, Miguel tiene la del equipo que viene con la plataforma.
        assert miguel["avatar"].startswith("/auth/avatar/miguel.vera")
        avatar = next(p["avatar"] for p in miguel["team"] if p["username"] == "iria.lozano")
        assert avatar == uploaded.json()["avatar"]
        assert client.get(avatar).content == PNG
        assert client.cookies.get("trazia_session") != previous
        with closing(TestClient(client.app)) as old_session:
            old_session.cookies.set("trazia_session", previous)
            assert old_session.get("/auth/session").status_code == 401


def test_reparar_acceso_local_solo_actualiza_a_javier_si_cambia_el_archivo(settings, monkeypatch):
    tmp, secret = settings
    app = create_app(data_root=tmp / "data", seed=False)
    with TestClient(app) as client, closing(TestClient(app)) as independent:
        assert _login(client, "javier.saguar", secret).status_code == 200
        assert _login(independent, "iria.lozano", secret).status_code == 200
        updated = secrets.token_hex(12)
        path = tmp / "acceso-local.txt"
        path.write_text(updated + "\n", encoding="utf-8")
        monkeypatch.setenv("TRAZIA_ADMIN_PASSWORD_FILE", str(path))

        assert sync_local_owner_password(app.state.store) is True
        assert client.get("/auth/session").status_code == 401
        assert independent.get("/auth/session").status_code == 200
        assert _login(client, "javier.saguar", secret).status_code == 401
        assert _login(client, "javier.saguar", updated).status_code == 200
        assert sync_local_owner_password(app.state.store) is False
        assert client.get("/auth/session").status_code == 200


def test_carga_las_revisiones_del_lote_con_sus_originales(monkeypatch, tmp_path):
    lote = tmp_path / "lote"
    for sufijo, rev in (("a", "rev1"), ("b", "rev2")):
        carpeta = lote / "V-101" / rev
        carpeta.mkdir(parents=True)
        shutil.copy(ROOT / "examples" / f"vessel_rev_{sufijo}.json", carpeta / "revision.json")
    monkeypatch.setenv("TRAZIA_LOTE", str(lote))
    monkeypatch.setenv("TRAZIA_DATASET_DIR", str(ROOT / "examples" / "documents"))
    with TestClient(create_app(root=tmp_path, data_root=tmp_path / "data")) as client:
        filas = client.get("/equipment").json()
        assert {fila["tag"] for fila in filas} == {"V-101"}
        versiones = filas[0]["revision_meta"]
        assert set(versiones) == {"A", "B"}
        for etiqueta, version in versiones.items():
            assert version["identity"].endswith(f":{etiqueta}")
            assert client.get(version["ifcUrl"]).content.startswith(b"ISO-10303-21;")
            planos = [doc for doc in version["documents"] if doc["filename"].endswith(".pdf")]
            assert [doc["filename"] for doc in planos] == [f"GAD_V-101_rev{etiqueta}.pdf"]
    # Sin el original, la carga se niega en lugar de servir una revisión sin evidencia.
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    monkeypatch.setenv("TRAZIA_DATASET_DIR", str(vacio))
    with pytest.raises(ValueError, match="Falta el original"):
        with TestClient(create_app(root=tmp_path, data_root=tmp_path / "otro")):
            pass
    assert json.loads((lote / "V-101" / "rev1" / "revision.json").read_text(encoding="utf-8"))


def test_metricas_y_exportaciones_del_administrador(settings, monkeypatch):
    tmp, secret = settings
    monkeypatch.setenv("TRAZIA_REGISTRO_LLM", str(tmp / "llm.jsonl"))
    monkeypatch.setenv("TRAZIA_REGISTRO_ENVIOS", str(tmp / "envios.jsonl"))
    with TestClient(create_app(root=ROOT, data_root=tmp / "data")) as client:
        _login(client, "javier.saguar", secret)
        datos = client.get("/admin/metricas").json()
        assert datos["revisiones"]["total"] == 2 and len(datos["trabajos"]["por_hora"]) == 24
        ids = [fila["revision_id"] for fila in client.get("/equipment").json()]
        now = time.time()
        with Session(client.app.state.store.engine) as session:
            for i in range(6):
                session.add(
                    JobRecord(
                        id=f"trabajo-{i}",
                        tag="V-101",
                        status="done" if i else "running",
                        created_at=now - (6 - i) * 3600,
                        updated_at=now - i * 60,
                        request_json=json.dumps({"actor": "javier.saguar"} if i else {}),
                    )
                )
            session.add(
                AuditRecord(
                    revision_id=ids[0],
                    path="equipment.tag",
                    actor="javier.saguar",
                    before_json='{"value":"V-100"}',
                    after_json='{"value":"V-101"}',
                )
            )
            session.commit()
        recientes = client.get("/admin/metricas?rango=1h").json()
        assert recientes["trabajos"]["activos"] == recientes["trabajos"]["en_ejecucion"] == 1
        assert recientes["trabajos"]["en_cola"] == 0
        assert sum(recientes["trabajos"]["finalizados_por_hora"]) == 5
        assert [job["id"] for job in recientes["trabajos"]["recientes"]] == [
            f"trabajo-{i}" for i in reversed(range(1, 6))
        ]
        assert recientes["trabajos"]["recientes"][0]["autor"] == "javier.saguar"
        assert recientes["revisiones"]["recientes"][0]["id"] == ids[0]
        assert recientes["revisiones"]["recientes"][0]["autor"] == "javier.saguar"
        assert recientes["revisiones"]["recientes"][0]["accion"] == "actualizada"
        assert (
            client.post(
                "/admin/exportaciones", json={"formato": "BCF", "revision_id": ids[0]}
            ).status_code
            == 422
        )
        fila = client.post(
            "/admin/exportaciones", json={"formato": "IFC", "revision_id": ids[0]}
        ).json()
        assert fila["estado"] == "Borrador" and len(fila["huella"]) == 12
        historial = client.get("/admin/exportaciones").json()
        assert historial[0]["formato"] == "IFC" and historial[0]["vigente"] is True
        resumen = client.get(f"/admin/revisiones/{ids[0]}/resumen").json()
        assert resumen["huella"] == fila["huella"] and resumen["aprobacion"] is None
        assert resumen["exportaciones"] == 1 and resumen["ultima_exportacion"]["vigente"]
        assert resumen["campos"] >= resumen["pendientes"] > 0
        assert sum(resumen["por_estado"].values()) == resumen["campos"]
        assert set(recientes["anterior"]) == {
            "trabajos",
            "finalizados",
            "errores",
            "p50_s",
            "llamadas",
        }
        archivo = f"/admin/exportaciones/{fila['archivo']}/archivo"
        original = client.get(archivo)
        assert original.status_code == 200 and original.content.startswith(b"ISO-10303-21;")
        assert client.get(archivo).content == original.content
        assert client.get(f"/admin/exportaciones/{'0' * 64}/archivo").status_code == 404
        assert client.get("/lote/resumen").json() == []
        client.post("/auth/logout")
        _login(client, "revisor", secret)
        assert client.get(archivo).status_code == 403


def test_metricas_filtran_el_periodo_y_conservan_costes_desconocidos(settings, monkeypatch):
    tmp, secret = settings
    registro = tmp / "llm.jsonl"
    monkeypatch.setenv("TRAZIA_REGISTRO_LLM", str(registro))
    monkeypatch.setenv("TRAZIA_REGISTRO_ENVIOS", str(tmp / "envios.jsonl"))
    ahora = time.time()
    filas = [
        {
            "at": datetime.fromtimestamp(ahora - edad, timezone.utc).isoformat(),
            "estado": "ok",
            "proveedor": "prueba",
            "tokens_in": 12,
            "tokens_out": 8,
            "coste_eur": coste,
            "coste_conocido": coste is not None,
        }
        for edad, coste in [(30, None), (7200, 0.05), (9 * 86400, 3.0)]
    ]
    registro.write_text("\n".join(json.dumps(fila) for fila in filas), encoding="utf-8")
    app = create_app(data_root=tmp / "data", seed=False)
    with TestClient(app) as client:
        _login(client, "javier.saguar", secret)
        with Session(app.state.store.engine) as session:
            session.add(
                JobRecord(
                    id="error-sintetico",
                    tag="V-001",
                    status="error",
                    request_json="{}",
                    elapsed_seconds=4,
                    error="Error de prueba",
                )
            )
            session.flush()
            session.add(
                EventRecord(
                    job_id="error-sintetico",
                    stage="ifc",
                    status="ok",
                    file="",
                    detail="",
                    duration_seconds=1.5,
                )
            )
            session.commit()
        hora = client.get("/admin/metricas?rango=1h").json()
        assert len(hora["intervalos"]) == 12
        assert hora["duraciones"]["ifc"] == [0, 1, 0, 0, 0]
        assert hora["errores"][0]["id"] == "error-sintetico"
        proveedor = hora["modelos"]["por_proveedor"]["prueba"]
        assert proveedor["llamadas"] == 1 and proveedor["tokens_serie"][-1] == 20
        assert proveedor["coste_eur"] is None and proveedor["coste_serie"][-1] is None
        semana = client.get("/admin/metricas?rango=7d").json()
        assert len(semana["intervalos"]) == 7 and semana["modelos"]["llamadas"] == 2
        assert client.get("/admin/metricas?rango=12h").status_code == 422


def test_campos_csv_e_informe_pdf_solo_para_administradores(settings):
    tmp, secret = settings
    with TestClient(create_app(root=ROOT, data_root=tmp / "data")) as client:
        _login(client, "javier.saguar", secret)
        revision = client.get("/equipment").json()[0]["revision_id"]
        ruta = f"/admin/revisiones/{revision}"
        tabla = client.get(f"{ruta}/campos.csv")
        assert tabla.status_code == 200 and "DRAFT" in tabla.headers["content-disposition"]
        cabecera = tabla.text.lstrip("\ufeff").splitlines()[0]
        assert cabecera == "campo,valor,unidad,documento,pagina,confianza,estado"
        informe = client.get(f"{ruta}/informe.pdf")
        assert informe.status_code == 200 and informe.content.startswith(b"%PDF")
        client.post("/auth/logout")
        _login(client, "revisor", secret)
        assert client.get(f"{ruta}/campos.csv").status_code == 403


def test_reintento_de_lote_reutiliza_originales_y_la_clave_idempotente(settings, monkeypatch):
    tmp, secret = settings
    app = create_app(data_root=tmp / "data", seed=False)
    with TestClient(app) as client:

        async def conservar_en_cola(identity):
            assert identity

        monkeypatch.setattr(app.state.queue, "enqueue", conservar_en_cola)
        _login(client, "javier.saguar", secret)
        pdf = ROOT / "examples" / "documents" / "GAD_V-101_revA.pdf"
        document = client.post(
            "/documents",
            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
            data={"revision": "A"},
            headers={"Idempotency-Key": "original-sintetico"},
        )
        assert document.status_code == 201
        data = {
            "tag": "V-101",
            "revision": "A",
            "project_id": "ENSAYO",
            "equipment_id": "v101",
            "strategy": "b_reglas",
            "dataset": "synthetic",
            "documents": [document.json()["id"]],
        }
        first = client.post("/jobs", json=data, headers={"Idempotency-Key": "primera-ejecucion"})
        assert first.status_code == 202
        with Session(app.state.store.engine) as session:
            record = session.get(JobRecord, first.json()["job_id"])
            record.status = "error"
            record.error = "Interrupción de prueba"
            session.add(record)
            session.commit()
        assert client.get("/admin/lote").json()[0]["estado"] == "error"
        retry = {"proyecto": "ENSAYO", "tag": "V-101", "revision": "A"}
        headers = {"Idempotency-Key": "reintentar"}
        second = client.post("/admin/lote/reintentar", json=retry, headers=headers)
        assert second.status_code == 202
        assert second.json()["job_id"] != first.json()["job_id"]
        assert (
            client.post("/admin/lote/reintentar", json=retry, headers=headers).json()
            == second.json()
        )
        lote = client.get("/admin/lote").json()
        assert len(lote) == 1 and lote[0]["estado"] == "queued"
        # Lo que sigue en cola no se reintenta, aunque cambie la clave idempotente.
        en_cola = client.post(
            "/admin/lote/reintentar", json=retry, headers={"Idempotency-Key": "otra"}
        )
        assert en_cola.status_code == 409
        with Session(app.state.store.engine) as session:
            record = session.get(JobRecord, second.json()["job_id"])
            assert json.loads(record.request_json)["documents"] == data["documents"]


def test_el_modelo_preferido_reordena_sin_saltar_la_politica(settings, monkeypatch):
    from trazia.copilot import cloud

    tmp, secret = settings
    monkeypatch.setenv("GROQ_API_KEY", "prueba")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://ejemplo.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "prueba")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-01-01")
    monkeypatch.setattr(cloud.policy, "check_external", lambda name, dataset: None)
    monkeypatch.setattr(cloud, "offline", lambda: False)
    with TestClient(create_app(root=ROOT, data_root=tmp / "data")) as client:
        _login(client, "revisor", secret)
        datos = client.get("/ajustes/modelos").json()
        assert datos["actual"] == "auto" and [o["id"] for o in datos["opciones"]] == list(
            cloud.PREFERENCIAS
        )
        client.cookies.set("trazia_modelo", "azure")
        assert client.get("/ajustes/modelos").json()["actual"] == "azure"
    for preferencia, esperado in (
        ("auto", cloud.PROVIDER),
        ("azure", "azure-openai:gpt-6-luna"),
        ("ninguno", None),
    ):
        token = cloud.PREFERENCIA.set(preferencia)
        try:
            assert cloud.provider("synthetic") == esperado
            if preferencia != "ninguno":
                assert cloud.provider("real") == "azure-openai:gpt-6-luna"
        finally:
            cloud.PREFERENCIA.reset(token)


def test_documentos_abre_cualquier_original_citado_en_el_lote(settings, monkeypatch):
    tmp, secret = settings
    lote, dataset = tmp / "lote", tmp / "dataset" / "D-9"
    lote.mkdir()
    dataset.mkdir(parents=True)
    # Equipo inventado sin modelo: sus originales también deben poder abrirse.
    resumen = [{"tag": "D-9", "revision": "1", "documentos": ["GAD_D-9_rev1.pdf"]}]
    (lote / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
    (dataset / "GAD_D-9_rev1.pdf").write_bytes(b"%PDF-1.4 sintetico")
    (dataset / "OTRO.pdf").write_bytes(b"%PDF-1.4 fuera del lote")
    monkeypatch.setenv("TRAZIA_LOTE", str(lote))
    monkeypatch.setenv("TRAZIA_DATASET_DIR", str(tmp / "dataset"))
    with TestClient(create_app(data_root=tmp / "data", seed=False)) as client:
        _login(client, "revisor", secret)
        pdf = client.get("/lote/documentos/GAD_D-9_rev1.pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
        assert client.get("/lote/documentos/OTRO.pdf").status_code == 404
        assert client.get("/lote/documentos/..%2Fsecreto.pdf").status_code == 404

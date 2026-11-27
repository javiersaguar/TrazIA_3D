"""Contratos de clasificación para originales con nombres ajenos al dataset."""

import io
import json

from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlmodel import Session

from trazia.api.app import create_app
from trazia.ingest import ingest_bytes
from trazia.lectura.clasificar import classify
from trazia.lote import agrupar, procesar_carpeta
from trazia.pipeline import InputDocument, process
from trazia.store import DocumentRecord


def pdf(*rows, paper=(841, 595)):
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=paper, invariant=1)
    for i, row in enumerate(rows):
        if isinstance(row, str):
            row = (row,)
        for column, cell in enumerate(row):
            canvas.drawString(45 + 165 * column, paper[1] - 45 - 22 * i, cell)
    # Una página técnica también puede venir sin capa de texto.
    canvas.rect(70, 110, 210, 190)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_ga_por_cabecera_y_tag_citado():
    content = pdf(("MARK", "SIZE", "RATING"), ("N1", '2"', "150#"), "TAG: VX-207")
    eventos = []
    output = process(
        [InputDocument("plano del jurado.pdf", content, "DOC-PLANO")],
        project_id="PRUEBA",
        equipment_id="vx-207",
        revision="B",
        dataset="real",
        reader=lambda bundles, **_: [],
        on_event=eventos.append,
    )
    assert any(
        "Clasificado como GA" in e.detail
        and "tabla de boquillas" in e.detail
        and "pág. 1" in e.detail
        for e in eventos
    )
    tag = next(c for c in output.candidates if c.path == "tag")
    assert tag.value == "VX-207" and tag.source.bbox and tag.source.page == 1
    assert tag.source.locator == "Cajetín de equipo: TAG: VX-207"


def test_indicaciones_manuales_tienen_precedencia():
    content = pdf("GENERAL ARRANGEMENT", "TAG: VX-207")
    eventos = []
    output = process(
        [InputDocument("plano.pdf", content, "DOC-P", kind="HDM", equipment_tag="VX-300")],
        project_id="PRUEBA",
        equipment_id="vx-300",
        revision="B",
        reader=lambda bundles, **_: [],
        on_event=eventos.append,
    )
    assert any("HDM" in e.detail and "indicación manual" in e.detail for e in eventos)
    tag = next(c for c in output.candidates if c.path == "tag")
    assert tag.value == "VX-300" and tag.source.locator == "Tag indicado manualmente"


def test_distintos_tipos_por_el_contenido():
    for heading, expected in (
        ("MECHANICAL DATA SHEET", "HDM"),
        ("NOZZLES & PLATFORMS ORIENTATION", "VESOR"),
        ("NOZZLE SCHEDULE", "GA"),
    ):
        parsed = ingest_bytes(pdf(heading), "archivo.pdf", "DOC", "1")
        detected = classify(parsed)
        assert detected.kind == expected
        assert detected.kind_source.source.page == 1
    conventional = ingest_bytes(pdf("GENERAL ARRANGEMENT"), "HDM_VX-1.pdf", "DOC", "1")
    assert classify(conventional).kind == "HDM"


def test_revisiones_y_avisos_de_archivos_ignorados(tmp_path):
    equipo = tmp_path / "entrada" / "KV-501"
    equipo.mkdir(parents=True)
    (equipo / "001.pdf").write_bytes(pdf("GENERAL ARRANGEMENT", "REV. 2"))
    (equipo / "002.pdf").write_bytes(pdf("GENERAL ARRANGEMENT", "Vista lateral"))
    (equipo / "003.pdf").write_bytes(pdf("MECHANICAL DATA SHEET"))
    (equipo / "004.pdf").write_bytes(pdf())
    (equipo / "005.pdf").write_bytes(b"documento roto")
    ignored = []
    revs = agrupar(equipo.parent, ignored)["KV-501"]
    assert set(revs) == {"2", "3"}
    for docs in revs.values():
        assert [doc.kind for doc in docs] == ["GA", "HDM"]
    assert "cajetín" in " ".join(revs["2"][0].alertas)
    assert "por orden" in " ".join(revs["3"][0].alertas)
    assert [item["archivo"] for item in ignored] == ["KV-501/004.pdf", "KV-501/005.pdf"]
    assert "plano sin texto: necesita OCR" in ignored[0]["motivo"]


def test_tipologia_fuera_de_alcance_en_resumen(tmp_path):
    entrada = tmp_path / "entrada" / "P-201"
    entrada.mkdir(parents=True)
    (entrada / "alzados.pdf").write_bytes(
        pdf("GENERAL ARRANGEMENT", "AXIAL FAN", "TAG: P-201", "REV 1")
    )
    salida = tmp_path / "salida"
    (fila,) = procesar_carpeta(entrada.parent, salida, dataset="synthetic")
    assert fila.estado == "tipologia_no_soportada"
    assert fila.error == "tipología no soportada: ventilador"
    assert fila.error in fila.avisos_documentos


def test_lote_utiliza_la_carpeta_si_el_ga_no_lleva_tag(tmp_path):
    entrada = tmp_path / "entrada" / "VA-910"
    entrada.mkdir(parents=True)
    (entrada / "plano.pdf").write_bytes(pdf("GENERAL ARRANGEMENT", "REV. A"))
    salida = tmp_path / "salida"
    (fila,) = procesar_carpeta(entrada.parent, salida)
    found = json.loads((salida / "VA-910/revA/candidatos.json").read_text("utf-8"))
    tag = next(item for item in found if item["path"] == "tag")
    assert tag["value"] == "VA-910" and "carpeta" in tag["source"]["locator"]
    assert "tag" not in fila.error


def test_plano_sin_texto_en_eventos_y_resumen(tmp_path):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "GAD_V-777_rev1.pdf").write_bytes(pdf())
    salida = tmp_path / "salida"
    (fila,) = procesar_carpeta(entrada, salida)
    events = json.loads((salida / "V-777/rev1/eventos.json").read_text("utf-8"))
    summary = json.loads((salida / "resumen.json").read_text("utf-8"))
    assert any("plano sin texto: necesita OCR" in m for m in fila.avisos_documentos)
    assert any("plano sin texto: necesita OCR" in m for m in summary[0]["avisos_documentos"])
    assert any(
        e["stage"] == "extract.ocr" and "plano sin texto" in e["detail"] for e in events["eventos"]
    )


def test_api_guarda_tipo_y_tag_y_rechaza_identificadores_invalidos(tmp_path):
    app = create_app(data_root=tmp_path, seed=False)
    content = pdf("TÍTULO DEL PLANO")
    with TestClient(app) as client:
        response = client.post(
            "/documents",
            files={"file": ("documento.pdf", content, "application/pdf")},
            data={"kind": "VESOR", "equipment_tag": "va-203"},
            headers={"Idempotency-Key": "prueba-metadatos"},
        )
        assert response.status_code == 201
        identity = response.json()["id"]
        with Session(app.state.store.engine) as session:
            row = session.get(DocumentRecord, identity)
            assert (row.kind, row.equipment_tag) == ("VESOR", "VA-203")
        invalid = client.post(
            "/documents",
            files={"file": ("documento.pdf", content, "application/pdf")},
            data={"kind": "VESOR", "equipment_tag": "../otra-carpeta"},
            headers={"Idempotency-Key": "prueba-metadatos-invalidos"},
        )
        assert invalid.status_code == 422


def test_un_a0_con_cien_palabras_no_es_un_plano_sin_texto():
    a0 = (3370, 2384)
    filas = [f"TP{100 + i} SEAL GAS VENT HEADER 3/4 300# RF" for i in range(20)]  # unas 620 letras
    bundle = ingest_bytes(pdf(*filas, paper=a0), "plano.pdf", "GA-X", "1")
    assert bundle.sparse_pages == []
    assert ingest_bytes(pdf("SOLO UN ROTULO", paper=a0), "r.pdf", "GA-Y", "1").sparse_pages == [1]


def test_un_error_del_ensamblado_no_se_tapa_con_la_tipologia():
    from trazia.extraction import Candidate
    from trazia.model import Source

    def leido(path, value, unit="mm", **extra):
        source = Source(document_id="GA-C", page=1, locator=path, confidence=0.9)
        return Candidate(path=path, value=value, unit=unit, source=source, **extra)

    candidatos = [
        leido("tag", "C-1", "1"),
        leido("attributes.equipment_type", "fan", "1"),
        *(leido(f"envelope.size.{eje}", 1000.0) for eje in "xyz"),
        # Supuesto sin regla: el contrato lo rechaza al ensamblar.
        *(leido(f"envelope.origin.{eje}", 0.0, state="assumed") for eje in "xyz"),
    ]
    result = process(
        [InputDocument("plano.pdf", pdf("GENERAL ARRANGEMENT"), "GA-C")],
        project_id="P",
        equipment_id="c-1",
        revision="1",
        dataset="real",
        reader=lambda *_a, **_k: list(candidatos),
    )
    assert result.revision is None and result.unsupported_type is None
    assert "source.rule" in result.error
    assert "tipología no soportada: ventilador" in result.warnings

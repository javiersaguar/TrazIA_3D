"""Envolvente mecánica con evidencia sintética y exportación IFC DRAFT."""

import pytest

from trazia.extraction import assemble
from trazia.extractors.mechanical import pump_envelope
from trazia.ifc import build_ifc
from trazia.ingest import Bundle, EvidenceLine
from trazia.model import Document, Source


def line(text, x, y, width=0.1, height=0.01):
    return EvidenceLine(
        text=text,
        source=Source(
            document_id="GA",
            locator="OCR sintético",
            page=1,
            bbox=(x, y, x + width, y + height),
            confidence=0.9,
        ),
    )


def pump_bundle():
    return Bundle(
        document=Document(
            id="GA", filename="GAD_P-1_rev1.pdf", revision="1", sha256="0" * 64, page_count=1
        ),
        media_type="pdf",
        lines=[
            line("CENTRIFUGAL PUMP", 0.6, 0.1),
            line("P-1", 0.7, 0.15),
            line("SIDE ELEVATION", 0.3, 0.3),
            line("PLAN", 0.3, 0.6),
            line("DATUM: BASEPLATE UNDERSIDE", 0.8, 0.75),
            line("1200", 0.25, 0.12),
            line("540", 0.12, 0.15, width=0.01, height=0.09),
            line("620", 0.16, 0.4, width=0.01, height=0.09),
        ],
    )


def test_pump_envelope_with_explicit_dimensions_and_stable_ifc():
    bundle = pump_bundle()
    revision = assemble(
        [bundle],
        pump_envelope(bundle.lines),
        project_id="TEST",
        equipment_id="pump",
        revision="1",
        dataset="synthetic",
    )
    equipment = revision.equipment
    assert (equipment.kind, equipment.lod) == ("pump", 1)
    assert [getattr(equipment.envelope.size, axis).value for axis in "xyz"] == [1200, 620, 540]
    assert equipment.envelope.origin.x.state == "assumed"
    assert equipment.envelope.origin.x.source.rule == "asumido.origen_bancada"
    assert not equipment.nozzles and revision.approval is None
    first = build_ifc(revision, draft=True).by_type("IfcPump")
    second = build_ifc(revision, draft=True).by_type("IfcPump")
    assert first and [part.GlobalId for part in first] == [part.GlobalId for part in second]


def test_missing_pump_dimension_leaves_the_model_pending():
    bundle = pump_bundle()
    bundle.lines = [line for line in bundle.lines if line.text != "620"]
    candidates = pump_envelope(bundle.lines)
    assert candidates == []
    with pytest.raises(ValueError, match="Faltan datos explícitos"):
        assemble([bundle], candidates, project_id="TEST", equipment_id="pump", revision="1")


def _mechanical_pdf(title: str, *, width: bool = True, dense: bool = False) -> bytes:
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    buffer = BytesIO()
    page = Canvas(buffer, pageCompression=1)
    page.drawString(100, 680, title)
    page.drawString(100, 630, "OVERALL LENGTH: 1520 mm")
    if width:
        page.drawString(100, 600, "OVERALL WIDTH: 920 mm")
    page.drawString(100, 570, "OVERALL HEIGHT: 730 mm")
    if dense:
        for i in range(5000):
            page.line(10, i % 300, 65, i % 300)
    page.save()
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("name", "title", "tag", "entity"),
    [
        ("BOMBA-GA1-Rev0.pdf", "CENTRIFUGAL PUMP", "BOMBA-GA1", "IfcPump"),
        (
            "COMPRESOR-GA2-Rev0.pdf",
            "CENTRIFUGAL COMPRESSOR",
            "COMPRESOR-GA2",
            "IfcCompressor",
        ),
    ],
)
def test_mechanical_pipeline_keeps_bounded_text_and_citations(
    name, title, tag, entity, monkeypatch
):
    from trazia import pdf_limits
    from trazia.ifc import validate_ifc
    from trazia.pipeline import InputDocument, process

    # Ese presupuesto es insuficiente para pdfminer; la vía de texto CAD
    # conserva las cotas sin materializar todos los segmentos.
    monkeypatch.setattr(pdf_limits, "MAX_CONTENT_BYTES", 48_000)
    result = process(
        [InputDocument(name, _mechanical_pdf(title, dense=True), "GA")],
        equipment_id=tag.lower(),
        project_id="TEST",
        revision="0",
    )
    assert result.error is None
    revision = result.revision
    assert (revision.equipment.tag.value, revision.equipment.lod) == (tag, 1)
    for axis, expected in zip("xyz", (1520, 920, 730), strict=True):
        dimension = getattr(revision.equipment.envelope.size, axis)
        assert dimension.value == expected
        assert dimension.source.page == 1 and dimension.source.bbox
    assert revision.approval is None
    model = build_ifc(revision, draft=True)
    assert model.by_type(entity)
    assert not validate_ifc(model)


def test_missing_mechanical_cota_does_not_ask_for_vessel_dimensions():
    from trazia.pipeline import InputDocument, process

    result = process(
        [
            InputDocument(
                "BOMBA-GA4-Rev1.pdf", _mechanical_pdf("CENTRIFUGAL PUMP", width=False), "GA"
            )
        ],
        equipment_id="bomba-ga4",
        project_id="TEST",
        revision="1",
    )
    assert result.missing_data and result.revision is None
    assert result.error == "Cotas verificables pendientes (bomba): anchura."

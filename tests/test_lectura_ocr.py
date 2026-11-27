"""OCR y comprobación de cita (tarea 2.2, DEC-06 y DEC-10)."""

from trazia.extraction import Candidate
from trazia.ingest import EvidenceLine
from trazia.model import Source
from trazia.pipeline import _ground
from trazia.reconcile.grounding import is_grounded


def _line(text, bbox=(0.1, 0.1, 0.2, 0.12), page=1):
    source = Source(document_id="GA", page=page, locator="t", bbox=bbox, confidence=0.9)
    return EvidenceLine(text=text, source=source)


def _cand(value, unit="mm", bbox=(0.1, 0.1, 0.2, 0.12), channel="vision", **extra):
    source = Source(document_id="GA", page=1, locator="t", bbox=bbox, confidence=0.8)
    return Candidate(
        path="diameter", value=value, unit=unit, source=source, channel=channel, **extra
    )


def test_grounding_accepts_values_present_in_the_cited_region():
    lines = [_line('ID 78 3/4"'), _line("ID 2000", bbox=(0.5, 0.5, 0.6, 0.52))]
    assert is_grounded(_cand(2000.25), lines) is True  # 78 3/4" = 2000,25 mm
    assert is_grounded(_cand(2000.0, bbox=(0.5, 0.5, 0.6, 0.52)), lines) is True
    assert is_grounded(_cand(1800.0), lines) is False  # inventado
    assert is_grounded(_cand(2000.0, bbox=(0.8, 0.8, 0.9, 0.82)), lines) is False  # mal citado
    assert is_grounded(_cand(1.0, text_original="ID 2000"), [_line("ID 2000")]) is True
    assert is_grounded(_cand(2000.0), []) is None  # sin texto con el que comparar
    pressure = _cand(10.0, unit="bar")
    assert is_grounded(pressure, [_line("145.0 psig")]) is True


def test_pipeline_drops_model_values_that_their_citation_does_not_support():
    from trazia.ingest import Bundle
    from trazia.model import Document

    bundle = Bundle(
        document=Document(id="GA", filename="GAD_X_rev1.pdf", revision="1", sha256="0" * 64),
        media_type="pdf",
        lines=[_line("ID 2000")],
    )
    warnings, events = [], []
    kept = _ground(
        [_cand(2000.0), _cand(1800.0), _cand(1800.0, channel="tabla")],
        [bundle],
        warnings,
        events.append,
        "e",
    )
    assert [c.value for c in kept] == [
        2000.0,
        1800.0,
    ]  # el candidato de tabla se conserva para revisión
    assert kept[0].grounded is True and kept[1].grounded is False
    assert "sin respaldo" in warnings[0] and events[0].stage == "validate"

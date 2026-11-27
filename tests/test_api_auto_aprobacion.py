"""Aprobación automática de campos fiables al guardar una revisión nueva.

Datos sintéticos del ejemplo V-101 del repositorio; nada de TR.
"""

from pathlib import Path

from trazia.api import auto_approval
from trazia.model import load_revision

EJEMPLO = Path(__file__).resolve().parents[1] / "examples" / "vessel_rev_a.json"


def _revision(confianza, grounded=True, estado="candidate"):
    revision = load_revision(EJEMPLO)
    campo = revision.traced_fields()["height"]
    campo.state = estado
    campo.alternatives = []
    campo.source = campo.source.model_copy(update={"confidence": confianza, "grounded": grounded})
    return revision


def test_solo_se_aprueba_un_candidato_fiable_y_encontrado_en_el_original(monkeypatch):
    monkeypatch.delenv("TRAZIA_AUTO_APROBACION", raising=False)
    assert "height" in auto_approval.aprobables(_revision(0.95), 0.9)
    assert "height" not in auto_approval.aprobables(_revision(0.85), 0.9)
    assert "height" not in auto_approval.aprobables(_revision(0.95, grounded=None), 0.9)
    assert "height" not in auto_approval.aprobables(_revision(0.95, estado="conflict"), 0.9)


def test_la_aprobacion_queda_en_la_auditoria_y_dice_que_fue_automatica(monkeypatch):
    monkeypatch.delenv("TRAZIA_AUTO_APROBACION", raising=False)
    revision, accion = auto_approval.aprobar_al_guardar("P:E:A", _revision(0.97))
    campo = revision.traced_fields()["height"]
    assert campo.state == "accepted"
    assert campo.source.reviewed is True
    assert campo.explanation.startswith(auto_approval.PREFIJO)
    assert accion is not None
    assert (accion.path, accion.actor, accion.revision_id) == (
        "$auto_accept",
        auto_approval.ACTOR,
        "P:E:A",
    )


def test_se_puede_apagar(monkeypatch):
    monkeypatch.setenv("TRAZIA_AUTO_APROBACION", "off")
    revision, accion = auto_approval.aprobar_al_guardar("P:E:A", _revision(0.99))
    assert accion is None
    assert revision.traced_fields()["height"].state == "candidate"


def test_el_umbral_por_defecto_es_0_8(monkeypatch):
    monkeypatch.delenv("TRAZIA_AUTO_APROBACION", raising=False)
    assert auto_approval.umbral() == 0.8
    revision, accion = auto_approval.aprobar_al_guardar("P:E:A", _revision(0.85))
    assert accion is not None
    assert revision.traced_fields()["height"].state == "accepted"
    revision, accion = auto_approval.aprobar_al_guardar("P:E:A", _revision(0.75))
    assert revision.traced_fields()["height"].state == "candidate"

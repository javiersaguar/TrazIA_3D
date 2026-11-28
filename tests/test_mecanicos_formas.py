"""Piezas de un mecánico con forma (cilindro, revolución, extrusión), clase IFC y clasificación.

Ficha sintética: no cita ningún plano del reto.
"""

import sys
from pathlib import Path

import pytest

from trazia.ifc import build_ifc, validate_ifc
from trazia.model import SkidPart

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mecanicos_manual as mm  # noqa: E402

ISO = [["ISO 14224:2016", "CO", "Compresores"], ["IFC4", "IfcCompressor.DYNAMIC", "Dinámico"]]


def _ficha():
    def pieza(id_, **kw):
        return {"id": id_, "name": id_, "page": 1, "locator": "Vista de prueba", **kw}

    return {
        "tag": "EQ-1",
        "equipment_id": "eq-1",
        "revision": "0",
        "document": {"id": "GA", "filename": "EQ-1-Rev0.pdf", "page_count": 2},
        "kind": "compressor",
        "predefined_type": "DYNAMIC",
        "tag_page": 1,
        "tag_locator": "Rótulo de prueba",
        "classification": ISO,
        "attributes": {"norma": ["API 617", "1", 1, "Notas de prueba"]},
        "components": [
            pieza(
                "bancada",
                origin=[0, -500, 0],
                size=[3000, 1000, 200],
                ifc_class="IfcPlate",
                predefined_type="BASEPLATE",
                object_type="SKID_BASE",
            ),
            pieza(
                "maquina",
                shape="revolve",
                axis="x",
                center=[0, 800],
                profile=[[500, 0], [500, 400], [2500, 400], [2500, 0]],
                classification=ISO,
            ),
            pieza(
                "eje",
                shape="cylinder",
                axis="x",
                origin=[2500, -50, 750],
                size=[300, 100, 100],
                object_type="SHAFT",
            ),
            pieza(
                "viga",
                shape="extrude",
                axis="x",
                range=[0, 3000],
                profile=[[-500, 0], [-400, 0], [-400, 200], [-500, 200]],
                ifc_class="IfcBeam",
                predefined_type="BEAM",
            ),
            pieza(
                "rodete",
                shape="revolve",
                axis="x",
                center=[0, 800],
                profile=[[1400, 50], [1400, 300], [1450, 300], [1450, 50]],
                regla="asumido.interior_no_dibujado",
                explicacion="No se dibuja en el GA.",
            ),
        ],
        "nozzles": [
            mm_n("TP1", "6", [1000, 0, 1400]),
            {**mm_n("TP2", "HOLD", [2000, 0, 1400]), "od_provisional": 60.3, "b16_5": False},
        ],
    }


def mm_n(id_, nps, cara):
    return {
        "id": id_,
        "service": "SERVICIO",
        "nps": nps,
        "rating": "300# RF",
        "face": cara,
        "dir": [0, 0, 1],
        "page": 2,
        "locator": "Tabla de prueba",
        "projection": 200,
        "medido": False,
        "b16_5": True,
        "preliminar": True,
        "note": None,
    }


@pytest.fixture
def revision(tmp_path):
    (tmp_path / "mechanical").mkdir()
    (tmp_path / "mechanical" / "EQ-1-Rev0.pdf").write_bytes(b"%PDF-1.4 prueba")
    return mm.revision(_ficha(), tmp_path)


def test_formas_y_clasificacion_entran_en_el_contrato(revision):
    eq = revision.equipment
    piezas = {p.id: p for p in eq.components}
    assert piezas["maquina"].shape == "revolve" and piezas["maquina"].axis == "x"
    assert piezas["viga"].ifc_class == "IfcBeam"
    assert [c.system for c in eq.classification] == ["ISO 14224:2016", "IFC4"]
    # La envolvente de la revolución sale del perfil: radio 400 alrededor de (0, 800).
    env = piezas["maquina"].envelope
    assert (env.origin.x.value, env.size.x.value) == (500.0, 2000.0)
    assert (env.origin.z.value, env.size.z.value) == (400.0, 800.0)
    # Pieza interior que el GA no dibuja: supuesta, con su regla.
    assert piezas["rodete"].envelope.origin.x.state == "assumed"
    assert piezas["rodete"].envelope.origin.x.source.rule == "asumido.interior_no_dibujado"


def test_tobera_hold_sin_norma_de_brida(revision):
    toberas = {n.id: n for n in revision.equipment.nozzles}
    hold = toberas["TP2"]
    assert hold.size_nps.value == "HOLD"
    assert hold.diameter.value == pytest.approx(60.3)
    assert hold.diameter.source.rule == "asumido.od_tamano_hold"
    assert hold.flange_standard is None
    assert toberas["TP1"].flange_standard.value == "B16.5"
    assert hold.position.x.state == "candidate"


def test_ifc_valido_con_formas(revision):
    ifc = build_ifc(revision)
    assert not validate_ifc(ifc)


def test_recuadro_en_su_lamina():
    rec = {"x": [0.1, 0.1, 0.2, 0.2], "_paginas": {"x": 3}}
    assert mm.pagina_de(rec, "x", 1) == 3
    assert mm.pagina_de(rec, "z", 1) == 1
    assert mm.pagina_de({}, "x", 2) == 2


def test_extrusion_necesita_tres_vertices():
    base = {
        "id": "p",
        "name": {
            "value": "p",
            "unit": "1",
            "state": "accepted",
            "source": {
                "document_id": "GA",
                "page": 1,
                "locator": "x",
                "confidence": 1.0,
                "channel": "humano",
            },
        },
    }
    campo = base["name"] | {"value": 1.0, "unit": "mm"}
    env = {"origin": {a: campo for a in "xyz"}, "size": {a: campo for a in "xyz"}}
    with pytest.raises(ValueError):
        SkidPart.model_validate(
            {**base, "envelope": env, "shape": "extrude", "axis": "x", "profile": [(0, 0), (1, 1)]}
        )

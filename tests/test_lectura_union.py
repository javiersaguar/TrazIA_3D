import pytest
from reportlab.pdfgen import canvas

from scripts.lectura_union import unir_ga_hdm, unir_pdf
from trazia.model import Source


def _candidato(documento, path, valor, unidad=""):
    return {
        "path": path,
        "value": valor,
        "unit": unidad,
        "source": {"document_id": documento, "page": 1, "locator": f"Lectura {valor}"},
    }


def _entrada(tag="EJ-01", rev="rev1", candidatos=(), ids=None):
    return {
        "equipment_tag": tag,
        "revision": rev,
        "candidates": list(candidatos),
        "identifiers": ids or {},
    }


def test_une_ga_hdm_con_conflictos_citados_y_equipara_unidades():
    ga = _entrada(
        candidatos=[
            _candidato("GA", "attributes.weight_empty", 1000, "kg"),
            _candidato("GA", "nozzles.N1.projection", 600, "mm"),
            _candidato("GA", "nozzles.N1.rating", "300#"),
            _candidato("GA", "nozzles.N1.schedule", "80"),
        ],
        ids={"N1": {"kind": "nozzle", "appearances": [{"role": "ga_table"}]}},
    )
    hdm = _entrada(
        tag="ej-01",
        rev="REV 1",
        candidatos=[
            _candidato("HDM", "attributes.weight_empty", 1.1, "t"),
            _candidato("HDM", "nozzles.N01.projection", 0.6, "m"),
            _candidato("HDM", "nozzles.N01.rating", "300#", "1"),
            _candidato("HDM", "nozzles.N01.schedule", "Sch.80", "1"),
        ],
        ids={"N01": {"kind": "nozzle", "appearances": [{"role": "hdm_table"}]}},
    )

    salida = unir_ga_hdm(ga, hdm)
    assert salida["conflicts"] == ["attributes.weight_empty"]
    assert [
        (c["source"]["document_id"], c["value"], c["state"])
        for c in salida["candidates"]
        if c["path"] == "attributes.weight_empty"
    ] == [("GA", 1000, "conflict"), ("HDM", 1.1, "conflict")]
    proyecciones = [c for c in salida["candidates"] if c["path"] == "nozzles.N1.projection"]
    assert len(proyecciones) == 2 and all(c.get("state") != "conflict" for c in proyecciones)
    assert any(c["path"] == "nozzles.N1.rating" for c in salida["candidates"])
    assert salida["identifiers"]["N1"]["appearances"] == [
        {"role": "ga_table"},
        {"role": "hdm_table"},
    ]
    assert "state" not in ga["candidates"][0] and "state" not in hdm["candidates"][0]


@pytest.mark.parametrize(("tag", "rev"), [("EJ-02", "rev1"), ("EJ-01", "rev2"), ("EJ-01", "")])
def test_no_une_equipos_o_revisiones_distintos(tag, rev):
    with pytest.raises(ValueError):
        unir_ga_hdm(_entrada(), _entrada(tag=tag, rev=rev))


def test_une_pdfs_y_conserva_citas_dentro_de_la_pagina(tmp_path):
    ga, hdm = tmp_path / "GAD_EJ-03_rev2.pdf", tmp_path / "HDM_EJ-03.pdf"
    for path, lines in (
        (ga, ("EMPTY WEIGHT (Kg) 100",)),
        (hdm, ("WEIGHT & CAPACITY", "EMPTY WEIGHT (Kg) 120")),
    ):
        doc = canvas.Canvas(str(path))
        for i, linea in enumerate(lines):
            doc.drawString(35, 600 - i * 35, linea)
        doc.save()

    unido = unir_pdf(ga, hdm)
    assert unido["conflicts"] == ["attributes.weight_empty"]
    assert unido["revision"] == "rev2"
    assert [dato["value"] for dato in unido["candidates"]] == [100, 120]
    for dato in unido["candidates"]:
        cita = Source.model_validate(dato["source"])
        assert cita.page == 1 and cita.bbox and str(int(dato["value"])) in cita.locator

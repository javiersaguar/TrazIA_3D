import json
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from trazia import lote, pdf_limits
from trazia.ingest import ingest_bytes


def test_paginas_vectoriales_densas_se_rechazan_antes_del_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_limits, "MAX_CONTENT_BYTES", 48_000)
    ruta = tmp_path / "GAD_ZZ_rev1.pdf"
    plano = canvas.Canvas(str(ruta), pageCompression=1)
    for i in range(5000):
        plano.line(5, i % 300, 65, i % 300)
    plano.showPage()
    plano.save()
    assert ruta.stat().st_size < pdf_limits.MAX_CONTENT_BYTES
    with pytest.raises(ValueError, match="Página 1.*descomprimido.*presupuesto"):
        ingest_bytes(ruta.read_bytes(), ruta.name, "GA-ZZ", "1")
    [fila] = lote.procesar_carpeta(tmp_path, tmp_path / "salida")
    assert fila.estado == "error"
    eventos = Path(fila.carpeta) / "eventos.json"
    avisos = json.loads(eventos.read_text(encoding="utf-8"))["avisos"]
    assert any("Página 1" in aviso and "presupuesto" in aviso for aviso in avisos)

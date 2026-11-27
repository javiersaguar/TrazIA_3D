from PIL import Image
from reportlab.pdfgen import canvas

from scripts import medir_vision_envolvente
from trazia.vision.base import ProviderResult


def test_medicion_solo_pide_huecos_y_descarta_cotas_sin_cita(tmp_path, monkeypatch):
    ruta = tmp_path / "GAD_EJ-08_rev1.pdf"
    doc = canvas.Canvas(str(ruta), pagesize=(600, 800))
    for y, dato in (
        (750, "HORIZONTAL VESSEL"),
        (710, "ID Ø1400 x 8mm"),
        (610, "4200(T.L. To T.L.)"),
        (500, "230 mm"),
    ):
        doc.drawString(100, y, dato)
    doc.save()

    class Provider:
        def read(self, imagen, task, schema, *, page_ref):
            assert imagen and task == "campos" and page_ref.endswith("#p1")
            ruta = schema["properties"]["fields"]["items"]["properties"]["field"]
            assert ruta["enum"] == ["horizontal.saddle_width"]
            fields = [
                {
                    "field": "horizontal.saddle_width",
                    "value": valor,
                    "unit": "mm",
                    "text": "230 mm",
                    "bbox": [0.14, 0.35, 0.27, 0.40],
                }
                for valor in ("230", "510")
            ]
            return ProviderResult({"fields": fields}, "local-fixture", "local", "p")

    monkeypatch.setattr(medir_vision_envolvente, "get_provider", lambda *_, **__: Provider())
    monkeypatch.setattr(
        medir_vision_envolvente, "render_page", lambda *_: Image.new("RGB", (60, 80))
    )
    informe = medir_vision_envolvente.medir(
        ruta, ["horizontal.diameter", "horizontal.saddle_width"], vision=True
    )
    assert set(informe["cpu"]["fields"]) == {"horizontal.diameter"}
    assert informe["vision"]["rejected"] == 1
    assert [r["value"] for r in informe["vision"]["fields"]] == [230]
    assert informe["vision"]["cost_eur"] is None

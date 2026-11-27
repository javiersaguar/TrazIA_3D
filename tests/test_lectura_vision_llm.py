"""Visión del plan A (J4) con un proveedor falso y datos sintéticos: nada sale del equipo."""

from PIL import Image

from trazia.extraction import Candidate
from trazia.ingest import EvidenceLine
from trazia.lectura import vision_llm
from trazia.model import Source
from trazia.vision.base import ProviderResult, VisionError

DOC = "GA-EJ-V-01"


def _c(path, value, unit="mm", confianza=0.9, bbox=(0.1, 0.1, 0.2, 0.12)):
    fuente = Source(
        document_id=DOC, page=1, bbox=bbox, locator=f"{path} {value}", confidence=confianza
    )
    return Candidate(path=path, value=value, unit=unit, source=fuente, channel="cota")


def _linea(texto, bbox):
    return EvidenceLine(
        text=texto,
        source=Source(document_id=DOC, page=1, bbox=bbox, locator=texto, confidence=1.0),
    )


class Falso:
    """Devuelve respuestas fijas por tarea y apunta lo que se le pide."""

    model = "falso-1"

    def __init__(self, huecos=(), veredicto="confirma", falla=False):
        self.huecos = list(huecos)
        self.veredicto = veredicto
        self.falla = falla
        self.pedidos = []

    def read(self, image_png, task, schema, *, page_ref):
        self.pedidos.append((task, schema, page_ref))
        if self.falla:
            raise VisionError("sin conexión")
        if task == "huecos":
            data = {"fields": self.huecos}
        else:
            data = {"veredicto": self.veredicto, "texto": "T.L.-T.L. 1925"}
        return ProviderResult(data=data, provider="falso", model=self.model, prompt_sha256="0" * 64)


VERTICAL = [
    _c("attributes.equipment_type", "vertical_vessel", "1"),
    _c("attributes.support", "skirt", "1"),
    _c("diameter", 800.0),
    _c("head_depth", 257.0),
    _c("skirt_height", 1500.0),
    _c("nozzles.N1.size_nps", 2.0, "in"),
    _c("nozzles.N1.elevation", 900.0),
]
LINEAS = [
    _linea("T.L.-T.L. 1925", (0.40, 0.30, 0.46, 0.32)),
    _linea("N1 90°", (0.7, 0.7, 0.74, 0.72)),
]
IMAGEN = Image.new("RGB", (1000, 700), "white")


def _completar(proveedor, candidatos=VERTICAL):
    informe = vision_llm.Informe()
    nuevos = vision_llm.completar(
        proveedor,
        IMAGEN,
        documento=DOC,
        pagina=1,
        lineas=LINEAS,
        candidatos=candidatos,
        page_ref="a" * 64 + "#p1",
        informe=informe,
    )
    return nuevos, informe


def test_huecos_de_la_familia_y_de_las_boquillas():
    assert vision_llm.huecos(VERTICAL) == ["height", "nozzles.N1.bearing"]
    # Sin familia reconocible no se pide nada.
    assert vision_llm.huecos([_c("diameter", 800.0)]) == []


def test_solo_entra_lo_que_respalda_el_texto_vectorial():
    proveedor = Falso(
        huecos=[
            # Respaldado: «1925» está en la caja citada (cajas 0-1 tras el escalado del proveedor).
            {
                "field": "height",
                "text": "1925",
                "value": "1925",
                "unit": "mm",
                "bbox": [0.40, 0.30, 0.46, 0.32],
            },
            # Inventado: no hay ningún 90 en esa caja.
            {
                "field": "nozzles.N1.bearing",
                "text": "90°",
                "value": "90",
                "unit": "deg",
                "bbox": [0.1, 0.8, 0.15, 0.82],
            },
            # Fuera del enum: se ignora aunque llegue.
            {"field": "tag", "text": "EJ-V-01", "value": "EJ-V-01", "bbox": [0, 0, 0.1, 0.1]},
        ]
    )
    nuevos, informe = _completar(proveedor)
    assert [(c.path, c.value, c.unit) for c in nuevos] == [("height", 1925.0, "mm")]
    assert nuevos[0].channel == "vision" and nuevos[0].grounded is True
    assert nuevos[0].source.rule == "vision.hueco" and nuevos[0].source.model == "falso-1"
    assert informe.rechazados == 1 and informe.aceptados == ["height"]
    # Las rutas pedidas van en el enum del esquema, no en el prompt.
    tarea, esquema, _ = proveedor.pedidos[0]
    assert tarea == "huecos"
    assert esquema["properties"]["fields"]["items"]["properties"]["field"]["enum"] == [
        "height",
        "nozzles.N1.bearing",
    ]


def test_sin_huecos_no_llama_al_proveedor():
    completo = [*VERTICAL, _c("height", 1925.0), _c("nozzles.N1.bearing", 90.0, "deg")]
    proveedor = Falso()
    nuevos, informe = _completar(proveedor, completo)
    assert nuevos == [] and proveedor.pedidos == [] and informe.llamadas == 0


def test_validador_solo_cambia_la_confianza():
    dudoso = _c("height", 1925.0, confianza=0.5, bbox=(0.40, 0.30, 0.46, 0.32))
    candidatos = [*VERTICAL, dudoso]
    for veredicto, esperada in (("confirma", 0.8), ("contradice", 0.3), ("no_visible", 0.5)):
        informe = vision_llm.Informe()
        salida = vision_llm.validar(
            Falso(veredicto=veredicto),
            IMAGEN,
            candidatos,
            documento=DOC,
            pagina=1,
            page_ref="a" * 64 + "#p1",
            informe=informe,
        )
        assert len(salida) == len(candidatos)
        nuevo = next(c for c in salida if c.path == "height")
        assert nuevo.value == 1925.0 and nuevo.source.confidence == esperada
        assert informe.validados == {"height": veredicto}
        # Los de confianza alta no se mandan.
        assert all(c is o for c, o in zip(salida[:-1], candidatos[:-1], strict=True))


def test_un_fallo_del_proveedor_queda_en_el_informe():
    nuevos, informe = _completar(Falso(falla=True))
    assert nuevos == [] and informe.errores and "sin conexión" in informe.errores[0]

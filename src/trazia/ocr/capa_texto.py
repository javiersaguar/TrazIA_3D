"""Capa de texto OCR y rayado de tablas para páginas sin texto (escaneos o texto en trazos).

Un GA de otro fabricante puede llegar escaneado, girado o exportado con el texto convertido en
trazos. El lector de TrazIA-3D trabaja sobre palabras y bordes de tabla con coordenadas, así que
aquí se le da a cada página sin texto lo que le falta, sin tocar el resto del documento:

- la imagen de la página ya enderezada (el giro `/Rotate` queda aplicado),
- el texto reconocido como texto invisible en su posición: horizontal y también vertical
  (cotas de un alzado), en el sentido de lectura que dé mejor confianza,
- las líneas largas horizontales y verticales del dibujo como trazos transparentes, para que
  las tablas (lista de boquillas, datos de diseño) vuelvan a tener sus celdas.

Las páginas con texto se copian tal cual. Las cajas quedan en el mismo sistema que la página
mostrada, así que la evidencia apunta al sitio que ve el revisor en el original.
"""

import io
from dataclasses import dataclass

import pdfplumber
from PIL import Image

from ..pdf_limits import PDFIUM_LOCK
from .engine import OcrLine, _tiled_lines

MAX_LADO_PX = 8000  # un A1 a unos 240 ppp; más no mejora el OCR y multiplica el tiempo
DPI_MAX = 300
DPI_IMAGEN = 150  # imagen de fondo de la página nueva: solo la ve quien abra este PDF derivado
CONFIANZA_MINIMA = 0.5
VERSION = "capa-ocr-v1"


@dataclass(frozen=True)
class PaginaLeida:
    numero: int
    horizontales: int
    verticales: int
    reglas: int


def _dpi(page) -> int:
    lado = max(page.width, page.height) / 72
    return max(100, min(DPI_MAX, int(MAX_LADO_PX / lado)))


def _girar(lineas: list[OcrLine], sentido: int) -> list[OcrLine]:
    """Cajas leídas en la imagen girada, devueltas al sistema de la página.

    `sentido=90`: la imagen se giró 90° antihorario (texto que baja). `sentido=270`: horario
    (texto que sube, el habitual en cotas verticales).
    """
    salida = []
    for linea in lineas:
        a, b, c, d = linea.bbox
        caja = (1 - d, a, 1 - b, c) if sentido == 90 else (b, 1 - c, d, 1 - a)
        salida.append(OcrLine(linea.text, caja, linea.score))
    return salida


def _area(caja):
    return max(0.0, caja[2] - caja[0]) * max(0.0, caja[3] - caja[1])


def _solape(a, b):
    ancho = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    alto = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ancho * alto


def _vertical(caja, proporcion):
    """Caja más alta que ancha en la página mostrada (en unidades reales, no normalizadas)."""
    return (caja[3] - caja[1]) * proporcion > 1.5 * (caja[2] - caja[0])


def _combinar(rectas, sube, baja, proporcion):
    """Texto horizontal y vertical sin duplicados: cada zona conserva su mejor lectura."""
    verticales = []
    for linea, sentido in sorted(
        [(x, 270) for x in sube] + [(x, 90) for x in baja], key=lambda par: -par[0].score
    ):
        if (
            linea.score < CONFIANZA_MINIMA
            or len(linea.text.strip()) < 2
            or not _vertical(linea.bbox, proporcion)
        ):
            continue
        if any(_solape(linea.bbox, otra.bbox) > 0.3 * _area(linea.bbox) for otra, _ in verticales):
            continue
        verticales.append((linea, sentido))
    horizontales = []
    for linea in rectas:
        if linea.score < CONFIANZA_MINIMA or _vertical(linea.bbox, proporcion):
            continue
        tapada = any(
            _solape(linea.bbox, otra.bbox) > 0.5 * _area(linea.bbox) and otra.score > linea.score
            for otra, _ in verticales
        )
        if not tapada:
            horizontales.append(linea)
    return horizontales, verticales


def _reglas(imagen: Image.Image) -> list[tuple[float, float, float, float]]:
    """Segmentos largos horizontales y verticales, normalizados 0–1 (origen arriba-izquierda)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    gris = np.array(imagen.convert("L"))
    _, tinta = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    alto, ancho = tinta.shape
    segmentos = []
    for horizontal in (True, False):
        largo = max(25, (ancho if horizontal else alto) // 60)
        nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (largo, 1) if horizontal else (1, largo))
        trazos = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, nucleo)
        cuenta, _, datos, _ = cv2.connectedComponentsWithStats(trazos, connectivity=8)
        for i in range(1, cuenta):
            x, y, w, h, _ = datos[i]
            if horizontal and w >= largo and h <= 12:
                medio = (y + h / 2) / alto
                segmentos.append((x / ancho, medio, (x + w) / ancho, medio))
            elif not horizontal and h >= largo and w <= 12:
                medio = (x + w / 2) / ancho
                segmentos.append((medio, y / alto, medio, (y + h) / alto))
    return segmentos


def _texto_seguro(texto: str) -> str:
    """Helvetica estándar (WinAnsi): lo que no cabe se cambia por su equivalente ASCII."""
    cambios = {"⌀": "Ø", "–": "-", "—": "-", "’": "'", "“": '"', "”": '"', "×": "x"}
    texto = "".join(cambios.get(c, c) for c in texto)
    return texto.encode("cp1252", "replace").decode("cp1252")


def _pagina(lienzo, page, imagen, horizontales, verticales, reglas):
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth

    ancho, alto = float(page.width), float(page.height)
    lienzo.setPageSize((ancho, alto))
    fondo = imagen.convert("L")
    escala = DPI_IMAGEN / 72
    fondo.thumbnail((max(1, int(ancho * escala)), max(1, int(alto * escala))))
    buffer = io.BytesIO()
    fondo.save(buffer, "JPEG", quality=70)
    lienzo.drawImage(ImageReader(io.BytesIO(buffer.getvalue())), 0, 0, ancho, alto)
    lienzo.saveState()
    lienzo.setStrokeAlpha(0)
    lienzo.setLineWidth(0.5)
    for x0, y0, x1, y1 in reglas:
        lienzo.line(x0 * ancho, alto - y0 * alto, x1 * ancho, alto - y1 * alto)
    lienzo.restoreState()

    def escribir(texto, largo, cuerpo):
        texto = _texto_seguro(texto)
        natural = stringWidth(texto, "Helvetica", cuerpo) or 1
        objeto = lienzo.beginText()
        objeto.setTextRenderMode(3)  # invisible: lo lee pdfplumber, no tapa el escaneo
        objeto.setFont("Helvetica", cuerpo)
        objeto.setHorizScale(max(20.0, min(400.0, 100 * largo / natural)))
        objeto.setTextOrigin(0, 0)
        objeto.textOut(texto)
        lienzo.drawText(objeto)

    for linea in horizontales:
        x0, y0, x1, y1 = linea.bbox
        cuerpo = max(2.0, (y1 - y0) * alto * 0.8)
        lienzo.saveState()
        lienzo.translate(x0 * ancho, alto - y1 * alto + 0.2 * cuerpo)
        escribir(linea.text, (x1 - x0) * ancho, cuerpo)
        lienzo.restoreState()
    for linea, sentido in verticales:
        x0, y0, x1, y1 = linea.bbox
        cuerpo = max(2.0, (x1 - x0) * ancho * 0.8)
        lienzo.saveState()
        if sentido == 270:  # sube: línea base a la derecha, de abajo arriba
            lienzo.translate(x1 * ancho - 0.2 * cuerpo, alto - y1 * alto)
            lienzo.rotate(90)
        else:  # baja: línea base a la izquierda, de arriba abajo
            lienzo.translate(x0 * ancho + 0.2 * cuerpo, alto - y0 * alto)
            lienzo.rotate(-90)
        escribir(linea.text, (y1 - y0) * alto, cuerpo)
        lienzo.restoreState()


def paginas_sin_texto(data: bytes) -> list[int]:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [page.page_number for page in pdf.pages if not page.chars]


def pdf_legible(data: bytes, paginas: list[int]) -> tuple[bytes, list[PaginaLeida]]:
    """PDF con capa de texto y rayado en `paginas` (1-based); el resto se copia sin cambios.

    Lanza `OcrUnavailable` si no hay motor ni caché, e `ImportError` sin reportlab o pypdfium2.
    """
    import pypdfium2 as pdfium
    from reportlab.pdfgen.canvas import Canvas

    from ..page_cache import render_page

    salida_ocr = io.BytesIO()
    lienzo = Canvas(salida_ocr, pageCompression=1)
    leidas = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for numero in paginas:
            page = pdf.pages[numero - 1]
            imagen = render_page(page, _dpi(page))
            try:
                rectas = _tiled_lines(imagen)
                sube = _girar(_tiled_lines(imagen.transpose(Image.Transpose.ROTATE_270)), 270)
                baja = _girar(_tiled_lines(imagen.transpose(Image.Transpose.ROTATE_90)), 90)
                proporcion = float(page.height) / float(page.width)
                horizontales, verticales = _combinar(rectas, sube, baja, proporcion)
                reglas = _reglas(imagen)
                _pagina(lienzo, page, imagen, horizontales, verticales, reglas)
                lienzo.showPage()
            finally:
                imagen.close()
            leidas.append(PaginaLeida(numero, len(horizontales), len(verticales), len(reglas)))
        total = len(pdf.pages)
    lienzo.save()
    with PDFIUM_LOCK:
        original = pdfium.PdfDocument(data)
        leido = pdfium.PdfDocument(salida_ocr.getvalue())
        nuevo = pdfium.PdfDocument.new()
        try:
            posicion = {numero: i for i, numero in enumerate(paginas)}
            for numero in range(1, total + 1):
                if numero in posicion:
                    nuevo.import_pages(leido, [posicion[numero]])
                else:
                    nuevo.import_pages(original, [numero - 1])
            buffer = io.BytesIO()
            nuevo.save(buffer)
        finally:
            nuevo.close()
            leido.close()
            original.close()
    return buffer.getvalue(), leidas

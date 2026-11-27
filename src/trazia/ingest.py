import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Literal, NamedTuple, cast

import pdfplumber
from openpyxl import load_workbook
from PIL import Image
from pydantic import Field

from .model import Document, Model, Source
from .pdf_limits import check_page_content

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 100
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
IMAGE_DPI = 200  # el mismo del OCR: el PDF de una imagen se reconoce a su tamaño original
A1 = 2384 * 1684  # área de una lámina A1 en puntos PDF
SPARSE_TEXT_MAX = 450  # letras que bastan para que una lámina no se tome por un raster
# Firma de los primeros bytes por extensión: la extensión sola no dice qué es el archivo.
SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".xlsx": (b"PK\x03\x04",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
}
# El layout de PDFMiner expande todos los trazos. Para los GA mecánicos se
# habilita otro presupuesto, solo en el lector de texto de PDFium.
CAD_PAGE_BYTES = 64 * 1024**2
CAD_DOCUMENT_BYTES = 128 * 1024**2
DocumentKind = Literal["GA", "HDM", "VESOR", "ESTRUCTURA"]


_STATIC_NAME = re.compile(
    r"(?P<kind>GAD|GA|HDM|VESOR|ESTRUCTURA)_(?P<tag>.+?)(?:_rev(?P<rev>[^_.]+))?\.\w+",
    re.IGNORECASE,
)
_MECHANICAL_NAME = re.compile(
    r"(?P<tag>.+?)-(?P<sheet>GA\d+)-Rev(?P<rev>[^.]+)\.pdf",
    re.IGNORECASE,
)


class DatasetFilename(NamedTuple):
    kind: DocumentKind
    tag: str
    revision: str | None
    sheet: str | None = None

    @property
    def mechanical_kind(self) -> Literal["pump", "compressor"] | None:
        if self.sheet and self.tag.upper() == "BOMBA":
            return "pump"
        if self.sheet and self.tag.upper() == "COMPRESOR":
            return "compressor"
        return None

    @property
    def catalogue_tag(self) -> str:
        if self.mechanical_kind:
            return f"{self.tag.upper()}-{self.sheet}"
        return self.tag


def dataset_filename(filename: str) -> DatasetFilename | None:
    """Reconoce el tipo, tag y revisión del nombre de un documento del reto."""
    name = Path(filename).name
    if match := _STATIC_NAME.fullmatch(name):
        kind = match["kind"].upper()
        return DatasetFilename(
            cast(DocumentKind, "GA" if kind == "GAD" else kind), match["tag"], match["rev"]
        )
    if match := _MECHANICAL_NAME.fullmatch(name):
        return DatasetFilename("GA", match["tag"], match["rev"], match["sheet"].upper())
    return None


def _check_signature(data: bytes, suffix: str) -> None:
    signatures = SIGNATURES.get(suffix)
    if signatures is None:
        return
    # Un PDF puede llevar basura antes de la cabecera; los lectores la aceptan en el primer KB.
    head = data[:1024] if suffix == ".pdf" else data[:16]
    found = any(s in head for s in signatures) if suffix == ".pdf" else head.startswith(signatures)
    if not found:
        raise ValueError(
            f"No es un {suffix.lstrip('.').upper()} válido: no corresponde a la extensión"
        )


def image_to_pdf(data: bytes) -> bytes:
    """Una imagen (PNG, JPEG o TIFF de varias páginas) como PDF escaneado, para el OCR y la visión.

    Cada píxel queda a `IMAGE_DPI`: al renderizar el PDF para el OCR sale la imagen original.
    """
    with Image.open(io.BytesIO(data)) as image:
        frames = []
        for index in range(getattr(image, "n_frames", 1)):
            if index >= MAX_PAGES:
                raise ValueError("Límite de la base: 100 páginas por documento")
            image.seek(index)
            frames.append(image.convert("RGB"))
    buffer = io.BytesIO()
    frames[0].save(buffer, "PDF", resolution=IMAGE_DPI, save_all=True, append_images=frames[1:])
    return buffer.getvalue()


class EvidenceLine(Model):
    text: str
    source: Source


class Bundle(Model):
    document: Document
    media_type: str
    lines: list[EvidenceLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    kind: DocumentKind | None = Field(default=None, exclude=True)
    equipment_tag: str | None = Field(default=None, exclude=True)
    sparse_pages: list[int] = Field(default_factory=list, exclude=True)


def ingest_bytes(data: bytes, filename: str, document_id: str, revision: str) -> Bundle:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("El documento debe ocupar entre 1 byte y 25 MB")
    suffix = Path(filename).suffix.lower()
    _check_signature(data, suffix)
    document = Document(
        id=document_id,
        filename=Path(filename).name,
        revision=revision,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    bundle = Bundle(document=document, media_type=suffix.lstrip("."))
    if suffix == ".pdf":
        from pdfminer.pdfdocument import PDFPasswordIncorrect

        try:
            pdf = pdfplumber.open(io.BytesIO(data))
        except PDFPasswordIncorrect:
            raise ValueError("PDF cifrado con contraseña: hay que pedir el original sin cifrar")
        except Exception as exc:  # pdfminer lanza sus propias excepciones con bytes corruptos
            raise ValueError(f"No es un PDF válido: {exc}") from None
        with pdf:
            if getattr(pdf.doc, "encryption", None):
                bundle.warnings.append(
                    "PDF cifrado sin contraseña de apertura: se lee, pero conviene el original"
                )
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError("Límite de la base: 100 páginas por PDF")
            document.page_count = len(pdf.pages)
            named = dataset_filename(filename)
            if named and named.mechanical_kind:
                from .pdf_text import read_vector_lines

                remaining = CAD_DOCUMENT_BYTES
                for page in pdf.pages:
                    remaining -= check_page_content(page, limit=min(remaining, CAD_PAGE_BYTES))
                bundle.lines = read_vector_lines(data, document_id)
                with_text = {line.source.page for line in bundle.lines}
                bundle.sparse_pages = [
                    page.page_number for page in pdf.pages if page.page_number not in with_text
                ]
                _read_drawing_revision(bundle)
                return bundle
            for page in pdf.pages:
                check_page_content(page)
            for page in pdf.pages:
                clipped = dropped = 0
                page_lines: list[EvidenceLine] = []
                from .page_cache import memo_page

                def text_rows(page=page):
                    return [
                        {
                            "chars": [
                                {key: char[key] for key in ("text", "x0", "x1", "top", "bottom")}
                                for char in row["chars"]
                            ]
                        }
                        for row in page.extract_text_lines(return_chars=True)
                    ]

                rows = memo_page(page, "text-lines-v1", text_rows)
                characters = sum(len(c["text"].strip()) for row in rows for c in row["chars"])
                # Umbral de CAD proporcional al papel. A1 necesita unas 450 letras,
                # A4 unas 55, para que unos pocos rótulos de un raster no pasen por texto útil.
                # Por encima de A1 no crece: un A0 de un paquete mecánico, casi todo dibujo,
                # trae 170-210 palabras de texto real y no es un plano sin texto.
                minimum = max(20, min(SPARSE_TEXT_MAX, round(page.width * page.height * 450 / A1)))
                if characters < minimum:
                    bundle.sparse_pages.append(page.page_number)
                if not rows:
                    bundle.warnings.append(
                        f"Página {page.page_number}: sin texto; necesita OCR/visión"
                    )
                for row in rows:
                    # Separar columnas que comparten una misma línea base: en un plano, un hueco de
                    # más de 12 pt (unos cuatro espacios) es un cambio de celda o de bloque.
                    groups = [[]]
                    for char in sorted(row["chars"], key=lambda c: c["x0"]):
                        if groups[-1] and char["x0"] - groups[-1][-1]["x1"] > COLUMN_GAP_PT:
                            groups.append([])
                        groups[-1].append(char)
                    for group in groups:
                        parts = []
                        for i, char in enumerate(group):
                            if i and char["x0"] - group[i - 1]["x1"] > 1.0:
                                parts.append(" ")
                            parts.append(char["text"])
                        text = "".join(parts).strip()
                        if not text:
                            continue
                        raw = (
                            min(c["x0"] for c in group) / page.width,
                            min(c["top"] for c in group) / page.height,
                            max(c["x1"] for c in group) / page.width,
                            max(c["bottom"] for c in group) / page.height,
                        )
                        bbox = _clip_bbox(raw)
                        if bbox is None:
                            dropped += 1
                            continue
                        clipped += bbox != raw
                        page_lines.append(
                            EvidenceLine(
                                text=text,
                                source=Source(
                                    document_id=document_id,
                                    page=page.page_number,
                                    locator=f"Texto de página {page.page_number}",
                                    bbox=bbox,
                                    confidence=0.75,
                                ),
                            )
                        )
                bundle.lines.extend(_merge_rotated(page_lines))
                if dropped:
                    bundle.warnings.append(
                        f"Página {page.page_number}: {dropped} texto(s) fuera de la página, "
                        "descartado(s)"
                    )
                if clipped:
                    bundle.warnings.append(
                        f"Página {page.page_number}: {clipped} texto(s) recortado(s) al borde"
                    )
                page.close()
        _read_drawing_revision(bundle)
    elif suffix == ".xlsx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(f.file_size for f in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Libro demasiado grande al descomprimir")
        workbook = load_workbook(
            io.BytesIO(data), read_only=True, data_only=False, keep_links=False
        )
        try:
            total = 0
            for sheet in workbook:
                if sheet.max_row * sheet.max_column > 20000:
                    raise ValueError("Límite de la base: 20.000 celdas por hoja")
                for row in sheet.iter_rows():
                    cells = [c for c in row if c.value is not None]
                    total += len(cells)
                    if total > 50000:
                        raise ValueError("Límite de la base: 50.000 celdas por libro")
                    if not cells:
                        continue
                    if any(c.data_type == "f" for c in cells):
                        bundle.warnings.append(f"{sheet.title}!{cells[0].row}: fórmula sin evaluar")
                        continue
                    values = [str(c.value) for c in cells]
                    if len(values) > 2 and values[-1] == "1":
                        values = values[:-1]
                    text = f"{values[0]} = {' '.join(values[1:])}" if len(values) > 1 else values[0]
                    location = f"{cells[0].coordinate}:{cells[-1].coordinate}"
                    bundle.lines.append(
                        EvidenceLine(
                            text=text,
                            source=Source(
                                document_id=document_id,
                                sheet=sheet.title,
                                cell=location,
                                locator=f"{sheet.title}!{location}",
                                confidence=0.75,
                            ),
                        )
                    )
        finally:
            workbook.close()
    elif suffix in IMAGE_SUFFIXES:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            document.page_count = getattr(image, "n_frames", 1)
        bundle.warnings.append(
            "Imagen recibida: `trazia.pipeline.process` la convierte en PDF escaneado para el OCR"
        )
    elif suffix in (".xls", ".xlsm"):
        raise ValueError(
            f"{suffix} no se admite: hay que guardarlo como .xlsx (las macros no se ejecutan nunca)"
        )
    else:
        raise ValueError("Formato admitido: PDF, XLSX, PNG, JPEG o TIFF")
    return bundle


def _read_drawing_revision(bundle: Bundle) -> None:
    from .lectura.clasificar import revision_del_plano
    from .model import Tag

    value, evidence = revision_del_plano(bundle.lines)
    if value is not None and evidence is not None:
        bundle.document.drawing_revision = Tag(
            value=value,
            source=evidence.source.model_copy(
                update={"locator": evidence.text, "text_original": evidence.text}
            ),
        )


COLUMN_GAP_PT = 12


def _merge_rotated(lines: list[EvidenceLine]) -> list[EvidenceLine]:
    """Une los trozos de un texto girado 90° que pdfplumber entrega apilados.

    Una cota girada como «559 1/16"» llega en dos líneas estrechas, una encima de otra, separadas
    por el espacio. Se unen de arriba abajo con un espacio: el resultado conserva el orden de
    caracteres de pdfplumber (invertido), igual que una cota girada de un solo trozo.
    """
    if not lines:
        return lines

    def vertical(line: EvidenceLine) -> bool:
        x0, y0, x1, y1 = line.source.bbox
        return (y1 - y0) > 1.5 * (x1 - x0)

    pending = sorted(lines, key=lambda line: (line.source.bbox[0], line.source.bbox[1]))
    out: list[EvidenceLine] = []
    for line in pending:
        last = out[-1] if out else None
        if last is not None:
            a0, b0, a1, b1 = last.source.bbox
            x0, y0, x1, y1 = line.source.bbox
            same_column = abs(a0 - x0) < 0.003 and abs(a1 - x1) < 0.003 and (a1 - a0) < 0.015
            if same_column and 0 <= y0 - b1 < 0.006 and (vertical(last) or vertical(line)):
                bbox = (min(a0, x0), b0, max(a1, x1), max(b1, y1))
                out[-1] = EvidenceLine(
                    text=f"{last.text} {line.text}",
                    source=last.source.model_copy(update={"bbox": bbox}),
                )
                continue
        out.append(line)
    return out


def _clip_bbox(raw: tuple[float, float, float, float]) -> tuple | None:
    """Recorta una caja normalizada a la página; None si queda fuera del todo."""
    x0, y0, x1, y1 = (min(1.0, max(0.0, v)) for v in raw)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def render_evidence(
    data: bytes, filename: str, page: int = 1, bbox: tuple | None = None
) -> Image.Image:
    if Path(filename).suffix.lower() == ".pdf":
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if not 1 <= page <= len(pdf.pages):
                raise ValueError("Página fuera del documento")
            selected = pdf.pages[page - 1]
            image = selected.to_image(resolution=110)
            if bbox:
                x0, y0, x1, y1 = bbox
                image.draw_rect(
                    (
                        x0 * selected.width,
                        y0 * selected.height,
                        x1 * selected.width,
                        y1 * selected.height,
                    ),
                    stroke="orange",
                    fill=None,
                    stroke_width=3,
                )
            return image.annotated.copy()
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGB")

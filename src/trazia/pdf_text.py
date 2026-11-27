"""Texto y citas de CAD sin materializar su geometría vectorial."""

from pypdfium2 import PdfDocument, PdfiumError

from .ingest import EvidenceLine, _clip_bbox
from .model import Source
from .pdf_limits import PDFIUM_LOCK

MAX_CHARS_PER_PAGE = 80_000


def read_vector_lines(data: bytes, document_id: str) -> list[EvidenceLine]:
    lines = []
    try:
        with PDFIUM_LOCK, PdfDocument(data) as document:
            for number, page in enumerate(document, 1):
                left, bottom, right, top = page.get_bbox()
                width, height = right - left, top - bottom
                text = page.get_textpage()
                count = text.count_chars()
                if count > MAX_CHARS_PER_PAGE:
                    raise ValueError(f"Página {number}: demasiados caracteres de texto CAD")
                raw = text.get_text_range(0, count)
                # Algunos PDF contienen caracteres invisibles que PDFium omite al extraer
                # el texto. Conserva los índices de las cajas en ese caso.
                chars = (
                    list(raw)
                    if len(raw) == count
                    else [text.get_text_range(index, 1) or " " for index in range(count)]
                )
                start = 0
                for end, char in enumerate((*chars, "\n")):
                    if char not in ("\n", "\r"):
                        continue
                    indexes = [i for i in range(start, end) if chars[i].strip()]
                    value = "".join(chars[start:end]).strip()
                    start = end + 1
                    if not indexes:
                        continue
                    boxes = [text.get_charbox(i) for i in indexes]
                    bbox = _clip_bbox(
                        (
                            (min(box[0] for box in boxes) - left) / width,
                            (top - max(box[3] for box in boxes)) / height,
                            (max(box[2] for box in boxes) - left) / width,
                            (top - min(box[1] for box in boxes)) / height,
                        )
                    )
                    if bbox:
                        lines.append(
                            EvidenceLine(
                                text=value,
                                source=Source(
                                    document_id=document_id,
                                    page=number,
                                    bbox=bbox,
                                    locator=f"Texto CAD de página {number}",
                                    confidence=0.75,
                                ),
                            )
                        )
                text.close()
                page.close()
    except (OSError, PdfiumError) as error:
        raise ValueError("No se pudo leer la capa de texto CAD del PDF") from error
    return lines

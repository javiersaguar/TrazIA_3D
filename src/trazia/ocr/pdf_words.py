"""Expone las líneas OCR con las coordenadas de pdfplumber en puntos PDF."""

import argparse
import io
import json
from pathlib import Path

import pdfplumber

from .engine import DPI, ocr_pdf_lines


def lines_in_pdf_points(
    pdf: bytes,
    document_id: str,
    *,
    pages: list[int] | None = None,
    dpi: int = DPI,
    tiles: bool = False,
) -> dict[int, list[dict]]:
    """Conserva la caja y la confianza sin volver a ejecutar el OCR en páginas cacheadas."""
    output: dict[int, list[dict]] = {}
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        page_numbers = (
            list(range(1, len(document.pages) + 1)) if pages is None else list(dict.fromkeys(pages))
        )
        for number in page_numbers:
            if not 1 <= number <= len(document.pages):
                raise ValueError(f"Página fuera del documento: {number}")
            output[number] = []
        if not page_numbers:
            return output
        for line in ocr_pdf_lines(pdf, document_id, pages=page_numbers, dpi=dpi, tiles=tiles):
            source = line.source
            page = document.pages[source.page - 1]
            left, top, right, bottom = page.cropbox
            width, height = right - left, bottom - top
            x0, y0, x1, y1 = source.bbox
            output[source.page].append(
                {
                    "text": line.text,
                    "x0": left + x0 * width,
                    "top": top + y0 * height,
                    "x1": left + x1 * width,
                    "bottom": top + y1 * height,
                    "confidence": source.confidence,
                    "document_id": source.document_id,
                    "page": source.page,
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, action="append", dest="pages")
    parser.add_argument("--dpi", type=int, default=DPI)
    parser.add_argument("--tiles", action="store_true")
    args = parser.parse_args()
    rows = lines_in_pdf_points(
        args.pdf.read_bytes(), args.pdf.stem, pages=args.pages, dpi=args.dpi, tiles=args.tiles
    )
    print(json.dumps(rows, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

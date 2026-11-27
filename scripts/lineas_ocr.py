"""Comando compatible para consultar las líneas OCR en puntos PDF."""

from trazia.ocr.pdf_words import lines_in_pdf_points, main

__all__ = ["lines_in_pdf_points"]

if __name__ == "__main__":
    main()

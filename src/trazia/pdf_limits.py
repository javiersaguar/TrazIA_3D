"""Presupuesto de contenido vectorial antes de construir el layout del PDF."""

import zlib
from threading import Lock

from pdfminer.ascii85 import ascii85decode, asciihexdecode
from pdfminer.pdftypes import (
    LITERALS_ASCII85_DECODE,
    LITERALS_ASCIIHEX_DECODE,
    LITERALS_FLATE_DECODE,
    PDFStream,
    dict_value,
    resolve1,
)
from pdfminer.psparser import LIT

MAX_CONTENT_BYTES = 16 * 1024 * 1024
MAX_FORM_DEPTH = 24
# La cola de trabajos usa hilos y PDFium comparte estado nativo.
PDFIUM_LOCK = Lock()


def _stream_size(stream, remaining):
    data = stream.rawdata
    if data is None:
        size = len(stream.get_data())
        if size > remaining:
            raise ValueError("contenido vectorial descomprimido por encima del presupuesto")
        return size
    if len(data) > MAX_CONTENT_BYTES:
        raise ValueError("contenido vectorial codificado por encima del presupuesto")
    for name, _ in stream.get_filters():
        if name in LITERALS_FLATE_DECODE:
            decoder = zlib.decompressobj()
            data = decoder.decompress(data, remaining + 1)
            if decoder.unconsumed_tail or len(data) > remaining:
                raise ValueError("contenido vectorial descomprimido por encima del presupuesto")
        elif name in LITERALS_ASCII85_DECODE:
            data = ascii85decode(data)
        elif name in LITERALS_ASCIIHEX_DECODE:
            data = asciihexdecode(data)
        else:
            raise ValueError("filtro de contenido vectorial sin descompresión acotada")
    if len(data) > remaining:
        raise ValueError("contenido vectorial descomprimido por encima del presupuesto")
    return len(data)


def check_page_content(page, *, limit: int | None = None) -> int:
    """Rechaza páginas vectoriales densas antes de que pdfminer materialice sus objetos."""
    budget = MAX_CONTENT_BYTES if limit is None else limit
    remaining = budget
    seen = set()

    def add(stream):
        nonlocal remaining
        if isinstance(stream, PDFStream) and id(stream) not in seen:
            seen.add(id(stream))
            remaining -= _stream_size(stream, remaining)

    def forms(resources, depth=0):
        for ref in dict_value(resources.get("XObject", {})).values():
            obj = resolve1(ref)
            if not isinstance(obj, PDFStream) or id(obj) in seen:
                continue
            if resolve1(obj.get("Subtype")) == LIT("Form"):
                if depth >= MAX_FORM_DEPTH:
                    raise ValueError("demasiados niveles de formularios vectoriales")
                add(obj)
                forms(dict_value(obj.get("Resources", {})), depth + 1)

    try:
        for stream in page.page_obj.contents:
            add(resolve1(stream))
        forms(page.page_obj.resources)
    except (ValueError, zlib.error) as error:
        raise ValueError(
            f"Página {page.page_number}: {error}. "
            "Divide el plano o exporta esta lámina con menos detalle."
        ) from None
    return budget - remaining

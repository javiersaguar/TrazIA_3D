"""Búsqueda por palabras en la documentación del producto, sin embeddings.

Se indexan por secciones unas guías concretas del repositorio. Los informes internos de agentes y
los planes no entran: la respuesta debe salir de documentación pensada para el usuario o el jurado.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .tools import stems

ROOT = Path(__file__).resolve().parents[3]
SOURCES = (
    "docs/AYUDA_APP.md",
    "README.md",
    "docs/FLUJO_IA.md",
    "docs/PREGUNTAS_JURADO.md",
    "docs/ESTUDIO.md",
    "docs/EDICION_ASISTIDA.md",
    "docs/DATA_CONTRACT.md",
    "docs/MARCAS_REVISION.md",
    "docs/AUDITORIA_REVISION.md",
    "docs/APRENDIZAJE_APROBADO.md",
    "docs/BIBLIOTECA_INDUSTRIAL.md",
    "docs/PROYECTOS_PROCESO.md",
    "docs/BASE_DEL_RETO.md",
    "docs/NORMALIZACION.md",
    "docs/EXPORTACION_CAMPOS.md",
)
# Palabras que aparecen en casi cualquier pregunta y no distinguen una sección de otra.
COMMON = stems(
    "que como cual cuales donde cuando para por con una uno los las del este esta esto eso ese "
    "funciona hace puedo puede hacer quiero sirve tiene hay son sus mas pero"
)
CHUNK = 900
STRATEGIES = {"a": "vision", "b": "reglas", "c": "recuperacion rag", "d": "hibrido"}


@dataclass(frozen=True)
class Section:
    source: str
    title: str
    text: str
    terms: frozenset[str]
    title_terms: frozenset[str]
    length: int


def _plain(markdown):
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`>|]+", " ", text)
    text = re.sub(r"^\s*[-+]\s+", "· ", text, flags=re.M)
    return re.sub(r"[ \t]+", " ", text).strip()


def _split(source, markdown):
    heads = []
    body = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,4})\s+(.*)", line)
        if match:
            if body:
                yield heads[:], "\n".join(body)
            level = len(match.group(1))
            heads = [*heads[: level - 1], match.group(2).strip()]
            body = []
        else:
            body.append(line)
    if body:
        yield heads[:], "\n".join(body)


def _chunks(text):
    parts, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) > CHUNK:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        parts.append(current)
    return parts


@lru_cache(maxsize=4)
def _index(root, signature):
    sections = []
    for source in SOURCES:
        path = Path(root) / source
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for heads, body in _split(source, markdown):
            title = " · ".join(heads[-2:]) or source
            for text in _chunks(_plain(body)):
                if len(text) < 60:
                    continue
                terms = stems(text)
                sections.append(
                    Section(
                        source,
                        title,
                        text,
                        frozenset(terms),
                        # Solo el título propio: el del documento se repite en todas sus secciones.
                        frozenset(stems(heads[-1] if heads else "")),
                        len(text.split()),
                    )
                )
    return tuple(sections)


def _signature(root):
    parts = []
    for source in SOURCES:
        try:
            stat = (Path(root) / source).stat()
            parts.append(f"{source}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            parts.append(f"{source}:-")
    return "|".join(parts)


def sections(root=ROOT):
    return _index(str(root), _signature(root))


def digest(root=ROOT):
    """Huella del contenido indexado, para invalidar respuestas cacheadas."""
    sha = hashlib.sha256()
    for item in sections(root):
        sha.update(f"{item.source}\n{item.title}\n{item.text}\n".encode())
    return sha.hexdigest()


@dataclass(frozen=True)
class Hit:
    section: Section
    score: float
    coverage: float


def terms(question):
    """Raíces de la pregunta que distinguen unas secciones de otras."""
    query = stems(question) - COMMON
    # «Estrategia D» tiene una sola letra: se busca también por su nombre.
    for letter in re.findall(r"\bestrategias?\s+([abcd])\b", question.casefold()):
        query |= stems(STRATEGIES[letter])
    return query


def search(question, *, root=ROOT, limit=3, prefer=None):
    """BM25 sobre raíces de palabras, con más peso si la sección se titula con ellas.

    `prefer` da ventaja a una guía concreta, como la de uso para preguntas de ayuda.
    """
    index = sections(root)
    query = terms(question)
    if not query or not index:
        return []
    count = len(index)
    average = sum(item.length for item in index) / count
    frequency = {term: sum(term in item.terms for item in index) for term in query}
    hits = []
    for item in index:
        matched = query & item.terms
        if not matched:
            continue
        score = 0.0
        for term in matched:
            idf = math.log(1 + (count - frequency[term] + 0.5) / (frequency[term] + 0.5))
            norm = 1.2 * (0.25 + 0.75 * item.length / average)
            score += idf * 2.2 / (1 + norm)
            if term in item.title_terms:
                score += idf
        if prefer and item.source == prefer:
            score *= 1.6
        hits.append(Hit(item, score, len(matched) / len(query)))
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]

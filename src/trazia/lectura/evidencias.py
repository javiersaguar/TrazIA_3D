"""Cotas cotejadas localmente, asociadas a la huella exacta de su plano."""

from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter

from ..extraction import Alternative, Candidate
from ..model import SHA256, BBox, Model, Source
from . import leer


class LecturaCotejada(Model):
    path: str = Field(
        pattern=r"^(?:diameter|height|head_depth|skirt_(?:height|thickness)|"
        r"(?:attributes|horizontal|tank|column\.sections)\.[A-Za-z0-9_.-]+)$"
    )
    value: float | str
    unit: str = Field(min_length=1)
    page: int = Field(ge=1)
    bbox: BBox
    text: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    state: Literal["candidate", "assumed"] = "candidate"
    channel: Literal["cota", "geometria", "tabla"] = "cota"


def cargar(path: Path) -> dict[str, list[LecturaCotejada]]:
    schema = TypeAdapter(dict[SHA256, list[LecturaCotejada]])
    data = schema.validate_json(path.read_bytes())
    for fields in data.values():
        if len({field.path for field in fields}) != len(fields):
            raise ValueError("Cada fuente puede aportar una sola lectura cotejada por campo")
    return data


def incorporar(documentos, lecturas, evidencias):
    seleccionadas = {}
    for bundle in documentos:
        doc = bundle.document
        for field in evidencias.get(doc.sha256, ()):
            if bundle.media_type != "pdf" or doc.page_count is None or field.page > doc.page_count:
                raise ValueError("La página cotejada no pertenece al PDF registrado")
            if field.path in seleccionadas:
                raise ValueError(f"Más de una evidencia cotejada para {field.path} en la revisión")
            alternas = [
                Alternative(value=c.value, unit=c.unit, source=c.source, channel=c.channel)
                for c in lecturas
                if c.path == field.path and (c.value, c.unit) != (field.value, field.unit)
            ]
            seleccionadas[field.path] = Candidate(
                path=field.path,
                value=field.value,
                unit=field.unit,
                source=Source(
                    document_id=doc.id,
                    page=field.page,
                    bbox=field.bbox,
                    locator=field.text,
                    text_original=field.text,
                    confidence=0.75 if field.state == "assumed" else 0.96,
                    channel=field.channel,
                    rule="ga.cotejo_local",
                ),
                channel=field.channel,
                state=field.state,
                explanation=field.explanation,
                alternatives=alternas,
            )
        if doc.sha256 in evidencias:
            bundle.warnings.append(
                f"{doc.id}: cotas de geometría cotejadas por huella del original."
            )
    return [field for field in lecturas if field.path not in seleccionadas] + list(
        seleccionadas.values()
    )


def leer_con_evidencias(documentos, *, evidencias, **options):
    return incorporar(documentos, leer(documentos, **options), evidencias)

"""Contextos del copilot: revisiones con evidencia, complejos y catálogo publicado."""

import asyncio
import hashlib
import json
import re
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from sqlmodel import Session, select

from trazia.copilot import router as copilot_router
from trazia.copilot.grounded import fact, fold, respond, words
from trazia.copilot.models import CopilotAnswer
from trazia.model import Model
from trazia.process_catalog.process_projects import PROJECTS, edit_fields
from trazia.store import RevisionRecord
from trazia.store.accounts import CatalogueGroup, PublishedDesign

router = APIRouter(prefix="/copiloto")
PROCESS = {project.id: project for project in PROJECTS}


class ContextInput(Model):
    kind: Literal["project", "process", "catalogue"]
    id: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=1, max_length=2000)
    revision: Literal["A", "B"] = "A"


class ProcessIntent(Model):
    project_id: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=2000)


@router.get("/contexts")
def contexts(request: Request):
    with Session(request.app.state.store.engine) as session:
        rows = session.exec(
            select(
                RevisionRecord.id,
                RevisionRecord.project_id,
                RevisionRecord.equipment_id,
                RevisionRecord.tag,
                RevisionRecord.revision,
            ).order_by(RevisionRecord.project_id, RevisionRecord.tag, RevisionRecord.revision)
        ).all()
        names = {
            group.id: group.name
            for group in session.exec(
                select(CatalogueGroup).where(CatalogueGroup.kind == "project")
            )
        }
        projects = list(session.exec(select(PublishedDesign.project).distinct()))
    previous = {}
    identities = {
        (project, equipment, revision): identity
        for identity, project, equipment, _, revision in rows
    }
    revisions = []
    for identity, project, equipment, tag, revision in rows:
        key = (project, equipment)
        parent = revision.rpartition("-D")[0] if "-D" in revision else None
        parent_id = identities.get((*key, parent)) if parent else None
        revisions.append(
            dict(
                kind="revision",
                id=identity,
                project=project,
                equipment=equipment,
                tag=tag,
                revision=revision,
                previous_id=parent_id or previous.get(key),
                label=f"{tag} · rev. {revision}",
            )
        )
        if not parent:
            previous[key] = identity
    return [
        *[
            dict(kind="project", id=project, project=project, label="Inventario del proyecto")
            for project in sorted({item["project"] for item in revisions})
        ],
        *revisions,
        *[
            dict(kind="process", id=project.id, project="Complejos sintéticos", label=project.name)
            for project in PROJECTS
        ],
        *[
            dict(
                kind="catalogue",
                id=project,
                project="Catálogo publicado",
                label=names.get(project, project),
            )
            for project in sorted(set(projects) | names.keys())
        ],
    ]


def process_facts(project, revision, question):
    tokens = words(question)
    terms = "inventario resumen equipos lineas tuberias entorno proceso plataforma altura"
    facts = [
        fact(
            project.id,
            "project",
            "GA de implantación sintético",
            f"{project.name} ({project.code}), rev. {revision}: {project.description} "
            f"Entorno: {project.setting}. Cota de la plataforma: {project.deck:g} m. "
            f"{len(project.equipment)} equipos y {len(project.lines)} líneas.",
            terms=terms,
        )
    ]
    changes = {(item.tag, item.property): item.after for item in project.changes if revision == "B"}
    mentions = set(re.findall(r"\b[A-Za-z]{1,7}-\d+\b", question.upper()))
    if mentions - {item.tag.upper() for item in (*project.equipment, *project.lines)}:
        return []
    if tokens & {"cambio", "cambios", "cambia", "diferencias", "respecto"}:
        return [
            fact(
                project.id,
                change.tag,
                f"Cambios A → B · {change.tag}",
                f"{change.tag} · {change.label}: "
                f"{change.before:g} → {change.after:g} {change.unit}.",
                terms="cambio cambios diferencias",
                kind="change",
            )
            for change in project.changes
            if not mentions or change.tag.upper() in mentions
        ]
    if mentions:
        facts = []
    for item in project.equipment:
        if mentions and item.tag.upper() not in mentions:
            continue
        length, width, height = (
            changes.get((item.tag, key), value)
            for key, value in zip(("length", "width", "height"), item.size, strict=True)
        )
        facts.append(
            fact(
                project.id,
                item.tag,
                f"Hoja de equipo sintética · {item.tag}",
                f"{item.tag} · {item.name}, rev. {revision}. Servicio: {item.service}. "
                f"Largo {length:g} m, ancho {width:g} m y alto {height:g} m.",
                terms=f"{item.name} {item.service} longitud largo ancho cota altura dimensiones",
            )
        )
    for line in project.lines:
        if mentions and line.tag.upper() not in mentions:
            continue
        dn = changes.get((line.tag, "dn"), line.dn)
        height = changes.get((line.tag, "rack_z"), line.rack_z)
        facts.append(
            fact(
                project.id,
                line.tag,
                f"Lista de líneas sintética · {line.tag}",
                f"{line.tag}, rev. {revision}: {line.start} → {line.end}, {line.fluid}. "
                f"DN {dn:g} mm. Cota en rack: {height:g} m.",
                terms=f"{line.fluid} tuberia conexiones conecta diametro dn rack cota",
            )
        )
    return facts


CONTEXT_LABELS = {
    "project": "el proyecto {}",
    "process": "el complejo de proceso {}",
    "catalogue": "el catálogo publicado de {}",
}


@router.post("/project", response_model=CopilotAnswer)
async def ask_project(request: Request, body: ContextInput):
    if not body.question.strip():
        raise HTTPException(422, "Escribe una pregunta")
    question = body.question.strip()
    intent = copilot_router.classify(question)
    scope = {
        "identity": body.id,
        "version": 1,
        "fingerprint": hashlib.sha256(f"{body.kind}:{body.id}".encode()).hexdigest(),
        "dataset": "synthetic" if body.kind == "process" else "real",
    }
    try:
        async with asyncio.timeout(14), request.app.state.copilot_limit:
            if intent == "charla":
                label = CONTEXT_LABELS[body.kind].format(body.id)
                return await copilot_router.chat(question, scope=scope, context=label)
            if intent in ("ayuda", "producto"):
                answer = await copilot_router.from_docs(question, scope=scope, intent=intent)
                if answer is not None:
                    return answer
    except TimeoutError as error:
        raise HTTPException(503, "El copiloto ha agotado el tiempo de consulta") from error
    answer = await _answer_context(request, body)
    if answer.abstained and intent != "datos":
        try:
            async with asyncio.timeout(10), request.app.state.copilot_limit:
                docs = await copilot_router.from_docs(
                    question, scope=scope, intent=intent, minimum=0.75
                )
        except TimeoutError:
            docs = None
        if docs is not None:
            return docs
    return answer


async def _answer_context(request: Request, body: ContextInput):
    if body.kind == "process":
        project = PROCESS.get(body.id)
        if project is None:
            raise HTTPException(404, "No existe ese complejo")
        facts = process_facts(project, body.revision, body.question)
        digest = hashlib.sha256(json.dumps(asdict(project), sort_keys=True).encode()).hexdigest()
        dataset = "synthetic"
    elif body.kind == "catalogue":
        with Session(request.app.state.store.engine) as session:
            rows = session.exec(
                select(PublishedDesign)
                .where(PublishedDesign.project == body.id)
                .order_by(PublishedDesign.published_at.desc())
                .limit(200)
            ).all()
        facts = [
            fact(
                body.id,
                row.id,
                "Ficha de Documentos",
                f"{row.name} · archivo {row.filename} · {row.size} bytes · familia {row.family}.",
                terms=f"{row.name} {row.filename} archivo archivos documento documentos "
                "publicado diseños inventario lista",
            )
            for row in rows
        ]
        dataset = "real"  # La publicación de un archivo no certifica que sea sintético.
    else:
        with Session(request.app.state.store.engine) as session:
            rows = session.exec(
                select(RevisionRecord.tag, RevisionRecord.revision)
                .where(RevisionRecord.project_id == body.id)
                .order_by(RevisionRecord.tag, RevisionRecord.revision)
            ).all()
        if not rows:
            raise HTTPException(404, "No existe ese proyecto")
        equipment = {}
        for tag, revision in rows:
            equipment.setdefault(tag, []).append(revision)
        facts = [
            fact(
                body.id,
                tag,
                "Índice de revisiones",
                f"{body.id} · {tag} · revisiones: {', '.join(labels)}.",
                terms=f"{tag} equipos inventario revisiones lista contiene",
            )
            for tag, labels in equipment.items()
        ]
        dataset = "real"  # Puede agrupar equipos de procedencias distintas.
    if body.kind != "process":
        digest = hashlib.sha256("".join(item.citation.id for item in facts).encode()).hexdigest()
    try:
        async with asyncio.timeout(12), request.app.state.copilot_limit:
            return await respond(
                facts,
                body.question.strip(),
                identity=body.id,
                version=1,
                fingerprint=digest,
                dataset=dataset,
            )
    except TimeoutError as error:
        raise HTTPException(503, "El copiloto ha agotado el tiempo de consulta") from error


PROCESS_FIELDS = {
    "length": r"largo|longitud|virola",
    "width": r"ancho|anchura|diametro",
    "height": r"alto|altura",
    "dn": r"dn|diametro",
    "rack_z": r"cota|elevacion|altura",
}


@router.post("/process-drafts")
def process_draft(body: ProcessIntent):
    from trazia.design.intent import FORBIDDEN, UNITS
    from trazia.design.quantities_es import digits

    project = PROCESS.get(body.project_id)
    if project is None:
        raise HTTPException(404, "No existe ese complejo")
    adjustments, questions = [], []
    clauses = re.split(r";|\s+y\s+", digits(fold(body.text)))
    if len(clauses) > 8:
        return {"adjustments": [], "questions": ["Un borrador admite hasta ocho cambios."]}
    for clause in clauses:
        match = re.search(r"\b[a-z]{1,7}-\d+\b", clause)
        tag = match[0].upper() if match else ""
        allowed = edit_fields(project, tag)
        if (
            not allowed
            or re.search(r"\b(?:no|excepto|salvo)\b", clause)
            or any(re.search(pattern, clause) for pattern, _ in FORBIDDEN)
        ):
            questions.append("Indica un TAG del complejo y un cambio de borrador permitido.")
            continue
        fields = [key for key in allowed if re.search(rf"\b(?:{PROCESS_FIELDS[key]})\b", clause)]
        number = re.search(
            r"\b(?:a|hasta|sea de|quede en|mida)\s+(\d+(?:[.,]\d+)?)\s*"
            r"(mm|cm|m|milimetros?|centimetros?|metros?)\b",
            clause,
        )
        if len(fields) != 1 or number is None or len(re.findall(r"\d+(?:[.,]\d+)?", clause)) != 2:
            questions.append(
                f"Para {tag}, indica un parámetro y valor final con unidad, "
                "por ejemplo «altura a 8 m»."
            )
            continue
        field = fields[0]
        value = (
            float(number[1].replace(",", ".")) * {"mm": 0.001, "cm": 0.01, "m": 1}[UNITS[number[2]]]
        )
        if field == "dn":
            value = round(value * 1000, 8)
        bounds = allowed[field]
        if not bounds["min"] <= value <= bounds["max"] or (
            field == "dn" and not value.is_integer()
        ):
            unit = "mm" if field == "dn" else "m"
            questions.append(
                f"{tag}: usa un valor entre {bounds['min']:g} y {bounds['max']:g} {unit}."
            )
            continue
        adjustments.append({"tag": tag, "field": field, "value": value})
    if questions or len({(item["tag"], item["field"]) for item in adjustments}) != len(adjustments):
        return {
            "adjustments": [],
            "questions": questions or ["Indica un solo valor final por parámetro."],
        }
    return {"adjustments": adjustments, "questions": []}

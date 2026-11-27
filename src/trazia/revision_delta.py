"""Adapta el delta del modelo al contrato de revisión por marca."""

from .extractors.revision_marks import RevisionMark, covers
from .families.change_detection import equal_value
from .families.revision_marks import locations
from .ingest import dataset_filename
from .lectura.cambios import notacion_espesor_comparable
from .model import Revision


def _component_field(path: str) -> tuple[str, str]:
    for prefix in ("nozzles.", "shell.courses.", "column.sections."):
        if path.startswith(prefix):
            mark, _, field = path.removeprefix(prefix).partition(".")
            return mark, field
    return "", ""


def _ga_schedule(revision):
    ga = []
    for doc in revision.documents:
        name = dataset_filename(doc.filename)
        if name and name.kind == "GA":
            ga.append(((name.tag.upper(), name.sheet), doc.nozzle_schedule))
        elif doc.nozzle_schedule is not None:
            # Lectura solo almacena el inventario después de identificar un GA.
            # En un nombre libre, la tabla y el tag del equipo dan la misma asociación.
            ga.append(((revision.equipment.tag.value.upper(), None), doc.nozzle_schedule))
    return ga[0] if len(ga) == 1 and ga[0][1] is not None else None


def _schedule_change(path, operation, before, after, old_source, new_source):
    return {
        "path": path,
        "operation": operation,
        "before": before,
        "after": after,
        "before_source": old_source.model_dump(mode="json"),
        "after_source": new_source.model_dump(mode="json"),
        "affects_geometry": False,
        "source_scope": "nozzle_schedule",
    }


def nozzle_schedule_changes(before, after, *, tolerances=None):
    """Compara filas citadas de la misma tabla de GA, aunque falte su geometría."""
    old_ga, new_ga = _ga_schedule(before), _ga_schedule(after)
    if not old_ga or not new_ga or old_ga[0] != new_ga[0]:
        return []
    old, new = old_ga[1], new_ga[1]
    closed = old.complete and new.complete
    pending = set(before.unplaced_nozzles) | set(after.unplaced_nozzles)
    old_placed = {n.id for n in before.equipment.nozzles}
    new_placed = {n.id for n in after.equipment.nozzles}
    changes = []
    for mark in sorted(pending & (old.rows.keys() | new.rows.keys())):
        left, right = old.rows.get(mark), new.rows.get(mark)
        path = f"nozzles.{mark}"
        if closed and left is None and mark not in old_placed:
            changes.append(
                _schedule_change(
                    path, "added", None, {"value": mark, "unit": "1"}, old.source, right.source
                )
            )
        elif closed and right is None and mark not in new_placed:
            changes.append(
                _schedule_change(
                    path, "removed", {"value": mark, "unit": "1"}, None, left.source, new.source
                )
            )
        elif left is not None and right is not None:
            for key in sorted(left.fields.keys() & right.fields.keys()):
                a, b = left.fields[key], right.fields[key]
                if key == "projection" and not _same_projection_basis(left.fields, right.fields):
                    continue
                if key == "projection_basis" and "desconocida" in (a.value, b.value):
                    continue
                if not equal_value(a, b, f"{path}.{key}", tolerances=tolerances):
                    change = _schedule_change(
                        f"{path}.{key}",
                        "modified",
                        {"value": a.value, "unit": a.unit},
                        {"value": b.value, "unit": b.unit},
                        a.source,
                        b.source,
                    )
                    if key == "schedule" and not notacion_espesor_comparable(a.value, b.value):
                        change["motivo"] = "notacion_de_espesor"
                    changes.append(change)
    return changes


def _same_projection_basis(left, right):
    a, b = left.get("projection_basis"), right.get("projection_basis")
    return a is not None and b is not None and a.value == b.value and a.value != "desconocida"


def by_id(report: dict, before: Revision, after: Revision) -> dict:
    old = {nozzle.id for nozzle in before.equipment.nozzles}
    new = {nozzle.id for nozzle in after.equipment.nozzles}
    unresolved = set(report["unplaced_nozzles"])
    renamed = {
        change["before"]["value"]: change["after"]["value"]
        for change in report["changes"]
        if change["operation"] == "renamed" and change["path"].startswith("nozzles.")
    }
    covered = {renamed.get(mark, mark) for mark in old}
    added = new - covered - unresolved
    removed = old - new - renamed.keys() - unresolved
    from .lectura.cambios import grupos_raiz

    grupos = grupos_raiz(old, new)
    if grupos:
        added -= set(grupos)
        removed -= {hija for hijas in grupos.values() for hija in hijas}
    changed = {}
    unmarked = []
    membership_sources = {}
    for change in report["changes"]:
        path = change["path"]
        if change.get("source_scope") == "nozzle_schedule" and path.count(".") == 1:
            _, mark = path.split(".")
            (added if change["operation"] == "added" else removed).add(mark)
            membership_sources[mark] = {
                "antes": change["before_source"],
                "despues": change["after_source"],
            }
            continue
        mark, field = _component_field(change["path"])
        if not field:
            unmarked.append(change)
            continue
        if mark in added or mark in removed:
            continue
        entry = changed.setdefault(mark, {"citas": [], "citas_por_campo": {}})
        entry[field] = [
            value.get("value") if value else None for value in (change["before"], change["after"])
        ]
        citations = [change["before_source"], change["after_source"]]
        entry["citas_por_campo"][field] = citations
        for citation in citations:
            if citation is not None and citation not in entry["citas"]:
                entry["citas"].append(citation)

    grouped = {
        "altas": sorted(added),
        "bajas": sorted(removed),
        "cambiados": changed,
        "sin_marca": unmarked,
        "delta_del_plano": _drawing_labels(report, after),
    }
    if membership_sources:
        grouped["citas_altas_bajas"] = membership_sources
    return grouped


def _drawing_labels(report: dict, revision: Revision) -> dict[str, str]:
    marked = report["layers"]["revision_marks"]["documents"]
    labels: dict[str, set[str]] = {}
    for document in marked:
        usable = [
            RevisionMark("delta", mark["page"], tuple(mark["bbox"]), mark["label"], mark["method"])
            for mark in document["marks"]
            if mark["kind"] == "delta"
            and mark["label"]
            and mark["page"] not in document["unread_pages"]
        ]
        if not usable:
            continue
        for change in locations(revision, report["changes"]):
            tag, field = _component_field(change["path"])
            if not field:
                continue
            for hit in change["locations"]:
                if hit["document_id"] == document["document_id"]:
                    for mark in usable:
                        if covers(mark, hit["page"], hit["bbox"]):
                            labels.setdefault(tag, set()).add(mark.label)
    return {tag: next(iter(values)) for tag, values in labels.items() if len(values) == 1}

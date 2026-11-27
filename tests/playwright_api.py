"""Arranca una API de pruebas con originales sintéticos y revisiones independientes."""

import os
from pathlib import Path

import uvicorn
from sqlmodel import Session
from test_plataforma_families import family_data

from trazia.api.app import create_app
from trazia.api.repository import revision_id, seed_demo
from trazia.model import Revision, load_revision
from trazia.store import RevisionRecord, Store


def seed_for_browser(data: Path, root: Path):
    store = Store(data)
    try:
        seed_demo(store, root)
        copies = {
            "ENSAYO-APROBACION": ("b",),
            "ENSAYO-DISENO": ("a", "b"),
            "ENSAYO-VOZ": ("a", "b"),
        }
        models = []
        for project, revisions in copies.items():
            for suffix in revisions:
                model = load_revision(root / "examples" / f"vessel_rev_{suffix}.json")
                model.project_id = project
                models.append(model)
        horizontal = Revision.model_validate(family_data("horizontal_vessel"))
        store.put(b"synthetic-family-parameters")
        with Session(store.engine) as session:
            for model in [*models, horizontal]:
                session.merge(
                    RevisionRecord(
                        id=revision_id(model),
                        project_id=model.project_id,
                        equipment_id=model.equipment.id,
                        tag=model.equipment.tag.value,
                        revision=model.revision,
                        payload=model.model_dump_json(),
                    )
                )
            session.commit()
    finally:
        store.close()


if __name__ == "__main__":
    root = Path(os.environ["TRAZIA_ROOT"])
    data = Path(os.environ["TRAZIA_DATA"]).resolve()
    if not data.is_relative_to(root.resolve() / "generated") or not data.name.startswith(
        "e2e-api-"
    ):
        raise ValueError("La API de pruebas requiere un almacén e2e nuevo dentro de generated.")
    if os.getenv("TRAZIA_AUTH") == "0":
        seed_for_browser(data, root)
    uvicorn.run(
        create_app(root=root, data_root=data), host="127.0.0.1", port=int(os.environ["TRAZIA_PORT"])
    )

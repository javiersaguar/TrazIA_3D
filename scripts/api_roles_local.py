"""API de la vista previa local. Reutiliza datos y sincroniza el acceso de Javier."""

import argparse
import os
from pathlib import Path

import uvicorn
from sqlmodel import Session, select

from trazia.api.accounts import seed_accounts, sync_local_owner_password
from trazia.api.app import create_app
from trazia.store import RevisionRecord, Store

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "generated" / "roles-local" / "datos"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archivo", type=Path, required=True, help="Archivo de contraseña habitual."
    )
    parser.add_argument("--lote", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--puerto", type=int, default=8044)
    parser.add_argument("--puerto-web", type=int, default=3044)
    parser.add_argument("--solo-acceso", action="store_true", help="Corrige el acceso y termina.")
    args = parser.parse_args()
    if args.lote and not args.dataset:
        parser.error("Indica también --dataset para comprobar los originales del lote.")
    os.environ["TRAZIA_ADMIN_PASSWORD_FILE"] = str(args.archivo.resolve(strict=True))
    os.environ["TRAZIA_AUTH"] = "1"
    os.environ["TRAZIA_AUTH_COOKIE_SECURE"] = "0"
    os.environ["TRAZIA_DATABASE_URL"] = ""
    os.environ["TRAZIA_CORS_ORIGINS"] = (
        f"http://127.0.0.1:{args.puerto_web},http://localhost:{args.puerto_web}"
    )
    os.environ["TRAZIA_LOTE"] = str(args.lote.resolve(strict=True)) if args.lote else ""
    if args.dataset:
        os.environ["TRAZIA_DATASET_DIR"] = str(args.dataset.resolve(strict=True))
    for variable, filename in (
        ("TRAZIA_CORRECTIONS_FILE", "correcciones.jsonl"),
        ("TRAZIA_REGISTRO_LLM", "modelos.jsonl"),
        ("TRAZIA_REGISTRO_ENVIOS", "envios.jsonl"),
    ):
        os.environ[variable] = str(DATA.parent / filename)
    store = Store(DATA)
    try:
        seed_accounts(store)
        changed = sync_local_owner_password(store)
        with Session(store.engine) as db:
            has_revisions = db.exec(select(RevisionRecord.id).limit(1)).first() is not None
    finally:
        store.close()
    print(
        "Acceso local de Javier actualizado." if changed else "Acceso local de Javier comprobado."
    )
    if not args.solo_acceso:
        uvicorn.run(
            create_app(root=ROOT, data_root=DATA, seed=bool(args.lote) or not has_revisions),
            host="127.0.0.1",
            port=args.puerto,
        )


if __name__ == "__main__":
    main()

"""Aprobación automática de los campos que no necesitan revisión humana.

Un campo se aprueba solo si cumple todo esto a la vez:

- está como candidato: ni en conflicto, ni descartado, ni supuesto por una regla;
- su confianza (calibrada cuando la hay) llega al umbral, 0,8 por defecto;
- el valor se ha encontrado escrito en el original (`grounded`);
- no tiene lecturas alternativas que discrepen.

En el lote del reto son, sobre todo, filas de la hoja de datos y de la tabla de boquillas
copiadas tal cual. El campo queda `accepted`, con una explicación que dice que la aprobación
fue automática, y la API deja una acción de auditoría a nombre de TrazIA. El revisor puede
revocarla devolviendo el campo a candidato (PATCH con `state="candidate"`).

`TRAZIA_AUTO_APROBACION` cambia el umbral (p. ej. `0.95`) o la apaga (`0`, `no`, `off`).
"""

import os

from trazia.model import Revision
from trazia.store import AuditRecord

UMBRAL = 0.8
ACTOR = "TrazIA · aprobación automática"
RUTA = "$auto_accept"
PREFIJO = "Aprobado automáticamente"


def umbral() -> float | None:
    valor = os.environ.get("TRAZIA_AUTO_APROBACION", "").strip().lower()
    if not valor:
        return UMBRAL
    if valor in ("0", "no", "off", "false"):
        return None
    numero = float(valor.replace(",", "."))
    if not 0 < numero <= 1:
        raise ValueError("TRAZIA_AUTO_APROBACION debe estar entre 0 y 1")
    return numero


def _coma(numero: float) -> str:
    return f"{numero:.2f}".replace(".", ",")


def aprobables(revision: Revision, limite: float) -> list[str]:
    return [
        path
        for path, campo in revision.traced_fields().items()
        if campo.state == "candidate"
        and campo.source.confidence >= limite
        and campo.source.grounded is True
        and not campo.alternatives
    ]


def aprobar(revision: Revision, limite: float) -> list[str]:
    """Aprueba en `revision` los campos fiables y devuelve sus rutas."""
    rutas = aprobables(revision, limite)
    campos = revision.traced_fields()
    for path in rutas:
        campo = campos[path]
        nota = (
            f"{PREFIJO}: confianza {_coma(campo.source.confidence)} ≥ {_coma(limite)} y valor "
            "encontrado en el original. Se puede revocar."
        )
        campo.state = "accepted"
        campo.explanation = f"{nota} {campo.explanation}" if campo.explanation else nota
    return rutas


def aprobar_al_guardar(identity: str, revision: Revision) -> tuple[Revision, AuditRecord | None]:
    """Aplica la aprobación automática a una revisión nueva.

    Devuelve la revisión que hay que guardar y la acción de auditoría que lo registra, que se
    añade a la sesión después del registro de la revisión. Sin nada que aprobar, la misma
    revisión y ninguna acción.
    """
    limite = umbral()
    if limite is None:
        return revision, None
    antes = revision.model_dump_json()
    copia = Revision.model_validate_json(antes)
    if not aprobar(copia, limite):
        return revision, None
    copia = Revision.model_validate_json(copia.model_dump_json())
    accion = AuditRecord(
        revision_id=identity,
        path=RUTA,
        actor=ACTOR,
        before_json=antes,
        after_json=copia.model_dump_json(),
    )
    return copia, accion

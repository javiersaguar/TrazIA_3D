"""Azimut supuesto de una boquilla cuando su revisión deja la orientación al cliente.

Algunos planos (BF-C-0003 rev1, «TO BE DEFINED BY CLIENT») traen la tabla de boquillas y sus
cotas, pero ningún azimut. Sin azimut una boquilla no se coloca en 3D. Si la revisión siguiente
del mismo equipo sí fija el azimut de esa marca, se usa como valor **supuesto**:

- estado `assumed`, regla `boquilla.azimut_de_revision_posterior` y confianza 0,5;
- la cita es la fila de la boquilla en el plano de esta revisión, que es lo que se sabe de ella;
- la explicación dice de qué documento y página sale el azimut, y que hay que verificarlo.

Solo actúa cuando la revisión no trae ningún azimut: si trae alguno, la orientación es suya.
"""

from collections.abc import Sequence

from ..extraction import Candidate

REGLA = "boquilla.azimut_de_revision_posterior"


def _marca(path: str) -> str | None:
    partes = path.split(".")
    return partes[1] if len(partes) == 3 and partes[0] == "nozzles" else None


# La cita del azimut supuesto sale de la fila de esta revisión, no del plano siguiente.
_CITA = ("diameter", "elevation", "size_nps", "projection", "service", "rating")


def _filas_boquilla(leidos: Sequence[Candidate]) -> dict[str, Candidate]:
    mejor: dict[str, tuple[int, Candidate]] = {}
    for candidato in leidos:
        marca = _marca(candidato.path)
        if marca is None:
            continue
        campo = candidato.path.rsplit(".", 1)[-1]
        if campo in {"azimuth", "bearing"}:
            continue
        orden = _CITA.index(campo) if campo in _CITA else len(_CITA)
        actual = mejor.get(marca)
        if actual is None or orden < actual[0]:
            mejor[marca] = (orden, candidato)
    return {marca: candidato for marca, (_, candidato) in mejor.items()}


def azimuts_supuestos(
    leidos: Sequence[Candidate], posteriores: Sequence[dict | Candidate]
) -> list[Candidate]:
    """Candidatos de azimut supuesto para las marcas de `leidos` que la revisión siguiente fija."""
    if any(c.path.startswith("nozzles.") and c.path.endswith(".azimuth") for c in leidos):
        return []
    azimuts = {}
    for c in posteriores:
        dato = c.model_dump(mode="json") if isinstance(c, Candidate) else c
        marca = _marca(dato.get("path", ""))
        if (
            marca
            and dato["path"].endswith(".azimuth")
            and isinstance(dato.get("value"), int | float)
        ):
            azimuts.setdefault(marca, dato)
    filas = _filas_boquilla(leidos)
    salida = []
    for marca, fila in sorted(filas.items()):
        otro = azimuts.get(marca)
        if marca is None or otro is None:
            continue
        cita = otro.get("source") or {}
        donde = cita.get("document_id", "la revisión siguiente")
        if cita.get("page"):
            donde += f", pág. {cita['page']}"
        salida.append(
            Candidate(
                path=f"nozzles.{marca}.azimuth",
                value=float(otro["value"]),
                unit="deg",
                source=fila.source.model_copy(
                    update={
                        "confidence": 0.5,
                        "confidence_raw": None,
                        "rule": REGLA,
                        "locator": f"{marca} · orientación pendiente en esta revisión",
                        "text_original": None,
                        "unit_original": None,
                    }
                ),
                channel=fila.channel,
                state="assumed",
                explanation=(
                    "Esta revisión deja la orientación al cliente; se supone el azimut "
                    f"{float(otro['value']):g}° que fija la revisión siguiente ({donde}). "
                    "A verificar."
                ),
            )
        )
    return salida

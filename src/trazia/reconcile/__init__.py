"""Reconciliación de candidatos (DEC-11).

Agrupa por campo. Si todas las lecturas coinciden, gana la de mayor confianza y las demás refuerzan.
Si no coinciden, también gana la de mayor confianza, pero el campo queda marcado como conflicto, con
las alternativas y una explicación en español: nunca se elige en silencio.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from ..extraction import Alternative, Candidate


@dataclass
class Resolution:
    chosen: list[Candidate]
    conflicts: list[str] = field(default_factory=list)  # rutas en conflicto
    warnings: list[str] = field(default_factory=list)


def _same(a: Candidate, b: Candidate) -> bool:
    if a.unit != b.unit:
        return False
    if isinstance(a.value, float) and isinstance(b.value, float):
        return abs(a.value - b.value) <= 1e-6
    return str(a.value).strip().upper() == str(b.value).strip().upper()


def _prioridad_geometrica(candidato: Candidate) -> bool:
    """La proyección y el NPS de la revisión se toman de su GA si las fuentes difieren.

    La hoja de datos es una sola para todas las revisiones; la tabla del GA es la de esa revisión.
    """
    return (
        candidato.path.startswith("nozzles.")
        and candidato.path.endswith((".projection", ".projection_basis", ".size_nps"))
        and candidato.channel in {"tabla", "cota"}
        and candidato.value != "desconocida"
    )


def resolve(candidates: list[Candidate]) -> Resolution:
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[c.path].append(c)
    out = Resolution(chosen=[])
    for path, group in groups.items():
        ranked = sorted(
            group, key=lambda c: (_prioridad_geometrica(c), c.source.confidence), reverse=True
        )
        best = ranked[0]
        disagreeing = [c for c in ranked[1:] if not _same(best, c)]
        agreeing = len(ranked) - 1 - len(disagreeing)
        update: dict = {}
        if disagreeing:
            update["state"] = "conflict"
            update["alternatives"] = [
                Alternative(value=c.value, unit=c.unit, source=c.source, channel=c.channel)
                for c in disagreeing
            ]
            update["explanation"] = (
                f"{len(disagreeing) + 1} lecturas distintas; se propone la de mayor confianza "
                f"({best.channel or 'sin canal'}) y queda para revisión."
            )
            if _prioridad_geometrica(best) and any(
                c.source.confidence > best.source.confidence for c in disagreeing
            ):
                update["explanation"] = (
                    "Se propone el valor citado en la tabla del GA de la revisión. "
                    "La discrepancia queda para revisión."
                )
            out.conflicts.append(path)
            out.warnings.append(f"Conflicto en {path}: {update['explanation']}")
        elif agreeing:
            update["explanation"] = f"{agreeing + 1} lecturas coinciden."
        out.chosen.append(best.model_copy(update=update) if update else best)
    return out

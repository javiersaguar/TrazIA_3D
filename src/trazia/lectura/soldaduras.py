"""Uniones soldadas deducidas de las piezas leídas (J6, sección 7.5 del plan).

Primera pasada: cada unión sale de las piezas que ya tienen cita (virolas de la lista de
materiales, fondos, tapa embridada y boquillas de la tabla). Lleva la cita de la pieza que
la justifica, una regla `soldadura.*` y una confianza baja, porque la línea de la costura no
se ha leído todavía en el alzado. La revisión las trata como `assumed` con su regla.

Rutas (interfaz 1): `welds.<ID>.{kind, joins, elevation_mm}`. El ID depende solo de lo que
une (`W:V01|V02`, `W:SHELL|HEAD_BOTTOM`, `W:N1|SHELL`), así que se conserva entre revisiones.
`elevation_mm` es la distancia axial desde la T.L. de referencia (la inferior en verticales y
la primera en horizontales) y solo se da cuando las cotas leídas la fijan.
"""

import re

from ..extraction import Candidate

CONFIANZA = 0.55
_VIROLA = re.compile(r"^shell\.courses\.(?P<pos>[^.]+)\.height$")
_TANQUE = re.compile(r"^tank\.courses\.(?P<n>\d+)\.(?:thickness|height)$")
_TABLA = (".size_nps", ".rating")


def _indice(candidatos) -> dict[str, Candidate]:
    rutas: dict[str, Candidate] = {}
    for c in candidatos:
        if c.path not in rutas or c.source.confidence > rutas[c.path].source.confidence:
            rutas[c.path] = c
    return rutas


def _dato(ident, campo, valor, unidad, base: Candidate, regla, explicacion) -> Candidate:
    fuente = base.source.model_copy(
        update={"confidence": min(CONFIANZA, base.source.confidence), "rule": regla}
    )
    return Candidate(
        path=f"welds.{ident}.{campo}",
        value=valor,
        unit=unidad,
        source=fuente,
        confidence_raw=fuente.confidence,
        explanation=explicacion,
    )


def _union(ident, tipo, une, base, regla, explicacion, cota=None) -> list[Candidate]:
    datos = [
        _dato(ident, "kind", tipo, "1", base, regla, explicacion),
        _dato(ident, "joins", "|".join(une), "1", base, regla, explicacion),
    ]
    if cota is not None:
        datos.append(_dato(ident, "elevation_mm", float(cota), "mm", base, regla, explicacion))
    return datos


def _valor(rutas, *claves):
    for clave in claves:
        if clave in rutas:
            return rutas[clave]
    return None


def _virolas(rutas) -> list[tuple[str, Candidate]]:
    virolas = [(m["pos"], c) for ruta, c in rutas.items() if (m := _VIROLA.match(ruta))]
    return sorted(
        virolas, key=lambda v: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", v[0])]
    )


def _cuerpo(rutas) -> list[Candidate]:
    """Virola–virola y virola–fondo."""
    datos: list[Candidate] = []
    virolas = _virolas(rutas)
    estacion = {pos: rutas.get(f"shell.courses.{pos}.station") for pos, _ in virolas}
    for (a, ca), (b, _cb) in zip(virolas, virolas[1:], strict=False):
        cota = estacion[b]
        datos += _union(
            f"W:{a}|{b}",
            "circumferential",
            (a, b),
            cota or ca,
            "soldadura.virola_virola",
            f"Las virolas {a} y {b} son consecutivas"
            + (" en la cadena de cotas." if cota else " en la lista de materiales."),
            cota.value if cota else None,
        )
    horizontal = _valor(rutas, "horizontal.diameter", "horizontal.length") is not None
    largo = _valor(rutas, "horizontal.length", "height")
    fondo = _valor(rutas, "horizontal.head_depth", "head_depth")
    # Sin diámetro leído, la lista de virolas también prueba que hay cuerpo.
    cuerpo = _valor(rutas, "horizontal.diameter", "diameter") or (virolas and virolas[0][1])
    if not cuerpo:
        return datos
    if horizontal:
        extremos = (("HEAD_LEFT", 0.0), ("HEAD_RIGHT", largo.value if largo else None))
    else:
        superior = (
            "BODY_FLANGE"
            if (c := rutas.get("attributes.upper_closure")) and c.value == "blind_flange"
            else "HEAD_TOP"
        )
        extremos = (("HEAD_BOTTOM", 0.0), (superior, largo.value if largo else None))
        faldilla = rutas.get("attributes.head_straight_flange")
        chapa = rutas.get("attributes.shell_height")
        if faldilla and chapa:
            # La virola (su desarrollo axial) empieza tras la faldilla recta del fondo.
            f = faldilla.value
            largo = chapa
            extremos = (("HEAD_BOTTOM", f), (superior, f + chapa.value))
    cadena = bool(virolas) and all(estacion.values())
    explicacion = "La virola termina en la T.L.; ahí se suelda el fondo o la brida del cuerpo."
    if cadena:
        # Con la cadena de tramos, el fondo se suelda tras su faldilla recta (S.F.), no en la T.L.
        primera, (ultima, c_ultima) = virolas[0][0], virolas[-1]
        fin = estacion[ultima].value + c_ultima.value
        extremos = ((extremos[0][0], estacion[primera].value), (extremos[1][0], fin))
        explicacion = "La cadena de tramos sitúa el extremo de la virola tras la faldilla recta."
    for pieza, cota in extremos:
        base = estacion[virolas[0][0]] if cadena else (largo if cota and largo else fondo or cuerpo)
        datos += _union(
            f"W:SHELL|{pieza}",
            "circumferential",
            ("SHELL", pieza),
            base,
            "soldadura.virola_fondo" if pieza.startswith("HEAD") else "soldadura.virola_brida",
            explicacion,
            cota,
        )
    return datos


def _tanque(rutas) -> list[Candidate]:
    anillos = sorted({int(m["n"]) for r in rutas if (m := _TANQUE.match(r))})
    datos: list[Candidate] = []
    for a, b in zip(anillos, anillos[1:], strict=False):
        base = rutas.get(f"tank.courses.{a}.thickness") or rutas.get(f"tank.courses.{a}.height")
        datos += _union(
            f"W:C{a}|C{b}",
            "circumferential",
            (f"C{a}", f"C{b}"),
            base,
            "soldadura.anillo_anillo",
            f"Los anillos {a} y {b} del tanque son consecutivos (el 1 es el inferior).",
        )
    if anillos:
        primero = rutas.get(f"tank.courses.{anillos[0]}.thickness")
        if primero:
            datos += _union(
                f"W:C{anillos[0]}|BOTTOM",
                "circumferential",
                (f"C{anillos[0]}", "BOTTOM"),
                primero,
                "soldadura.anillo_fondo",
                "El primer anillo se suelda al fondo del tanque.",
                0.0,
            )
    return datos


def _boquillas(rutas) -> list[Candidate]:
    marcas = sorted(
        {r.split(".")[1] for r in rutas if r.startswith("nozzles.") and r.endswith(_TABLA)}
    )
    tanque = any(r.startswith("tank.") for r in rutas)
    datos: list[Candidate] = []
    for marca in marcas:
        base = rutas.get(f"nozzles.{marca}.size_nps") or rutas[f"nozzles.{marca}.rating"]
        datos += _union(
            f"W:{marca}|{'SHELL' if not tanque else 'TANK'}",
            "nozzle",
            (marca, "SHELL" if not tanque else "TANK"),
            base,
            "soldadura.boquilla_cuerpo",
            f"La boquilla {marca} de la tabla se suelda al cuerpo; falta ver a qué pieza.",
        )
    return datos


def inferir(candidatos) -> list[Candidate]:
    """Uniones `welds.*` deducidas de los candidatos de la lectura."""
    rutas = _indice(candidatos)
    return _cuerpo(rutas) + _tanque(rutas) + _boquillas(rutas)

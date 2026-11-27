"""Asocia cotas explícitas a marcas verificadas de una misma página del GA."""

import math
import re
from dataclasses import dataclass

_MARCA = r"[A-Z]{1,4}\d{1,4}[A-Z]?"
_VALOR = r"\d+(?:[.,]\d+)?"
_ELEVACION = re.compile(
    rf"^(?:(?P<antes>{_MARCA})\s+)?(?:EL\.?|ELEV(?:ATION)?\.?)\s*:?\s*"
    rf"(?P<signo>[+\-−])\s*(?:(?P<medio>{_MARCA})\s+)?(?P<valor>{_VALOR})"
    rf"(?:\s*MM)?(?:\s+(?P<despues>{_MARCA}))?$",
    re.I,
)
_AZIMUT = re.compile(
    rf"^(?:(?P<marca>{_MARCA})\s+(?:(?:AZIMUT(?:H)?|BEARING)\s*[:=]?\s*)?"
    rf"|(?:AZIMUT(?:H)?|BEARING)\s*[:=]?\s*)(?P<valor>{_VALOR})\s*[°º]$",
    re.I,
)


@dataclass(frozen=True)
class Rotulo:
    campo: str
    valor: float
    texto: str
    caja: tuple[float, float, float, float]
    marca: str | None


def leer_rotulos(lineas):
    rotulos = []
    for texto, caja in lineas:
        if dato := _ELEVACION.fullmatch(texto):
            marcas = {dato[k] for k in ("antes", "medio", "despues") if dato[k]}
            if len(marcas) <= 1:
                valor = float(dato["valor"].replace(",", "."))
                if dato["signo"] != "+":
                    valor = -valor
                rotulos.append(Rotulo("elevation", valor, texto, caja, next(iter(marcas), None)))
        elif dato := _AZIMUT.fullmatch(texto):
            valor = float(dato["valor"].replace(",", "."))
            if 0 <= valor < 360:
                rotulos.append(Rotulo("azimuth", valor, texto, caja, dato["marca"]))
    return rotulos


def _centro(caja):
    x0, y0, x1, y1 = caja
    return (x0 + x1) / 2, (y0 + y1) / 2


def _marca_cercana(rotulo, rotulos, anclas):
    centro = _centro(rotulo.caja)
    proximas = sorted(
        (math.dist(centro, _centro(caja)), marca, caja) for marca, cajas in anclas for caja in cajas
    )
    if not proximas:
        return None
    distancia, marca, caja = proximas[0]
    if distancia > 45 or any(d <= distancia + 4 for d, otra, _ in proximas[1:] if otra != marca):
        return None
    # Dos rótulos cercanos al mismo globo no heredan ambos la marca.
    distancias_al_globo = [
        math.dist(_centro(otro.caja), _centro(caja))
        for otro in rotulos
        if otro is not rotulo and otro.campo == rotulo.campo
    ]
    if any(d <= distancia + 2 for d in distancias_al_globo):
        return None
    return marca


def _fila_encima(rotulo, rotulos, anclas):
    """Globos en fila justo encima de un rótulo de cota: la cota vale para toda la fila.

    En los GA se agrupan varias boquillas a la misma cota con sus globos contiguos y un único
    «EL.+ 1100» debajo. Solo cuenta una fila de dos o más globos a la misma altura, sin huecos,
    centrada sobre el rótulo y sin otro rótulo de cota más cerca de ella.
    """
    if rotulo.campo != "elevation":
        return []
    x0, y0, x1, _ = rotulo.caja
    debajo = [
        (marca, caja)
        for marca, cajas in anclas
        for caja in cajas
        if 0 <= y0 - caja[3] <= 8 and caja[2] >= x0 - 25 and caja[0] <= x1 + 25
    ]
    if len(debajo) < 2:
        return []
    ancho = max(c[2] - c[0] for _, c in debajo)
    alto = min(debajo, key=lambda d: y0 - d[1][3])[1][1]
    fila = sorted((d for d in debajo if abs(d[1][1] - alto) <= 1.5), key=lambda d: d[1][0])
    if len(fila) < 2 or len({m for m, _ in fila}) != len(fila):
        return []
    if any(b[1][0] - a[1][2] > ancho for a, b in zip(fila, fila[1:], strict=False)):
        return []
    centro = (fila[0][1][0] + fila[-1][1][2]) / 2
    if abs(centro - (x0 + x1) / 2) > ancho:
        return []
    for otro in rotulos:
        if otro is not rotulo and otro.campo == "elevation":
            ox0, oy0, ox1, _ = otro.caja
            if (
                0 <= oy0 - fila[0][1][3] < y0 - fila[0][1][3]
                and ox1 >= fila[0][1][0]
                and (ox0 <= fila[-1][1][2])
            ):
                return []
    return [marca for marca, _ in fila]


def asociar(rotulos, ids, pagina, normalizar_marca):
    anclas = [
        (
            marca,
            [
                a["bbox"]
                for a in item["appearances"]
                if a["page"] == pagina and a["role"] == "label"
            ],
        )
        for marca, item in ids.items()
        if item["kind"] == "nozzle"
    ]
    for rotulo in rotulos:
        if rotulo.marca:
            literal = rotulo.marca.upper()
            if (pieza := ids.get(literal)) and pieza["kind"] == "bom_item":
                continue
            marca = normalizar_marca(literal)
            if len(marca) == 1 and marca[0] in ids and ids[marca[0]]["kind"] == "nozzle":
                yield rotulo, marca[0], "explicita", 0.85
        elif fila := _fila_encima(rotulo, rotulos, anclas):
            for marca in fila:
                yield rotulo, marca, "fila", 0.60
        elif marca := _marca_cercana(rotulo, rotulos, anclas):
            yield rotulo, marca, "proximidad", 0.60

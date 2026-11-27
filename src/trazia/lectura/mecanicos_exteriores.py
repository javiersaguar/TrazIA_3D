"""Tren exterior y toberas de proceso de un GA mecánico.

Solo lo llama la lectura de bombas y compresores. La envolvente principal no se toca:
la bancada, el motor, la reductora y la máquina son volúmenes añadidos, y cada tobera
que no cabe se descarta en el ensamblado.
"""

import re

from ..extraction import Candidate
from ..model import Source

_NPS_MM = {
    8: 203.2,
    10: 254.0,
    12: 304.8,
    14: 355.6,
    16: 406.4,
    18: 457.2,
    20: 508.0,
    24: 609.6,
    26: 660.4,
}
_PROCESO = re.compile(r"SUCTION|DISCHARGE|PROCESS GAS|INLET|OUTLET", re.I)
_MARCA = re.compile(r"^(?:TP\d+|N\d+|\d{3})\b", re.I)
_PULGADAS = re.compile(r"(\d+)\s*(?:''|\"|”)")
_RATING = re.compile(r"#\s*(\d+)|\b(\d+)\s*#")
_COORD = re.compile(r"(-?\d+(?:\.\d+)?)\*?\s+(-?\d+(?:\.\d+)?)\*?\s+(-?\d+(?:\.\d+)?)\*?\s*$")
_SALIDA = 250.0


def exteriores(
    lines, kind: str, size: tuple[float, float, float], datum: Source
) -> list[Candidate]:
    lx, ly, lz = size
    if min(lx, ly, lz) <= 0:
        return []
    tren = _tren(kind, lx, ly, lz)
    out = []
    for pieza, (origen, medida) in tren.items():
        cita = _etiqueta(lines, pieza, kind) or datum
        out.extend(_volumen(pieza, _nombre(pieza, kind), origen, medida, cita))
    maquina = tren["maquina"]
    bancada_z = tren["bancada"][1][2]
    for marca in _toberas(lines):
        out.extend(_colocar(marca, kind, size, maquina, bancada_z))
    return out


def _tren(kind, lx, ly, lz):
    base = min(max(120.0, round(lz * 0.1, 1)), round(lz * 0.22, 1))
    resto = lz - base

    def hueco(x0, x1, margen_y, alto):
        x = round(lx * x0, 1)
        sx = round(lx * (x1 - x0), 1)
        sy = round(ly * (1 - 2 * margen_y), 1)
        y = round((ly - sy) / 2, 1)
        sz = round(resto * alto, 1)
        return (x, y, base), (sx, sy, sz)

    piezas = {
        "bancada": ((0.0, 0.0, 0.0), (lx, ly, base)),
        "motor": hueco(0.04, 0.36, 0.22, 0.62),
        "maquina": hueco(0.54, 0.96, 0.14, 0.9),
    }
    if kind == "compressor":
        piezas["motor"] = hueco(0.03, 0.32, 0.24, 0.55)
        piezas["reductora"] = hueco(0.34, 0.5, 0.28, 0.48)
        piezas["maquina"] = hueco(0.52, 0.96, 0.16, 0.78)
    else:
        piezas["motor"] = hueco(0.04, 0.46, 0.2, 0.6)
        piezas["maquina"] = hueco(0.52, 0.96, 0.12, 0.88)
    return piezas


def _nombre(pieza, kind):
    if pieza == "maquina":
        return "Compresor" if kind == "compressor" else "Bomba"
    return {"bancada": "Bancada", "motor": "Motor", "reductora": "Reductora"}[pieza]


def _etiqueta(lines, pieza, kind):
    patrones = {
        "bancada": r"BASEPLATE|BASE FRAME|BASE PLATE",
        "motor": r"ELECTRIC MOTOR|^MOTOR\b",
        "reductora": r"GEARBOX|^GEAR\b",
        "maquina": r"^COMPRESSOR\b|^PUMP\b",
    }
    if pieza == "maquina" and kind == "pump":
        patrones["maquina"] = r"^PUMP\b|PUMP TYPE"
    return next(
        (line for line in lines if re.search(patrones[pieza], line.text, re.I)),
        None,
    )


def _volumen(pieza, nombre, origen, medida, cita) -> list[Candidate]:
    fuente = cita.source if hasattr(cita, "source") else cita
    out = [
        _campo(
            f"components.{pieza}.name",
            nombre,
            "1",
            fuente,
            regla="mecanico.componente_del_tren",
            texto=nombre,
            explicacion=f"Volumen exterior del {nombre.lower()} dentro de la envolvente.",
        )
    ]
    for eje, valor in zip("xyz", origen, strict=True):
        out.append(
            _campo(
                f"components.{pieza}.envelope.origin.{eje}",
                valor,
                "mm",
                fuente,
                regla="mecanico.componente_del_tren",
                explicacion="Esquina del componente en el origen de la bancada.",
            )
        )
    for eje, valor in zip("xyz", medida, strict=True):
        out.append(
            _campo(
                f"components.{pieza}.envelope.size.{eje}",
                valor,
                "mm",
                fuente,
                regla="mecanico.componente_del_tren",
                explicacion="Tamaño del componente a lo largo del tren.",
            )
        )
    return out


def _toberas(lines):
    vistas = []
    for line in lines:
        texto = " ".join(line.text.split())
        marca = _MARCA.match(texto)
        if not _PROCESO.search(texto) or not (
            marca or re.search(r"SUCTION|DISCHARGE", texto, re.I)
        ):
            continue
        if re.search(r"SEAL|DRAIN|VENT|QUENCH|HOLD|GROUT|JACKING", texto, re.I):
            continue
        pulgadas = _PULGADAS.search(texto)
        if pulgadas is None or int(pulgadas[1]) not in _NPS_MM:
            continue
        rating = _RATING.search(texto)
        coords = _COORD.search(texto)
        servicio = "SUCTION" if re.search(r"SUCTION|INLET", texto, re.I) else "DISCHARGE"
        vistas.append(
            {
                "id": marca[0].upper() if marca else ("N1" if servicio == "SUCTION" else "N2"),
                "servicio": servicio,
                "nps": int(pulgadas[1]),
                "rating": f"{next(g for g in rating.groups() if g)}#" if rating else None,
                "xyz": tuple(float(v) for v in coords.groups()) if coords else None,
                "preliminar": "*" in texto,
                "line": line,
            }
        )
    unicos = {}
    for marca in vistas:
        unicos.setdefault(marca["id"], marca)
    return list(unicos.values())


def _colocar(marca, kind, size, maquina, bancada_z) -> list[Candidate]:
    lx, ly, lz = size
    (mx, my, mz), (sx, sy, sz) = maquina
    local = marca["xyz"]
    if local is None:
        if kind == "pump" and marca["servicio"] == "SUCTION":
            origen = (mx + sx, my + sy / 2, mz + sz * 0.45)
            direccion = (1.0, 0.0, 0.0)
        else:
            origen = (mx + sx * 0.5, my + sy / 2, mz + sz)
            direccion = (0.0, 0.0, 1.0)
            if kind == "compressor":
                orden = {"N1": 0.2, "N2": 0.4, "781": 0.25, "782": 0.45, "783": 0.65, "784": 0.85}
                origen = (mx + sx * orden.get(marca["id"], 0.5), my + sy / 2, mz + sz)
    else:
        x, y, z = local
        # Las tablas de puntos dan coordenadas locales de la máquina, no de la esquina del skid.
        if abs(x) < lx * 0.5:
            x = mx + min(max(x, 0), sx * 0.92)
        y = ly / 2 + y
        z = bancada_z + max(z, 0)
        origen = (x, y, z)
        direccion = (0.0, 0.0, 1.0)
    if origen[2] < 0 or origen[0] < 0 or origen[1] < 0:
        return []
    if origen[0] > lx or origen[1] > ly or origen[2] > lz + _SALIDA:
        return []
    fuente = marca["line"].source
    regla = "mecanico.tobera_preliminar" if marca["preliminar"] else "mecanico.tobera_proceso"
    confianza = 0.55 if marca["preliminar"] else 0.7
    marca_id = marca["id"]
    out = []
    for eje, valor in zip("xyz", origen, strict=True):
        out.append(
            _campo(
                f"nozzles.{marca_id}.position.{eje}",
                round(valor, 1),
                "mm",
                fuente,
                regla=regla,
                confianza=confianza,
                texto=marca["line"].text,
                explicacion="Posición de la tobera de proceso respecto a la bancada.",
            )
        )
    for eje, valor in zip("xyz", direccion, strict=True):
        out.append(
            _campo(
                f"nozzles.{marca_id}.direction.{eje}",
                valor,
                "1",
                fuente,
                regla="mecanico.direccion_supuesta",
                confianza=0.55,
                explicacion="Dirección supuesta de la cara de la brida.",
            )
        )
    out.append(
        _campo(
            f"nozzles.{marca_id}.elevation",
            round(origen[2], 1),
            "mm",
            fuente,
            regla=regla,
            confianza=confianza,
            explicacion="La elevación es la coordenada Z de la tobera.",
        )
    )
    out.append(
        _campo(
            f"nozzles.{marca_id}.azimuth",
            0.0,
            "deg",
            fuente,
            regla="mecanico.azimut_supuesto",
            confianza=0.55,
            explicacion="Azimut de referencia; la posición explícita coloca la tobera.",
        )
    )
    out.append(
        _campo(
            f"nozzles.{marca_id}.diameter",
            _NPS_MM[marca["nps"]],
            "mm",
            fuente,
            regla=regla,
            confianza=confianza,
            texto=marca["line"].text,
            explicacion=f"Diámetro interior nominal de {marca['nps']} pulgadas.",
        )
    )
    out.append(
        _campo(
            f"nozzles.{marca_id}.projection",
            _SALIDA,
            "mm",
            fuente,
            regla="mecanico.saliente_supuesto",
            confianza=0.55,
            explicacion="Saliente supuesto para que la brida se vea fuera del cuerpo.",
        )
    )
    out.append(
        _campo(
            f"nozzles.{marca_id}.service",
            marca["servicio"],
            "1",
            fuente,
            regla=regla,
            confianza=confianza,
            texto=marca["line"].text,
        )
    )
    out.append(
        _campo(
            f"nozzles.{marca_id}.size_nps",
            str(marca["nps"]),
            "in",
            fuente,
            regla=regla,
            confianza=confianza,
            texto=marca["line"].text,
        )
    )
    if marca["rating"]:
        out.append(
            _campo(
                f"nozzles.{marca_id}.rating",
                marca["rating"],
                "1",
                fuente,
                regla=regla,
                confianza=confianza,
                texto=marca["line"].text,
            )
        )
    return out


def _campo(path, value, unit, source, *, regla, texto=None, explicacion="", confianza=0.7):
    return Candidate(
        path=path,
        value=value,
        unit=unit,
        source=source.model_copy(update={"confidence": confianza, "rule": regla}),
        state="assumed",
        channel="geometria",
        text_original=texto,
        explanation=explicacion,
    )

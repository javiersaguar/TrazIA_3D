"""Lee tablas e identificadores citados de GA vectoriales, sin usar la HDM."""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO

import pdfplumber
from pdfplumber.utils import cluster_objects

from ..extractors.units import NPS_OUTSIDE_DIAMETER_MM
from ..ingest import dataset_filename
from .envolvente import leer_envolvente
from .rotulos import asociar, leer_rotulos
from .tipologia import indicios_tipologia, masas_ga
from .tipologia import normalizar as _canon

_MARCA = re.compile(r"([A-Z]{1,4})([0-9]{1,4})([A-Z]?)")
_GRUPO = re.compile(r"([A-Z]{1,4})([0-9]{1,4})[-–](?:\1)?([0-9]{1,4})")
_COLUMNAS = {
    "ITEM": "mark",
    "POS": "mark",
    "MARK": "mark",
    "MARCA": "mark",
    "NOZZLE": "mark",
    "DENOMINACION": "mark",
    "QUANT": "quantity",
    "QTY": "quantity",
    "QUANTITY": "quantity",
    "AANTAL": "quantity",
    "CANTIDAD": "quantity",
    "CANT": "quantity",
    "SIZE": "size_nps",
    "NPS": "size_nps",
    "NOMINAL": "size_nps",
    "TAMANO": "size_nps",
    "TIPO": "flange_type",
    "TYPE": "flange_type",
    "FLANGE": "flange_type",
    "RATING": "rating",
    "CLASE": "rating",
    "FACE": "facing",
    "FACING": "facing",
    "SCH": "schedule",
    "SCHEDULE": "schedule",
    "SERVICE": "service",
    "OBSERVATIONS": "service",
    "SERVICIO": "service",
    "DESCRIPTION": "description",
    "DESCRIPCION": "description",
    "DESIGNATION": "description",
    "DESIGNACION": "description",
    "PROJECTION": "standout",
    "PROYECTION": "standout",
    "PROYECCION": "standout",
    "PROYEC": "standout",
    "STANDOUT": "standout",
    "MATERIAL": "material",
    "CALIDAD": "material",
    "CODE": "code",
    "CODIGO": "code",
    # Posición de la boquilla en la tabla: estación desde la tangente izquierda (horizontales)
    # y orientación en grados.
    "STATION": "station",
    "ESTACION": "station",
    "ORIENT": "azimuth",
    "ORIENTATION": "azimuth",
    "ORIENTACION": "azimuth",
    "AZIMUTH": "azimuth",
    "AZIMUT": "azimuth",
}
_PUNTOS = ("x0", "top", "x1", "bottom")
_ORIENTACION = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*[°º]?")
_AJUSTES_TABLA = {"snap_tolerance": 1.5, "join_tolerance": 3, "intersection_tolerance": 2}
_INICIO_NOTA = re.compile(r"^(?:N\s*)?(?:\((\d+)\)|(\d+)\s*[.)])[-.\s:]*(?=\D)", re.I)


def _columna(texto: str | None) -> str:
    canon = _canon(texto or "").lstrip()
    # «FLANGE STANDARD» es la norma de la brida (B16.5), no su tipo.
    if re.match(r"FLANGE\s*STANDARD", canon):
        return ""
    if re.fullmatch(r"TYPE\s*&\s*FACE", canon.strip()):
        return "facing"
    # «NOZZLE» solo es la columna de marca si va sola: «Nozzle Type» es otra columna.
    if canon.startswith("NOZZLE"):
        return "mark" if re.fullmatch(r"NOZZLE(?:\s*(?:MARK|NO\.?))?", canon.strip()) else ""
    nombre = re.match(r"[A-Z]+", canon)
    return _COLUMNAS.get(nombre[0], "") if nombre else ""


def expandir_marcas(
    texto: str, cantidad: int | None = None, *, invertida: bool = False
) -> list[str]:
    marca = re.sub(r"\s*\(HOLD\)$", "", texto.strip().upper())
    marca = re.sub(r"\s+", "", marca)
    if invertida:
        marca = marca[::-1]
    if grupo := _GRUPO.fullmatch(marca):
        prefijo, inicio, fin = grupo.groups()
        diferencia = int(fin) - int(inicio)
        if cantidad != diferencia + 1 or not 0 <= diferencia < 99:
            return []
        return [f"{prefijo}{i}" for i in range(int(inicio), int(fin) + 1)]
    partes = re.split(r"[/,]", marca)
    if primero := _MARCA.fullmatch(partes[0]):
        base = primero[1] + str(int(primero[2]))
        codigos = [base + primero[3]]
        for parte in partes[1:]:
            if completo := _MARCA.fullmatch(parte):
                codigos.append(completo[1] + str(int(completo[2])) + completo[3])
            elif primero[3] and re.fullmatch(r"[A-Z]", parte):
                codigos.append(base + parte)
            elif cantidad == len(partes) and not primero[3] and re.fullmatch(r"\d{1,4}", parte):
                codigos.append(primero[1] + str(int(parte)))
            else:
                return []
        return codigos if cantidad in (None, len(codigos)) else []
    return []


def _tipo(columnas: list[str]) -> str | None:
    presentes = set(columnas)
    if {"mark", "size_nps", "rating"} <= presentes:
        return "ga_table"
    if {"mark", "material"} <= presentes and {"description", "quantity"} & presentes:
        return "bom"
    return None


def _secciones(header, bordes):
    """Encuentra una regla de tabla que atraviesa las columnas detectadas."""
    marca, ultima = header[0], header[-1]
    alto = marca["bottom"] - marca["top"]
    por_fila = cluster_objects(
        [e for e in bordes if marca["top"] - alto * 5 <= e["top"] <= marca["bottom"] + alto],
        "top",
        1,
    )
    for fila in por_fila:
        intervalos: list[list[float]] = []
        for e in sorted(fila, key=lambda e: e["x0"]):
            if intervalos and e["x0"] <= intervalos[-1][1] + 3:
                intervalos[-1][1] = max(intervalos[-1][1], e["x1"])
            else:
                intervalos.append([e["x0"], e["x1"]])
        for izquierda, derecha in intervalos:
            ancho = ultima["x1"] - marca["x0"]
            if (
                izquierda <= marca["x0"] <= izquierda + alto * 12
                and derecha >= ultima["x1"] - 1
                and derecha - izquierda <= max(ancho * 2.4, alto * 35)
            ):
                yield izquierda, derecha


def _tablas(page, palabras):
    bordes = [b for b in page.edges if b["orientation"] == "h" and b["width"] >= 2]
    tituladas = list(_tablas_tituladas(page, palabras, bordes))
    for _, tabla in tituladas:
        yield tabla
    vistos = set()
    con_columna = [p for p in palabras if _columna(p["text"])]
    for linea in cluster_objects(palabras, "top", 2):
        # Cabeceras en dos líneas («NOMINAL / SIZE» bajo «NOZZLE … RATING»): entran las palabras
        # de cabecera de las líneas pegadas, pero la tabla solo se abre en la línea de la marca.
        alto_linea = max(p["bottom"] - p["top"] for p in linea)
        arriba = min(p["top"] for p in linea) - alto_linea * 1.6
        abajo = max(p["bottom"] for p in linea) + alto_linea * 1.6
        campos = sorted(
            (p for p in con_columna if p["top"] >= arriba and p["bottom"] <= abajo),
            key=lambda p: p["x0"],
        )
        todas = [i for i, p in enumerate(campos) if _columna(p["text"]) == "mark"]
        fuertes = {i for i in todas if not _canon(campos[i]["text"]).lstrip().startswith("NOZZLE")}
        marcas = [i for i in todas if any(campos[i] is q for q in linea)]
        # Una palabra «Nozzle» suelta no abre tabla si la línea ya tiene otra marca (Pos., Mark).
        marcas = [i for i in marcas if i in fuertes] or marcas
        # Cada cabecera acaba en la siguiente marca, sea de esta línea o de una pegada (la tabla
        # de al lado con su cabecera bilingüe en dos líneas).
        limites = sorted(fuertes | set(marcas))
        for inicio in marcas:
            fin = next((i for i in limites if i > inicio), len(campos))
            encabezado = campos[inicio:fin]
            primero = encabezado[0]
            if any(_en_caja(primero, region) for region, _ in tituladas):
                continue
            alto = primero["bottom"] - primero["top"]
            encabezado = [p for p in encabezado if p["x0"] - primero["x0"] < alto * 180]
            tipo = _tipo([_columna(p["text"]) for p in encabezado])
            if not tipo:
                continue
            cortes = sorted(
                set(_secciones(encabezado, bordes)),
                key=lambda intervalo: intervalo[1] - intervalo[0],
            )
            for izquierda, derecha in cortes[:2]:
                x0, top, x1, bottom = page.bbox
                recorte = (
                    max(x0, izquierda - 2),
                    max(top, primero["top"] - alto * 5),
                    min(x1, derecha + 2),
                    min(bottom, primero["bottom"] + alto * 120),
                )
                for tabla in page.crop(recorte).find_tables(_AJUSTES_TABLA):
                    if not (
                        tabla.bbox[0] <= primero["x0"] <= tabla.bbox[2]
                        and tabla.bbox[1] <= primero["top"] <= tabla.bbox[3]
                    ):
                        continue
                    filas = tabla.extract(x_tolerance=1, y_tolerance=2)
                    for i, textos in enumerate(filas):
                        columnas = [_columna(t) for t in textos]
                        if _tipo(columnas) != tipo:
                            continue
                        celdas = _celdas(columnas, textos, tabla.rows[i].cells)
                        firma = (tipo, tuple(round(x) for x in celdas["mark"][1]))
                        if firma not in vistos:
                            vistos.add(firma)
                            yield (
                                tipo,
                                tabla.rows[i + 1 :],
                                columnas,
                                filas[i + 1 :],
                                celdas,
                            )
                        break


def _recorte_titulo(page, titulo, horizontales, verticales):
    """Localiza las reglas del título y los costados que cierran su tabla."""
    x0, top, x1, bottom = titulo
    alto = bottom - top
    reglas = [b for b in horizontales if b["x0"] <= x0 and b["x1"] >= x1]
    for inferior in sorted(reglas, key=lambda b: b["top"]):
        y = inferior["top"]
        if not bottom <= y <= bottom + alto * 2:
            continue
        izquierda, derecha = inferior["x0"], inferior["x1"]
        superiores = [
            b["top"]
            for b in reglas
            if top - alto * 2 <= b["top"] <= top
            and abs(b["x0"] - izquierda) <= 1
            and abs(b["x1"] - derecha) <= 1
        ]
        if not superiores:
            continue
        comienzo = max(superiores)
        costados = [
            [
                b["bottom"]
                for b in verticales
                if abs(b["x0"] - x) <= 1 and b["top"] <= comienzo + 1 and b["bottom"] > y
            ]
            for x in (izquierda, derecha)
        ]
        if all(costados):
            return izquierda, comienzo, derecha, min(min(map(max, costados)), page.bbox[3])
    return None


def _tablas_tituladas(page, palabras, horizontales):
    titulos = [
        (texto, caja)
        for texto, caja in map(_texto_caja, _segmentos_linea(palabras))
        if _canon(texto) == "NOZZLE SCHEDULE"
    ]
    if not titulos:
        return
    verticales = [b for b in page.edges if b["orientation"] == "v"]
    for titulo in titulos:
        if not (region := _recorte_titulo(page, titulo[1], horizontales, verticales)):
            continue
        for tabla in page.crop(region).find_tables(_AJUSTES_TABLA):
            filas = tabla.extract(x_tolerance=1, y_tolerance=2)
            if not any(_canon(t or "").strip() == "NOZZLE SCHEDULE" for t in filas[0]):
                continue
            columnas = [""] * len(filas[0])
            cabeceras = {"title": titulo}
            for i, textos in enumerate(filas[1:], 1):
                if not any(_columna(t) for t in textos):
                    break
                for j, (texto, caja) in enumerate(zip(textos, tabla.rows[i].cells, strict=True)):
                    if columna := _columna(texto):
                        columnas[j] = columna
                        cabeceras[columna] = (texto, caja)
            else:
                continue
            if _tipo(columnas) == "ga_table" and columnas.count("mark") == 1:
                # Retiene la caja de la celda hoja si hay encabezados agrupados encima.
                cabeceras = {k: v for k, v in cabeceras.items() if k in columnas or k == "title"}
                yield region, ("ga_table", tabla.rows[i:], columnas, filas[i:], cabeceras)
                break


def _valor_nps(texto: str) -> float | None:
    limpio = re.sub(r"\s*\(HOLD\)$", "", texto.strip(), flags=re.I)
    limpio = re.sub(r"\s*\[\s*DN\s*\d+(?:[.,]\d+)?\s*\]$", "", limpio, flags=re.I)
    limpio = limpio.replace('"', "").replace("″", "").replace(",", ".")
    if not re.fullmatch(r"\d+(?:[.,]\d+|[ -]\d+/\d+|/\d+)?", limpio):
        return None
    try:
        return float(sum(Fraction(p) for p in limpio.replace("-", " ").split()))
    except ZeroDivisionError:
        return None


def _numero(texto: str) -> float | None:
    if re.fullmatch(r"\d+(?:[.,]\d+)?", texto):
        return float(texto.replace(",", "."))
    return None


def _segmentos_linea(palabras):
    for linea in cluster_objects(palabras, "top", 2):
        grupo = []
        for palabra in sorted(linea, key=lambda p: p["x0"]):
            alto = palabra["bottom"] - palabra["top"]
            if grupo and palabra["x0"] - grupo[-1]["x1"] > max(20, alto * 4):
                yield grupo
                grupo = []
            grupo.append(palabra)
        if grupo:
            yield grupo


def _texto_caja(grupo):
    return (
        " ".join(p["text"] for p in grupo),
        (
            min(p["x0"] for p in grupo),
            min(p["top"] for p in grupo),
            max(p["x1"] for p in grupo),
            max(p["bottom"] for p in grupo),
        ),
    )


def _notas_proyeccion(lineas):
    """Retiene el texto y la caja de notas numeradas de una página."""
    for i, (texto, caja) in enumerate(lineas):
        if not (marca := _INICIO_NOTA.match(texto)):
            continue
        x0, top, x1, bottom = caja
        alto = bottom - top
        for j in range(i + 1, len(lineas)):
            linea, siguiente = lineas[j]
            if siguiente[1] > bottom + alto * 1.5:
                break
            if siguiente[1] <= top + 2 or abs(siguiente[0] - x0) > alto * 3:
                continue
            if _INICIO_NOTA.match(linea):
                break
            texto += " " + linea
            x1, bottom = max(x1, siguiente[2]), max(bottom, siguiente[3])
        yield marca[1] or marca[2], (texto, (x0, top, x1, bottom))


def _marcos(texto):
    texto = _canon(texto)
    patrones = {
        "axis": r"\b(?:AXIS|CENT(?:ER|RE)(?:\s*LINE)?|EJE)\b",
        "shell": r"\b(?:SHELL|VIROLA)\b",
        "tangent": r"\b(?:TANGEN(?:T|CIA|CY)|T\s*\.\s*L\b)",
    }
    return {marco for marco, patron in patrones.items() if re.search(patron, texto)}


def _base_proyeccion(cabecera, notas):
    if cabecera is None:
        return "desconocida", None
    numero = re.search(r"\((\d+)\)", cabecera[0])
    evidencia = cabecera
    marcos = set()
    for id_nota, nota in notas:
        aplica = (
            numero[1] == id_nota
            if numero
            else re.search(r"\b(?:PRO[JY]EC|STAND\s?OUT)", _canon(nota[0]))
        )
        if aplica and (marcos_nota := _marcos(nota[0])):
            if not marcos:
                evidencia = nota
            marcos.update(marcos_nota)
    if not marcos:
        marcos = _marcos(cabecera[0])
    if len(marcos) == 1 and "tangent" not in marcos:
        return next(iter(marcos)), evidencia
    return "desconocida", evidencia


def _valor_proyeccion(texto):
    dato = re.fullmatch(r"(\d+(?:[.,]\d+)?)(?:\s*mm)?(?:\s*\(\d+\))?", texto, re.I)
    return _numero(dato[1]) if dato else None


def _cita(documento, page, caja, texto):
    x0, y0, x1, y1 = caja
    # El registro usa puntos PDF. Source.bbox del contrato 0.3 usa coordenadas normalizadas.
    return {
        "document_id": documento,
        "page": page.page_number,
        "bbox": [x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height],
        "locator": texto,
        "text_original": texto,
        "confidence": 0.85,
    }


def _candidato(documento, page, caja, texto, ruta, valor, unidad=""):
    return {
        "path": ruta,
        "value": valor,
        "unit": unidad,
        "source": _cita(documento, page, caja, texto),
    }


def _aparicion(documento, page, caja, texto, rol):
    return {
        "document_id": documento,
        "page": page.page_number,
        "role": rol,
        "bbox": list(caja),
        "locator": texto,
    }


def _celdas(columnas, textos, cajas):
    celdas = {}
    for columna, texto, caja in zip(columnas, textos, cajas, strict=True):
        if columna and texto and re.search(r"[^\s–—-]", texto) and caja is not None:
            if columna == "code" and not re.fullmatch(r"\d{8}", texto.strip()):
                continue
            celdas[columna] = (texto.strip(), caja)
    return celdas


def _lee_filas(documento, page, tabla, notas, registro, candidatos, avisos):
    rol, filas, columnas, textos, cabeceras = tabla
    referencia = _base_proyeccion(cabeceras.get("standout"), notas)
    regiones = []
    inventario = {}
    ambiguas = set()
    completo = rol == "ga_table"
    fin = None
    titulo = cabeceras.get("title")
    for fila, valores in zip(filas, textos, strict=True):
        rotulo = "".join(_canon(valor).replace(" ", "") for valor in valores if valor)
        if any(t in rotulo for t in ("DESIGNDATA", "ACCESSORIES", "MATERIALLIST", "NOZZLELIST")):
            fin = fila.bbox
            break
        celdas = _celdas(columnas, valores, fila.cells)
        if "mark" not in celdas:
            if celdas:
                completo = False
            continue
        texto, caja = celdas["mark"]
        if _columna(texto) == "mark":
            break
        cantidad = celdas.get("quantity", ("", None))[0]
        if rol == "bom" and texto.isdecimal():
            marcas = [texto]
        else:
            n = int(cantidad) if rol == "ga_table" and cantidad.isdecimal() else None
            marcas = expandir_marcas(texto, n)
        servicio = _canon(celdas.get("service", ("", None))[0])
        if rol == "ga_table" and servicio.startswith(("SKIRT ACCESS", "SKIRT OPENING")):
            continue
        if rol == "ga_table" and not {"size_nps", "rating"} & celdas.keys():
            completo = False
            continue
        if titulo and (
            "rating" not in celdas or _valor_nps(celdas.get("size_nps", ("", None))[0]) is None
        ):
            completo = False
            continue
        if rol == "bom" and not {"material", "description"} <= celdas.keys():
            continue
        if not marcas:
            completo = False
            continue
        regiones.append(fila.bbox)
        for marca in marcas:
            if rol == "bom":
                _registra_bom(documento, page, marca, texto, caja, celdas, registro, candidatos)
            else:
                clave = ("nozzle", marca)
                registro.setdefault(clave, {"kind": "nozzle", "code": None, "appearances": []})[
                    "appearances"
                ].append(_aparicion(documento, page, caja, texto, rol))
                inicio = len(candidatos)
                _candidatos_boquilla(documento, page, marca, celdas, referencia, candidatos, avisos)
                if marca in inventario:
                    completo = False
                    ambiguas.add(marca)
                if marca in ambiguas:
                    inventario.pop(marca, None)
                    continue
                inventario[marca] = {
                    "source": _cita(
                        documento, page, fila.bbox, " ".join(v.strip() for v in valores if v)
                    ),
                    "fields": {
                        c["path"].split(".", 2)[-1]: {
                            "value": c["value"],
                            "unit": c["unit"] or "1",
                            "source": c["source"],
                        }
                        for c in candidatos[inicio:]
                    },
                }
                if titulo:
                    inventario[marca]["fields"]["mark"] = {
                        "value": texto,
                        "unit": "1",
                        "source": _cita(documento, page, caja, texto),
                    }
    if not inventario:
        return regiones, None
    cabecera, inicio = titulo or cabeceras["mark"]
    caja = (
        min(inicio[0], *(b[0] for b in regiones)),
        inicio[1],
        max(inicio[2], *(b[2] for b in regiones)),
        fin[1] if fin else max(b[3] for b in regiones),
    )
    return regiones, {
        "source": _cita(documento, page, caja, cabecera),
        "rows": inventario,
        "complete": completo and (fin is not None or titulo is not None),
    }


def _registra_bom(documento, page, marca, texto, caja, celdas, registro, candidatos):
    posicion = re.sub(r"\s+", "", texto.upper())
    marca = posicion if _MARCA.fullmatch(posicion) else marca
    cod = celdas.get("code", ("", None))[0]
    codigo = cod if re.fullmatch(r"\d{8}", cod) else None
    clave = ("bom_item", marca)
    registro.setdefault(clave, {"kind": "bom_item", "code": codigo, "appearances": []})[
        "appearances"
    ].append(_aparicion(documento, page, caja, texto, "bom"))
    if not re.fullmatch(r"V\d+[A-Z]?", marca):
        return
    ruta = f"shell.courses.{marca}."
    material, celda = celdas["material"]
    candidatos.append(_candidato(documento, page, celda, material, ruta + "material", material))
    if codigo:
        candidatos.append(_candidato(documento, page, celdas["code"][1], cod, ruta + "code", cod))
    descripcion, celda = celdas["description"]
    if dimensiones := re.search(
        r"\bTHK\.?\s*(\d+(?:[.,]\d+)?)\s*[X×]\s*(\d+(?:[.,]\d+)?)\s*[X×]\s*(\d+(?:[.,]\d+)?)",
        descripcion,
        re.I,
    ):
        for campo, valor in zip(
            ("thickness", "height", "development"), dimensiones.groups(), strict=True
        ):
            candidatos.append(
                _candidato(documento, page, celda, descripcion, ruta + campo, _numero(valor), "mm")
            )


def _candidatos_boquilla(documento, page, marca, celdas, referencia, candidatos, avisos):
    ruta = f"nozzles.{marca}."
    for campo in (
        "size_nps",
        "rating",
        "flange_type",
        "facing",
        "schedule",
        "service",
        "description",
    ):
        if celda := celdas.get(campo):
            texto, caja = celda
            destino = "service" if campo == "description" else campo
            unidad = "in" if campo == "size_nps" else ""
            valor = _valor_nps(texto) if campo == "size_nps" else texto
            if valor is not None:
                candidatos.append(
                    _candidato(documento, page, caja, texto, ruta + destino, valor, unidad)
                )
                exterior = NPS_OUTSIDE_DIAMETER_MM.get(valor) if campo == "size_nps" else None
                if exterior is not None:
                    candidatos.append(
                        {
                            **_candidato(
                                documento, page, caja, texto, ruta + "diameter", exterior, "mm"
                            ),
                            "explanation": "Diámetro exterior según ASME B36.10",
                        }
                    )
    if (estacion := celdas.get("station")) and (
        valor := _valor_proyeccion(estacion[0].lstrip("+"))
    ) is not None:
        candidatos.append(
            _candidato(documento, page, estacion[1], estacion[0], ruta + "station", valor, "mm")
        )
    if (orientacion := celdas.get("azimuth")) and (dato := _ORIENTACION.fullmatch(orientacion[0])):
        valor = float(dato[1].replace(",", "."))
        if 0 <= valor < 360:
            candidatos.append(
                _candidato(
                    documento, page, orientacion[1], orientacion[0], ruta + "azimuth", valor, "deg"
                )
            )
    if not (proyeccion := celdas.get("standout")):
        return
    if (valor := _valor_proyeccion(proyeccion[0])) is not None:
        base, evidencia = referencia
        texto_base, caja_base = evidencia or proyeccion
        candidatos.append(
            _candidato(
                documento, page, proyeccion[1], proyeccion[0], ruta + "projection", valor, "mm"
            )
        )
        candidatos.append(
            _candidato(documento, page, caja_base, texto_base, ruta + "projection_basis", base)
        )
        if base == "desconocida":
            avisos.append(
                f"{ruta}projection: la referencia no está determinada para esa fila del GA."
            )
    elif re.match(r"REFER\s+(?:TO\s+)?SKETCH\b", _canon(proyeccion[0])):
        texto, caja = proyeccion
        referencia = re.sub(r"\s*/\s*", "/", " ".join(texto.split()))
        candidatos.append(
            _candidato(documento, page, caja, texto, ruta + "projection_reference", referencia)
        )


def _en_caja(palabra, caja):
    x = (palabra["x0"] + palabra["x1"]) / 2
    y = (palabra["top"] + palabra["bottom"]) / 2
    return caja[0] <= x <= caja[2] and caja[1] <= y <= caja[3]


_TAG_COLUMNA = re.compile(r"(?:^|[-_\d])C[-_]?\d", re.I)


def _inferido(base, path, valor, confianza, regla, explicacion):
    return {
        **base,
        "path": path,
        "value": valor,
        "explanation": explicacion,
        "source": {**base["source"], "confidence": confianza, "rule": regla},
    }


def _inferir_por_familia(clasificacion, etiqueta):
    """Completa tipo o soporte cuando el otro campo está citado y la familia no deja duda."""
    tipo, soporte = "attributes.equipment_type", "attributes.support"
    c_tipo = clasificacion.get(tipo, (0, None))[1]
    c_soporte = clasificacion.get(soporte, (0, None))[1]
    if c_tipo and c_tipo["value"] == "tank" and c_soporte is None:
        # Un tanque de fondo plano apoya en la cimentación; no tiene faldón, patas ni silletas.
        clasificacion[soporte] = (
            70,
            _inferido(
                c_tipo,
                soporte,
                "none",
                0.7,
                "ga.tipologia.tanque_en_cimentacion",
                f"Tanque («{c_tipo['source']['locator']}»): apoya en la cimentación.",
            ),
        )
    if c_tipo is None and c_soporte and c_soporte["value"] == "skirt":
        if _TAG_COLUMNA.search(etiqueta):
            clasificacion[tipo] = (
                65,
                _inferido(
                    c_soporte,
                    tipo,
                    "column",
                    0.65,
                    "ga.tipologia.faldon_y_tag",
                    f"Faldón («{c_soporte['source']['locator']}») y tag {etiqueta}, "
                    "con la letra C de columna.",
                ),
            )


def leer_pdf(ruta: Path) -> dict:
    documento = re.sub(r"[^A-Za-z0-9_-]", "_", ruta.stem)
    return leer_ga(ruta, documento=documento, nombre=ruta.name)


def leer_ga(
    archivo: Path | BinaryIO, *, documento: str, nombre: str, tag: str | None = None
) -> dict:
    registro: dict = {}
    candidatos: list = []
    descartados = []
    avisos = []
    clasificacion = {}
    rotulos_por_pagina = []
    recipiente = None
    alzado = None
    tablas_boquillas = []
    with pdfplumber.open(archivo) as pdf:
        for page in pdf.pages:
            palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
            visibles = [p for p in palabras if _en_caja(p, page.bbox)]
            lineas = [_texto_caja(grupo) for grupo in _segmentos_linea(visibles)]
            filas = [
                _texto_caja(sorted(fila, key=lambda p: p["x0"]))
                for fila in cluster_objects(visibles, "top", 2)
            ]
            notas = list(_notas_proyeccion(lineas))
            if rotulos := leer_rotulos(lineas):
                rotulos_por_pagina.append((page, rotulos))
            for campo, valor, prioridad, texto, caja in indicios_tipologia(lineas, filas):
                path = f"attributes.{campo}"
                if prioridad > clasificacion.get(path, (0, None))[0]:
                    c = _candidato(documento, page, caja, texto, path, valor)
                    c["source"]["confidence"] = prioridad / 100
                    clasificacion[path] = (prioridad, c)
            candidatos.extend(
                _candidato(documento, page, caja, texto, path, valor, "kg")
                for path, valor, texto, caja in masas_ga(filas)
            )
            for path, valor, unidad, texto, caja, regla, estado in leer_envolvente(
                page, lineas, filas, visibles
            ):
                lectura = _candidato(documento, page, caja, texto, path, valor, unidad)
                lectura["source"]["rule"] = regla
                if estado:
                    lectura["state"] = estado
                    lectura["source"]["confidence"] = 0.6
                    lectura["explanation"] = {
                        "ga.fondo_elipsoidal_2_a_1": (
                            "Semi-elipse 2:1, profundidad estimada como D/4."
                        ),
                        "ga.silleta_movil_medida_a_escala": (
                            "Ancho del contorno vectorial de la silleta móvil, medido a la escala "
                            "de la sección y contrastado con la cota entre sus anclajes. "
                            "Redondeado a 5 mm para revisión."
                        ),
                    }[regla]
                candidatos.append(lectura)
            for texto, caja in lineas:
                if recipiente is None and re.search(r"\b(?:VESSEL|RECIPIENTE)\b", texto, re.I):
                    recipiente = texto
                if alzado is None and re.match(r"EL\.?\s*[+\-−]", texto, re.I):
                    alzado = _cita(documento, page, caja, texto)
            regiones = []
            for tabla in _tablas(page, palabras):
                filas_leidas, inventario = _lee_filas(
                    documento, page, tabla, notas, registro, candidatos, avisos
                )
                regiones.extend(filas_leidas)
                if tabla[0] == "ga_table":
                    tablas_boquillas.append(inventario)
            for palabra in palabras:
                texto = palabra["text"].upper()
                if not _MARCA.fullmatch(texto) or any(_en_caja(palabra, c) for c in regiones):
                    continue
                caja = [palabra[k] for k in _PUNTOS]
                descartados.append(_aparicion(documento, page, caja, palabra["text"], "label"))
            page.close()
    tipo = "attributes.equipment_type"
    soporte = clasificacion.get("attributes.support", (0, None))[1]
    if tipo not in clasificacion and soporte and soporte["value"] == "legs":
        if recipiente and alzado:
            tipo_candidato = {
                **soporte,
                "path": tipo,
                "value": "vertical_vessel",
                "explanation": (
                    f"Detalle de patas y rótulo «{recipiente}», "
                    f"con cota de alzado «{alzado['locator']}»."
                ),
                "source": {
                    **soporte["source"],
                    "confidence": 0.72,
                    "rule": "ga.tipologia.patas_alzado",
                    "inferred_region": {"page": alzado["page"], "bbox": alzado["bbox"]},
                },
            }
            clasificacion[tipo] = (72, tipo_candidato)
    paquete = dataset_filename(nombre)
    _inferir_por_familia(clasificacion, tag or (paquete.tag if paquete else ""))
    candidatos.extend(c for _, c in clasificacion.values())
    pendientes = []
    for aparicion in descartados:
        literal = aparicion["locator"].upper()
        marca = expandir_marcas(literal)[0]
        pieza = registro.get(("bom_item", literal))
        boquilla = registro.get(("nozzle", marca)) if pieza is None or literal == marca else None
        entradas = [entrada for entrada in (pieza, boquilla) if entrada is not None]
        if len(entradas) == 1:
            entradas[0]["appearances"].append(aparicion)
        else:
            razon = "id ambiguo" if entradas else "id sin fila en las tablas del GA"
            pendientes.append({"text": aparicion["locator"], "reason": razon, **aparicion})
    ids = {marca: entrada for (tipo, marca), entrada in registro.items() if tipo == "nozzle"}
    for (tipo, marca), entrada in registro.items():
        if tipo == "bom_item":
            if marca in ids:
                ids[f"bom_item__{marca}"] = {"id": marca, **entrada}
            else:
                ids[marca] = entrada
    rotulos = []
    for page, pagina in rotulos_por_pagina:
        for rotulo, marca, asociacion, confianza in asociar(
            pagina, ids, page.page_number, expandir_marcas
        ):
            dato = _candidato(
                documento,
                page,
                rotulo.caja,
                rotulo.texto,
                f"nozzles.{marca}.{rotulo.campo}",
                rotulo.valor,
                "mm" if rotulo.campo == "elevation" else "deg",
            )
            dato["source"]["confidence"] = confianza
            dato["association"] = asociacion
            rotulos.append(dato)
    salida = {
        "identifiers": ids,
        "identifiers_discarded": pendientes,
        "candidates": candidatos,
        "nozzle_labels": rotulos,
        "warnings": avisos,
    }
    if len(tablas_boquillas) == 1 and tablas_boquillas[0] is not None:
        salida["nozzle_schedule"] = tablas_boquillas[0]
    if (paquete := dataset_filename(nombre)) is not None and paquete.kind == "GA":
        salida["equipment_tag"] = paquete.tag.upper()
        if paquete.revision:
            salida["revision"] = f"rev{paquete.revision.lower()}"
    return salida

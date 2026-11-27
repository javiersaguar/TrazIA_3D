"""Cotas de posición en vistas vectoriales con referencias explícitas."""

import math
import re
from collections import defaultdict
from contextlib import closing
from itertools import product

from pdfplumber.utils import cluster_objects

from ..extraction import Candidate
from ..model import InferredRegion, Source
from ..reference import internal_azimuth

_CAJA = ("x0", "top", "x1", "bottom")
_ANGULO = re.compile(r"(0|90|180|270)\s*[°º�]")
_RUMBO = re.compile(r"(0|45|90|135|180|225|270|315)\s*[°º�]")
_ESTACION = re.compile(r"([+−-]\s*\d{2,5})(?![\d.,])")
_ORIGEN = re.compile(r"(?<!\d)0[.,]0+\s*\(\s*REF\.?\s*\)", re.I)
_DATUM = re.compile(r"\bT\s*\.\s*L\.?\s+EL\.?\s*0[.,]0+(?!\d)", re.I)
_TANGENTES = re.compile(r"\b(\d{3,5})\s*\(?\s*T\.\s*L\.\s+TO\s+T\.\s*L\.", re.I)
_CERO_TANGENTE = re.compile(r"T\.\s*L\.\s*EL\.?\s*\+?\s*0[.,]0+", re.I)
_COTA_AXIAL = re.compile(r"EL\.?\s*\+\s*(\d{2,5}(?:[.,]\d+)?)", re.I)
_VISTA_EXTREMO = re.compile(r"VIEW\s+[`'‘]?\s*([A-Z])-\1\s*['’]?", re.I)
_NOTA_PROYECCION = re.compile(
    r"\bNOZZLE PROJECTIONS?\b.*\b(CENT(?:ER|RE)\s*LINE|HORIZONTAL LINE)\s*/\s*TANGENT\s+LINE\b"
    r".*\bDISH(?:ED)?\s+END\b",
    re.I,
)


def _caja(item):
    return tuple(item[k] for k in _CAJA)


def _centro(item):
    return ((item["x0"] + item["x1"]) / 2, (item["top"] + item["bottom"]) / 2)


def _region(*items):
    return (
        min(x["x0"] for x in items),
        min(x["top"] for x in items),
        max(x["x1"] for x in items),
        max(x["bottom"] for x in items),
    )


def _candidato(page, documento, marca, campo, valor, dibujos, texto, canal, regla):
    x0, y0, x1, y1 = _region(*dibujos)
    c = 0.86 if canal == "cota" else 0.74
    return Candidate(
        path=f"nozzles.{marca}.{campo}",
        value=valor,
        unit="deg" if campo in {"azimuth", "bearing"} else "mm",
        source=Source(
            document_id=documento,
            page=page.page_number,
            bbox=(x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height),
            locator=texto,
            confidence=c,
            rule=regla,
        ),
        channel=canal,
        confidence_raw=c,
        text_original=texto,
    )


def _globos(page, palabras, marcas):
    # Los globos CAD son curvas cerradas. Exigir su perímetro excluye textos de la lista y notas.
    curvas = [
        curva
        for curva in page.curves
        if 8 <= curva["width"] <= 40
        and abs(curva["width"] - curva["height"]) <= 0.15 * curva["width"]
        and len(curva["pts"]) >= 5
        and math.dist(curva["pts"][0], curva["pts"][-1]) < 1
    ]
    globos = []
    for palabra in palabras:
        marca = palabra["text"].upper()
        x, y = _centro(palabra)
        if marca not in marcas:
            continue
        for curva in curvas:
            cx, cy = _centro(curva)
            if math.dist((x, y), (cx, cy)) <= 0.18 * curva["width"]:
                globos.append((marcas[marca], palabra, curva))
                break
    return globos


def _rosas(palabras, *, tolerancia_lateral=0.1):
    rotulos = defaultdict(list)
    for palabra in palabras:
        if dato := _ANGULO.fullmatch(palabra["text"]):
            rotulos[int(dato[1])].append(palabra)
    for norte, este, sur, oeste in product(*(rotulos[a] for a in (0, 90, 180, 270))):
        nx, ny = _centro(norte)
        ex, ey = _centro(este)
        sx, sy = _centro(sur)
        ox, oy = _centro(oeste)
        ancho, alto = ex - ox, sy - ny
        if (
            min(ancho, alto) >= 65
            and 0.55 < ancho / alto < 1.55
            and abs(nx - sx) < 0.1 * ancho
            and abs(ey - oy) < tolerancia_lateral * alto
            and abs((ex + ox) / 2 - nx) < 0.18 * ancho
            and abs((sy + ny) / 2 - ey) < 0.18 * alto
        ):
            yield norte, este, sur, oeste


def _grupo(globos, indice):
    usados = {indice}
    pendientes = [indice]
    while pendientes:
        base = globos[pendientes.pop()][2]
        for i, (_, _, curva) in enumerate(globos):
            if i in usados:
                continue
            if math.dist(_centro(base), _centro(curva)) <= (base["width"] + curva["width"]) / 2 + 2:
                usados.add(i)
                pendientes.append(i)
    return [globos[i] for i in sorted(usados)]


def _azimuts_horizontales(page, palabras, globos, documento, canal):
    lecturas = defaultdict(dict)
    for norte, este, sur, oeste in _rosas(palabras):
        ancho = _centro(este)[0] - _centro(oeste)[0]
        for angulo, orientacion, sentido in ((0, norte, -1), (180, sur, 1)):
            x, y = _centro(orientacion)
            proximos = [
                (math.dist((x, y), _centro(curva)), i)
                for i, (_, _, curva) in enumerate(globos)
                if abs(x - _centro(curva)[0]) <= 0.12 * ancho
                and 0
                < sentido * (_centro(curva)[1] - y)
                <= (0.4 if canal == "vesor" else 0.28) * ancho
            ]
            if not proximos:
                continue
            _, ancla = min(proximos)
            for marca, palabra, _ in _grupo(globos, ancla):
                lecturas[marca][angulo] = _candidato(
                    page,
                    documento,
                    marca,
                    "azimuth",
                    angulo,
                    (palabra, orientacion),
                    f"{palabra['text']} · {orientacion['text']} en el extremo del recipiente",
                    canal,
                    "horizontal.angulo_cabezal",
                )
    return [next(iter(c.values())) for c in lecturas.values() if len(c) == 1]


def _verticales(page):
    caracteres = [
        c
        for c in page.chars
        if abs(c["matrix"][0]) < 0.1 and c["matrix"][1] > 0.5 and c["width"] >= 4
    ]
    for columna in cluster_objects(caracteres, "x0", 0.8):
        grupos = []
        for char in sorted(columna, key=lambda c: c["bottom"], reverse=True):
            if not grupos or grupos[-1][-1]["top"] - char["bottom"] > 5:
                grupos.append([])
            grupos[-1].append(char)
        for grupo in grupos:
            texto = "".join(c["text"] for c in grupo)
            cota = _ESTACION.match(texto)
            if cota:
                caja = _region(*grupo[: cota.end()])
                valor = float(cota[1].replace(" ", "").replace("−", "-"))
            elif _ORIGEN.search(texto):
                caja, valor = _region(*grupo), None
            else:
                continue
            yield {**dict(zip(_CAJA, caja, strict=True)), "text": texto, "valor": valor}


def _estaciones(page, lineas, globos, documento):
    if not any(re.search(r"\bFRONT\s+VIEW\b", texto, re.I) for texto, _ in lineas):
        return []
    cotas = list(_verticales(page))
    origenes = [c for c in cotas if c["valor"] is None]
    if len(origenes) != 1:
        return []
    origen = origenes[0]
    lecturas = defaultdict(dict)
    for cota in cotas:
        if cota["valor"] is None or cota["x0"] < origen["x0"]:
            continue
        x, y = _centro(cota)
        proximos = []
        for i, (_, _, curva) in enumerate(globos):
            cx, cy = _centro(curva)
            distancia = min(abs(cota["top"] - curva["bottom"]), abs(cota["bottom"] - curva["top"]))
            if abs(cx - x) <= 0.42 * curva["width"] and distancia <= 0.9 * curva["width"]:
                proximos.append((abs(cy - y), i))
        if not proximos:
            continue
        _, indice = min(proximos)
        for marca, palabra, curva in _grupo(globos, indice):
            if abs(_centro(curva)[0] - x) > 0.42 * curva["width"]:
                continue
            lecturas[marca][cota["valor"]] = _candidato(
                page,
                documento,
                marca,
                "station",
                cota["valor"],
                (palabra, cota),
                f"{palabra['text']} · {cota['text']} desde {origen['text']}",
                "cota",
                "horizontal.estacion_tangente",
            )
    return [next(iter(c.values())) for c in lecturas.values() if len(c) == 1]


def bases_horizontales(page, lineas, lecturas, candidatos):
    longitudes = {float(m[1]) for texto, _ in lineas if (m := _TANGENTES.search(texto))}
    if len(longitudes) != 1:
        return []
    longitud = longitudes.pop()
    estaciones = {
        c.path.rsplit(".", 1)[0]: c
        for c in lecturas
        if c.path.endswith(".station") and 0 < c.value < longitud
    }
    radiales = {c.path.rsplit(".", 1)[0] for c in lecturas if c.path.endswith(".azimuth")}
    bases = []
    for dato in candidatos:
        ruta = dato["path"].rsplit(".", 1)[0]
        if not (
            dato["path"].endswith(".projection_basis")
            and dato["value"] == "desconocida"
            and dato["source"]["page"] == page.page_number
            and ruta in estaciones.keys() & radiales
        ):
            continue
        original = Candidate.model_validate(dato)
        cabecera = original.source.locator
        if not re.search(r"\bCENT(?:ER|RE)\s*/\s*T\.\s*L\.", cabecera, re.I):
            continue
        estacion = estaciones[ruta]
        cita = estacion.source.model_copy(
            update={
                "locator": f"«{cabecera}» · {estacion.source.locator} · orientación radial",
                "rule": "horizontal.proyeccion_desde_eje",
                "confidence": 0.78,
                "inferred_region": InferredRegion(page=page.page_number, bbox=original.source.bbox),
            }
        )
        bases.append(
            Candidate(
                path=original.path,
                value="axis",
                unit="1",
                source=cita,
                channel="cota",
                confidence_raw=cita.confidence,
                explanation="Orientación radial y estación entre tangentes en la misma lámina.",
            )
        )
    return bases


def horizontal(page, palabras, lineas, documento, marcas, *, vesor=False):
    """Lee elevación longitudinal y orientación de cabezal para marcas de la revisión."""
    globos = _globos(page, palabras, marcas)
    angulos = _azimuts_horizontales(page, palabras, globos, documento, "vesor" if vesor else "cota")
    return angulos if vesor else [*angulos, *_estaciones(page, lineas, globos, documento)]


def _texto_girado(page):
    # La matriz de una fuente CAD puede incorporar escala y una ligera pendiente.
    caracteres = [
        c for c in page.chars if c["matrix"][1] > 0 and abs(c["matrix"][0]) < c["matrix"][1] * 0.06
    ]
    for columna in cluster_objects(caracteres, "x0", page.width / 3000):
        grupos = []
        for char in sorted(columna, key=lambda c: c["bottom"], reverse=True):
            if not grupos or grupos[-1][-1]["top"] - char["bottom"] > char["width"] * 0.45:
                grupos.append([])
            grupos[-1].append(char)
        for grupo in grupos:
            texto = "".join(c["text"] for c in grupo).strip()
            yield {**dict(zip(_CAJA, _region(*grupo), strict=True)), "text": texto}


def _cotas_axiales(textos):
    for texto in textos:
        if _CERO_TANGENTE.fullmatch(texto["text"]):
            yield {**texto, "valor": 0.0}
        elif cota := _COTA_AXIAL.fullmatch(texto["text"]):
            yield {**texto, "valor": float(cota[1].replace(",", "."))}


def _marco_axial(cotas, lineas):
    ceros = [cota for cota in cotas if cota["valor"] == 0]
    if len(ceros) != 1:
        return None
    cero = ceros[0]
    largos = {
        float(m[1])
        for texto, caja in lineas
        if caja[0] > cero["x1"] and caja[3] < cero["top"] and (m := _TANGENTES.search(texto))
    }
    if len(largos) != 1:
        return None
    largo = largos.pop()
    extremos = [
        cota
        for cota in cotas
        if cota["x0"] > cero["x1"] and abs(cota["valor"] - largo) <= 0.001 * largo
    ]
    if len(extremos) != 1:
        return None
    extremo = extremos[0]
    for texto, caja in lineas:
        if (
            texto.upper() == "ELEVATION"
            and cero["x1"] < caja[0] < caja[2] < extremo["x0"]
            and caja[1] > cero["bottom"]
        ):
            return cero, extremo, largo, caja[1]
    return None


def _hexagono(curva):
    ancho, alto = curva["width"], curva["height"]
    puntos = curva["pts"]
    if not (
        7 <= ancho <= 40
        and 0.78 * ancho < alto < 0.92 * ancho
        and len(puntos) == 7
        and math.dist(puntos[0], puntos[-1]) < 0.2
    ):
        return False
    x, y = _centro(curva)
    trazados = [((a - x) / ancho, (b - y) / alto) for a, b in puntos[:6]]
    vertices = [(-0.5, 0), (-0.25, -0.5), (0.25, -0.5), (0.5, 0), (0.25, 0.5), (-0.25, 0.5)]
    return all(any(math.dist(v, p) < 0.07 for p in trazados) for v in vertices)


def _globos_en_contorno(page, pdf_bytes, palabras, marcas, region):
    from PIL import Image, ImageDraw, ImageOps
    from pypdfium2 import PdfDocument, PdfiumError

    from ..ocr.engine import OcrUnavailable, ocr_image
    from ..pdf_limits import PDFIUM_LOCK
    from .tablas import expandir_marcas

    globos = []
    sin_texto = []
    for curva in page.curves:
        if not (_hexagono(curva) and region(curva)):
            continue
        coincidencias = [
            (p, marcas[p["text"].upper()])
            for p in palabras
            if p["text"].upper() in marcas
            and math.dist(_centro(p), _centro(curva)) < curva["width"] * 0.24
        ]
        if len(coincidencias) == 1:
            palabra, marca = coincidencias[0]
            globos.append((marca, palabra, curva))
        elif not coincidencias:
            sin_texto.append(curva)
    if not sin_texto or len(sin_texto) > 160 or page.rotation != 0:
        return globos
    try:
        recortes = []
        with PDFIUM_LOCK, PdfDocument(pdf_bytes) as pdf:
            with closing(pdf[page.page_number - 1]) as lamina:
                ancho, alto = lamina.get_size()
                if page.bbox != (0, 0, ancho, alto):
                    return globos
                for curva in sin_texto:
                    x, y = _centro(curva)
                    dx, dy = curva["width"] * 0.48, curva["height"] * 0.29
                    caja = (x - dx, alto - y - dy, ancho - x - dx, y - dy)
                    if min(caja) < 0:
                        continue
                    with closing(lamina.render(scale=100 / (2 * dx), crop=caja)) as bitmap:
                        recorte = bitmap.to_pil().convert("RGB")
                    mascara = Image.new("L", recorte.size)
                    puntos = [
                        (
                            (0.5 + 0.94 * (a - x) / (2 * dx)) * recorte.width,
                            (0.5 + 0.94 * (b - y) / (2 * dy)) * recorte.height,
                        )
                        for a, b in curva["pts"]
                    ]
                    ImageDraw.Draw(mascara).polygon(puntos, fill=255)
                    limpio = Image.composite(
                        recorte, Image.new("RGB", recorte.size, "white"), mascara
                    )
                    estrecho = limpio.crop((11, 0, limpio.width - 11, limpio.height))
                    recortes.append((curva, (limpio, estrecho)))
        inventario = set(marcas.values())
        for curva, variantes in recortes:
            for recorte in variantes:
                lecturas = ocr_image(
                    ImageOps.expand(recorte, border=4, fill="white"), single_line=True
                )
                if len(lecturas) != 1 or lecturas[0].score < 0.9:
                    continue
                texto = lecturas[0].text
                ids = expandir_marcas(texto)
                if len(ids) == 1 and ids[0] in inventario:
                    globos.append((ids[0], {**curva, "text": texto}, curva))
                    break
    except (OcrUnavailable, PdfiumError, OSError):
        pass
    return globos


def _estaciones_desde_tangente(page, documento, marco, cotas, globos):
    cero, extremo, largo, pie = marco
    lecturas = defaultdict(dict)
    for marca, palabra, globo in globos:
        x, y = _centro(globo)
        if not cero["x1"] < x < extremo["x0"] or y >= pie:
            continue
        cerca = []
        for cota in cotas:
            valor = cota["valor"]
            if not 0 < valor < largo:
                continue
            cx, _ = _centro(cota)
            if (
                abs(cx - x) <= 0.61 * globo["width"]
                and abs((cx - cero["x1"]) / (extremo["x0"] - cero["x1"]) - valor / largo) < 0.08
                and min(abs(cota["top"] - globo["bottom"]), abs(cota["bottom"] - globo["top"]))
                <= 0.9 * globo["height"]
            ):
                cerca.append(cota)
        if len(cerca) == 1:
            cota = cerca[0]
            lecturas[marca][cota["valor"]] = _candidato(
                page,
                documento,
                marca,
                "station",
                cota["valor"],
                (palabra, cota),
                f"{palabra['text']} · {cota['text']} en ELEVATION · datum {cero['text']}",
                "cota",
                "horizontal.estacion_desde_tangente_izquierda",
            )
    return [next(iter(valores.values())) for valores in lecturas.values() if len(valores) == 1]


def _azimuts_en_secciones(page, documento, secciones, globos):
    lecturas = defaultdict(dict)
    for titulo, norte, este, sur, oeste in secciones:
        ancho = _centro(este)[0] - _centro(oeste)[0]
        for angulo, rotulo in ((0, norte), (180, sur)):
            x = _centro(sur)[0]
            y = _centro(rotulo)[1]
            candidatos = [
                (abs(_centro(curva)[0] - x), abs(_centro(curva)[1] - y), i)
                for i, (_, _, curva) in enumerate(globos)
                if abs(_centro(curva)[0] - x) < curva["width"] * 0.42
                and 0 < y - _centro(curva)[1] < ancho * 0.19
            ]
            if not candidatos:
                continue
            _, _, indice = min(candidatos, key=lambda v: (v[1], v[0]))
            ancla = globos[indice][2]
            grupo = [globos[indice]] if angulo == 180 else _grupo(globos, indice)
            for marca, palabra, curva in grupo:
                gx, gy = _centro(curva)
                ax, ay = _centro(ancla)
                apilado = (
                    abs(gx - ax) < ancla["width"] * 0.2 and 0 < ay - gy <= 1.05 * ancla["height"]
                )
                if abs(gy - ay) > ancla["height"] * 0.3 and not apilado:
                    continue
                lecturas[marca][angulo] = _candidato(
                    page,
                    documento,
                    marca,
                    "azimuth",
                    angulo,
                    (palabra, rotulo),
                    f"{palabra['text']} · {rotulo['text']} en {titulo}",
                    "cota",
                    "horizontal.angulo_en_seccion",
                )
    return [next(iter(valores.values())) for valores in lecturas.values() if len(valores) == 1]


def _sentido_de_corte(page, palabras, titulo, marco):
    """Las dos flechas del alzado fijan hacia dónde mira la sección."""
    letra = _VISTA_EXTREMO.fullmatch(titulo)[1]
    cero, extremo, _, pie = marco
    flechas = []
    for rotulo in palabras:
        if (
            rotulo["text"].strip("`'‘’") != letra
            or rotulo["text"] == letra
            or rotulo["x0"] >= extremo["x0"]
            or rotulo["top"] >= pie
        ):
            continue
        x, y = _centro(rotulo)
        alto = rotulo["bottom"] - rotulo["top"]
        puntas = []
        for curva in page.curves:
            cx, cy = _centro(curva)
            if not (
                0 < cx - x < 3 * alto
                and abs(cy - y) < 0.4 * alto
                and 0.45 * alto < curva["width"] < 1.2 * alto
                and len(curva["pts"]) == 4
            ):
                continue
            a, b, c, d = curva["pts"]
            if a == d and a[0] == b[0] and abs(c[1] - (a[1] + b[1]) / 2) <= alto * 0.1:
                puntas.append((1 if c[0] > a[0] else -1, curva))
        if len(puntas) == 1:
            flechas.append((puntas[0][0], rotulo, puntas[0][1]))
    if len(flechas) == 2 and flechas[0][0] == flechas[1][0]:
        return flechas[0]
    return None


def _montaje_inferior(page, documento, marco, secciones, globos, palabras, angulos, estaciones):
    cero, extremo, longitud, pie = marco
    escala = (_centro(extremo)[0] - _centro(cero)[0]) / longitud
    por_marca = {c.path.split(".")[1]: c for c in estaciones}
    for titulo, _, _, sur, _ in secciones:
        centros = [
            c.path.split(".")[1]
            for c in angulos
            if c.value == 180 and c.source.locator.endswith(titulo)
        ]
        if len(centros) != 1 or not (mirada := _sentido_de_corte(page, palabras, titulo, marco)):
            continue
        centro = centros[0]
        x, y = _centro(sur)
        anclas = [
            g
            for m, _, g in globos
            if m == centro
            and abs(_centro(g)[0] - x) < g["width"] * 0.45
            and 0 < y - _centro(g)[1] < 2 * g["height"]
        ]
        if len(anclas) != 1:
            continue
        ancla = anclas[0]
        ax, ay = _centro(ancla)
        ancho, alto = ancla["width"], ancla["height"]
        prueba = []
        for marca, palabra, globo in globos:
            gx, gy = _centro(globo)
            if not (0.65 * ancho < abs(gx - ax) < 1.3 * ancho and abs(gy - ay) < alto * 0.65):
                continue
            cotas = [
                p
                for p in palabras
                if p["text"].isdecimal()
                and abs((_centro(p)[0] - (ax + gx) / 2)) < 0.25 * ancho
                and 0.9 * alto < gy - _centro(p)[1] < 3 * alto
                and 0.8 * abs(gx - ax) < int(p["text"]) * escala < 1.2 * abs(gx - ax)
            ]
            if len(cotas) == 1:
                prueba.append((marca, palabra, globo, cotas[0], gx - ax))

        # Los dos ramales deben estar acotados respecto al mismo eje en la sección.
        if len(prueba) != 2 or prueba[0][-1] * prueba[1][-1] >= 0:
            continue
        sentido, rotulo, flecha = mirada
        for marca, palabra, globo, cota, dx in prueba:
            # Con X creciendo hacia la derecha del alzado, mirar según +X invierte
            # la coordenada horizontal de la sección respecto a +Y del IFC.
            offset = math.copysign(float(cota["text"]), -sentido * dx)
            prueba_angular = (palabra, ancla, cota)
            yield _candidato(
                page,
                documento,
                marca,
                "azimuth",
                180,
                prueba_angular,
                f"{marca} · ramal vertical paralelo a {centro} en {titulo}",
                "cota",
                "horizontal.angulo_en_seccion",
            )
            yield _candidato(
                page,
                documento,
                marca,
                "offset_lateral_mm",
                offset,
                (*prueba_angular, rotulo, flecha),
                f"{marca} · {cota['text']} de desplazamiento en {titulo} · corte en alzado",
                "cota",
                "horizontal.desplazamiento_en_seccion",
            )
            if marca in por_marca:
                continue
            otra = next((p for p in prueba if p[0] in por_marca), None)
            if otra is None:
                continue
            vecinos = [
                (a, b)
                for m, _, a in globos
                for n, _, b in globos
                if m == marca
                and n == otra[0]
                and _centro(a)[1] > pie
                and _centro(b)[1] > pie
                and abs(_centro(a)[0] - _centro(b)[0]) <= 0.15 * ancho
                and abs(_centro(a)[1] - _centro(b)[1]) > 3 * alto
            ]
            elevados = [
                g
                for m, _, g in globos
                if m == marca
                and _centro(g)[0] < extremo["x1"] + 2 * ancho
                and _centro(g)[1] < pie
                and any(
                    n == otra[0]
                    and abs(_centro(g)[1] - _centro(h)[1]) < 0.3 * alto
                    and 0.65 * ancho < abs(_centro(g)[0] - _centro(h)[0]) < 1.6 * ancho
                    for n, _, h in globos
                )
            ]
            for a, b in vecinos:
                if not any(
                    0.65 * ancho < abs(_centro(g)[0] - _centro(b)[0]) < 1.6 * ancho
                    for g in elevados
                ):
                    continue
                estacion = por_marca[otra[0]]
                yield _candidato(
                    page,
                    documento,
                    marca,
                    "station",
                    estacion.value,
                    (a, b),
                    f"{marca} y {otra[0]} alineadas en PLAN VIEW · {estacion.source.locator}",
                    "cota",
                    "horizontal.estacion_desde_tangente_izquierda",
                )
                break


def _proyeccion_tipo_inferior(page, documento, angulos, secciones, girados, candidatos):
    referencias = {
        c["path"].split(".")[1]: m[1]
        for c in candidatos
        if c["path"].endswith(".projection_reference")
        and (m := re.fullmatch(r"REFER\s+(?:TO\s+)?SKETCH/(\d{3,5})", c["value"], re.I))
    }
    for titulo, _, este, sur, oeste in secciones:
        ancho = _centro(este)[0] - _centro(oeste)[0]
        for angulo in angulos:
            marca = angulo.path.split(".")[1]
            if (
                marca not in referencias
                or angulo.value != 180
                or not angulo.source.locator.endswith(titulo)
            ):
                continue
            cotas = [
                p
                for p in girados
                if re.fullmatch(rf"{referencias[marca]}\s*\(TYP\.\)", p["text"], re.I)
                and este["x0"] < p["x0"] < este["x1"] + 0.5 * ancho
                and este["top"] <= _centro(p)[1] <= sur["bottom"]
            ]
            if len(cotas) == 1:
                cota = cotas[0]
                yield _candidato(
                    page,
                    documento,
                    marca,
                    "projection",
                    float(referencias[marca]),
                    (cota,),
                    f"{marca} · {cota['text']} para el ramal inferior en {titulo}",
                    "cota",
                    "horizontal.proyeccion_tipica_inferior",
                )


def _pendiente_alzado(page, palabras, lineas, marco):
    cero, extremo, _, pie = marco
    ancho = extremo["x0"] - cero["x0"]
    wp = [
        p
        for p in palabras
        if p["text"] == "W.P."
        and cero["x0"] < p["x0"] < cero["x0"] + ancho * 0.07
        and cero["bottom"] < p["top"] < pie
    ]
    refs = [
        (texto, caja)
        for texto, caja in lineas
        if re.search(r"\bREF\.\s+HORIZONTAL\s+LINE\b", texto, re.I)
        and cero["x0"] < caja[0] < extremo["x0"]
        and cero["bottom"] < caja[1] < pie
    ]
    if len(wp) != 1 or len(refs) != 1:
        return None
    for rotulo in palabras:
        if rotulo["text"] != "SLOPE" or not cero["x0"] < rotulo["x0"] < extremo["x0"]:
            continue
        x, y = _centro(rotulo)
        if not pie - ancho * 0.07 < y < pie:
            continue
        alto = rotulo["bottom"] - rotulo["top"]
        componentes = [
            p
            for p in palabras
            if p["text"].isdecimal()
            and abs(_centro(p)[0] - x) <= 2 * alto
            and y < _centro(p)[1] < y + 2 * alto
        ]
        if len(componentes) != 2:
            continue
        numerador, denominador = sorted(componentes, key=lambda p: p["top"])
        subida, avance = int(numerador["text"]), int(denominador["text"])
        if not 0 < subida < avance * 0.1:
            continue
        for curva in page.curves:
            if not (curva["x0"] < x < curva["x1"] and y <= _centro(curva)[1] < y + alto):
                continue
            if len(curva["pts"]) != 4:
                continue
            punta, alta, baja, base = curva["pts"]
            if (
                alta[0] == baja[0]
                and alta[1] < baja[1]
                and alta[0] < punta[0] <= base[0]
                and punta[1] == baja[1] == base[1]
            ):
                return (
                    subida / avance,
                    (rotulo, numerador, denominador, wp[0]),
                    f"{subida}/{avance}",
                )
    return None


def _proyeccion_en_seccion(page, documento, angulos, secciones, girados):
    # Una cota individual está flanqueada por la marca girada y la regla de dimensión de
    # la vista. Las cotas «TYP.» se quedan como referencia general de la tabla.
    for titulo, norte, este, _, oeste in secciones:
        ancho = _centro(este)[0] - _centro(oeste)[0]
        for angulo in angulos:
            if angulo.value != 0 or not angulo.source.locator.endswith(titulo):
                continue
            marca = angulo.path.split(".")[1]
            rotulos = [
                p
                for p in girados
                if p["text"] == marca
                and oeste["x0"] - 0.65 * ancho < p["x0"] < oeste["x0"]
                and norte["bottom"] < p["top"] < oeste["top"]
            ]
            if len(rotulos) != 1:
                continue
            rotulo = rotulos[0]
            _, y = _centro(rotulo)
            ancho_texto = rotulo["x1"] - rotulo["x0"]
            cotas = [
                p
                for p in girados
                if re.fullmatch(r"\d{3,5}", p["text"])
                and 0 < p["x0"] - rotulo["x0"] <= 1.5 * ancho_texto
                and abs(_centro(p)[1] - y) <= ancho_texto
            ]
            if len(cotas) == 1:
                cota = cotas[0]
                yield _candidato(
                    page,
                    documento,
                    marca,
                    "projection",
                    float(cota["text"]),
                    (rotulo, cota),
                    f"{marca} · {cota['text']} en {titulo}",
                    "cota",
                    "horizontal.proyeccion_individual",
                )


def alzado_con_tangente(page, palabras, lineas, documento, marcas, datos, candidatos):
    titulos = [(t, caja) for t, caja in lineas if _VISTA_EXTREMO.fullmatch(t)]
    if not titulos or not any(t.upper() == "ELEVATION" for t, _ in lineas):
        return []
    girados = list(_texto_girado(page))
    cotas = list(_cotas_axiales(girados))
    if not (marco := _marco_axial(cotas, lineas)):
        return []
    secciones = [
        (titulo, norte, este, sur, oeste)
        for norte, este, sur, oeste in _rosas(palabras)
        for titulo, caja in titulos
        if oeste["x0"] < caja[0] < caja[2] < este["x1"]
        and 0 < caja[1] - sur["bottom"] < _centro(sur)[1] - _centro(este)[1]
    ]
    if not secciones:
        return []

    cero, extremo, _, pie = marco
    pie_planta = next(
        (
            b[1]
            for t, b in lineas
            if t.upper() == "PLAN VIEW" and b[1] > pie and cero["x0"] < b[0] < extremo["x1"]
        ),
        pie,
    )

    def region(curva):
        x, y = _centro(curva)
        return (cero["x0"] < x < extremo["x1"] + curva["width"] and y < pie_planta) or any(
            oeste["x0"] < x < este["x1"]
            and norte["top"] - 0.25 * (sur["bottom"] - norte["top"]) < y < sur["bottom"]
            for _, norte, este, sur, oeste in secciones
        )

    globos = _globos_en_contorno(page, datos, palabras, marcas, region)
    estaciones = _estaciones_desde_tangente(page, documento, marco, cotas, globos)
    angulos = _azimuts_en_secciones(page, documento, secciones, globos)
    montaje = list(
        _montaje_inferior(page, documento, marco, secciones, globos, palabras, angulos, estaciones)
    )
    estaciones.extend(c for c in montaje if c.path.endswith(".station"))
    angulos.extend(c for c in montaje if c.path.endswith(".azimuth"))
    desniveles = []
    if pendiente := _pendiente_alzado(page, palabras, lineas, marco):
        tasa, figuras, texto = pendiente
        for estacion in estaciones:
            marca = estacion.path.split(".")[1]
            desniveles.append(
                _candidato(
                    page,
                    documento,
                    marca,
                    "projection_datum_offset",
                    tasa * estacion.value,
                    figuras,
                    f"SLOPE {texto} · W.P. en la tangente izquierda · {estacion.source.locator}",
                    "cota",
                    "horizontal.desnivel_desde_linea_horizontal",
                )
            )
    return [
        *estaciones,
        *angulos,
        *desniveles,
        *(c for c in montaje if c.path.endswith(".offset_lateral_mm")),
        *_proyeccion_en_seccion(page, documento, angulos, secciones, girados),
        *_proyeccion_tipo_inferior(page, documento, angulos, secciones, girados, candidatos),
    ]


def notas_proyeccion_radial(page, lineas):
    for texto, caja in lineas:
        if nota := _NOTA_PROYECCION.search(texto):
            base = "horizontal_ref" if nota[1].upper() == "HORIZONTAL LINE" else "axis"
            texto = re.split(r"\s+[B-Z]\)\s+", texto, maxsplit=1)[0]
            yield page, texto, dict(zip(_CAJA, caja, strict=True)), base


def base_eje_por_seccion(documento, notas, posiciones, candidatos):
    if len(notas) != 1:
        return []
    page, nota, caja, base = notas[0]
    estaciones = {
        c.path.rsplit(".", 1)[0]
        for c in posiciones
        if c.source.rule == "horizontal.estacion_desde_tangente_izquierda"
    }
    secciones = {
        c.path.rsplit(".", 1)[0]
        for c in posiciones
        if c.source.rule == "horizontal.angulo_en_seccion"
    }
    if base == "horizontal_ref":
        secciones &= {
            c.path.rsplit(".", 1)[0]
            for c in posiciones
            if c.source.rule == "horizontal.desnivel_desde_linea_horizontal"
        }
    medidas = {
        c["path"].rsplit(".", 1)[0]
        for c in candidatos
        if c["path"].endswith(".projection_basis") and c["value"] == "desconocida"
    }
    medidas.update(
        c.path.rsplit(".", 1)[0]
        for c in posiciones
        if c.source.rule == "horizontal.proyeccion_tipica_inferior"
    )
    bases = []
    for ruta in sorted(medidas & estaciones & secciones):
        marca = ruta.split(".")[1]
        valor = _candidato(
            page,
            documento,
            marca,
            "projection_basis",
            base,
            (caja,),
            nota,
            "cota",
            "horizontal.proyeccion_seccion_desde_eje",
        )
        bases.append(valor.model_copy(update={"unit": "1"}))
    return bases


def _globo_hexagonal(palabra, lineas):
    x, y = _centro(palabra)
    alto = palabra["bottom"] - palabra["top"]
    borde = ([], [])
    for linea in lineas:
        if linea["height"] > 0.3 or not 0.65 * alto <= linea["width"] <= 2.5 * alto:
            continue
        lx, ly = _centro(linea)
        if abs(lx - x) <= 0.48 * alto and 0.48 * alto <= abs(ly - y) <= 1.2 * alto:
            borde[ly > y].append(linea)
    return bool(borde[0] and borde[1])


def _norte_vertical(page, palabras, centro, radio):
    cx, cy = centro
    for palabra in palabras:
        x, y = _centro(palabra)
        if palabra["text"].upper() != "N" or not (
            0.8 * radio < abs(x - cx) < 2.4 * radio and 0.8 * radio < cy - y < 1.55 * radio
        ):
            continue
        ejes = [
            linea
            for linea in page.lines
            if linea["width"] <= 0.4
            and 0.12 * radio <= linea["height"] <= 0.65 * radio
            and abs(linea["x0"] - x) < 3
            and 0 <= linea["top"] - y <= 0.20 * radio
        ]
        for eje in ejes:
            punta = [
                linea
                for linea in page.lines
                if abs(linea["top"] - eje["top"]) < 1
                and 0.8 < linea["width"] < 7
                and 4 < linea["height"] < 0.24 * radio
                and abs(_centro(linea)[0] - x) < 4
            ]
            if len(punta) >= 2:
                return palabra, eje
    return None


def vertical(page, palabras, lineas, documento, marcas, elevaciones, candidatos):
    lecturas = []
    entradas = defaultdict(list)
    radiales = {
        c["path"].rsplit(".", 1)[0] for c in candidatos if c["path"].endswith(".projection")
    }
    elevadas = {c["path"].rsplit(".", 1)[0] for c in elevaciones if c["value"] > 0}
    titulos = [dict(zip(_CAJA, caja, strict=True)) for t, caja in lineas if t.upper() == "TOP VIEW"]
    for norte, este, sur, oeste in _rosas(palabras, tolerancia_lateral=0.25):
        x = (_centro(norte)[0] + _centro(sur)[0]) / 2
        y = _centro(este)[1]
        radio = (_centro(sur)[1] - _centro(norte)[1]) / 2
        if not any(
            abs(_centro(t)[0] - x) < 0.4 * radio and radio < _centro(t)[1] - y < 1.8 * radio
            for t in titulos
        ):
            continue
        marco = _norte_vertical(page, palabras, (x, y), radio)
        marcas_angulares = {}
        for p in palabras:
            if (dato := _RUMBO.fullmatch(p["text"])) and 0.65 * radio < math.dist(
                (x, y), _centro(p)
            ) < 1.5 * radio:
                marcas_angulares[int(dato[1])] = p
        # Cotas de detalle con forma de identificador quedan fuera de los globos del plano.
        trazos = [
            linea
            for linea in page.lines
            if abs(_centro(linea)[0] - x) < 1.6 * radio and abs(_centro(linea)[1] - y) < 1.6 * radio
        ]
        for p in palabras:
            if (marca := marcas.get(p["text"].upper())) is None:
                continue
            px, py = _centro(p)
            distancia = math.dist((x, y), (px, py))
            if not 0.9 * radio < distancia < 1.6 * radio or not _globo_hexagonal(p, trazos):
                continue
            rumbo = math.degrees(math.atan2(px - x, y - py)) % 360
            sector = (round(rumbo / 45) * 45) % 360
            if abs((rumbo - sector + 180) % 360 - 180) > 14 or sector not in marcas_angulares:
                continue
            entradas[marca].append((sector, p, marcas_angulares[sector], marco))
    for marca, valores in entradas.items():
        if len({v[0] for v in valores}) != 1:
            continue
        sector, globo, rotulo, marco = valores[0]
        texto = f"{globo['text']} · {rotulo['text']} en TOP VIEW"
        lecturas.append(
            _candidato(
                page,
                documento,
                marca,
                "bearing",
                sector,
                (globo, rotulo),
                texto,
                "geometria",
                "vertical.rumbo_planta",
            )
        )
        ruta = f"nozzles.{marca}"
        if ruta in radiales and ruta in elevadas:
            valor = internal_azimuth(sector, north_deg=90, clockwise=True)
            if marco:
                dibujos, cita, regla = (globo, rotulo, *marco), " · flecha N y giro horario", None
            else:
                # Sin flecha N, la escala angular del plano (0° arriba, giro horario de la rosa)
                # hace de marco, como en el oro. Queda supuesta para la revisión humana.
                dibujos, cita, regla = (globo, rotulo), " · 0° arriba y giro horario", "plano"
            candidato = _candidato(
                page,
                documento,
                marca,
                "azimuth",
                valor,
                dibujos,
                texto + cita,
                "geometria",
                "vertical.azimut_escala_plano" if regla else "vertical.azimut_desde_norte",
            )
            if regla:
                candidato = candidato.model_copy(
                    update={
                        "state": "assumed",
                        "explanation": "El plano no dibuja el Norte: el azimut se toma en su "
                        "escala angular (0° arriba, sentido horario).",
                    }
                )
            lecturas.append(candidato)
    datum = next((texto for texto, _ in lineas if _DATUM.search(texto)), None)
    if datum:
        for dato in elevaciones:
            if dato["source"]["page"] != page.page_number or not dato["path"].endswith(
                ".elevation"
            ):
                continue
            candidato = {k: v for k, v in dato.items() if k != "association"}
            candidato["source"] = {**dato["source"], "rule": "vertical.elevacion_tangente"}
            candidato["explanation"] = f"Cota relativa a la tangente inferior «{datum}»."
            candidato["channel"] = "cota"
            candidato["confidence_raw"] = candidato["source"]["confidence"]
            lecturas.append(Candidate.model_validate(candidato))
    return lecturas

"""Dimensiones de virola, fondos y apoyos con referencia a la vista que las acota."""

import math
import re
from collections import defaultdict

from pdfplumber.utils import cluster_objects

_BOX = ("x0", "top", "x1", "bottom")
_NUM = r"[0-9]+(?:[.,][0-9]+)?"
_DIAMETRO = rf"(?:[Ø⌀]\s*)?(?:I\.?D\.?|INT\.?)\s*[:=]?\s*[Ø⌀]?\s*({_NUM})"
_VIROLA = re.compile(
    rf"\bSHELL\s+{_DIAMETRO}\s*MM?\s*;?\s*"
    rf"DES\.?\s*=\s*({_NUM})\s*[X×]\s*({_NUM}).*?\bTHK\.?\s*({_NUM})",
    re.I,
)
_FONDO = re.compile(rf"\bEL+IPSOIDAL HEAD\s+2\s*:\s*1.*?\bH=\s*({_NUM})\s*MM", re.I)
# Faldilla recta del fondo («h= 50mm», en minúscula; «H=» es la profundidad).
_FALDILLA = re.compile(rf"(?i:EL+IPSOIDAL HEAD)\s+2\s*:\s*1.*?(?<![A-Za-z])h=\s*({_NUM})\s*(?i:MM)")
# «T.L. TO T.L.» y también «TL. to TL.» (81V01).
_TANGENTES = re.compile(rf"\b({_NUM})\s*\(?T\s*\.?\s*L\.\s*TO\s*T\s*\.?\s*L\.", re.I)
_CARA = re.compile(rf"^({_NUM})\s*\(\s*T\.?L\.?\s*TO\s+F\.?F\.?", re.I)
_DATUM = re.compile(r"\bT\s*\.L\.?\s+EL\.?\s*0[.,]0+(?!\d)", re.I)
_APOYO = re.compile(r"\b([A-Z]+\d+[A-Z]?)\s+\d+\s+(SLIDING|FIXED)\s+SADDLE\b", re.I)
_TRAMO = re.compile(rf"^({_NUM})\s*[X×]\s*({_NUM})\s+(\d+)\.(\d+)$", re.I)
_ESCALA_SECCION = re.compile(r"^SECTION\s+.+?\(\s*1\s*:\s*(\d+)\s*\)$", re.I)


def _n(valor):
    return float(valor.replace(",", "."))


def _centro(caja):
    x0, y0, x1, y1 = caja
    return (x0 + x1) / 2, (y0 + y1) / 2


def _union(*cajas):
    return (
        min(c[0] for c in cajas),
        min(c[1] for c in cajas),
        max(c[2] for c in cajas),
        max(c[3] for c in cajas),
    )


def _unico(lineas, patron, grupos=1):
    resultados = {}
    for texto, bbox in lineas:
        for dato in patron.finditer(texto):
            clave = tuple(dato[i] for i in range(1, grupos + 1))
            resultados.setdefault(clave, (dato[0], bbox))
    if len(resultados) == 1:
        return next(iter(resultados.items()))
    return None


def rotados(page):
    """Reconstruye los rótulos girados 90° por matriz PDF, incluidos puntos y signos."""
    caracteres = [
        c
        for c in page.chars
        if abs(c["matrix"][0]) < 0.1
        and c["matrix"][1] > 0.5
        and c["width"] >= 4
        and 0 <= c["x0"] < c["x1"] <= page.width
        and 0 <= c["top"] < c["bottom"] <= page.height
    ]
    for columna in cluster_objects(caracteres, "x0", 0.8):
        grupos = []
        for char in sorted(columna, key=lambda c: c["bottom"], reverse=True):
            if not grupos or grupos[-1][-1]["top"] - char["bottom"] > 5:
                grupos.append([])
            grupos[-1].append(char)
        for grupo in grupos:
            yield (
                "".join(c["text"] for c in grupo).strip(),
                _union(*(tuple(c[k] for k in _BOX) for c in grupo)),
            )


def _cotas_verticales(page, etiquetas, *, inicio=None):
    """Busca la línea de dimensión adyacente y comprueba la relación de escala."""
    lineas = [trazo for trazo in page.lines if trazo["width"] < 0.3 and trazo["height"] > 50]
    for texto, caja in etiquetas:
        if not re.fullmatch(_NUM, texto) or (valor := _n(texto)) < 250:
            continue
        x, y = _centro(caja)
        cerca = [
            linea
            for linea in lineas
            if -2 <= linea["x0"] - x <= 24
            and abs((linea["top"] + linea["bottom"]) / 2 - y) <= 10
            and (inicio is None or abs(inicio - linea["top"]) <= 10)
        ]
        for trazo in cerca:
            yield valor, texto, caja, trazo


def _vertical(page, lineas, filas, etiquetas):
    virola = _unico(filas, _VIROLA, 4)
    if not virola or not any(re.search(r"\bLATERAL VIEW\b", t, re.I) for t, _ in lineas):
        return []
    (d, h, desarrollo, espesor), (texto, bbox) = virola
    diametro, alto = _n(d), _n(h)
    if not math.isclose(_n(desarrollo), math.pi * (diametro + _n(espesor)), rel_tol=0.05):
        return []
    out = [
        ("diameter", diametro, "mm", texto, bbox, "ga.virola_diametro_interior", None),
        (
            "attributes.diameter_basis",
            "inside",
            "1",
            texto,
            bbox,
            "ga.virola_diametro_interior",
            None,
        ),
        ("attributes.shell_height", alto, "mm", texto, bbox, "ga.virola_desarrollo_axial", None),
    ]
    if fondo := _unico(lineas, _FONDO):
        (valor,), (cita, caja) = fondo
        out.append(("head_depth", _n(valor), "mm", cita, caja, "ga.fondo_cota_h", None))
    if faldilla := _unico(lineas, _FALDILLA):
        (valor,), (cita, caja) = faldilla
        out.append(
            (
                "attributes.head_straight_flange",
                _n(valor),
                "mm",
                cita,
                caja,
                "ga.fondo_faldilla_h",
                None,
            )
        )
    # `height` es de la T.L. a la cara de la brida del cuerpo si el plano la acota (como el oro);
    # si no, el desarrollo axial de la virola. El desarrollo va siempre en `shell_height`.
    if a_cara := _unico(etiquetas, _CARA):
        (valor,), (cita, caja) = a_cara
        out += [
            ("height", _n(valor), "mm", cita, caja, "ga.tl_a_cara", None),
            ("attributes.height_to_flange", _n(valor), "mm", cita, caja, "ga.tl_a_cara", None),
        ]
    else:
        out.append(("height", alto, "mm", texto, bbox, "ga.virola_desarrollo_axial", None))
    if tapa := next(((t, b) for t, b in lineas if t.upper() == "TOP FLANGE COVER"), None):
        out.append(
            (
                "attributes.upper_closure",
                "blind_flange",
                "1",
                tapa[0],
                tapa[1],
                "ga.tapa_embridada",
                None,
            )
        )
    if not any(re.search(r'DETAIL\s+"?LEG(?:S)?\b', t, re.I) for t, _ in lineas):
        return out
    placas = _unico(filas, re.compile(r"\b\d+\s+([1-9]\d?)\s+BASE PLATE\b", re.I))
    perfiles = _unico(filas, re.compile(r"\b\d+\s+([1-9]\d?)\s+ANGLE PROFILE\b", re.I))
    if placas and perfiles and placas[0] == perfiles[0]:
        (valor,), (cita, caja) = perfiles
        out.append(("legs.count", int(valor), "1", cita, caja, "ga.patas_lista_materiales", None))
    datums = [(texto, caja) for texto, caja in lineas if _DATUM.search(texto)]
    medidas = {}
    for datum, c in datums:
        for valor, texto, caja, trazo in _cotas_verticales(page, etiquetas, inicio=c[3]):
            if _centro(caja)[0] < c[2] and trazo["top"] >= c[1]:
                medidas[valor] = (f"{texto} · {datum}", _union(caja, c))
    if len(medidas) == 1:
        valor, (texto, caja) = next(iter(medidas.items()))
        out.append(("legs.height", valor, "mm", texto, caja, "ga.patas_desde_tangente", None))
    return out


def _espesor_comun(lineas, tangentes, longitud):
    alto = tangentes[3] - tangentes[1]
    y = _centro(tangentes)[1]
    fila = [(texto, caja) for texto, caja in lineas if alto < y - _centro(caja)[1] < 3 * alto]
    tramos = sorted(
        ((dato, caja) for texto, caja in fila if (dato := _TRAMO.fullmatch(texto))),
        key=lambda tramo: tramo[1][0],
    )
    if len(tramos) < 2:
        return None
    primero, ultimo = tramos[0][1], tramos[-1][1]
    if not primero[0] < _centro(tangentes)[0] < ultimo[2]:
        return None
    if any(abs(_centro(caja)[1] - _centro(primero)[1]) > alto / 3 for _, caja in tramos):
        return None
    referencias = [(int(dato[3]), int(dato[4])) for dato, _ in tramos]
    if any(a[0] != b[0] or a[1] + 1 != b[1] for a, b in zip(referencias, referencias[1:])):
        return None
    espesores = {_n(dato[2]) for dato, _ in tramos}
    if len(espesores) != 1:
        return None
    extremos = [
        (texto, caja, rotulo)
        for texto, caja in fila
        if re.fullmatch(_NUM, texto)
        and (caja[2] < primero[0] or caja[0] > ultimo[2])
        and abs(_centro(caja)[1] - _centro(primero)[1]) <= alto / 3
        for nota, rotulo in lineas
        if nota.upper().replace(" ", "") == "S.F."
        and abs(_centro(rotulo)[0] - _centro(caja)[0]) < alto / 2
        and 0 <= rotulo[1] - caja[3] < alto
    ]
    lados = {b[2] < primero[0] for _, b, _ in extremos}
    if extremos and (len(extremos) != 2 or len(lados) != 2):
        return None
    total = sum(_n(dato[1]) for dato, _ in tramos) + sum(_n(t) for t, _, _ in extremos)
    if not math.isclose(total, longitud, rel_tol=0, abs_tol=1):
        return None
    espesor = next(iter(espesores))
    if not 0 < espesor < min(_n(dato[1]) for dato, _ in tramos):
        return None
    cita = " · ".join([*(dato[0] for dato, _ in tramos), *(f"{t} S.F." for t, _, _ in extremos)])
    caja = _union(tangentes, *(b for _, b in tramos), *(b for _, a, c in extremos for b in (a, c)))
    # Virolas de la cadena, en orden desde la T.L. izquierda: la primera empieza tras el S.F.
    estacion = sum(_n(t) for t, b, _ in extremos if b[2] < primero[0])
    virolas = []
    for dato, caja_tramo in tramos:
        virolas.append((f"{dato[3]}-{dato[4]}", _n(dato[1]), estacion, dato[0], caja_tramo))
        estacion += _n(dato[1])
    return espesor, cita, caja, virolas


def _ancho_silleta_movil(page, lineas, fundacion):
    titulo, ref = fundacion
    alto = ref[3] - ref[1]
    escala = _unico(
        [(t, b) for t, b in lineas if 0 < ref[1] - b[1] <= 2 * alto and b[0] <= ref[0] <= b[2]],
        _ESCALA_SECCION,
    )
    if not escala:
        return None
    (factor,), (seccion, caja_seccion) = escala
    mm_por_punto = int(factor) * 25.4 / 72
    rotulos = [
        _union(a, b)
        for t, a in lineas
        if t.upper() == "SLIDING" and 0 < a[1] - ref[1] <= 24 * alto
        for s, b in lineas
        if s.upper() == "SADDLE" and abs(a[0] - b[0]) <= 1 and 0 < b[1] - a[1] <= 2 * alto
    ]
    perfiles = [
        (r, rotulo)
        for rotulo in rotulos
        for r in page.rects
        if 0 < rotulo[0] - r["x1"] <= 4 * alto
        and alto < r["width"] < 5 * alto
        and r["height"] >= 4 * r["width"]
        and ref[3] < r["top"] < rotulo[1] < r["bottom"]
        and any(
            abs(llamada["x0"] - r["x1"]) <= 0.5
            and rotulo[1] <= llamada["top"] <= rotulo[3] + alto
            and llamada["width"] > 2
            and llamada["height"] > 2
            for llamada in page.lines
        )
    ]
    if len(perfiles) != 1:
        return None
    perfil, rotulo = perfiles[0]
    anclajes = sorted(
        (
            c
            for c in page.curves
            if perfil["x0"] < c["x0"] < c["x1"] < perfil["x1"]
            and 0 < c["top"] - perfil["top"] < 2 * alto
            and 0.2 * alto < c["width"] < 0.7 * alto
            and math.isclose(c["width"], c["height"], rel_tol=0.1)
        ),
        key=lambda c: c["x0"],
    )
    if len(anclajes) != 2 or abs(anclajes[0]["top"] - anclajes[1]["top"]) > 1:
        return None
    primero, segundo = anclajes
    separacion = (segundo["x0"] + segundo["x1"] - primero["x0"] - primero["x1"]) / 2
    cotas = [
        (t, b)
        for t, b in lineas
        if re.fullmatch(_NUM, t)
        and 0 <= perfil["x0"] - b[2] <= 3 * alto
        and 0 < perfil["top"] - b[3] <= 3 * alto
        and math.isclose(_n(t), separacion * mm_por_punto, rel_tol=0.02)
    ]
    if len(cotas) != 1:
        return None
    cota, caja_cota = cotas[0]
    medida = perfil["width"] * mm_por_punto
    caja = _union(caja_seccion, rotulo, caja_cota, tuple(perfil[k] for k in _BOX))
    texto = f"{seccion} · {titulo} · Sliding Saddle · {cota}"
    return 5 * round(medida / 5), texto, caja


def _horizontal(page, lineas, filas, palabras, etiquetas):
    if not any(re.search(r"\bHORIZONTAL VESSEL\b", t, re.I) for t, _ in lineas):
        return []
    capa = list(lineas)
    diam = _unico(capa, re.compile(_DIAMETRO + rf"\s*[X×]\s*{_NUM}\s*MM", re.I))
    largo = _unico(capa, _TANGENTES)
    if not diam or not largo:
        return []
    (diametro,), (cita_d, caja_d) = diam
    (longitud,), (cita_l, caja_l) = largo
    d, largo_mm = _n(diametro), _n(longitud)
    out = [
        ("horizontal.diameter", d, "mm", cita_d, caja_d, "ga.virola_diametro_interior", None),
        (
            "attributes.diameter_basis",
            "inside",
            "1",
            cita_d,
            caja_d,
            "ga.virola_diametro_interior",
            None,
        ),
        ("horizontal.length", largo_mm, "mm", cita_l, caja_l, "ga.distancia_tangentes", None),
    ]
    if cadena := _espesor_comun(capa, caja_l, largo_mm):
        espesor, cita, caja, virolas = cadena
        out.append(
            (
                "attributes.shell_thickness",
                espesor,
                "mm",
                f"{cita} · {cita_l}",
                caja,
                "ga.espesor_tramos_virola",
                None,
            )
        )
        # J6: cada tramo es una virola; su estación fija las costuras circunferenciales.
        for pos, largo_v, estacion, cita_v, caja_v in virolas:
            base = f"shell.courses.{pos}"
            out += [
                (f"{base}.height", largo_v, "mm", cita_v, caja_v, "ga.tramos_virola", None),
                (f"{base}.thickness", espesor, "mm", cita_v, caja_v, "ga.tramos_virola", None),
                (
                    f"{base}.station",
                    estacion,
                    "mm",
                    f"{cita_v} · {cita}",
                    _union(caja_v, caja),
                    "ga.tramos_virola",
                    None,
                ),
            ]
    if forma := next(
        ((t, b) for t, b in capa if re.search(r"\bELLIPSOIDAL HEAD 2:1\b", t, re.I)), None
    ):
        out.append(
            (
                "horizontal.head_depth",
                d / 4,
                "mm",
                f"{forma[0]} · {cita_d}",
                _union(forma[1], caja_d),
                "ga.fondo_elipsoidal_2_a_1",
                "assumed",
            )
        )
    marcas = {m[1].upper(): m[2].upper() for t, _ in filas for m in _APOYO.finditer(t)}
    posiciones = {}
    for palabra in palabras:
        marca = palabra["text"].upper()
        if marca not in marcas:
            continue
        px, py = _centro(tuple(palabra[k] for k in _BOX))
        for texto, caja in etiquetas:
            if not re.fullmatch(r"\+\d{2,5}", texto):
                continue
            x, y = _centro(caja)
            if abs(px - x) < 9 and 0 < py - y < 55 and _n(texto) < largo_mm:
                posiciones[marcas[marca]] = (
                    _n(texto),
                    f"{texto} {marca} {marcas[marca]} SADDLE",
                    _union(caja, tuple(palabra[k] for k in _BOX)),
                )
    if posiciones.keys() == {"SLIDING", "FIXED"}:
        for i, (valor, cita, caja) in enumerate(sorted(posiciones.values())):
            out.append(
                (
                    f"horizontal.saddle_positions.{i}",
                    valor,
                    "mm",
                    cita,
                    caja,
                    "ga.silleta_estacion",
                    None,
                )
            )
    if fundacion := next(((t, b) for t, b in capa if t.upper() == "FOUNDATION PLAN"), None):
        _, ref = fundacion
        anchos_fijos = [
            (t, b)
            for t, b in capa
            if re.fullmatch(_NUM, t)
            and 40 < _n(t) < d / 4
            and ref[2] < b[0]
            and 0 < b[1] - ref[1] < 1.6 * (ref[3] - ref[1])
            and any(s.upper() == "FIXED" and abs(c[2] - b[0]) < 30 and c[1] > b[3] for s, c in capa)
        ]
        ancho_fijo = None
        if len(anchos_fijos) == 1:
            texto, caja = anchos_fijos[0]
            ancho_fijo = _n(texto)
            out.append(
                (
                    "attributes.saddle_width_fixed",
                    ancho_fijo,
                    "mm",
                    f"{texto} · Fixed Saddle · {fundacion[0]}",
                    caja,
                    "ga.silleta_fija_ancho_en_planta",
                    None,
                )
            )
        if ancho_movil := _ancho_silleta_movil(page, capa, fundacion):
            valor, cita, caja = ancho_movil
            regla = "ga.silleta_movil_medida_a_escala"
            out.append(
                ("attributes.saddle_width_sliding", valor, "mm", cita, caja, regla, "assumed")
            )
            if valor == ancho_fijo:
                out.append(("horizontal.saddle_width", valor, "mm", cita, caja, regla, "assumed"))
    pares = defaultdict(list)
    for valor, texto, caja, trazo in _cotas_verticales(page, etiquetas):
        if valor < d and _centro(caja)[0] < caja_l[2]:
            pares[valor].append((texto, caja, trazo))
    apoyos = []
    for valor, opciones in pares.items():
        for texto, a, uno in opciones:
            if any(
                abs(otro["top"] - uno["top"]) < 3
                and abs(otro["bottom"] - uno["bottom"]) < 3
                and abs(otro["x0"] - uno["x0"]) > 80
                for _, _, otro in opciones
            ):
                apoyos.append((valor, texto, a, uno))
                break
    if len(apoyos) == 1:
        valor, texto, caja, trazo = apoyos[0]
        out.append(
            (
                "horizontal.support_height",
                valor,
                "mm",
                texto,
                _union(caja, tuple(trazo[k] for k in _BOX)),
                "ga.silleta_base_a_eje",
                None,
            )
        )
        anchos = {}
        for texto, b in capa:
            if not re.fullmatch(_NUM, texto) or not 0.75 * d < _n(texto) < d:
                continue
            x, y = _centro(b)
            if x < caja_l[0] and 0 < y - trazo["bottom"] < 0.75 * trazo["height"]:
                anchos[_n(texto)] = (texto, b)
        if len(anchos) == 1:
            valor, (texto, b) = next(iter(anchos.items()))
            out.append(
                (
                    "horizontal.saddle_span",
                    valor,
                    "mm",
                    texto,
                    b,
                    "ga.silleta_ancho_transversal",
                    None,
                )
            )
    return out


_METROS = re.compile(rf"^[Ø⌀]?\s*({_NUM})\s*m$", re.I)


def _seguidas(palabras, primera, segunda):
    """Pares de palabras `primera` y `segunda` seguidas en la misma línea."""
    for a in palabras:
        if a["text"].upper() != primera:
            continue
        for b in palabras:
            if (
                b["text"].upper() == segunda
                and abs(b["top"] - a["top"]) < 2
                and 0 <= b["x0"] - a["x1"] < 3 * (a["bottom"] - a["top"])
            ):
                yield a, b


def _tanque(palabras):
    """Diámetro interior y altura del cilindro de la tabla de datos del GA de un tanque.

    La cabecera es «Inside diameter · Cyl. height» y los valores van en metros en la fila de debajo
    («Ø20,0m x tank», «23,4m»). Solo se lee con una cabecera y un valor bajo cada columna.
    """
    cabeceras = [
        (d, c)
        for d in _seguidas(palabras, "INSIDE", "DIAMETER")
        for c in _seguidas(palabras, "CYL.", "HEIGHT")
        if abs(c[0]["top"] - d[0]["top"]) < 2 and c[0]["x0"] > d[1]["x1"]
    ]
    if len(cabeceras) != 1:
        return []
    (inside, _), (cyl, height) = cabeceras[0]
    alto = inside["bottom"] - inside["top"]
    valores = sorted(
        (
            p
            for p in palabras
            if 0.5 * alto < p["top"] - inside["top"] < 3 * alto
            and inside["x0"] - 2 * alto <= p["x0"] <= height["x1"] + 8 * alto
            and _METROS.match(p["text"])
        ),
        key=lambda p: p["x0"],
    )
    # Uno a cada lado del comienzo de «Cyl. height».
    if len(valores) != 2 or not valores[0]["x0"] < cyl["x0"] <= valores[1]["x1"]:
        return []
    caja = _union(*(tuple(p[k] for k in _BOX) for p in (inside, height, *valores)))
    diametro = round(_n(_METROS.match(valores[0]["text"])[1]) * 1000)
    altura = round(_n(_METROS.match(valores[1]["text"])[1]) * 1000)
    cita_d = f"Inside diameter {valores[0]['text']}"
    cita_h = f"Cyl. height {valores[1]['text']}"
    regla_d = "ga.tanque_diametro_interior"
    return [
        ("tank.diameter", diametro, "mm", cita_d, caja, regla_d, None),
        ("attributes.diameter_basis", "inside", "1", cita_d, caja, regla_d, None),
        ("tank.height", altura, "mm", cita_h, caja, "ga.tanque_altura_cilindro", None),
    ]


def leer_envolvente(page, lineas, filas, palabras):
    tanque = _tanque(palabras)
    if not any(re.search(r"\b(?:LATERAL VIEW|HORIZONTAL VESSEL)\b", t, re.I) for t, _ in lineas):
        return tanque
    etiquetas = list(rotados(page))
    return (
        tanque
        + _vertical(page, lineas, filas, etiquetas)
        + _horizontal(page, lineas, filas, palabras, etiquetas)
    )

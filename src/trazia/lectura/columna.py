"""Columna: diámetro, tangentes, faldón y tramos citados en el alzado del GA.

El alzado de una columna dibuja las dos líneas de tangente («T.L.»), el suelo («GROUND»), las
marcas de las virolas de la lista de materiales y los diámetros interiores («D.I. Ø…»). Las cotas
principales (entre tangentes y del faldón) son texto vectorial girado sin capa de texto: se leen
con el OCR en mosaico y solo valen si caen en su sitio del alzado y cuadran con la lista de
materiales. Ningún valor se inventa: si una comprobación falla, el campo no sale y el ensamblado
sigue pidiéndolo.
"""

import io
import math
import re

import pdfplumber

from ..ocr.engine import OcrUnavailable
from ..ocr.pdf_words import lines_in_pdf_points

_TL = re.compile(r"T\s*\.\s*L\s*\.")
_DI = re.compile(r"(?:D\.I\.|I\.D\.)", re.I)
_PHI = re.compile(r"^[OØøΦφ](\d{3,5})$")
_TRAMO = re.compile(r"^V\d{2}$")
_ENTERO = re.compile(r"^\d{3,5}$")
# Las pestañas rectas de los dos fondos caben entre la suma de virolas y la cota entre tangentes.
_HOLGURA_TANGENTES = 0.03
_HOLGURA_FALDON = 0.10


def _centro(caja):
    return (caja["x0"] + caja["x1"]) / 2, (caja["top"] + caja["bottom"]) / 2


def _cita(page, caja, texto, regla, confianza=0.85):
    return {
        "document_id": None,
        "page": page.page_number,
        "bbox": [
            caja["x0"] / page.width,
            caja["top"] / page.height,
            caja["x1"] / page.width,
            caja["bottom"] / page.height,
        ],
        "locator": texto,
        "text_original": texto,
        "confidence": confianza,
        "rule": regla,
    }


def _candidato(documento, page, caja, texto, ruta, valor, unidad, regla, canal, explicacion):
    fuente = _cita(page, caja, texto, regla)
    fuente["document_id"] = documento
    return {
        "path": ruta,
        "value": valor,
        "unit": unidad,
        "source": fuente,
        "channel": canal,
        "explanation": explicacion,
    }


def _diametros(palabras):
    """Rótulos «D.I. / I.D. Ø4150»: valor y caja de cada uno, en el orden de la página."""
    salida = []
    for palabra in palabras:
        dato = _PHI.fullmatch(palabra["text"])
        if not dato:
            continue
        x, y = _centro(palabra)
        prefijo = [
            otra
            for otra in palabras
            if otra is not palabra
            and abs(_centro(otra)[1] - y) < 2.5
            and 0 <= palabra["x0"] - otra["x1"] < 40
            and _DI.search(otra["text"])
        ]
        if prefijo:
            texto = " ".join(p["text"] for p in sorted(prefijo, key=lambda p: p["x0"]))
            caja = {
                "x0": min(p["x0"] for p in [*prefijo, palabra]),
                "x1": max(p["x1"] for p in [*prefijo, palabra]),
                "top": min(p["top"] for p in [*prefijo, palabra]),
                "bottom": max(p["bottom"] for p in [*prefijo, palabra]),
            }
            salida.append((float(dato[1]), caja, f"{texto} {palabra['text']}", y))
    return salida


def _tramos(candidatos, documento):
    tramos = {}
    for dato in candidatos:
        match = re.fullmatch(r"shell\.courses\.(V\d{2})\.(height|thickness)", dato["path"])
        if match and dato["source"]["document_id"] == documento:
            tramos.setdefault(match[1], {})[match[2]] = dato
    return {k: v for k, v in tramos.items() if "height" in v}


def _cota_ocr(lineas, x_min, x_max, y_min, y_max):
    valores = {}
    for linea in lineas:
        texto = linea["text"].strip()
        if not _ENTERO.fullmatch(texto):
            continue
        x, y = _centro(linea)
        # Cota vertical: el texto girado es más alto que ancho.
        if (
            x_min <= x <= x_max
            and y_min < y < y_max
            and linea["bottom"] - linea["top"] > (linea["x1"] - linea["x0"])
        ):
            valores.setdefault(int(texto), linea)
    return valores


def leer_columna(pdf: bytes, documento: str, candidatos: list[dict], avisos: list[str]):
    """Candidatos de geometría de columna de un GA, o [] si el alzado no se reconoce."""
    tramos = _tramos(candidatos, documento)
    if not tramos:
        return []
    with pdfplumber.open(io.BytesIO(pdf)) as pdf_doc:
        for page in pdf_doc.pages:
            palabras = page.extract_words(x_tolerance=1, y_tolerance=2)
            tangentes = sorted((p for p in palabras if _TL.search(p["text"])), key=_cy)
            marcas = {p["text"]: p for p in palabras if _TRAMO.fullmatch(p["text"])}
            if len(tangentes) < 2 or not set(tramos) <= set(marcas):
                continue
            salida = _leer_alzado(page, palabras, tangentes, marcas, tramos, pdf, documento, avisos)
            page.close()
            return salida
    return []


def _cy(palabra):
    return _centro(palabra)[1]


def _leer_alzado(page, palabras, tangentes, marcas, tramos, pdf, documento, avisos):
    superior, inferior = tangentes[0], tangentes[-1]
    suelo = next(
        (
            p
            for p in sorted(palabras, key=_cy)
            if p["text"].upper() == "GROUND" and p["top"] > inferior["bottom"]
        ),
        None,
    )
    salida = []
    rotulos = _diametros(palabras)
    virola = [r for r in rotulos if superior["bottom"] < r[3] < inferior["top"]]
    if len({r[0] for r in virola}) != 1:
        avisos.append(f"Columna {documento}: sin un diámetro interior único entre tangentes.")
        return salida
    diametro, caja_d, texto_d, _ = virola[0]
    explicacion_d = "Diámetro interior rotulado entre las tangentes del alzado."
    salida.append(
        _candidato(
            documento,
            page,
            caja_d,
            texto_d,
            "diameter",
            diametro,
            "mm",
            "ga.columna_diametro_interior",
            "cota",
            explicacion_d,
        )
    )
    salida.append(
        _candidato(
            documento,
            page,
            caja_d,
            texto_d,
            "attributes.diameter_basis",
            "inside",
            "1",
            "ga.columna_diametro_interior",
            "cota",
            "El rótulo dice D.I. / I.D.: diámetro interior.",
        )
    )
    # Tramos por su marca en el alzado: entre tangentes la virola, debajo el faldón.
    cuerpo = sorted(
        (t for t in tramos if superior["bottom"] < _cy(marcas[t]) < inferior["top"]),
        key=lambda t: -_cy(marcas[t]),
    )
    faldon = sorted(
        (t for t in tramos if _cy(marcas[t]) > inferior["bottom"]), key=lambda t: _cy(marcas[t])
    )
    if not cuerpo:
        return salida
    try:
        lineas = lines_in_pdf_points(pdf, documento, pages=[page.page_number], tiles=True)
        lineas = lineas.get(page.page_number, [])
    except (OcrUnavailable, OSError) as error:
        avisos.append(f"Columna {documento}: OCR no disponible para las cotas giradas ({error}).")
        lineas = []
    x_min = min(t["x0"] for t in tangentes) - 0.05 * page.width
    x_max = max(t["x1"] for t in tangentes) + 0.05 * page.width
    suma = sum(tramos[t]["height"]["value"] for t in cuerpo)
    tramo_medio = (superior["bottom"] + inferior["top"]) / 2
    alto = inferior["top"] - superior["bottom"]
    cotas = _cota_ocr(lineas, x_min, x_max, tramo_medio - 0.2 * alto, tramo_medio + 0.2 * alto)
    validas = {v: c for v, c in cotas.items() if suma <= v <= suma * (1 + _HOLGURA_TANGENTES)}
    if len(validas) != 1:
        avisos.append(
            f"Columna {documento}: la cota entre tangentes no cuadra con las virolas "
            f"(suma {suma:g} mm; leído {sorted(cotas) or 'nada'})."
        )
        return salida
    ((altura, caja_h),) = validas.items()
    salida.append(
        _candidato(
            documento,
            page,
            caja_h,
            str(altura),
            "height",
            float(altura),
            "mm",
            "ga.columna_tangentes_ocr",
            "ocr",
            f"Cota girada entre las dos «T.L.» del alzado; las virolas {cuerpo[-1]}–{cuerpo[0]} "
            f"suman {suma:g} mm y el resto son las pestañas rectas de los fondos.",
        )
    )
    for orden, tramo in enumerate(cuerpo, 1):
        marca = marcas[tramo]
        salida.append(
            _candidato(
                documento,
                page,
                marca,
                tramo,
                f"column.sections.{tramo}.order",
                orden,
                "1",
                "ga.columna_orden_alzado",
                "geometria",
                "Orden de abajo arriba según la marca del tramo en el alzado.",
            )
        )
        salida.append(
            _candidato(
                documento,
                page,
                caja_d,
                texto_d,
                f"column.sections.{tramo}.diameter",
                diametro,
                "mm",
                "ga.columna_diametro_interior",
                "cota",
                explicacion_d + " El tramo se modela con el diámetro interior.",
            )
        )
    if not faldon or suelo is None:
        return salida
    suma_f = sum(tramos[t]["height"]["value"] for t in faldon)
    cotas_f = _cota_ocr(lineas, x_min, x_max, inferior["bottom"], suelo["top"])
    validas_f = {v: c for v, c in cotas_f.items() if suma_f <= v <= suma_f * (1 + _HOLGURA_FALDON)}
    if len(validas_f) == 1:
        ((altura_f, caja_f),) = validas_f.items()
        salida.append(
            _candidato(
                documento,
                page,
                caja_f,
                str(altura_f),
                "skirt_height",
                float(altura_f),
                "mm",
                "ga.columna_faldon_ocr",
                "ocr",
                f"Cota girada entre la «T.L.» inferior y el suelo; los tramos {faldon[0]}–"
                f"{faldon[-1]} del faldón suman {suma_f:g} mm.",
            )
        )
    else:
        avisos.append(
            f"Columna {documento}: la cota del faldón no cuadra con sus tramos "
            f"(suma {suma_f:g} mm; leído {sorted(cotas_f) or 'nada'})."
        )
    principal = max(faldon, key=lambda t: tramos[t]["height"]["value"])
    espesor = tramos[principal].get("thickness")
    rotulos_f = [r for r in rotulos if inferior["bottom"] < r[3] < suelo["top"]]
    if espesor is None or not rotulos_f:
        return salida
    salida.append(
        {
            **{k: v for k, v in espesor.items() if k not in ("path", "association")},
            "path": "skirt_thickness",
            "source": {**espesor["source"], "rule": "ga.columna_faldon_espesor"},
            "explanation": f"Espesor del tramo más alto del faldón ({principal}).",
        }
    )
    interior, caja_s, texto_s, _ = min(rotulos_f, key=lambda r: abs(r[3] - _cy(marcas[principal])))
    exterior = interior + 2 * espesor["value"]
    if not math.isfinite(exterior) or exterior <= 0:
        return salida
    salida.append(
        _candidato(
            documento,
            page,
            caja_s,
            texto_s,
            "attributes.skirt_diameter",
            exterior,
            "mm",
            "ga.columna_faldon_diametro_exterior",
            "cota",
            f"Diámetro interior {interior:g} mm del tramo {principal} más dos espesores de "
            f"{espesor['value']:g} mm: diámetro exterior del faldón.",
        )
    )
    return salida


_DATUM_EL = re.compile(r"^EL\.?\s*[±+]?\s*0(?:[.,]0+)?$", re.I)
_RUMBO_EJE = re.compile(r"^(90|270)\s*[°º]$")
_TITULO_PLANTA = re.compile(r"ORIENTACIONES|TOP\s+VIEW|ORIENTATIONS", re.I)
# Un globo se dibuja junto a su boquilla, no sobre su eje: el ángulo se mide sobre la planta,
# se redondea a 5° y queda como supuesto para la revisión humana.
_PASO_AZIMUT = 5
_NOTA_EJE = re.compile(r"CENT(?:ER|RE)\s*LINE\s+OF\s+VESSEL\s+TO\s+FLANGE\s+FACE", re.I)
_DISPERSION_MAXIMA = 8


def posiciones(page, palabras, lineas, documento, marcas, elevaciones):
    """Cota EL. desde la tangente inferior y ángulo en planta de las boquillas de una columna."""
    from ..extraction import Candidate
    from ..model import Source

    lecturas = []
    # En un alzado tumbado los rótulos van girados y pdfplumber los da al revés
    # («0+.LE» es «EL.+0» junto a «B.T.L.»): se prueban en los dos sentidos.
    tangentes = [caja for texto, caja in lineas if any(_TL.search(t) for t in _sentidos(texto))]
    datum = next(
        (
            (_derecho(texto, _DATUM_EL), caja)
            for texto, caja in lineas
            if _derecho(texto, _DATUM_EL)
            and any(
                (abs(caja[1] - t[3]) < 15 and abs(caja[0] - t[0]) < 60) or _hueco(caja, t) < 15
                for t in tangentes
            )
        ),
        None,
    )
    if datum:
        for dato in elevaciones:
            if dato["source"]["page"] != page.page_number or not dato["path"].endswith(
                ".elevation"
            ):
                continue
            candidato = {k: v for k, v in dato.items() if k != "association"}
            candidato["source"] = {**dato["source"], "rule": "vertical.elevacion_tangente"}
            candidato["explanation"] = (
                f"Cota relativa a la tangente inferior «T.L. {datum[0]}» del alzado."
            )
            candidato["channel"] = "cota"
            candidato["confidence_raw"] = candidato["source"]["confidence"]
            lecturas.append(Candidate.model_validate(candidato))
    lecturas.extend(_bases_radiales(page, lineas, documento, elevaciones))
    ejes = [p for p in palabras if _RUMBO_EJE.fullmatch(p["text"])]
    for este, oeste in (
        (a, b)
        for a in ejes
        for b in ejes
        if a["text"].startswith("90")
        and b["text"].startswith("270")
        and abs(_cy(a) - _cy(b)) < 3
        and _centro(a)[0] > _centro(b)[0]
    ):
        x = (_centro(este)[0] + _centro(oeste)[0]) / 2
        y = _cy(este)
        radio = (_centro(este)[0] - _centro(oeste)[0]) / 2
        titulo = [
            p
            for p in palabras
            if _TITULO_PLANTA.search(p["text"])
            and abs(_centro(p)[0] - x) < 0.8 * radio
            and radio < _cy(p) - y < 1.8 * radio
        ]
        if not titulo:
            continue
        angulos = {}
        for p in palabras:
            if (marca := marcas.get(p["text"].upper())) is None:
                continue
            px, py = _centro(p)
            if not 0.9 * radio < math.dist((x, y), (px, py)) < 1.6 * radio:
                continue
            angulos.setdefault(marca, []).append(
                (math.degrees(math.atan2(px - x, y - py)) % 360, p)
            )
        for marca, valores in angulos.items():
            base = valores[0][0]
            giros = [((a - base + 180) % 360) - 180 for a, _ in valores]
            if max(giros) - min(giros) > _DISPERSION_MAXIMA:
                continue
            medio = (base + sum(giros) / len(giros)) % 360
            valor = float(round(medio / _PASO_AZIMUT) * _PASO_AZIMUT % 360)
            globo = valores[0][1]
            texto = f"{globo['text']} en {titulo[0]['text']} · 0° arriba, 90° a la derecha"
            caja = (
                min(globo["x0"], oeste["x0"]),
                min(globo["top"], este["top"]),
                max(globo["x1"], este["x1"]),
                max(globo["bottom"], este["bottom"]),
            )
            lecturas.append(
                Candidate(
                    path=f"nozzles.{marca}.azimuth",
                    value=valor,
                    unit="deg",
                    source=Source(
                        document_id=documento,
                        page=page.page_number,
                        bbox=(
                            caja[0] / page.width,
                            caja[1] / page.height,
                            caja[2] / page.width,
                            caja[3] / page.height,
                        ),
                        locator=texto,
                        confidence=0.6,
                        rule="columna.azimut_planta_medido",
                    ),
                    channel="geometria",
                    confidence_raw=0.6,
                    text_original=texto,
                    state="assumed",
                    explanation=(
                        f"Ángulo del globo medido sobre la planta ({medio:.1f}°) y redondeado a "
                        f"{_PASO_AZIMUT}°. El plano no dibuja el Norte: se usa su escala angular "
                        "(0° arriba, sentido horario)."
                    ),
                )
            )
        break
    return lecturas


def _sentidos(texto):
    return texto.strip(), texto.strip()[::-1]


def _derecho(texto, patron):
    """El texto en el sentido en que casa con el patrón, o None."""
    return next((t for t in _sentidos(texto) if patron.fullmatch(t)), None)


def _hueco(a, b):
    """Distancia entre dos cajas (x0, top, x1, bottom); 0 si se tocan."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def _bases_radiales(page, lineas, documento, elevaciones):
    """Base de la proyección de las boquillas de virola según la nota de la tabla del GA.

    La nota dice «eje del equipo a cara de brida, o tangente más próxima a cara de brida»: la
    segunda opción es la de las boquillas de los fondos. Una boquilla con su propia cota EL. en
    la virola se mide desde el eje.
    """
    from ..extraction import Candidate
    from ..model import Source

    nota = next(((t, c) for t, c in lineas if _NOTA_EJE.search(t)), None)
    if nota is None:
        # Nota general «NOZZLE PROJECTIONS … MEASURED FROM THE CENTERLINE …» repartida en líneas.
        from .columna_alzado import _NOTA_DESDE_EJE, _NOTA_PROYECCIONES

        proyecciones = page.search(_NOTA_PROYECCIONES.pattern, regex=True, case=False)
        desde_eje = page.search(_NOTA_DESDE_EJE.pattern, regex=True, case=False)
        if not (proyecciones and desde_eje):
            return []
        cita = desde_eje[0]
        nota = (
            f"{proyecciones[0]['text']} … {cita['text']}",
            (cita["x0"], cita["top"], cita["x1"], cita["bottom"]),
        )
    texto, (x0, y0, x1, y1) = nota
    marcas = sorted(
        {
            d["path"].split(".")[1]
            for d in elevaciones
            if d["path"].endswith(".elevation") and d["source"]["document_id"] == documento
        }
    )
    return [
        Candidate(
            path=f"nozzles.{marca}.projection_basis",
            value="axis",
            unit="1",
            source=Source(
                document_id=documento,
                page=page.page_number,
                bbox=(x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height),
                locator=texto,
                confidence=0.85,
                rule="ga.proyeccion_radial_desde_eje",
            ),
            channel="tabla",
            confidence_raw=0.85,
            text_original=texto,
            explanation=f"Boquilla de virola con cota EL. propia: la nota de la tabla la mide "
            f"desde el eje del equipo («{texto}»).",
        )
        for marca in marcas
    ]

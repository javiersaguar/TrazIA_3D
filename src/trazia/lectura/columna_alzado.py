"""Columna dibujada tumbada: tramos, transiciones cónicas y faldón leídos del alzado del GA.

Algunos GA de columna (BF-C-0001, BF-C-0008) dibujan el alzado en horizontal, con la tangente
superior a un lado y el faldón al otro. No tienen marcas de virola «V01…», así que `columna`
no los reconoce. Este lector usa lo que sí está en el plano:

- la cota entre tangentes, el número sobre la línea de cota con «T.T.L. … B.T.L.» debajo;
  sus extremos fijan la escala del dibujo;
- la cota que sigue en la misma línea más allá de una tangente es la altura del faldón
  (de la tangente inferior a la base), y ese lado es el de abajo;
- los rótulos girados «I.D. Ø…» entre tangentes dan los diámetros de cada tramo, y los que
  caen más allá de la tangente inferior, el del faldón;
- si hay dos diámetros, la silueta de la virola cambia de altura en el dibujo: el hueco entre
  los dos trazos es el cono de transición. Su posición se mide con la escala y se ajusta a la
  cota rotulada que coincide; si no hay cota que coincida, el valor queda como supuesto.

Si una comprobación no cuadra, el lector no devuelve nada y el ensamblado sigue pidiendo datos.
"""

import io
import re
from collections import Counter

import pdfplumber
from pdfplumber.utils import cluster_objects

_ENTERO = re.compile(r"^\d{3,6}$")
_BTL = re.compile(r"B\.?\s?T\.?\s?L", re.I)
_ID = re.compile(r"I\.?\s?D\.?", re.I)
_DIAMETRO = re.compile(r"(?:I\.?\s?D\.?\s*)?[ØOΦφϕ⌀]?\s*(\d{3,5})$", re.I)
_ESPESOR = re.compile(r"^(\d{1,2})\s*THK\.?$", re.I)
_DOS_CIFRAS = re.compile(r"^\d{1,2}$")
CONFIANZA = 0.8
# Una cota rotulada vale para un tramo medido si difieren menos de esto.
_AJUSTE = 0.03


def _centro_x(caja):
    return (caja[0] + caja[2]) / 2


def _girados(page):
    """Rótulos girados 90° (letra a letra), con umbrales relativos al tamaño de letra."""
    caracteres = [
        c
        for c in page.chars
        if abs(c["matrix"][0]) < 0.1
        and abs(c["matrix"][1]) > 0.5
        and 0 <= c["x0"] < c["x1"] <= page.width
        and 0 <= c["top"] < c["bottom"] <= page.height
    ]
    salida = []
    for columna in cluster_objects(caracteres, "x0", 0.8):
        grupos = []
        sube = columna[0]["matrix"][1] > 0
        orden = sorted(columna, key=lambda c: c["bottom"], reverse=sube)
        for char in orden:
            alto = char["bottom"] - char["top"]
            separacion = (
                (
                    grupos[-1][-1]["top"] - char["bottom"]
                    if sube
                    else char["top"] - grupos[-1][-1]["bottom"]
                )
                if grupos
                else None
            )
            if separacion is None or separacion > max(1.2, 0.9 * alto):
                grupos.append([])
            grupos[-1].append(char)
        for grupo in grupos:
            texto = "".join(c["text"] for c in grupo).strip()
            caja = (
                min(c["x0"] for c in grupo),
                min(c["top"] for c in grupo),
                max(c["x1"] for c in grupo),
                max(c["bottom"] for c in grupo),
            )
            if texto:
                salida.append((texto, caja))
    return salida


def _horizontales(page):
    """Segmentos horizontales (líneas, curvas y lados de rectángulos) como (y, x0, x1, grosor)."""
    salida = []
    for objeto in (*page.lines, *page.curves):
        puntos = objeto.get("pts") or []
        for (x0, y0), (x1, y1) in zip(puntos, puntos[1:], strict=False):
            if abs(y1 - y0) < 0.3 and abs(x1 - x0) > 1:
                salida.append((y0, min(x0, x1), max(x0, x1), objeto.get("linewidth") or 0))
    return salida


def _cadena(segmentos, y, x, holgura=2.5):
    """Extensión de la línea de cota a la altura `y` que pasa por `x`.

    Solo se unen trozos que se solapan: dos cotas seguidas de una cadena se tocan en la línea
    de referencia común y son cotas distintas.
    """
    fila = sorted((a, b) for yy, a, b, _ in segmentos if abs(yy - y) < 0.6)
    tramos = []
    for a, b in fila:
        if tramos and a < tramos[-1][1] - 0.3:
            tramos[-1][1] = max(tramos[-1][1], b)
        else:
            tramos.append([a, b])
    for a, b in tramos:
        if a - holgura <= x <= b + holgura:
            return a, b
    return None


def _siluetas(segmentos, hueco=8):
    """Trazos gruesos horizontales unidos por filas: la silueta cortada por otras líneas."""
    filas: dict[float, list[tuple[float, float]]] = {}
    for y, a, b, grosor in sorted(segmentos):
        if grosor < 0.5:
            continue
        clave = next((k for k in filas if abs(k - y) < 0.3), y)
        filas.setdefault(clave, []).append((a, b))
    salida = []
    for y, trozos in filas.items():
        unidos: list[list[float]] = []
        for a, b in sorted(trozos):
            if unidos and a - unidos[-1][1] <= hueco:
                unidos[-1][1] = max(unidos[-1][1], b)
            else:
                unidos.append([a, b])
        salida.extend((y, a, b, 1.0) for a, b in unidos if b - a > 10)
    return salida


def _cotas(palabras, segmentos):
    """Cotas horizontales: número, su caja y la extensión de la línea justo debajo."""
    salida = []
    for palabra in palabras:
        if not palabra["upright"] or not _ENTERO.fullmatch(palabra["text"]):
            continue
        alto = palabra["bottom"] - palabra["top"]
        x = (palabra["x0"] + palabra["x1"]) / 2
        filas = sorted(
            {
                round(y, 1)
                for y, a, b, _ in segmentos
                if palabra["bottom"] - 0.5 <= y <= palabra["bottom"] + 1.5 * alto
                and a - 2 <= x <= b + 2
            }
        )
        for y in filas:
            extension = _cadena(segmentos, y, x)
            if extension and extension[1] - extension[0] > 2 * (palabra["x1"] - palabra["x0"]):
                salida.append((float(palabra["text"]), palabra, y, extension))
                break
    return salida


def _cita(page, documento, caja, texto, regla, confianza=CONFIANZA):
    x0, y0, x1, y1 = caja
    return {
        "document_id": documento,
        "page": page.page_number,
        "bbox": [x0 / page.width, y0 / page.height, x1 / page.width, y1 / page.height],
        "locator": texto[:120],
        "text_original": texto[:200],
        "confidence": confianza,
        "rule": regla,
    }


def _caja(palabra):
    return (palabra["x0"], palabra["top"], palabra["x1"], palabra["bottom"])


def leer(pdf: bytes, documento: str, avisos: list[str]) -> list[dict]:
    """Candidatos de tramos y faldón de una columna dibujada en horizontal, o []."""
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            salida = _pagina(page, documento, avisos)
            page.close()
            if salida:
                return salida
    return []


def _pagina(page, documento, avisos):
    palabras = page.extract_words(x_tolerance=1.5, y_tolerance=2)
    segmentos = _horizontales(page)
    cotas = _cotas(palabras, segmentos)
    # Cota entre tangentes: «T.T.L. … B.T.L.» escrito justo debajo de su línea.
    total = None
    for valor, palabra, y, (xa, xb) in cotas:
        alto = palabra["bottom"] - palabra["top"]
        if any(
            _BTL.search(p["text"])
            and y < p["top"] < y + 3 * alto
            and xa <= (p["x0"] + p["x1"]) / 2 <= xb
            for p in palabras
        ):
            if total is None or xb - xa > total[3][1] - total[3][0]:
                total = (valor, palabra, y, (xa, xb))
    if total is None:
        return []
    altura, palabra_h, y_h, (xa, xb) = total
    escala = altura / (xb - xa)
    # Faldón: la cota más larga que arranca en una tangente y sigue hacia fuera.
    faldon = None
    for valor, palabra, _, (a, b) in cotas:
        if palabra is palabra_h:
            continue
        if abs(a - xb) < 2.5 and b > xb + 5:
            opcion = (valor, palabra, +1, b - a)
        elif abs(b - xa) < 2.5 and a < xa - 5:
            opcion = (valor, palabra, -1, b - a)
        else:
            continue
        if faldon is None or opcion[3] > faldon[3]:
            faldon = opcion
    if faldon is None:
        avisos.append(f"Columna {documento}: sin cota de faldón junto a la tangente inferior.")
        return []
    altura_f, palabra_f, lado, _ = faldon
    x_inf, x_sup = (xb, xa) if lado > 0 else (xa, xb)

    def desde_abajo(x):
        return abs(x_inf - x) * escala

    girados = _girados(page)
    gruesos = _siluetas(segmentos)
    rotulos_id = [
        caja for texto, caja in girados if _ID.search(texto) or texto.strip() in ("Ø", "⌀", "Φ")
    ]

    def ancho_dibujado(x, diametro):
        """Dos trazos de silueta que pasan por `x` separados el diámetro a escala."""
        filas = sorted({round(y, 1) for y, a, b, _ in gruesos if a <= x <= b})
        objetivo = diametro / escala
        return any(
            abs((b - a) - objetivo) < 0.08 * objetivo
            for i, a in enumerate(filas)
            for b in filas[i + 1 :]
        )

    diametros = []
    for texto, caja in girados:
        dato = _DIAMETRO.fullmatch(texto.replace(" ", ""))
        if not dato or "THK" in texto.upper() or caja[1] > y_h + 0.35 * page.height:
            continue
        x = _centro_x(caja)
        nombrado = _ID.search(texto) or re.match(r"[ØOΦφϕ⌀]", texto.replace(" ", ""))
        # Un número suelto vale como diámetro si lleva «I.D.» o «Ø» al lado o si la silueta
        # dibujada en ese punto mide ese diámetro a escala.
        if (
            not nombrado
            and not any(abs(_centro_x(r) - x) < 3 for r in rotulos_id)
            and not ancho_dibujado(x, float(dato[1]))
        ):
            continue
        diametros.append((float(dato[1]), caja, texto, x))
    cuerpo = sorted(
        (d for d in diametros if min(xa, xb) < d[3] < max(xa, xb)), key=lambda d: desde_abajo(d[3])
    )
    falda = [d for d in diametros if (d[3] - x_inf) * lado > 0]
    if not cuerpo:
        avisos.append(f"Columna {documento}: sin rótulos de diámetro interior entre tangentes.")
        return []
    grupos = []
    for d in cuerpo:
        if grupos and grupos[-1][-1][0] == d[0]:
            grupos[-1].append(d)
        else:
            grupos.append([d])
    if len({g[0][0] for g in grupos}) != len(grupos):
        avisos.append(f"Columna {documento}: los diámetros del alzado no siguen un orden claro.")
        return []

    salida = []

    def añadir(ruta, valor, unidad, caja, texto, regla, explicacion, canal="cota", supuesto=False):
        dato = {
            "path": ruta,
            "value": valor,
            "unit": unidad,
            "source": _cita(page, documento, caja, texto, regla, 0.5 if supuesto else CONFIANZA),
            "channel": canal,
            "explanation": explicacion,
        }
        if supuesto:
            dato["state"] = "assumed"
        salida.append(dato)

    caja_h, texto_h = _caja(palabra_h), f"{palabra_h['text']} T.T.L. TO B.T.L."
    añadir(
        "height",
        altura,
        "mm",
        caja_h,
        texto_h,
        "ga.columna_alzado_tangentes",
        "Cota entre la tangente superior y la inferior del alzado.",
    )
    # Transiciones: el trazo de la silueta de un tramo acaba y el del siguiente empieza
    # desplazado la diferencia de radios a escala.
    cortes = []
    for bajo, alto in zip(grupos, grupos[1:], strict=False):
        d_bajo, d_alto = bajo[0][0], alto[0][0]
        x_bajo, x_alto = bajo[-1][3], alto[0][3]
        izquierda, derecha = sorted((x_bajo, x_alto))
        salto = abs(d_bajo - d_alto) / 2 / escala
        mejor = None
        for y1, a1, b1, _ in gruesos:
            for y2, a2, b2, _ in gruesos:
                if abs(abs(y1 - y2) - salto) > 0.25 * salto:
                    continue
                # Trazo del lado de arriba de la columna que termina y del de abajo que empieza.
                if lado > 0:
                    fin, inicio = b1, a2  # arriba a la izquierda, abajo a la derecha
                else:
                    fin, inicio = b2, a1
                if izquierda < fin < inicio < derecha and inicio - fin < 0.2 * (
                    derecha - izquierda
                ):
                    # La silueta son los trazos largos: gana el par cuyo trazo más corto es mayor.
                    largo = min(b1 - a1, b2 - a2)
                    if largo > 3 * (inicio - fin) and (mejor is None or largo > mejor[2]):
                        mejor = (fin, inicio, largo)
        if mejor is None:
            avisos.append(
                f"Columna {documento}: no se ve en el dibujo la transición entre Ø{d_bajo:g} "
                f"y Ø{d_alto:g}."
            )
            return []
        cortes.append(mejor[:2])

    def ajustar(medido, extremos):
        """Cota rotulada que coincide con un tramo medido entre dos x del dibujo.

        La tolerancia es un 3 % o tres puntos del dibujo a escala, lo que sea mayor: los tramos
        cortos (un cono) se dibujan con radios de transición que mueven el trazo.
        """
        izquierda, derecha = sorted(extremos)
        tolerancia = max(_AJUSTE * medido, 3 * escala)
        for valor, palabra, _, (a, b) in cotas:
            if abs(valor - medido) > tolerancia:
                continue
            centro = (palabra["x0"] + palabra["x1"]) / 2
            if (abs(a - izquierda) < 3 and abs(b - derecha) < 3) or izquierda <= centro <= derecha:
                return valor, palabra
        for palabra in palabras:
            if not palabra["upright"] or not _ENTERO.fullmatch(palabra["text"]):
                if not (palabra["upright"] and re.fullmatch(r"\d{2,3}", palabra["text"])):
                    continue
            centro = (palabra["x0"] + palabra["x1"]) / 2
            valor = float(palabra["text"])
            if izquierda <= centro <= derecha and abs(valor - medido) <= tolerancia:
                return valor, palabra
        return None

    tramos = []
    inicio_mm = 0.0
    for i, grupo in enumerate(grupos):
        diametro, caja_d, texto_d, _ = grupo[0]
        if i < len(cortes):
            corte_bajo = cortes[i][1] if lado > 0 else cortes[i][0]
            fin_mm = desde_abajo(corte_bajo)
            cota = ajustar(fin_mm, (corte_bajo, x_inf))
            if cota is not None:
                fin_mm = cota[0]
            tramos.append((diametro, None, inicio_mm, fin_mm, caja_d, texto_d, cota))
            # El extremo alto del cono se mide desde la tangente inferior, como el bajo.
            corte_alto = cortes[i][0] if lado > 0 else cortes[i][1]
            alto_mm = desde_abajo(corte_alto)
            cota_a = ajustar(alto_mm, (corte_alto, x_inf))
            if cota_a is not None:
                alto_mm = cota_a[0]
            cono_mm = alto_mm - fin_mm
            cota_c = ajustar(cono_mm, (corte_alto, corte_bajo))
            if cota_c is not None:
                cono_mm = cota_c[0]
            d_alto = grupos[i + 1][0][0]
            tramos.append((diametro, d_alto, fin_mm, fin_mm + cono_mm, caja_d, texto_d, cota_c))
            inicio_mm = fin_mm + cono_mm
        else:
            tramos.append((diametro, None, inicio_mm, altura, caja_d, texto_d, (altura, palabra_h)))
    for orden, (diametro, superior, desde, hasta, caja_d, texto_d, cota) in enumerate(tramos, 1):
        tramo = f"T{orden}"
        alto = round(hasta - desde, 1)
        if alto <= 0:
            avisos.append(f"Columna {documento}: tramo {tramo} sin altura positiva.")
            return []
        añadir(
            f"column.sections.{tramo}.order",
            orden,
            "1",
            caja_d,
            texto_d,
            "ga.columna_alzado_orden",
            "Orden de abajo arriba desde la tangente inferior del alzado.",
            canal="geometria",
        )
        añadir(
            f"column.sections.{tramo}.diameter",
            diametro,
            "mm",
            caja_d,
            texto_d,
            "ga.columna_alzado_diametro",
            "Diámetro interior rotulado en el tramo.",
        )
        if superior is not None:
            añadir(
                f"column.sections.{tramo}.top_diameter",
                superior,
                "mm",
                caja_d,
                texto_d,
                "ga.columna_alzado_cono",
                f"Transición cónica de Ø{diametro:g} a Ø{superior:g}: la silueta cambia de "
                "altura en el dibujo.",
            )
        ultimo = orden == len(tramos)
        if ultimo:
            explicacion = (
                f"Resto de la cota entre tangentes ({altura:g} mm) tras los tramos de abajo."
                if len(tramos) > 1
                else "Tramo único: la cota entre tangentes."
            )
            añadir(
                f"column.sections.{tramo}.height",
                alto,
                "mm",
                caja_h,
                texto_h,
                "ga.columna_alzado_resto",
                explicacion,
            )
        elif cota is not None:
            caja_c = _caja(cota[1])
            añadir(
                f"column.sections.{tramo}.height",
                alto,
                "mm",
                caja_c,
                cota[1]["text"],
                "ga.columna_alzado_cota_tramo",
                f"Medida en el dibujo y confirmada por la cota rotulada {cota[1]['text']}.",
            )
        else:
            añadir(
                f"column.sections.{tramo}.height",
                alto,
                "mm",
                caja_d,
                texto_d,
                "ga.columna_alzado_medida",
                f"Longitud medida a escala en el dibujo ({escala:.2f} mm por punto); no hay "
                "cota rotulada que la confirme. A verificar.",
                canal="geometria",
                supuesto=True,
            )
    if len(grupos) == 1:
        añadir(
            "diameter",
            grupos[0][0][0],
            "mm",
            grupos[0][0][1],
            grupos[0][0][2],
            "ga.columna_alzado_diametro",
            "Diámetro interior rotulado entre tangentes.",
        )
        añadir(
            "attributes.diameter_basis",
            "inside",
            "1",
            grupos[0][0][1],
            grupos[0][0][2],
            "ga.columna_alzado_diametro",
            "El rótulo da el diámetro interior.",
        )
    añadir(
        "skirt_height",
        altura_f,
        "mm",
        _caja(palabra_f),
        palabra_f["text"],
        "ga.columna_alzado_faldon",
        "Cota que arranca en la tangente inferior y llega a la base del faldón.",
    )
    _faldon(palabras, girados, falda, x_inf, lado, altura_f / escala, añadir)
    return salida


def _faldon(palabras, girados, falda, x_inf, lado, largo, añadir):
    """Espesor y diámetro exterior del faldón, si el alzado los rotula."""
    if not falda:
        return

    def dentro(x):
        return 0 < (x - x_inf) * lado < largo + 5

    espesores = []
    for palabra in palabras:
        texto = palabra["text"].upper()
        siguiente = next(
            (
                p
                for p in palabras
                if p is not palabra
                and abs(p["top"] - palabra["top"]) < 2
                and 0 <= p["x0"] - palabra["x1"] < 12
            ),
            None,
        )
        dato = _ESPESOR.fullmatch(texto) or (
            _DOS_CIFRAS.fullmatch(texto)
            and siguiente is not None
            and siguiente["text"].upper().startswith("THK")
            and re.match(r"\d+", texto)
        )
        if palabra["upright"] and dato and dentro((palabra["x0"] + palabra["x1"]) / 2):
            espesores.append((float(dato[0].rstrip("THK. ")), _caja(palabra), f"{dato[0]} THK."))
    for texto, caja in girados:
        dato = re.fullmatch(r"(\d{1,2})(THK\.?)?", texto.replace(" ", "").upper())
        x = _centro_x(caja)
        if dato and dentro(x) and (dato[2] or any(abs(x - d[3]) < 4 for d in falda)):
            espesores.append((float(dato[1]), caja, texto))
    if not espesores:
        return
    cuenta = Counter(e[0] for e in espesores)
    espesor = max(cuenta, key=lambda v: (cuenta[v], v))
    _, caja_e, texto_e = next(e for e in espesores if e[0] == espesor)
    explicacion = "Espesor rotulado en el faldón."
    if len(cuenta) > 1:
        explicacion = (
            f"El faldón tiene rótulos de {', '.join(f'{v:g}' for v in sorted(cuenta))} mm; se "
            f"toma el más repetido ({espesor:g} mm)."
        )
    añadir(
        "skirt_thickness", espesor, "mm", caja_e, texto_e, "ga.columna_alzado_faldon", explicacion
    )
    interiores = Counter(d[0] for d in falda)
    interior = interiores.most_common(1)[0][0]
    caja_i, texto_i = next((d[1], d[2]) for d in falda if d[0] == interior)
    añadir(
        "attributes.skirt_diameter",
        interior + 2 * espesor,
        "mm",
        caja_i,
        texto_i,
        "ga.columna_alzado_faldon",
        f"Diámetro interior {interior:g} mm del faldón más dos espesores de {espesor:g} mm.",
    )


_SIGNO = re.compile(r"^[+\-−]$")
_COTA_SIGNADA = re.compile(r"^([+\-−])?(\d{2,6}(?:[.,]\d+)?)$")
_TO = re.compile(r"^TO$", re.I)
_TL_PALABRA = re.compile(r"^T\.?\s?L\.?$", re.I)
_ANGULO = re.compile(r"^(\d{1,3})\s*[°º]$")
_NOTA_PROYECCIONES = re.compile(r"NOZZLE\s+PROJECTIONS", re.I)
_NOTA_DESDE_EJE = re.compile(r"MEASURED\s+FROM\s+THE\s+CENT(?:ER|RE)\s*LINE", re.I)


def _cerca(caja, globos, alto, alcance=40):
    """Globos en la misma fila que el rótulo, a un lado y a menos de `alcance` pt."""
    x0, y0, x1, y1 = caja
    cy = (y0 + y1) / 2
    lado = []
    for globo in globos:
        if abs((globo["top"] + globo["bottom"]) / 2 - cy) > alto:
            continue
        hueco = x0 - globo["x1"] if globo["x1"] <= x0 else globo["x0"] - x1
        if 0 <= hueco <= alcance:
            lado.append((hueco, -1 if globo["x1"] <= x0 else 1, globo))
    return sorted(lado, key=lambda g: g[0])


def _globos_en_fila(caja, globos, alto, hueco=20):
    """Globos en fila a un lado del rótulo: el más cercano marca el lado y la cadena sigue."""
    cerca = _cerca(caja, globos, alto)
    if not cerca:
        return []
    _, sentido, primero = cerca[0]
    cadena = [primero]
    while True:
        borde = min(g["x0"] for g in cadena) if sentido < 0 else max(g["x1"] for g in cadena)
        cy = (cadena[-1]["top"] + cadena[-1]["bottom"]) / 2
        siguiente = next(
            (
                g
                for g in globos
                if g not in cadena
                and abs((g["top"] + g["bottom"]) / 2 - cy) <= alto
                and 0 <= (borde - g["x1"] if sentido < 0 else g["x0"] - borde) <= hueco
            ),
            None,
        )
        if siguiente is None:
            return cadena
        cadena.append(siguiente)


def posiciones(page, palabras, documento, marcas):
    """Cotas «±N TO T.L.», ángulos «NNNº» junto a los globos y base de la proyección.

    Es el formato de las columnas dibujadas tumbadas (BF-C-0001): la cota de cada boquilla
    se escribe desde la tangente inferior al lado de su globo en el alzado, y en las secciones
    el ángulo va escrito junto a los globos. En el alzado el eje del equipo es horizontal, así
    que dos globos en fila están a cotas distintas: la cota es solo del globo más cercano. En
    una sección todos los globos en fila junto al ángulo comparten orientación. Una boquilla con
    dos valores distintos no recibe ninguno.
    """
    from ..extraction import Candidate
    from ..model import Source

    rectas = [p for p in palabras if p["upright"]]
    globos = [p for p in rectas if marcas.get(p["text"].upper())]
    if not globos:
        return []
    elevaciones: dict[str, list] = {}
    angulos: dict[str, list] = {}
    for fila in cluster_objects(rectas, "top", 2):
        fila = sorted(fila, key=lambda p: p["x0"])
        for i, palabra in enumerate(fila):
            signo, j = None, i
            if _SIGNO.fullmatch(palabra["text"]) and i + 1 < len(fila):
                signo, j = palabra["text"], i + 1
            dato = _COTA_SIGNADA.fullmatch(fila[j]["text"])
            if (
                dato
                and (signo is None) != (dato[1] is None)
                and j + 2 < len(fila)
                and _TO.fullmatch(fila[j + 1]["text"])
                and _TL_PALABRA.fullmatch(fila[j + 2]["text"])
            ):
                valor = float(dato[2].replace(",", "."))
                if (signo or dato[1]) in "-−":
                    valor = -valor
                trozo = fila[i : j + 3]
                caja = (
                    trozo[0]["x0"],
                    min(p["top"] for p in trozo),
                    trozo[-1]["x1"],
                    max(p["bottom"] for p in trozo),
                )
                cerca = _cerca(caja, globos, alto=6)
                if cerca:
                    globo = cerca[0][2]
                    texto = " ".join(p["text"] for p in trozo)
                    elevaciones.setdefault(marcas[globo["text"].upper()], []).append(
                        (valor, caja, texto, globo)
                    )
            elif dato := _ANGULO.fullmatch(palabra["text"]):
                valor = float(dato[1])
                if valor >= 360:
                    continue
                caja = (palabra["x0"], palabra["top"], palabra["x1"], palabra["bottom"])
                for globo in _globos_en_fila(caja, globos, alto=6):
                    angulos.setdefault(marcas[globo["text"].upper()], []).append(
                        (valor, caja, palabra["text"], globo)
                    )

    def fuente(caja, globo, texto, regla, confianza=0.75):
        return Source(
            document_id=documento,
            page=page.page_number,
            bbox=(
                min(caja[0], globo["x0"]) / page.width,
                min(caja[1], globo["top"]) / page.height,
                max(caja[2], globo["x1"]) / page.width,
                max(caja[3], globo["bottom"]) / page.height,
            ),
            locator=f"{globo['text']} · {texto}",
            confidence=confianza,
            rule=regla,
        )

    salida = []
    for marca, valores in sorted(elevaciones.items()):
        if len({v[0] for v in valores}) != 1:
            continue
        valor, caja, texto, globo = valores[0]
        salida.append(
            Candidate(
                path=f"nozzles.{marca}.elevation",
                value=valor,
                unit="mm",
                source=fuente(caja, globo, texto, "vertical.elevacion_tangente"),
                channel="cota",
                confidence_raw=0.75,
                text_original=texto,
                explanation=f"Cota «{texto}» junto al globo {globo['text']}: medida desde la "
                "tangente inferior.",
            )
        )
    for marca, valores in sorted(angulos.items()):
        if len({v[0] for v in valores}) != 1:
            continue
        valor, caja, texto, globo = valores[0]
        salida.append(
            Candidate(
                path=f"nozzles.{marca}.azimuth",
                value=valor,
                unit="deg",
                source=fuente(caja, globo, texto, "columna.azimut_rotulado"),
                channel="cota",
                confidence_raw=0.75,
                text_original=texto,
                explanation=f"Ángulo «{texto}» escrito junto al globo {globo['text']} en una "
                "sección de la columna.",
            )
        )
    proyecciones = page.search(_NOTA_PROYECCIONES.pattern, regex=True, case=False)
    desde_eje = page.search(_NOTA_DESDE_EJE.pattern, regex=True, case=False)
    if proyecciones and desde_eje and elevaciones:
        nota = desde_eje[0]
        caja = (nota["x0"], nota["top"], nota["x1"], nota["bottom"])
        texto = f"{proyecciones[0]['text']} … {nota['text']}"
        for marca in sorted(m for m, v in elevaciones.items() if len({x[0] for x in v}) == 1):
            salida.append(
                Candidate(
                    path=f"nozzles.{marca}.projection_basis",
                    value="axis",
                    unit="1",
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
                        confidence=0.85,
                        rule="ga.proyeccion_radial_desde_eje",
                    ),
                    channel="tabla",
                    confidence_raw=0.85,
                    text_original=texto,
                    explanation="Boquilla de virola con cota propia: la nota del plano mide las "
                    f"proyecciones desde el eje del equipo («{texto}»).",
                )
            )
    return salida

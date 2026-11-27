"""Valores preliminares para los datos obligatorios que faltan en el plano.

Cuando la lectura no encuentra un dato que la familia necesita, el proceso no se corta: el campo
nace como marcador `assumed`, con una regla `preliminar.*`, confianza baja y una explicación que
dice que falta en el plano. Su valor sale, por este orden:

1. de una lectura dudosa del mismo campo (abstenida por la calibración), que sí cita el plano;
2. de proporciones habituales a partir de otro dato leído (L/D = 3, fondo 2:1, ...);
3. de un valor por defecto de la familia de equipo.

Un marcador nunca sustituye a un valor leído. La revisión no se puede aprobar mientras quede
alguno sin corregir: `review.approve` lo comprueba con `es_preliminar`.
"""

import re

from ..extraction import Candidate
from ..ingest import Bundle
from ..model import Source

PREFIJO = "preliminar."
CONFIANZA = 0.1
AVISO = "Valores preliminares (faltan en el plano, revísalos y complétalos): "

# Proporciones y valores por defecto, en mm, de cada familia.
ESBELTEZ = 3.0  # longitud entre tangentes / diámetro de un recipiente a presión habitual
POR_DEFECTO = {
    "vertical_vessel": {"diameter": 1500.0, "height": 4500.0},
    "horizontal_vessel": {"diameter": 1500.0, "length": 4500.0},
    "column": {"diameter": 1500.0, "height": 15000.0},
    "tank": {"diameter": 6000.0, "height": 6000.0},
}
ENVOLVENTE = {
    "pump": (1500.0, 800.0, 1000.0),
    "compressor": (3000.0, 2000.0, 2000.0),
    "generic": (1000.0, 1000.0, 1000.0),
}
TIPO_POR_NOMBRE = (
    (re.compile(r"BOMBA|PUMP", re.I), "pump"),
    (re.compile(r"COMPRESOR|COMPRESSOR", re.I), "compressor"),
)


def es_preliminar(field) -> bool:
    """Un campo marcador: nació de una regla `preliminar.*` y nadie lo ha corregido."""
    rule = field.source.rule or ""
    return rule.startswith(PREFIJO) and field.state != "corrected"


def _origen(bundles: list[Bundle]) -> Source:
    document = bundles[0].document
    return Source(document_id=document.id, page=1, locator="Sin cota en el plano", confidence=0)


def _marcador(path, value, unit, regla, explicacion, origen: Source, base=None) -> Candidate:
    source = (base.source if base is not None else origen).model_copy(
        update={
            "rule": PREFIJO + regla,
            "confidence": CONFIANZA,
            "confidence_raw": None,
            "grounded": False,
            "locator": (
                base.source.locator
                if base is not None
                else f"Falta en el plano: valor preliminar de {path}"
            ),
        }
    )
    return Candidate(
        path=path,
        value=value,
        unit=unit,
        source=source,
        state="assumed",
        explanation=f"Falta en el plano. Valor preliminar: {explicacion} Revísalo y complétalo.",
    )


def tipo_por_nombre(chosen: dict[str, Candidate], bundles: list[Bundle]) -> Candidate | None:
    """Tipología supuesta desde el tag o el nombre del archivo (p. ej. BOMBA → pump)."""
    tag = chosen.get("tag")
    textos = [str(tag.value)] if tag is not None else []
    textos += [b.document.filename for b in bundles]
    for patron, tipo in TIPO_POR_NOMBRE:
        if any(patron.search(texto) for texto in textos):
            return _marcador(
                "attributes.equipment_type",
                tipo,
                "1",
                "tipo_por_nombre",
                f"tipología {tipo} deducida del nombre; el plano no la rotula.",
                _origen(bundles),
            )
    return None


def _numero(candidate: Candidate | None) -> float | None:
    if candidate is None or candidate.state == "abstained":
        return None
    if not isinstance(candidate.value, int | float) or candidate.value <= 0:
        return None
    return float(candidate.value) if candidate.unit == "mm" else None


def _entre(valor: float, bajo: float, alto: float) -> float:
    return float(round(min(alto, max(bajo, valor))))


def completar(
    chosen: dict[str, Candidate],
    missing: list[str],
    *,
    family: tuple[str, str],
    kind: str | None,
    envelope: bool,
    bundles: list[Bundle],
) -> list[str]:
    """Añade a `chosen` un marcador por cada ruta de `missing` y devuelve las que ha cubierto."""
    origen = _origen(bundles)
    cubiertas = []

    def poner(path, value, unit, regla, explicacion, base=None):
        chosen[path] = _marcador(path, value, unit, regla, explicacion, origen, base)
        cubiertas.append(path)

    def dudosa(path) -> bool:
        """Una lectura abstenida del mismo campo es mejor punto de partida que una proporción."""
        lectura = chosen.get(path)
        if lectura is None or lectura.state != "abstained":
            return False
        poner(
            path,
            lectura.value,
            lectura.unit,
            "lectura_dudosa",
            f"lectura dudosa del plano ({lectura.value} {lectura.unit}) a confirmar.",
            lectura,
        )
        return True

    def medida(path) -> float | None:
        return _numero(chosen.get(path))

    pendientes = list(missing)
    if envelope:
        size = ENVOLVENTE.get(kind or "generic", ENVOLVENTE["generic"])
        for path in pendientes:
            if dudosa(path):
                continue
            match = re.fullmatch(r"envelope\.(origin|size)\.([xyz])", path)
            if not match:
                continue
            part, axis = match.groups()
            value = 0.0 if part == "origin" else size["xyz".index(axis)]
            poner(
                path,
                value,
                "mm",
                f"envolvente_{kind or 'generic'}",
                "origen en el punto de referencia del equipo."
                if part == "origin"
                else f"tamaño habitual de un equipo {kind or 'genérico'} ({value:g} mm).",
            )
    else:
        equipo = family[0]
        defecto = POR_DEFECTO.get(equipo, POR_DEFECTO["vertical_vessel"])
        prefijo = {"horizontal_vessel": "horizontal.", "tank": "tank."}.get(equipo, "")
        ruta_d = prefijo + "diameter"
        ruta_l = prefijo + ("length" if equipo == "horizontal_vessel" else "height")
        # Primero los dos datos principales: diámetro y longitud se derivan uno del otro.
        for path in (ruta_d, ruta_l):
            if path in pendientes:
                dudosa(path)
        d, largo = medida(ruta_d), medida(ruta_l)
        esbeltez = 1.0 if equipo == "tank" else ESBELTEZ
        if ruta_d in pendientes and ruta_d not in cubiertas:
            if largo is not None:
                poner(
                    ruta_d,
                    float(round(largo / esbeltez)),
                    "mm",
                    "diametro_por_esbeltez",
                    f"diámetro supuesto con L/D = {esbeltez:g} a partir de la longitud leída.",
                )
            else:
                poner(
                    ruta_d,
                    defecto["diameter"],
                    "mm",
                    f"{equipo}.diametro_por_defecto",
                    f"diámetro por defecto de la familia ({defecto['diameter']:g} mm).",
                )
        d = medida(ruta_d)
        clave_l = ruta_l.rsplit(".", 1)[-1]
        if ruta_l in pendientes and ruta_l not in cubiertas:
            if d is not None:
                poner(
                    ruta_l,
                    float(round(d * esbeltez)),
                    "mm",
                    "longitud_por_esbeltez",
                    f"longitud supuesta con L/D = {esbeltez:g} a partir del diámetro.",
                )
            else:
                poner(
                    ruta_l,
                    defecto[clave_l],
                    "mm",
                    f"{equipo}.longitud_por_defecto",
                    f"longitud por defecto de la familia ({defecto[clave_l]:g} mm).",
                )
        d = medida(ruta_d) or defecto["diameter"]
        largo = medida(ruta_l) or defecto[clave_l]
        if equipo == "column" and any(p.startswith("column.sections") for p in pendientes):
            if not any(p.startswith("column.sections.") for p in chosen):
                poner(
                    "column.sections.T1.diameter",
                    d,
                    "mm",
                    "columna.tramo_unico",
                    "un solo tramo con el diámetro de la columna.",
                )
                poner(
                    "column.sections.T1.height",
                    largo,
                    "mm",
                    "columna.tramo_unico",
                    "un solo tramo con la longitud de la columna.",
                )
        reglas = {
            "head_depth": (round(d / 4), "fondo_2_1", "fondo elipsoidal 2:1 (D/4)."),
            "horizontal.head_depth": (round(d / 4), "fondo_2_1", "fondo elipsoidal 2:1 (D/4)."),
            "skirt_height": (
                _entre(d, 1000, 3000),
                "faldon_altura",
                "altura de faldón igual al diámetro, entre 1000 y 3000 mm.",
            ),
            "skirt_thickness": (10.0, "faldon_espesor", "espesor de faldón habitual (10 mm)."),
            "attributes.skirt_diameter": (d, "faldon_diametro", "faldón con el diámetro."),
            "legs.count": (4.0 if d > 1000 else 3.0, "patas_numero", "número habitual de patas."),
            "legs.height": (
                _entre(0.6 * d, 500, 1500),
                "patas_altura",
                "altura de patas de 0,6 D, entre 500 y 1500 mm.",
            ),
            "horizontal.support_height": (
                round(0.35 * d),
                "silleta_altura",
                "altura de silleta de 0,35 D.",
            ),
            "horizontal.saddle_width": (
                round(min(500, max(200, 0.1 * d)), -1),
                "silleta_ancho",
                "ancho de silleta del 10 % del diámetro (200 a 500 mm).",
            ),
            "horizontal.saddle_span": (
                round(0.9 * d),
                "silleta_huella",
                "huella de silleta de 0,9 D.",
            ),
            "horizontal.saddle_positions.0": (
                round(0.2 * largo),
                "silletas_a_un_quinto",
                "silleta a 0,2 L de la tangente.",
            ),
            "horizontal.saddle_positions.1": (
                round(0.8 * largo),
                "silletas_a_un_quinto",
                "silleta a 0,8 L de la tangente.",
            ),
            "tank.roof": ("flat", "techo_plano", "techo plano, el caso más sencillo."),
            "tank.roof_height": (0.0, "techo_plano", "techo plano sin flecha."),
        }
        for path in pendientes:
            if path in cubiertas or path not in reglas or dudosa(path):
                continue
            value, regla, explicacion = reglas[path]
            if isinstance(value, str):
                poner(path, value, "1", regla, explicacion)
            else:
                unit = "1" if path == "legs.count" else "mm"
                poner(path, float(value), unit, regla, explicacion)
    if "tag" in pendientes and not dudosa("tag"):
        poner("tag", _tag(bundles), "1", "tag_sin_rotular", "el plano no rotula el tag.")
    for path in pendientes:
        if path not in cubiertas:
            dudosa(path)  # p. ej. la base del diámetro o de la altura de apoyo, abstenida
    return cubiertas


def _tag(bundles: list[Bundle]) -> str:
    nombre = bundles[0].document.filename.rsplit(".", 1)[0]
    return re.split(r"[-_ ]", nombre, maxsplit=1)[0] or "SIN-TAG"

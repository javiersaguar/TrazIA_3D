"""Reglas geométricas del ensamblado: completan la familia desde lo leído, con su cita.

Cada regla parte de un candidato leído y deja la regla en `source.rule`. Si la regla supone algo
que el plano no dice, el campo nace `assumed`: el IFC lo pinta con el estilo de geometría supuesta
y la revisión humana lo tiene que confirmar. Una regla nunca sustituye a un valor leído.
"""

import math
import re

from ..extraction import Candidate

# Flecha de un techo en cúpula con radio igual al diámetro (API 650 admite de 0,8 D a 1,2 D).
FLECHA_CUPULA = 1 - math.sqrt(3) / 2

REGLAS = {
    "horizontal.apoyo_base_a_eje": "Cota de la silleta medida de su base al eje del recipiente.",
    "horizontal.ancho_silleta_como_la_fija": (
        "Ancho de silleta supuesto igual al de la silleta fija, el único acotado en planta."
    ),
    "tank.espesor_virola_1": "Espesor de virola del tanque tomado de la virola inferior.",
    "tank.flecha_cupula_radio_d": (
        "Flecha del techo en cúpula supuesta con radio igual al diámetro (API 650: 0,8 D a 1,2 D)."
    ),
    "tank.flecha_cono_1_16": (
        "Flecha del techo cónico supuesta con la pendiente mínima de API 650 (1:16)."
    ),
    "fondo.elipsoidal_2_1": "Profundidad de un fondo elipsoidal 2:1: un cuarto del diámetro.",
    "fondo.supuesto_2_1": (
        "Profundidad supuesta de un fondo elipsoidal 2:1 (un cuarto del diámetro): el documento no"
        " rotula el tipo de fondo."
    ),
    "horizontal.silletas_a_un_quinto": (
        "Silletas supuestas a 0,2 L de cada tangente, la posición habitual (Zick); el plano no"
        " acota su estación."
    ),
    "horizontal.ancho_silleta_proporcional": (
        "Ancho de silleta supuesto en un 10 % del diámetro (entre 200 y 500 mm);"
        " el plano no lo acota."
    ),
    "horizontal.huella_silleta_proporcional": (
        "Ancho transversal de silleta supuesto en 0,9 D, como en 80V01; el plano no lo acota."
    ),
    "horizontal.altura_silleta_proporcional": (
        "Altura de la silleta hasta la virola supuesta en 0,35 D, como en 80V01;"
        " el plano no la acota."
    ),
    "columna.tramo_unico": (
        "Un solo tramo de columna con el diámetro y la longitud entre tangentes leídos:"
        " el documento no rotula cambios de diámetro."
    ),
    "faldon.espesor_de_la_hoja": "Espesor del faldón tomado de la hoja de datos.",
    "faldon.diametro_como_virola": (
        "Diámetro del faldón supuesto igual al exterior de la virola; el plano no lo acota."
    ),
}


def _derivado(base: Candidate, path: str, value, unit: str, rule: str, *, supuesto: bool):
    return base.model_copy(
        update={
            "path": path,
            "value": value,
            "unit": unit,
            "source": base.source.model_copy(update={"rule": rule}),
            "state": "assumed" if supuesto else base.state,
            "alternatives": [],
            "interval": None,
            "explanation": REGLAS[rule],
        }
    )


def completar(elegidos: dict[str, Candidate]) -> list[str]:
    """Añade a `elegidos` los campos que salen de una regla y devuelve los avisos."""

    def leido(path):
        candidate = elegidos.get(path)
        return candidate if candidate is not None and candidate.state != "abstained" else None

    avisos = []

    def añadir(path, base, value, unit, rule, *, supuesto):
        if path in elegidos:
            return
        elegidos[path] = _derivado(base, path, value, unit, rule, supuesto=supuesto)
        avisos.append(f"{path} por regla {rule}" + (" (supuesto)" if supuesto else ""))

    altura = leido("horizontal.support_height")
    if altura is not None and altura.source.rule == "ga.silleta_base_a_eje":
        añadir(
            "attributes.support_height_basis",
            altura,
            "axis",
            "1",
            "horizontal.apoyo_base_a_eje",
            supuesto=False,
        )
    fija = leido("attributes.saddle_width_fixed")
    if fija is not None and isinstance(fija.value, int | float) and fija.value > 0:
        añadir(
            "horizontal.saddle_width",
            fija,
            fija.value,
            fija.unit,
            "horizontal.ancho_silleta_como_la_fija",
            supuesto=True,
        )
    virola = leido("tank.courses.1.thickness")
    if virola is not None and isinstance(virola.value, int | float) and virola.value > 0:
        añadir(
            "attributes.shell_thickness",
            virola,
            virola.value,
            virola.unit,
            "tank.espesor_virola_1",
            supuesto=False,
        )
    techo, diametro = leido("tank.roof"), leido("tank.diameter")
    if (
        techo is not None
        and techo.value == "domed"
        and diametro is not None
        and isinstance(diametro.value, int | float)
        and diametro.unit == "mm"
    ):
        añadir(
            "tank.roof_height",
            techo,
            round(diametro.value * FLECHA_CUPULA),
            "mm",
            "tank.flecha_cupula_radio_d",
            supuesto=True,
        )
    if (
        techo is not None
        and techo.value == "conical"
        and diametro is not None
        and isinstance(diametro.value, int | float)
        and diametro.unit == "mm"
    ):
        añadir(
            "tank.roof_height",
            techo,
            round(diametro.value / 2 / 16),
            "mm",
            "tank.flecha_cono_1_16",
            supuesto=True,
        )
    avisos.extend(_proporciones(elegidos, leido, añadir))
    return avisos


def _numero(candidato):
    if candidato is None or not isinstance(candidato.value, int | float) or candidato.value <= 0:
        return None
    return candidato.value if candidato.unit == "mm" else None


def _proporciones(elegidos, leido, añadir) -> list[str]:
    """Piezas que el plano no acota, supuestas con proporciones habituales y a revisar.

    Solo actúan cuando ya hay un diámetro y una longitud leídos: dan la geometría secundaria
    (fondos, silletas, faldón) para que el modelo exista, siempre `assumed` y con su regla.
    """
    fondo = leido("attributes.head_type")
    tipo = leido("attributes.equipment_type")
    columna = tipo is not None and tipo.value == "column"
    for ruta_d, ruta_f in (
        ("diameter", "head_depth"),
        ("horizontal.diameter", "horizontal.head_depth"),
    ):
        base = leido(ruta_d)
        d = _numero(base)
        if d is None or (columna and ruta_d == "diameter"):
            continue
        if fondo is not None and fondo.value == "ellipsoidal_2_1":
            añadir(ruta_f, fondo, round(d / 4), "mm", "fondo.elipsoidal_2_1", supuesto=False)
        else:
            añadir(ruta_f, base, round(d / 4), "mm", "fondo.supuesto_2_1", supuesto=True)

    base_d, base_l = leido("horizontal.diameter"), leido("horizontal.length")
    d, largo = _numero(base_d), _numero(base_l)
    if d is not None and largo is not None:
        if (
            "horizontal.saddle_positions.0" not in elegidos
            and "horizontal.saddle_positions.1" not in elegidos
        ):
            for i, x in enumerate((0.2 * largo, 0.8 * largo)):
                añadir(
                    f"horizontal.saddle_positions.{i}",
                    base_l,
                    round(x),
                    "mm",
                    "horizontal.silletas_a_un_quinto",
                    supuesto=True,
                )
        ancho = round(min(500, max(200, 0.1 * d)), -1)
        añadir(
            "horizontal.saddle_width",
            base_d,
            ancho,
            "mm",
            "horizontal.ancho_silleta_proporcional",
            supuesto=True,
        )
        añadir(
            "horizontal.saddle_span",
            base_d,
            round(0.9 * d),
            "mm",
            "horizontal.huella_silleta_proporcional",
            supuesto=True,
        )
        if "attributes.support_height_basis" not in elegidos:
            añadir(
                "horizontal.support_height",
                base_d,
                round(0.35 * d),
                "mm",
                "horizontal.altura_silleta_proporcional",
                supuesto=True,
            )

    base_d, base_h = leido("diameter"), leido("height")
    d, alto = _numero(base_d), _numero(base_h)
    if (
        columna
        and d is not None
        and alto is not None
        and not any(path.startswith("column.sections.") for path in elegidos)
    ):
        añadir(
            "column.sections.T1.diameter", base_d, d, "mm", "columna.tramo_unico", supuesto=False
        )
        añadir(
            "column.sections.T1.height", base_h, alto, "mm", "columna.tramo_unico", supuesto=False
        )
    hoja = leido("attributes.skirt_thickness")
    if _numero(hoja) is not None:
        añadir(
            "skirt_thickness", hoja, hoja.value, "mm", "faldon.espesor_de_la_hoja", supuesto=False
        )
    soporte = leido("attributes.support")
    if d is not None and soporte is not None and soporte.value == "skirt":
        espesor = (
            _numero(leido("attributes.shell_thickness")) or _numero(leido("skirt_thickness")) or 0
        )
        añadir(
            "attributes.skirt_diameter",
            base_d,
            round(d + 2 * espesor),
            "mm",
            "faldon.diametro_como_virola",
            supuesto=True,
        )
    if columna:
        _fondos_columna(elegidos, leido, añadir, fondo)
    return []


def _fondos_columna(elegidos, leido, añadir, fondo):
    """Fondos de una columna: el de abajo con el primer tramo y el de arriba con el último."""
    tramos = {}
    for path in elegidos:
        dato = re.fullmatch(r"column\.sections\.([^.]+)\.(order|diameter|top_diameter)", path)
        if dato:
            tramos.setdefault(dato[1], {})[dato[2]] = leido(path)
    if not tramos:
        return
    if len(tramos) == 1:
        primero = ultimo = next(iter(tramos.values()))
    else:
        orden = {}
        for tramo in tramos.values():
            numero = tramo.get("order")
            if numero is None or not isinstance(numero.value, int | float):
                return
            orden[numero.value] = tramo
        primero, ultimo = orden[min(orden)], orden[max(orden)]
    for lado, base in (
        ("bottom", primero.get("diameter")),
        ("top", ultimo.get("top_diameter") or ultimo.get("diameter")),
    ):
        d = _numero(base)
        if d is None:
            continue
        ruta = f"attributes.column_head_depth_{lado}"
        if fondo is not None and fondo.value == "ellipsoidal_2_1":
            añadir(ruta, fondo, round(d / 4), "mm", "fondo.elipsoidal_2_1", supuesto=False)
        else:
            añadir(ruta, base, round(d / 4), "mm", "fondo.supuesto_2_1", supuesto=True)

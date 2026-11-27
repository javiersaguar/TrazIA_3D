"""Cambios entre dos revisiones por ID, a partir de lo leído en cada una.

Sirve cuando alguna de las dos revisiones no llega a modelo: compara los candidatos
citados ruta a ruta. Solo hay cambio cuando las dos revisiones leen la ruta y el valor
difiere. Una ruta que solo se lee en una revisión no es un alta ni una baja, porque
puede ser un fallo de lectura. Las altas y bajas de boquillas solo se dan cuando las
dos revisiones tienen lista de boquillas y el ID desaparece o aparece en la tabla.

Dos casos van a `revisar` y no cuentan como cambio:
- el rumbo cambia en la mayoría de las boquillas a la vez, señal de que cambió el marco de
  la planta (por ejemplo, aparece el Norte) y no las boquillas;
- el espesor se escribe con otra notación («SCH 160», «THK: 15.85», «I.D. ø50,8»), que no
  se puede comparar sin la tabla de tubería.

La misma cota con otra grafía no es un cambio: el schedule y la cara de la brida se
comparan sin la notación. «80» y «Sch.80» son el mismo schedule, y «R.F.» y «WNRF» la
misma cara. El GA da la cara sola y la HDM la escribe junto al tipo de brida, que solo
cuenta como cambio si lo dan las dos revisiones.
Si la revisión nueva nombra solo la raíz de un grupo que desaparece («N13» frente a
«N13A» y «N13B»), los campos se heredan por esos ID.

Los cambios de `welds.*` van a `derivados`: las uniones se deducen de las piezas leídas.
"""

import re
from copy import deepcopy

TOLERANCIA_MM = 1.0
TOLERANCIA_RELATIVA = 0.005
# Rutas de la tabla de boquillas: dicen que el ID está en la lista de esa revisión.
_CAMPOS_TABLA = ("size_nps", "rating", "service", "facing")
_RUMBOS = ("bearing", "azimuth")
# Rumbos que cambian a la vez: a partir de esta fracción se trata como cambio de marco.
FRACCION_MARCO = 0.5
_GEOMETRIA = ("envelope.", "horizontal.", "column.", "tank.", "legs.", "shell.", "skirt")
_MARCA_CON_SUFIJO = re.compile(r"^([A-Z]+)(\d+)([A-Z]+)$")
_SCHEDULE = re.compile(r"(?:SCH(?:EDULE)?\s+)?(\d+S?|STD|XS|XXS)")
_CARAS = {
    "RF": "RF",
    "RAISEDFACE": "RF",
    "FF": "FF",
    "FLATFACE": "FF",
    "RTJ": "RTJ",
    "RINGTYPEJOINT": "RTJ",
}


def _indice(candidatos) -> dict[str, dict]:
    """Ruta → candidato de más confianza."""
    rutas: dict[str, dict] = {}
    for c in candidatos:
        c = c if isinstance(c, dict) else c.model_dump(mode="json")
        actual = rutas.get(c["path"])
        if actual is None or _confianza(c) > _confianza(actual):
            rutas[c["path"]] = c
    return rutas


def _confianza(c: dict) -> float:
    return float((c.get("source") or {}).get("confidence") or 0)


def _texto(valor) -> str:
    return re.sub(r"\s+", " ", str(valor)).strip().upper()


def _compacto(valor) -> str:
    return re.sub(r"\s+", "", str(valor)).upper()


def token_schedule(valor) -> str | None:
    """Número o serie de schedule, sin la palabra «Sch» ni los puntos."""
    texto = _texto(valor).replace(".", " ")
    encontrado = _SCHEDULE.fullmatch(texto)
    return encontrado[1] if encontrado else None


def token_cara(valor) -> str | None:
    """Cara de brida. «WN» es el cuello soldado y no cambia la cara: WNRF y R.F. son RF."""
    texto = re.sub(r"[^A-Z]", "", _texto(valor))
    if texto in _CARAS:
        return _CARAS[texto]
    if texto.startswith("WN") and texto[2:] in _CARAS:
        return _CARAS[texto[2:]]
    return None


def notacion_equivalente(ruta, antes, despues) -> bool:
    """True cuando las dos grafías son el mismo schedule o la misma cara."""
    if str(ruta).endswith(".schedule"):
        primera, segunda = token_schedule(antes), token_schedule(despues)
    elif str(ruta).endswith(".facing"):
        primera, segunda = token_cara(antes), token_cara(despues)
    else:
        return False
    return primera is not None and primera == segunda


def iguales(a: dict, b: dict) -> bool:
    va, vb = a["value"], b["value"]
    ruta = a.get("path") or b.get("path") or ""
    if notacion_equivalente(ruta, va, vb) and a.get("unit") == b.get("unit"):
        return True
    if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
        if a.get("unit") != b.get("unit"):
            return False
        # Los atributos son valores de tabla citados: solo la tolerancia relativa, no la de medida.
        medida = a.get("unit") == "mm" and not str(a.get("path", "")).startswith("attributes.")
        tolerancia = TOLERANCIA_MM if medida else max(abs(va), abs(vb)) * TOLERANCIA_RELATIVA
        return abs(float(va) - float(vb)) <= tolerancia
    if a.get("unit") != b.get("unit"):
        return False
    campo = str(a.get("path", "")).rsplit(".", 1)[-1]
    if campo == "facing":
        return _facing_igual(va, vb)
    if campo == "schedule":
        return _schedule(va) == _schedule(vb)
    # Sin espacios: el texto extraído a veces sale con letras sueltas («H a t ch»).
    return _compacto(va) == _compacto(vb)


def _schedule(valor) -> str:
    """«SCH 80», «Sch.80» y «80» son el mismo schedule. Otra notación («THK: 15.85») queda igual."""
    texto = _compacto(valor)
    if _notacion(valor) == "schedule":
        return re.sub(r"^SCH\.?", "", texto)
    return texto


_TIPOS_BRIDA = ("LWN", "WN", "SO", "SW", "BL", "LJ", "TH", "PL")
_CARAS = {"RF": "RF", "RAISEDFACE": "RF", "FF": "FF", "FLATFACE": "FF", "RTJ": "RTJ", "RJ": "RTJ"}


def _facing(valor) -> str | tuple[str | None, str]:
    """Cara de la brida y, si viene, tipo: «R.F.», «RF» y «WNRF» tienen la misma cara.

    La tabla del GA da solo la cara y la HDM la escribe junto al tipo de brida. Si las dos
    revisiones dan tipo y el tipo cambia («SORF» → «WNRF»), sí es un cambio.
    """
    texto = re.sub(r"[^A-Z]", "", str(valor).upper())
    for tipo in ("", *_TIPOS_BRIDA):
        if texto.startswith(tipo) and texto[len(tipo) :] in _CARAS:
            return (tipo or None, _CARAS[texto[len(tipo) :]])
    return texto


def _facing_igual(va, vb) -> bool:
    a, b = _facing(va), _facing(vb)
    if isinstance(a, tuple) and isinstance(b, tuple):
        return a[1] == b[1] and (a[0] is None or b[0] is None or a[0] == b[0])
    return a == b


def _notacion(valor) -> str | None:
    texto = _texto(valor)
    if re.search(r"\bTHK\b|\bTHICK", texto):
        return "espesor"
    if re.search(r"I\.?\s?D\.?|Ø|ø", texto, re.I):
        return "diametro_interior"
    if re.fullmatch(r"(?:SCH\.?\s*)?(?:\d+S?|STD|XS|XXS)", texto):
        return "schedule"
    return None


def notacion_espesor_comparable(antes, despues) -> bool:
    primera = _notacion(antes)
    return primera is not None and primera == _notacion(despues)


def raiz_marca(marca: str) -> str | None:
    """«N13A» → «N13». Una marca sin sufijo no es raíz de otra."""
    encontrado = _MARCA_CON_SUFIJO.fullmatch(marca)
    if not encontrado:
        return None
    return f"{encontrado[1]}{int(encontrado[2])}"


def grupos_raiz(ids_antes: set[str], ids_despues: set[str]) -> dict[str, list[str]]:
    """Raíz nueva → sufijos que desaparecen. Hacen falta al menos dos: N13 → N13A y N13B."""
    desaparecen = ids_antes - ids_despues
    aparecen = ids_despues - ids_antes
    grupos: dict[str, list[str]] = {}
    for ident in desaparecen:
        raiz = raiz_marca(ident)
        if raiz and raiz in aparecen and raiz not in ids_antes:
            grupos.setdefault(raiz, []).append(ident)
    return {raiz: sorted(hijas) for raiz, hijas in grupos.items() if len(hijas) >= 2}


def _ids_boquilla(rutas) -> set[str]:
    return {
        ruta.split(".")[1] for ruta in rutas if ruta.startswith("nozzles.") and ruta.count(".") >= 2
    }


def _reasignar(valor, ruta):
    if isinstance(valor, dict):
        return {**valor, "path": ruta}
    return valor


def heredar_marcas(antes: dict, despues: dict) -> dict[str, list[str]]:
    """Copia los campos de la raíz nueva sobre cada sufijo y quita la raíz.

    La revisión que solo escribe «N13» no da de baja N13A y N13B ni de alta N13.
    """
    grupos = grupos_raiz(_ids_boquilla(antes), _ids_boquilla(despues))
    for raiz, hijas in grupos.items():
        prefijo = f"nozzles.{raiz}."
        for ruta in [r for r in despues if r.startswith(prefijo)]:
            campo = ruta.removeprefix(prefijo)
            valor = despues.pop(ruta)
            for hija in hijas:
                despues[f"nozzles.{hija}.{campo}"] = _reasignar(valor, f"nozzles.{hija}.{campo}")
    return grupos


def _boquillas_de_tabla(rutas: dict[str, dict]) -> set[str]:
    return {
        partes[1]
        for ruta in rutas
        if (partes := ruta.split(".")) and len(partes) == 3 and partes[0] == "nozzles"
        if partes[2] in _CAMPOS_TABLA
    }


def _geometria(ruta: str) -> bool:
    if ruta.startswith("nozzles."):
        return ruta.split(".")[-1] not in ("service", "rating", "flange_type")
    return ruta.startswith(_GEOMETRIA) or ruta in ("diameter", "height", "head_depth")


def _lado(c: dict | None):
    return {"value": c["value"], "unit": c.get("unit")} if c else None


def _cambio(ruta, operacion, antes, despues):
    return {
        "path": ruta,
        "operation": operacion,
        "before": _lado(antes),
        "after": _lado(despues),
        "affects_geometry": _geometria(ruta),
        "before_source": antes.get("source") if antes else None,
        "after_source": despues.get("source") if despues else None,
    }


def _por_id(cambios, base=None):
    grupos = (
        deepcopy(base)
        if base is not None
        else {
            "altas": [],
            "bajas": [],
            "cambiados": {},
            "sin_marca": [],
            "delta_del_plano": {},
        }
    )
    for cambio in cambios:
        ruta = cambio["path"]
        for prefijo in ("nozzles.", "shell.courses.", "column.sections."):
            if ruta.startswith(prefijo):
                marca, _, campo = ruta.removeprefix(prefijo).partition(".")
                break
        else:
            grupos["sin_marca"].append(cambio)
            continue
        if not campo:
            grupo = {"added": "altas", "removed": "bajas"}.get(cambio["operation"])
            if grupo and marca not in grupos["altas"] and marca not in grupos["bajas"]:
                grupos[grupo].append(marca)
            continue
        if marca in grupos["altas"] or marca in grupos["bajas"]:
            continue
        entrada = grupos["cambiados"].setdefault(marca, {"citas": [], "citas_por_campo": {}})
        entrada[campo] = [(cambio.get(lado) or {}).get("value") for lado in ("before", "after")]
        citas = [cambio.get("before_source"), cambio.get("after_source")]
        entrada["citas_por_campo"][campo] = citas
        for cita in citas:
            if cita is not None and cita not in entrada["citas"]:
                entrada["citas"].append(cita)
    for grupo in ("altas", "bajas"):
        grupos[grupo].sort()
        for marca in grupos[grupo]:
            grupos["cambiados"].pop(marca, None)
    return grupos


def comparar_candidatos(antes, despues) -> dict:
    """Mismo formato que `revisions.compare` (`changes`), con `nivel: candidatos`."""
    a, b = _indice(antes), _indice(despues)
    heredar_marcas(a, b)
    cambios, revisar, derivados = [], [], []
    comunes = sorted(a.keys() & b.keys())
    rumbos = [r for r in comunes if r.startswith("nozzles.") and r.endswith(_RUMBOS)]
    girados = [r for r in rumbos if not iguales(a[r], b[r])]
    marco = len(girados) >= 3 and len(girados) >= FRACCION_MARCO * len(rumbos)
    for ruta in comunes:
        if ruta == "tag" or iguales(a[ruta], b[ruta]):
            continue
        cambio = _cambio(ruta, "modified", a[ruta], b[ruta])
        if marco and ruta in girados:
            revisar.append({**cambio, "motivo": "marco_de_rumbos"})
            continue
        if ruta.endswith(".schedule") and not notacion_espesor_comparable(
            a[ruta]["value"], b[ruta]["value"]
        ):
            revisar.append({**cambio, "motivo": "notacion_de_espesor"})
            continue
        if ruta.startswith("welds."):
            # Las uniones se deducen de las piezas: su cambio sigue al de la pieza leída.
            derivados.append(cambio)
            continue
        cambios.append(cambio)

    ids_a, ids_b = _boquillas_de_tabla(a), _boquillas_de_tabla(b)
    if ids_a and ids_b:
        for operacion, ids, rutas in (
            ("removed", ids_a - ids_b, a),
            ("added", ids_b - ids_a, b),
        ):
            for ident in sorted(ids):
                # Ninguna ruta de ese ID en la otra revisión: no es un fallo de un campo suelto.
                otra = b if operacion == "removed" else a
                if any(r.startswith(f"nozzles.{ident}.") for r in otra):
                    continue
                cita = next(rutas[r] for r in sorted(rutas) if r.startswith(f"nozzles.{ident}."))
                cambios.append(
                    _cambio(
                        f"nozzles.{ident}",
                        operacion,
                        cita if operacion == "removed" else None,
                        cita if operacion == "added" else None,
                    )
                )
    return {
        "nivel": "candidatos",
        "changes": cambios,
        "revisar": revisar,
        "derivados": derivados,
        "por_id": _por_id(cambios),
        # Revisión sin ninguna boquilla leída (tabla sin texto): sus altas y bajas no se ven.
        "sin_boquillas": {
            "antes": not any(r.startswith("nozzles.") for r in a),
            "despues": not any(r.startswith("nozzles.") for r in b),
        },
        "summary": {
            "changes": len(cambios),
            "geometry_changes": sum(c["affects_geometry"] for c in cambios),
            "revisar": len(revisar),
            "derivados": len(derivados),
            "rumbos_girados": len(girados),
            "rumbos_comparados": len(rumbos),
            "rutas_comparadas": len(a.keys() & b.keys()),
            "rutas_solo_antes": len(a.keys() - b.keys()),
            "rutas_solo_despues": len(b.keys() - a.keys()),
        },
    }


_ORIENTACION = re.compile(
    r"^nozzles\.([^.]+)\.(?:azimuth|bearing|direction\.[xyz]|position\.[xy])$"
)


def _orientacion(ruta: str) -> str | None:
    """Marca de la boquilla si la ruta es de su orientación en planta."""
    return m[1] if (m := _ORIENTACION.match(ruta)) else None


def completar(modelo: dict, leido: dict) -> dict:
    """Completa y contrasta el delta del modelo con los candidatos de ambas revisiones.

    El modelo puede ensamblarse con menos boquillas o campos de los que se leen. Cada cambio
    añadido lleva `nivel: candidatos`. Las altas y bajas de atributos aislados del modelo
    requieren confirmación en revisión.
    """
    confirmados = []
    sin_contraste = []
    # Si la lectura ve que cambia el marco de la planta, la orientación del modelo de esas
    # boquillas (azimut, dirección y posición en planta) también la decide la revisión humana.
    en_marco = {
        item["path"].split(".")[1]
        for item in leido.get("revisar", [])
        if item.get("motivo") == "marco_de_rumbos" and item["path"].startswith("nozzles.")
    }
    # Si una revisión no tiene ninguna boquilla leída (tabla dibujada sin texto), las boquillas
    # que el modelo solo coloca en la otra no son altas ni bajas vistas: las decide la revisión
    # humana. Con boquillas leídas en las dos, el delta del modelo vale como hasta ahora.
    sin_boquillas = leido.get("sin_boquillas", {})
    ciegas = {
        "added": sin_boquillas.get("antes", False),
        "removed": sin_boquillas.get("despues", False),
    }
    vistas = {
        "added": set(leido.get("por_id", {}).get("altas", [])),
        "removed": set(leido.get("por_id", {}).get("bajas", [])),
    }
    for cambio in modelo.get("changes", []):
        ruta, operacion = cambio["path"], cambio["operation"]
        if ruta.startswith("attributes.") and operacion in ("added", "removed"):
            sin_contraste.append({**cambio, "motivo": "atributo_sin_lectura_en_ambas_revisiones"})
        elif (
            ruta.startswith("nozzles.")
            and ciegas.get(operacion)
            and ruta.split(".")[1] not in vistas[operacion]
        ):
            sin_contraste.append({**cambio, "motivo": "boquilla_sin_alta_ni_baja_en_la_lectura"})
        elif _orientacion(cambio["path"]) in en_marco:
            sin_contraste.append({**cambio, "motivo": "marco_de_rumbos"})
        else:
            confirmados.append(cambio)
    revisar = [*modelo.get("revisar", []), *sin_contraste]
    rutas = {c["path"] for c in confirmados} | {c["path"] for c in revisar}
    extra = [{**c, "nivel": "candidatos"} for c in leido["changes"] if c["path"] not in rutas]
    resultado = {**modelo, "changes": [*confirmados, *extra]}
    motivos_del_modelo = {(item["path"], item.get("motivo")) for item in revisar}
    resultado["revisar"] = revisar + [
        item
        for item in leido.get("revisar", [])
        if (item["path"], item.get("motivo")) not in motivos_del_modelo
    ]
    resultado["derivados"] = [*modelo.get("derivados", []), *leido.get("derivados", [])]
    base = modelo.get("por_id")
    resultado["por_id"] = _por_id(extra if base else resultado["changes"], base)
    if sin_contraste and base:
        descartadas = {c["path"] for c in sin_contraste}
        resultado["por_id"]["sin_marca"] = [
            c for c in resultado["por_id"]["sin_marca"] if c["path"] not in descartadas
        ]
        quedan = {
            c["path"].split(".")[1]
            for c in resultado["changes"]
            if c["path"].startswith("nozzles.")
        }
        for grupo in ("altas", "bajas"):
            resultado["por_id"][grupo] = [
                marca
                for marca in resultado["por_id"].get(grupo, [])
                if marca in quedan
                or not any(
                    r.startswith(f"nozzles.{marca}.") or r == f"nozzles.{marca}"
                    for r in descartadas
                )
            ]
        cambiados = resultado["por_id"]["cambiados"]
        for ruta in descartadas:
            if not ruta.startswith("nozzles.") or ruta.count(".") < 2:
                continue
            marca, campo = ruta.removeprefix("nozzles.").split(".", 1)
            entrada = cambiados.get(marca)
            if entrada is None:
                continue
            entrada.pop(campo, None)
            entrada.get("citas_por_campo", {}).pop(campo, None)
            if not entrada.get("citas_por_campo"):
                cambiados.pop(marca)
    resumen = dict(modelo.get("summary", {}))
    resumen["changes"] = len(resultado["changes"])
    resumen["geometry_changes"] = sum(bool(c.get("affects_geometry")) for c in resultado["changes"])
    resumen["changes_from_candidates"] = len(extra)
    resultado["summary"] = resumen
    return resultado

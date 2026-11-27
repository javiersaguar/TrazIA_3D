"""Medida de un lote contra el oro de planos de TR.

    python -m bench.oro <salida_del_lote> [eval/verdad] [--salida generated/oro]

El oro (`eval/verdad/<TAG>.json`) lo prepara a mano quien no escribe el extractor: cada valor con
documento, página y texto de la línea, y `null` cuando el plano no lo da. Formato en
docs/PLAN.md (A1). `rev2` puede declararse como `rev1` más sus cambios
(`igual_que`, `campos`, `boquillas_modificadas`, `boquillas_completadas`,
`boquillas_eliminadas`).

Por equipo y revisión mide:

- si hay modelo (`revision.json`) e IFC válido (`modelo.ifc`, que el lote solo escribe validado);
- tipo y soporte;
- error relativo del diámetro y de la longitud principal;
- marcas de boquilla: recall y precisión, acierto de NPS y de rating, error de proyección;
- diámetro, longitud y proyección solo se puntúan si el oro y la lectura usan la misma base
  (interior o exterior; T.L.-T.L. u otra cota; desde el eje o desde la virola). Si no, la medida
  queda «no comparable» con su motivo y no cuenta como error. El oro se pasa a la base de la
  lectura solo cuando el propio oro da lo necesario: el espesor de virola para el diámetro y el
  diámetro con su base para la proyección;
- error de elevación (o estación) en mm y de azimut en grados, en la escala angular del plano
  (`marco` del oro);
- textos con forma de marca que no son boquillas (`fuera_de_tabla`) leídos como boquilla;
- piezas de la lista de materiales (`piezas`) frente a `shell.courses.<POS>`: espesor, altura,
  desarrollo y código. El contrato todavía no lleva las piezas, así que con modelo se completan
  con los candidatos;
- uniones soldadas (`soldaduras`, 7.5) frente a `welds.*`: encontradas, falsas, cota y pieza de
  cada boquilla. Si el oro del equipo no trae la clave `soldaduras`, las uniones leídas quedan
  «sin oro» y no cuentan como falsas. Una lista vacía sí dice que el plano no tiene uniones;
- cambios rev1 → rev2: acertados, a revisión, faltantes y falsos. «A revisión» es un cambio del
  oro que la comparación manda a `revisar` y no a `changes`: lo ve la revisión humana, así que
  no cuenta como faltante, pero tampoco como acertado;
- avisos y segundos del lote.

Sin modelo, las lecturas salen de `candidatos.json`, que el lote escribe siempre. Así se puede
medir la lectura aunque la familia todavía falle.

La salida (JSON y Markdown) va a `generated/`, que Git ignora porque puede contener valores de TR.
Las cifras se publican con su denominador.
"""

import argparse
import fnmatch
import json
import re
import statistics
import sys
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

RUTAS_DIAMETRO = ("diameter", "horizontal.diameter", "tank.diameter")
RUTAS_LONGITUD = ("height", "horizontal.length", "tank.height")
CAMBIOS_EVALUABLES = {
    "boquilla_eliminada",
    "boquilla_añadida",
    "boquilla_modificada",
    "campo_modificado",
    "campo_añadido",
}


# --- Oro ------------------------------------------------------------------------------------


def cargar_oro(carpeta: Path) -> dict[str, dict]:
    oro = {}
    for path in sorted(Path(carpeta).glob("*.json")):
        datos = json.loads(path.read_text(encoding="utf-8"))
        oro[datos["tag"]] = datos
    return oro


def revisiones_efectivas(oro: dict) -> dict[str, dict]:
    """Resuelve `igual_que`: cada revisión completa, con sus campos y boquillas."""
    resueltas: dict[str, dict] = {}
    for etiqueta, rev in oro["revisiones"].items():
        base = rev.get("igual_que")
        if base:
            efectiva = deepcopy(resueltas[base])
            efectiva["equipment_type"] = rev.get("equipment_type", efectiva["equipment_type"])
            efectiva["support"] = rev.get("support", efectiva["support"])
            efectiva["campos"].update(rev.get("campos", {}))
            for clave in ("boquillas_modificadas", "boquillas_completadas"):
                for id_boq, cambios in rev.get(clave, {}).items():
                    if isinstance(cambios, dict) and id_boq in efectiva["boquillas"]:
                        efectiva["boquillas"][id_boq].update(cambios)
            for id_boq in rev.get("boquillas_eliminadas", []):
                efectiva["boquillas"].pop(id_boq, None)
            for id_boq, nueva in rev.get("boquillas_añadidas", {}).items():
                efectiva["boquillas"][id_boq] = nueva
            for posicion, cambios in rev.get("piezas", {}).items():
                efectiva["piezas"].setdefault(posicion, {}).update(cambios)
        else:
            efectiva = {
                "equipment_type": rev.get("equipment_type"),
                "support": rev.get("support"),
                "campos": dict(rev.get("campos", {})),
                "boquillas": deepcopy(rev.get("boquillas", {})),
                "piezas": deepcopy(rev.get("piezas", {})),
            }
        # Sin la clave, el oro no dice nada de las uniones: `None` y no lista vacía.
        efectiva["soldaduras"] = (
            None
            if "soldaduras" not in oro
            else [s for s in oro["soldaduras"] if etiqueta in s.get("revisiones", [etiqueta])]
        )
        efectiva["fuera_de_tabla"] = sorted(
            {
                marca(f["texto"])
                for f in oro.get("fuera_de_tabla", [])
                if etiqueta in f.get("revisiones", [etiqueta])
            }
        )
        resueltas[etiqueta] = efectiva
    return resueltas


# --- Predicción -----------------------------------------------------------------------------


def marca(texto: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(texto).upper())


def rating(texto) -> str | None:
    if texto is None:
        return None
    numeros = re.findall(r"\d+", str(texto))
    return f"{numeros[0]}#" if numeros else None


def _numero(valor) -> float | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def _aplanar(objeto, ruta: str, salida: dict, reglas: dict | None = None):
    """Rutas como las de `trazia.model.fields`: IDs en listas con `id`, índices en el resto."""
    if isinstance(objeto, dict):
        if "value" in objeto and ("unit" in objeto or "source" in objeto):
            salida[ruta] = objeto["value"]
            regla = (objeto.get("source") or {}).get("rule")
            if reglas is not None and regla:
                reglas[ruta] = regla
            return
        for nombre, hijo in objeto.items():
            _aplanar(hijo, f"{ruta}.{nombre}" if ruta else nombre, salida, reglas)
    elif isinstance(objeto, list):
        for indice, hijo in enumerate(objeto):
            clave = hijo.get("id", indice) if isinstance(hijo, dict) else indice
            _aplanar(hijo, f"{ruta}.{clave}" if ruta else str(clave), salida, reglas)
    elif ruta in ("kind", "support"):
        salida[ruta] = objeto


@dataclass
class Prediccion:
    modelo: bool = False
    ifc: bool = False
    fuente: str = "nada"
    valores: dict = field(default_factory=dict)
    colocadas: int | None = None  # boquillas con posición en el modelo; None sin modelo
    reglas: dict = field(default_factory=dict)  # {ruta: source.rule} de revision.json
    candidatos: dict = field(default_factory=dict)  # mejor valor por ruta de candidatos.json
    soldaduras: dict = field(default_factory=dict)  # {ID: {kind, joins, elevation_mm}}
    ids_colocados: set = field(default_factory=set)  # boquillas con posición en el modelo

    def tangente_inferior(self) -> float:
        """Cota de la T.L. inferior en el marco del modelo (z = 0 en el suelo).

        En los verticales es `legs.height` o `skirt_height` (`Equipment.shell_bottom`). Los
        candidatos de la lectura ya dan «EL.+» desde la T.L., así que sin modelo es 0.
        """
        if not self.modelo:
            return 0.0
        for ruta in ("legs.height", "skirt_height"):
            if (valor := _numero(self.valores.get(ruta))) is not None:
                return valor
        return 0.0

    def _por_id(self, prefijo: tuple[str, ...], valores: dict | None = None) -> dict[str, dict]:
        resultado: dict[str, dict] = {}
        n = len(prefijo)
        for ruta, valor in (self.valores if valores is None else valores).items():
            partes = ruta.split(".")
            if len(partes) >= n + 2 and tuple(partes[:n]) == prefijo:
                resultado.setdefault(marca(partes[n]), {})[".".join(partes[n + 1 :])] = valor
        return resultado

    def boquillas(self) -> dict[str, dict]:
        return self._por_id(("nozzles",))

    def piezas(self) -> dict[str, dict]:
        """Filas de la lista de materiales: `shell.courses.<POS>.*` (interfaz 2).

        El contrato aún no lleva las piezas, así que con modelo siguen en `candidatos.json`. Lo
        que dé `revision.json` manda sobre el candidato.
        """
        prefijo = ("shell", "courses")
        piezas = self._por_id(prefijo, self.candidatos)
        for posicion, campos in self._por_id(prefijo).items():
            piezas.setdefault(posicion, {}).update(campos)
        return piezas


def _mejores_candidatos(path: Path) -> dict[str, object]:
    """El valor de mayor confianza por ruta de `candidatos.json`."""
    mejores: dict[str, tuple[float, object]] = {}
    for c in json.loads(path.read_text(encoding="utf-8")):
        confianza = c.get("confidence_raw") or 0.0
        if c["path"] not in mejores or confianza > mejores[c["path"]][0]:
            mejores[c["path"]] = (confianza, c["value"])
    return {ruta: valor for ruta, (_, valor) in mejores.items()}


def _soldaduras(valores: dict) -> dict[str, dict]:
    """`welds.<ID>.<campo>`: el ID puede llevar puntos (`W:1.1|1.2`), el campo es el último."""
    resultado: dict[str, dict] = {}
    for ruta, valor in valores.items():
        partes = ruta.split(".")
        if len(partes) >= 3 and partes[0] == "welds":
            resultado.setdefault(".".join(partes[1:-1]), {})[partes[-1]] = valor
    return resultado


def leer_prediccion(carpeta: Path) -> Prediccion:
    pred = Prediccion()
    revision = carpeta / "revision.json"
    candidatos = carpeta / "candidatos.json"
    if candidatos.exists():
        pred.candidatos = _mejores_candidatos(candidatos)
        pred.soldaduras = _soldaduras(pred.candidatos)
    if revision.exists():
        datos = json.loads(revision.read_text(encoding="utf-8"))
        pred.modelo, pred.fuente = True, "revision"
        pred.ifc = (carpeta / "modelo.ifc").exists()
        _aplanar(datos.get("equipment", {}), "", pred.valores, pred.reglas)
        pred.ids_colocados = set(pred.boquillas())
        pred.colocadas = len(pred.ids_colocados)
        # Las boquillas identificadas sin posición (`unplaced_nozzles`) no entran en el modelo,
        # pero sí cuentan como marcas leídas. Sus atributos salen de los candidatos.
        sin_colocar = {marca(i) for i in datos.get("unplaced_nozzles", [])} - set(pred.boquillas())
        de_candidatos = _mejores_candidatos(candidatos) if candidatos.exists() else {}
        for ruta, valor in de_candidatos.items():
            partes = ruta.split(".")
            if len(partes) >= 3 and partes[0] == "nozzles" and marca(partes[1]) in sin_colocar:
                pred.valores.setdefault(ruta, valor)
        for id_boq in sin_colocar - set(pred.boquillas()):
            pred.valores[f"nozzles.{id_boq}.id"] = id_boq
        return pred
    if candidatos.exists():
        pred.fuente = "candidatos"
        pred.valores = _mejores_candidatos(candidatos)
        tipo = pred.valores.get("attributes.equipment_type")
        if tipo:
            pred.valores.setdefault("kind", tipo)
        soporte = pred.valores.get("attributes.support")
        if soporte:
            pred.valores.setdefault("support", soporte)
    return pred


# --- Métricas -------------------------------------------------------------------------------


def _error_relativo(pred: float | None, oro: float | None) -> float | None:
    if pred is None or oro in (None, 0):
        return None
    return abs(pred - oro) / abs(oro)


# --- Bases de medida -------------------------------------------------------------------------
# Una cota solo se compara con otra medida desde el mismo sitio. En el modelo, `height` y
# `horizontal.length` son la virola entre tangentes y `tank.height` la altura de la virola
# (trazia.model). Un diámetro pasado a exterior lleva la regla `<familia>.diametro_exterior`
# y una proyección pasada del eje a la virola, `virola.proyeccion_desde_eje`.

BASES_LONGITUD_MODELO = {
    "height": "tl-tl",
    "horizontal.length": "tl-tl",
    "tank.height": "virola",
}
BASES_PROYECCION = {"eje": "axis", "axis": "axis", "virola": "shell", "shell": "shell"}
# El ensamblado deja la proyección del modelo desde la virola con estas reglas, sea cual sea la
# base leída: vertical (`families/upright.py`) y horizontal (`families/horizontal.py`).
REGLAS_PROYECCION_VIROLA = (
    "virola.proyeccion_desde_eje",
    "horizontal.proyeccion_desde_eje",
    "horizontal.proyeccion_desde_virola",
)


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _primero_con_ruta(valores: dict, rutas) -> tuple[str | None, float | None]:
    for ruta in rutas:
        numero = _numero(valores.get(ruta))
        if numero is not None:
            return ruta, numero
    return None, None


def _oro_con_ruta(campos: dict, rutas) -> tuple[str | None, float | None]:
    for ruta in rutas:
        campo = campos.get(ruta)
        if isinstance(campo, dict) and _numero(campo.get("valor")) is not None:
            return ruta, _numero(campo["valor"])
    return None, None


def _valor(campos: dict, ruta: str):
    campo = campos.get(ruta)
    return campo.get("valor") if isinstance(campo, dict) else None


def _base_diametro_oro(campos: dict, ruta: str) -> str | None:
    for base in ((campos.get(ruta) or {}).get("base"), _valor(campos, "attributes.diameter_basis")):
        if base in ("inside", "outside"):
            return base
    return None


def _base_diametro_pred(pred: Prediccion, ruta: str) -> str | None:
    if str(pred.reglas.get(ruta, "")).endswith("diametro_exterior"):
        return "outside"
    for base in (
        pred.valores.get("attributes.diameter_basis"),
        pred.candidatos.get("attributes.diameter_basis"),
    ):
        if base in ("inside", "outside"):
            return base
    return None


def _sin_comparar(motivo: str | None = None) -> dict:
    return {"error": None, "base": None, "no_comparable": motivo}


def comparar_diametro(campos: dict, pred: Prediccion) -> dict:
    """Error relativo del diámetro en una base común, o el motivo de que no sea comparable."""
    ruta_oro, esperado = _oro_con_ruta(campos, RUTAS_DIAMETRO)
    ruta_pred, leido = _primero_con_ruta(pred.valores, RUTAS_DIAMETRO)
    if esperado is None or leido is None:
        return _sin_comparar()
    base_oro, base_pred = _base_diametro_oro(campos, ruta_oro), _base_diametro_pred(pred, ruta_pred)
    if base_oro is None:
        return _sin_comparar("el oro no indica ID u OD")
    if base_pred is None:
        return _sin_comparar("la lectura no indica ID u OD")
    base = base_pred
    if base_oro != base_pred:
        espesor = _numero(_valor(campos, "attributes.shell_thickness"))
        if espesor is None:
            return _sin_comparar(f"oro {base_oro} y lectura {base_pred}, sin espesor de virola")
        esperado += 2 * espesor if base_pred == "outside" else -2 * espesor
        base = f"{base_pred} (oro convertido con el espesor de virola)"
    return {"error": _error_relativo(leido, esperado), "base": base, "no_comparable": None}


def _base_longitud_oro(campo: dict) -> str | None:
    texto = str(campo.get("base") or "").strip()
    if not texto:
        return None
    plano = re.sub(r"\s+", "", _sin_acentos(texto).upper())
    if re.search(r"T\.?L\.?(-|A|TO)T\.?L", plano):
        return "tl-tl"
    if "ALTURACILINDRICA" in plano or "ALTURADEVIROLA" in plano:
        return "virola"
    return texto


def comparar_longitud(campos: dict, pred: Prediccion) -> dict:
    """La longitud del oro solo se compara con la del modelo si las dos van entre tangentes.

    Los candidatos no dicen desde dónde se mide la longitud que leen: sin modelo, la longitud
    no es comparable.
    """
    ruta_oro, esperado = _oro_con_ruta(campos, RUTAS_LONGITUD)
    ruta_pred, leido = _primero_con_ruta(pred.valores, RUTAS_LONGITUD)
    if esperado is None or leido is None:
        return _sin_comparar()
    base_oro = _base_longitud_oro(campos[ruta_oro])
    base_pred = BASES_LONGITUD_MODELO.get(ruta_pred) if pred.modelo else None
    if base_oro is None:
        return _sin_comparar("el oro no indica la base")
    if base_pred is None:
        return _sin_comparar("la lectura no indica la base")
    if base_oro != base_pred:
        return _sin_comparar(f"oro «{base_oro}» y modelo «{base_pred}»")
    return {"error": _error_relativo(leido, esperado), "base": base_pred, "no_comparable": None}


def _radio_exterior_oro(campos: dict) -> float | None:
    ruta, diametro = _oro_con_ruta(campos, RUTAS_DIAMETRO)
    if diametro is None:
        return None
    base = _base_diametro_oro(campos, ruta)
    if base == "outside":
        return diametro / 2
    espesor = _numero(_valor(campos, "attributes.shell_thickness"))
    if base == "inside" and espesor is not None:
        return diametro / 2 + espesor
    return None


def _ruta_de_boquilla(ruta: str, id_boq: str, campo: str) -> bool:
    partes = ruta.split(".")
    return (
        len(partes) == 3
        and partes[0] == "nozzles"
        and partes[2] == campo
        and marca(partes[1]) == id_boq
    )


def _base_proyeccion_pred(pred: Prediccion, id_boq: str) -> str | None:
    for ruta, regla in pred.reglas.items():
        if _ruta_de_boquilla(ruta, id_boq, "projection") and regla in REGLAS_PROYECCION_VIROLA:
            return "shell"
    for ruta, valor in pred.candidatos.items():
        if _ruta_de_boquilla(ruta, id_boq, "projection_basis"):
            return BASES_PROYECCION.get(str(valor))
    return None


def comparar_proyecciones(campos, oro_boq, pred_boq, comunes, pred) -> tuple[list[float], int]:
    """Diferencias de proyección en mm en una base común y cuántas no son comparables."""
    radio = _radio_exterior_oro(campos)
    diferencias, no_comparables = [], 0
    for m in comunes:
        esperado = _numero(oro_boq[m].get("standout_mm"))
        leido = _numero(pred_boq[m].get("projection"))
        if esperado is None or leido is None:
            continue
        base_oro = BASES_PROYECCION.get(str(oro_boq[m].get("standout_base")))
        base_pred = _base_proyeccion_pred(pred, m)
        if base_oro is None or base_pred is None:
            no_comparables += 1
            continue
        if base_oro != base_pred:
            if radio is None:
                no_comparables += 1
                continue
            esperado += -radio if base_pred == "shell" else radio
        diferencias.append(abs(leido - esperado))
    return diferencias, no_comparables


# Reglas con las que la lectura pasa el rumbo del plano (0° arriba, horario) al convenio del
# contrato para verticales (0° hacia +X, antihorario): `reference.internal_azimuth` con el
# Norte en +Y, es decir, azimut = 90 − rumbo.
REGLAS_AZIMUT_VERTICAL = ("vertical.azimut_escala_plano", "vertical.azimut_desde_norte")


def azimut_en_plano(pred: Prediccion, id_boq: str, valor: float | None) -> float | None:
    """El azimut del modelo en la escala angular del plano, la misma del oro.

    El ángulo de cabezal de los horizontales ya va en esa escala y se deja igual.
    """
    if valor is None:
        return None
    for ruta, regla in pred.reglas.items():
        if _ruta_de_boquilla(ruta, id_boq, "azimuth") and regla in REGLAS_AZIMUT_VERTICAL:
            return (90 - valor) % 360
    return valor


def diferencia_cota(oro_boq: dict, pred_boq: dict, origen: float = 0.0) -> float | None:
    """Diferencia en mm entre la cota del oro y la del modelo, en la misma dirección.

    `elevation_mm` es vertical y se compara con `elevation`. `station_mm` es la estación axial
    de un horizontal desde la T.L. y se compara con `position.x` del modelo o con `station` de la
    lectura. La `elevation` de un horizontal es la altura de la boquilla sobre el suelo, así que
    no se compara con la estación. `origen` es la cota de la T.L. inferior en el marco de la
    lectura: el modelo vertical mide desde el suelo y el oro «EL.+» desde la tangente.
    """
    if (cota := _numero(oro_boq.get("elevation_mm"))) is not None:
        leida = _numero(pred_boq.get("elevation"))
        leida = None if leida is None else leida - origen
    elif (cota := _numero(oro_boq.get("station_mm"))) is not None:
        leida = _numero(pred_boq.get("position.x", pred_boq.get("station")))
    else:
        return None
    return None if leida is None else abs(leida - cota)


def medir_revision(oro_rev: dict, pred: Prediccion) -> dict:
    campos = oro_rev["campos"]
    oro_boq = {marca(m): b for m, b in oro_rev["boquillas"].items()}
    pred_boq = pred.boquillas()
    comunes = sorted(set(oro_boq) & set(pred_boq))

    nps = [
        _numero(pred_boq[m].get("size_nps")) == _numero(oro_boq[m].get("size_nps"))
        for m in comunes
        if oro_boq[m].get("size_nps") is not None
    ]
    ratings = [
        rating(pred_boq[m].get("rating")) == rating(oro_boq[m].get("rating"))
        for m in comunes
        if oro_boq[m].get("rating") is not None
    ]
    proyeccion, proyecciones_no_comparables = comparar_proyecciones(
        campos, oro_boq, pred_boq, comunes, pred
    )
    diametro = comparar_diametro(campos, pred)
    longitud = comparar_longitud(campos, pred)
    elevacion = []
    azimut = []
    for m in comunes:
        origen = pred.tangente_inferior() if m in pred.ids_colocados else 0.0
        if (diferencia := diferencia_cota(oro_boq[m], pred_boq[m], origen)) is not None:
            elevacion.append(diferencia)
        angulo = _numero(oro_boq[m].get("azimuth_deg"))
        leido = azimut_en_plano(pred, m, _numero(pred_boq[m].get("azimuth")))
        if angulo is not None and leido is not None:
            diferencia = abs(leido - angulo) % 360
            azimut.append(min(diferencia, 360 - diferencia))
    falsos = set(oro_rev.get("fuera_de_tabla", [])) - set(oro_boq)
    piezas = medir_piezas(oro_rev.get("piezas", {}), pred.piezas())
    return {
        "modelo": pred.modelo,
        "ifc_valido": pred.ifc,
        "fuente": pred.fuente,
        "tipo_ok": pred.valores.get("kind") == oro_rev["equipment_type"],
        "soporte_ok": pred.valores.get("support") == oro_rev["support"],
        "error_diametro": diametro["error"],
        "diametro_base": diametro["base"],
        "diametro_no_comparable": diametro["no_comparable"],
        "error_longitud": longitud["error"],
        "longitud_base": longitud["base"],
        "longitud_no_comparable": longitud["no_comparable"],
        "marcas_oro": len(oro_boq),
        "marcas_leidas": len(pred_boq),
        "marcas_acertadas": len(comunes),
        "boquillas_colocadas": pred.colocadas,
        "nps_evaluables": len(nps),
        "nps_ok": sum(nps),
        "rating_evaluables": len(ratings),
        "rating_ok": sum(ratings),
        "error_proyeccion_mm": statistics.median(proyeccion) if proyeccion else None,
        "proyecciones_evaluables": len(proyeccion),
        "proyecciones_no_comparables": proyecciones_no_comparables,
        "error_elevacion_mm": statistics.median(elevacion) if elevacion else None,
        "elevaciones_evaluables": len(elevacion),
        "error_azimut_deg": statistics.median(azimut) if azimut else None,
        "azimuts_evaluables": len(azimut),
        "fuera_de_tabla": len(falsos),
        "falsos_ids_como_boquilla": sorted(falsos & set(pred_boq)),
        **piezas,
        **medir_soldaduras(oro_rev.get("soldaduras"), pred.soldaduras),
    }


TOLERANCIA_SOLDADURA_MM = 100


def _norma(texto) -> str:
    return re.sub(r"[^0-9A-Z:|.]", "", str(texto or "").upper())


def medir_soldaduras(oro_sold: list[dict] | None, pred_sold: dict[str, dict]) -> dict:
    """Uniones del oro frente a `welds.*` leídas.

    Boquillas por marca; circunferenciales y uniones de piezas por cota (±100 mm) y tipo; el resto
    por ID o `id_alias`. Las piezas de cada lado se nombran distinto en el oro (posición de la
    lista de materiales) y en la lectura (`SHELL`, `HEAD_BOTTOM`…), por eso no se exige el ID.

    Con `oro_sold` a `None` el oro no anota uniones: las leídas quedan «sin oro», no falsas.
    """
    sin_oro = oro_sold is None
    oro_sold = oro_sold or []
    libres = {} if sin_oro else dict(pred_sold)
    encontradas, errores, partes = 0, [], []
    for s in oro_sold:
        elegido = None
        if s["tipo"] == "nozzle":
            for ident, p in libres.items():
                une = str(p.get("joins") or ident.removeprefix("W:")).split("|")
                if p.get("kind") == "nozzle" and marca(une[0]) == marca(s["une"][0]):
                    elegido = ident
                    break
        cota = _numero(s.get("cota_mm"))
        if elegido is None and cota is not None:
            cerca = [
                (abs(_numero(p.get("elevation_mm")) - cota), ident)
                for ident, p in libres.items()
                if p.get("kind") == s["tipo"] and _numero(p.get("elevation_mm")) is not None
            ]
            cerca = [c for c in cerca if c[0] <= TOLERANCIA_SOLDADURA_MM]
            elegido = min(cerca)[1] if cerca else None
        if elegido is None:
            nombres = {_norma(s["id"]), _norma(s.get("id_alias"))} - {""}
            elegido = next((i for i in libres if _norma(i) in nombres), None)
        if elegido is None:
            continue
        p = libres.pop(elegido)
        encontradas += 1
        leida = _numero(p.get("elevation_mm"))
        if cota is not None and leida is not None:
            errores.append(abs(leida - cota))
        if s["tipo"] == "nozzle" and s["une"][1] is not None:
            otra = str(p.get("joins") or elegido.removeprefix("W:")).split("|")[-1]
            alias = str(s.get("id_alias") or "").split("|")[-1]
            partes.append(_norma(otra) in {_norma(s["une"][1]), _norma(alias)})
    return {
        "soldaduras_oro": len(oro_sold),
        "soldaduras_leidas": len(pred_sold),
        "soldaduras_encontradas": encontradas,
        "soldaduras_falsas": len(libres),
        "soldaduras_sin_oro": len(pred_sold) if sin_oro else 0,
        "error_cota_soldadura_mm": statistics.median(errores) if errores else None,
        "soldaduras_pieza_ok": sum(partes),
        "soldaduras_pieza_evaluables": len(partes),
    }


CAMPOS_PIEZA = {
    "espesor_mm": "thickness",
    "altura_mm": "height",
    "desarrollo_mm": "development",
    "codigo": "code",
}


def medir_piezas(oro_piezas: dict, pred_piezas: dict) -> dict:
    """Piezas de la lista de materiales por posición (V01…, F01A…): presentes y campo a campo."""
    oro_pos = {marca(p): datos for p, datos in oro_piezas.items()}
    presentes = sorted(set(oro_pos) & set(pred_piezas))
    evaluables = acertados = 0
    for posicion in presentes:
        for campo_oro, campo_pred in CAMPOS_PIEZA.items():
            esperado = oro_pos[posicion].get(campo_oro)
            if esperado is None:
                continue
            evaluables += 1
            leido = pred_piezas[posicion].get(campo_pred)
            if campo_oro == "codigo":
                acertados += str(leido).strip() == str(esperado).strip()
            else:
                numero = _numero(leido)
                acertados += numero is not None and abs(numero - float(esperado)) <= 0.5
    return {
        "piezas_oro": len(oro_pos),
        "piezas_leidas": len(pred_piezas),
        "piezas_presentes": len(presentes),
        "piezas_faltantes": sorted(set(oro_pos) - set(pred_piezas)),
        "piezas_campos_evaluables": evaluables,
        "piezas_campos_ok": acertados,
    }


# Rutas del oro que el contrato (interfaz 2) nombra de otra forma. Un patrón con `*` agrupa los
# cambios de varias piezas: el oro anota una vez «espesores de las virolas» y la lectura da uno
# por anillo. En los tanques, `attributes.shell_thickness` es el espesor de la virola 1
# (regla `tank.espesor_virola_1`) y forma parte del mismo cambio.
RUTAS_CAMBIO_CONTRATO = {
    "attributes.shell_height": ("height",),
    "attributes.shell_courses_thickness": (
        "tank.courses.*.thickness",
        "attributes.shell_thickness",
    ),
}


# Campo de boquilla del oro → campos de la ruta de la lectura (interfaz 2). Un campo que no está
# aquí («hold», «reinforcement») se casa solo por la marca.
CAMPOS_CAMBIO_BOQUILLA = {
    "standout_mm": ("projection",),
    "servicio": ("service",),
    "size_nps": ("size_nps", "diameter"),
    "rating": ("rating",),
    "facing": ("facing", "flange_type"),
    "schedule": ("schedule",),
    "elevation_mm": ("elevation", "position.z"),
    "station_mm": ("station", "position.x"),
    "azimuth_deg": ("azimuth", "bearing", "direction.x", "direction.y", "position.x", "position.y"),
}


def _campos_de_boquilla(cambio_oro: dict) -> set[str] | None:
    """Campos de la lectura que valen para el cambio, o None si basta la marca."""
    nombres = [c for c in str(cambio_oro.get("campo") or "").split("/") if c]
    if not nombres or any(c not in CAMPOS_CAMBIO_BOQUILLA for c in nombres):
        return None
    return {campo for c in nombres for campo in CAMPOS_CAMBIO_BOQUILLA[c]}


def _coincide(cambio_oro: dict, ruta_predicha: str) -> bool:
    ruta = ruta_predicha.lower()
    if cambio_oro.get("marca"):
        # La marca entera: el cambio de N1 no puede dar por buena la ruta de N10 ni de N13A.
        partes = ruta.split(".")
        if not (
            len(partes) > 1
            and partes[0] == "nozzles"
            and marca(partes[1]) == marca(cambio_oro["marca"])
        ):
            return False
        # Y el campo, si el oro lo da: el cambio de proyección de A1 no da por buena su cota.
        campos = _campos_de_boquilla(cambio_oro)
        return campos is None or ".".join(partes[2:]) in campos
    objetivo = str(cambio_oro.get("ruta", "")).lower()
    if not objetivo:
        return False
    if ruta == objetivo or ruta.endswith("." + objetivo):
        return True
    return any(fnmatch.fnmatch(ruta, patron) for patron in RUTAS_CAMBIO_CONTRATO.get(objetivo, ()))


def medir_cambios(
    oro: dict, cambios_predichos: list[dict] | None, a_revisar: list[dict] | None = None
) -> dict:
    """Cambios del oro frente a `changes` y, si no están ahí, frente a `revisar`.

    Lo que solo está en `revisar` no cuenta como falso: la comparación no lo da por cambio.
    """
    evaluables = [c for c in oro.get("cambios_rev1_rev2", []) if c["tipo"] in CAMBIOS_EVALUABLES]
    if cambios_predichos is None:
        return {
            "evaluables": len(evaluables),
            "acertados": 0,
            "a_revision": 0,
            "faltantes": len(evaluables),
            "falsos": None,
            "predichos": None,
        }
    rutas = [c.get("path", "") for c in cambios_predichos]
    rutas_revisar = [c.get("path", "") for c in a_revisar or []]
    usadas: set[int] = set()
    acertados = a_revision = 0
    for cambio in evaluables:
        indices = [i for i, ruta in enumerate(rutas) if _coincide(cambio, ruta)]
        if indices:
            acertados += 1
            usadas.update(indices)
        elif any(_coincide(cambio, ruta) for ruta in rutas_revisar):
            a_revision += 1
    return {
        "evaluables": len(evaluables),
        "acertados": acertados,
        "a_revision": a_revision,
        "faltantes": len(evaluables) - acertados - a_revision,
        "falsos": len(rutas) - len(usadas),
        "predichos": len(rutas),
    }


def _filas_resumen(lote: Path) -> dict[tuple[str, str], dict]:
    path = lote / "resumen.json"
    if not path.exists():
        return {}
    datos = json.loads(path.read_text(encoding="utf-8"))
    filas = datos.get("filas", datos) if isinstance(datos, dict) else datos
    return {(f["tag"], str(f["revision"])): f for f in filas if isinstance(f, dict)}


def evaluar(lote: Path, carpeta_oro: Path) -> dict:
    lote, oro_todo = Path(lote), cargar_oro(carpeta_oro)
    resumen = _filas_resumen(lote)
    filas, cambios = [], {}
    for tag, oro in oro_todo.items():
        for etiqueta, oro_rev in revisiones_efectivas(oro).items():
            pred = leer_prediccion(lote / tag / etiqueta)
            fila = {"tag": tag, "revision": etiqueta, **medir_revision(oro_rev, pred)}
            meta = resumen.get((tag, etiqueta.removeprefix("rev")), {})
            fila["avisos"], fila["segundos"] = meta.get("avisos"), meta.get("segundos")
            filas.append(fila)
        archivo = lote / tag / "cambios_rev1_rev2.json"
        leido = json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else None
        cambios[tag] = (
            medir_cambios(oro, None)
            if leido is None
            else medir_cambios(oro, leido.get("changes", []), leido.get("revisar", []))
        )
    return {"filas": filas, "cambios": cambios, "agregado": agregar(filas, cambios)}


def agregar(filas: list[dict], cambios: dict) -> dict:
    def mediana(clave):
        valores = [f[clave] for f in filas if f[clave] is not None]
        return {"mediana": statistics.median(valores) if valores else None, "n": len(valores)}

    def suma(clave):
        return sum(f[clave] for f in filas)

    total = len(filas)
    return {
        "revisiones": total,
        "con_modelo": sum(f["modelo"] for f in filas),
        "ifc_validos": sum(f["ifc_valido"] for f in filas),
        "boquillas_colocadas": {
            "colocadas": sum(f["boquillas_colocadas"] or 0 for f in filas if f["modelo"]),
            "leidas": sum(f["marcas_leidas"] for f in filas if f["modelo"]),
        },
        "tipo_ok": sum(f["tipo_ok"] for f in filas),
        "soporte_ok": sum(f["soporte_ok"] for f in filas),
        "error_diametro": mediana("error_diametro"),
        "error_longitud": mediana("error_longitud"),
        "diametro_dentro_2pct": sum(
            1 for f in filas if f["error_diametro"] is not None and f["error_diametro"] <= 0.02
        ),
        "error_proyeccion_mm": mediana("error_proyeccion_mm"),
        "no_comparables": {
            "diametro": sum(1 for f in filas if f["diametro_no_comparable"]),
            "longitud": sum(1 for f in filas if f["longitud_no_comparable"]),
            "proyecciones": suma("proyecciones_no_comparables"),
            "proyecciones_evaluables": suma("proyecciones_evaluables"),
        },
        "marcas": {
            "oro": suma("marcas_oro"),
            "leidas": suma("marcas_leidas"),
            "acertadas": suma("marcas_acertadas"),
        },
        "nps": {"ok": suma("nps_ok"), "evaluables": suma("nps_evaluables")},
        "rating": {"ok": suma("rating_ok"), "evaluables": suma("rating_evaluables")},
        "error_elevacion_mm": mediana("error_elevacion_mm"),
        "error_azimut_deg": mediana("error_azimut_deg"),
        "fuera_de_tabla": {
            "evaluables": suma("fuera_de_tabla"),
            "contados_como_boquilla": sum(len(f["falsos_ids_como_boquilla"]) for f in filas),
        },
        "soldaduras": {
            "oro": suma("soldaduras_oro"),
            "encontradas": suma("soldaduras_encontradas"),
            "leidas": suma("soldaduras_leidas"),
            "falsas": suma("soldaduras_falsas"),
            "sin_oro": suma("soldaduras_sin_oro"),
            "pieza_ok": suma("soldaduras_pieza_ok"),
            "pieza_evaluables": suma("soldaduras_pieza_evaluables"),
            "error_cota_mm": mediana("error_cota_soldadura_mm"),
        },
        "piezas": {
            "oro": suma("piezas_oro"),
            "presentes": suma("piezas_presentes"),
            "campos_ok": suma("piezas_campos_ok"),
            "campos_evaluables": suma("piezas_campos_evaluables"),
        },
        "cambios": {
            clave: sum((c[clave] or 0) for c in cambios.values())
            for clave in ("evaluables", "acertados", "a_revision", "faltantes", "falsos")
        },
    }


# --- Informe --------------------------------------------------------------------------------


def _pct(x, n) -> str:
    return f"{x}/{n}" + (f" ({100 * x / n:.0f} %)" if n else "")


def _err(valor) -> str:
    return "—" if valor is None else f"{100 * valor:.1f} %"


def _mm(valor) -> str:
    return "—" if valor is None else f"{valor:.0f} mm"


def _grados(valor) -> str:
    return "—" if valor is None else f"{valor:.1f}°"


def markdown(informe: dict) -> str:
    a = informe["agregado"]
    n = a["revisiones"]
    lineas = [
        "# Medida contra el oro de TR",
        "",
        f"- Revisiones con modelo: {_pct(a['con_modelo'], n)}; "
        f"IFC válidos: {_pct(a['ifc_validos'], n)}",
        f"- Tipo acertado: {_pct(a['tipo_ok'], n)}; soporte acertado: {_pct(a['soporte_ok'], n)}",
        f"- Error de diámetro (mediana): {_err(a['error_diametro']['mediana'])} "
        f"en {a['error_diametro']['n']} revisiones; dentro del 2 %: {a['diametro_dentro_2pct']}; "
        f"no comparables por la base: {a['no_comparables']['diametro']}",
        f"- Error de longitud (mediana): {_err(a['error_longitud']['mediana'])} "
        f"en {a['error_longitud']['n']} revisiones; "
        f"no comparables por la base: {a['no_comparables']['longitud']}",
        f"- Proyección (mediana): {_mm(a['error_proyeccion_mm']['mediana'])} en "
        f"{a['no_comparables']['proyecciones_evaluables']} boquillas; no comparables por la "
        f"base: {a['no_comparables']['proyecciones']}",
        f"- Marcas de boquilla: recall {_pct(a['marcas']['acertadas'], a['marcas']['oro'])}, "
        f"precisión {_pct(a['marcas']['acertadas'], a['marcas']['leidas'])}",
        f"- Boquillas colocadas en los modelos: "
        f"{_pct(a['boquillas_colocadas']['colocadas'], a['boquillas_colocadas']['leidas'])}",
        f"- NPS: {_pct(a['nps']['ok'], a['nps']['evaluables'])}; "
        f"rating: {_pct(a['rating']['ok'], a['rating']['evaluables'])}",
        f"- Cambios rev1→rev2: acertados "
        f"{_pct(a['cambios']['acertados'], a['cambios']['evaluables'])}, "
        f"a revisión {a['cambios']['a_revision']}, faltantes {a['cambios']['faltantes']}, "
        f"falsos {a['cambios']['falsos']}",
        f"- Elevación o estación (mediana): {_mm(a['error_elevacion_mm']['mediana'])} "
        f"en {a['error_elevacion_mm']['n']} revisiones; azimut (mediana): "
        f"{_grados(a['error_azimut_deg']['mediana'])} en {a['error_azimut_deg']['n']} revisiones",
        f"- Falsos IDs de fuera de tabla contados como boquilla: "
        f"{a['fuera_de_tabla']['contados_como_boquilla']} de {a['fuera_de_tabla']['evaluables']}",
        f"- Soldaduras: encontradas "
        f"{_pct(a['soldaduras']['encontradas'], a['soldaduras']['oro'])}, "
        f"falsas {a['soldaduras']['falsas']} de "
        f"{a['soldaduras']['leidas'] - a['soldaduras']['sin_oro']} leídas en equipos con oro de "
        f"uniones; {a['soldaduras']['sin_oro']} leídas sin oro; pieza de la "
        f"boquilla {_pct(a['soldaduras']['pieza_ok'], a['soldaduras']['pieza_evaluables'])}; "
        f"cota (mediana) {_mm(a['soldaduras']['error_cota_mm']['mediana'])}",
        f"- Piezas de la lista de materiales: presentes "
        f"{_pct(a['piezas']['presentes'], a['piezas']['oro'])}; campos "
        f"{_pct(a['piezas']['campos_ok'], a['piezas']['campos_evaluables'])}",
        "",
        "| Equipo | Rev | Modelo | IFC | Tipo | Soporte | Err. Ø | Err. L "
        "| Marcas | NPS | Rating | Fuente |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    si = {True: "sí", False: "no"}
    for f in informe["filas"]:
        lineas.append(
            f"| {f['tag']} | {f['revision']} | {si[f['modelo']]} | {si[f['ifc_valido']]} "
            f"| {si[f['tipo_ok']]} | {si[f['soporte_ok']]} | {_err(f['error_diametro'])} "
            f"| {_err(f['error_longitud'])} | {f['marcas_acertadas']}/{f['marcas_oro']} "
            f"| {f['nps_ok']}/{f['nps_evaluables']} | {f['rating_ok']}/{f['rating_evaluables']} "
            f"| {f['fuente']} |"
        )
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lote", type=Path, help="Carpeta de salida de `trazia lote`")
    parser.add_argument(
        "oro",
        type=Path,
        nargs="?",
        default=Path("eval/verdad"),
        help="Carpeta con <TAG>.json (eval/verdad)",
    )
    parser.add_argument("--salida", type=Path, default=Path("generated/oro"))
    args = parser.parse_args(argv)
    if not (args.lote / "resumen.json").exists() and not any(args.lote.glob("*/rev*")):
        print(f"{args.lote}: no parece la salida de un lote", file=sys.stderr)
        return 1
    informe = evaluar(args.lote, args.oro)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "oro.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    texto = markdown(informe)
    (args.salida / "oro.md").write_text(texto, encoding="utf-8")
    try:
        print(texto)
    except UnicodeEncodeError:
        # El informe en disco conserva el texto UTF-8 aunque la consola use otra codificación.
        print(texto.encode(sys.stdout.encoding, "backslashreplace").decode(sys.stdout.encoding))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

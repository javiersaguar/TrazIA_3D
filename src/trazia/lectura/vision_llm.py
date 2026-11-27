"""Visión del plan A (J4): huecos de la lectura y validador, con citas que pasan `_ground`.

- `huecos` calcula qué campos de la familia deja vacíos la lectura por reglas (J1–J3) y qué
  boquillas de la tabla siguen sin posición.
- `completar` pide solo esos campos por mosaicos. Cada valor debe traer su texto impreso y su caja,
  y solo se acepta si el texto vectorial del PDF en esa caja lo respalda (`is_grounded`). Lo que no
  tiene respaldo se descarta y se cuenta.
- `validar` contrasta los campos por debajo del umbral con su recorte. Responde `confirma`,
  `contradice` o `no_visible` y solo cambia la confianza; nunca crea ni cambia valores.

Todas las llamadas pasan por `vision.providers` (política de envíos, registro y caché).
"""

import hashlib
import io
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field

from ..extraction import Candidate
from ..model import Source
from ..reconcile.grounding import is_grounded
from ..units import UnitError, normalize
from ..vision.base import PolicyError, VisionError
from ..vision.prompts import HUECOS, VALIDAR
from ..vision.tiling import merge_duplicates, tiles

CONFIANZA_VISION = 0.6
UMBRAL_VALIDAR = 0.7
MAX_VALIDAR = 8
_FAMILIAS = {
    ("vertical_vessel", "legs"): ("diameter", "height", "head_depth", "legs.height"),
    ("vertical_vessel", "skirt"): ("diameter", "height", "head_depth", "skirt_height"),
    ("horizontal_vessel", "saddles"): (
        "horizontal.diameter",
        "horizontal.length",
        "horizontal.head_depth",
        "horizontal.support_height",
        "horizontal.saddle_width",
        "horizontal.saddle_span",
        "horizontal.saddle_positions.0",
        "horizontal.saddle_positions.1",
    ),
    ("column", "skirt"): ("skirt_height",),
    ("tank", "none"): ("tank.diameter", "tank.height"),
}
_ANGULO = re.compile(r"\.bearing$")


@dataclass
class Informe:
    huecos: list[str] = field(default_factory=list)
    aceptados: list[str] = field(default_factory=list)
    rechazados: int = 0
    mosaicos: int = 0
    llamadas: int = 0
    validados: dict[str, str] = field(default_factory=dict)
    errores: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    segundos: float = 0.0

    def resumen(self) -> str:
        validados = {
            v: list(self.validados.values()).count(v) for v in set(self.validados.values())
        }
        return (
            f"Visión (J4): {len(self.aceptados)}/{len(self.huecos)} huecos con cita, "
            f"{self.rechazados} sin respaldo vectorial, validador {validados or '{}'}, "
            f"{self.llamadas} llamadas en {self.segundos:.1f} s"
        )


def _indice(candidatos) -> dict[str, Candidate]:
    out: dict[str, Candidate] = {}
    for c in candidatos:
        if c.path not in out or c.source.confidence > out[c.path].source.confidence:
            out[c.path] = c
    return out


def familia(rutas) -> tuple[str, str] | None:
    tipo = rutas.get("attributes.equipment_type")
    soporte = rutas.get("attributes.support")
    tipo = tipo.value if tipo else None
    soporte = soporte.value if soporte else None
    if tipo == "horizontal_vessel" or (tipo is None and soporte == "saddles"):
        return ("horizontal_vessel", "saddles")
    if tipo == "tank":
        return ("tank", "none")
    if tipo == "column":
        return ("column", "skirt") if soporte == "skirt" else None
    if tipo == "vertical_vessel" or soporte in ("legs", "skirt"):
        return ("vertical_vessel", "legs" if soporte == "legs" else "skirt")
    return None


def huecos(candidatos) -> list[str]:
    """Rutas que la familia necesita y la lectura por reglas no ha dado."""
    rutas = _indice(candidatos)
    clave = familia(rutas)
    if clave is None:
        return []
    faltan = [r for r in _FAMILIAS[clave] if r not in rutas]
    base = rutas.get("attributes.diameter_basis")
    if base and base.value == "inside" and "attributes.shell_thickness" not in rutas:
        faltan.append("attributes.shell_thickness")
    eje = "station" if clave[0] == "horizontal_vessel" else "elevation"
    marcas = sorted(
        {r.split(".")[1] for r in rutas if r.startswith("nozzles.") and r.endswith(".size_nps")}
    )
    if clave[0] != "tank":
        for marca in marcas:
            if f"nozzles.{marca}.{eje}" not in rutas:
                faltan.append(f"nozzles.{marca}.{eje}")
            if not any(f"nozzles.{marca}.{c}" in rutas for c in ("azimuth", "bearing")):
                faltan.append(f"nozzles.{marca}.bearing")
    return faltan


def _png(imagen) -> bytes:
    stream = io.BytesIO()
    imagen.save(stream, "PNG", optimize=True)
    return stream.getvalue()


def _medida(ruta, valor, unidad):
    texto = f"{valor} {unidad or ''}".strip()
    if _ANGULO.search(ruta):
        return normalize(texto.replace("°", " deg"), "angle", default_unit="deg")
    return normalize(texto, "length", default_unit="mm")


def completar(
    proveedor,
    imagen,
    *,
    documento: str,
    pagina: int,
    lineas,
    candidatos,
    page_ref: str,
    informe: Informe,
    tile_size: int = 1280,
) -> list[Candidate]:
    """Lee por mosaicos solo los huecos. Devuelve candidatos `vision` respaldados por el PDF."""
    faltan = huecos(candidatos)
    informe.huecos = faltan
    if not faltan:
        return []
    esquema = deepcopy(HUECOS.schema)
    esquema["properties"]["fields"]["items"]["properties"]["field"]["enum"] = faltan
    recogidos = []
    partes = tiles(imagen, size=tile_size, overlap=0.15)
    informe.mosaicos += len(partes)
    for indice, parte in enumerate(partes):
        try:
            leido = proveedor.read(parte.png(), "huecos", esquema, page_ref=f"{page_ref}/t{indice}")
        except (VisionError, PolicyError) as exc:
            informe.errores.append(f"mosaico {indice}: {exc}")
            continue
        informe.llamadas += int(not leido.cached)
        informe.tokens_in += leido.tokens_in or 0
        informe.tokens_out += leido.tokens_out or 0
        informe.segundos += leido.seconds or 0
        for dato in leido.data.get("fields", []):
            if dato.get("field") in faltan and len(dato.get("bbox") or []) == 4:
                caja = parte.to_page(tuple(dato["bbox"]))
                recogidos.append({**dato, "bbox": list(caja), "box": caja})
    mejores: dict[str, Candidate] = {}
    for dato in merge_duplicates(recogidos):
        ruta = dato["field"]
        try:
            medida = _medida(ruta, str(dato.get("value", "")).replace(",", "."), dato.get("unit"))
            x0, y0, x1, y1 = (min(max(v, 0.0), 1.0) for v in dato["bbox"])
            candidato = Candidate(
                path=ruta,
                value=medida.value,
                unit=medida.unit,
                source=Source(
                    document_id=documento,
                    page=pagina,
                    bbox=(x0, y0, max(x1, x0), max(y1, y0)),
                    locator=str(dato.get("text") or "")[:200] or ruta,
                    confidence=CONFIANZA_VISION,
                    channel="vision",
                    model=getattr(proveedor, "model", None),
                    prompt_sha256=HUECOS.prompt_sha256,
                    rule="vision.hueco",
                    text_original=str(dato.get("text") or "")[:200] or None,
                ),
                channel="vision",
                model=getattr(proveedor, "model", None),
                prompt_sha256=HUECOS.prompt_sha256,
                text_original=None,
                confidence_raw=CONFIANZA_VISION,
                explanation="Leído por visión en un hueco de la lectura por reglas.",
            )
            respaldo = is_grounded(candidato, lineas)
        except (UnitError, ValueError, TypeError):
            informe.rechazados += 1
            continue
        if respaldo is not True:
            informe.rechazados += 1
            continue
        candidato.source.grounded = True
        candidato.grounded = True
        if ruta not in mejores:
            mejores[ruta] = candidato
    informe.aceptados = sorted(mejores)
    return list(mejores.values())


def _recorte(imagen, caja, margen=0.03):
    ancho, alto = imagen.size
    x0, y0, x1, y1 = caja
    zona = (
        max(0, round((x0 - margen) * ancho)),
        max(0, round((y0 - margen) * alto)),
        min(ancho, round((x1 + margen) * ancho)),
        min(alto, round((y1 + margen) * alto)),
    )
    return imagen.crop(zona)


def a_validar(candidatos, *, documento: str, pagina: int) -> list[Candidate]:
    """Campos citados en esta página con confianza bajo el umbral (sin uniones deducidas)."""
    elegidos = [
        c
        for c in candidatos
        if c.source.document_id == documento
        and c.source.page == pagina
        and c.source.bbox is not None
        and c.source.confidence < UMBRAL_VALIDAR
        and c.channel != "vision"
        and not c.path.startswith(("welds.", "nozzles."))
    ]
    return sorted(elegidos, key=lambda c: c.source.confidence)[:MAX_VALIDAR]


def validar(
    proveedor, imagen, candidatos, *, documento: str, pagina: int, page_ref: str, informe: Informe
) -> list[Candidate]:
    """Devuelve los candidatos con la confianza ajustada por el validador. Nunca crea valores."""
    cambios: dict[int, Candidate] = {}
    for candidato in a_validar(candidatos, documento=documento, pagina=pagina):
        esquema = deepcopy(VALIDAR.schema)
        afirmacion = {"campo": candidato.path, "valor": candidato.value, "unidad": candidato.unit}
        esquema["description"] = "Claim to check: " + json.dumps(afirmacion, ensure_ascii=False)
        huella = hashlib.sha256(candidato.path.encode()).hexdigest()[:8]
        try:
            leido = proveedor.read(
                _png(_recorte(imagen, candidato.source.bbox)),
                "validar",
                esquema,
                page_ref=f"{page_ref}/v{huella}",
            )
        except (VisionError, PolicyError) as exc:
            informe.errores.append(f"validar {candidato.path}: {exc}")
            continue
        informe.llamadas += int(not leido.cached)
        informe.tokens_in += leido.tokens_in or 0
        informe.tokens_out += leido.tokens_out or 0
        informe.segundos += leido.seconds or 0
        veredicto = leido.data.get("veredicto")
        if veredicto not in ("confirma", "contradice", "no_visible"):
            continue
        informe.validados[candidato.path] = veredicto
        if veredicto == "no_visible":
            continue
        confianza = (
            max(candidato.source.confidence, 0.8)
            if veredicto == "confirma"
            else min(candidato.source.confidence, 0.3)
        )
        nota = f"Validador ({getattr(proveedor, 'model', '')}): {veredicto}"
        if texto := str(leido.data.get("texto") or "").strip():
            nota += f" («{texto[:120]}»)"
        cambios[id(candidato)] = candidato.model_copy(
            update={
                "source": candidato.source.model_copy(update={"confidence": confianza}),
                "explanation": "; ".join(filter(None, (candidato.explanation, nota))),
            }
        )
    return [cambios.get(id(c), c) for c in candidatos]


def aplicar(proveedor, bundle, pdf: bytes, candidatos, *, dpi: int = 150) -> tuple[list, Informe]:
    """Huecos y validador sobre la primera página citada del plano. Devuelve la lista nueva."""
    from ..vision.reader import render_page

    documento = bundle.document.id
    paginas = sorted({c.source.page for c in candidatos if c.source.document_id == documento})
    pagina = next((p for p in paginas if p), 1)
    informe = Informe()
    imagen = render_page(pdf, pagina, dpi=dpi).convert("RGB")
    page_ref = f"{bundle.document.sha256}#p{pagina}"
    nuevos = completar(
        proveedor,
        imagen,
        documento=documento,
        pagina=pagina,
        lineas=bundle.lines,
        candidatos=candidatos,
        page_ref=page_ref,
        informe=informe,
    )
    salida = validar(
        proveedor,
        imagen,
        candidatos,
        documento=documento,
        pagina=pagina,
        page_ref=page_ref,
        informe=informe,
    )
    return salida + nuevos, informe

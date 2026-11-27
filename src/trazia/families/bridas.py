"""Bridas ASME B16.5 y B16.47 (series A y B): identificación de la norma y medidas.

Las medidas vienen de catálogos públicos y se citan por fila. No se extrapolan tamaños ni
clases. Una tobera de 26" o más necesita la serie de B16.47 escrita en el plano o en la
especificación: A y B tienen diámetro, taladrado y espesor distintos y el tamaño no las
distingue.
"""

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

TABLE = Path(__file__).with_name("bridas_asme.json")

SOURCES = {
    "apiint-wn-150": "https://apiint.com/flange-dimensions/weld-neck-flange-dimensions/class-150-weld-neck/",
    "apiint-wn-300": "https://apiint.com/flange-dimensions/weld-neck-flange-dimensions/class-300-weld-neck/",
    "etb-600": "https://www.engineeringtoolbox.com/ansi-carbon-stainless-steel-flanges-d_304.html",
    "etb-900": "https://www.engineeringtoolbox.com/ansi-pipes-flanges-d_216.html",
    "etb-1500": "https://www.engineeringtoolbox.com/carbon-stainless-steel-flanges-d_348.html",
    "etb-2500": "https://www.engineeringtoolbox.com/steam-properties-d_316.html",
    "wermac-b16.47a": "https://www.wermac.org/flanges/dimensions_welding-neck_blind-flanges_class-150_asme-b16-47-a.html",
    "wermac-b16.47b": "https://www.wermac.org/flanges/dimensions_welding-neck_blind-flanges_class-150_asme-b16-47-b.html",
}

STANDARD_NAMES = {
    "B16.5": "ASME B16.5",
    "B16.47A": "ASME B16.47 Serie A",
    "B16.47B": "ASME B16.47 Serie B",
}

# Clases que cada norma define, para rechazar combinaciones imposibles (p. ej. B16.47 2500).
CLASSES = {
    "B16.5": (150, 300, 400, 600, 900, 1500, 2500),
    "B16.47A": (150, 300, 400, 600, 900),
    "B16.47B": (75, 150, 300, 400, 600, 900),
}

# DN (mm) → NPS (pulgadas), ASME B36.10. Desde NPS 14 el DN es 25·NPS.
_DN_NPS = {
    15: 0.5, 20: 0.75, 25: 1, 32: 1.25, 40: 1.5, 50: 2, 65: 2.5, 80: 3, 90: 3.5,
    100: 4, 125: 5, 150: 6, 200: 8, 250: 10, 300: 12,
}  # fmt: skip

# Raised face: 1,6 mm en clases 150 y 300; 6,4 mm en el resto (B16.5 y B16.47).
RAISED_FACE_LOW = 1.6
RAISED_FACE_HIGH = 6.4


@dataclass(frozen=True)
class FlangeDims:
    standard: str
    pressure_class: int
    nps: float
    outside: float
    thickness: float | None
    raised_face: float | None
    hub_base: float | None
    hub_length: float | None
    hub_bevel: float | None
    pitch: float
    count: int
    hole: float
    source: str

    @property
    def complete(self) -> bool:
        """Con espesor y cuello se puede dibujar la brida de cuello soldado completa."""
        return None not in (self.thickness, self.hub_base, self.hub_length, self.hub_bevel)

    @property
    def raised_face_height(self) -> float:
        return RAISED_FACE_LOW if self.pressure_class <= 300 else RAISED_FACE_HIGH

    @property
    def bolt(self) -> float:
        """Perno 1/8" menor que el taladro, regla habitual de B16.5; no es dato del plano."""
        return self.hole - 3.175

    @property
    def source_url(self) -> str:
        return SOURCES[self.source]

    @property
    def label(self) -> str:
        """Misma forma que la descripción de los IFC de referencia («BRIDA WN RF 12" 300#»)."""
        nps = f"{self.nps:g}"
        return f'BRIDA WN RF {nps}" {self.pressure_class}# S/{STANDARD_NAMES[self.standard]}'


def _number(text: str) -> float | None:
    return float(text) if text else None


@cache
def table() -> dict[tuple[str, int, float], FlangeDims]:
    data = json.loads(TABLE.read_text(encoding="utf-8"))
    rows = [dict(zip(data["columnas"], row)) for row in data["filas"]]
    return {
        (row["standard"], int(row["class"]), float(row["nps"])): FlangeDims(
            standard=row["standard"],
            pressure_class=int(row["class"]),
            nps=float(row["nps"]),
            outside=float(row["od_mm"]),
            thickness=_number(row["thickness_mm"]),
            raised_face=_number(row["raised_face_dia_mm"]),
            hub_base=_number(row["hub_base_dia_x_mm"]),
            hub_length=_number(row["length_through_hub_mm"]),
            hub_bevel=_number(row["hub_dia_at_bevel_mm"]),
            pitch=float(row["bolt_circle_mm"]),
            count=int(row["bolt_holes"]),
            hole=float(row["hole_dia_mm"]),
            source=row["source"],
        )
        for row in rows
    }


def nps_from_dn(dn: float) -> float | None:
    """NPS de un DN nominal exacto; None si el DN no es nominal."""
    if dn in _DN_NPS:
        return _DN_NPS[dn]
    if dn >= 350 and dn % 50 == 0:
        return dn / 25
    return None


def parse_nps(value) -> float | None:
    """«12», «12"», «1-1/2"», «1.1/2», «3/4» → pulgadas. Otro texto → None."""
    text = str(value).strip().replace("”", '"').replace("″", '"').rstrip('"').strip()
    text = re.sub(r"\s*(?:IN|INCH|INCHES|NPS)\.?$", "", text, flags=re.I).strip()
    match = re.fullmatch(r"(\d+)(?:[ .-](\d+)/(\d+))?", text)
    if match:
        whole, num, den = match.groups()
        return int(whole) + (int(num) / int(den) if num else 0)
    match = re.fullmatch(r"(\d+)/(\d+)", text)
    if match:
        return int(match[1]) / int(match[2])
    try:
        return float(text)
    except ValueError:
        return None


def parse_class(value) -> int | None:
    """«300», «300#», «#300», «300 LB», «CL 300», «Class 300» → 300. «PN16» u otro texto → None."""
    match = re.search(
        r"(?:^#?\s*|\b(?:CL(?:ASS)?\.?|CLASE)\s*)(\d{2,4})\s*(?:#|LBS?\.?)?(?:\b|$)",
        str(value).strip(),
        re.I,
    )
    if not match or re.search(r"\bPN\s*\d", str(value), re.I):
        return None
    return int(match[1])


_SERIES = re.compile(
    r"B[\s-]?16[.,]?47\s*[,(-]?\s*(?:SER(?:IE|IES)?\.?\s*)?(?P<serie>[AB])\b"
    r"|(?P<mss>MSS[\s-]*SP[\s-]*44)|(?P<api>API[\s-]*605)",
    re.I,
)
_B165 = re.compile(r"B[\s-]?16[.,]?5(?!\d)", re.I)
_B1647 = re.compile(r"B[\s-]?16[.,]?47", re.I)


def parse_standard(value) -> str | None:
    """Norma citada en un texto del plano. «B16.47» sin serie no basta y devuelve None."""
    text = str(value)
    match = _SERIES.search(text)
    if match:
        if match["mss"]:
            return "B16.47A"
        if match["api"]:
            return "B16.47B"
        return "B16.47" + match["serie"].upper()
    if _B165.search(text):
        return "B16.5"
    return None


@dataclass(frozen=True)
class Resolution:
    dims: FlangeDims | None
    standard: str | None
    origin: str  # campo_trazado | deducida_por_tamano | ""
    reason: str


def resolve(nps: float | None, pressure_class: int | None, standard: str | None) -> Resolution:
    """Elige la fila de la tabla y explica por qué no hay brida cuando no la hay."""
    if nps is None:
        return Resolution(None, standard, "", "tamaño nominal desconocido")
    if pressure_class is None:
        return Resolution(None, standard, "", "clase de brida no reconocida")
    origin = "campo_trazado" if standard else ""
    if standard is None:
        if nps <= 24:
            standard, origin = "B16.5", "deducida_por_tamano"
        else:
            return Resolution(
                None, None, "", f'NPS {nps:g}" es B16.47: falta la serie (A o B) en el plano'
            )
    if standard == "B16.5" and nps > 24:
        return Resolution(None, standard, origin, f'B16.5 llega a NPS 24"; NPS {nps:g}" no existe')
    if standard.startswith("B16.47") and nps < 26:
        return Resolution(None, standard, origin, f'B16.47 empieza en NPS 26"; NPS {nps:g}"')
    if pressure_class not in CLASSES[standard]:
        return Resolution(
            None,
            standard,
            origin,
            f"{STANDARD_NAMES[standard]} no define la clase {pressure_class}",
        )
    dims = table().get((standard, pressure_class, float(nps)))
    if dims is None:
        return Resolution(None, standard, origin, "sin fila en la tabla de medidas")
    return Resolution(dims, standard, origin, "")


def mentions_b1647_without_series(value) -> bool:
    text = str(value)
    return bool(_B1647.search(text)) and parse_standard(text) is None

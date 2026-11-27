import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")]
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
FieldState = Literal["candidate", "conflict", "abstained", "accepted", "corrected", "assumed"]
Channel = Literal[
    "texto",
    "tabla",
    "cota",
    "cajetin",
    "hoja_datos",
    "vesor",
    "ocr",
    "detector",
    "vision",
    "geometria",
    "rag",
    "memoria_revision",
    "humano",
    "diseno",
]


def _is_none(value) -> bool:
    return value is None


# Ampliación aditiva de 0.3: un campo opcional ausente no se serializa, así que los JSON
# y las huellas de aprobación anteriores no cambian.
def optional(**kwargs):
    return Field(default=None, exclude_if=_is_none, **kwargs)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


ViewKind = Literal[
    "elevation",
    "plan",
    "section",
    "nozzle_table",
    "design_data",
    "weights",
    "bom",
    "title_block",
    "notes",
    "detail",
]


def _ordered_bbox(value: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("bbox debe ser una región normalizada y ordenada")
    return value


BBox = Annotated[
    tuple[float, float, float, float], Field(strict=False), AfterValidator(_ordered_bbox)
]


class InferredRegion(Model):
    page: int = Field(ge=1)
    bbox: BBox
    view: ViewKind | None = optional()


class DesignRef(Model):
    """Orden de diseño confirmada por una persona; no es una lectura del plano."""

    kind: Literal["cambio_diseno"] = "cambio_diseno"
    proposal_id: Identifier
    operation_id: Identifier


class Source(Model):
    document_id: Identifier
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    cell: str | None = None
    locator: str = Field(min_length=1)
    bbox: BBox | None = None
    confidence: float = Field(ge=0, le=1)
    reviewed: bool = False
    confidence_raw: float | None = None
    channel: Channel | None = None
    strategy: str | None = None
    model: str | None = None
    prompt_sha256: SHA256 | None = None
    grounded: bool | None = None
    text_original: str | None = None
    unit_original: str | None = None
    design: DesignRef | None = optional()
    inferred_region: InferredRegion | None = optional()
    rule: str | None = optional(pattern=r"^[a-z0-9_.:-]+$")

    @model_validator(mode="after")
    def check_location(self):
        if self.design is not None or self.channel == "diseno":
            return self.check_design()
        if self.page is None and self.inferred_region is None and not (self.sheet and self.cell):
            raise ValueError("La evidencia necesita página, región inferida o bien hoja y celda")
        if self.bbox is not None and self.page is None:
            raise ValueError("bbox de palabra requiere página")
        if self.inferred_region is not None and self.bbox is None and self.grounded is True:
            raise ValueError("Una inferred_region sin bbox de palabra no admite grounded=True")
        return self

    def check_design(self):
        # La orden se localiza en su propio documento por operación; nunca en una página
        # inventada del plano ni con una confianza de lectura heredada o estimada.
        if self.design is None or self.channel != "diseno":
            raise ValueError("Una orden de diseño requiere canal diseno y referencia de orden")
        if any(
            v is not None
            for v in (self.page, self.sheet, self.cell, self.bbox, self.inferred_region)
        ):
            raise ValueError("Una orden de diseño no tiene página, celda ni región del plano")
        if self.confidence != 1 or self.confidence_raw is not None:
            raise ValueError("Una orden de diseño es un valor declarado: confianza 1 y sin bruta")
        if any(v is not None for v in (self.strategy, self.model, self.prompt_sha256)):
            raise ValueError("Una orden de diseño no procede de una estrategia de extracción")
        if self.grounded is not None:
            raise ValueError("Una orden de diseño no se contrasta con el plano original")
        return self


class Interval(Model):
    low: float
    high: float
    level: float = Field(gt=0, lt=1)
    method: Literal["conformal"] = "conformal"

    @model_validator(mode="after")
    def check_order(self):
        if self.low > self.high:
            raise ValueError("El límite inferior del intervalo no puede superar al superior")
        return self


class Alternative(Model):
    value: float | str
    unit: str = Field(min_length=1)
    source: Source


class TracedField(Model):
    source: Source
    state: FieldState = "candidate"
    interval: Interval | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    explanation: str | None = None

    @model_validator(mode="after")
    def sync_reviewed(self):
        if self.state == "assumed" and not self.source.rule:
            raise ValueError("El estado assumed requiere source.rule")
        self.source = self.source.model_copy(
            update={"reviewed": self.state in ("accepted", "corrected")}
        )
        return self


class Dimension(TracedField):
    # Las coordenadas del origen también son Dimension: pueden ser cero o negativas.
    # La positividad se valida en los parámetros físicos y en Envelope.size.
    value: float
    unit: Literal["mm"] = "mm"


class Elevation(TracedField):
    value: float = Field(ge=0)
    unit: Literal["mm"] = "mm"


class Angle(TracedField):
    value: float = Field(ge=0, lt=360)
    unit: Literal["deg"] = "deg"


class Attribute(TracedField):
    value: float | str
    unit: str = Field(min_length=1)


class Tag(TracedField):
    value: str = Field(min_length=1)
    unit: Literal["1"] = "1"


class Vector3(Model):
    x: Dimension
    y: Dimension
    z: Dimension


class Envelope(Model):
    origin: Vector3
    size: Vector3

    @model_validator(mode="after")
    def check_size(self):
        if any(getattr(self.size, axis).value <= 0 for axis in "xyz"):
            raise ValueError("Los tamaños de la envolvente deben ser positivos")
        return self


class SkidPart(Model):
    """Volumen exterior de un mecánico: bancada, motor, reductora o máquina."""

    id: Identifier
    name: Attribute
    envelope: Envelope


class DirectionComponent(TracedField):
    value: float
    unit: Literal["1"] = "1"


class Direction3(Model):
    x: DirectionComponent
    y: DirectionComponent
    z: DirectionComponent

    @model_validator(mode="after")
    def check_direction(self):
        if sum(getattr(self, axis).value ** 2 for axis in "xyz") < 1e-12:
            raise ValueError("La dirección no puede ser nula")
        return self


class PositiveDimension(Dimension):
    value: float = Field(gt=0)


class PositiveCount(TracedField):
    value: int = Field(gt=0)
    unit: Literal["1"] = "1"


class LegParameters(Model):
    count: PositiveCount
    height: PositiveDimension
    section: Attribute | None = optional()
    azimuths: list[Angle] | None = optional()

    @model_validator(mode="after")
    def check_azimuths(self):
        if self.azimuths is not None:
            if len(self.azimuths) != self.count.value:
                raise ValueError("Los azimuts deben corresponder al número de patas")
            if len({angle.value for angle in self.azimuths}) != len(self.azimuths):
                raise ValueError("Los azimuts de las patas deben ser distintos")
        return self


class HorizontalParameters(Model):
    diameter: PositiveDimension
    length: PositiveDimension
    head_depth: PositiveDimension
    support_height: PositiveDimension
    saddle_width: PositiveDimension
    saddle_span: PositiveDimension
    saddle_positions: list[Dimension] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def check_saddles(self):
        left, right = sorted(p.value for p in self.saddle_positions)
        width = self.saddle_width.value
        if left < width / 2 or right + width / 2 > self.length.value or right - left <= width:
            raise ValueError("Las dos silletas deben quedar separadas dentro de la virola")
        if self.saddle_span.value >= self.diameter.value:
            raise ValueError("El ancho transversal de silleta debe ser menor que el diámetro")
        if self.head_depth.value > self.diameter.value / 2:
            raise ValueError("La profundidad del fondo no puede superar el radio")
        return self


class ColumnSection(Model):
    id: Identifier
    diameter: PositiveDimension
    top_diameter: PositiveDimension | None = None
    height: PositiveDimension
    order: PositiveCount | None = optional()


class ColumnParameters(Model):
    sections: list[ColumnSection] = Field(min_length=1)

    @model_validator(mode="after")
    def check_sections(self):
        if len({s.id for s in self.sections}) != len(self.sections):
            raise ValueError("Los tramos deben tener IDs únicos")
        if any(s.order is not None and s.order.value != i for i, s in enumerate(self.sections, 1)):
            raise ValueError("El orden citado de los tramos debe coincidir con la secuencia")
        for low, high in zip(self.sections, self.sections[1:]):
            if abs((low.top_diameter or low.diameter).value - high.diameter.value) > 1e-6:
                raise ValueError(
                    "Los diámetros contiguos requieren un tramo de transición explícito"
                )
        return self


class TankParameters(Model):
    diameter: PositiveDimension
    height: PositiveDimension
    roof: Literal["flat", "conical", "domed"]
    roof_height: Dimension
    roof_evidence: Attribute | None = optional()

    @model_validator(mode="after")
    def check_roof(self):
        height = self.roof_height.value
        if self.roof_evidence is not None and (
            self.roof_evidence.value != self.roof or self.roof_evidence.unit != "1"
        ):
            raise ValueError(
                "La evidencia del tipo de techo debe coincidir con roof y tener unidad 1"
            )
        if (self.roof == "flat" and height != 0) or (self.roof != "flat" and height <= 0):
            raise ValueError(
                "El techo plano tiene altura cero; los otros requieren altura positiva"
            )
        if self.roof == "domed" and height > self.diameter.value / 2:
            raise ValueError("La profundidad del techo curvo no puede superar el radio")
        return self


class FlangeParameters(Model):
    outer_diameter: PositiveDimension
    thickness: PositiveDimension


class PlatformParameters(Model):
    id: Identifier
    origin: Vector3
    size: Vector3

    @model_validator(mode="after")
    def check_size(self):
        if any(getattr(self.size, axis).value <= 0 for axis in "xyz"):
            raise ValueError("La plataforma requiere tamaños positivos")
        return self


class LadderParameters(Model):
    id: Identifier
    origin: Vector3
    width: PositiveDimension
    height: PositiveDimension
    rail_diameter: PositiveDimension
    rung_spacing: PositiveDimension

    @model_validator(mode="after")
    def check_spacing(self):
        if self.rung_spacing.value > self.height.value:
            raise ValueError("La escalera debe contener al menos un peldaño")
        if self.width.value <= 2 * self.rail_diameter.value:
            raise ValueError("Las barras de la escalera deben quedar separadas")
        if self.height.value / self.rung_spacing.value > 1000:
            raise ValueError("Demasiados peldaños: revise las unidades")
        return self


class SheetSizeMM(Model):
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


class SheetView(Model):
    kind: ViewKind
    bbox: BBox


class SheetMapEntry(Model):
    page: int = Field(ge=1)
    size: Literal["A0", "A1", "A2", "A3", "A4"] | SheetSizeMM
    rotation: Literal[0, 90, 180, 270]
    text_layer: Literal["text", "strokes", "none"]
    views: list[SheetView]


class NozzleScheduleRow(Model):
    source: Source
    fields: dict[Identifier, Attribute]


class NozzleSchedule(Model):
    source: Source
    rows: dict[Identifier, NozzleScheduleRow] = Field(min_length=1)
    complete: bool = False


class Document(Model):
    id: Identifier
    filename: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    sha256: SHA256
    page_count: int | None = Field(default=None, ge=1)
    # Ausente = original aportado. Una orden de diseño es un JSON propio, nunca un original.
    role: Literal["orden_diseno"] | None = optional()
    sheet_map: list[SheetMapEntry] | None = optional()
    drawing_revision: Tag | None = optional()
    nozzle_schedule: NozzleSchedule | None = optional()

    @model_validator(mode="after")
    def check_sheet_map(self):
        pages = [entry.page for entry in self.sheet_map or []]
        if len(set(pages)) != len(pages):
            raise ValueError("sheet_map contiene páginas repetidas")
        if any(self.page_count is None or page > self.page_count for page in pages):
            raise ValueError("sheet_map contiene una página fuera de page_count")
        if self.drawing_revision is not None:
            source = self.drawing_revision.source
            if (
                self.role is not None
                or source.document_id != self.id
                or source.bbox is None
                or source.page is None
                or self.page_count is None
                or source.page > self.page_count
            ):
                raise ValueError("La revisión del plano debe citar su propio original")
        if self.nozzle_schedule is not None:
            schedule = self.nozzle_schedule
            sources = [schedule.source]
            for row in schedule.rows.values():
                sources.append(row.source)
                sources.extend(field.source for field in row.fields.values())
            if (
                self.role is not None
                or any(
                    s.document_id != self.id or s.page != schedule.source.page or s.bbox is None
                    for s in sources
                )
                or schedule.source.page is None
                or (self.page_count is not None and schedule.source.page > self.page_count)
            ):
                raise ValueError("La tabla de boquillas debe citar la misma página de su original")
        return self


class Derivation(Model):
    """Revisión creada desde otra por una propuesta confirmada, no por una extracción."""

    kind: Literal["cambio_diseno", "reversion"]
    revision_id: str = Field(min_length=1)
    input_sha256: SHA256
    proposal_id: Identifier
    order_document_id: Identifier


class Nozzle(Model):
    id: Identifier
    stable_id: Identifier | None = None
    diameter: Dimension
    projection: Dimension
    elevation: Elevation
    azimuth: Angle
    position: Vector3 | None = None
    direction: Direction3 | None = None
    flange: FlangeParameters | None = None
    service: Attribute | None = None
    rating: Attribute | None = None
    # Tamaño nominal (NPS, pulgadas) de la tabla del GA o de la HDM, citado como el rating.
    size_nps: Attribute | None = optional()
    # Norma de la brida leída del plano o de la especificación: «B16.5», «B16.47A» o «B16.47B».
    # Hasta NPS 24 se deduce B16.5; desde NPS 26 la serie de B16.47 tiene que estar trazada.
    flange_standard: Attribute | None = optional()
    nozzle_type: Literal["radial", "tangential", "top", "bottom", "inclined"] | None = None

    @model_validator(mode="after")
    def check_sizes(self):
        if self.diameter.value <= 0 or self.projection.value <= 0:
            raise ValueError("Diámetro y proyección de boquilla deben ser positivos")
        if (self.position is None) != (self.direction is None):
            raise ValueError("Posición y dirección explícitas se aportan juntas")
        if self.position is not None and abs(self.position.z.value - self.elevation.value) > 1e-6:
            raise ValueError("La elevación debe coincidir con la coordenada Z explícita")
        if self.flange and self.flange.outer_diameter.value <= self.diameter.value:
            raise ValueError("La brida debe superar el diámetro de la boquilla")
        if self.flange and self.flange.thickness.value > self.projection.value:
            raise ValueError("La brida no puede ser más gruesa que la proyección")
        return self


def nozzle_misfit(
    diameter: float, elevation: float, vessel_diameter: float, shell_bottom: float, height: float
) -> str | None:
    """Por qué una boquilla radial no cabe en la virola, o None si cabe (mm)."""
    radius = diameter / 2
    if not shell_bottom + radius <= elevation <= shell_bottom + height - radius:
        return "debe quedar dentro de la virola"
    if diameter >= vessel_diameter:
        return "diámetro incompatible con la virola"
    return None


class Equipment(Model):
    id: Identifier
    tag: Tag
    kind: Literal[
        "vertical_vessel", "horizontal_vessel", "column", "tank", "pump", "compressor", "generic"
    ] = "vertical_vessel"
    lod: Literal[1, 2, 3] = 2
    support: Literal["skirt", "legs", "saddles", "lugs", "baseplate", "none"] | None = None
    envelope: Envelope | None = None
    # Vacío no se serializa: los recipientes y las huellas ya aprobadas no cambian.
    components: list[SkidPart] | None = optional()
    diameter: Dimension | None = None
    height: Dimension | None = None  # Longitud de virola entre tangentes, no altura total.
    head_depth: Dimension | None = None  # Profundidad común de los dos fondos semielipsoidales.
    skirt_height: Dimension | None = None  # Desde suelo hasta la tangente inferior de la virola.
    skirt_thickness: Dimension | None = None
    legs: LegParameters | None = optional()
    horizontal: HorizontalParameters | None = None
    column: ColumnParameters | None = None
    tank: TankParameters | None = None
    platforms: list[PlatformParameters] = Field(default_factory=list)
    ladders: list[LadderParameters] = Field(default_factory=list)
    attributes: dict[Identifier, Attribute] = Field(default_factory=dict)
    nozzles: list[Nozzle]

    @property
    def effective_support(self) -> str:
        # El contrato anterior omitía support para las familias por defecto.
        return self.support or DEFAULT_SUPPORT.get(self.kind, "none")

    @property
    def shell_bottom(self) -> float:
        if self.legs is not None:
            return self.legs.height.value
        return self.skirt_height.value if self.skirt_height else 0

    @property
    def total_height(self) -> float:
        if self.lod == 1 and self.envelope:
            return self.envelope.origin.z.value + self.envelope.size.z.value
        if self.horizontal:
            return self.horizontal.support_height.value + self.horizontal.diameter.value
        if self.column:
            return self.shell_bottom + sum(s.height.value for s in self.column.sections)
        if self.tank:
            return self.tank.height.value + self.tank.roof_height.value
        if self.height and self.head_depth:
            return self.shell_bottom + self.head_depth.value + self.height.value
        return self.envelope.size.z.value if self.envelope else 0

    @model_validator(mode="after")
    def check_geometry(self):
        ids = [n.id for n in self.nozzles]
        if len(ids) != len(set(ids)):
            raise ValueError("Las boquillas deben tener identificadores únicos")
        piezas = [p.id for p in self.components or []]
        if len(piezas) != len(set(piezas)):
            raise ValueError("Los componentes exteriores deben tener identificadores únicos")
        stable_ids = [n.stable_id or n.id for n in self.nozzles]
        if len(stable_ids) != len(set(stable_ids)):
            raise ValueError("Las identidades estables de boquillas deben ser únicas")
        for name in GEOMETRY_FIELDS:
            value = getattr(self, name)
            if value is not None and value.value <= 0:
                raise ValueError(f"{name}: la dimensión física debe ser positiva")
        for name in ("platforms", "ladders"):
            ids = [item.id for item in getattr(self, name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name}: IDs duplicados")
        specs = {"horizontal_vessel": self.horizontal, "column": self.column, "tank": self.tank}
        for kind, spec in specs.items():
            if spec is not None and self.kind != kind:
                raise ValueError("Parámetros de familia incompatibles con kind")
        support = self.effective_support
        if support != "skirt" and (
            self.skirt_height is not None or self.skirt_thickness is not None
        ):
            raise ValueError("skirt_height y skirt_thickness requieren soporte skirt")
        if self.legs is not None and support != "legs":
            raise ValueError("legs requiere soporte legs")
        if self.lod >= 2:
            if self.kind in ("pump", "compressor", "generic"):
                raise ValueError("Esta tipología requiere envolvente de nivel 1")
            if (self.kind, support) not in LOD2_REQUIREMENTS:
                raise ValueError(f"Soporte {support} incompatible con {self.kind}")
        missing = missing_fields(self)
        if missing:
            raise ValueError("Faltan campos de geometría: " + ", ".join(missing))
        if self.lod == 3:
            if not (any(n.flange for n in self.nozzles) or self.platforms or self.ladders):
                raise ValueError("El nivel 3 requiere detalles con evidencia")
            if any(n.flange and n.rating is None for n in self.nozzles):
                raise ValueError("La brida de nivel 3 requiere rating trazado")
        elif self.platforms or self.ladders or any(n.flange for n in self.nozzles):
            raise ValueError("Los detalles solo se exportan declarando nivel 3")
        if (self.kind != "vertical_vessel" or self.lod == 1) and any(
            n.position is None for n in self.nozzles
        ):
            raise ValueError(
                "Las boquillas de esta familia requieren posición y dirección explícitas"
            )
        if self.kind != "vertical_vessel" or self.lod == 1:
            return self
        if (
            self.skirt_thickness is not None
            and self.skirt_thickness.value >= self.diameter.value / 2
        ):
            raise ValueError("El espesor del faldón debe ser menor que el radio")
        if self.shell_bottom <= self.head_depth.value:
            raise ValueError("El fondo inferior debe quedar por encima del suelo")
        if self.head_depth.value > self.diameter.value / 2:
            raise ValueError("Esta familia admite fondos con profundidad hasta el radio")
        for nozzle in self.nozzles:
            if nozzle.position is not None:
                continue
            if nozzle.nozzle_type not in (None, "radial"):
                raise ValueError("Una boquilla no radial requiere posición y dirección explícitas")
            problem = nozzle_misfit(
                nozzle.diameter.value,
                nozzle.elevation.value,
                self.diameter.value,
                self.shell_bottom,
                self.height.value,
            )
            if problem:
                raise ValueError(f"Boquilla {nozzle.id}: {problem}")
        return self


class Approval(Model):
    reviewer: str = Field(min_length=2)
    timestamp: datetime = Field(strict=False)
    input_sha256: SHA256

    @model_validator(mode="after")
    def check_timezone(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("La fecha de revisión debe incluir zona horaria")
        return self


class RunInfo(Model):
    strategy: str
    providers: list[str]
    seconds: float = Field(ge=0)
    gpu_seconds: float | None = Field(default=None, ge=0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_eur: float | None = Field(default=None, ge=0)
    external_calls: int = Field(ge=0)
    accounting_complete: bool = True


WeldKindValue = Literal["circumferential", "longitudinal", "nozzle", "attachment"]
PieceId = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9_./-]+$")]


class WeldKind(TracedField):
    value: WeldKindValue
    unit: Literal["1"] = "1"


class Weld(Model):
    """Unión soldada entre dos piezas (plan 7.5). Opcional y fuera de la huella de aprobación.

    El `id` depende solo de lo que une (`W:V01|V02`, `W:SHELL|HEAD_BOTTOM`, `W:N1|SHELL`), así que
    una soldadura que no cambia conserva su GUID entre revisiones. `elevation` es la distancia
    axial desde la T.L. de referencia: la inferior en verticales, columnas y tanques, y la primera
    en horizontales. Nunca se inventa el tamaño: `size` y `note` solo si el plano los da.
    """

    id: str = Field(pattern=r"^W:[A-Za-z0-9_./|:-]+$")
    kind: WeldKind
    joins: list[PieceId] = Field(min_length=2, max_length=2)
    elevation: Dimension | None = optional()
    azimuth: Angle | None = optional()
    size: Attribute | None = optional()
    note: Attribute | None = optional()

    def traced(self) -> dict[str, TracedField]:
        names = ("kind", "elevation", "azimuth", "size", "note")
        return {
            f"welds.{self.id}.{name}": field
            for name in names
            if (field := getattr(self, name)) is not None
        }


class RevisionIdentifiers(Model):
    drawing_number: Tag | None = optional()
    drawing_revision: Tag | None = optional()
    project_number: Tag | None = optional()


class Revision(Model):
    schema_version: Literal["0.3"] = "0.3"
    project_id: Identifier
    revision: str = Field(min_length=1)
    dataset: Literal["synthetic", "real"]
    documents: list[Document] = Field(min_length=1)
    equipment: Equipment
    approval: Approval | None = None
    run: RunInfo | None = None
    # Boquillas leídas que aún no entraron en el modelo. Su presencia documental se comprueba
    # por separado en las tablas de boquillas.
    unplaced_nozzles: list[Identifier] = Field(default_factory=list)
    unplaced_nozzle_reasons: dict[Identifier, list[str]] = Field(
        default_factory=dict, exclude_if=lambda reasons: not reasons
    )
    derived_from: Derivation | None = optional()
    identifiers: RevisionIdentifiers | None = optional()
    # Uniones soldadas: fuera de la huella de aprobación hasta que su lectura esté medida.
    welds: list[Weld] = Field(default_factory=list, exclude_if=lambda welds: not welds)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy(cls, data):
        return migrate_revision(data) if isinstance(data, dict) else data

    @model_validator(mode="after")
    def check_sources_and_approval(self):
        docs = {d.id: d for d in self.documents}
        if len(docs) != len(self.documents):
            raise ValueError("Los documentos deben tener identificadores únicos")
        for path, field in self.traced_fields().items():
            document = docs.get(field.source.document_id)
            if document is None:
                raise ValueError(f"{path}: referencia a documento desconocido")
            for source in [field.source, *[a.source for a in field.alternatives]]:
                reference = docs.get(source.document_id)
                if reference is None:
                    raise ValueError(f"{path}: alternativa con documento desconocido")
                if reference.page_count and source.page and source.page > reference.page_count:
                    raise ValueError(f"{path}: página fuera del documento")
                region = source.inferred_region
                if region is not None and (
                    reference.page_count is None or region.page > reference.page_count
                ):
                    raise ValueError(f"{path}: página de inferred_region fuera del documento")
                # Un valor pedido como diseño nunca se atribuye al plano original, ni una
                # lectura del plano a la orden.
                if (source.channel == "diseno") != (reference.role == "orden_diseno"):
                    raise ValueError(
                        f"{path}: una orden de diseño solo cita su documento de orden"
                        if source.channel == "diseno"
                        else f"{path}: el documento de orden no es evidencia de lectura"
                    )
        ids = [weld.id for weld in self.welds]
        if len(ids) != len(set(ids)):
            raise ValueError("Las soldaduras deben tener identificadores únicos")
        for weld in self.welds:
            for path, field in weld.traced().items():
                if field.source.document_id not in docs:
                    raise ValueError(f"{path}: referencia a documento desconocido")
        if self.derived_from:
            order = docs.get(self.derived_from.order_document_id)
            if order is None or order.role != "orden_diseno":
                raise ValueError("La revisión derivada debe incluir su documento de orden")
        if self.approval:
            if self.pending_review():
                raise ValueError("La aprobación requiere revisar todos los campos")
            # Un DRAFT con menos sí existe: sin modelo no habría nada que revisar ni completar.
            equipment = self.equipment
            if (
                equipment.kind == "vertical_vessel"
                and equipment.lod >= 2
                and len(equipment.nozzles) < 3
            ):
                raise ValueError(
                    "El recipiente vertical de nivel 2/3 necesita al menos tres boquillas"
                )
            # Una boquilla leída que no entró en el modelo no la ha visto nadie en la revisión:
            # aprobar así dejaría fuera del IFC aprobado un dato del plano sin decisión humana.
            if self.unplaced_nozzles:
                raise ValueError(
                    "Hay boquillas leídas sin colocar en el modelo ("
                    + ", ".join(self.unplaced_nozzles)
                    + "): hay que resolverlas antes de aprobar"
                )
            if self.approval.input_sha256 != self.fingerprint():
                raise ValueError("La aprobación no corresponde a estos datos; vuelva a revisar")
        return self

    def traced_fields(self) -> dict[str, TracedField]:
        result = fields(self.equipment)
        result.update(_traced_fields(self.identifiers, "identifiers"))
        return result

    def pending_review(self) -> list[str]:
        return [
            p for p, f in self.traced_fields().items() if f.state not in ("accepted", "corrected")
        ]

    def fingerprint(self) -> str:
        # Vacío no cuenta: las huellas ya aprobadas siguen siendo válidas.
        exclude = (
            {"approval", "welds", "unplaced_nozzle_reasons"}
            if self.unplaced_nozzles
            else {
                "approval",
                "unplaced_nozzles",
                "unplaced_nozzle_reasons",
                "welds",
            }
        )
        content = json.dumps(
            self.model_dump(mode="json", exclude=exclude),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(content.encode()).hexdigest()


GEOMETRY_FIELDS = ("diameter", "height", "head_depth", "skirt_height", "skirt_thickness")


DEFAULT_SUPPORT = {"vertical_vessel": "skirt", "horizontal_vessel": "saddles"}
LOD1_REQUIREMENTS = tuple(
    f"envelope.{part}.{axis}" for part in ("origin", "size") for axis in "xyz"
)
_VERTICAL_SHELL = ("diameter", "height", "head_depth")
LOD2_REQUIREMENTS = {
    ("vertical_vessel", "skirt"): (*_VERTICAL_SHELL, "skirt_height"),
    ("vertical_vessel", "legs"): (*_VERTICAL_SHELL, "legs.count", "legs.height"),
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
    ("column", "none"): ("column.sections",),
    ("column", "skirt"): ("column.sections", "skirt_height"),
    ("tank", "none"): ("tank.diameter", "tank.height", "tank.roof", "tank.roof_height"),
}


def missing_fields(equipment: Equipment) -> list[str]:
    """Devuelve rutas pendientes para el nivel de detalle, la tipología y su soporte."""
    required = (
        LOD1_REQUIREMENTS
        if equipment.lod == 1
        else LOD2_REQUIREMENTS.get((equipment.kind, equipment.effective_support), ())
    )

    def present(path: str) -> bool:
        value = equipment
        for segment in path.split("."):
            if isinstance(value, list):
                index = int(segment)
                value = value[index] if index < len(value) else None
            else:
                value = getattr(value, segment, None)
        return bool(value) if isinstance(value, list) else value is not None

    return [path for path in required if not present(path)]


def fields(equipment: Equipment) -> dict[str, TracedField]:
    """Rutas estables con IDs de componentes e índices en listas sin identificador."""
    return _traced_fields(equipment, "")


def _traced_fields(model, prefix: str) -> dict[str, TracedField]:
    result = {}

    def visit(value, path):
        if isinstance(value, TracedField):
            result[path] = value
        elif isinstance(value, BaseModel):
            for name in type(value).model_fields:
                visit(getattr(value, name), f"{path}.{name}" if path else name)
        elif isinstance(value, dict):
            for name, child in value.items():
                visit(child, f"{path}.{name}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}.{getattr(child, 'id', index)}")

    visit(model, prefix)
    return result


def load_revision(path: Path) -> Revision:
    return Revision.model_validate_json(path.read_text(encoding="utf-8"))


def migrate_revision(data: dict) -> dict:
    """0.2 → 0.3 sin mutar la entrada; una migración nunca conserva la aprobación."""
    if data.get("schema_version") != "0.2":
        return data
    result = copy.deepcopy(data)
    result["schema_version"] = "0.3"
    result["approval"] = None

    def visit(value):
        if isinstance(value, dict):
            source = value.get("source")
            if isinstance(source, dict) and "value" in value:
                value["state"] = "accepted" if source.get("reviewed") else "candidate"
                if source.get("confidence_raw") is None:
                    source["confidence_raw"] = source.get("confidence")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result.get("equipment", {}))
    return result

# Contrato 0.3 y compatibilidad con 0.2

Emitir esquema con `uv run trazia schema -o generated/revision.schema.json`.
Ejemplo completo en `examples/vessel_rev_a.json`.

Cada campo contiene `value`, `unit` y `source`. `source` incluye documento, página o
hoja/celda, localizador, región PDF opcional normalizada `[x0,y0,x1,y1]`, score y revisión.
El origen de coordenadas de la región PDF es la esquina superior izquierda.

La revisión incluye proyecto, revisión, tipo de dataset, catálogo documental y un equipo.
Los IDs de proyecto/equipo/boquilla son estables y solo admiten letras, números, `_` y `-`.
El tag tiene su propia evidencia; no se usa para calcular GUID porque puede cambiar.


## Contrato 0.3

Se conservan los nombres de todos los campos de 0.2. Se añaden:

- `state`: candidate, conflict, abstained, accepted, corrected o assumed en cada valor trazable.
- `interval`: low, high, level (entre 0 y 1) y method=conformal; solo se informa si se ha calculado.
- `alternatives`: valores/unidades con su propia evidencia; `explanation` explica la incertidumbre.
- `Source`: confidence_raw, channel, strategy, model, prompt_sha256, grounded,
  text_original y unit_original. Son opcionales: ausencia significa desconocido.
- `Equipment` contiene siete tipologías con LOD 1, 2 o 3. La tabla de familias define
  los campos obligatorios de cada soporte. Un DRAFT vertical puede tener menos de tres boquillas
  completas. La aprobación exige al menos tres.
- `Envelope`: origin y size con componentes x/y/z en mm y evidencia por componente. El origen
  puede ser cero o negativo; las dimensiones físicas y los tamaños deben ser positivos.
- `Nozzle`: service, rating y nozzle_type opcionales.
- `Revision.run`: estrategia, proveedores, segundos totales/GPU, tokens, coste y llamadas externas.
- `Revision.unplaced_nozzles`: marcas leídas que no entraron en el modelo (incompletas o fuera de
  la virola). `compare` no las informa como altas ni bajas y las devuelve en `unplaced_nozzles`.
  Vacío no cuenta para la huella: las aprobaciones anteriores siguen siendo válidas.
  Una revisión con boquillas sin colocar no se puede aprobar: nadie las ha revisado.
  Un coste desconocido es null; no se transforma en cero.

`source.reviewed` se sincroniza con `state in (accepted, corrected)`; un supuesto no equivale a
aceptación. No se aprueba una revisión con conflictos, abstenciones o supuestos pendientes.
Las alternativas también se validan contra el catálogo documental y los límites de página.

### Migrar

```bash
uv run trazia migrate antiguo.json -o revision-0.3.json
uv run trazia schema -o generated/revision.schema.json
```

`migrate_revision(dict)` no modifica la entrada y es idempotente. `load_revision` acepta 0.2 para
mantener operativo el extractor actual; devuelve siempre 0.3. reviewed=true migra a accepted;
el resto, a candidate. La confianza original también se guarda en confidence_raw. **Migrar no
calibra el score 0,75 del baseline**: Lectura debe aportar la calibración medida antes de usarlo
como probabilidad de acierto. No se inventan canales, modelos, intervalos ni metadatos de coste.

Una migración retira la aprobación porque cambia la huella. Los datos y la evidencia siguen
revisables; la nueva revisión necesita una aprobación nueva. El identificador estable del equipo
y de cada boquilla no cambia, y por tanto tampoco cambia el algoritmo de GUID del IFC.

## Formato acotado que reconoce el baseline

En texto PDF, una etiqueta por región o fila:

```text
TAG = V-101
DIAMETER = 2000 mm
HEIGHT = 6000 mm
HEAD_DEPTH = 500 mm
SKIRT_HEIGHT = 1200 mm
SKIRT_THICKNESS = 20 mm
NOZZLE N1: DIAMETER=200 mm; PROJECTION=400 mm; ELEVATION=2500 mm; AZIMUTH=0 deg
```

Para aprobarse, la familia vertical de nivel 2/3 necesita al menos tres boquillas completas. Se normalizan longitudes `mm`, `cm`, `m`
e `in` a milímetros. Solo se reconocen decimales con punto; no se interpretan separadores
de miles, unidades implícitas, cotas gráficas o ángulos sin referencia.

En Excel, una fila por parámetro: columna de etiqueta, valor y unidad. Atributos reconocidos:
`DESIGN_PRESSURE` (bar/kPa/MPa), `DESIGN_TEMPERATURE` (C), `OPERATING_WEIGHT` (kg)
y `MATERIAL` (sin unidad física, representada como `1`). No se evalúan fórmulas.

Se aceptan algunos alias literales en inglés/español; no son un motor general de comprensión.
La separación de columnas PDF usa una heurística de espacio. Planos densos y tablas con
saltos de línea pueden necesitar el futuro extractor de visión.

## Incertidumbre y conflictos

El score del baseline es 0,75: identifica candidatos de una regla, no una probabilidad de
acierto calibrada. No se convierte en aprobación. Todos los candidatos empiezan sin revisar.
Dos valores o unidades diferentes para el mismo campo bloquean `assemble`; la interfaz
permite desmarcar evidencias contradictorias. Si faltan parámetros se informa del error y
no se completa la geometría con valores inventados.

La interfaz `Extractor.extract(bundles) -> list[Candidate]` es el punto de extensión.
Un adaptador IA deberá conservar páginas/celdas/regiones y devolver campos desconocidos
fuera del contrato geométrico hasta su resolución. El texto de documentos es dato, nunca
instrucciones para ejecutar acciones o cambiar las reglas del sistema.

## Aprobación y revisiones

`approve` verifica hashes de originales, registra una declaración de revisión humana y
crea la huella de los datos incluyendo unidades, fuentes y documentos. El validador rechaza
una aprobación cuyo hash no coincide. No autentica al revisor ni verifica la verdad técnica
del contenido. Modificar datos requiere una nueva revisión.

La comparación separa cambios semánticos (valor/unidad), de evidencia y de catálogo.
La unidad de un atributo es parte del significado: el mismo número en bar y MPa cambia.
Con el extra geo/API se reconocen equivalencias físicas; 1 bar y 100 kPa se registran como cambio de procedencia, sin cambio de valor físico.

Los JSON sintéticos de la fase 0.1 eran un borrador local sin publicar. La versión 0.2
añade unidades por campo, tag trazable, fondos, faldón y aprobación; no es compatible con
ese contrato anterior. Los ejemplos del repositorio ya usan 0.3.


## Familias paramétricas y detalle (0.3, ampliación aditiva)

Todos los parámetros numéricos siguientes son campos trazados (valor, unidad mm, fuente,
estado e incertidumbre). Los tipos se publican también en `trazia.families.parameters`.

| Tipología | Soporte | Campos obligatorios |
| --- | --- | --- |
| `vertical_vessel` | `skirt` | `diameter`, `height` entre tangentes, `head_depth` y `skirt_height` |
| `vertical_vessel` | `legs` | `diameter`, `height`, `head_depth`, `legs.count` y `legs.height` |
| `horizontal_vessel` | `saddles` | `horizontal` con diámetro, longitud, fondo, altura y ancho de silleta, ancho transversal y dos posiciones |
| `column` | `skirt` | `column.sections` y `skirt_height` |
| `column` | `none` | `column.sections`, para columnas apoyadas al nivel del suelo |
| `tank` | `none` | `tank.diameter`, `tank.height`, `tank.roof` y `tank.roof_height` |
| `pump`, `compressor`, `generic` | Según equipo | LOD 1 con las seis componentes trazadas de `envelope.origin` y `envelope.size` |

En el contrato anterior se podía omitir `support`. Se sigue interpretando como `skirt` en
recipientes verticales, `saddles` en horizontales y `none` en columnas y tanques. El valor
omitido se conserva al serializar.

El validador usa `missing_fields(equipment)` para señalar las rutas de los campos pendientes
en el mismo formato de puntos e índices que `fields()`. `column.sections` señala la
colección completa cuando faltan los tramos. Cada tramo presente tiene un ID estable,
diámetro inferior y altura. El diámetro superior es opcional y un salto de diámetro
requiere un tramo de transición.

El ensamblador recibe `column.sections.<ID>.diameter`, `.height` y, para una transición,
`.top_diameter`. Esos diámetros son exteriores. Con varios tramos, cada uno requiere
`.order` citado y numerado desde 1, de abajo arriba. `shell.courses.<ID>.height` puede
aportar la altura de un tramo cuya pertenencia a la columna ya esté identificada.

`legs.count` es un entero positivo con unidad `1`. `legs.height` mide desde el suelo hasta
la tangente inferior y determina `shell_bottom`. `legs.section` puede documentar la sección
o el perfil trazado. Cuando se informan `legs.azimuths`, se registra un ángulo distinto por
pata en el sistema interno (+X, sentido antihorario visto desde +Z). El IFC representa
las patas con cilindros simplificados hasta la tangente inferior. Marca la sección
supuesta en `Pset_TrazIA` y en color ámbar. Si faltan los azimuts, la distribución
uniforme se marca también como supuesta. Los parámetros de patas requieren soporte
`legs`. `skirt_height` y `skirt_thickness` requieren soporte `skirt`.

`skirt_thickness` se puede omitir del contrato. El IFC del recipiente vertical requiere
un espesor trazado. Un espesor derivado debe indicar `state: assumed` y la regla declarada
en `source.rule`. En LOD 2/3, el faldón de una columna requiere también su diámetro
exterior trazado en `attributes.skirt_diameter`.

La virola horizontal se extiende en X entre la tangente izquierda (cero) y `length`.
`diameter` es exterior y `support_height` va desde el suelo hasta la cara inferior
de la virola. Para recipientes y tanques, si la lectura declara
`attributes.diameter_basis=inside`, se requiere `attributes.shell_thickness` para
obtener el diámetro exterior. Si declaran `attributes.support_height_basis=axis`, el
ensamblador horizontal resta el radio exterior de la cota al eje.

Para una boquilla radial de virola, `station` es la X desde la tangente izquierda.
`azimuth` es el ángulo de cabezal (0° hacia +Z, 90° hacia +Y). La proyección se mide
desde la cara exterior: si la lectura aporta `projection_basis=axis` en su documento,
se resta el radio exterior. Las boquillas con geometría o referencia incompleta se
registran en `unplaced_nozzles`.

`tank.height` es la altura de la virola. La altura total suma `tank.roof_height`.
El tipo de techo se conserva con su cita en `tank.roof_evidence`. Un techo plano
tiene altura cero. Un techo curvo o cónico requiere su altura citada. Si el lector
declara un diámetro interior, se necesita el espesor general de virola para obtener
el diámetro exterior. Cualquier familia admite una envolvente de LOD 1 con origen
local y tamaño positivo.

Para convertir una boquilla a las coordenadas del equipo desde las cotas del plano se
requiere la referencia citada de elevación (`grade` o `lower_tl`) y de proyección
(`axis` o `shell`). La proyección desde el eje se convierte con el radio exterior del
tramo. La cota desde la tangente inferior se convierte con la altura del soporte.

Las boquillas conservan los cuatro campos históricos. Fuera de la familia vertical radial
requieren también position (Vector3 en mm) y direction (componentes trazadas de unidad 1,
vector no nulo). Se normaliza la dirección al generar geometría; elevation coincide con Z.
En vertical se admiten también estas colocaciones explícitas para boquillas superiores,
inferiores, tangenciales o inclinadas. Una dirección ausente no se adivina.

Nivel 3 requiere al menos un detalle trazado: flange en boquilla (outer_diameter, thickness
más rating), platforms (id, origin, size) o ladders (id, origin, width, height, rail_diameter,
rung_spacing). Una brida representa su envolvente anular según dimensiones aportadas; no
se atribuye conformidad ASME ni se deducen dimensiones de una clase sin tabla autorizada.
Los campos de detalles también bloquean la aprobación. No se aceptan detalles con lod=1/2.

`fields()` recorre los parámetros trazados. Usa IDs estables para boquillas, tramos
y detalles e índices para `saddle_positions` y `legs.azimuths`.
Se conservan las rutas históricas y los GUID del ejemplo.
El IFC incluye LOD, Family y campos completos en TrazIA_Traceability.


## Identidad de boquillas y comparación

`nozzles[].stable_id` es opcional y administrativo: preserva el GUID si cambia el nombre `id`.
Sin él, se conserva el algoritmo histórico basado en id. Los stable_id efectivos deben ser
únicos. Con previous_id aprobado, el trabajo empareja boquillas y propaga identidades en una
copia DRAFT; no hereda una aprobación. La comparación de consulta no modifica revisiones.
El emparejamiento húngaro de nombres nuevos usa servicio, DN, posición y dirección;
los empates cercanos quedan ambiguos y no reciben identidad automáticamente. Su coste
es heurístico, no una probabilidad de acierto calibrada.

La comparación separa equivalencia física y tolerancia de la huella: ignorar una diferencia
menor de 1 mm para el informe no conserva una aprobación si el dato fue modificado.
Tolerancia angular por defecto: 0,5 grados con distancia circular. Los atributos numéricos
usan equivalencia de unidades con Pint; las temperaturas con C se interpretan como degC
solo en campos de temperatura. Las tolerancias se pueden pasar por ruta al comparador.

### Cambios por ID en el lote

`trazia lote` escribe `cambios_rev<A>_rev<B>.json` aunque alguna revisión no llegue a modelo.
Lo hace `lectura/cambios.py`, documentado en `docs/LECTURA_PUERTA.md`.

### Soldaduras (`welds`, M5)

`Revision.welds` es una lista opcional de `Weld` (plan 7.5). No forma parte de la huella de
aprobación: añadir, quitar o corregir una soldadura no invalida una aprobación hasta que su
lectura esté medida. Una revisión sin soldaduras se serializa igual que antes.

| Campo | Tipo | Nota |
| --- | --- | --- |
| `id` | `W:<pieza>\|<pieza>` | Depende solo de lo que une. Da el GUID (`<proyecto>/equipment/<id>/weld/<id>`), así que se conserva entre revisiones. |
| `kind` | trazado | `circumferential`, `longitudinal`, `nozzle` o `attachment` |
| `joins` | dos IDs de pieza | `SHELL`, `TANK`, `HEAD_BOTTOM`/`HEAD_LEFT`, `HEAD_TOP`/`HEAD_RIGHT`, `SKIRT`, `ROOF`, una boquilla, una virola (`V01`), un tramo (`1-2`) o un anillo (`C3`) |
| `elevation` | `Dimension`, opcional | Distancia axial desde la T.L. de referencia: la inferior en verticales, columnas y tanques, y la primera en horizontales |
| `azimuth` | `Angle`, opcional | Solo en longitudinales |
| `size`, `note` | `Attribute`, opcionales | Solo si el plano los da. El tamaño nunca se inventa. |

Entrada: los candidatos `welds.<ID>.{kind, joins, elevation_mm, azimuth_deg, size, note}` de
`lectura/soldaduras.py`. Las uniones deducidas con una regla `soldadura.*` nacen `assumed`. Una
unión sin `kind` o sin las dos piezas no entra en la revisión y deja un aviso.

En el IFC, cada soldadura es un `IfcFastener` con `PredefinedType=WELD` y la misma cantidad que
en el JSON:

- **Geometría:** un anillo de 20 mm a la cota en las circunferenciales, un anillo en la base de
  la boquilla y un tramo a lo largo de la generatriz en las longitudinales. Lleva el estilo
  «Soldadura», morado y distinto del naranja de «Geometría supuesta». Sin posición conocida
  (circunferencial sin cota, boquilla sin colocar), el `IfcFastener` va sin representación y con
  `SinGeometria = True`.
- **Relación:** `IfcRelConnectsWithRealizingElements` entre las dos piezas que une, cuando las
  dos existen en el IFC y son distintas. Virolas, tramos y anillos forman parte de la envolvente.
- **Pset `TrazIA_Soldadura`:** `Tipo`, `Une`, `Estado`, `Regla`, `Tamano`, `Nota`,
  `CotaDesdeTL_mm`, `SinGeometria`, `RequiereVerificacion` y `CitasJSON`.

Los tipos de la web (`web/src/lib/api/schema.ts`) se regeneran con `pnpm gen:api`.

### Reglas del ensamblado (`lectura/ensamblar.py`)

Completan la familia desde un candidato leído y dejan la regla en `source.rule`. Nunca
sustituyen un valor leído. Si suponen algo que el plano no dice, el campo nace `assumed` y la
pieza del IFC lleva `Pset_TrazIA.Estado = assumed` con su regla y el estilo de geometría
supuesta.

| Regla | Campo | Estado |
| --- | --- | --- |
| `horizontal.apoyo_base_a_eje` | `attributes.support_height_basis = axis` cuando la cota de la silleta se leyó de su base al eje | leído |
| `horizontal.ancho_silleta_como_la_fija` | `horizontal.saddle_width` desde `attributes.saddle_width_fixed` | supuesto |
| `tank.espesor_virola_1` | `attributes.shell_thickness` desde `tank.courses.1.thickness` | leído |
| `tank.flecha_cupula_radio_d` | `tank.roof_height` de un techo `domed`, con radio igual al diámetro | supuesto |
| `<familia>.diametro_interior_sin_espesor` | diámetro interior sin espesor de virola: se modela con el interior | supuesto |


## Entrada de envolventes LOD 1 (31/10)

El ensamblador acepta candidatos trazados `envelope.origin.{x,y,z}` y
`envelope.size.{x,y,z}` en mm. Las seis componentes y el tag deben estar presentes;
no se rellenan dimensiones ausentes. Se conserva el contrato 0.3 sin renombrar campos.
`attributes.equipment_type="pump"` identifica una bomba; sin esa clasificación la
familia es `generic`, siempre LOD 1.

El lector de bombas reconoce un alzado lateral, una planta y su nota de datum, y lee
las tres cotas exteriores. La esquina inferior local de representación se declara
con `state: assumed` y `source.rule: asumido.origen_bancada`. Su alineación con la planta
requiere confirmación. No se modelan
el motor ni salientes de boquillas que el lector no haya determinado. El IFC contiene
la envolvente declarada; el visor representa ese IFC. La aprobación de recipientes verticales de LOD 2/3 exige tres boquillas completas.

El pipeline toma el tag del nombre del fichero cuando el lector todavía no aporta uno.
La fuente registra esa procedencia para que pueda revisarse.

## Identificadores y estructura de la hoja

`Revision.identifiers` contiene los campos trazados opcionales `drawing_number`,
`drawing_revision` y `project_number`. Sus fuentes y alternativas citan documentos de la
misma revisión. `Revision.revision` mantiene el identificador de la revisión del dataset.
El diff usa esa revisión para emparejar y muestra por separado la marca impresa en el cajetín.

`Document.sheet_map` admite una entrada por página catalogada del documento. Cada entrada
contiene `page`, `size` (A0 a A4 o un objeto con `width_mm` y `height_mm` positivos),
`rotation` (0, 90, 180 o 270 grados), `text_layer` (`text`, `strokes` o `none`) y
`views`. Las entradas usan páginas únicas dentro de `page_count`. Las vistas registran
`kind` y `bbox`. Los tipos de vista son `elevation`, `plan`, `section`, `nozzle_table`,
`design_data`, `weights`, `bom`, `title_block`, `notes` y `detail`.
El pipeline todavía deja el mapa sin rellenar.

`Source.inferred_region` registra `page`, `bbox` y, opcionalmente, un `view` de esa misma
lista. Sirve para valores deducidos de una región, como el azimut indicado por la posición
de una boquilla en planta. La página debe existir en el documento citado. Las cajas de
vistas, regiones inferidas y palabras se expresan como `[x0, y0, x1, y1]`, con origen
arriba a la izquierda, coordenadas entre 0 y 1 y extremos ordenados.
`grounded: true` requiere una caja de palabra cuando se aporta una región inferida.

`Source.rule` identifica la regla determinista aplicada y cumple `^[a-z0-9_.:-]+$`. Por
ejemplo, `tablas.lista_boquillas` o `rotulos.el_tl`. Es obligatorio en campos con
`state: assumed`.

Los campos de M1 se omiten cuando están ausentes. El esquema sigue en `0.3` y las
huellas de los ejemplos históricos se conservan. Los tipos de TypeScript se actualizarán
al incorporar la web.

## Sistema de referencia interno (C.4, 31/10)

El IFC usa un sistema local dextrógiro, con Z vertical positiva y origen en el centro del equipo
en planta a nivel del suelo local; no implica georreferenciación ni Norte de planta. Las longitudes
del contrato se expresan en mm y se convierten una vez a metros en el IFC.

Para las boquillas radiales del recipiente vertical, azimut 0° apunta a +X y 90° a +Y:
`(x, y, z) = (R cos(a), R sin(a), elevación)`. El giro es antihorario visto desde +Z.
Los elementos con posición/dirección explícitas usan esos vectores trazados. Cambiar este
convenio silenciosamente a Norte/horario desplazaría la geometría existente.

En la web, web-ifc incorpora `(X,Y,Z) → (X,Z,-Y)` en `flatTransformation`; el worker aplica
esa matriz una vez. Se comprobó su base con el IFC sintético, sin render ni inferencia GPU.
`GET /reference-system` declara unidades, ejes y límites. Las pruebas cardinales y de unidades
IFC están en `tests/test_plataforma_reference.py`.

La orientación del Norte de planta y la equivalencia con el IFC de referencia TR **no están
verificadas**. C.4 permanece parcial hasta disponer de una referencia autorizada. No se ha
abierto `data/private/` ni se atribuye este convenio matemático a VESOR o a TR.


### Normalización y referencia (01/11)

Sin cambios de esquema 0.3: Source conserva la unidad y el texto originales; presión absoluta sigue marcada como bara. El PATCH normaliza antes de validar y deja auditoría de la conversión. El IFC puede declarar Norte explícito y lleva Pset TrazIA_ReferenceFrame. [Convenios, casos ambiguos y límite TR](NORMALIZACION.md).

## Órdenes de diseño y revisiones derivadas (K.0, 08/11)

Ampliación aditiva de 0.3, sin cambiar `schema_version`. Los campos opcionales nuevos no se
serializan cuando faltan, así que los JSON y las huellas existentes no cambian.
`Source.channel = "diseno"` exige `Source.design` y un documento con `role: orden_diseno`.
Ese documento es la orden confirmada, no un original. Una orden no tiene página, región,
estrategia ni confianza estimada: confianza 1 y sin bruta. `Revision.derived_from` liga la
revisión DRAFT nueva con su base, su huella y la propuesta. Un valor de diseño nunca cita el
plano original y nunca entra en el aprendizaje de extracción.
[Matriz, API y límites](EDICION_ASISTIDA.md).

## Piezas de mecánicos con forma, clase IFC y clasificación (28/11)

Ampliación aditiva de 0.3, sin cambiar `schema_version`. Los campos nuevos son opcionales y no
se serializan cuando faltan, así que los JSON y las huellas existentes no cambian.

- `SkidPart.shape`: `box` (por defecto), `cylinder`, `revolve` o `extrude`. Cilindro,
  revolución y extrusión llevan `axis`. `revolve` gira un perfil `[(a, r)]` (coordenada absoluta
  sobre el eje y radio, en mm) alrededor de un eje que pasa por el centro de la envolvente.
  `extrude` estira un polígono de las otras dos coordenadas (en orden xyz) entre las caras de la
  envolvente. El perfil comparte la fuente de la envolvente.
- `SkidPart.ifc_class`: una de las clases IFC4 admitidas (`IfcPump`, `IfcCompressor`,
  `IfcElectricMotor`, `IfcHeatExchanger`, `IfcTank`, `IfcFilter`, `IfcUnitaryEquipment`,
  `IfcElectricDistributionBoard`, `IfcJunctionBox`, `IfcPlate`, `IfcMember`, `IfcFooting`,
  `IfcValve`, `IfcSensor`, `IfcPipeSegment`, `IfcPipeFitting`, `IfcMechanicalFastener`,
  `IfcDiscreteAccessory`, `IfcColumn`, `IfcBeam`, `IfcSlab`, `IfcRailing`). Lo que no tiene clase
  propia en IFC4 (multiplicador, acoplamiento, bancada) sale como `IfcBuildingElementProxy` con su
  `object_type`. `predefined_type` sigue el enumerado IFC4 de la clase (`USERDEFINED` si no hay).
- `SkidPart.classification` y `Equipment.classification`: lista de `{system, code, name}` para
  ISO 14224 (clase, tipo y subunidad), la norma API que aplique y la clase IFC4.
- Pieza que el plano no dibuja (rotor, rodetes, cojinetes, recorridos de tubería no acotados):
  su envolvente lleva `state: assumed`, una regla `asumido.*` y una explicación de cómo se ha
  dimensionado.
- `Source.bbox` de cada campo apunta a la vista del plano de la que se ha leído. Cuando el GA tiene
  vistas en láminas distintas, `Source.page` es la lámina de ese recuadro.
- Boquilla con tamaño `HOLD` en la tabla de puntos de conexión: `size_nps = "HOLD"`, diámetro
  provisional con regla `asumido.od_tamano_hold` y sin `flange_standard`.

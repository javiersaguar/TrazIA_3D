# Lectura para la puerta del backend

## Cotas de la envolvente

| Equipo | Cotas leídas en ambas revisiones | Pendiente de ensamblado o medida |
| --- | --- | --- |
| BF-V-0016 | Diámetro interior 800 mm, fondo inferior H = 257 mm, 4 patas, 1.000 mm de la base a la tangente y virola de 1.925 mm en rev1 y 1.940 mm en rev2 | La tapa superior es embridada. La cota de 2.100 mm llega a la cara de la brida y queda en `attributes.height_to_flange`. |
| 80V01 | Diámetro interior 1.900 mm, 5.700 mm entre tangentes, silletas en 750 y 4.950 mm, 1.620 mm de base a eje y 1.754 mm de ancho transversal | La silleta fija acota 230 mm. El ancho común queda pendiente. Los 475 mm de profundidad de fondo proceden de D/4 para el perfil 2:1 y se etiquetan como supuestos. |

El lote guarda la página, caja y regla de cada medida en `candidatos.json`. El informe de
`bench.oro` con ambas familias da un 0 % de error de diámetro en las cuatro revisiones. La
comparación de longitud de BF-V-0016 requiere distinguir el desarrollo axial de la cota a la
cara de brida del oro. Para Miguel quedan la semántica de la tapa y la integración del horizontal.

En una copia aislada con el commit de patas `551b984` de Miguel, el lote validó los dos IFC
DRAFT de BF-V-0016. Quedaron sin boquillas por la conversión pendiente de referencias al marco
del modelo. Las dos revisiones horizontales siguen pendientes del ensamblador de esa familia.

## Rumbos y revisión

El marco de rev1 publicado por Alejandro en `495c877` confirma giro horario, cero arriba,
referencia vertical en la tangente inferior y Norte sin declarar. En rev2 aparece la flecha
de Norte. El contraste de los rumbos escritos se hace en el marco de la lámina.

| Marca | Rev1, coincide con el oro | Rev2, lectura de la planta |
| --- | ---: | ---: |
| A1 | 0° | 90° |
| L2 | 270° | 45° |
| L5 | 135° | 225° |
| L6 | 0° | 225° |
| L7 | 90° | 315° |
| L8 | 90° | 315° |
| S1 | 90° | 45° |

Las citas están en la página 1 de cada revisión. Alejandro puede contrastar la asociación
de los globos con sus sectores antes de actualizar el oro. La prueba de regresión verifica que
una nube por sí sola no genera cambios y que la proyección D1 pasa de 610 a 410 mm por ID.

## Visión y OCR

En una pasada de lectura vectorial, la cobertura de las cotas seleccionadas fue 4/4 en cada GA
del vertical y 6/8 en cada GA del horizontal. Quedaron pendientes la profundidad de fondo como
medida directa y el ancho común de las silletas. Las lecturas tardaron de 1,81 a 4,02 s por
lámina, con cero llamadas externas.

**Visión en los huecos (J4, 26/11).** `lectura/vision_llm.py` se activa con
`trazia lote … --proveedor azure-openai` (despliegue `gpt-6.1-sol`). Solo pide por mosaicos los
campos que la familia necesita y la lectura por reglas no dio, y las posiciones de boquilla que
faltan. Cada valor trae su texto y su caja, y entra solo si el texto vectorial del PDF en esa
caja lo respalda (`is_grounded`); queda con canal `vision`, regla `vision.hueco` y confianza 0,6.
El validador contrasta los campos con confianza menor de 0,7 y solo sube o baja la confianza.

Lote de las 20 revisiones, medido con `bench.oro` frente al mismo lote sin visión:

| Medida | Sin visión | Con visión |
| --- | ---: | ---: |
| Revisiones con modelo e IFC válido | 2/20 | 4/20 |
| Revisiones con diámetro y longitud evaluables | 6 | 12 (error mediano 0,0 %) |
| Cambios rev1 → rev2 acertados | 40/97 | 42/97 |
| Falsos cambios | 11 | 12 |

- Huecos rellenados con cita: 101 de 273. Se descartaron 61 lecturas cuyo texto no estaba en
  su caja.
- Coste: 362 llamadas, 33 min de modelo y unos 14 min de reloj con 4 procesos. Cada envío queda
  en el registro de envíos.
- Aciertos nuevos: el cambio de elevación de V1 en BF-V-0016 (2879 → 2864) y la falda de
  BF-C-0008 (2450 → 4700).
- Falso nuevo: la altura de apoyo de BU-V-110 (2150 → 3000). Hay que revisarlo.
- 80V01 llega a modelo porque la visión aporta el ancho de silleta (254).
- La bajada de marcas, NPS y rating en la tabla global no viene de la lectura. Cuando una
  revisión llega a modelo, `bench.oro` cuenta solo las boquillas colocadas en el modelo.

RapidOCR produjo 510 y 571 líneas en rev1 y rev2 de BP-T-710, y 58 en el VESOR de 62T02. El
asociador explícito de la rama de Iria (`a1b4961`) dio cero pares marca–rumbo con esta
configuración. Con mosaicos a 240 DPI, el VESOR produjo 76 líneas y siguió con cero pares.
Las líneas incluyen ángulos y marcas separados. Queda revisar con Iria la
asociación por posición de los globos; el OCR no declara una orientación por proximidad sola.

La revisión de Iria añade sugerencias de parejas cuando el OCR divide el rótulo en dos cajas.
Exige que las cajas estén alineadas y que cada una tenga una sola pareja posible en la misma página.
El aviso conserva las dos cajas para cotejar la línea de llamada en el plano. En la comprobación
local se cotejó una sugerencia por revisión de BP-T-710. Estas sugerencias quedan en la revisión
humana. El VESOR de 62T02 conserva su lectura explícita bajo HOLD.

## Cambios rev1 → rev2 por ID

Ninguna revisión de TR llega todavía a modelo, así que `trazia lote` no escribía
`cambios_rev1_rev2.json` y `bench.oro` daba 0/97 cambios. Ahora, si alguna de las dos revisiones
no tiene modelo, el lote compara lo leído ruta a ruta (`lectura/cambios.py`, `nivel: candidatos`).
Solo hay cambio cuando las dos revisiones leen la ruta y el valor difiere. Una ruta leída en una
sola revisión no cuenta como alta ni como baja. Las altas y bajas de boquillas se exigen en la
tabla de las dos revisiones.

Dos casos van a `revisar` y no cuentan como cambio:

- el rumbo de la mayoría de las boquillas cambia a la vez, señal de que cambió el marco de la
  planta (en BF-V-0016 rev2 aparece el Norte);
- el espesor cambia de notación («160», «THK: 15.85», «I.D. ø50,8»).

Medida sobre `data/Dataset-tecnicasreunidas/vessels`, sin proveedores externos:

| Equipo | Cambios en el oro | Acertados por ID | Con el campo exacto | Predichos fuera del oro |
| --- | ---: | ---: | ---: | ---: |
| 80V01 | 4 | 1 | 1 | 0 |
| 81V01 | 16 | 8 | 8 | 0 |
| BF-C-0001 | 9 | 0 | 0 | 0 |
| BF-C-0003 | 23 | 21 | 10 | 0 |
| BF-C-0008 | 14 | 0 | 0 | 0 |
| BF-V-0016 | 15 | 5 | 1 | 1 |
| BP-T-710 | 10 | 5 | 4 | 5 |
| BU-V-110 | 3 | 0 | 0 | 5 |
| BW-C-0001 | 3 | 0 | 0 | 0 |
| **Total** | **97** | **40** | **24** | **11** |

Con el ensamblado de Miguel, BF-V-0016 llega a modelo con menos boquillas de las que se leen.
Desde entonces, el lote completa la comparación del modelo con lo leído en las rutas que el
modelo no tiene. Esos cambios llevan `nivel: candidatos`. Medido con `bench.oro` el 26/11
sobre `main`: 40/97 acertados y 13 falsos. Dos de esos falsos vienen de la comparación del
modelo: los pesos de BF-V-0016 que aparecen y desaparecen.

«Acertados por ID» es el criterio de `bench.oro`: cualquier cambio leído en la boquilla del oro.
«Con el campo exacto» exige además el campo equivalente (`standout_mm` ↔ `projection`,
`elevation_mm` ↔ `elevation`, etc.). 10 de los 11 de fuera del oro parecen cambios
reales con otra ruta o que el oro no recoge. Alejandro debería revisarlos:

- BU-V-110: los cinco pesos de la hoja 3 (vacío 91.000 → 89.800 kg, etc.).
- BP-T-710: el espesor de las virolas 6 a 9 (6 → 8 mm). El oro lo agrupa en
  `attributes.shell_courses_thickness`.
- BF-V-0016: `height` 1.925 → 1.940 mm. Es el `attributes.shell_height` del oro.

Lo que falta lo limita la lectura, no la comparación:

- las cotas de elevación de BF-C-0003 (12 cambios);
- las marcas de BF-C-0001, BF-C-0008 y BU-V-110, que hoy son 0;
- las estaciones K2, K3A–C y K4 de 81V01;
- las silletas y pernos de 81V01.

### Puerta 7.0 (26/11, tarde)

Lote de BF-V-0016 y 80V01 sin proveedores externos, medido con `bench.oro`:

| Equipo | Cambios acertados | Falsos | Boquillas colocadas rev1 / rev2 |
| --- | ---: | ---: | ---: |
| 80V01 | 1/4 | 0 | 5 / 5 |
| BF-V-0016 | 9/15 | 0 | 6 / 6 |

Cinco arreglos para llegar a 0 falsos y a 3 o más boquillas colocadas:

- **Altura.** `height` es la cota de la T.L. a la cara de la brida («2100»). El desarrollo de
  la chapa (1925 → 1940) va a `attributes.shell_height`, que es el campo del oro. Las
  costuras verticales salen de la chapa y de la faldilla recta.
- **Azimut sin Norte.** Si la planta no dibuja el Norte, el azimut se toma en la escala del
  plano (0° arriba, sentido horario) y queda como supuesto.
- **Emparejamiento por marca.** Si una marca existe en la otra revisión, nunca se empareja
  con otra marca por parecido. Antes L7 de rev1 se emparejaba con L4 de rev2. El cambio
  está en `families/change_detection.py` y `revisions.py`, que son de Miguel.
- **Marco de rumbos.** Si el marco de la planta cambia entre revisiones, los cambios de
  orientación del modelo van a `revisar` y no a `cambiados`. En BF-V-0016 rev2 aparece el
  Norte y casi todos los rumbos cambian. Algunos cambios parecen reales, pero el oro no los
  recoge. Alejandro debe decidir si los añade o si siguen en `revisar`.
- **Rótulo de una fila.** Un «EL.+ 1100» bajo una fila de globos contiguos da la cota a
  todas las boquillas de la fila: L3/L5/L7 y L4/L6/L8 en rev1, y L2/L4/L6/L8 en rev2. La
  asociación es `fila`, con confianza 0,60. S1 sigue sin colocar, porque su tamaño es
  «3 (HOLD)» y no da diámetro.

## Uniones soldadas (J6, primera pasada)

`lectura/soldaduras.py` deduce las uniones a partir de las piezas que ya tienen cita, en
`welds.<ID>.{kind, joins, elevation_mm}` (interfaz 1). El ID depende solo de lo que une, así que
se mantiene entre revisiones:

- `W:V01|V02`: virola–virola, consecutivas en la lista de materiales.
- `W:SHELL|HEAD_BOTTOM` y `HEAD_TOP`, o `BODY_FLANGE` si la tapa es embridada.
- `HEAD_LEFT` y `HEAD_RIGHT` en los horizontales.
- `W:C1|C2` y `W:C1|BOTTOM` en tanques.
- `W:N1|SHELL`: cada boquilla de la tabla.

Cada unión lleva la cita de la pieza que la justifica, una regla `soldadura.*` y una confianza
de 0,55 como máximo. La revisión debe tratarla como `assumed`. `elevation_mm` es la distancia
axial desde la T.L. de referencia. Solo se da cuando las cotas leídas la fijan.

| Equipo (rev1) | Uniones | Circunferenciales | Boquilla–cuerpo | Con cota |
| --- | ---: | ---: | ---: | ---: |
| 62T02 | 18 | 0 | 18 | 0 |
| 80V01 | 15 | 2 | 13 | 2 |
| 81V01 | 14 | 0 | 14 | 0 |
| BF-C-0003 | 39 | 15 | 24 | 1 |
| BF-V-0016 | 16 | 2 | 14 | 2 |
| BP-T-710 | 39 | 9 | 30 | 1 |
| BW-C-0001 | 31 | 0 | 31 | 0 |

BF-C-0001, BF-C-0008 y BU-V-110 no tienen uniones porque no se les lee ninguna pieza. El oro
aún no tiene `soldaduras` (interfaz 3), así que no hay medida de acierto. `assemble` ignora
estas rutas hasta que exista `Weld` en el modelo (M5).

**Comprobación en el plano (26/11).** Se cotejaron las cotas de las costuras con el alzado:

- **80V01:** la cadena de cotas bajo la planta da tres virolas (`1655 x 10 ⟨1.2⟩`,
  `1980 x 10 ⟨1.3⟩`, `1965 x 10 ⟨1.4⟩`) y 50 S.F. a cada lado, que suman 5700 T.L.–T.L. La
  primera pasada ponía los fondos en la T.L. (0 y 5700) y no tenía las dos costuras entre
  virolas. Ahora la envolvente emite `shell.courses.1-2`…`1-4` con `height`, `thickness` y
  `station` (regla `ga.tramos_virola`). Las costuras quedan en 50, 1705, 3685 y 5650.
- **BF-V-0016:** el alzado lateral acota 50 desde la T.L. hasta el arranque de la virola,
  1925 de virola y 2100 hasta la cara de la brida. La lista de materiales dice
  «H= 257 mm; h= 50mm» del fondo. La envolvente lee la faldilla `h` como
  `attributes.head_straight_flange` (regla `ga.fondo_faldilla_h`). Las costuras pasan de 0 y
  1925 a 50 (virola–fondo) y 1975 (virola–brida del cuerpo, 125 mm bajo la cara).

Las dos siguen siendo `assumed`: la cota fija el límite entre piezas, pero la línea de la
costura no se ha leído como trazo.

Pendiente:

- Confirmar cada costura con la línea continua del alzado y subir su confianza.
- Ordenar las virolas de la lista de materiales en verticales para dar su cota.
- Saber a qué pieza va cada boquilla (virola o fondo).
- Leer tamaño y notas («0.7t», «a = 0.7 x z», «ONE LONG. SEAM»).

## Cifra del par de la demo (26/11, madrugada)

Lote de `main` en `65b52f7` (incluye M3 de Miguel), medido con `bench.oro` de `47a250a`, que
marca «no comparable» cuando el oro y el modelo usan bases distintas. Sin proveedores externos.
Cada equipo se procesó por separado (ver nota de memoria abajo).

| Equipo | Rev | Modelo e IFC | Ø | L | Boquillas colocadas | Proyección (mediana) | Elevación (mediana) |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| 80V01 | rev1 | sí | 0,0 % | 0,0 % | 5 | 960 mm en 6; 7 no comparables | 1.920 mm |
| 80V01 | rev2 | sí | 0,0 % | 0,0 % | 5 | 960 mm en 6; 6 no comparables | 1.920 mm |
| BF-V-0016 | rev1 | sí | 0,0 % | no comparable | 0 | 0 mm en 13 | 0 mm |
| BF-V-0016 | rev2 | sí | 0,0 % | no comparable | 0 | 0 mm en 13 | 0 mm |

L de BF-V-0016 no es comparable: el oro mide «T.L. a cara de brida del cuerpo» y el modelo «tl-tl».

| Equipo | Cambios en el oro | Acertados por ID | Falsos |
| --- | ---: | ---: | ---: |
| 80V01 | 4 | 1 | 0 |
| BF-V-0016 | 15 | 9 | 21 |

Soldaduras del par: 65/75 encontradas y 0 falsas de 65. Son uniones deducidas de las piezas,
no de la línea del plano.

Con `d9d8816` (antes de M3), BF-V-0016 tenía 5 acertados, 1 falso y 3 boquillas colocadas en rev2.

Lo que queda abierto:

- **Falsos de BF-V-0016 (21).** Son `facing` (14) y `schedule` (9), por ejemplo
  `WNRF → R.F.` y `Sch.80 → 80`. rev1 toma el valor de la HDM y rev2 del GA. Es un desacuerdo
  entre documentos con distinta notación, no un cambio de revisión. Los cambios desde candidatos
  deberían comparar la misma fuente en las dos revisiones o normalizar la notación.
- **Boquillas de BF-V-0016 fuera del modelo.** La HDM dice «Dimension "L" is from the Vessel
  Centerline to Flange Face and from BTL for nozzles on dish end». Como la nota da dos orígenes,
  `projection_basis` queda sin resolver para las 14 boquillas. Haría falta eje para las de la
  virola y BTL para las del fondo.
- **80V01: proyección y elevación desviadas en 960 y 1.920 mm.** Era el banco, no el modelo
  (`fb9e3c0`, parte horizontal de I-06). No reconocía la regla `horizontal.proyeccion_desde_eje`,
  y comparaba `station_mm` con la altura de la boquilla en vez de con `position.x`. Con el
  arreglo, 80V01 da 0 mm de proyección en 6 boquillas y 0 mm de estación en 10. La parte
  vertical de I-06 (EL.+ desde la tangente inferior) sigue abierta.
- **Memoria en el lote.** Con 2 procesos el lote se cae (`OpenBLAS`, `BrokenProcessPool`). Con
  1 proceso, la HDM de BF-V-0016 da `MemoryError` si se lee después de 80V01, y se lee bien si va
  sola.

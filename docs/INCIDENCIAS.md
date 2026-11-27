# Incidencias abiertas

Problemas que bloquean una tarea y necesitan a otra persona. Cada una dice quién la abre, a quién
se asigna y qué se ha hecho mientras tanto.

El encargo para Javier con las que le tocan está en
[encargos/JAVIER_25NOV.md](encargos/JAVIER_25NOV.md).

## I-01 · `trazia lote` agota la memoria con los mecánicos · cerrada

- **Cerrada:** `44f684e`. La ingesta comprueba hasta 16 MiB de contenido vectorial
  descomprimido por página antes de construir el layout. Si una página supera el presupuesto,
  el lote omite el PDF con un aviso y sigue con los documentos restantes. El widget `excluir`
  vuelve a empezar vacío.
- **Verificación:** la prueba sintética reproduce el caso con un PDF comprimido. De 38 PDF
  del dataset, la comprobación de tamaño solo rechaza las páginas 1, 2 y 5 de GA2 rev0 del
  compresor. El lote real del compresor termina sus dos revisiones como `faltan_datos`.
- **Medición previa al límite:** extracción de palabras con pdfplumber, una página por
  proceso en Windows. El pico es memoria residente observada. Un corte a los 45 s indica
  que el proceso seguía activo y que el valor observado es un mínimo.

  | Página | Contenido vectorial descomprimido (MiB) | Pico residente (MiB) | Tiempo del proceso |
  | ---: | ---: | ---: | ---: |
  | 1 | 22,47 | 1.407 | corte a 45 s |
  | 2 | 45,74 | 774 | corte a 45 s |
  | 3 | 5,56 | 361 | 8,33 s |
  | 4 | 4,54 | 305 | 6,64 s |
  | 5 | 27,88 | 1.579 | corte a 45 s |

- **Abre:** Alejandro, 25/11. **Asignada a:** Javier (`ingest.py`, `page_cache.py`).
- **Qué pasa:** `uv run trazia lote data/Dataset-tecnicasreunidas -o generated/lote --dataset real`
  procesa los diez recipientes de `vessels/` y `BOMBA`, y se queda en `COMPRESOR` rev0. El proceso
  de Python pasó de 5 GB y el portátil dejó de responder. Ha ocurrido dos veces.
- **Sospechoso:** `mechanical/COMPRESOR-GA2-Rev0.pdf`, de 19,5 MB. El resto de PDF del dataset
  pesa menos de 2,2 MB. No se ha vuelto a abrir para no repetir el cuelgue.
- **Mientras tanto:** el lote se lanza por equipo de `vessels/` con `--tag`, por ejemplo
  `--tag BF-V-0016 --tag 80V01`. Los candidatos de los diez recipientes del 25/11 están en
  `generated/lote` y sirven para medir.
- **Para cerrarla:** un límite de memoria o de tamaño por página en la ingesta, con aviso y salida
  ordenada, y una prueba sintética con una página vectorial muy pesada.

## I-02 · Marcos de la vía 2 · verificación parcial

- **Abre:** Alejandro, 25/11. **Asignada a:** Javier, o quien tenga una máquina con memoria de sobra.
- **Qué falta:** el eje en planta (`eje_xy_mm`) y la cota de la T.L. inferior en las IFC de TR
  de BF-C-0003 (56 MB), BF-C-0001 (12 MB), BW-C-0001 (6 MB) y BF-C-0008 (3 MB), además de qué
  eje de la IFC corresponde al 0° de cada plano. Es la interfaz 5 (`eval/marcos/<TAG>.json`).
- **Verificación del 25/11 (`27af03b`):** se abrieron las cuatro IFC en un equipo con 64 GB de RAM. En
  BF-C-0003, las virolas dan el eje XY = (0, 0) mm a precisión milimétrica y los contactos con
  los fondos confirman las tangentes. Las juntas del fondo superior e inferior en la vista
  de planta permiten asociar el 0° de la lámina con +Y del IFC. El Norte sigue sin indicarse.
- **Pendiente:** las otras tres IFC contienen estructura auxiliar. Se dejó un marco para cada
  una con las cotas y el eje en `null`. Para medirlos hace falta el IFC del recipiente o una
  correspondencia documentada entre el GA y la geometría de estructura.

## I-03 · Prueba de arranque en rojo y extra `api` sin documentar · cerrada

- **Cerrada:** Iria, `c85a90d` («Aísla la prueba de arranque e incluye el extra API en la
  instalación»). Comprobado el 25/11: `tests/test_automatizacion.py` pasa entero.

- **Abre:** Alejandro, 25/11. **Asignada a:** Javier (commit `329b5e7`, «Trae a hack-tc02 el estado
  completo de trazia-3d»).
- **Qué pasa:** `tests/test_automatizacion.py::test_arranque_cierra_el_registro_y_etiqueta_la_base`
  falla en `origin/main` (`aae468d`) sin otros cambios. `scripts/arranque_evento.py` sale con
  `SystemExit` en `registro_cerrado`, y una de sus expresiones lleva `\.` en lugar de `\.`.
- **Además:** 24 archivos de pruebas necesitan `fastapi`, `httpx` y `sqlmodel`, que están en el extra
  `api`. `AGENTS.md` y `README.md` siguen indicando
  `uv sync --frozen --extra dev --extra ocr --extra geo`, sin `--extra api`.
- **Medido:** con `--extra api`, 478 pasan, 1 falla (esta), 70 xfail y 97 xpass.

## I-04 · Los ejemplos sintéticos ya no llegan a modelo · cerrada

- **Cerrada:** `9c65a3b`. El lector compartido recupera las cotas etiquetadas y la HDM de los
  ejemplos sintéticos. El notebook 00 exige los dos modelos y una comparación con cambios.
- **Verificación local:** V-101 A y B en `ok`, con 3 y 4 boquillas y 8 cambios. La prueba
  de la CLI ejecuta ahora el lector real.
- **Además (Miguel):** `procesar_carpeta` rechaza un `dataset` distinto de `real` o `synthetic`.
  Con `sintetico`, los ejemplos se leían como planos reales y acababan en `faltan_datos` sin aviso.

- **Abre:** Alejandro, 25/11. **Asignada a:** Javier y Miguel (lectura y ensamblado).
- **Qué pasa:** `trazia.lote.procesar_carpeta` sobre `examples/documents` (V-101, revA y revB)
  termina en `faltan_datos` con «Faltan datos explícitos: diameter, height, head_depth,
  skirt_height». Por eso no se escriben `revision.json`, `modelo.ifc` ni `cambios_revA_revB.json`.
  La lectura de hack-tc02 no saca esas dimensiones del GA sintético ni de su HDM en `.xlsx`.
- **Efecto:** `databricks/00_comprobar_entorno` exigía dos revisiones `ok`. Ahora solo exige que el
  lote termine ordenado y deje candidatos, y avisa si no hay modelo. La puerta del backend (7.0,
  punto 4) pide una prueba de extremo a extremo con un equipo sintético.
- **Para cerrarla:** que V-101 vuelva a dar dos revisiones `ok` y su comparación, y restaurar la
  comprobación estricta del notebook 00.

## I-05 · `pytest -q` completo tumba el proceso en un portátil · cerrada

- **Cerrada para la ejecución habitual:** `4820dae`. La geometría nativa se libera entre
  elementos. El estudio geométrico largo se ejecuta aparte para aislar eventuales fallos
  nativos de IfcOpenShell. En PowerShell, con memoria suficiente:

  ```powershell
  $env:TRAZIA_TEST_ESTUDIO_COMPLETO = '1'
  uv run pytest -q tests/test_lectura_estudio.py::test_study_writes_interface_3
  Remove-Item Env:TRAZIA_TEST_ESTUDIO_COMPLETO
  ```

- **Verificación del 25/11:** 501 pruebas aprobadas en la batería principal, un único
  `skip` para el estudio largo y cero fallos. El estudio también pasó solo en 19,51 s.

- **Abre:** Alejandro, 25/11. **Asignada a:** Javier (`bench/estudio.py`, `bench/ifc_geometry.py`).
- **Qué pasa:** al 44 % de `uv run pytest -q`, `tests/test_lectura_estudio.py::test_study_writes_interface_3`
  termina con «Windows fatal exception: access violation» dentro de
  `ifcopenshell.geom.create_shape` (`bench/ifc_geometry.py`, `element_boxes`). Se pierde el resto
  de la batería y el portátil se queda sin memoria. En una ejecución anterior la misma batería
  terminó (478 pasan, 1 falla por I-03), así que el fallo no es determinista.
- **Mientras tanto:** en este portátil se ejecutan solo las pruebas afectadas por cada cambio.
  La batería completa, en una máquina con más memoria.
- **Para cerrarla:** liberar la geometría entre elementos o limitar los hilos de
  `create_shape` en `element_boxes`. Otra opción es marcar la prueba como lenta y sacarla de la
  ejecución por defecto.

## I-06 · `bench.oro` mide los modelos en otro marco que el contrato · cerrada

- **Cerrada (Alejandro, 26/11):**
  - horizontales: `station_mm` se compara con `position.x` del modelo (`fb9e3c0`);
  - verticales: a la `elevation` de las boquillas colocadas se le resta la T.L. inferior del
    modelo (`legs.height` o `skirt_height`); las no colocadas salen de los candidatos y ya miden
    desde la T.L.;
  - rutas de cambios: `attributes.shell_height` → `height` y
    `attributes.shell_courses_thickness` → `tank.courses.*.thickness`;
  - oro de BU-V-110: faltaban los cinco cambios de peso de rev2 (transporte, izado, vacío,
    operación y prueba), que ya están con su cita.
- **Verificación:** lote local de BF-V-0016, 80V01 y BU-V-110. Error de cota con mediana de
  0 mm en 4 revisiones; cambios: 11 de 34 acertados y 1 falso.

- **Abre:** Miguel, 26/11. **Asignada a:** Alejandro (`bench/oro.py`).
- **Ya resuelto en `8d25689`:** las boquillas sin colocar cuentan como marcas, con sus
  atributos de `candidatos.json`. Con el lote de M3, la proyección y el NPS de los modelos se miden
  bien y el recall de marcas es 286/430.
- **Qué queda:** la cota de los modelos se compara en otro marco. La geometría es correcta: en
  80V01, la x de las boquillas coincide con `station_mm` del oro (1150, 5100, 5400, 4500 y
  2400 mm).
  - **Horizontales:** se compara la `elevation` del modelo con `station_mm`. En 80V01 sale un
    error de 1920 mm.
  - **Verticales:** el modelo guarda la elevación desde el suelo, y el oro da «EL.+» desde la
    tangente inferior. En BF-V-0016 rev2 la diferencia es la altura de las patas: A1, L4 y U1 dan
    2200, 1300 y 1500 frente a 1200, 300 y 500.
  - **Rutas de cambios:** el oro usa `attributes.shell_height` y
    `attributes.shell_courses_thickness`, y el contrato `height` y `tank.courses.<n>.thickness`.
    Esto explica 6 de los 12 falsos cambios del lote. Otros 5 son los pesos de BU-V-110, que
    cambian entre rev1 y rev2 (91000 → 89800 kg en vacío, por ejemplo) pero no aparecen en
    `cambios_rev1_rev2` del oro. Conviene comprobar si faltan en el oro.
- **Para cerrarla:**
  - en horizontales, comparar `station` con `station_mm`;
  - en verticales, restar la cota de la tangente inferior del modelo antes de comparar;
  - mapear esas rutas del oro a las del contrato.

## I-07 · Windows bloquea el `.venv` del clon de la D5 · resuelta con un rodeo

- **Qué pasa:** en el portátil de Javier, `scripts/entrega.py --clon` hace `uv sync` sin
  problema. Después, Smart App Control bloquea `.venv\Scripts\python.exe` del clon nuevo con el
  mensaje «Una directiva de Control de aplicaciones bloqueó este archivo» (WinError 4551). uv
  crea un lanzador propio sin firmar, y Windows lo juzga por reputación. Así fallan el pytest,
  el lote y la API del clon, aunque el repositorio esté bien.
- **Rodeo (26/11), sin tocar directivas:** en el clon, renombrar `python.exe` y `pythonw.exe`
  de `.venv\Scripts` y copiar en su lugar los de
  `%APPDATA%\uv\python\cpython-3.11-windows-x86_64-none\Lib\venv\scripts\nt\`. Después se
  repiten los pasos del clon con `.venv\Scripts\python.exe -m ...`: `pytest -q`,
  `-m trazia lote` y `-m trazia.api`. Resultado en
  `docs/evidencias/cierre-mvp/REGISTRO.md`, sección 7.
- **En otra máquina sin Smart App Control** no hace falta: basta con `entrega.py --clon`.

## I-08 · Los mecánicos no llegan a IFC · abierta

- **Encargo (26/11):** toberas exteriores y componentes exteriores en cualquier GA mecánico, por
  fases y con puerta de no regresión, en [encargos/MECANICOS_EXTERIORES.md](encargos/MECANICOS_EXTERIORES.md).
- **Avance del 26/11:** el lote con el dataset completo produjo 26 de 26 IFC, seis de
  ellos de bombas y compresores. La API procesó esos seis originales y sirvió el PDF y el
  IFC4 DRAFT de cada revisión. Se separan los GA1 y GA2 y se conserva un GUID por máquina.
  Documentos indica «Envolvente LOD 1». Las conexiones de proceso, los subconjuntos y la
  comparación más allá de la envolvente siguen pendientes.
- La lectura de los GA mecánicos usa PDFium con presupuesto de 64 MiB por página y 128 MiB
  por documento. El presupuesto de PDFMiner queda en 16 MiB por página. Las dos revisiones
  de la primera bomba usan OCR local para sus cotas dibujadas.

- **Abre:** Alejandro, 26/11. **Propuesta de reparto:** Javier (ingesta, tipología, lectura y
  tablas) y Miguel (ensamblado, ID e IFC). Iria muestra «no comparable» en la API y Alejandro en
  el banco.
- **Criterio:** [PLAN.md](PLAN.md), sección 4: en `mechanical/`, IFC válido con la envolvente, las
  dimensiones principales y los componentes exteriores que tengan evidencia.
  [DATA_CONTRACT.md](DATA_CONTRACT.md): envolvente LOD 1 con el origen supuesto y declarado.
  [AGENTS.md](../AGENTS.md): valor, unidad, fuente y confianza por campo, y GUID estable por ID.
  [PLAN_DATOS_REALES_TR.md](agentes/PLAN_DATOS_REALES_TR.md), P4: cada GA<n> es un equipo distinto.
- **Medido en `d5f3d58`:** el lote de `mechanical/` deja 0 de 4 revisiones con modelo y 0
  candidatos en los 6 PDF (solo el tag, sacado del nombre del archivo). Las cuatro terminan en
  `faltan_datos` y piden campos de recipiente. Entre Rev0 y Rev1 del GA1 del compresor, el texto
  cambia en 6 pesos, unas 10 cotas y unas 20 cotas que pasan a ser de otro alcance. Además, los
  tags de los componentes aparecen en Rev1. Aun así, el lote da «0 cambios». Detalle, pruebas y
  tiempos en [INFORME_MECANICOS_26NOV.md](agentes/INFORME_MECANICOS_26NOV.md).
- **La vía ya existe:** con `equipment_type` `pump` o `compressor`, el ensamblado solo pide
  `envelope.origin/size` y produce un IFC LOD 1 (`extraction.py`, rama `envelope`). Con candidatos
  correctos a mano sale un `IfcCompressor` válido. La lectura de `main` no llega a esa vía.

### Orden de trabajo

**P0. Sin esto no sale ningún IFC:**

1. **Tipología.** Las reglas de `lectura/tipologia.py` exigen «CENTRIFUGAL PUMP» o «COMPRESOR
   CENTRIFUGO» al principio de la línea. Los planos reales dicen «COMPRESSOR <modelo>»,
   «PUMP TYPE…», «API 610/617», «ELECTRIC MOTOR», «GEARBOX» o «BASEPLATE». El nombre
   `<TIPO>-GA<n>-Rev<r>` ya lo reconoce `ingest.dataset_filename`, pero no pasa el tipo. Sin tipo,
   el equipo cae en recipiente vertical con faldón y pide diámetro, altura, fondo y faldón.
2. **Ingesta por página.** `ingest.py` comprueba todas las páginas con `check_page_content` antes de
   leer ninguna. Si una sola página supera el límite de I-01, se descarta el PDF entero, y con él
   el GA2 del compresor: la bancada, los niveles absolutos y la tabla de puntos de conexión con
   X/Y/Z. El límite se mantiene. Una página por encima se lee con `pypdfium2` (ya en el lock), que
   da el texto con cajas en milisegundos y se marca «lectura ligera». Las demás siguen con
   pdfplumber.
3. **Un equipo por GA<n>.** `lote.Documento` toma como tag el prefijo y junta GA1 y GA2 en la misma
   revisión. Son máquinas de fabricante y modelo distintos. El ID (y con él el GUID) debe ser
   `<TIPO>-GA<n>`. Así una envolvente no mezcla cotas de dos máquinas, y una hoja sin Rev1 no
   aparece como baja en la comparación.
   **Hecho en `ed9f1dd`** (`catalogue_tag`). Desde `84f4eab`, una hoja que solo nombra el prefijo
   (`HDM_BOMBA`) acompaña a cada GA<n>.
4. **Envolvente desde cotas rotuladas.** `extractors/mechanical.py` solo lo usa el camino de
   estrategias y espera la lámina sintética. En los 6 PDF devuelve `None`. Los planos reales traen
   la envolvente como texto rotulado: bancada (BASEPLATE, BASE FRAME), DATUM y niveles
   (T.O.B., T.O.C.). Se lee solo lo rotulado. El origen va `assumed` con su regla, como dice el
   contrato.
5. **Cotas dibujadas como trazos.** El GA1 de la bomba tiene unos 8.000 trazos y unos 50 textos:
   sus cotas no son texto, y el aviso de OCR no salta porque se calcula por número de caracteres.
   Debe saltar cuando no hay cotas numéricas. Al revés, en láminas A0 con poco texto salta sin
   hacer falta. Solo bloquea el GA1 de la bomba; el GA2 sí trae texto.
   **Hecho en `84f4eab`, solo la mitad A0:** en la vía de pdfplumber, el umbral deja de crecer por
   encima de A1. Sigue pendiente que salte cuando no hay cotas numéricas.

**P1. El IFC saldría, pero incumpliendo los criterios:**

6. **Boquillas en LOD 1.** La rama `envelope` de `assemble` descarta todas las `nozzles.*`. Una
   conexión con posición X/Y/Z en tabla es un componente exterior con evidencia y debe entrar con
   su cita. La dirección se lee de la vista o se supone, con `state: assumed`. Hace falta que
   `lectura/tablas.py` reconozca `TP` y `Pos.` como marca, `DN` como tamaño, `PN` como rating y
   `LOCATIONS X/Y/Z` como posición, con cada fila anclada a su marca.
7. **ID estable aunque el tag aparezca tarde.** El tag de la máquina y de sus componentes solo
   aparece en Rev1 del GA1 del compresor. Si el ID se toma del plano, la misma máquina cambia de ID
   y de GUID entre revisiones. El ID sale del archivo (punto 3). El tag del plano se guarda como
   atributo citado, con aviso si cambia. El GA2 de la bomba cubre dos bombas (A y B): un solo
   IFC necesita revisión humana.
8. **Unidades.** Las cotas duales mm y pies-pulgadas con fracciones apiladas dejan números sueltos
   en líneas aparte. Las cotas en pulgadas llevan los mm entre corchetes. El GA2 de la bomba
   declara a la vez pulgadas y mm en dos notas. Se leen los mm y la conversión imperial sirve de
   comprobación. Una declaración contradictoria es un conflicto, no una elección.
9. **Valores que no son definitivos.** `*` (preliminar), `**` (dato del cliente), `HOLD`,
   `BY CLIENT`, `BY CONTRACTOR` y `TBC` solo se tratan en la HDM y en las tablas (`HOLD`). En las
   cotas del GA, un valor preliminar entraría con confianza plena. Deben llevar estado y no
   aprobarse solos. Si un número pasa a «BY CONTRACTOR», cambia el alcance: no es una cota
   borrada.
10. **Mensajes y comparación.** Si una de las dos revisiones no tiene lectura, el resultado es «no
    comparable» con su motivo, no «0 cambios». El error de un mecánico no nombra campos de
    recipiente. Si `assemble` falla con otra excepción, se muestra esa causa y no solo «tipología
    no soportada».
    **Hecho en `84f4eab`:** los tres puntos, con pruebas en `test_lote.py` y
    `test_document_metadata.py`.

**No impiden el IFC:** la tabla de pesos por componente con el total del skid (`masas_ga` solo
conoce vacío, operación y prueba), las notas renumeradas entre revisiones y el falso aviso de OCR
en isométricas.

- **Para cerrarla:** el compresor y la bomba dan, en Rev0 y Rev1, un IFC LOD 1 válido con la
  envolvente citada, el origen supuesto declarado y las conexiones de proceso de su tabla. El ID es
  el mismo en las dos revisiones. Ninguna cota preliminar entra como firme. La comparación da sus
  cambios contra una verdad mínima del GA1 del compresor escrita a mano desde el plano, o
  «no comparable».

## I-09 · BW-C-0001 cambia de familia entre revisiones · abierta

- **Abre:** Alejandro, 26/11. **Propuesta:** Miguel (ensamblado).
- **Qué pasa:** en el lote `lote_a3_b2b1441`, BW-C-0001 sale `vertical_vessel` en rev1 y `column`
  en rev2. Las piezas del IFC y sus GUID no se corresponden entre revisiones, y la comparación
  enfrenta dos familias.
- **Para cerrarla:** la familia se fija por equipo con la evidencia de las dos revisiones. Si no
  coinciden, va a revisión como conflicto, no como cambio.

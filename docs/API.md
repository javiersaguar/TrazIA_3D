# API local de TrazIA-3D

## Arranque

```bash
uv sync --extra dev --extra api
uv run --extra api python -m trazia.api
```

Escucha en `127.0.0.1:8000`. Documentación interactiva: `/docs`; contrato: `/openapi.json`.
La primera ejecución aplica la migración Alembic 0001 y carga las revisiones sintéticas A/B.
Los reinicios conservan los cambios humanos: el seed no sobrescribe revisiones existentes.
`TRAZIA_DATA` cambia la carpeta de datos; `TRAZIA_DATABASE_URL` permite Postgres.
Las credenciales se configuran por entorno y no se guardan en Git.

## Endpoints de la base

| Método y ruta | Resultado |
| --- | --- |
| GET /health | Estado de API y versión del contrato |
| POST /documents | Multipart file + document_id, revision, kind y equipment_tag opcionales; registro y SHA-256 |
| GET /documents | Documentos registrados con `uploaded`, `cited_by` (revisiones que citan su SHA-256) y `active_jobs` |
| DELETE /documents/{id} | Borra un documento; requiere Idempotency-Key. 409 si una revisión guardada cita su SHA-256 o lo usa un trabajo en cola o en curso. El original solo sale del almacén si nada más comparte su SHA-256 |
| GET /equipment | Equipos con revisiones persistidas; sin equipos de relleno |
| GET /equipment/match?tag= | Fichas con ese código (sin mayúsculas ni espacios) y la huella de sus originales; la web añade ahí la subida como versión nueva |
| DELETE /equipment/{project_id}/{equipment_id} | Solo administradores. Borra todas las revisiones de la ficha; 409 sin borrar nada si alguna está aprobada, en un trabajo activo o enlazada por un cambio de diseño |
| POST /equipment/retire | Solo administradores. Retira una ficha del catálogo y conserva su historial. Lo borrado o retirado no vuelve con la siembra al reiniciar; una lectura nueva del equipo lo recupera |
| GET /equipment/{tag}/revisions/{rev} | Contrato 0.3 y ETag; query project_id |
| GET /revisions/{id} | Revisión completa y ETag por ID estable, incluidos resultados del pipeline |
| DELETE /revisions/{id} | Borra un borrador; requiere If-Match e Idempotency-Key. 409 si está aprobada, la usa un trabajo activo o la enlaza un cambio de diseño aplicado. Elimina su auditoría, sesiones, propuestas sin aplicar y artefactos; conserva los originales. No vuelve con la siembra al reiniciar |
| GET /revisions/{id}/fields | Campos trazables por ruta y ETag |
| PATCH /revisions/{id}/fields/{path} | Estado/corrección, nueva versión y auditoría |
| POST /revisions/{id}/approve | Aprobación si todos los campos están aceptados/corregidos y los originales coinciden |
| GET /revisions/{id}/audit | Antes/después, actor, fecha y tiempo declarado por acción |
| GET /revisions/{id}/documents/{document_id} | Original comprobado por SHA-256 |
| GET /revisions/{id}/ifc?draft=true | IFC4 DRAFT; sin draft requiere aprobación |
| POST /equipment/{tag}/jobs | Procesamiento asíncrono; 202 y job_id |
| POST /jobs | Procesamiento de cualquier equipo. Mismo contrato con `tag` en el cuerpo |
| GET /jobs/{id} | Estado, intentos, error y RunInfo |
| GET /jobs/{id}/events | SSE persistente; eventos stage y complete; admite Last-Event-ID |
| POST /jobs/{id}/cancel | Cancelación; no se publica un resultado después de cancelar |
| GET /diff?from=A&to=B | Diferencias actuales de campos/evidencia/documentos |
| GET /bench?extractor=etiquetas | Informe sintético existente, sin inventar mediciones |
| GET /plant | Equipos; layout=null hasta disponer de posición real |
| GET /estudio | Último trabajo terminado, informe de Lectura o estado vacío explícito |
| POST /estudio | StudyInput, Idempotency-Key, trabajo asíncrono 202 |
| GET /learning/corrections | Correcciones sintéticas vigentes y aprobadas, con cursor |

El id completo de revisión es `proyecto:equipo:revisión`; A/B son alias de la demo V-101.
BCF y exportación multiesquema están implementados (ver secciones posteriores).
POST /copiloto selecciona fuentes con Groq para sintéticos o usa evidencia indexada.
POST /estudio ejecuta el arnés mediante la cola común y publica el resultado por trabajo.

## Concurrencia e idempotencia

Todos los POST con efecto y PATCH requieren `Idempotency-Key` (1–128 caracteres). Se conserva
24 horas, con hash del cuerpo y la respuesta en la misma transacción que el efecto.
Repetir clave/cuerpo devuelve la respuesta original. Reutilizarla con otro cuerpo devuelve 409.
Una clave se limita a su operación y recurso.

PATCH y aprobación requieren `If-Match` con el ETag devuelto al leer la revisión. Si falta: 428;
si ya cambió: 412. El update compara la versión también en SQL. La idempotencia se comprueba
antes del ETag: un reintento de una operación ya confirmada puede usar el ETag anterior.
Una edición retira la aprobación. Ni los trabajos ni el seed sobrescriben una revisión existente.

```bash
curl -i http://127.0.0.1:8000/equipment/V-101/revisions/A
curl -X PATCH http://127.0.0.1:8000/revisions/A/fields/diameter \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: ejemplo-aceptar-1' \
  -H 'If-Match: "1"' -d '{"state":"accepted","actor":"Javier Saguar Antona"}'
curl -N http://127.0.0.1:8000/jobs/JOB_ID/events
```

En PowerShell, usar `curl.exe` para evitar el alias de Invoke-WebRequest.

## Archivos, trabajos y límites actuales

- Archivos inmutables por SHA-256 en `data/store/`, fuera de Git. Lectura verifica el hash.
- Límite de archivo: 25 MiB; multipart completo: 26 MiB, incluso con transferencia por fragmentos.
- CORS solo para localhost y 127.0.0.1, puertos 3000/3100/3200; ETag expuesto al cliente.
- El actor de revisión se registra, pero no se autentica: esta base se sirve en local.
- La cola local limita a dos trabajos simultáneos. Se recuperan trabajos interrumpidos al arrancar.
- Cancelación cooperativa entre etapas: un parseo nativo ya iniciado puede terminar en su hilo;
  el estado persistido impide que publique el resultado tras cancelar o agotar el tiempo.
- El adaptador temporal mantiene la firma de process y solo ejecuta b_reglas sin proveedores.
  Cuando exista trazia.pipeline, se usa automáticamente su process sin modificar sus archivos.
- RunInfo mide segundos con reloj monotónico. En el baseline no hay tokens, llamadas externas ni
  coste de proveedor; GPU permanece null. No se calcula un coste energético sin medirlo.
- El tiempo de revisión suma únicamente acciones que aportan seconds. No se atribuye tiempo cero
  a las acciones sin cronometraje ni se presenta ese registro como atención activa demostrada.

## Fuentes de implementación

[Sesiones SQLModel](https://sqlmodel.tiangolo.com/tutorial/fastapi/session-with-dependency/),
[Alembic programático](https://alembic.sqlalchemy.org/en/latest/api/config.html),
[cola arq](https://arq-docs.helpmanual.io/).


## Cola local y Redis

`TRAZIA_QUEUE=process` es el valor por defecto. Con `TRAZIA_QUEUE=redis`, configurar
`TRAZIA_REDIS_URL` y arrancar uno o más workers:

```bash
uv run --extra api arq trazia.queue.worker.WorkerSettings
```

Los workers comparten la base de datos y data/store con la API. La migración 0002 incorpora
leases: solo un ejecutor reclama un trabajo, incluso ante una entrega repetida de Redis.
Un trabajo interrumpido se puede recuperar al caducar su lease. Un cierre limpio deja la tarea
pendiente; el reinicio conserva sus intentos anteriores y no duplica la revisión.

JobInput admite timeout_seconds (plazo total, máximo 3.600), max_attempts (1–5) y
retry_backoff_seconds (0–30). Se reintentan errores de transporte y fallos que Lectura marque
opcionalmente retryable=true; los datos inválidos no se reintentan. El backoff es exponencial,
limitado a 30 segundos y contenido en el plazo total.

RunInfo suma consumo de los intentos que lo devuelven. El campo opcional accounting_complete=false
avisa si algún intento no devolvió contabilidad; en ese caso tokens/coste/GPU son null y
external_calls representa solo las llamadas contabilizadas, no un total garantizado.
El RunInfo de la revisión conserva la ejecución de Lectura; el del trabajo mide también la
orquestación y los reintentos. Así no se cambia la huella del IFC ya producido al cerrar el trabajo.


## Docker Compose

Usar un perfil cada vez (local/gpu/escala comparten el puerto de API):

```bash
docker compose --profile local up --build
docker compose --profile gpu up --build
docker compose --profile gpu exec ollama ollama pull qwen3-vl:4b-instruct
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile escala up --build
# Aumentar workers; todos comparten Postgres y el almacén de contenido:
docker compose --profile escala up --scale worker=4
```

Local: web 3000 y API 8000. Escala: web 3200 y API 8000, Redis y Postgres internos.
GPU: Ollama con reserva de GPU NVIDIA; descargar el modelo en su volumen antes de usarlo.
La configuración de escala añade dos workers por defecto en docker-compose.prod.yml.
Los puertos publicados se limitan a 127.0.0.1. Las credenciales de la base de datos son de demo local.
API y web se ejecutan como usuarios sin privilegios. Los contextos de build excluyen .env,
datos privados, cachés y dependencias del host mediante archivos Dockerfile.*.dockerignore.

El cliente Next recibe NEXT_PUBLIC_API_URL al compilar la imagen. Dejar el build arg vacío
produce la demo offline. Para el perfil local con Ollama en el host, usar
TRAZIA_OLLAMA_URL=http://host.docker.internal:11434; GPU usa el servicio interno ollama.
Sin Docker, las variables de .env se pueden cargar con `uv run --env-file .env --extra api ...`.

**Validación 27/10/2026:** imágenes Linux construidas y perfiles local, escala y GPU
arrancados en Docker 29.6.2 / Compose 5.3.1 dentro de Ubuntu/WSL. API, trabajo B, SSE, IFC,
idempotencia, HTTP de Next y persistencia tras reinicio pasan en los tres perfiles. Escala
usa Redis/arq/Postgres; NVIDIA visible desde el contenedor Ollama: RTX 5070 Laptop, 8151 MiB.
No se ha medido inferencia dentro del contenedor GPU ni un lote de 400 equipos.

Repetir después de construir las imágenes con
`uv run python scripts/check_compose.py --wsl Ubuntu --profiles local escala gpu` desde
PowerShell, o sin `--wsl Ubuntu` donde Docker esté en PATH. El chequeo crea y elimina solo su
proyecto temporal, sin publicar puertos. [Evidencias de Fase 1](FASE1.md).


## Web conectada y tipos

Sin `NEXT_PUBLIC_API_URL`, la web conserva la demo offline. Para conectar:

```powershell
# Terminal 1, raíz del repositorio
uv run --extra api python -m trazia.api
# Terminal 2, web/
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
corepack pnpm dev
```

El cliente no sustituye errores de API por datos simulados. Las ediciones envían ETag e
Idempotency-Key; se serializan por revisión y un conflicto 412 actualiza la consulta.
En **Documentos → Procesar planos con la API**, selecciona los originales de un equipo
y una revisión. Puedes cargar hasta 30 archivos PDF, XLSX, PNG o JPEG de hasta 25 MiB cada
uno. El formulario propone tag y revisión para nombres como `GAD_D-100_rev1.pdf` y
`HDM_D-100_rev1.xlsx`. Comprueba ambos antes de procesar. Si el tag contiene espacios
o barras, indica un ID estable de equipo para reutilizarlo en las siguientes revisiones.

La web registra los originales en `POST /documents` y envía sus IDs a `POST /jobs`.
En trabajos con estrategia `lectura`, los archivos con nombres libres se clasifican
por su contenido. El evento SSE `classify` incluye la señal y página cuando procede.
Para corregir la clasificación, añade los campos opcionales `kind` (`GA`, `HDM`,
`VESOR` o `ESTRUCTURA`) y `equipment_tag` (por ejemplo, `V-207`) al multipart
de `POST /documents`. Se guardan con ese documento y tienen prioridad sobre la
inferencia. Si se indica el tag, usa también ese valor en el trabajo y conserva un
`equipment_id` estable para las siguientes revisiones.

La revisión se guarda por proyecto, ID estable de equipo y revisión, con origen y
evidencia por campo. El enlace `/pipeline?trabajo=<id>` recupera el historial SSE al
recargar. **Ver resultado IFC DRAFT** abre el modelo, los originales verificados y los
campos trazables. La pantalla de revisión interactiva A/B sigue dedicada a la demo.

Para probar con un equipo distinto de V-101, genera un conjunto desde la raíz:

```powershell
uv run --extra api python -m synthetic --casos 1 --estilos rotulado --salida generated/integracion-fixture
```

Selecciona el PDF y el XLSX de `rev1` en la misma carpeta del equipo. Usa el origen
**Sintéticos de prueba**. Para los originales del reto, ejecuta dentro del entorno
autorizado de Databricks. El formulario está pensado para una revisión por trabajo.
Para una carpeta con varios equipos y revisiones, usa `databricks/01_procesar_lote.py`
según [el flujo del evento](FLUJO_IA.md).

También puedes cargar la pareja PDF/XLSX de un equipo de los
[proyectos sintéticos de petróleo y gas](PROYECTOS_PROCESO.md).
El resultado contiene sus cotas de envolvente LOD 1 y las fuentes por campo.

`corepack pnpm gen:api` desde web/ exporta `create_app().openapi()` con uv y regenera
openapi.json y schema.ts con openapi-typescript, sin necesitar un servidor en ejecución.
`corepack pnpm gen:types` regenera el contrato de revisión desde su JSON Schema.
Para verificar ambos transportes, ejecutar los comandos web con la variable definida y
sin ella. Playwright arranca una API aislada y persistencia bajo generated/ para el modo
conectado; `PW_EXTERNAL_API=1` permite usar un servidor ya iniciado.


## IFC multiesquema y comparación geométrica

`GET /revisions/{id}/ifc?draft=true&schema=IFC4X3` admite IFC4 (por defecto), IFC4X3 e IFC2X3.
La ruta mantiene las comprobaciones de aprobación y originales del flujo de revisión.
Los trabajos validan contrato y reglas EXPRESS antes de publicar el IFC; un error no se
presenta como modelo válido. Esta validación verifica estructura IFC, no exactitud del plano.

```bash
uv run --extra api trazia export examples/vessel_rev_a.json --draft --schema IFC2X3 -o generated/rev_a_2x3.ifc
uv run --extra api trazia validate-ifc generated/rev_a_2x3.ifc
uv run --extra geo trazia compare-ifc generated/rev_a.ifc referencia.ifc --samples 1024 -o generated/geometry.json
```

La comparación empareja elementos por GlobalId y usa mallas trianguladas del IFC en metros.
Informa IoU de cajas, Chamfer simétrico no cuadrático y Hausdorff **muestreado**, con semilla
reproducible y distancias por vértice para un mapa de error. Se comparan muestras con
triángulos; el máximo observado no garantiza el máximo continuo de toda la superficie.
Un GUID sin pareja aparece añadido/eliminado, sin inventar una correspondencia.
Instalar `--extra geo` para estas métricas; Docker.api ya lo incluye.

Entidades IFC4/4X3: Tank/Pump/Compressor, componentes agregados y un DistributionPort por
boquilla en su extremo. IFC2X3 usa FlowStorageDevice/FlowMovingDevice/FlowSegment/FlowFitting
con tipos TankType/PumpType/CompressorType/PipeSegmentType/PipeFittingType: esas clases de
ocurrencia modernas no existen en 2X3. Conserva Names, GUID y geometría; los fondos usan BRep.

DocumentReference apunta a urn:sha256 del original; su asociación y TrazIA_Provenance
conservan hashes, fuentes y RunInfo. Los psets comunes añaden referencias y diámetro nominal.
IfcApproval solo se añade a una exportación aprobada, tras revisión humana; un DRAFT no crea
una aprobación automática. OwnerHistory identifica la aplicación local, sin autenticar personas.

Fuentes: [validación IfcOpenShell](https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html),
[proximidad trimesh](https://trimesh.org/trimesh.proximity.html) y
[metadatos de autor IFC](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/owner/settings/index.html).

Para referencias externas con GUID distintos pero nombres coincidentes y únicos, usar
`compare-ifc ... --match name`. Este modo se elige explícitamente y rechaza nombres
ambiguos; no empareja elementos por parecido visual sin una correspondencia comprobable.


## Cambios en tres capas y BCF 2.1

- GET /diff?from=A&to=B conserva la respuesta rápida de campos para la web.
- GET /diff?from=A&to=B&layers=true añade páginas alineadas con OpenCV ECC, geometría
  por GUID y comprobaciones cruzadas de regiones/campos y marcadores de revisión.
- GET /diff/visual?from=A&to=B&document_id=GA-V101&page=1 devuelve PNG con diferencias
  resaltadas; 409 si no se puede alinear, 422 si la página no existe.
- GET /diff/bcf?from=A&to=B descarga un topic por cambio de campo, selección IFC y cámara.

```bash
uv run --extra api trazia diff examples/vessel_rev_a.json examples/vessel_rev_b.json --geometry -o generated/changes.json
uv run --extra api trazia bcf examples/vessel_rev_a.json examples/vessel_rev_b.json -o generated/changes_DRAFT.bcfzip
```

La API instala el extra geo a través de su dependencia de extras; el CLI geométrico también
puede instalarlo por separado. La diferencia visual verifica originales por SHA-256, usa
traslación/rotación ECC acotada a 3 grados y 5 % de página y transforma evidencias y marcadores
al marco de la página anterior. Si falla la alineación se informa, sin atribuir cambios.
Se procesan hasta diez páginas por PDF común y hasta 200 regiones/marcadores por página.
Los triángulos y nubes son candidatos heurísticos que hay que confirmar. Los cruces señalan
campos sin región y regiones sin campo; un cajetín modificado también puede producir avisos.

La capa geométrica usa distancias de vértices de mallas propias con discretización fija,
en metros y por GUID; compare-ifc ofrece el contraste adicional contra superficies.
No se incorpora un mapa de calor al visor protegido. BCF contiene cámaras, GUID, huellas y
referencias documentales; no incluye originales privados ni declara aprobación automática.
El formato se ha contrastado con los XSD oficiales de la etiqueta v2.1 de buildingSMART.

Fuentes: [BCF 2.1](https://github.com/buildingSMART/BCF-XML/releases/tag/v2.1),
[ECC OpenCV](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html).


## Copiloto con Groq y citas

Configura `GROQ_API_KEY` en el entorno de FastAPI. El frontend usa la API misma que
Documentos. La clave se carga en el servidor y se conserva fuera del repositorio.
La política predeterminada `TRAZIA_EXTERNAL_PROVIDERS=synthetic_only` autoriza
las consultas sintéticas. El Copiloto trabaja sin Ollama.

- `GET /copiloto/contexts` lista los proyectos, equipos y revisiones indexados,
  los complejos sintéticos y los proyectos con archivos publicados.
- `POST /copiloto` recibe `revision_id`, `question` y, opcionalmente, `path` y
  `previous_id`. Las dos revisiones deben ser del mismo equipo y proyecto.
- `POST /copiloto/project` recibe `kind` (`project`, `process` o `catalogue`),
  `id`, `question` y la `revision` A/B del complejo cuando corresponda. El
  catálogo publicado responde sobre los archivos registrados. Las cotas de un
  equipo de un proyecto indexado se consultan en una de sus revisiones.

La API recupera hasta 26 fuentes del contexto. Para los datos sintéticos, Groq
GPT-OSS 20B selecciona sus identificadores en una llamada con esquema estricto.
El servidor valida los identificadores y forma las frases con los valores de
las fuentes. Puede abstenerse si falta respaldo. Las citas de originales
incluyen SHA-256 y página/región o celda si el texto pudo verificarse.
Las consultas sobre datos no clasificados como sintéticos usan la evidencia
indexada sin enviarla a Groq. Evita introducir originales o datos privados en
las preguntas de un contexto sintético.

La respuesta mantiene `read_only: true`, fuentes y versión del contexto.
`run` registra tiempo, llamadas y tokens reportados, con coste sin medir si falta
una cifra verificable. El registro de envíos guarda la huella del contexto y
el proveedor. Las respuestas respaldadas de una revisión se reutilizan en
caché cuando la pregunta, las fuentes, el proveedor y la revisión coinciden.
El modo offline conserva esas respuestas. El modo local por evidencia no
arranca ningún modelo.

- `POST /copiloto/design-proposals` prepara operaciones sobre una revisión.
  Las reglas resuelven las órdenes explícitas. Groq puede identificar el
  parámetro para un valor final con unidad ya escrito. El editor valida y
  previsualiza el lote y requiere una confirmación humana para crear una
  revisión DRAFT.
- `POST /copiloto/process-drafts` devuelve ajustes acotados a los rangos del
  complejo. Indica TAG, parámetro, valor final y unidad. El editor de la planta
  conserva su paso de previsualización.

[Salida estructurada de Groq](https://console.groq.com/docs/structured-outputs).

### Dictado y lectura de respuestas

El dictado usa Whisper Large V3 Turbo y está apagado por defecto. Para activarlo,
verifica **Free** en Settings → Billing de Groq y conserva esa organización sin
facturación. Configura una clave dedicada y distinta de la del chat de texto con
`GROQ_VOICE_FREE_API_KEY` y habilita `TRAZIA_VOICE_GROQ_FREE=1` en FastAPI. En
Windows, añade ambos valores al archivo local que se pasa como `-GroqEnvFile` y
reinicia el supervisor de la API. Desactiva el dictado antes de modificar el plan
de esa organización. El ajuste confirma una verificación operativa del plan.

- `GET /copiloto/voice?kind=revision&identity=<id>` comprueba si se ofrece el
  micrófono. `kind=process` admite complejos sintéticos del catálogo incluido.
- `POST` a la misma ruta acepta un archivo multipart `file` de hasta 512 KiB
  en WebM, MP4 u Ogg. Devuelve `{"text":"…"}`. La API comprueba el contexto
  almacenado y bloquea el envío en modo offline. El navegador limita cada
  grabación a 20 segundos. Usa el micrófono solo para hablar de sintéticos.
- Si se agota la cuota, la API devuelve 429 y el usuario puede escribir. El
  Copiloto conserva la transcripción como texto editable hasta que el usuario
  pregunta o prepara un borrador. El registro de envíos guarda una huella del
  audio y el proveedor, sin grabar el audio ni la transcripción.
- **Escuchar respuesta** usa una voz local en español del navegador si existe.
  El navegador lee las frases respaldadas a petición del usuario.
- **Conversar por voz** abre un avatar 3D con estados de escucha, consulta y
  respuesta. La pantalla oculta ambas transcripciones. El navegador detecta
  el fin de cada turno por la pausa de voz, envía el clip a la misma ruta de
  dictado y vuelve a escuchar después de leer la respuesta. Se puede enviar
  el turno manualmente, pausar o interrumpir la lectura para hablar. Las
  consultas usan la revisión seleccionada y la búsqueda habitual de fuentes.
  Para preparar un cambio de diseño, vuelve al modo de texto y usa el editor.

[Cuotas de Groq](https://console.groq.com/docs/rate-limits) ·
[Facturación de Groq](https://console.groq.com/docs/billing-faqs).

## Medición del lote con workers

`scripts/run_scale.py --wsl Ubuntu --workers 1 4` levanta despliegues aislados Redis/arq/Postgres
y llama al cliente `scripts/measure_scale.py` para procesar todo el corpus sintético. Requiere
la imagen API construida y generated/synthetic_v2. Publica la API de prueba solo en localhost
18000 dentro de WSL; no sustituye el servidor de desarrollo. Los almacenes son nuevos por prueba
y se eliminan con sus contenedores al terminar. Se conserva el estado terminal de cada trabajo.

El informe separa tiempos observados, costes no informados y extrapolación a 400×4. No supone
que un trabajo fallido haya producido un IFC, ni que un IFC estructuralmente válido coincida
con el plano. Resultados y límites de la primera medición: [FASE3.md](FASE3.md).


## Estudio, modo offline y correcciones · 30/10/2026

[Contrato, ejemplos, arquitectura y verificación](BACKEND_2026-10-30.md).
`POST /estudio` exige un cuerpo StudyInput y `Idempotency-Key`. Devuelve 202 con `job_id`;
se consulta y cancela mediante `/jobs/{id}`. `GET /estudio?job_id=…` selecciona su resultado.
La ruta de conjuntos sintéticos la fija `TRAZIA_STUDY_DATA`, nunca el cliente.
`GET /learning/corrections?after=0&limit=100` no entrena ni recalibra.
Con `TRAZIA_OFFLINE=1`, visión y copiloto usan sus cachés; una consulta sin caché devuelve
un error recuperable. Los tipos OpenAPI de la web reflejan el contrato actualizado.


## Estudio mediante CLI estable · sesión Plataforma 30/10

El trabajo lanza `python -u -m bench.estudio` como subproceso con los argumentos estables
`--datos`, `--conjuntos`, `--variantes`, `--casos`, `--degradaciones`, `--remuestreos`,
`--semilla` y `--salida`. No importa funciones internas de `bench`. El directorio de
salida pertenece al trabajo; el JSON se guarda en el almacén SHA-256 al terminar.
Se conservan SSE de inicio/salida resumida/fin, timeout, cancelación del proceso e
idempotencia. Un proceso que termine sin `estudio.json` deja un error explícito; no
publica resultados ni sustituye el estado vacío. Prueba real: un caso, variante B,
vectorial, 20 remuestreos.


## Caché de trabajos en la API · 4.2

Los trabajos de lectura terminados y con IFC validado guardan su revisión DRAFT y avisos
en el almacén SHA-256. La clave combina hashes de originales, metadatos documentales
(identidad, nombre, revisión y orden), estrategia, proveedores, dataset y huella de la
memoria anterior, cuando la haya. Los IDs SQL de subida no forman parte de la clave.
No se cachean fallos, cancelaciones, timeouts ni aprobaciones humanas posteriores.

Con `TRAZIA_OFFLINE=1`, POST de trabajo comprueba la entrada antes de encolar: un fallo
devuelve HTTP 409 en español. También se verifican los originales y el blob cacheado.
En un acierto el worker restaura el resultado sin llamar al pipeline, asigna los IDs
del trabajo nuevo y mantiene approval=null. GET /jobs/{id} indica cache_hit=true y SSE
explica la reutilización. La contabilidad de esa lectura de caché tiene cero tokens,
inferencia GPU y llamadas externas nuevas; no suma el coste histórico del trabajo
original ni mide energía. El modo online sigue ejecutando el pipeline y calentando
la caché; esta es una instantánea preparada para la demo, no una evaluación de un
modelo actualizado. Al cambiar modelos/reglas se prepara una caché nueva.

Persistencia: Alembic 0004 añade job_cache y el indicador de acierto al trabajo. No cambia
el contrato 0.3 ni se modifica vision/cache.py. Las cachés de visión/copiloto existentes
se conservan, separadas de esta caché de resultados del pipeline.


## CORS configurable · sesión Plataforma

`TRAZIA_CORS_ORIGINS` acepta orígenes HTTP(S) separados por comas y sustituye la lista
predeterminada. Se recortan espacios, se normalizan puertos estándar y se eliminan
duplicados. Rutas, credenciales, comodines y puertos inválidos se rechazan al crear la API.
Ausente o vacía conserva localhost y 127.0.0.1 en 3000, 3100, 3200, 3300, 3310 y 3311.
Compose propaga la variable a API y workers. Para el frontend de esta sesión, PowerShell:

```powershell
$env:TRAZIA_CORS_ORIGINS="http://localhost:3120,http://127.0.0.1:3120"
$env:TRAZIA_PORT="8020"
uv run --extra api python -m trazia.api
```

Las cabeceras de idempotencia, If-Match y ETag y los métodos admitidos no cambian.


## Registro de correcciones humanas · 3.8 (datos)

Cada PATCH confirmado que cambia valor, unidad o estado registra una fila transaccional
y añade una línea a `generated/correcciones/correcciones.jsonl`. La ruta estándar es
relativa a la raíz del repo; `TRAZIA_CORRECTIONS_FILE` permite fijarla. Con data_root
explícito en una aplicación embebida, la salida predeterminada queda dentro de ese
almacén, para aislar datos y pruebas. Compose usa /data/correcciones/correcciones.jsonl.

Formato de cada línea: revision_id, equipment_tag, revision, path, value_before,
value_after, unit, state_before, state_after, confidence, confidence_raw, channel,
strategy, document_id, page, bbox, actor, at y data_sha256. Los opcionales ausentes
son null. La confianza, canal, estrategia y cita pertenecen a la predicción ANTERIOR
a la intervención; unit y data_sha256 corresponden al resultado. at es ISO 8601 UTC.
No se exige ni se supone que la confianza esté calibrada o que exista un intervalo.

GET /correcciones?desde=2026-10-30T00:00:00Z devuelve {correcciones:[...],count:N},
filtrado inclusivamente desde esa fecha. Se requiere zona horaria; no llama a modelos
ni a calibración. Son intervenciones históricas, incluidas revisiones aún no aprobadas.
La exportación previa /learning/corrections conserva su selección de ejemplos aprobados.

Se conserva auditoría, ETag/If-Match e idempotencia. Una petición repetida no duplica
líneas; una edición rechazada o sin cambios no crea una corrección. Alembic 0005 añade
una bandeja de salida SQL y un cursor. El bloqueo de publicación funciona en SQLite
y Postgres. Ante un fallo tras escribir, el reintento descarta solo la cola no confirmada
y vuelve a publicar; el archivo perdido o truncado se reconstruye con las filas SQL.
Usar un único almacén SQL por archivo configurado. Si falla la exportación, el PATCH
informa 503: el campo está guardado y se reintenta con la misma Idempotency-Key. Las
filas siguen accesibles por GET; al arrancar se intenta publicar lo pendiente.


## Recalibración desde las correcciones (31/10)

`uv run python -m bench.recalibrar --almacen <TRAZIA_DATA> --correcciones <JSONL> --base <calibracion.json> --salida generated/recalibracion`
propone un reajuste isotónico y conforme en CPU, sin ejecutar visión. `--base` es opcional.
El JSONL se contrasta con el registro SQL, la predicción original de la auditoría, la
aprobación vigente y los originales disponibles. Se deduplican los clics por campo;
se incluyen confirmaciones correctas y correcciones, no solo errores. Los ejemplos
reales, borradores, intervenciones sustituidas, valores ya humanos y predicciones sin
confianza bruta identificable quedan fuera. Las revisiones del mismo tag no se reparten
entre ajuste y prueba. Los cambios de unidad sin normalizar se excluyen, y los textos
se comparan sin distinguir mayúsculas.

Mínimos: seis equipos independientes por estrategia, 30 campos por grupo de ajuste
y 30 campos de validación por estrategia. Dos tercios de los equipos se dividen de nuevo entre curva y cuantil; el
tercio restante valida ECE. Solo se escribe `calibracion.json` si todas las estrategias
observadas tienen curva y el ECE de validación no empeora frente a la base. Siempre se
escribe `informe.json`, con estado `insufficient`, `rejected` o `candidate`; la propuesta
no activa nada. No se sobrescribe la base. Las estrategias sin nuevos ejemplos
conservan su calibración anterior (o confianza bruta si no tenían parámetros), también
para intervalos y abstención. El sesgo de qué campos revisa una persona
impide interpretar esta validación como precisión sobre todos los planos.

Para activar una propuesta revisada, usar su archivo como `TRAZIA_CALIBRATION`. En
Compose, API y workers comparten `/data/calibration/calibracion.json` por defecto. La
clave de caché incorpora la huella de la calibración; las entradas de la versión previa
no se reutilizan. Si los parámetros cambian mientras corre un trabajo, ese resultado
se entrega pero no se incorpora a la caché. Los valores/calibraciones no cambian las
revisiones ya aprobadas.

El lote de escala informa ahora `lod` y `equipment_kind` para cada modelo accesible y
`successful_lods`/`errors_by_message` en el resumen. Una envolvente de bomba LOD 1 no
se presenta como un recipiente detallado. Los errores de inspección por tag permanecen
explícitos y no interrumpen la contabilidad del lote.


## Revisión, sesiones y ejemplos aprobados (31/10)

- `GET /reference-system`: origen, ejes y unidades internos; Norte de planta/TR sin verificar.
- `GET /revisions/{id}/validation`: avisos de revisión y posible solape; no certificación normativa.
- `PATCH /revisions/{id}/fields/{path}` admite `source`, `explanation`, `seconds`,
  `review_session_id`, `action` y `expected` opcionales. `expected` es el campo trazado mostrado
  al usuario; si ya cambió se devuelve 412 aunque el ETag global fuese reciente.
- `action=reject` exige `state=abstained`. Conserva el candidato, añade la explicación de rechazo
  y bloquea aprobar. `accept/correct/assume` deben coincidir con el estado correspondiente.
- `X-Audit-Id` y ETag identifican una escritura confirmada y se exponen por CORS.
- `POST /revisions/{id}/audit/{audit_id}/undo`: actor, segundos/sesión opcionales, If-Match e
  Idempotency-Key. Restaura el campo completo, registra `undo_of` y retira la aprobación. 409 si
  el campo cambió después o la acción ya fue deshecha; 404 para auditoría ajena o aprobación.
- Un 422 devuelve `detail` legible y `issues` con `path`, `message`, `action`; la transacción no
  guarda datos inválidos. Los avisos de geometría aproximada se distinguen de las restricciones
  bloqueantes del contrato.
- Si solo falla exportar el JSONL, el 503 contiene `persisted=true`, `revision`, ETag y
  X-Audit-Id. La edición SQL ya existe. `POST /correcciones/export` reintenta idempotentemente el
  volcado, sin reescribir el campo. También se conserva el reintento del PATCH con su clave original.

`POST /review-sessions` recibe `revision_id`, `actor`, `kind=human|test` e Idempotency-Key.
`POST /review-sessions/{id}/finish` recibe `active_seconds`; finalizar otra vez no modifica el
registro anterior. El reloj declarado debe caber en el tiempo de sesión (tolerancia 2 s) e incluir
los segundos de sus acciones. No se permiten acciones nuevas en una sesión terminada.

`GET /revisions/{id}/review-metrics` y `GET /equipment/{tag}/review-metrics?project_id=...`
informan de tiempo activo del cliente, sesiones abiertas/terminadas/de prueba, dataset, pendientes
y aprobación. Agrupan por proyecto, equipo y dataset; no mezclan sintéticos con reales. Sin
sesiones humanas terminadas con acciones, `active_seconds=null`. En la auditoría, `review_seconds`
es solo la suma de tiempos declarados de acciones, `null` si no hay ninguno; `untimed_actions`
explicita la cobertura faltante. No es una duración completa de revisión.

`GET /learning/few-shot?path=diameter&strategy=b_reglas&target_revision_id=B&limit=3`
entrega hasta cinco pares user/assistant de correcciones sintéticas actualmente aprobadas,
con hashes de documento y aprobación. `target_revision_id` excluye el mismo equipo y los
mismos documentos. `GET /learning/few-shot/{id}/evidence` verifica el original y devuelve su
recorte PNG PDF (CPU, hasta 1000 px de página); si se revoca la aprobación, deja de servirlo.
La selección se limita a revisiones marcadas sintéticas; las marcadas reales quedan excluidas.

El contexto del Copiloto recibe esos ejemplos como datos de revisión, sin usarlos como evidencia
actual. Su caché cambia con el manifiesto. El uso por extractores y el ajuste de prioridad de
fuentes se coordinan con Lectura: `applied_to_extraction=false`. No se activa calibración al leer
un ejemplo. La caché de trabajos v3 incluye SHA de fusión y calibración, capturados antes de
ejecutar; un cambio de pesos invalida resultados anteriores, incluidos los offline v2.

Ver [auditoría y límites](AUDITORIA_REVISION.md), [sesión manual preparada](MUESTRA_REVISION_MANUAL.md)
y [diagrama y coste para el pitch](PITCH_ESCALA.md). Migración de almacén `0006`; sin dependencias
nuevas ni cambios del contrato `model.py` 0.3.


## Ampliaciones 01/11

- PATCH de campo admite `decimal_separator: "." | ","`, convierte con Pint y conserva texto/unidad originales. Ambigüedad, unidad incompatible o cambio de unidad sin valor devuelve 422 sin mutación ni cambio de ETag. La base absoluta/manométrica no se convierte implícitamente. [Normalización](NORMALIZACION.md).
- POST de trabajo admite `use_learning: boolean` (por defecto true): ejemplos y prioridades solo desde revisiones aprobadas con sesión humana finalizada; exclusión de equipo/documentos y verificación de originales. Caché v4 incluye estado de feedback. [Condiciones y límites](APRENDIZAJE_APROBADO.md).
- `POST /viewer/bcf` convierte una captura del navegador en BCF 2.1: `png_base64`, `eye`, `target`, `up` (triples de coordenadas web), `zoom`, `viewport_height`, `guid` IFC seleccionado y `actor` opcional. Devuelve application/zip con ZIP BCF, snapshot PNG y cámara ortográfica convertida a IFC; no modifica revisiones ni aprueba. Rechaza PNG inválido/demasiado grande, cámara degenerada, coordenadas no finitas y GUID inválido con 422. Es una conversión de datos aportados; no certifica su procedencia ni sus rótulos. El visor adjunta DRAFT y procedencia de su IFC real.
- `TRAZIA_PAGE_CACHE` es opcional; por defecto, las etapas de texto, raster y geometría usan `TRAZIA_OCR_CACHE/page-stages`. La caché OCR por página tiene huella propia de contenido/recursos/geometría PDF más DPI y motor; se regenera si falla la integridad. Una página reutilizada recibe el document_id actual, no el de la revisión anterior. Sin huella segura se procesa normalmente.


## Marcas de revisión · F.5 (01/11)

`GET /diff?from=A&to=B&marks=true` incorpora `layers.revision_marks`. Con `layers=false`
(predeterminado), este modo solo lee los originales de B y no ejecuta ECC ni genera IFC.
Con `layers=true` se mantienen las capas completas y sus límites anteriores.

El cruce verifica SHA y separa documentos y páginas; una marca del documento X nunca cubre
un campo del Y. Coordenadas normalizadas respecto a la página de B (`coordinate_frame=after-page`).
Devuelve `documents` (marcas candidatas, estado, páginas sin lectura), `unmarked_changes`,
`marks_without_change` y `unlocated_changes`. `is_design_validation=false`: nunca aprueba ni altera
ETag/revisiones. Los identificadores de marca son estables por documento y contenido detectado.

Hasta 100 páginas por original; las restantes se declaran truncadas. Páginas dominadas por
raster quedan sin lectura aunque incluyan una cabecera vectorial. Campos eliminados sin caja
en B quedan sin localizar; no se proyecta su caja antigua sobre el plano nuevo. Ausencia de
original, SHA diferente o error de lectura se declara explícitamente. [Detalle](MARCAS_REVISION.md).


### Lectura CPU y aprendizaje aprobado · 02/11, revisión nocturna

El OCR conserva el tamaño original del perfil de lectura y fija ONNX en CPU.
`TRAZIA_OCR_THREADS=2` limita los hilos internos por sesión (1–8). La huella de trabajos
incluye el perfil OCR y la versión del lector; una actualización no reutiliza resultados
incompatibles. La caché OCR de imagen y página lleva suma de comprobación y escritura atómica.

La cabecera de boquillas se reconstruye respecto a su marca para que una cota de otra zona
no la parta en filas. Si faltan dimensiones o su combinación es incoherente, se prueba el giro
90° para números verticales y, después, cuatro recortes solapados. Las cajas se transforman
al sistema normalizado del PDF original. El mosaico solo sustituye dimensiones cuando la lectura
es completa, compatible con las cotas previas de alta confianza y pasa las mismas restricciones.
Las tablas y los atributos previos se conservan. No se rellenan campos desde GT ni se relajan
los validadores. La geometría automática sigue siendo DRAFT.

`python -m bench.recalibrar --almacen <store> --correcciones <jsonl> --base <base> --salida <dir>`
exige por defecto intervenciones vinculadas a sesiones humanas finalizadas, auditoría SQL,
originales verificables y aprobación vigente. `--simulacion-sintetica` permite ensayos de pruebas
y marca el artefacto; no acredita una sesión humana real. Las APIs de correcciones no cambian.

Las particiones agrupan por equipo y por componentes de documentos compartidos, incluidos
alias transitivos. Hay grupos separados para curva, conformal y validación. La ruta de feedback
de D ajusta una sola curva global posterior a la fusión; nunca curvas por canal. El ajuste
habitual de `bench.calibrar` mantiene su protección original para D. Se conservan la calibración
anterior y su huella como respaldo para las estrategias no observadas. Una propuesta rechazada
no se publica y ninguna propuesta se activa automáticamente.

La tasa de acierto por canal produce `candidate_priorities` y estadísticas, pero no cambia los
pesos usados por el pipeline. `priority_status=requires_independent_validation` y
`activated=false`: la evaluación anterior encontró una regresión, por lo que registrar más
correcciones no autoriza aplicarla. Los ejemplos aprobados siguen viajando como datos citados,
con exclusión del equipo y originales destino y los límites de contexto existentes.

La validación representativa continúa dependiendo de correcciones humanas independientes.
Las simulaciones no miden tiempo humano ni eficacia few-shot de un proveedor de visión.

## Edición asistida del modelo · workstream K (08/11)

Propuestas de cambio de diseño: `GET /revisions/{id}/design-operations`,
`POST /revisions/{id}/change-proposals`, `GET|PUT /change-proposals/{id}`,
`POST /change-proposals/{id}/preview|apply|discard|revert`, `GET /change-proposals/{id}/preview.ifc`,
`GET /revisions/{id}/artifacts`, `GET /revisions/{id}/design-report.pdf` y
`POST /copiloto/design-proposals`, que solo devuelve un borrador. Aplicar crea una revisión DRAFT
nueva; nunca edita la base. Detalle y garantías en [EDICION_ASISTIDA.md](EDICION_ASISTIDA.md).


## K8 · piezas y planos GA nuevos (08/11)

`POST /revisions/{id}/change-proposals` admite, además de las operaciones de campo:

```json
{
  "actor": "Revisor local",
  "reason": "Añadir conexión de prueba sintética",
  "part_changes": [{
    "action": "add", "collection": "nozzles", "id": "N5",
    "parameters": {
      "diameter": {"value": 100, "unit": "mm"},
      "projection": {"value": 200, "unit": "mm"},
      "elevation": {"value": 4500, "unit": "mm"},
      "azimuth": {"value": 45, "unit": "deg"}
    }
  }]
}
```

`remove` lleva colección e ID, sin parámetros. Máximo 20 cambios en total. El catálogo
`GET /revisions/{id}/design-operations` incluye capacidades por familia y LOD. Plataformas
(x/y/z, size_x/y/z) y escaleras (x/y/z, width, height, rail_diameter, rung_spacing) requieren
LOD 3 explícito; en una base LOD 2 se envía `detail_level: 3`. En conexiones de horizontal,
columna y tanque se usan diámetro, proyección, x/y/z y dx/dy/dz (unidad `1`).
Las reglas validan el candidato completo y no mueven conexiones para ocultar errores.
Previsualizar, aplicar y deshacer conservan sus endpoints, ETag e idempotencia.

- `POST /revisions/{id}/ga-drawings`: `{}` o `{"scale":100}`, `If-Match` e
  `Idempotency-Key` obligatorios. Responde 202 con `job_id`; seguimiento/cancelación por los
  endpoints existentes de trabajos y SSE. Tiempo máximo 240 s, publicación condicionada al ETag.
- `GET /revisions/{id}/ga-drawings`: enlaces de los cuatro artefactos vigentes (`pdf`, `svg`,
  `manifest`, `ifc`), con SHA-256. Una revisión sin plano devuelve `files: {}`.
- `GET /revisions/{id}/ga-drawings/{formato}?sha=<sha>`: descarga un artefacto histórico
  registrado para esa revisión. Cabeceras `X-Derived-Document: true` y `X-Content-SHA256`.

El PDF vectorial y SVG son A3 apaisado, con escala común admitida, alzado, perfil, planta,
cotas exteriores y cajetín DRAFT. El manifiesto vincula revisión, versión, huella de datos,
IFC exacto, dimensiones mm y GUID. No se modifica el PDF original. La subida de documentos
rechaza el GA registrado/identificado como derivado. No hay ocultación de líneas ni validación
resistente o de fabricación. ReportLab pasa también al extra `api`; `uv.lock` mantiene las
versiones anteriores. Cancelar impide publicar, aunque un hilo de cálculo nativo ya iniciado
puede acabar en segundo plano. [Evidencias reproducibles](evidencias/k8/README.md).
## Borrador de planta sintética

`POST /proyectos-proceso/{project_id}/borrador` devuelve un IFC4 `DRAFT`.
El cuerpo JSON contiene `applied` con los tags de los cambios A/B activos y
`adjustments` con hasta ocho objetos `{tag, field, value}`. Los campos
publicados por componente son `length`, `width`, `height` y `rack_z` en
metros, y `dn` en milímetros enteros. `rack_z` es relativo a la cubierta.

La operación se limita al catálogo público sintético y genera un archivo
efímero. Los errores de entrada o de geometría devuelven 422. Un proyecto
desconocido devuelve 404 y un generador ocupado, 429.
## Cuentas y catálogo compartido

Con `TRAZIA_AUTH=1`, la API valida la contraseña de `javier.saguar`,
`iria.lozano`, `miguel.vera` y `alejandro.cuevas`. En el primer arranque,
inyecta `TRAZIA_ADMIN_PASSWORD_FILE` o `TRAZIA_ADMIN_PASSWORD`. La API guarda
un hash scrypt con sal por cuenta. El arranque posterior usa los hashes
existentes. El invitado entra desde la portada con un botón de solo lectura.

| Método y ruta | Acceso |
| --- | --- |
| POST /auth/login, POST /auth/guest | Entrada de cuentas registradas o invitado |
| GET /auth/session, POST /auth/logout | Sesión vigente y cierre de sesión |
| PUT /auth/session/role | Cada integrante con cuenta administradora alterna su sesión entre `admin` y `usuario` |
| PUT /auth/avatar | La cuenta activa sube su propia foto PNG, JPEG o WebP de hasta 1 MB |
| GET /catalogue, GET /catalogue/designs/{id}/file | Consultar el catálogo y sus archivos |
| POST /catalogue/groups | Administradores crean familias y proyectos |
| POST /catalogue/designs, PATCH /catalogue/designs/{id} | Administradores publican y reclasifican diseños |

El selector de **Ajustes → Perfil** cambia el rol solo en la sesión actual. La API aplica ese rol a cada petición. Una sesión nueva usa el rol asignado a la cuenta. Desde el mismo perfil, el equipo puede cambiar de cuenta iniciando sesión con la contraseña de la cuenta elegida. Las fotos se conservan en `TRAZIA_DATA/avatars/` y se muestran en Ajustes y en la barra lateral.

La web sirve la API desde su propio origen. Configura `NEXT_PUBLIC_API_URL=/api/trazia`
y `TRAZIA_API_ORIGIN` con la URL interna de FastAPI al construir y arrancar Next.
Lista el origen público de la web en `TRAZIA_CORS_ORIGINS`. En local por HTTP,
usa `TRAZIA_AUTH_COOKIE_SECURE=0`. Para publicar el sitio, sirve la web por HTTPS
y conserva la configuración segura predeterminada de las cookies.

Conserva PostgreSQL mediante `TRAZIA_DATABASE_URL` y el volumen `TRAZIA_DATA`
entre despliegues. Los archivos publicados se escriben en
`TRAZIA_DATA/catalogue-files/`. Realiza copias de seguridad de ambos.
El perfil `escala` de Docker Compose incluye PostgreSQL y los volúmenes.
En dicho perfil, `TRAZIA_API_ORIGIN=http://api-scale:8000` conecta la web con la API.

La biblioteca compartida admite IFC, PDF, XLSX, XLS, PNG y JPEG de hasta 25 MB.
Los diseños de la demo local se pueden publicar mediante **Añadir diseño**.

### Vista previa local de roles

Arranca la API con el archivo de contraseña habitual y apunta la web al puerto local.
El script reutiliza `generated/roles-local/datos`, comprueba el acceso de
`javier.saguar` y actualiza su contraseña y sus sesiones si el archivo ha cambiado.
Añade `--solo-acceso` para reparar una instancia que ya está en marcha.

```powershell
uv run --extra api python scripts/api_roles_local.py --archivo "<archivo local de contraseña>" --lote "<lote local>" --dataset "<originales del lote>"
```

Desde `web/`, arranca Next con `NEXT_PUBLIC_API_URL=/api/trazia`,
`TRAZIA_API_ORIGIN=http://127.0.0.1:8044` y `corepack pnpm dev --port 3044`.

### Vercel con una API local a través de ngrok

1. Arranca una sola instancia de FastAPI con `TRAZIA_AUTH=1`, `TRAZIA_CORS_ORIGINS`
   igual a la URL pública de Vercel y cookies seguras. Escucha solo en el bucle
   local y conserva `TRAZIA_DATABASE_URL` y `TRAZIA_DATA` del catálogo.
2. Con ngrok autenticado, crea el túnel hacia la API. Para una API local en el
   puerto 8020, usa `ngrok http http://127.0.0.1:8020 --inspect=false`.
3. En las variables de **Production** del proyecto Vercel, configura
   `NEXT_PUBLIC_API_URL=/api/trazia` y `TRAZIA_API_ORIGIN` con el origen HTTPS
   de ngrok. Vuelve a desplegar el frontend. `web/vercel.ts` reenvía las peticiones
   a FastAPI desde el propio dominio de la web.
4. Comprueba el inicio de sesión, una subida sintética cercana a 25 MB y la
   descarga como invitado después de reiniciar la API. Conserva el mismo volumen
   y la misma base de datos entre arranques.

La API, PostgreSQL y el agente de ngrok deben seguir activos en el equipo que
aloja los datos. El dominio asignado por ngrok se mantiene al reiniciar su agente.

En Windows, `scripts/serve_windows.ps1` supervisa este despliegue con los volúmenes
locales `generated/cuentas-datos` y `generated/cuentas-postgres`. Reutiliza el túnel
activo y relanza FastAPI, PostgreSQL y ngrok cuando dejan de escuchar. El arranque
de PostgreSQL corre aparte para que el supervisor pueda comprobar el puerto y
continuar con FastAPI aunque el lanzador de PostgreSQL tarde en terminar. Los
arranques y salidas quedan en `generated/servicio-windows/supervisor.log`, con los
registros de cada proceso al lado.

Con la tarea `TrazIA-3D API` ya instalada, ejecuta
`./scripts/update_windows_service_task.ps1 -TunnelUrl <origen HTTPS de ngrok>`.
Conserva el inicio al abrir sesión y añade un intento cada minuto sin límite de
duración. La tarea usa la configuración existente `IgnoreNew` para evitar instancias
simultáneas. El supervisor pide a ngrok el mismo dominio que usa Vercel al reiniciar.
El equipo debe estar encendido, despierto, conectado y con la sesión de Windows
abierta para que pueda ejecutarse la tarea.

Para recuperar la tarea en ese equipo, `Start-ScheduledTask -TaskName 'TrazIA-3D API'`.
Comprueba `/api/trazia/health` en el dominio público y después el inicio de sesión.
Si el agente de ngrok responde `ERR_NGROK_8012`, verifica primero que FastAPI
escucha en `127.0.0.1:8020`. La sesión pública depende de que Windows siga
encendido, despierto y conectado.

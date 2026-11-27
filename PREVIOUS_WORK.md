# Trabajo previo al evento

Equipo: Javier Saguar Antona, Iria Lozano Carrasco, Miguel Vera del Castillo y Alejandro Cuevas Cid.

- Repositorio de origen: [javiersaguar/trazia-3d](https://github.com/javiersaguar/trazia-3d).
- Etiqueta: `pre-hackathon-baseline`.
- Commit: `906a97e79ab0cc0f56aaefb018480eb87321990b`.
- Fecha de corte: 25 de noviembre de 2026, 11:55:40 (Europe/Madrid), según el commit etiquetado.

Toda la base previa usa datos sintéticos. Los documentos, planos, modelos y salidas de Técnicas Reunidas pertenecen al trabajo del evento.

## Base preparada

### Lectura de documentos y modelo

- Núcleo Python y contrato 0.3: valor, unidad, fuente, confianza, estado y aprobación por campo.
- Ingesta de PDF vectorial y escaneado, XLSX e imágenes, con huella SHA-256 de cada original.
- Cuatro estrategias de lectura (A geometría, B reglas con OCR, C recuperación y D híbrida),
  con calibración, intervalos y abstención.
- Familias paramétricas y exportación IFC4, IFC4X3 e IFC2X3 con trazabilidad y GUID estables.
- Comparación de revisiones, BCF 2.1 y auditoría automática de geometría, unidades y propiedades IFC.
- Edición asistida (K.0–K.8): propuestas de cambio con vista previa del IFC, revisión derivada,
  deshacer, plano derivado en PDF, piezas reversibles y planos GA desde IFC.

### Plataforma

- API FastAPI con eventos SSE, cola Redis y workers, Postgres o SQLite, cachés y modo offline.
- Lote por carpeta y cuatro notebooks de Databricks preparados para la plataforma del evento:
  comprobación del entorno, proceso del lote, perfil del dataset y evaluación contra los IFC de
  referencia. Solo trabajan con agregados; ningún dato del reto sale de la plataforma.

### Web

- Next.js con portada, documentos por familias y proyectos, pipeline por estrategia, revisión,
  cambios entre revisiones, modelo 3D que lee el IFC, estudio, lote, impacto y copiloto.
- Catálogo sintético de 18 familias con 72 diseños: 56 con plano GA e IFC paramétrico y 16 bocetos.
  Desde Modelo › Diseños se ven en 3D y se editan en directo; el IFC se regenera en el navegador.

### Estudio y evidencias

- Banco sintético y estudio A/B/C/D con intervalos del 95 %, en `docs/ESTUDIO.md`.
- Mediciones y sus límites en `docs/evidencias/`. Proceden de sintéticos y no acreditan fidelidad
  en los planos que se entreguen en el evento.

### Presentación y preparación del evento

- Pitch web de seis minutos (`pitch/web`), exportable a `pitch/TrazIA-3D.pptx` y PDF.
- Guion de la demo con voz, pantallas, tomas y clips (`docs/GUION_DEMO.md`), vídeo de producto
  de 45 s (`promo/trazia-hackathon`) y grabación automática del vídeo de respaldo.
- Automatización del evento (`docs/AUTOMATIZACION.md`): guardián de datos en el pre-commit,
  cifras del lote al pitch, triaje de fallos, arranque y reinicio de la demo y comprobación de entrega.

### Calidad

- Pruebas de Python (538 al 18/11), pruebas unitarias de la web y del pitch y recorridos e2e con
  Playwright. CI en GitHub con Ubuntu y Windows.

## Pendiente de realizar con el equipo y los datos del evento

Recepción e inventario del dataset, permisos de procesamiento, referencia espacial y contraste
con los IFC de TR. Adaptación y evaluación real de los lectores, correcciones humanas, estudio
y demostración sobre los datos recibidos. Presentación, grabaciones y montaje finales.

## Migrado a hack-tc02

La tabla registra las rutas procedentes del trabajo previo y el commit que las incorpora. El resto del trabajo de `hack-tc02` corresponde al evento.

| Ruta | Commit |
| --- | --- |
| `PREVIOUS_WORK.md`, `AGENTS.md`, `.gitignore` (adaptados) | 1 · Base del repositorio |
| `.gitattributes`, `.githooks/`, `scripts/guardian_datos.py`, `.guardian-permitidos` | 1 · Base del repositorio |
| `pyproject.toml`, `uv.lock`, `src/trazia/__init__.py` | 1 · Base del repositorio |
| `src/trazia/{model,units,reference,runtime,extraction,ingest,page_cache,review,revisions,bcf,bcf_snapshot,ifc,viewer,app}.py` | 2 · Modelo e IFC |
| `src/trazia/families/`, `src/trazia/ocr/`, `src/trazia/reconcile/`, `src/trazia/extractors/{units,revision_marks,mechanical}.py` | 2 · Modelo e IFC |
| `examples/`, `tests/conftest.py`, pruebas de contrato, unidades, referencia, familias, IFC, cambios, marcas, ingesta, OCR, caché de páginas y Streamlit, `docs/DATA_CONTRACT.md` | 2 · Modelo e IFC |
| `src/trazia/vision/{__init__,base,cache,policy,tiling,reader,prompts,providers}.py`, `src/trazia/feedback.py`, `tests/test_lectura_vision.py` (adaptados) | 3 · Visión |
| `src/trazia/{pipeline,cli,__main__,lote}.py` (adaptados) | 4 · Pipeline y lote |
| Pruebas de CLI, pipeline, lote, IFC y exportación y casos de ingesta y OCR recuperados | 4 · Pipeline y lote |
| API de documentos, trabajos y revisión, almacén SQLite y cola local, adaptados al pipeline del evento | 5 · API recortada |

## Autoría en hack-tc02

- Los tres primeros commits (`8ddf59c`, `6e5cdff` y `1eeae5e`, del 24/07/2026) son la plantilla
  que dio la organización. La autoría del equipo se cuenta desde `1eeae5e`, igual que en
  `scripts/entrega.py`.
- «DRO98» es Alejandro Cuevas Cid. Usa ese nombre de usuario de git con el correo que figura en
  `.github/autores.txt`. Firma `83cc54a`, `f5d293c` y `7b5767a`, del 25/11, que son trabajo del
  evento. La historia no se reescribe, así que la comprobación de la entrega (D5) muestra ese
  nombre como aviso.

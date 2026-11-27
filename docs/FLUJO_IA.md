# Flujo de trabajo con asistentes de IA durante el evento

El código del evento se entrega en GitLab. El equipo tiene acceso al dataset de Técnicas Reunidas
y autorización explícita para descargarlo y trabajar con él. En el repositorio privado del equipo
la copia original está en `data/tr/`. Databricks sigue siendo el entorno oficial para repetir los
lotes, validar sus artefactos y documentar la ejecución ante el jurado. El equipo puede reproducir
los fallos también en el portátil con la copia autorizada.

Complementa a [PLATAFORMA_INDESIA.md](PLATAFORMA_INDESIA.md) (acceso, notebooks y calendario) y a
[CONTRIBUTING.md](../CONTRIBUTING.md) (autoría, ramas y comprobaciones).

## Qué pasa en cada sitio

| Sitio | Qué se hace allí | Dónde quedan los artefactos |
| --- | --- | --- |
| Portátil | Worktree propio, pruebas, diagnóstico con la copia autorizada y demo local | Originales en `data/tr/` y resultados locales en `data/private/` |
| Databricks | Carpeta Git personal, `00_comprobar_entorno`, `01_procesar_lote` y revisión de los fallos | Resultados, oro y registros en la carpeta de trabajo del volumen |
| GitLab | Ramas, integración y entrega oficial de código a las 10:00 del viernes | Código y artefactos elegidos para la entrega |
| Teams | Coordinación y entrega de presentación en el canal privado | Instrucciones de acceso en General y credenciales en 1Password |

## La regla de los datos

1. Usa el ZIP autorizado o `data/tr/` para el trabajo del equipo. Mantén los originales como
   entrada y crea una carpeta de salida por ejecución.
2. Para compartir resultados agregados, reutiliza «Resumen para el asistente» de
   `01_procesar_lote` y `03_evaluar_contra_tr`, y el perfil de `02_perfil_dataset`.
3. El pipeline exige configurar la política y registrar la autorización para enviar datos
   reales a un proveedor remoto. Consulta la sección de servicios para elegir el destino.
4. La web pública y sus ejemplos usan datos sintéticos. La copia local permite preparar la
   demostración interna con los datos del reto.

`resumen_compartible` no incluye nombres de archivo, rutas, tags ni textos de error. Renombra los
equipos a `E01`, `E02`… y reduce cada error a su categoría (`ifc_invalido`, `ValueError`,
`pipeline`…). Aun así, hay que leerlo antes de pegarlo.

| Resumen agregado | Revisar antes de compartir | Artefactos de trabajo del equipo |
| --- | --- | --- |
| Resumen de 01 y 03, perfil de 02, versiones, tiempos y categorías de error | Avisos y trazas que puedan incluir tags o cotas | Documentos, planos, JSON e IFC del lote real |

## El ciclo de trabajo

1. **Portátil.** Rama y worktree propios (`git worktree add ../TrazIA-3D-<tema> -b feat/<tema>`) y
   el agente trabajando ahí, como hasta ahora.
2. **Probar con sintéticos.** `ruff`, `pytest` y el mismo lote que correrá en la plataforma:
   `uv run trazia lote examples/documents -o /tmp/trazia/salida --dataset synthetic`.
3. **Subir la rama a GitLab** (`git push gitlab feat/<tema>`).
4. **Databricks.** En tu carpeta Git: cambiar a la rama y hacer *Pull*.
5. **Ejecutar `01_procesar_lote`** primero con `tags` = uno o dos equipos (minutos) y, si va
   bien, con el lote completo.
6. **Revisar en la plataforma.** Una persona abre allí los casos que fallan y mira qué tienen
   de especial.
7. **Volver al agente** con el resumen para el asistente y una descripción del patrón, sin valores.
8. **Reproducir con sintéticos**, arreglar y volver al paso 2.

En el portátil el ciclo dura segundos; el viaje por GitLab y Databricks, unos minutos. Por eso
se agrupan los cambios antes de subirlos y se prueba en local todo lo que se pueda.

## Reproducir un fallo real sin enseñar el plano

Describe el patrón cuando prepares un caso reproducible para las pruebas:

- «La lista de boquillas sigue en una segunda hoja del XLSX.»
- «Plano escaneado y girado 90°; el cajetín queda a la izquierda.»
- «Las cotas vienen en pulgadas y con fracciones.»
- «El tag lleva barra: `V/101`.»

Con eso el agente crea un caso sintético que reproduce el patrón: con el generador
(`uv run python -m synthetic --conjunto … --degradaciones …`) o con un caso mínimo en `tests/`.
El fixture de las pruebas usa valores sintéticos. Después de arreglarlo, repite el equipo
real en el portátil o en Databricks y deja constancia del resultado.

`uv run python -m bench.triaje <salida>` (o la celda de triaje de `04_todo`) agrupa los fallos
por categoría y etapa y deja esta plantilla rellena salvo el patrón.

Plantilla para pedírselo:

```text
En la plataforma, <n> de <total> revisiones fallan con la categoría <categoría>.
Resumen para el asistente: <pegar>.
Patrón observado (sin datos del plano): <descripción>.
Reprodúcelo con un caso sintético, añade una prueba que falle y arréglalo sin romper el resto.
```

## Git entre portátil, GitLab y Databricks

- **GitLab es el destino oficial de entrega.** GitHub privado sigue alojando el trabajo del
  equipo y la copia local autorizada. Para integrar la plantilla de GitLab, comprueba la URL
  y decide qué historial debe acompañar al código.
  [Inventario TC02 y plan](agentes/PLATAFORMA_TC02_Y_PLAN_TR.md)
- **Una carpeta Git por persona** en Databricks, dentro de su usuario. Nadie comparte la misma:
  dos personas haciendo *Pull* y *Commit* en una sola carpeta acaban en conflicto.
- **El código se edita en el portátil.** En Databricks solo se cambian los widgets. Si hace falta
  un arreglo urgente allí, se hace commit y push desde la carpeta Git en ese momento y `git pull`
  en el portátil antes de que el agente siga.
- **Sin salidas en el repo.** Los notebooks del repo están en formato fuente (`.py`), que no
  guarda salidas. No se versionan notebooks `.ipynb` con resultados; para explorar, copias
  personales fuera de la carpeta Git.
- **Autoría.** Los commits hechos desde Databricks llevan la identidad de la cuenta de GitLab:
  hay que usar el mismo nombre y correo que en `.github/autores.txt` (o añadir ese correo). El
  hook de `.githooks` no corre allí, así que nadie añade coautores a mano.
- **Comprobaciones.** Los workflows de GitHub Actions no se ejecutan en GitLab. Antes de integrar
  en `main` se pasa en local `uv run python scripts/comprobar.py` (Ruff, pruebas y lote
  sintético). El `.gitlab-ci.yml` hace lo mismo si la organización ofrece
  runners: preguntarlo. Detalle en [AUTOMATIZACION.md](AUTOMATIZACION.md).
- **Integración.** Una persona integra cada vez y lo avisa en el canal privado del equipo:
  `git pull`, comprobaciones, `merge --no-ff` y push. Recomendación: congelar `main` el viernes a
  las 9:00 para tener margen hasta la entrega de las 10:00.

## Reparto recomendado

Para que el viaje a Databricks no frene a todos, una persona por turno hace de **operadora de la
plataforma**: mantiene su carpeta Git al día, lanza los lotes, revisa los fallos en los planos
reales y pasa al resto el resumen y el patrón de cada fallo. Los otros tres programan en local
con su agente y con sintéticos. El turno rota para que los cuatro dominen la plataforma, como
piden las bases.

## IA dentro del producto: servicios de la plataforma

Esto es otra cosa: la visión que usa el pipeline, no el asistente que programa.

- El widget `proveedores` de `01_procesar_lote` pasa los proveedores al pipeline. Vacío significa
  que no hay llamadas externas.
- Con `dataset = real` cualquier proveedor externo se bloquea salvo con
  `TRAZIA_EXTERNAL_PROVIDERS=allow` y `TRAZIA_EXTERNAL_AUTH` citando la autorización escrita
  (`src/trazia/vision/policy.py`).
- Cada envío queda en `registro_envios.jsonl` dentro de `trabajo`. Con datos reales, `trabajo`
  debe apuntar a un volumen para conservar ese registro.
- Hoy no hay adaptador para el servicio de la plataforma: las familias de
  `OpenAICompatibleProvider` tienen las URL fijas (Groq, OpenRouter, NVIDIA y Cloudflare). Cuando
  sepamos qué servicio hay, se añade una familia con su URL y la clave por variable de entorno.
- Las claves de Teams se guardan en un *secret scope* de Databricks o en variables de la sesión.
  Nunca en el repo ni en el chat con el agente.

## Chuleta

En el portátil:

```bash
git worktree add ../TrazIA-3D-<tema> -b feat/<tema>
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run trazia lote examples/documents -o /tmp/trazia/salida --dataset synthetic
git push gitlab feat/<tema>
```

En Databricks: carpeta Git → rama `feat/<tema>` → *Pull* → `databricks/01_procesar_lote` →
widgets → *Run all* → celda «Resumen para el asistente».

## Antes del 25

Ensayar el ciclo entero en Databricks Free Edition con GitHub en lugar de GitLab:

1. Subir una rama.
2. Hacer *Pull* en la carpeta Git.
3. Lanzar `01_procesar_lote` con `examples/documents`.
4. Copiar el resumen y medir cuánto tarda la vuelta completa.

Ese tiempo dice cada cuánto conviene subir cambios durante el evento.

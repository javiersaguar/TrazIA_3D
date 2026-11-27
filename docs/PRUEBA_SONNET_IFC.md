# Sonnet para lectura y generación experimental de IFC

El enrutador prioriza Sonnet 5.5 en los niveles 2 y 3 con datos sintéticos. GPT‑6.1 Sol
queda de respaldo y GPT‑6 Luna abre el nivel 1. Para datos del reto, el enrutador
incorpora Claude en Azure AI Foundry con `TRAZIA_SONNET_DATOS_RETO=1` una vez confirmado
su uso. Mientras tanto, GPT‑6.1 Sol abre los niveles 2 y 3 de ese conjunto.

En la comparación de cinco modelos sobre recortes sintéticos, Sonnet obtuvo **76/76**,
con mediana de **1,89 s** y **0,002721 USD** por tarea a precio de lista. Sol obtuvo
**72/76**, **2,96 s** y **0,002160 USD** por tarea. El anexo web conserva los resultados
de todos los modelos. [Resultados agregados](../pitch/track/src/model-benchmark.json).

En una segunda prueba pasaron ocho recortes sintéticos (cuatro con desenfoque suave)
por la tarea `huecos` del enrutador. Se pidieron dos cotas visibles y una ausente
por recorte. El modo inicial de Sonnet devolvía muchas cajas en píxeles del recorte.
El adaptador envía ahora un marco cuadrado de 1.000 píxeles y devuelve cada caja al
recorte original. Con el ajuste, Sonnet acertó **12/16 cotas con cita localizada**
y Sol **8/16**. Ambos omitieron las **8/8 cotas ausentes**. Una cita se da por localizada
cuando su caja se solapa con la región de texto esperada.

## Generación experimental de IFC

**Ensayo del 26/11/2026.** Dos revisiones de V-101 y dos recipientes horizontales
sintéticos. Ambos métodos reciben las mismas cotas y boquillas. El motor de Miguel
compone las familias paramétricas. Sonnet decide qué primitivas usar y sus dimensiones,
coordenadas y ejes. Un adaptador genérico valida la receta y serializa las primitivas
a IFC4 DRAFT. Ambos métodos usan IfcOpenShell. El adaptador comparte la discretización
de los fondos, pero ensambla las piezas a partir de la receta de Sonnet.

Se escribió y reabrió cada IFC y se aplicaron las reglas EXPRESS. Se contrastaron el
inventario de piezas, los límites de cada componente y las superficies sobre el
mismo sistema de coordenadas, usando el motor paramétrico como referencia del ensayo.
La tolerancia de **2 mm** es para los límites de las piezas en estos sintéticos.

| Caso | IFC motor / Sonnet | Piezas dentro de 2 mm | Desviación máxima de los límites | Motor | Sonnet |
| --- | --- | ---: | ---: | ---: | ---: |
| V-101 A | Válido / válido | 7/7 | 0,36 mm | 2,22 s | 11,54 s |
| V-101 B | Válido / válido | 8/8 | 0,36 mm | 6,05 s | 11,57 s |
| Horizontal 1 | Válido / válido | 7/7 | 0,44 mm | 2,79 s | 18,38 s |
| Horizontal 2 | Válido / válido | 8/8 | 0,44 mm | 6,29 s | 19,18 s |

La mediana incluye generar, escribir, reabrir y validar el IFC. Sonnet tardó **14,98 s**
frente a **4,42 s** del motor. Las cuatro recetas de la pasada final funcionaron
en el primer intento y sumaron **0,071 USD** a precio de lista. La mayor distancia P95
entre superficies fue **0,37 mm**. La regeneración local conservó el GUID de N1
entre A y B. Estos resultados comparan geometría exterior a partir de cotas
conocidas. La fidelidad respecto a un IFC de TR y la trazabilidad por campo
requieren sus propias comprobaciones. Los IFC experimentales usan elementos proxy
y los IFC de Miguel conservan la semántica, los puertos y la procedencia del producto.

## Reproducir

```powershell
uv run --frozen python -m bench.agente_ifc --env .env --salida generated/bench/agente-ifc
uv run --frozen pytest -q tests/test_llm_enrutador.py tests/test_bench_agente_ifc.py
```

El banco escribe las recetas, los pares de IFC y `comparativa.json` en el directorio
de salida. El modelo trabaja con las cotas de ejemplos sintéticos del propio banco.

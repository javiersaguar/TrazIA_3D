# Presentaciones de TrazIA-3D

Hay dos pitches distintos, para públicos distintos. No se mezclan: ni el contenido ni la plantilla
de uno sirven de referencia para el otro.

| | Pitch final de 3 minutos | Pitch del track de 5 minutos |
| --- | --- | --- |
| Carpeta | [`pitch/concurso/`](concurso/README.md) | [`pitch/track/`](track/README.md) |
| Público | Jurado de la final: dirección y tecnología (CEO, CTO) | Ingenieros de Técnicas Reunidas |
| Enfoque | Producto, dificultad, escala y negocio, como pitch de startup | Los temas del track, con la identidad de TR y modelos 3D en directo |
| Duración | 3:00 en 8 hojas, más el vídeo de la interfaz (34 s) | 5:00, 8 hojas y un anexo |
| Texto y cifras | [`concurso/src/content.js`](concurso/src/content.js) | [`track/src/content.js`](track/src/content.js) |
| PowerPoint | `pitch/concurso/salida/TrazIA-3D-pitch.pptx` | `pitch/track/salida/TrazIA-3D-track.pptx` |
| Guion | `pitch/concurso/salida/TrazIA-3D-guion.pdf` y notas del orador | `pitch/track/salida/TrazIA-3D-track-guion.pdf` y notas del orador |

Las cifras del lote y del oro que citan los dos salen de [`cifras-evento.js`](cifras-evento.js),
que escribe `python -m bench.cifras aplicar` ([AUTOMATIZACION.md](../docs/AUTOMATIZACION.md)).

## Cuál usar

- «La presentación de la final», «el pitch de 3 minutos», «la del jurado», «la de los CEO»:
  **`pitch/concurso`**.
- «La de los ingenieros de TR», «la del track», «la de 5 minutos»: **`pitch/track`**.
- Si no está claro, pregunta cuál antes de tocar nada.

## Abrirlas y exportarlas

Los `.pptx` y los PDF no están en Git: se generan en local en un minuto. Hace falta Node.js 22.12
o posterior y Google Chrome. Desde la carpeta de cada pitch:

```powershell
corepack pnpm@10.18.0 install --frozen-lockfile
corepack pnpm@10.18.0 export     # .pptx y guion en PDF, en salida/
corepack pnpm@10.18.0 build
corepack pnpm@10.18.0 preview    # concurso en http://127.0.0.1:4180 y track en :4182; F, pantalla completa
```

El del track usa planos e IFC del 80V01 que no están en Git; ver
[`pitch/track/README.md`](track/README.md).

Si cambias una cifra o un texto, edita el archivo de contenido de esa presentación y vuelve a
exportar. Las diapositivas del `.pptx` son imágenes: no se editan en PowerPoint.

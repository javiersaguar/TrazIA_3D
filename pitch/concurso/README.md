# Pitch final · TrazIA-3D en 3 minutos

Presentación para la final de IndesIAhack 2026, ante un jurado de dirección y tecnología.
Abre con el equipo y cuenta TrazIA-3D como producto: el problema, por qué es difícil, cómo lo
resolvemos, pruebas con planos reales, benchmarks (cotas inventadas, aprobación automática y coste de
IA, cada uno con una cifra y su gráfica) y en qué nos diferenciamos, en cuatro escenas animadas con el cierre.
Termina con la hoja 9: el vídeo de la interfaz (34 s, sin audio) a toda la lámina, que arranca solo.

El vídeo no está en Git (61 MB): cópialo en `public/local/interfaz.mp4` antes de presentar o
exportar. Sin él, la hoja 9 avisa de que falta y el `.pptx` sale sin ese vídeo. Es independiente del pitch del track (`pitch/track`), que va dirigido a los
ingenieros de Técnicas Reunidas.

Cada lámina es un plano GA: un marco de dibujo y un cajetín con la hoja, la revisión y el
cliente. La portada lleva también el logo de Multiplica, que apoya al jurado del reto. Las cifras
se dibujan como cotas. La portada lee el IFC sintético del V-101 y mide su altura desde la geometría.

## Presentar

Desde esta carpeta, con Node.js 22.12 o posterior:

```powershell
corepack pnpm@10.18.0 install --frozen-lockfile
corepack pnpm@10.18.0 build
corepack pnpm@10.18.0 preview
```

Abre [127.0.0.1:4180](http://127.0.0.1:4180/) y pulsa **F** al empezar a hablar: pasa a
pantalla completa y arranca el reloj de 3:00. Una línea roja sobre el marco marca el ritmo
de cada hoja; el reloj se pone rojo si vas por detrás del guion.

| Acción | Tecla |
| --- | --- |
| Avanzar o retroceder | → ←, espacio o clic en la mitad derecha o izquierda |
| Pantalla completa y reloj | F |
| Pausar o reanudar el reloj | T |
| Guion de la hoja | N |
| Volver al principio y poner el reloj a cero | Inicio |

`?hoja=4` abre directamente una hoja.

## Exportar a PowerPoint

```powershell
corepack pnpm@10.18.0 export
```

Compila, captura cada hoja a 1920 × 1080 en su estado final y escribe
`salida/TrazIA-3D-pitch.pptx`, con el guion en las notas del orador. Usa el Google Chrome
del sistema; con Edge, `$env:PW_CHANNEL="msedge"`. El servidor temporal usa el puerto 4193
(`PUERTO_EXPORT` lo cambia). `salida/` no se sube a Git.

`export` genera también `salida/TrazIA-3D-guion.pdf`: cada hoja con su miniatura, su tiempo, el texto que
se dice y los datos y fuentes que no salen en la lámina. `corepack pnpm@10.18.0 guion` lo rehace solo.

Las diapositivas del `.pptx` son imágenes: para cambiar un texto, edita
[`src/content.js`](src/content.js) y vuelve a exportar.

### Animaciones en el PowerPoint

Cada hoja lleva encima su animación de entrada grabada en MP4: las cotas que se trazan, las cifras
que cuentan, el recipiente que se dibuja y las escenas de la última hoja. El vídeo arranca solo al entrar en
la hoja, se queda en su último fotograma y un clic o el mando pasan a la siguiente, con un fundido.
Debajo queda la captura final, que es lo que se ve si el programa no reproduce vídeo. Hay que
presentar con PowerPoint (F5); Google Slides no reproduce estos vídeos.

[`scripts/animaciones.mjs`](scripts/animaciones.mjs) graba cada hoja en tiempo real con Chrome, la
codifica en H.264 con WebCodecs y escribe el MP4, sin dependencias nuevas. Lo que dura cada
grabación está en `DURACION`: si una animación se alarga, súbelo ahí. Opciones de `exportar.mjs`:
`--sin-animaciones` (solo imágenes) y `--reusar-animaciones` (monta el `.pptx` con los vídeos de
`salida/animaciones/` sin volver a grabarlos).

Para añadir a mano un vídeo propio al final: Insertar › Vídeo › Este dispositivo, y en la pestaña
Reproducción, «Iniciar: automáticamente» y «Reproducir a pantalla completa».

## Cifras y fuentes

Todo el texto y las cifras están en [`src/content.js`](src/content.js), con su procedencia
al principio del archivo:

- Horas manuales: enunciado GA2MODEL, pág. 5.
- Lote real del 26/11 (`lote_a3_b2b1441`): `pitch/cifras-evento.js`, generado por
  `bench.cifras`. Solo agregados.
- Aprobación automática, 116 de 121: [docs/BENCH.md](../../docs/BENCH.md).
- Coste de visión, 86 llamadas: [docs/PLAN.md](../../docs/PLAN.md), sección 7.8.
- Dificultad: estudio 7 sobre planos **sintéticos**, rotulado así en la lámina.
- Benchmarks: aprobación automática con el lote real (61 %, 121 de 197; ver arriba), estudio 7
  sobre planos **sintéticos** ([docs/ESTUDIO.md](../../docs/ESTUDIO.md)) y la
  medición de modelos en Azure del 26/11 con recortes **sintéticos**
  (`pitch/track/src/model-benchmark.json`). Rotulados así en cada tarjeta.
- Escala 400 × 4: [docs/PITCH_ESCALA.md](../../docs/PITCH_ESCALA.md), extrapolación sintética.
- `TARIFA_HORA` (50 €/h) es una **hipótesis** para pasar horas a euros. Cámbiala ahí si el
  jurado o el mentor dan otra; todas las láminas se recalculan.

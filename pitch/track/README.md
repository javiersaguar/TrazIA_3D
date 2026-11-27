# Pitch del track · TrazIA-3D para los ingenieros de TR

Pitch del reto GA2MODEL para los ingenieros de Técnicas Reunidas. Recorre los seis bloques del enunciado (pág. 15): problema, entrada,
extracción, 3D, cambio, e impacto y escala. El enunciado los reparte en 6:00, pero la organización ha
confirmado 5:00, y en ellos entra la demo en vídeo: cortes en 0:00, 0:40, 1:05, 1:35, 2:10 y 2:45,
la demo de 3:30 a 4:52 y la hoja de cierre, «Gracias» con los logos de TrazIA-3D, Técnicas Reunidas
y Multiplica, hasta las 5:00. Las dos hojas de modelos van entre «futuro» y la demo, fuera de tiempo.

Presentan Javier y Miguel. El guion en PDF dice quién habla en cada hoja, cuándo pasa la palabra y
la narración de la demo segundo a segundo, con el reloj de la charla al lado.

Diseño con la identidad de Técnicas Reunidas: fondo blanco, pizarra `#5f7997`, aguamarina
`#74d1e0`, turquesa `#469ba9` y Kanit en pesos finos. Una línea aguamarina barre cada titular y
cada plano, como el lector sobre el documento. Los modelos 3D se leen en directo de su IFC:

- Portada y lámina 3D: el IFC que TrazIA-3D generó del 80V01 real, revisión 2.
- Lámina de cambios: el V-101 sintético de A a B. Lo nuevo sale por GUID y lo modificado, de las
  piezas que señala el delta. La lámina lo rotula como ejemplo sintético.

## Material del reto

Los planos y el IFC del 80V01 son datos de TR y no están en Git. `scripts/medios.mjs` los copia a
`public/local/`, también ignorada, desde:

- `generated/pitch-medios/` (`plano-80v01.webp`, `plano-reto.webp`, `cita-80v01.webp`): el GA del
  80V01, el mismo plano marcado con las citas y el recorte de la cota de 5.700 mm;
- `generated/lote_a3_f61e613/80V01/rev2/modelo.ifc`, del lote local (`LOTE_TR` cambia el lote).

Si falta algo, la lámina usa el ejemplo sintético y lo rotula. `dev`, `build` y `export` ejecutan
`medios` antes.

## Vídeo de la demo

La hoja 11 es la grabación de la aplicación, a toda la lámina. Arranca sola al llegar a la hoja y se
queda en su último fotograma. No está en Git: copia el `.mp4` a mano en `public/local/demo.mp4`. Si
falta, la hoja lo dice. En el `.pptx` la hoja sale como imagen, sin el vídeo.

## Presentar y exportar

Desde esta carpeta, con Node.js 22.12 o posterior y Google Chrome:

```powershell
corepack pnpm@10.18.0 install --frozen-lockfile
corepack pnpm@10.18.0 export     # salida/TrazIA-3D-track.pptx y salida/TrazIA-3D-track-guion.pdf
corepack pnpm@10.18.0 build
corepack pnpm@10.18.0 preview    # http://127.0.0.1:4182, F para pantalla completa
```

| Acción | Tecla |
| --- | --- |
| Avanzar o retroceder | → ←, espacio o clic en la mitad derecha o izquierda |
| Pantalla completa | F |
| Pausar o reanudar el reloj | T |
| Guion de la hoja | N |
| Volver al principio | Inicio |

Arriba, en el centro, va el contador: el tiempo total frente a los 5:00 y lo que lleva la hoja
frente a lo previsto, en rojo si vais tarde. Arranca solo al pasar la primera hoja; T lo pausa e
Inicio lo pone a cero.

Todo el texto y las cifras están en [`src/content.js`](src/content.js), con su procedencia al
principio del archivo. Las fuentes y los matices van en el guion en PDF, no en las láminas.

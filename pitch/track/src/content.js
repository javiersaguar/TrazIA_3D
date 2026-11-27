// Pitch del track GA2MODEL para los ingenieros de Técnicas Reunidas. Único punto de edición.
//
// Los seis bloques del enunciado (pág. 15). El enunciado los reparte en 6:00, pero la organización
// ha confirmado 5:00, y en ellos entra la demo en vídeo con su narración: cortes en 0:00, 0:40,
// 1:05, 1:35, 2:10 y 2:45; la demo, de 3:30 a 4:52, y el cierre hasta las 5:00. Los dos anexos
// de modelos van entre «futuro» y la demo, fuera de tiempo. Presentan Javier y Miguel: `voz` dice quién
// habla en cada hoja y `narracion`, quién narra cada tramo de la demo. Procedencia de las cifras:
// - Horas manuales: enunciado GA2MODEL, pág. 5.
// - Campos del 80V01: generated/lote_a3_f61e613/80V01/rev2/revision.json (lote del 26/11).
// - Lote y oro: pitch/cifras-evento.js (bench.cifras) y docs/BENCH.md (bench.aprobacion).
// - Cambio real del 80V01 rev1 → rev2: trazia.revisions.compare sobre el mismo lote.
// - Cambio A → B del V-101: examples/ y web/public/demo/ifc/rev_a.ifc, rev_b.ifc. SINTÉTICO.
// - Modelos: docs/PLAN.md, 7.8.

export const deck = {
  proyecto: "TrazIA-3D",
  reto: "Reto GA2MODEL de Técnicas Reunidas",
  evento: "IndesIAhack 2026",
  equipo: ["Javier Saguar", "Iria Lozano", "Miguel Vera", "Alejandro Cuevas"],
};

export const capitulos = [
  { id: "problema", nombre: "Problema" },
  { id: "entrada", nombre: "Entrada" },
  { id: "extraccion", nombre: "Extracción" },
  { id: "modelo", nombre: "3D" },
  { id: "cambio", nombre: "Cambio" },
  { id: "impacto", nombre: "Impacto y escala" },
];

export const hojas = [
  {
    id: "portada",
    capitulo: "problema",
    titulo: "Portada",
    segundos: 15,
    voz: "Javier",
    lema: "Leemos el plano y la hoja de datos, generamos el IFC y cada cifra conserva su origen.",
    fuente: "A la izquierda, el GA real del 80V01, revisión 2. A la derecha, el IFC que TrazIA-3D generó de él en el lote del 26/11, leído en directo.",
    notas:
      "Somos TrazIA-3D. A la izquierda, el plano real del 80V01, uno de los equipos del reto; a la derecha, el IFC que hemos generado de él, en borrador. En cinco minutos: plano, dato, modelo, cambio y decisión.",
  },
  {
    id: "coste",
    capitulo: "problema",
    titulo: "Así se hace hoy",
    segundos: 25,
    voz: "Javier",
    factores: [
      { valor: "300–500", texto: "equipos por proyecto" },
      { valor: "3–5", texto: "revisiones de cada plano" },
      { valor: "2–4 h", texto: "de modelado por revisión" },
    ],
    horas: { min: 1800, max: 10000 },
    fuente: "Horas: estimación del enunciado GA2MODEL, pág. 5. No es una medida nuestra.",
    notas:
      "Hoy, un ingeniero lee el plano y la hoja de datos y vuelve a dibujar el equipo en 3D cada vez que cambia el plano. Según el enunciado: de trescientos a quinientos equipos por proyecto, de tres a cinco revisiones, de dos a cuatro horas cada una. Entre mil ochocientas y diez mil horas en redibujar. Queremos devolver ese tiempo; el de comprobar se queda.",
  },
  {
    id: "entrada",
    capitulo: "entrada",
    titulo: "Lo que leemos",
    segundos: 25,
    voz: "Javier",
    documentos: [
      { id: "GA", nombre: "Plano GA", paginas: "1 hoja" },
      { id: "HDM", nombre: "Hoja de datos", paginas: "11 páginas" },
    ],
    // Del 80V01 rev2, lote del 26/11 (revision.json): texto tal cual del documento, valor y cómo se obtuvo.
    lecturas: [
      { dato: "Material de virola", doc: "HDM, p. 1", texto: ["Shell & Heads:", "SA 240 Tp 304/304L"], valor: "SA 240 304/304L", como: "Leído" },
      { dato: "Diámetro exterior", doc: "GA", texto: ["ID Ø1900", "1655 x 10"], valor: "1.920 mm", como: "Calculado: ID + 2e" },
      { dato: "Boquilla N1", doc: "GA + HDM, p. 2", texto: ["N1 18\" 457 12 150#", "N1 1 18\" INLET 150# WN-RF"], valor: "18\" · 150# · Inlet", como: "Cruzado GA ↔ HDM" },
      { dato: "Soldaduras de virola", doc: "GA", texto: ["1655 x 10", "1980 x 10", "1965 x 10"], valor: "4 circunferenciales", como: "Deducido", revisar: true },
      { dato: "Silleta móvil", doc: "GA", texto: ["Section B-B ( 1 : 20 )"], valor: "230 mm", como: "Medido a escala", revisar: true },
      { dato: "Profundidad del fondo", doc: "GA", texto: ["Ellipsoidal head 2:1"], valor: "475 mm", como: "Supuesto: D/4", revisar: true },
    ],
    cierre: "Lo calculado guarda su cuenta. Lo supuesto se marca y va a revisión.",
    fuente:
      "80V01, revisión 2, lote del 26/11 (generated/lote_a3_f61e613/80V01/rev2/revision.json): texto original, regla y explicación de cada campo. Diámetro: ID 1.900 más dos espesores de virola de 10. Los textos de la columna «En el documento» están tal cual en GAD_80V01_rev2.pdf y HDM_80V01.pdf del dataset del reto. N1: fila de la tabla de boquillas del GA y fila de la HDM, página 2; tamaño, rating y servicio coinciden. Soldaduras: regla soldadura.virola_virola sobre la cadena de virolas, estado supuesto. Silleta móvil: regla ga.silleta_movil_medida_a_escala, contorno vectorial medido a 1:20 y contrastado con la cota entre anclajes. Fondo: 2:1 rotulado, profundidad D/4, supuesta. En ese plano quedan además 9 marcas de boquilla sin colocar, que van a revisión.",
    notas:
      "Leemos como lee quien dibuja. El material, de la hoja de datos. El diámetro exterior se calcula: el interior más dos espesores. La boquilla N1 se cruza entre la tabla del plano y la de la hoja de datos. La silleta se mide a escala y el fondo 2:1 se supone: eso va marcado, a revisión.",
  },
  {
    id: "cita",
    capitulo: "extraccion",
    titulo: "Cada cifra con su cita",
    segundos: 30,
    voz: "Javier",
    cita: {
      campo: "Longitud entre tangentes",
      valor: "5.700 mm",
      texto: "5700(T.L. To T.L.)",
      documento: "GA-80V01",
      pagina: 1,
      regla: "ga.distancia_tangentes",
      confianza: "0,85",
      // Zona medida sobre el recorte cita-80v01.webp.
      caja: { left: 34.8, top: 59.54, width: 10.05, height: 13.22 },
    },
    aceptados: { valor: 95.9, aciertos: 116, total: 121, resto: "66 de 76" },
    fuente:
      "La confianza 0,85 es la puntuación fija de la regla que encuentra el rótulo en el texto del PDF; no es una probabilidad calibrada. 116 de 121: bench.aprobacion frente a un oro manual elaborado aparte, en revisión, en 10 equipos del reto (docs/BENCH.md).",
    notas:
      "Cada cifra guarda su origen. Este 5.700 es la longitud entre tangentes: en el plano pone «5700, T.L. to T.L.», página 1, y la cita guarda el texto y la zona. Lo que no se puede citar, no entra. Frente a lo que un ingeniero sacó a mano de los mismos planos, de lo que el sistema acepta solo coinciden 116 de 121 datos, un 95,9 %. Lo dudoso va a la cola de revisión.",
  },
  {
    id: "modelo",
    capitulo: "modelo",
    titulo: "El plano pasa a 3D",
    segundos: 35,
    voz: "Miguel",
    leyenda: [
      { color: "#1f2a33", texto: "Cuerpo del equipo", de: "plano" },
      { color: "#e5484d", texto: "Líneas de cota", de: "plano" },
      { color: "#2fa84f", texto: "Boquillas y marcas de revisión", de: "plano" },
      { color: "#4aa8e8", texto: "Cita de una cota", de: "lectura" },
      { color: "#f29a38", texto: "Cita de la tabla de boquillas", de: "lectura" },
    ],
    cifras: [
      { valor: "23 de 26", texto: "revisiones del reto con su IFC" },
      { valor: "54 s", texto: "por revisión, en un portátil y sin red" },
    ],
    fuente: "Lote del 26/11 por la noche con el main f61e613 (generated/lote_a3_f61e613), sobre todo el dataset del reto, bombas y compresores incluidos: 14 equipos, 26 revisiones, 23 con IFC. No salen el tanque 62T02, revisiones 1 y 2 (falta el techo: tank.roof y roof_height), y el compresor GA2 rev0, que no cupo en memoria al ingerirlo. Mediana de 54,2 s por revisión con dos procesos a la vez en el portátil; el lote anterior, de 12 equipos y con otro reparto, dio 36,8 s.",
    notas:
      "A la izquierda, el GA real. Negro, rojo y verde venían en el dibujo: cuerpo, cotas y boquillas. El azul y el ámbar los pone nuestra lectura: la cita de una cota y la de la tabla de boquillas. De esas citas sale el modelo de la derecha, en borrador, sin que nadie vuelva a dibujar. En el reto, 23 de 26 revisiones salen con su IFC, en menos de un minuto cada una, en un portátil y sin red.",
  },
  {
    id: "cambio",
    capitulo: "cambio",
    titulo: "De A a B",
    segundos: 35,
    voz: "Miguel",
    sintetico: "V-101, ejemplo sintético",
    // Piezas que el delta A → B marca como modificadas (nombre en el IFC). Lo nuevo sale por GUID.
    modificados: ["V-101", "V-101/skirt", "V-101/N3", "V-101/nozzle-N3/flange"],
    cambios: [
      { campo: "Largo del cuerpo", antes: "6.000", despues: "6.500 mm", delta: "+500 mm" },
      { campo: "Altura del faldón", antes: "1.200", despues: "1.350 mm", delta: "+150 mm" },
      { campo: "Altura de la boquilla N3", antes: "3.500", despues: "3.700 mm", delta: "+200 mm" },
      { campo: "Boquilla N4", antes: "No estaba", despues: "Nueva", delta: "" },
    ],
    real: [
      { campo: "Pernos de anclaje", antes: "4 × M30", despues: "4 × M24" },
      { campo: "Boquilla K5", antes: "Estaba", despues: "Quitada" },
    ],
    fuente:
      "El 3D es el V-101 sintético, revisiones A y B, con los IFC de web/public/demo/ifc. El cambio real del 80V01 sale de comparar sus dos revisiones del lote del 26/11.",
    notas:
      "Cuando llega la revisión B no se rehace nada: comparamos dato a dato. Cada boquilla se reconoce por su marca: N3 sigue siendo N3 aunque suba 200 milímetros, y N4 aparece como nueva. Es el V-101, un ejemplo sintético, porque se ve bien en 3D. En el 80V01 real, de la revisión 1 a la 2, los pernos pasan de M30 a M24 y desaparece la boquilla K5. Cada pieza conserva su GUID y los cambios salen en BCF.",
  },
  {
    id: "arquitectura",
    capitulo: "impacto",
    titulo: "Cómo está hecho",
    segundos: 20,
    voz: "Miguel",
    lectores: ["Reglas", "OCR", "Caso parecido", "Memoria", "Geometría", "Visión IA"],
    casos: [
      { cifra: "5.700 mm", lector: 0 },
      { cifra: "N3", lector: 1 },
      { cifra: "Elevación", lector: 5 },
    ],
    salida: ["IFC en borrador", "Cambios en BCF", "Cola de revisión"],
    notas:
      "Cada dato recorre una cascada de lectores y se queda en el primero que lo resuelve: una regla, el OCR y, solo si ningún texto lo dice, un modelo de visión, con la cifra a revisar. Al final aprueba el ingeniero, con su nombre.",
  },
  {
    id: "futuro",
    capitulo: "impacto",
    titulo: "Más que un lector de planos",
    segundos: 25,
    voz: "Javier",
    ya: [
      { titulo: "Copiloto con citas", corto: "Pregunta y responde con la página del plano.", texto: "«¿De dónde sale la elevación de N3?» Responde con la página y la zona. Por voz o por texto." },
      { titulo: "Cambios dictados", corto: "Se dicta y queda en borrador para comprobar.", texto: "«Sube la boquilla N1 200 mm» se convierte en un borrador que el ingeniero comprueba." },
      { titulo: "Aprobación auditable", corto: "Si cambia un dato, la aprobación cae.", texto: "Quién aprobó y sobre qué datos. Si cambia un dato, la aprobación cae." },
      { titulo: "En vuestra nube", corto: "Azure de la organización o sin modelo externo.", texto: "Azure de la organización, o sin ningún modelo externo." },
    ],
    siguiente: [
      { titulo: "Entrada continua", texto: "Cada plano nuevo del gestor documental entra por una cola de eventos, tipo Kafka, y lanza su revisión." },
      { titulo: "Escala por página", texto: "Workers en paralelo y caché por página: solo se relee lo que cambió." },
      { titulo: "Más familias de equipos", corto: "Más familias de equipos de TR", texto: "Ampliar el catálogo con los equipos y planos de TR." },
      { titulo: "Ahorro medido", corto: "Ahorro medido con vuestros ingenieros", texto: "Cronometrar la revisión con ingenieros de TR para convertir el potencial en horas reales." },
    ],
    fuente:
      "Ya funciona: Copiloto, dictado y órdenes de cambio en docs/AYUDA_APP.md; aprobación ligada a la huella y auditoría en docs/AUDITORIA_REVISION.md; datos del reto solo en Azure OpenAI de la organización o modo sin modelo de lenguaje (AYUDA_APP, Privacidad). Lo siguiente es propuesta: la cola de eventos no existe hoy (el lote usa una cola local); la caché por página está medida en una secuencia sintética (docs/PITCH_ESCALA.md, 2/1/0/2 páginas releídas), no en producción; el tiempo de revisión con ingenieros de TR está sin medir.",
    notas:
      "Y no es solo un lector. El Copiloto responde citando de dónde sale cada número, y un cambio se puede dictar: queda en borrador para comprobar. La aprobación es auditable y los datos se quedan en vuestra nube. Lo siguiente: que los planos entren solos por una cola de eventos, más familias y medir el ahorro con vuestros ingenieros.",
  },
  {
    id: "modelos-vision",
    tarea: "vision",
    capitulo: null,
    anexo: true,
    titulo: "Anexo: lectura compleja",
    segundos: 0,
    fuente: "Datos de pitch/track/src/model-benchmark.json: medición sintética en Azure del 26/11, coste medio a precio de lista y latencia mediana. Lectura compleja: 20 recortes sintéticos y 76 valores evaluables; los cinco modelos se abstienen bien en los 4 campos ausentes. Sonnet 5.5: 76 de 76, 1,89 s y 0,002721 USD por tarea; Sol: 72 de 76, 2,96 s y 0,00216 USD. En la segunda prueba de citas localizadas, Sonnet 12 de 16 y Sol 8 de 16 (docs/PRUEBA_SONNET_IFC.md). Con datos del reto, Sonnet entra por Claude en Azure AI Foundry cuando se confirma su uso (TRAZIA_SONNET_DATOS_RETO=1); mientras tanto, abre GPT-6.1 Sol.",
    notas:
      "Anexo para las preguntas, fuera de los cinco minutos. El número lo pone una regla y lo cita; un modelo solo entra donde la regla no llega. Para elegir cuál, medimos cinco modelos en Azure con recortes sintéticos de lectura compleja: a la izquierda, acierto frente a coste por tarea; a la derecha, frente a tiempo. Ninguno da un valor erróneo. Elegimos Sonnet 5.5: acierta 76 de 76, es el más rápido y cuesta la mitad que Opus. Luna también acierta todo, pero tarda el triple. Si el despliegue de Sonnet cae, entra GPT-6.1 Sol.",
  },
  {
    id: "modelos-texto",
    tarea: "texto",
    capitulo: null,
    anexo: true,
    titulo: "Anexo: normalización corta",
    segundos: 0,
    fuente: "Datos de pitch/track/src/model-benchmark.json: medición sintética en Azure del 26/11, coste medio a precio de lista y latencia mediana. Normalización corta: 40 fragmentos sintéticos y 40 valores evaluables. Luna: 40 de 40 y 0,00007 USD por tarea; Opus 5.5: 39 de 40 y 0,00329 USD, 46 veces más.",
    notas:
      "Para las respuestas cortas, convertir una nota técnica en campo, valor y unidad, todos aciertan y el más barato basta: GPT-6 Luna, con 40 de 40. Opus 5.5 hace 39 de 40 y cuesta más de cuarenta veces más por tarea.",
  },
  {
    id: "demo",
    capitulo: null,
    titulo: "Demo",
    // 81,7 s de vídeo; después, la hoja de cierre.
    segundos: 82,
    // Grabación de la demo (Demo-TR.mp4). No está en Git: se copia a pitch/track/public/local/demo.mp4.
    video: "local/demo.mp4",
    fuente: "Grabación de la aplicación TrazIA-3D: 80V01 (plano GA real, subido como revisión 1) y BF-V-0016, revisiones 1 y 2, del dataset del reto.",
    // Narración en directo: segundos del vídeo. El vídeo arranca solo al entrar en la hoja.
    narracion: [
      { desde: 0, hasta: 4, voz: "Miguel", pantalla: "Portada e inicio de sesión", texto: "Esta es la aplicación. Entramos con nuestro usuario." },
      { desde: 4, hasta: 11, voz: "Miguel", pantalla: "Documentos", texto: "Los equipos del reto, por familias: recipientes, columnas y tanques. Cada uno con sus planos y su 3D." },
      { desde: 11, hasta: 20, voz: "Miguel", pantalla: "Subir planos", texto: "Subimos el plano GA del 80V01. Avisa de que ese archivo ya está en la revisión 1: no se duplica." },
      { desde: 20, hasta: 27, voz: "Miguel", pantalla: "Proceso", texto: "El proceso: recibe los planos, lee los datos, prepara el diseño y genera y comprueba el IFC." },
      { desde: 27, hasta: 38, voz: "Miguel", pantalla: "Plano y modelo del 80V01", texto: "Y este es el resultado: el plano junto a su modelo. Pulso una boquilla en el 3D y el plano señala de dónde sale." },
      { desde: 38, hasta: 41, voz: "Miguel", pantalla: "Vista explosionada", texto: "Separado, se ve cada pieza." },
      { desde: 41, hasta: 51, voz: "Miguel", pantalla: "Cola de revisión", texto: "Abajo, la cola de revisión. La longitud entre tangentes, 5.700, entró aprobada sola. La silleta 2 espera al ingeniero: aceptar, corregir o rechazar." },
      { desde: 51, hasta: 54, voz: "Miguel", pantalla: "Plano completo", texto: "Y el plano, con lo leído marcado." },
      { desde: 54, hasta: 60, voz: "Javier", pantalla: "BF-V-0016, revisión 2", texto: "Ahora otro equipo, el BF-V-0016, en su revisión 2." },
      { desde: 60, hasta: 69, voz: "Javier", pantalla: "Comparar versiones", texto: "Comparamos la revisión 1 con la 2: 41 cambios, y cada uno se ve en 3D, pieza a pieza." },
      { desde: 69, hasta: 73, voz: "Javier", pantalla: "Historial", texto: "En el historial, cada versión y quién cambió qué." },
      { desde: 73, hasta: 78, voz: "Javier", pantalla: "Copiloto", texto: "Y el Copiloto: le dictamos subir la boquilla A1 a 2.300 milímetros de elevación." },
      { desde: 78, hasta: 82, voz: "Javier", pantalla: "Editor del cambio", texto: "Se abre ya comprobado y en 3D; lo confirma el ingeniero." },
    ],
  },
  {
    id: "gracias",
    capitulo: null,
    titulo: "Gracias",
    segundos: 8,
    voz: "Javier",
    sinMarca: true,
    notas: "Quitamos el redibujado; el ingeniero comprueba y aprueba. Somos TrazIA-3D. Gracias.",
  },
];

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
// En la demo, las notas del orador son su narración, con el segundo del vídeo.
for (const h of hojas) {
  if (h.narracion) h.notas = h.narracion.map((n) => `${mmss(n.desde)} ${n.voz}: ${n.texto}`).join("\n");
}

export const totalSegundos = hojas.reduce((s, h) => s + h.segundos, 0);

/** Inicio y fin de cada capítulo, sumando los segundos de sus hojas. */
export function tiempos() {
  let t = 0;
  const por = {};
  for (const h of hojas) {
    if (!h.capitulo) continue;
    por[h.capitulo] ??= { desde: t, hasta: t };
    t += h.segundos;
    por[h.capitulo].hasta = t;
  }
  return por;
}

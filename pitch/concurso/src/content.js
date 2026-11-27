// Contenido del pitch final de TrazIA-3D (3 minutos). Único punto de edición del texto y las cifras.
//
// Procedencia de cada cifra:
// - Horas manuales: enunciado GA2MODEL, pág. 5 (300–500 equipos, 3–5 revisiones, 2–4 h).
// - Lote real: pitch/cifras-evento.js, generado por `bench.cifras` (lote_a3_b2b1441, 26/11).
// - Aprobación automática: docs/BENCH.md, `bench.aprobacion` sobre el mismo lote (116/121).
// - Coste de visión: docs/PLAN.md, 7.8 «Hecho 2» (86 llamadas, 0,50 USD a precio de lista en 4 revisiones).
// - Dificultad (vectorial/escaneado, alucinación de modelos externos): docs/ESTUDIO.md, estudio 7,
//   y docs/PREGUNTAS_JURADO.md. Son datos SINTÉTICOS y se rotulan así.
// - Escala 400 × 4: docs/PITCH_ESCALA.md, extrapolación de un lote sintético de 336 revisiones.
// - Modelos (hoja de benchmarks): pitch/track/src/model-benchmark.json, medición SINTÉTICA en Azure del 26/11.
// - Tarifa horaria: HIPÓTESIS editable, no es un dato de TR.

export const TARIFA_HORA = 50; // €/h, hipótesis para pasar horas a euros

const eur = (n) => new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, useGrouping: "always" }).format(n);

export const deck = {
  proyecto: "TrazIA-3D",
  reto: "Reto GA2MODEL de Técnicas Reunidas",
  evento: "IndesIAhack 2026",
  fecha: "27/11/2026",
  revision: "Final",
  duracion: 180,
  equipo: ["Javier Saguar", "Iria Lozano", "Miguel Vera", "Alejandro Cuevas"],
};

export const hojas = [
  {
    id: "equipo",
    titulo: "Equipo",
    segundos: 8,
    sinCajetin: true,
    notas: "Hola, somos TrazIA-3D: Javier, Iria, Miguel y Alejandro.",
  },
  {
    id: "portada",
    titulo: "Portada",
    segundos: 14,
    fuente: "El V-101 es un recipiente sintético. La presentación lee su IFC y mide la altura desde la geometría. Reto GA2MODEL de Técnicas Reunidas, con el apoyo de Multiplica. IndesIAhack 2026.",
    notas:
      "Este es el V-101, un recipiente sintético que el visor carga desde su IFC. Una planta industrial tiene cientos de equipos como este. Y todos empiezan igual: como un plano.",
  },
  {
    id: "problema",
    titulo: "El coste de redibujar",
    segundos: 24,
    factores: [
      { valor: "300–500", texto: "equipos por proyecto" },
      { valor: "3–5", texto: "revisiones de cada plano" },
      { valor: "2–4 h", texto: "de modelado manual por revisión" },
    ],
    horas: { min: 1800, max: 10000 },
    euros: { min: 1800 * TARIFA_HORA, max: 10000 * TARIFA_HORA },
    fuente: `Horas: enunciado GA2MODEL, pág. 5. Euros: ${TARIFA_HORA} €/h de ingeniería, una hipótesis nuestra, no un dato de Técnicas Reunidas.`,
    notas:
      `¿Qué pasa hoy? Un ingeniero mira el plano y vuelve a dibujar el equipo en 3D, a mano, cada vez que cambia. Por proyecto: de trescientos a quinientos equipos, de tres a cinco cambios por plano y de dos a cuatro horas cada vez. Hasta diez mil horas. A ${TARIFA_HORA} euros la hora, medio millón de euros por dibujar dos veces lo mismo.`,
  },
  {
    id: "dificil",
    titulo: "Por qué es difícil",
    segundos: 28,
    muros: [
      {
        titulo: "Ningún plano se parece a otro",
        cifra: "0,95 → 0,48",
        texto: "Calidad de lectura de un plano vectorial frente a uno mal escaneado, en planos sintéticos.",
      },
      {
        titulo: "La IA sola se inventa cotas",
        cifra: "8,6–11,4 %",
        texto: "Valores inventados por los mejores de seis modelos externos, en planos sintéticos.",
      },
      {
        titulo: "El plano cambia en cada revisión",
        cifra: "3–5",
        texto: "Revisiones por equipo. El modelo se actualiza: cada pieza conserva su identidad.",
      },
      {
        titulo: "Tiene que abrir en su software",
        cifra: "IFC4",
        texto: "Un estándar BIM estricto, con identificadores estables y validado.",
      },
    ],
    fuente: "Calidad de lectura y modelos externos: estudio 7 sobre planos sintéticos (docs/ESTUDIO.md).",
    notas:
      "¿Por qué nadie lo ha resuelto? Por cuatro motivos. No hay dos planos iguales: si uno está mal escaneado, la lectura cae a la mitad. La inteligencia artificial, sola, se inventa números: hasta uno de cada diez en los mejores modelos que probamos. Y un número inventado es una tubería que no encaja en obra. El plano cambia, y el modelo tiene que cambiar con él. Y todo debe abrirse en sus programas de diseño.",
  },
  {
    id: "como",
    titulo: "Cómo lo resolvemos",
    segundos: 28,
    fuente: "Los tres casos son reales del producto: 5.700 mm es la longitud entre tangentes del GA 80V01 rev. 2, escrita en el plano; N3 sale de una tabla de boquillas escaneada; la elevación de una boquilla sin cota escrita solo la propone la visión IA y queda para revisar.",
    entradas: ["Plano GA", "Hoja de datos", "Revisión anterior"],
    lectores: ["Reglas", "OCR", "Caso parecido", "Memoria", "Geometría", "Visión IA"],
    casos: [
      { cifra: "5.700 mm", campo: "Longitud entre tangentes", lector: 0 },
      { cifra: "N3", campo: "Tabla de boquillas escaneada", lector: 1 },
      { cifra: "Elevación", campo: "Boquilla sin cota escrita", lector: 5 },
    ],
    salidas: ["IFC en borrador", "Cada cifra con su cita", "Cambios en BCF"],
    firma: "El ingeniero aprueba con su nombre. Si cambia un dato, la aprobación caduca.",
    garantias: [
      "Cada cifra cita documento, página y zona del plano.",
      "La IA solo entra donde las reglas no llegan.",
      "Los planos no salen de la nube del cliente. Sin red, todo funciona en local.",
    ],
    notas:
      "Nuestra solución trabaja como un buen ingeniero: primero lee lo que está escrito. Si la medida está en el plano, la copia y apunta de dónde sale. Si la tabla está escaneada, la lee como una imagen. Solo cuando el plano no lo dice entra la inteligencia artificial, y ese número queda marcado para revisar. Sale el modelo 3D, con cada número enlazado al plano. Y al final firma una persona.",
  },
  {
    id: "pruebas",
    titulo: "Con planos reales",
    segundos: 28,
    kpis: [
      { valor: 37, sufijo: " s", texto: "por revisión, frente a 2–4 h de modelado manual", nota: "Mediana de 36,8 s" },
      { valor: 20, prefijo: "", sufijo: " de 24", texto: "revisiones reales con IFC, de 12 equipos y 0 errores", nota: "Las 4 restantes, a la espera de datos" },
      { valor: 95.9, decimales: 1, sufijo: " %", texto: "de lo que se acepta solo es correcto, frente a un oro manual", nota: "116 de 121 campos" },
      { valor: 0.13, decimales: 2, prefijo: "", sufijo: " $", texto: "de IA por revisión. Ninguna de 86 llamadas tuvo que escalar", nota: "Tokens a precio de lista" },
    ],
    fuente:
      "Lote del 26/11 sobre el dataset de Técnicas Reunidas, en un portátil y sin red. Oro manual elaborado aparte, en revisión. Coste de IA: lote de BF-V-0016 y 80V01 con Azure OpenAI.",
    notas:
      "Y no es una maqueta: son los planos reales de Técnicas Reunidas, en un portátil y sin internet. Cada revisión tarda unos treinta y siete segundos, frente a horas a mano. Veinte de veinticuatro salen con su modelo 3D, sin un solo error. De lo que el sistema aprueba él solo, el noventa y seis por ciento está bien. Y la inteligencia artificial cuesta trece céntimos de dólar por revisión.",
  },
  {
    id: "benchmarks",
    titulo: "Benchmarks",
    segundos: 28,
    titular: "Menos IA, mejor resultado.",
    tarjetas: [
      {
        valor: 0,
        desde: 11.4,
        decimales: 0,
        sufijo: " %",
        titulo: "cotas inventadas. La IA sola se inventa hasta 1 de cada 9.",
        datos: "Planos sintéticos · estudio 7",
        filas: [
          { etiqueta: "Mejores modelos externos, solos", rango: [8.6, 11.4], texto: "8,6–11,4 %" },
          { etiqueta: "Visión IA local, sola", valor: 7.3, texto: "7,3 %" },
          { etiqueta: "TrazIA-3D", valor: 0, texto: "0 %", nuestro: true },
        ],
      },
      {
        valor: 61,
        sufijo: " %",
        titulo: "de los datos se aprueban solos, con un 96 % de acierto.",
        datos: "Planos reales de TR · frente a un oro manual",
        reparto: { total: 197, solos: 121, bien: 116 },
      },
      {
        valor: 46,
        sufijo: "×",
        titulo: "menos coste de IA que usar el modelo más grande para todo.",
        datos: "Recortes sintéticos · Azure, 26/11 · precio de lista",
        tareas: [
          {
            tarea: "Leer una cota difícil",
            grande: { nombre: "Opus 5.5", usd: 0.005663, texto: "76/76 aciertos" },
            elegido: { nombre: "Sonnet 5.5", usd: 0.002721, texto: "76/76" },
            ahorro: "−52 %",
          },
          {
            tarea: "Normalizar un valor",
            grande: { nombre: "Opus 5.5", usd: 0.003288, texto: "39/40 aciertos" },
            elegido: { nombre: "GPT-6 Luna", usd: 0.0000709625, texto: "40/40" },
            ahorro: "46× menos",
          },
        ],
      },
    ],
    // Procedencia. Tarjeta 1: alucinación = valores sin respaldo en la región citada (docs/ESTUDIO.md,
    // estudio 7: 0 % en todas las estrategias elegibles; a_vision con Qwen3-VL 4B, 7,3 %, subconjunto de
    // 6 equipos; seis modelos externos, los mejores 8,6–11,4 %, docs/PREGUNTAS_JURADO.md).
    // Tarjeta 2: docs/BENCH.md, «Aprobación automática frente al oro de TR», lote_a3_b2b1441: 197 campos
    // juzgables de 10 equipos, 121 se aprobarían solos con umbral 0,8 (61 %), 116 de ellos correctos (95,9 %).
    // Tarjeta 3: pitch/track/src/model-benchmark.json (Azure, 26/11, recortes sintéticos, coste medio por tarea).
    fuente:
      "Cotas inventadas, planos sintéticos: valores que no están en la zona del plano que citan; 0 % en las estrategias elegibles del estudio 7 (docs/ESTUDIO.md). Visión IA local: Qwen3-VL 4B como lector único, subconjunto de 6 equipos, 7,3 % y 172 s por revisión. Modelos externos: seis probados solo con sintéticos, los mejores entre 8,6 % y 11,4 % (docs/PREGUNTAS_JURADO.md). Aprobación automática: datos reales, lote del 26/11 (lote_a3_b2b1441) frente a un oro manual elaborado aparte, en revisión (docs/BENCH.md, bench.aprobacion). De 197 datos juzgables de 10 equipos, 121 superan el umbral de 0,8 y se aprobarían solos (61 %); 116 coinciden con el oro (95,9 %). Los 5 fallos: capacidad de BF-C-0003 en la hoja de datos (2) y la regla del faldón (3). De los 76 que van a la persona, 66 eran correctos. Modelos: medición en Azure del 26/11 con recortes sintéticos, coste medio por tarea a precio de lista (pitch/track/src/model-benchmark.json). Lectura compleja: Sonnet 5.5, 76 de 76 y 0,00272 USD, frente a Opus 5.5, 76 de 76 y 0,00566 USD. Normalización corta: GPT-6 Luna, 40 de 40 y 0,00007 USD, frente a Opus 5.5, 39 de 40 y 0,00329 USD. Ningún modelo dio un valor erróneo; Luna también acierta 76 de 76 en lectura compleja, pero tarda 6 s frente a 1,9 s.",
    notas:
      "Lo sorprendente: cuanta menos inteligencia artificial, mejor resultado. Uno: cero números inventados, porque lo que no se puede señalar en el plano no entra. Dos: con planos reales, seis de cada diez datos se aprueban solos, y casi todos coinciden con los de un ingeniero. Lo dudoso va a una persona. Tres: cada tarea va al modelo justo, y para lo sencillo uno pequeño acierta igual y cuesta cuarenta y seis veces menos.",
  },
  {
    id: "diferencia",
    titulo: "En qué nos diferenciamos",
    segundos: 22,
    escenas: [
      { id: "cita", titulo: "Cada cifra, con su cita", texto: "Documento, página y zona del plano. Lo que no se puede citar no entra." },
      { id: "cambio", titulo: "Revisiones sin redibujar", texto: "La revisión B actualiza el modelo. Cada pieza conserva su identidad." },
      { id: "voz", titulo: "Se habla con el modelo", texto: "Un cambio dictado queda en borrador para comprobar." },
      { id: "firma", titulo: "Una firma que caduca", texto: "El ingeniero aprueba con su nombre. Si cambia un dato, la aprobación cae." },
    ],
    cierre: "Nadie vuelve a dibujar un plano a mano.",
    cierre2: "La máquina lee y cita. El ingeniero revisa y firma.",
    fuente:
      "Cita: longitud entre tangentes del GA 80V01 rev. 2, 5.700 mm, regla ga.distancia_tangentes. Revisión A → B: V-101, ejemplo sintético (web/public/demo/ifc/rev_a.ifc y rev_b.ifc); N3 sube 200 mm y conserva su GUID, N4 es nueva; los cambios salen en BCF. Voz: Copiloto y órdenes de cambio por voz o por texto (docs/AYUDA_APP.md); la elevación de N1 del 80V01 es 2.580 mm. Firma: aprobación ligada a la huella de los datos (docs/AUDITORIA_REVISION.md).",
    notas:
      "¿Qué nos hace distintos? Cada número dice de qué plano y de qué página sale. Cuando el plano cambia, el modelo se actualiza solo, sin redibujar nada. Se le pueden pedir cambios hablando. Y la firma del ingeniero caduca en cuanto alguien toca un dato. La máquina lee y cita; el ingeniero revisa y firma.",
  },
  {
    id: "interfaz",
    titulo: "La interfaz",
    segundos: 34,
    sinCajetin: true,
    // Vídeo de la interfaz grabado por Javier (27/11): 34 s, 2560 × 1440, sin audio. No está en Git:
    // se copia a pitch/concurso/public/local/interfaz.mp4.
    video: "local/interfaz.mp4",
    fuente: "Grabación de la aplicación TrazIA-3D: portada, inicio de sesión, proyectos y la planta marina SIM-MAR, rotulada como datos sintéticos, con su plano, su lista de equipos y el modelo 3D.",
    notas: "Y así se ve funcionando. Entramos, elegimos un proyecto, aquí una planta de ejemplo con datos inventados, y tenemos el plano al lado de su modelo 3D. Cada dato nos lleva a su sitio en el plano. Nadie vuelve a dibujar un plano a mano. Somos TrazIA-3D. Gracias.",
  },
];

export const totalSegundos = hojas.reduce((s, h) => s + h.segundos, 0);
export { eur };

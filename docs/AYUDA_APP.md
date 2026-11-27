# Ayuda de TrazIA-3D

Guía breve de uso. El Copiloto la consulta para responder preguntas sobre cómo se hace algo en la
aplicación. Si cambia un flujo de la interfaz, se actualiza aquí.

## Qué es TrazIA-3D

TrazIA-3D convierte los planos de disposición general (GA) y las hojas de datos de un equipo en un
modelo IFC. Cada valor que lee lleva su unidad, el documento y la página de donde sale y su
confianza. Todo lo que genera la máquina es un borrador (DRAFT): solo una persona revisa, corrige y
aprueba.

## Estrategias de lectura A, B, C y D

TrazIA-3D compara cuatro maneras de leer un plano. Todas pasan por el mismo postproceso:
normalización de unidades, contrato de datos, familia paramétrica e IFC.

- **A · visión:** un modelo de visión lee el plano como una imagen.
- **B · reglas:** lee el texto, las tablas, las cotas, el cajetín, la hoja de datos y la tabla
  VESOR con reglas deterministas. Si el PDF no tiene capa de texto, trabaja sobre el OCR.
- **C · recuperación (RAG):** busca equipos parecidos ya leídos y adapta sus parámetros.
- **D · híbrido:** combina varios canales (reglas, geometría, memoria de revisiones aprobadas,
  recuperación, visión y detector) y decide cada campo con una fusión aprendida por regresión
  logística. Es la estrategia por defecto. La memoria solo usa revisiones aprobadas cuya huella
  coincide con sus datos.

El estudio comparativo mide las cuatro con los mismos casos y publica sus resultados en
docs/ESTUDIO.md.

## Apartados

- **Documentos:** lista los equipos del dataset, sus planos y su estado. Desde aquí se suben planos
  nuevos con «Subir planos» y se lanzan con «Procesar documentos».
- **Modelo:** reúne la revisión de la evidencia, la comparación entre revisiones y el visor del IFC.
  Se elige el equipo en el selector «Equipo» de la barra superior y la revisión en el selector
  «Revisión».
- **Proceso:** muestra las etapas y los eventos de cada ejecución del pipeline, con su procedencia.
- **Ajustes:** estrategia por defecto, conexión con la API, apariencia, perfil y modelo de lenguaje
  del Copiloto.
- **Lotes y Métricas:** solo para administración. Lotes procesa el dataset y exporta con la huella
  de los datos. Métricas muestra trabajos, etapas, modelos de lenguaje y lotes.

## Subir y procesar planos

1. Abre Documentos y pulsa «Subir planos».
2. Añade los PDF del plano GA y, si las hay, las hojas de datos en Excel o PDF.
3. Pulsa «Procesar documentos». El avance por etapas se ve en Proceso.
4. Al terminar, el equipo aparece con una revisión nueva en estado DRAFT.

## Revisar campos

En Modelo, vista Revisión, cada campo muestra su valor, su unidad y la cita del original. Atajos de
teclado:

- J y K: campo siguiente y anterior.
- A: aceptar el valor.
- E: corregir el valor.
- S: marcar como supuesto.
- Ctrl+Z: deshacer la última acción.
- F: pantalla completa de la vista bajo el cursor; Esc para salir.
- ?: ver todos los atajos. Ctrl+K: menú de comandos.

Al abrir una cita se ve la página y la región del plano de donde sale el valor.

## Aprobar una revisión

Para aprobar hace falta haber revisado los campos y verificado los originales por SHA-256. El botón
de aprobación abre un diálogo donde se registra quién revisa; «Guardar aprobación» vincula la
aprobación a la huella de los datos. Cualquier cambio posterior en los datos invalida esa
aprobación y hay que volver a aprobar.

## Comparar revisiones

En Modelo, vista Cambios, se comparan dos revisiones del mismo equipo. Se ven los campos que cambian
con su valor antes y después. Con la barra espaciadora se reproducen o pausan los cambios en 3D.

## Descargar el IFC

El visor de Modelo lee la geometría del IFC. Mientras la revisión no esté aprobada, la descarga es
«Descargar IFC en borrador». Una revisión aprobada exporta el IFC vinculado a su huella.

## Copiloto

El Copiloto lee la revisión activa y responde con citas a sus fuentes. No cambia ni aprueba nada.

- **Preguntar:** escribe la pregunta y pulsa «Preguntar» o Intro. Ejemplos: «¿cuál es el diámetro
  interior?», «¿de dónde sale la elevación de N3?», «¿qué cambia respecto a la revisión anterior?»,
  «¿está aprobada esta revisión?».
- **Escuchar respuesta:** lee en voz alta la respuesta con la voz del navegador.
- **Dictar:** transcribe lo que dices en la caja del mensaje para que lo revises antes de enviarlo.
- **Hablar por voz:** conversación manos libres. El Copiloto escucha, envía la pregunta cuando
  haces una pausa de 3 segundos, responde en voz alta y deja el diálogo escrito en el chat.
  «Pausar» detiene el micrófono y «Volver a texto» regresa al chat.
- **Dictar un cambio:** convierte una orden de diseño en un borrador que se abre en el editor.

## Órdenes de cambio por voz o por texto

Una orden indica el elemento, la magnitud y el valor final. Fórmulas que funcionan:

- «Cambia la elevación de la boquilla N3 a 650 mm».
- «Sube la boquilla N1 200 mm».
- «Gira N2 a 45 grados».
- «Cambia el diámetro a 2100 mm».

Se puede citar el valor actual si se dice como tal: «…a 650 mm, actualmente está en 660 mm» o «a
650 mm en vez de 660 mm». Si la orden da dos valores finales posibles, el Copiloto pide uno solo.
La propuesta se revisa con «Abrir en el editor» y «Comprobar cambios», y se guarda como DRAFT.

## Dictado en español

El dictado en el dispositivo usa el paquete de español del navegador. Si falta, aparece «Instalar
dictado en español»; mientras se descarga, «Comprobar dictado» vuelve a mirar si ya está listo.

## Privacidad

Los datos del reto solo se envían al servicio de Azure OpenAI de la organización. Groq solo recibe
datos sintéticos. En Ajustes se puede elegir «Sin modelo de lenguaje»; entonces el Copiloto responde
solo con la evidencia indexada y no envía nada fuera.

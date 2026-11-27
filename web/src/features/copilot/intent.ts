/** Comparte el enrutado del mensaje entre chat, dictado y conversación por voz. */
const verbs = /^(?:sub[aei]|baj[ae]|muev[ae]|mov[ei]|desplaz|cambi|modific|p[oó]n|pong|pon[eg]|fij|dej|añad|agreg|quit|elimin|borr|gi[r]|rot|aument|reduc|ampl[ií]|acort|alarg|sustituy|reemplaz|ajust|establec|prepar|propon|elev|recort)[a-záéíóú]*\b/i;
// Muletillas del habla al principio: «vale,», «perfecto», «más o menos».
const fillers = /^(?:(?:vale|venga|perfecto|bueno|bien|ok|okey|oye|mira|pues|entonces|genial|de acuerdo|m[aá]s o menos|por favor|copiloto|s[ií])\b[\s,.:;!¡]*)+/i;
// Fórmulas que introducen la orden: «podemos cambiar», «quiero que cambies», «vamos a subir».
const modals = /^(?:(?:puedes|podr[ií]as|podemos|podr[ií]amos|quiero|quisiera|queremos|necesito|necesitamos|me gustar[ií]a|vamos a|hay que|tienes que|tenemos que|deber[ií]amos|habr[ií]a que)\s+(?:que\s+)?)+/i;
const question = /^(?:qu[eé]|cu[aá]l|c[oó]mo|d[oó]nde|por qu[eé]|cu[aá]nt|qui[eé]n)\b/i;

export function isChangeRequest(text: string) {
  const clean = text.trim().replace(/^[¿¡"«]+/, "");
  const plain = clean.replace(fillers, "");
  if (question.test(plain)) return false;
  const request = plain.replace(modals, "");
  if (/^(?:ponte\b|cambia\s+de\s+(?:revision|revisión|vista|equipo))/i.test(request)) return false;
  if (verbs.test(request.replace(/^no\s+/i, ""))) return true;
  // «Hacer un cambio de ese valor», «aplica el cambio a 650 mm».
  if (/^(?:hacer|haz|hagamos|realiza|realizar|aplica|aplicar|prepara|preparar)\s+(?:me\s+)?(?:un|el|este|ese)\s+cambio\b/i.test(request)) return true;
  if (/(?:[,\s]|^)(?:c[aá]mbial[oa]|modif[ií]cal[oa]|aj[uú]stal[oa]|ponl[oa])(?:[.!?¡¿]|$)/i.test(request)) return true;
  return /^(?:quiero|necesito|me gustar[ií]a)\s+que\b/i.test(plain)
    && /\b(?:sea|mida|tenga|quede|est[eé])\s+(?:de\s+)?(?:[+-]?\d|cero\b|un[oa]?\b|dos\b|tres\b|cuatro\b|cinco\b|seis\b|siete\b|ocho\b|nueve\b|diez\b|cien\b|mil\b)/i.test(request);
}

const fold = (text: string) => text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const ordinals = [/\b(?:primer[oa]?|uno)\b/, /\b(?:segund[oa]|dos)\b/, /\b(?:tercer[oa]?|tres)\b/, /\b(?:cuart[oa]|cuatro)\b/];

/**
 * Una opción como «lado +Y» no se puede dictar: el reconocimiento escribe «lado y» o «lado guión y».
 * Se pide con palabras («lado positivo») y la respuesta se lee como esa palabra, el signo o el orden.
 */
export function speakableOption(option: string) {
  return option.replace(/\+\s*[a-z]\b/i, "positivo").replace(/[-−]\s*[a-z]\b/i, "negativo");
}

export function spokenOption(said: string, options: string[]): string | null {
  if (!options.length) return null;
  const text = ` ${fold(said).replace(/[«»"¿?¡!.,;:]/g, " ")} `;
  const exact = options.filter(option => text.includes(` ${fold(speakableOption(option))} `) || text.includes(` ${fold(option)} `));
  if (exact.length === 1) return exact[0] ?? null;
  const plus = options.filter(option => option.includes("+"));
  const minus = options.filter(option => /[-−]\s*[a-z]/i.test(option));
  const positive = /\s(?:positiv[oa]|mas|\+)/.test(text);
  const negative = /\s(?:negativ[oa]|menos|guion|-)/.test(text);
  if (positive !== negative && plus.length === 1 && minus.length === 1) return (positive ? plus[0] : minus[0]) ?? null;
  const heard = ordinals.filter(pattern => pattern.test(text));
  const ordinal = heard.length === 1 ? ordinals.findIndex(pattern => pattern.test(text)) : -1;
  return ordinal >= 0 ? options[ordinal] ?? null : null;
}

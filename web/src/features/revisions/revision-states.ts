const TEAM = [
  "Javier Saguar Antona",
  "Iria Lozano Carrasco",
  "Miguel Vera del Castillo",
  "Alejandro Cuevas Cid",
] as const;

const STATES = [
  { title: "Modelo de partida", summary: "IFC de referencia de cada equipo." },
  { title: "Ajuste de una pieza", summary: "Se desplaza una conexión o se ajusta la altura de un fondo o cubierta." },
  { title: "Ajuste de apoyos", summary: "Se eleva el equipo 120 mm mediante el apoyo o un zócalo." },
  { title: "Detalle de montaje", summary: "Se incorpora una tuerca de brida o una placa de identificación." },
  { title: "Refuerzo local", summary: "Se incorpora una cartela o un refuerzo en la zona de apoyo." },
] as const;

export function hash(text: string) {
  let value = 2166136261;
  for (const char of text) value = Math.imul(value ^ char.charCodeAt(0), 16777619);
  return value >>> 0;
}

export function revisionsFor(project: string) {
  const start = hash(project) % TEAM.length;
  return STATES.map((state, index) => ({
    ...state,
    index,
    label: index ? `SIM-0${index}` : "Base IFC",
    author: index ? TEAM[(start + index - 1) % TEAM.length]! : null,
  }));
}

export type RevisionState = ReturnType<typeof revisionsFor>[number];

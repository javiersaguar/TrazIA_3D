/*
  Clases de equipo usadas en listas de equipos de planta (EPC): el código que
  gobierna el aparato, no el nombre comercial. Sirve para agrupar el dataset
  y el catálogo de familias con la misma lista.
*/

export type EquipmentClass = {
  id: string;
  title: string;
  standard: string;
  keys: readonly string[];
};

export const EQUIPMENT_CLASSES: readonly EquipmentClass[] = [
  {
    id: "pressure",
    title: "Recipientes a presión",
    standard: "ASME BPVC VIII",
    keys: ["vertical", "horizontal", "vertical_vessel", "horizontal_vessel", "Recipiente vertical", "Recipiente horizontal", "filter"],
  },
  {
    id: "columns",
    title: "Columnas",
    standard: "ASME VIII · destilación y absorción",
    keys: ["column", "Columna"],
  },
  {
    id: "tanks",
    title: "Tanques de almacenamiento",
    standard: "API 650",
    keys: ["tank", "Tanque"],
  },
  {
    id: "heat",
    title: "Transferencia de calor",
    standard: "TEMA · API 660 / API 661 · CTI",
    keys: ["exchanger", "Intercambiador", "air-cooler", "evaporator", "cooling-tower"],
  },
  {
    id: "rotating",
    title: "Equipos rotativos",
    standard: "API 610 · API 617",
    keys: ["pump", "Bomba", "compressor", "Compresor", "centrifuge"],
  },
  {
    id: "separation",
    title: "Separación y sólidos",
    standard: "Equipos de proceso · ASME VIII",
    keys: ["cyclone", "dryer", "mixer-settler"],
  },
  {
    id: "packages",
    title: "Paquetes y líneas especiales",
    standard: "Paquetes de proceso",
    keys: ["static-mixer", "dosing-skid"],
  },
];

export const UNCLASSIFIED: EquipmentClass = {
  id: "other",
  title: "Envolventes y sin clasificar",
  standard: "Geometría de apoyo, sin código de equipo",
  keys: ["generic", "Genérico"],
};

const BY_KEY = new Map<string, EquipmentClass>();
for (const cls of [...EQUIPMENT_CLASSES, UNCLASSIFIED]) {
  for (const key of cls.keys) BY_KEY.set(key, cls);
}

export function classOf(key: string | null | undefined): EquipmentClass {
  if (!key) return UNCLASSIFIED;
  return BY_KEY.get(key) ?? UNCLASSIFIED;
}

/** Unifica la clave del lote (`vertical_vessel`), la etiqueta de la API y el id del catálogo. */
const ALIAS: Record<string, string> = {
  vertical: "vertical",
  vertical_vessel: "vertical",
  "Recipiente vertical": "vertical",
  horizontal: "horizontal",
  horizontal_vessel: "horizontal",
  "Recipiente horizontal": "horizontal",
  column: "column",
  Columna: "column",
  tank: "tank",
  Tanque: "tank",
  exchanger: "exchanger",
  Intercambiador: "exchanger",
  pump: "pump",
  Bomba: "pump",
  compressor: "compressor",
  Compresor: "compressor",
  generic: "generic",
  Genérico: "generic",
};

export function familyKey(raw: string | null | undefined): string {
  if (!raw) return "";
  return ALIAS[raw] ?? raw;
}

export function sameFamily(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  if (a === b) return true;
  if (EQUIPMENT_CLASSES.some((cls) => cls.id === a) || a === UNCLASSIFIED.id) return classOf(b).id === a;
  return familyKey(a) === familyKey(b);
}

export function groupByClass<T>(items: T[], key: (item: T) => string | null | undefined): { cls: EquipmentClass; items: T[] }[] {
  const buckets = new Map<string, T[]>();
  for (const item of items) {
    const cls = classOf(key(item));
    buckets.set(cls.id, [...(buckets.get(cls.id) ?? []), item]);
  }
  return [...EQUIPMENT_CLASSES, UNCLASSIFIED]
    .filter((cls) => buckets.has(cls.id))
    .map((cls) => ({ cls, items: buckets.get(cls.id) ?? [] }));
}

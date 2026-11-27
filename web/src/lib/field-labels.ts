/**
 * Nombre legible de cada campo del contrato, igual en toda la web.
 *
 * Norma: frase en español con mayúscula inicial. Un campo de una pieza repetida se nombra
 * «Pieza marca · magnitud» (p. ej. «Boquilla M1 · Elevación», «Virola V03 · Espesor»).
 * Una ruta que no está en la tabla se nombra a partir de sus partes, nunca en bruto.
 */

const DIRECTOS: Record<string, string> = {
  tag: "Tag del equipo",
  diameter: "Diámetro de la virola",
  height: "Longitud entre tangentes",
  head_depth: "Profundidad del fondo",
  skirt_height: "Altura del faldón",
  skirt_thickness: "Espesor del faldón",
  "legs.height": "Altura de las patas",
  "legs.count": "Número de patas",
  "horizontal.diameter": "Diámetro de la virola",
  "horizontal.length": "Longitud entre tangentes",
  "horizontal.head_depth": "Profundidad del fondo",
  "horizontal.support_height": "Altura de la silleta al eje",
  "horizontal.saddle_width": "Ancho de silleta",
  "horizontal.saddle_span": "Ancho transversal de silleta",
  "tank.diameter": "Diámetro del tanque",
  "tank.height": "Altura de la envolvente del tanque",
  "tank.roof": "Tipo de techo",
  "tank.roof_height": "Flecha del techo",
};

/** Magnitudes, comunes a todas las piezas. */
const MAGNITUDES: Record<string, string> = {
  azimuth: "Orientación",
  bearing: "Rumbo",
  code: "Código",
  count: "Número",
  development: "Desarrollo",
  diameter: "Diámetro",
  elevation: "Elevación",
  elevation_mm: "Elevación",
  facing: "Cara de brida",
  flange_type: "Tipo de brida",
  height: "Altura",
  joins: "Piezas que une",
  kind: "Tipo",
  material: "Material",
  order: "Orden de abajo arriba",
  projection: "Proyección",
  projection_basis: "Referencia de la proyección",
  rating: "Clase de brida",
  schedule: "Schedule",
  service: "Servicio",
  size_nps: "Tamaño nominal",
  station: "Posición",
  thickness: "Espesor",
  value: "Valor",
};

const ATRIBUTOS: Record<string, string> = {
  anchor_bolts: "Pernos de anclaje",
  body_flange_thickness: "Espesor de la brida de cuerpo",
  capacity: "Capacidad",
  capacity_working: "Capacidad de trabajo",
  cog_elevation: "Elevación del centro de gravedad",
  column_head_depth_bottom: "Profundidad del fondo inferior",
  column_head_depth_top: "Profundidad del fondo superior",
  cog_elevation_operating: "Elevación del centro de gravedad en operación",
  corrosion_allowance: "Sobreespesor de corrosión",
  design_pressure: "Presión de diseño",
  design_temperature: "Temperatura de diseño",
  diameter_basis: "Referencia del diámetro",
  equipment_type: "Tipo de equipo",
  head_straight_flange: "Faldilla recta del fondo",
  heads_thickness: "Espesor de los fondos",
  height_to_flange: "Altura de tangente a cara de brida",
  hydrotest_pressure: "Presión de prueba hidráulica",
  insulation: "Aislamiento",
  insulation_thickness: "Espesor del aislamiento",
  material: "Material",
  material_body_flange: "Material de la brida de cuerpo",
  material_heads: "Material de los fondos",
  material_nozzle_flanges: "Material de las bridas de boquilla",
  material_shell: "Material de la virola",
  material_skirt: "Material del faldón",
  mawp: "Presión máxima admisible (MAWP)",
  mdmt: "Temperatura mínima de diseño (MDMT)",
  operating_pressure: "Presión de operación",
  operating_temperature: "Temperatura de operación",
  operating_weight: "Peso en operación",
  pwht: "Tratamiento térmico postsoldadura",
  saddle_width_fixed: "Ancho de la silleta fija",
  saddle_width_sliding: "Ancho de la silleta deslizante",
  shell_height: "Altura de la virola",
  shell_thickness: "Espesor de la virola",
  shell_thicknesses: "Espesores de virola",
  skirt_diameter: "Diámetro del faldón",
  skirt_thickness: "Espesor del faldón",
  support: "Tipo de soporte",
  support_height_basis: "Referencia de la altura de silleta",
  upper_closure: "Cierre superior",
  weight_empty: "Peso en vacío",
  weight_fabrication: "Peso de fabricación",
  weight_full: "Peso lleno de agua",
  weight_operating: "Peso en operación",
  weight_test: "Peso en prueba",
  weight_transport: "Peso de transporte",
};

/** Piezas repetidas: prefijo de la ruta → nombre de la pieza. */
const PIEZAS: [RegExp, (marca: string) => string][] = [
  [/^nozzles\.([^.]+)\.(.+)$/, (m) => `Boquilla ${m}`],
  [/^welds\.([^.]+)\.(.+)$/, (m) => `Soldadura ${m.replace(/^W:/, "").replace("|", " – ")}`],
  [/^shell\.courses\.([^.]+)\.(.+)$/, (m) => `Virola ${m}`],
  [/^column\.sections\.([^.]+)\.(.+)$/, (m) => `Tramo de columna ${m}`],
  [/^tank\.courses\.([^.]+)\.(.+)$/, (m) => `Virola ${m} del tanque`],
  [/^horizontal\.saddle_positions\.(\d+)()$/, (m) => `Silleta ${Number(m) + 1}`],
  [/^envelope\.(origin|size)\.([xyz])$/, (m) => (m === "origin" ? "Origen" : "Dimensión")],
];

const humano = (texto: string) => {
  const limpio = texto.replace(/[_-]+/g, " ").trim();
  return limpio ? limpio.charAt(0).toUpperCase() + limpio.slice(1) : texto;
};

const magnitud = (clave: string) => MAGNITUDES[clave] ?? humano(clave);

export function fieldLabel(path: string): string {
  const directo = DIRECTOS[path];
  if (directo) return directo;
  if (path.startsWith("attributes.")) {
    const clave = path.slice("attributes.".length);
    return ATRIBUTOS[clave] ?? humano(clave);
  }
  for (const [patron, pieza] of PIEZAS) {
    const partes = patron.exec(path);
    if (!partes) continue;
    const marca = partes[1] ?? "";
    const resto = partes[2] ?? "";
    if (path.startsWith("horizontal.saddle_positions.")) return `${pieza(marca)} · Posición`;
    if (path.startsWith("envelope.")) return `${pieza(marca)} ${resto.toUpperCase()}`;
    return `${pieza(marca)} · ${magnitud(resto.split(".").at(-1) ?? resto)}`;
  }
  const partes = path.split(".");
  const ultima = partes.at(-1) ?? path;
  return partes.length > 1 ? `${humano(partes[0] ?? "")} · ${magnitud(ultima)}` : magnitud(ultima);
}

import type { ReviewField } from "@/lib/mock/fields";
import { parentElementId } from "./semantic";
import type { Annotation } from "./types";

const shellDimensions = new Set(["diameter", "height", "attributes.shell_height", "horizontal.diameter", "horizontal.length"]);
const nozzleDimensions = new Set(["diameter", "elevation", "projection", "azimuth", "position.x"]);
const ruleOf = ({ source }: ReviewField) => "rule" in source && typeof source.rule === "string" ? source.rule : "";

function readNumber(text: string, pattern: RegExp): number | undefined {
  const match = text.match(pattern)?.[1];
  if (match == null) return undefined;
  const number = Number(match.replace(",", "."));
  return Number.isFinite(number) ? number : undefined;
}

/** Una cota normalizada puede haber cambiado de origen durante el ensamblado. */
function originalDimension(field: ReviewField) {
  const text = field.source.text_original ?? "";
  const rule = ruleOf(field);
  if (rule.endsWith(".diametro_exterior")) {
    return { required: true, value: readNumber(text, /[Ø⌀]\s*(?:INT\.?\s*)?(\d+(?:[.,]\d+)?)/i) };
  }
  if (rule === "virola.cota_desde_tangente") {
    return { required: true, value: readNumber(text, /(?:^|\bEL\.?\s*)\+?\s*(\d+(?:[.,]\d+)?)(?:\s*mm)?\s*$/i) };
  }
  if (rule.endsWith(".proyeccion_desde_eje")) {
    return { required: true, value: readNumber(text, /^\s*(\d+(?:[.,]\d+)?)(?:\s*mm)?\s*$/i) };
  }
  if (field.path.endsWith(".azimuth")) {
    const value = readNumber(text, /(?:^|\s)(\d+(?:[.,]\d+)?)\s*°/);
    return { required: rule === "vertical.azimut_desde_norte", value };
  }
  return { required: false, value: undefined };
}

export function drawingAnnotations(fields: ReviewField[] | undefined, selectedId: string | null, horizontal: boolean): Annotation[] {
  if (!fields || !selectedId) return [];
  const id = parentElementId(selectedId);
  const nozzle = id.startsWith("nozzle:") ? `nozzles.${id.slice(7)}.` : null;
  const saddle = id.match(/^element:saddle-([12])$/);
  const section = id.startsWith("element:section-") ? `column.sections.${id.slice("element:section-".length)}.` : null;
  const selectedFields = fields.filter((field) => {
    if (field.unit !== "mm" && field.unit !== "deg") return false;
    if (id === "shell") return shellDimensions.has(field.path);
    if (id === "head-top" || id === "head-bottom") return field.path === "head_depth";
    if (id === "skirt") return field.path === "skirt_height" || field.path === "skirt_thickness";
    if (id.startsWith("element:leg-")) return field.path === "legs.height";
    if (saddle) return field.path === `horizontal.saddle_positions.${Number(saddle[1]) - 1}`;
    if (section) return field.path === `${section}height` || field.path === `${section}diameter`;
    if (!nozzle || !field.path.startsWith(nozzle)) return false;
    if (ruleOf(field) === "horizontal.boquilla_radial") return false;
    if (field.path.endsWith(".position.x") && ruleOf(field) !== "horizontal.estacion_tangente") return false;
    return nozzleDimensions.has(field.path.slice(nozzle.length));
  });
  const nominal = nozzle ? fields.find(field => field.path === `${nozzle}size_nps` && !field.abstained && !field.conflict) : undefined;
  const clockwise = (text: string) => /\bhorario\b/i.test(text) && !/\banti[ -]?horario\b/i.test(text);
  // La envolvente y su representación por familia pueden citar la misma cota.
  const seen = new Set<string>();
  return selectedFields.flatMap(field => {
    const value = field.correctedValue ?? field.value;
    if (typeof value !== "number" || !Number.isFinite(value) || field.abstained || field.conflict) return [];
    const original = field.status === "corrected" ? null : originalDimension(field);
    if (original?.required && original.value === undefined) return [];
    const kind = field.path.replace(/^horizontal\./, "").replace(/^attributes\./, "");
    if (seen.has(kind) || (kind === "length" && seen.has("height")) || (kind === "height" && seen.has("length"))) return [];
    seen.add(kind);
    return [{ id: field.path, productId: id, horizontal, label: field.label,
      value, unit: field.unit, confidence: field.confidence, source: field.source, state: field.status,
      explanation: field.explanation,
      drawingValue: original?.value,
      clockwise: field.unit === "deg" && clockwise(field.source.text_original ?? ""),
      nominalSize: nozzle && field.path.endsWith(".diameter") && nominal ? nominal.correctedValue ?? nominal.value : undefined,
    }];
  });
}

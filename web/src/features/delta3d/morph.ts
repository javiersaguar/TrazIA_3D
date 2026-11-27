import { fieldLabel } from "@/lib/field-labels";
import { elementForField, elementLabel } from "../viewer3d/semantic";

export type Pair<T> = { globalId: string; before: T | null; after: T | null };
export const clampProgress = (value: number) => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function pairByGlobalId<T extends { globalId: string }>(before: T[], after: T[]): Pair<T>[] {
  const index = (products: T[]) => {
    const map = new Map<string, T>();
    for (const product of products) {
      if (!product.globalId || map.has(product.globalId)) throw new Error("GlobalId vacío o duplicado: no se puede emparejar de forma inequívoca");
      map.set(product.globalId, product);
    }
    return map;
  };
  const a = index(before), b = index(after);
  return [...new Set([...a.keys(), ...b.keys()])].map(globalId => ({ globalId, before: a.get(globalId) ?? null, after: b.get(globalId) ?? null }));
}

export type Change = { path: string; operation: string; before: { value: number | string; unit: string } | null;
  after: { value: number | string; unit: string } | null; impact: string };
export type ChangeStep = { id: string; elementId: string; label: string; narration: string; fields: Change[] };

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object"; }

export function changeSteps(input: unknown): ChangeStep[] {
  const list = isRecord(input) && Array.isArray(input.changes) ? input.changes : Array.isArray(input) ? input : [];
  const byElement = new Map<string, Change[]>();
  for (const item of list) {
    if (!isRecord(item) || typeof item.path !== "string" || typeof item.operation !== "string") continue;
    const validValue = (v: unknown) => v === null || (isRecord(v) && ["number", "string"].includes(typeof v.value) && typeof v.unit === "string");
    if (!validValue(item.before) || !validValue(item.after)) continue;
    const change = item as unknown as Change;
    const id = elementForField(change.path);
    const group = byElement.get(id) ?? [];
    group.push(change); byElement.set(id, group);
  }
  return [...byElement].sort(([a], [b]) => a.localeCompare(b)).map(([elementId, changes]) => {
    const piece = changes.find(c => /^nozzles\.[^.]+$|^(?:shell\.courses|column\.sections)\.[^.]+$|^simulation\.[^.]+\.piece$/.test(c.path));
    const added = piece?.operation === "added", removed = piece?.operation === "removed";
    const deltas = changes.map(c => {
      if (typeof c.before?.value === "number" && typeof c.after?.value === "number" && c.before.unit === c.after.unit) {
        const difference = c.after.value - c.before.value;
        return `${difference > 0 ? "+" : ""}${difference.toLocaleString("es-ES")} ${c.after.unit}`;
      }
      return c.operation === "added" ? "nuevo" : c.operation === "removed" ? "retirado" : "modificado";
    });
    return { id: elementId, elementId,
      label: added ? (elementId.startsWith("nozzle:") ? "Nueva boquilla" : elementLabel(elementId)) : removed ? "Retirado" : [...new Set(deltas)].join(" · "),
      narration: added ? `${elementLabel(elementId)} se incorpora a la revisión B.` : removed ? `${elementLabel(elementId)} se retira en B.` :
        changes.map((c, i) => `${c.path.startsWith("pieces.") || c.path === "base_height" ? c.impact || fieldLabel(c.path) : fieldLabel(c.path)}: ${deltas[i]}.`).join(" "),
      fields: changes,
    };
  });
}

/** Un segmento por elemento: cámara 0–18 %, pulso 18–30 %, transformación 30–85 %. */
export const SEGMENT_SECONDS = 2.6;
export function timelineAt(progress: number, count: number) {
  const p = clampProgress(progress), n = Math.max(1, count);
  const index = Math.min(n - 1, Math.floor(p * n));
  const phase = p === 1 ? 1 : p * n - index;
  return { index, phase };
}
// Bézier (.65, 0, .35, 1), invertida en X para que el tiempo sea uniforme.
export function transformEase(value: number) {
  const x = clampProgress(value); let lo = 0, hi = 1;
  for (let i = 0; i < 14; i++) {
    const t = (lo + hi) / 2, u = 1 - t;
    const bx = 3 * u * u * t * .65 + 3 * u * t * t * .35 + t * t * t;
    if (bx < x) lo = t; else hi = t;
  }
  const t = (lo + hi) / 2; return x === 0 || x === 1 ? x : t * t * (3 - 2 * t);
}
export function segmentProgress(progress: number, index: number, count: number) {
  const local = clampProgress(progress) * Math.max(1, count) - index;
  return transformEase((local - .3) / .55);
}
export function dimensionText(step: ChangeStep, progress: number, continuous = true) {
  return step.fields.map(f => {
    if (typeof f.before?.value === "number" && typeof f.after?.value === "number" && f.before.unit === f.after.unit) {
      if (!continuous || /\.(?:azimuth|bearing)$/.test(f.path)) {
        return `${f.before.value.toLocaleString("es-ES")} → ${f.after.value.toLocaleString("es-ES")} ${f.after.unit}`;
      }
      const value = lerp(f.before.value, f.after.value, clampProgress(progress));
      return `${value.toLocaleString("es-ES", { maximumFractionDigits: 1 })} ${f.after.unit}`;
    }
    return `${f.before ? progress < .5 ? f.before.value : f.after?.value ?? "—" : f.after?.value ?? "—"} ${f.after?.unit ?? f.before?.unit ?? ""}`;
  }).join(" · ");
}

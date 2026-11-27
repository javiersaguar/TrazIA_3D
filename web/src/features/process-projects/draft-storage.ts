import type { Parameter } from "./catalog";
import type { ChangeRecord } from "./component-inspector";

export type Adjustment = { tag: string; field: string; value: number };
/** Borrador de un proyecto guardado en el navegador: lo necesario para regenerarlo al volver. */
export type SavedDraft = { version: 1; applied: string[]; adjustments: Adjustment[]; history: ChangeRecord[] };

const key = (project: string) => `trazia:borrador:${project}`;
const fields: readonly Parameter[] = ["length", "width", "height", "dn", "rack_z"];
const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isString = (value: unknown): value is string => typeof value === "string";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isChange(value: unknown): value is ChangeRecord {
  return isRecord(value) && isNumber(value.id) && isNumber(value.step) && isString(value.tag) && isString(value.at)
    && fields.includes(value.field as Parameter) && isNumber(value.after) && (value.before === undefined || isNumber(value.before));
}

/** Lee y valida el borrador guardado; lo que no encaja se descarta. */
export function parseDraft(text: string | null): SavedDraft | null {
  if (!text) return null;
  try {
    const data: unknown = JSON.parse(text);
    if (!isRecord(data) || data.version !== 1 || !Array.isArray(data.applied) || !Array.isArray(data.adjustments)
      || !Array.isArray(data.history)) return null;
    const applied = data.applied.filter(isString);
    const adjustments = data.adjustments.filter((item): item is Adjustment =>
      isRecord(item) && isString(item.tag) && isString(item.field) && isNumber(item.value));
    const history = data.history.filter(isChange);
    return adjustments.length && history.length ? { version: 1, applied, adjustments, history } : null;
  } catch {
    return null;
  }
}

export function readDraft(project: string): SavedDraft | null {
  try { return parseDraft(window.localStorage.getItem(key(project))); } catch { return null; }
}

export function saveDraft(project: string, draft: Omit<SavedDraft, "version">) {
  try { window.localStorage.setItem(key(project), JSON.stringify({ version: 1, ...draft })); } catch { /* Sin almacenamiento el borrador dura lo que la pestaña. */ }
}

export function clearDraft(project: string) {
  try { window.localStorage.removeItem(key(project)); } catch { /* Nada que borrar. */ }
}

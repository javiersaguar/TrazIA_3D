import type { MatchedFicha } from "@/lib/api/client";

export const fichaKey = (ficha: Pick<MatchedFicha, "project_id" | "equipment_id">) => `${ficha.project_id}:${ficha.equipment_id}`;
export const NEW_FICHA = "nueva";

/** Primera etiqueta libre a partir de la pedida: 2 → 3, B → C, X → X-2. */
export function nextRevision(labels: string[], wanted: string): string {
  const taken = new Set(labels.map(label => label.toUpperCase()));
  if (!taken.has(wanted.toUpperCase())) return wanted;
  const numbers = [...labels, wanted].filter(label => /^\d+$/.test(label)).map(Number);
  if (/^\d+$/.test(wanted)) return String(Math.max(...numbers) + 1);
  if (/^[A-Y]$/i.test(wanted)) {
    const letters = [...labels, wanted].filter(label => /^[A-Z]$/i.test(label)).map(label => label.toUpperCase().charCodeAt(0));
    const next = Math.max(...letters) + 1;
    if (next <= 90) return String.fromCharCode(next);
  }
  let index = 2;
  while (taken.has(`${wanted}-${index}`.toUpperCase())) index += 1;
  return `${wanted}-${index}`;
}

export type UploadPlan =
  | { kind: "new" }
  | { kind: "choose"; fichas: MatchedFicha[] }
  | { kind: "version"; ficha: MatchedFicha; revision: string }
  | { kind: "renamed"; ficha: MatchedFicha; requested: string; revision: string }
  | { kind: "duplicate"; ficha: MatchedFicha; revision: string };

/**
 * Decide dónde se guarda una subida: como versión de la ficha con el mismo código o como ficha
 * nueva. Si la revisión ya existe con los mismos archivos no se duplica; si trae otros archivos,
 * se propone la siguiente versión y se conserva la anterior.
 */
export function planUpload(fichas: MatchedFicha[], choice: string, revision: string, hashes: string[] | null): UploadPlan {
  if (!fichas.length || choice === NEW_FICHA) return { kind: "new" };
  const ficha = fichas.find(item => fichaKey(item) === choice) ?? (fichas.length === 1 ? fichas[0] : undefined);
  if (!ficha) return { kind: "choose", fichas };
  const existing = ficha.revisions.find(item => item.label.toUpperCase() === revision.trim().toUpperCase());
  if (!existing) return { kind: "version", ficha, revision: revision.trim() };
  const known = new Set(existing.documents.map(document => document.sha256));
  if (hashes?.length && hashes.every(hash => known.has(hash))) return { kind: "duplicate", ficha, revision: existing.label };
  return { kind: "renamed", ficha, requested: existing.label, revision: nextRevision(ficha.revisions.map(item => item.label), revision.trim()) };
}

export async function sha256(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

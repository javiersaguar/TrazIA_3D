import type { Document } from "@/lib/types/revision";

/** Entrada decimal del inspector; los límites físicos los valida la API por campo. */
export function parseReviewNumber(draft: string) {
  const value = draft.trim();
  if (value.includes(",") && value.includes(".") && !/^[+-]?\d{1,3}(?:\.\d{3})+,\d*$/.test(value)) return NaN;
  const normalized = value.includes(",") ? value.replace(/\./g, "").replace(",", ".") : value;
  return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized) ? Number(normalized) : NaN;
}

export const isSpreadsheet = (document: Document) => /\.xlsx?$/i.test(document.filename);

export function parseReviewRegion(draft: string): [number, number, number, number] | null {
  if (!draft.trim()) return null;
  const parts = draft.trim().split(/\s*;\s*|\s+/);
  if (parts.length !== 4) return null;
  const [x0 = NaN, y0 = NaN, x1 = NaN, y1 = NaN] = parts.map(parseReviewNumber);
  if (!(0 <= x0 && x0 < x1 && x1 <= 1 && 0 <= y0 && y0 < y1 && y1 <= 1)) return null;
  return [x0, y0, x1, y1];
}

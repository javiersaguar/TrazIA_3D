import type { EquipmentRow } from "@/lib/mock/api";
import type { Revision } from "@/lib/types/revision";

export type VersionEntry = {
  label: string;
  identity: string;
  /** Contador de guardados de la revisión: sube con cada corrección o decisión registrada. */
  saves: number | null;
  origin: string;
  dataset: "synthetic" | "real" | null;
  approval: { reviewer: string; at: string } | null;
  ifcUrl: string | null;
  documents: { id: string; filename: string }[];
};

const tail = (identity: string) => identity.split(":").at(-1) ?? identity;

/** Cómo nació la revisión: lectura de un plano o propuesta confirmada sobre otra revisión. */
export function versionOrigin(record: Pick<Revision, "derived_from" | "run"> | undefined): string {
  const derived = record?.derived_from;
  if (derived?.kind === "cambio_diseno") return `Cambio de diseño sobre Rev ${tail(derived.revision_id)}`;
  if (derived?.kind === "reversion") return `Reversión desde Rev ${tail(derived.revision_id)}`;
  if (record?.run?.strategy) return `Lectura del plano GA · ${record.run.strategy}`;
  return "Lectura del plano GA";
}

/** Versiones guardadas del equipo, de la más reciente a la primera. */
export function versionEntries(row: Pick<EquipmentRow, "project_id" | "equipment_id" | "revisions" | "revision_meta">,
  records: Record<string, Revision | undefined>): VersionEntry[] {
  return [...row.revisions].reverse().map((label) => {
    const meta = row.revision_meta?.[label];
    const record = records[label];
    const approval = record?.approval;
    return {
      label,
      identity: meta?.identity ?? `${row.project_id ?? ""}:${row.equipment_id ?? ""}:${label}`,
      saves: meta?.version ?? null,
      origin: versionOrigin(record),
      dataset: meta?.dataset ?? record?.dataset ?? null,
      approval: approval ? { reviewer: approval.reviewer, at: approval.timestamp } : null,
      ifcUrl: meta?.ifcUrl ?? null,
      documents: meta?.documents ?? record?.documents.map(({ id, filename }) => ({ id, filename })) ?? [],
    };
  });
}

import type { EquipmentRow } from "@/lib/mock/api";

export type ProjectModel = {
  id: string;
  tag: string;
  ifcUrl: string;
  version: string;
  horizontal: boolean;
};

export function projectModels(rows: EquipmentRow[], projectId: string, current: ProjectModel, realOnly: boolean) {
  const models = new Map([[current.id, current]]);
  for (const row of rows) {
    if (!projectId || row.project_id !== projectId || row.illustrative || !row.equipment_id || !row.ifcUrl) continue;
    const latest = row.revisions.at(-1);
    const meta = latest ? row.revision_meta?.[latest] : undefined;
    if (!latest || (realOnly && meta?.dataset !== "real")) continue;
    models.set(row.equipment_id, {
      id: row.equipment_id,
      tag: row.tag,
      ifcUrl: row.ifcUrl,
      version: latest,
      horizontal: row.kind === "Recipiente horizontal" || row.kind === "horizontal_vessel",
    });
  }
  return [...models.values()].sort((a, b) => a.tag.localeCompare(b.tag, "es", { numeric: true }));
}

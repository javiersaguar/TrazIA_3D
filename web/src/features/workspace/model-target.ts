import type { EquipmentRow } from "@/lib/mock/api";
import type { Revision } from "@/lib/types/revision";
import type { ActiveEquipment } from "@/stores/equipment";

/** Abre la revisión exacta de un documento y conserva un segundo estado para el selector A/B. */
export function modelTarget(record: Revision, rows: EquipmentRow[]): { equipment: ActiveEquipment; slot: "A" | "B" } {
  const row = rows.find((item) => item.project_id === record.project_id && item.equipment_id === record.equipment.id);
  const revisions = [...(row?.revisions ?? [])];
  if (!revisions.includes(record.revision)) revisions.push(record.revision);
  const index = revisions.indexOf(record.revision);
  const latest = index === revisions.length - 1;
  const before = latest ? revisions[index - 1] ?? record.revision : record.revision;
  const after = latest ? record.revision : revisions[index + 1]!;
  return {
    equipment: {
      project_id: record.project_id,
      equipment_id: record.equipment.id,
      tag: record.equipment.tag.value,
      revisions,
      revisionWindow: [before, after],
    },
    slot: latest ? "B" : "A",
  };
}

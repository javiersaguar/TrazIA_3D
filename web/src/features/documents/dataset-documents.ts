import type { EquipmentRow } from "@/lib/mock/api";

export type LotRow = {
  proyecto?: string;
  tag: string;
  revision: string;
  documentos: string[] | null;
  estado: string;
  error: string | null;
  familia: string | null;
  lod?: number | null;
  boquillas: number | null;
  segundos: number | null;
};

type RevisionModel = { identity: string; ifc: string };
export type ListedDocument = { filename: string; revision: string; id?: string; model?: RevisionModel };

export type GroupedRevision = {
  project: string;
  equipmentId: string;
  revision: string;
  source?: LotRow;
  model?: RevisionModel;
  version: number | null;
  approved: boolean;
  lod?: number | null;
  documents: ListedDocument[];
};

/** Código sin diferencias de mayúsculas ni espacios, como lo compara la API. */
export const tagKey = (tag: string) => tag.replace(/\s+/g, "").toLocaleUpperCase("es");

type Ficha = { project: string; equipmentId: string; tag: string; lot: LotRow[]; owner?: EquipmentRow };

/**
 * Una tarjeta por ficha: equipo de un proyecto con todas sus revisiones. Las fichas homónimas
 * (mismo código en otro proyecto o con otro ID) quedan separadas para poder decidir cuál borrar.
 * Una fila del lote sin revisión guardada se une a la ficha del mismo proyecto y código.
 */
export function groupDatasetDocuments(lot: LotRow[], equipment: EquipmentRow[]) {
  const fichas = new Map<string, Ficha>();
  for (const owner of equipment) {
    if (owner.illustrative) continue;
    const project = owner.project_id ?? "";
    const equipmentId = owner.equipment_id ?? owner.tag;
    fichas.set(JSON.stringify([project, equipmentId]), { project, equipmentId, tag: owner.tag, lot: [], owner });
  }
  for (const row of lot) {
    const project = row.proyecto ?? "INDESIAHACK";
    const same = [...fichas.values()].filter(ficha => ficha.project === project && tagKey(ficha.tag) === tagKey(row.tag));
    const target = same.find(ficha => ficha.owner?.revisions.includes(row.revision)) ?? same[0];
    if (target) target.lot.push(row);
    else fichas.set(JSON.stringify([project, `tag:${tagKey(row.tag)}`]), { project, equipmentId: "", tag: row.tag.trim(), lot: [row] });
  }

  return [...fichas].map(([key, ficha]) => {
    const labels = [...new Set([...ficha.lot.map(row => row.revision), ...(ficha.owner?.revisions ?? [])])];
    const revisions = labels.sort((a, b) => a.localeCompare(b, "es", { numeric: true })).map((label): GroupedRevision => {
      const source = ficha.lot.find(row => row.revision === label);
      const meta = ficha.owner?.revision_meta?.[label];
      const registered = ficha.owner?.revisions.includes(label);
      const identity = meta?.identity ?? (registered && ficha.equipmentId ? `${ficha.project}:${ficha.equipmentId}:${label}` : undefined);
      const model = identity ? {
        identity,
        ifc: meta?.ifcUrl ?? `/revisions/${encodeURIComponent(identity)}/ifc?draft=true&v=${meta?.version ?? "0"}`,
      } : undefined;
      const documents = new Map<string, ListedDocument>();
      for (const filename of source?.documentos ?? []) documents.set(filename, { filename, revision: label });
      for (const document of meta?.documents ?? []) documents.set(document.filename, { ...document, revision: label, model });
      return {
        project: ficha.project,
        equipmentId: ficha.equipmentId,
        revision: label,
        source,
        model,
        version: meta?.version ?? null,
        approved: meta?.approved === true,
        lod: meta?.lod ?? source?.lod,
        documents: [...documents.values()],
      };
    });
    return {
      key,
      tag: ficha.tag,
      project: ficha.project,
      equipmentId: ficha.equipmentId,
      equipment: ficha.owner,
      revisions,
      family: ficha.lot.find(row => row.familia)?.familia ?? ficha.owner?.kind,
    };
  });
}

export type DatasetGroup = ReturnType<typeof groupDatasetDocuments>[number];

/** Claves de código que aparecen en más de una ficha: ahí la tarjeta muestra el proyecto. */
export function homonymTags(groups: { tag: string }[]) {
  const counts = new Map<string, number>();
  for (const group of groups) counts.set(tagKey(group.tag), (counts.get(tagKey(group.tag)) ?? 0) + 1);
  return new Set([...counts].filter(([, count]) => count > 1).map(([key]) => key));
}

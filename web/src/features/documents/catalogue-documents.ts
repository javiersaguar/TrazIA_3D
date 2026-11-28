import { DEMO } from "@/lib/mock/api";
import { publishedFile, sketchAssets, tagFromFilename, type Design, type Project } from "./catalogue";
import { tagKey, type CatalogueModel, type EquipmentGroup } from "./dataset-documents";

function designModel(design: Design): CatalogueModel | undefined {
  if (design.demo && (design.rev === "A" || design.rev === "B")) {
    return { name: design.name, ifc: DEMO.revisions[design.rev].ifc, demoRevision: design.rev };
  }
  const ifc = sketchAssets(design.id)?.ifc;
  if (ifc) return { name: design.name, ifc };
  if (design.filename?.toLowerCase().endsWith(".ifc")) {
    return design.shared
      ? { name: design.name, ifc: publishedFile(design.id), published: true }
      : { name: design.name, documentId: design.id };
  }
}

export function groupCatalogueDocuments(designs: Design[], projects: Project[]): EquipmentGroup[] {
  const projectNames = new Map(projects.map(({ id, name }) => [id, name]));
  const groups = new Map<string, EquipmentGroup>();
  for (const design of designs) {
    const tag = design.tag ?? tagFromFilename(design.filename ?? design.name);
    const equipmentId = tag ? tagKey(tag) : design.id;
    const key = JSON.stringify([design.project, equipmentId]);
    let group = groups.get(key);
    if (!group) {
      group = {
        key, project: design.project, projectLabel: projectNames.get(design.project),
        equipmentId, tag: tag ?? design.name, family: design.family, equipment: undefined,
        revisions: [], local: true,
      };
      groups.set(key, group);
    }

    const label = design.rev ?? design.filename?.match(/(?:^|[-_\s])rev[. _-]*([a-z0-9]+)(?=\.|$)/i)?.[1]?.toUpperCase() ?? "—";
    let revision = group.revisions.find((item) => item.revision === label);
    if (!revision) {
      revision = { project: design.project, equipmentId, revision: label, version: null, approved: false, documents: [] };
      group.revisions.push(revision);
    }
    revision.localModel ??= designModel(design);
    revision.documents.push({ filename: design.filename ?? design.name, revision: label, id: design.id, design });
  }
  for (const group of groups.values()) {
    group.revisions.sort((a, b) => a.revision.localeCompare(b.revision, "es", { numeric: true }));
  }
  return [...groups.values()];
}

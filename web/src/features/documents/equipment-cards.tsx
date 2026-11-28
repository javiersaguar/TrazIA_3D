"use client";

import { Box } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button, Icon, Panel } from "@/components/ui/primitives";
import { modelHref } from "@/features/workspace/model-links";
import type { Family } from "./catalogue";
import { homonymTags, latestModel, tagKey, type EquipmentGroup } from "./dataset-documents";
import { DeleteEquipmentButton } from "./delete-equipment-button";
import { CatalogueModelButton } from "./document-actions";
import { groupByClass } from "./equipment-classes";
import { EquipmentDocumentsDialog } from "./equipment-documents-dialog";
import { IfcThumbnail } from "./ifc-thumbnail";

const FAMILY: Record<string, string> = {
  vertical: "Recipiente vertical",
  horizontal: "Recipiente horizontal",
  vertical_vessel: "Recipiente vertical",
  horizontal_vessel: "Recipiente horizontal",
  column: "Columna",
  tank: "Tanque",
  pump: "Bomba",
  compressor: "Compresor",
};

export function EquipmentCards({ groups, allGroups, families = [] }: {
  groups: EquipmentGroup[];
  allGroups: EquipmentGroup[];
  families?: Family[];
}) {
  const router = useRouter();
  const sections = groupByClass(groups, (group) => group.family);
  const homonyms = homonymTags(allGroups);
  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <section key={section.cls.id} aria-labelledby={`clase-${section.cls.id}`} className="space-y-2.5">
          <header className="flex flex-wrap items-end justify-between gap-x-3 gap-y-1 border-b border-border pb-2">
            <div className="border-l-2 border-accent pl-2.5">
              <h2 id={`clase-${section.cls.id}`} className="text-base leading-snug font-semibold text-strong">{section.cls.title}</h2>
              <p className="mt-0.5 text-xs text-muted">{section.cls.standard}</p>
            </div>
            <p className="rounded-md border border-border bg-surface px-2 py-0.5 text-xs font-medium text-muted">
              {section.items.length} {section.items.length === 1 ? "equipo" : "equipos"}
            </p>
          </header>
          <ul className="grid gap-3 md:grid-cols-2">
            {section.items.map((group) => {
              const latest = latestModel(group);
              const model = latest?.model;
              const localModel = latest?.localModel;
              const files = group.revisions.reduce((total, revision) => total + revision.documents.length, 0);
              const envelope = latest?.lod === 1 && (group.family === "pump" || group.family === "compressor");
              const error = group.revisions.find((revision) => revision.source?.estado !== "ok" && revision.source?.error)?.source?.error;
              const homonym = homonyms.has(tagKey(group.tag));
              const family = group.family && (FAMILY[group.family] ?? families.find((item) => item.id === group.family)?.name ?? group.family);
              return (
                <li key={group.key}>
                  <Panel className="grid h-full min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 p-3 sm:gap-x-4">
                    <IfcThumbnail name={group.tag} url={group.equipment?.ifcUrl ?? localModel?.ifc}
                      documentId={localModel?.documentId} size="card" />
                    <div className="relative min-w-0 space-y-2.5 self-center">
                      <header className="pr-8">
                        <h3 className="font-mono text-lg leading-tight text-strong [overflow-wrap:anywhere]">
                          {group.tag}
                          {homonym ? <span className="ml-2 align-middle font-sans text-xs font-medium text-muted">{group.projectLabel ?? group.project}</span> : null}
                        </h3>
                        <p className="mt-1 text-sm text-muted">{family || "Familia sin leer"}{envelope ? " · Envolvente LOD 1" : ""}</p>
                      </header>
                      {model || localModel || files ? (
                        <div className="flex flex-wrap items-center gap-2">
                          {model ? (
                            <Button variant="primary" onClick={() => router.push(modelHref("revision", model.identity))}>
                              <Icon icon={Box} size={16} />
                              Ver modelo 3D
                            </Button>
                          ) : null}
                          {localModel ? <CatalogueModelButton model={localModel} tag={group.tag} primary /> : null}
                          {files ? (
                            <EquipmentDocumentsDialog tag={group.tag} project={homonym ? group.projectLabel ?? group.project : undefined}
                              revisions={group.revisions} />
                          ) : null}
                        </div>
                      ) : null}
                      {error && !model ? <p className="text-xs leading-relaxed text-warning">{error}</p> : null}
                      {group.local ? null : <DeleteEquipmentButton tag={group.tag} project={group.project} equipmentId={group.equipmentId}
                        revisions={group.revisions} />}
                    </div>
                  </Panel>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

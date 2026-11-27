"use client";

import { useQuery } from "@tanstack/react-query";
import { Box, FileText, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Segmented } from "@/components/ui/controls";
import { Button, EmptyState, Icon, Panel, Skeleton } from "@/components/ui/primitives";
import { UploadPlansDialog } from "@/features/pipeline/upload-plans-dialog";
import { modelHref } from "@/features/workspace/model-links";
import { useCanEdit } from "@/lib/accounts";
import { apiURL } from "@/lib/api/config";
import { useEquipment as useEquipmentRows } from "@/lib/queries";
import { useCatalogue } from "./catalogue";
import { groupDatasetDocuments, homonymTags, tagKey, type LotRow } from "./dataset-documents";
import { classOf, groupByClass, sameFamily } from "./equipment-classes";
import { DeleteEquipmentButton } from "./delete-equipment-button";
import { EquipmentDocumentsDialog } from "./equipment-documents-dialog";
import { IfcThumbnail } from "./ifc-thumbnail";

const FAMILY: Record<string, string> = {
  vertical_vessel: "Recipiente vertical",
  horizontal_vessel: "Recipiente horizontal",
  column: "Columna",
  tank: "Tanque",
  pump: "Bomba",
  compressor: "Compresor",
};
type Filter = "todos" | "modelo" | "faltan";


/** Equipos del dataset del reto, con sus documentos por revisión y lo que ha leído el lote. */
export function DatasetLibrary() {
  const router = useRouter();
  const params = useSearchParams();
  const familia = params.get("familia");
  const proyecto = params.get("proyecto");
  const catalogue = useCatalogue();
  const canEdit = useCanEdit();
  const equipment = useEquipmentRows("always");
  const lote = useQuery({
    queryKey: ["lote-resumen"],
    queryFn: async () => {
      const response = await fetch(apiURL("/lote/resumen"));
      if (!response.ok) throw new Error("No se pudo leer el lote del dataset");
      return (await response.json()) as LotRow[];
    },
  });
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("todos");
  const projectTags = useMemo(() => {
    if (!proyecto) return null;
    return new Set(
      catalogue.designs
        .filter((design) => design.project === proyecto && design.tag)
        .map((design) => design.tag as string),
    );
  }, [catalogue.designs, proyecto]);

  const groups = useMemo(() => {
    const term = query.trim().toLowerCase();
    return groupDatasetDocuments(lote.data ?? [], equipment.data ?? [])
      .filter((group) => filter === "todos" || (filter === "modelo" ? group.equipment : !group.equipment))
      .filter((group) => !projectTags || projectTags.has(group.tag))
      .filter((group) => !familia || familia === "all" || sameFamily(familia, group.family))
      .filter((group) => {
        if (!term) return true;
        if (group.tag.toLowerCase().includes(term)) return true;
        return group.revisions.some((revision) =>
          revision.documents.some((document) => document.filename.toLowerCase().includes(term)),
        );
      })
      .sort((a, b) => Number(Boolean(b.equipment)) - Number(Boolean(a.equipment)) || a.tag.localeCompare(b.tag));
  }, [lote.data, equipment.data, filter, query, familia, projectTags]);

  const homonyms = useMemo(() => homonymTags(groupDatasetDocuments(lote.data ?? [], equipment.data ?? [])), [lote.data, equipment.data]);
  const sections = useMemo(() => groupByClass(groups, (group) => group.family), [groups]);
  const familyName = catalogue.families.find((family) => family.id === familia)?.name;
  const projectName = catalogue.projects.find((project) => project.id === proyecto)?.name;
  const withModel = (lote.data ?? []).filter((row) => row.estado === "ok").length;
  const hasFamily = Boolean(familia && familia !== "all");
  const filtered = Boolean(query || filter !== "todos" || hasFamily || proyecto);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">Buscar equipo o documento</span>
          <Icon icon={Search} size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por TAG o documento"
            className="h-11 w-full rounded-[var(--radius-control)] border border-border bg-surface pr-3 pl-9 text-sm sm:h-9"
          />
        </label>
        <Segmented<Filter>
          label="Estado"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "todos", label: "Todos" },
            { value: "modelo", label: "Con modelo" },
            { value: "faltan", label: "Faltan datos" },
          ]}
        />
        {canEdit ? <UploadPlansDialog /> : null}
        {lote.data && withModel < lote.data.length ? (
          <span className="text-xs text-muted">{withModel} de {lote.data.length} revisiones con modelo</span>
        ) : null}
      </div>
      {hasFamily || proyecto ? (
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span>
            {familyName ? `Familia ${familyName}` : familia && familia !== "all" ? `Familia ${classOf(familia).title}` : null}
            {familyName && projectName ? " · " : null}
            {projectName ? `Proyecto ${projectName}` : null}
          </span>
          <button
            type="button"
            className="text-accent-text underline-offset-2 hover:underline"
            onClick={() => window.history.replaceState(null, "", "/documentos?vista=equipos")}
          >
            Quitar filtro
          </button>
        </p>
      ) : null}

      {lote.isLoading || equipment.isLoading ? (
        <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}</div>
      ) : groups.length === 0 ? (
        <EmptyState icon={FileText} title={filtered ? "Ningún equipo coincide" : "Todavía no hay equipos"}>
          {filtered ? "Prueba con otro TAG o quita el filtro." : "Sube los planos de un equipo para empezar."}
        </EmptyState>
      ) : (
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
                  const recent = [...group.revisions].reverse();
                  const latest = recent.find((revision) => revision.model);
                  const model = latest?.model;
                  const files = group.revisions.reduce((total, revision) => total + revision.documents.length, 0);
                  const envelope = latest?.lod === 1 && (group.family === "pump" || group.family === "compressor");
                  const error = group.revisions.find((revision) => revision.source?.estado !== "ok" && revision.source?.error)?.source?.error;
                  const homonym = homonyms.has(tagKey(group.tag));
                  return (
                    <li key={group.key}>
                      <Panel className="grid h-full min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 p-3 sm:gap-x-4">
                        <IfcThumbnail name={group.tag} url={group.equipment?.ifcUrl} size="card" />
                        <div className="relative min-w-0 space-y-2.5 self-center">
                          <header className="pr-8">
                            <h3 className="font-mono text-lg leading-tight text-strong [overflow-wrap:anywhere]">
                              {group.tag}
                              {homonym ? <span className="ml-2 align-middle font-sans text-xs font-medium text-muted">{group.project}</span> : null}
                            </h3>
                            <p className="mt-1 text-sm text-muted">{group.family ? FAMILY[group.family] ?? group.family : "Familia sin leer"}{envelope ? " · Envolvente LOD 1" : ""}</p>
                          </header>
                          {model || files ? (
                            <div className="flex flex-wrap items-center gap-2">
                              {model ? (
                                <Button variant="primary" onClick={() => router.push(modelHref("revision", model.identity))}>
                                  <Icon icon={Box} size={16} />
                                  Ver modelo 3D
                                </Button>
                              ) : null}
                              {files ? (
                                <EquipmentDocumentsDialog tag={group.tag} project={homonym ? group.project : undefined}
                                  revisions={group.revisions} />
                              ) : null}
                            </div>
                          ) : null}
                          {error && !model ? <p className="text-xs leading-relaxed text-warning">{error}</p> : null}
                          <DeleteEquipmentButton tag={group.tag} project={group.project} equipmentId={group.equipmentId}
                            revisions={group.revisions} />
                        </div>
                      </Panel>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Segmented } from "@/components/ui/controls";
import { EmptyState, Icon, Skeleton } from "@/components/ui/primitives";
import { UploadPlansDialog } from "@/features/pipeline/upload-plans-dialog";
import { useCanEdit } from "@/lib/accounts";
import { apiURL } from "@/lib/api/config";
import { useEquipment as useEquipmentRows } from "@/lib/queries";
import { useCatalogue } from "./catalogue";
import { groupDatasetDocuments, type LotRow } from "./dataset-documents";
import { classOf, sameFamily } from "./equipment-classes";
import { EquipmentCards } from "./equipment-cards";

type Filter = "todos" | "modelo" | "faltan";


/** Equipos del dataset del reto, con sus documentos por revisión y lo que ha leído el lote. */
export function DatasetLibrary() {
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

  const allGroups = useMemo(() => groupDatasetDocuments(lote.data ?? [], equipment.data ?? []), [lote.data, equipment.data]);
  const groups = useMemo(() => {
    const term = query.trim().toLowerCase();
    return allGroups
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
  }, [allGroups, filter, query, familia, projectTags]);

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
        <EquipmentCards groups={groups} allGroups={allGroups} />
      )}
    </div>
  );
}

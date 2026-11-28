"use client";

import { FileText, FileUp, Search } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";

import { EmptyState, Icon } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { useCanEdit } from "@/lib/accounts";
import { accountsEnabled } from "@/lib/api/config";
import { DOCUMENT_ACCEPT, MAX_DOCUMENT_BYTES, MAX_DOCUMENT_MB, useCatalogue } from "./catalogue";
import { groupCatalogueDocuments } from "./catalogue-documents";
import { latestModel } from "./dataset-documents";
import { EquipmentCards } from "./equipment-cards";
import { sameFamily } from "./equipment-classes";
import { Segmented } from "@/components/ui/controls";

const fieldBase =
  "h-9 rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 text-[13px] text-text outline-none focus-visible:border-accent";
export const fieldClass = `${fieldBase} w-full`;
type Filter = "todos" | "modelo" | "faltan";

export function DocumentsTab({
  family,
  project,
  onProject,
  onFamily,
}: {
  family: string;
  project: string;
  onProject: (id: string) => void;
  onFamily: (id: string) => void;
}) {
  const catalogue = useCatalogue();
  const canEdit = useCanEdit();
  const [over, setOver] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("todos");
  const input = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState({ family: family === "all" ? "vertical" : family, project: project === "all" ? "demo" : project });
  // El destino sigue al filtro activo mientras el usuario no lo cambie a mano
  const [lastFilter, setLastFilter] = useState({ family, project });
  if (lastFilter.family !== family || lastFilter.project !== project) {
    setLastFilter({ family, project });
    setTarget((t) => ({ family: family === "all" ? t.family : family, project: project === "all" ? t.project : project }));
  }

  const groups = groupCatalogueDocuments(catalogue.designs, catalogue.projects);
  const term = query.trim().toLocaleLowerCase("es");
  const visible = groups
    .filter((group) => (family === "all" || sameFamily(family, group.family)) && (project === "all" || group.project === project))
    .filter((group) => filter === "todos" || Boolean(latestModel(group)) === (filter === "modelo"))
    .filter((group) => !term || group.tag.toLocaleLowerCase("es").includes(term)
      || group.revisions.some((revision) => revision.documents.some((file) =>
        `${file.filename} ${file.design?.name ?? ""}`.toLocaleLowerCase("es").includes(term))))
    .sort((a, b) => Number(Boolean(latestModel(b))) - Number(Boolean(latestModel(a))) || a.tag.localeCompare(b.tag, "es", { numeric: true }));

  async function add(files: FileList | null) {
    if (!canEdit || !files?.length) return;
    const list = [...files];
    const tooBig = list.filter((f) => f.size > MAX_DOCUMENT_BYTES);
    const ok = list.filter((f) => f.size <= MAX_DOCUMENT_BYTES && f.size > 0);
    let saved = 0;
    for (const file of ok) {
      try {
        await catalogue.publish(file, { ...target, name: file.name.replace(/\.[^.]+$/, "") || file.name });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : `No se pudo guardar ${file.name}.`);
        continue;
      }
      saved++;
    }
    if (tooBig.length) toast.error(`${tooBig.map((f) => f.name).join(", ")} supera ${MAX_DOCUMENT_MB} MB.`);
    if (saved) {
      const familyName = catalogue.families.find((f) => f.id === target.family)?.name ?? "la familia elegida";
      toast.success(saved === 1 ? `Documento añadido a ${familyName}` : `${saved} documentos añadidos a ${familyName}`);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    void add(e.dataTransfer.files);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">Buscar equipo o documento</span>
          <Icon icon={Search} size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por TAG o documento" className={cn(fieldClass, "pl-9")} />
        </label>
        <Segmented<Filter> label="Estado" value={filter} onChange={setFilter} options={[
          { value: "todos", label: "Todos" },
          { value: "modelo", label: "Con modelo" },
          { value: "faltan", label: "Faltan datos" },
        ]} />
        <select aria-label="Filtrar por familia" value={family} onChange={(event) => onFamily(event.target.value)}
          className={cn(fieldBase, "max-w-full")}>
          <option value="all">Todas las familias</option>
          {catalogue.families.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
        </select>
        <select aria-label="Filtrar por proyecto" value={project} onChange={(event) => onProject(event.target.value)}
          className={cn(fieldBase, "max-w-full")}>
          <option value="all">Todos los proyectos</option>
          {catalogue.projects.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
        </select>
      </div>

      {canEdit ? <details className="rounded-[var(--radius-panel)] border border-border bg-surface">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-accent-text">Subir planos</summary>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          data-testid="document-dropzone"
          className={cn(
            "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-panel)] border border-dashed px-6 py-9 text-center transition-[border-color,background-color] duration-200",
            over ? "border-accent bg-accent-soft" : "border-border-strong bg-surface",
          )}
        >
          <span
            className={cn(
              "flex size-11 items-center justify-center rounded-full border transition-transform duration-200",
              over ? "scale-110 border-accent text-accent" : "border-border text-muted",
            )}
          >
            <Icon icon={FileUp} size={20} />
          </span>
          <p className="text-[15px] font-medium text-strong">Suelta aquí los planos GA y las hojas de datos</p>
          <p className="text-[13px] text-muted">
            o{" "}
            <button type="button" onClick={() => input.current?.click()} className="text-accent-text underline-offset-2 hover:underline">
              elígelos en tu equipo
            </button>
            {accountsEnabled ? ". Se publican en el catálogo compartido." : ". Se guardan en este navegador."}
          </p>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2 text-[13px] text-muted">
            <span>Se añaden a</span>
            <select
              aria-label="Familia de destino"
              value={target.family}
              onChange={(e) => setTarget((t) => ({ ...t, family: e.target.value }))}
              className={cn(fieldBase, "w-60 max-w-full")}
            >
              {catalogue.families.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
            <span>en</span>
            <select
              aria-label="Proyecto de destino"
              value={target.project}
              onChange={(e) => setTarget((t) => ({ ...t, project: e.target.value }))}
              className={cn(fieldBase, "w-60 max-w-full")}
            >
              {catalogue.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <input
            ref={input}
            type="file"
            accept={DOCUMENT_ACCEPT}
            multiple
            className="sr-only"
            aria-label="Elegir documentos"
            onChange={(e) => {
              void add(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      </details> : null}

      {visible.length ? <EquipmentCards groups={visible} allGroups={groups} families={catalogue.families} /> : (
        <EmptyState icon={FileText} title={groups.length ? "Ningún equipo coincide" : "Todavía no hay equipos"}>
          {groups.length ? "Prueba con otro TAG o quita el filtro." : "Sube los planos de un equipo para empezar."}
        </EmptyState>
      )}
    </div>
  );
}

"use client";

import { FileUp, FolderOpen, Plus, Shapes } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/ui/controls";
import { Button, Icon, Panel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { accountsEnabled, apiEnabled } from "@/lib/api/config";
import { useCanEdit } from "@/lib/accounts";
import { useMounted } from "@/lib/use-mounted";
import { DOCUMENT_ACCEPT, useCatalogue } from "./catalogue";
import { DocumentsTab, fieldClass } from "./documents-tab";
import { FamiliesTab } from "./families-tab";
import { groupByClass } from "./equipment-classes";
import { projectFamilies, ProjectsTab } from "./projects-tab";

export type LibraryView = "documentos" | "proyectos" | "familias";
type FormKind = "family" | "project" | "design";
const FORM_TITLE: Record<FormKind, string> = { family: "Nueva familia", project: "Nuevo proyecto", design: "Añadir diseño" };

export function DocumentLibrary({ compact = false }: { compact?: boolean } = {}) {
  const catalogue = useCatalogue();
  const canEdit = useCanEdit();
  const mounted = useMounted();
  const params = useSearchParams();
  const raw = params.get("vista");
  const view: LibraryView = raw === "proyectos" || raw === "familias" ? raw : "documentos";
  const family = params.get("familia") ?? "all";
  const project = params.get("proyecto") ?? "all";
  function show(next: LibraryView, selectedFamily = family, selectedProject = project) {
    const query = new URLSearchParams({ vista: next === "documentos" ? "equipos" : next });
    if (selectedFamily !== "all") query.set("familia", selectedFamily);
    if (selectedProject !== "all" && next === "documentos") query.set("proyecto", selectedProject);
    window.history.replaceState(null, "", `/documentos?${query}`);
  }

  const [form, setForm] = useState<FormKind | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit || busy) return;
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    if (!name) return;
    setError("");
    setBusy(true);
    try {
      if (form === "family") {
        show(view, await catalogue.addFamily(name), "all");
      }
      if (form === "project") {
        await catalogue.addProject(name);
        show(view, family, "all");
      }
      if (form === "design") {
        const file = data.get("file");
        if (!(file instanceof File) || !file.size) throw new Error("Selecciona un documento para el diseño.");
        await catalogue.publish(file, {
          name,
          family: String(data.get("family")),
          project: String(data.get("project")),
        });
        show("documentos", String(data.get("family")), "all");
      }
      setForm(null);
      toast.success(accountsEnabled ? "Guardado en el catálogo compartido" : "Guardado en este navegador");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar. Comprueba el espacio disponible del navegador.");
    } finally {
      setBusy(false);
    }
  }

  if (!mounted) return <p role="status" className="p-6 text-sm text-muted">Cargando catálogo…</p>;

  const counts = (id: string) =>
    catalogue.projects.filter((p) => id === "all" || projectFamilies(p, catalogue.designs).includes(id)).length;

  return (
    <div className={compact ? "space-y-3" : "space-y-6"}>
      {compact ? <h1 className="sr-only">Documentos</h1> : null}
      {!compact || canEdit ? <header className="flex flex-wrap items-end justify-between gap-3">
        {!compact ? <div>
          <h1 className="text-2xl font-semibold text-strong">Documentos</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            {accountsEnabled
              ? "Consulta los diseños compartidos por familia y proyecto."
              : "Clasifica tus documentos por familia y proyecto. Los archivos se guardan en este navegador."}
          </p>
        </div> : null}
        {canEdit ? <div className="flex flex-wrap gap-2">
          <Button onClick={() => (setForm("family"), setError(""))}>
            <Icon icon={Shapes} /> Nueva familia
          </Button>
          <Button onClick={() => (setForm("project"), setError(""))}>
            <Icon icon={FolderOpen} /> Nuevo proyecto
          </Button>
          <Button variant="primary" onClick={() => (setForm("design"), setError(""))}>
            <Icon icon={FileUp} /> Añadir diseño
          </Button>
        </div> : null}
      </header> : null}

      {catalogue.loading ? <p role="status" className="text-sm text-muted">Cargando catálogo compartido…</p> : null}
      {catalogue.error ? <Panel className="flex items-center justify-between gap-2 p-4">
        <p role="alert" className="text-sm text-danger">{catalogue.error.message}</p>
        <Button onClick={() => void catalogue.reload()}>Reintentar</Button>
      </Panel> : null}

      {canEdit && apiEnabled && view === "documentos" ? (
        <Panel className="flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm text-muted">Para extraer cotas y generar un IFC DRAFT, carga los originales de una revisión en el Pipeline.</p>
          <Link href="/documentos" className="text-sm font-medium text-accent-text underline">Subir planos</Link>
        </Panel>
      ) : null}

      {canEdit && form ? (
        <Panel className="p-5">
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" aria-label={FORM_TITLE[form]}>
            <h2 className="text-lg font-semibold sm:col-span-2">{FORM_TITLE[form]}</h2>
            <label className="space-y-2 text-sm">
              Nombre
              <input name="name" required maxLength={120} autoFocus className={fieldClass} />
            </label>
            {form === "design" ? (
              <>
                <label className="space-y-2 text-sm">
                  Documento
                  <input type="file" name="file" required accept={DOCUMENT_ACCEPT} className="w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 py-1.5 text-[13px] text-text" />
                </label>
                <label className="space-y-2 text-sm">
                  Familia
                  <select aria-label="Familia" name="family" defaultValue={family === "all" ? "vertical" : family} className={fieldClass}>
                    {catalogue.families.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-2 text-sm">
                  Proyecto
                  <select aria-label="Proyecto" name="project" defaultValue={project === "all" ? "demo" : project} className={fieldClass}>
                    {catalogue.projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : null}
            {form === "family" ? (
              <p className="self-end text-sm text-muted">Puedes clasificar documentos en una familia nueva. La creación de su plantilla geométrica se revisa por separado.</p>
            ) : null}
            {error ? (
              <p role="alert" className="text-sm text-danger sm:col-span-2">
                {error}
              </p>
            ) : null}
            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit" variant="primary" disabled={busy}>
                <Icon icon={Plus} />
                {busy ? "Guardando…" : "Guardar"}
              </Button>
              <Button type="button" onClick={() => setForm(null)}>
                Cancelar
              </Button>
            </div>
          </form>
        </Panel>
      ) : null}

      {!compact ? <Segmented<LibraryView>
        label="Clasificación de documentos"
        value={view}
        onChange={(next) => show(next)}
        options={[
          { value: "documentos", label: "Equipos" },
          { value: "proyectos", label: "Proyectos" },
          { value: "familias", label: "Familias" },
        ]}
      /> : null}

      {view === "familias" ? (
        <FamiliesTab
          selected={family}
          onOpen={(id, next) => show(next, id, "all")}
        />
      ) : view === "documentos" ? (
        <DocumentsTab family={family} project={project}
          onFamily={(id) => show(view, id)} onProject={(id) => show(view, family, id)} />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[230px_minmax(0,1fr)]">
          <Panel className="h-fit p-3">
            <h2 className="px-2 py-2 text-sm font-semibold">Familias</h2>
            <nav aria-label="Familias de documentos" className="space-y-1">
              <button
                onClick={() => show(view, "all", "all")}
                aria-pressed={family === "all"}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm",
                  family === "all" ? "bg-accent-soft text-accent-text" : "text-muted hover:bg-surface-raised",
                )}
              >
                <span>Todas las familias</span>
                <span className="text-xs tabular-nums">{counts("all")}</span>
              </button>
              {groupByClass(catalogue.families, (item) => item.id).map((section) => (
                <div key={section.cls.id} className="pt-2">
                  <p className="px-3 pt-1 text-[11px] font-semibold text-strong">{section.cls.title}</p>
                  <p className="px-3 pb-1 text-[10px] text-faint">{section.cls.standard}</p>
                  {section.items.map((f) => (
                    <button
                      key={f.id}
                      onClick={() => show(view, f.id, "all")}
                      aria-pressed={family === f.id}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm",
                        family === f.id ? "bg-accent-soft text-accent-text" : "text-muted hover:bg-surface-raised",
                      )}
                    >
                      <span>{f.name}</span>
                      <span className="text-xs tabular-nums">{counts(f.id)}</span>
                    </button>
                  ))}
                </div>
              ))}
            </nav>
          </Panel>
          <div className="min-w-0">
            <ProjectsTab family={family} onOpenProject={(id) => show("documentos", family, id)} />
          </div>
        </div>
      )}
    </div>
  );
}

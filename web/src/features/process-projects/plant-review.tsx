"use client";

import { useQuery } from "@tanstack/react-query";
import { Crosshair, FileText, Layers3 } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState, type ReactNode } from "react";
import { Button, Icon, Panel, Skeleton } from "@/components/ui/primitives";
import { ReviewDrawer } from "@/features/review/review-drawer";
import { cn } from "@/lib/cn";
import type { Source } from "@/lib/types/revision";

const PdfPanel = dynamic(() => import("@/features/review/pdf-panel").then(module => module.PdfPanel), {
  ssr: false, loading: () => <Skeleton className="h-full" />,
});

type Cota = {
  path: string;
  label: string;
  elementId: string;
  value: number;
  unit: string;
  page: number;
  bbox: NonNullable<Source["bbox"]>;
};
type Evidence = Cota & { status: "candidate"; source: Pick<Source, "page" | "bbox"> };

const MODES = { both: "Todo", pdf: "Plano", model: "Modelo" } as const;
const measureFormat = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 3 });

export function PlantReview({ pdf, fieldsUrl, selected, onSelect, matchesModel, children }: {
  pdf: string; fieldsUrl: string; selected: string; onSelect(id: string): void; matchesModel: boolean; children: ReactNode;
}) {
  const [mode, setMode] = useState<keyof typeof MODES>("both");
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [requestedPath, setRequestedPath] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const fields = useQuery({
    queryKey: ["plant-evidence", fieldsUrl],
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      const response = await fetch(fieldsUrl, { signal });
      if (!response.ok) throw new Error("No se pudieron cargar las cotas");
      const items: Cota[] = await response.json();
      return items.map((item): Evidence => ({
        ...item, status: "candidate", source: { page: item.page, bbox: item.bbox },
      }));
    },
  });
  const measures = useMemo(() => fields.data ?? [], [fields.data]);
  const byPath = useMemo(() => new Map(measures.map(field => [field.path, field])), [measures]);
  const subject = matchesModel ? selected : "";
  const requested = requestedPath ? byPath.get(requestedPath) : undefined;
  const selectedPath = requested && (!matchesModel || requested.elementId === subject) ? requested.path
    : subject ? measures.find(field => field.elementId === subject)?.path ?? null : null;
  const query = filter.trim().toLocaleLowerCase("es");
  const visible = measures.filter(field => query
    ? field.label.toLocaleLowerCase("es").includes(query)
    : field.elementId === subject);

  function showEvidence(field: Evidence, close?: () => void) {
    setRequestedPath(field.path);
    setFilter("");
    if (matchesModel) onSelect(field.elementId);
    if (mode === "model") setMode("both");
    close?.();
  }

  return <section aria-label="Revisión de planta" className="space-y-2">
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
      <span className="mr-1 text-xs font-medium text-muted">Foco</span>
      <div className="flex flex-wrap gap-1" role="group" aria-label="Foco de revisión">
        {Object.entries(MODES).map(([key, label]) => <Button key={key} size="sm" variant="secondary"
          aria-pressed={mode === key} className={cn(mode === key && "bg-accent-soft text-accent-text")}
          onClick={() => setMode(key as keyof typeof MODES)}>{label}</Button>)}
        <Button size="sm" variant="secondary" aria-expanded={open} onClick={() => setOpen(value => !value)}>Campos</Button>
      </div>
      <a href={pdf} download className="ml-auto inline-flex min-h-8 items-center gap-1.5 text-xs font-medium text-accent-text hover:underline">
        <Icon icon={FileText} size={14} /> Descargar plano GA
      </a>
    </div>
    {!matchesModel ? <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
      El PDF es la referencia documental A o B. Las cotas del ensayo se consultan en su IFC.
    </p> : null}
    <div className="relative space-y-2 md:pb-11">
      <div className={cn("grid min-w-0 gap-2", mode === "both" && "md:grid-cols-2")}>
        <Panel className={cn("h-[clamp(330px,65dvh,730px)] min-w-0 overflow-hidden", mode === "model" && "hidden")}>
          <PdfPanel key={pdf} url={pdf} compactNavigation fields={measures}
            selectedPath={selectedPath} selectedId={subject || null} hoveredId={hovered}
            onSelect={field => { const item = byPath.get(field.path); if (item) showEvidence(item); }}
            onHover={field => setHovered(field?.elementId ?? null)} />
        </Panel>
        <div className={cn("min-w-0", mode === "pdf" && "hidden")}>{children}</div>
      </div>
      <ReviewDrawer title="Campos y cotas del plano" total={measures.length} open={open} onOpenChange={setOpen}
        mobileInline expanded={false}>
        {close => <div className="h-full max-h-[60dvh] overflow-auto px-3 pb-2">
          <div className="sticky top-0 z-10 flex flex-wrap items-end gap-2 border-b border-border bg-surface py-2.5">
            <label className="grid min-w-0 flex-1 gap-1 text-xs text-muted">Buscar equipo, pieza o cota
              <input type="search" value={filter} onChange={event => setFilter(event.target.value)}
                placeholder="Por ejemplo, V-110 o envolvente"
                className="h-9 rounded-md border border-border bg-canvas px-2.5 text-sm text-text" />
            </label>
            {subject ? <Button size="sm" variant="secondary" onClick={() => { setFilter(""); onSelect(""); setRequestedPath(null); }}>
              <Icon icon={Layers3} size={14} /> Planta general
            </Button> : null}
          </div>
          {fields.isError ? <p className="py-3 text-sm text-danger">No se pudieron cargar las cotas. <button className="underline" onClick={() => void fields.refetch()}>Reintentar</button></p>
            : fields.isPending ? <p role="status" className="py-3 text-sm text-muted">Cargando cotas…</p>
            : !visible.length ? <p className="py-3 text-sm text-muted">Ninguna cota coincide con esta selección.</p>
            : <ul className="divide-y divide-border" aria-label="Cotas del plano">
              {visible.slice(0, 100).map(field => <li key={field.path}>
                <button type="button" onClick={() => showEvidence(field, close)} aria-pressed={field.path === selectedPath}
                  className={cn("grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-2 py-2 text-left hover:bg-surface-raised",
                    field.path === selectedPath && "bg-accent-soft")}>
                  <span className="min-w-0 text-sm text-text">{field.label}</span>
                  <span className="inline-flex items-center gap-2 whitespace-nowrap font-mono text-xs text-accent-text">
                    {measureFormat.format(field.value)} {field.unit}<Icon icon={Crosshair} size={14} />
                  </span>
                  <span className="text-[11px] text-muted">Pág. {field.page}</span>
                </button>
              </li>)}
            </ul>}
          {visible.length > 100 ? <p className="py-2 text-xs text-muted">100 de {visible.length} cotas. Busca un tag completo para acotar la lista.</p> : null}
        </div>}
      </ReviewDrawer>
    </div>
  </section>;
}

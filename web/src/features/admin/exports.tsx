"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Box,
  Check,
  ChevronDown,
  Copy,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  Fingerprint,
  History,
  Layers3,
  MessageSquareWarning,
  RotateCcw,
  Search,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shell/page-header";
import { Segmented, Tip } from "@/components/ui/controls";
import { ConfidenceBar } from "@/components/ui/data";
import { Badge, Button, EmptyState, Icon, IconTile, LiveDot, Panel, PanelHeader, Skeleton, type Tone } from "@/components/ui/primitives";
import { apiEnabled, apiURL } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import type { EquipmentRow } from "@/lib/mock/api";
import { useEquipment as useEquipmentRows } from "@/lib/queries";

import { ProgressRing, SegmentBar } from "./charts";
import { DATETIME, NUM, ago, api, dayGroup, duration } from "./format";

type Format = "IFC" | "BCF" | "CSV" | "PDF";
type ExportRow = {
  fecha: string;
  formato: Format;
  alcance: string;
  huella: string;
  estado: "Aprobado" | "Borrador";
  usuario: string | null;
  archivo?: string;
  nombre?: string;
  revision_id?: string;
  /** La huella sigue coincidiendo con la revisión actual; `null` si la revisión ya no existe. */
  vigente?: boolean | null;
};
type LoteRow = {
  proyecto: string;
  job_id?: string;
  tag: string;
  revision: string;
  estado: string;
  error: string | null;
  familia?: string | null;
  lod?: number | null;
  boquillas?: number | null;
  campos?: number | null;
  pendientes?: number | null;
  segundos?: number | null;
  documentos?: string[] | null;
  documentos_con_error?: string[] | null;
  avisos_documentos?: string[] | null;
};
type RevisionSummary = {
  id: string;
  tag: string;
  revision: string;
  proyecto: string;
  dataset: "synthetic" | "real";
  huella: string;
  aprobacion: { revisor: string; fecha: string } | null;
  campos: number;
  por_estado: Record<string, number>;
  pendientes: number;
  confianza_media: number | null;
  documentos: number;
  exportaciones: number;
  ultima_exportacion: ExportRow | null;
};

const FORMATS: { id: Format; icon: LucideIcon; title: string; text: string; ext: string }[] = [
  { id: "IFC", icon: Box, title: "Modelo IFC", text: "IFC4 con GUID estable por ID, listo para el visor BIM del cliente.", ext: ".ifc" },
  { id: "PDF", icon: FileText, title: "Informe PDF", text: "Resumen de la revisión con estado, huella y la fuente de cada campo.", ext: ".pdf" },
  { id: "CSV", icon: FileSpreadsheet, title: "Campos en CSV", text: "Valor, unidad, documento, página y confianza de cada campo leído.", ext: ".csv" },
  { id: "BCF", icon: MessageSquareWarning, title: "Incidencias BCF", text: "Cambios frente a la revisión anterior como incidencias para el cliente.", ext: ".bcfzip" },
];
const FORMAT_ICON = Object.fromEntries(FORMATS.map((f) => [f.id, f.icon])) as Record<Format, LucideIcon>;

const LOTE_STATE: Record<string, { label: string; tone: Tone; color: string }> = {
  ok: { label: "Con modelo", tone: "approved", color: "var(--approved)" },
  running: { label: "En curso", tone: "accent", color: "var(--accent-strong)" },
  queued: { label: "En espera", tone: "sky", color: "var(--chip-sky)" },
  faltan_datos: { label: "Faltan datos", tone: "warning", color: "var(--warning-text)" },
  tipologia_no_soportada: { label: "Tipología no soportada", tone: "neutral", color: "var(--text-faint)" },
  error: { label: "Error", tone: "danger", color: "var(--danger)" },
  timeout: { label: "Tiempo agotado", tone: "danger", color: "color-mix(in oklab, var(--danger) 55%, var(--surface))" },
  cancelled: { label: "Cancelado", tone: "neutral", color: "var(--border-strong)" },
};
const ORDER = Object.keys(LOTE_STATE);
const RETRYABLE = new Set(["error", "timeout", "faltan_datos", "cancelled"]);
const PAGE = 40;

const identity = (row: EquipmentRow, label: string) => `${row.project_id}:${row.equipment_id}:${label}`;
const median = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
};

/** Lotes e informes (solo administradores): estado del lote, exportaciones trazables e historial. */
export function ExportsWorkspace() {
  if (apiEnabled) return <Workspace />;
  return (
    <div className="space-y-5">
      <PageHeader title="Lotes e informes" description="Sigue el lote del dataset y genera informes trazables de cada revisión." />
      <Panel>
        <EmptyState icon={FileText} title="Lotes e informes necesita la API">
          Arranca la API y define NEXT_PUBLIC_API_URL: las exportaciones salen siempre de revisiones reales.
        </EmptyState>
      </Panel>
    </div>
  );
}

function Workspace() {
  const [tab, setTab] = useState<"lote" | "informes">("lote");
  const lote = useQuery({ queryKey: ["admin-lote"], queryFn: () => api<LoteRow[]>("/admin/lote"), refetchInterval: 4000 });
  const history = useQuery({ queryKey: ["exportaciones"], queryFn: () => api<ExportRow[]>("/admin/exportaciones") });
  const tabs = [
    { id: "lote" as const, label: "Lote del dataset", icon: Database, count: lote.data?.length },
    { id: "informes" as const, label: "Informes y exportaciones", icon: FileText, count: history.data?.length },
  ];
  const baseId = useId();

  return (
    <div className="mx-auto w-full max-w-[1600px]">
      <PageHeader
        title="Lotes e informes"
        description="Sigue el procesamiento del lote del dataset y genera ficheros trazables de cada revisión, con la huella de los datos con que salen."
      />
      <div role="tablist" aria-label="Secciones" className="mb-5 flex gap-1 border-b border-border">
        {tabs.map((t) => {
          const selected = tab === t.id;
          return (
            <button
              key={t.id}
              id={`${baseId}-${t.id}`}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`${baseId}-${t.id}-panel`}
              onClick={() => setTab(t.id)}
              className={cn(
                "relative -mb-px inline-flex min-h-11 items-center gap-2 px-3 text-[13px] transition-colors sm:min-h-10",
                selected ? "font-medium text-strong" : "text-muted hover:text-text",
              )}
            >
              <Icon icon={t.icon} size={15} />
              {t.label}
              {t.count != null ? (
                <span className={cn("rounded-full px-1.5 text-[11px] tabular-nums", selected ? "bg-accent-soft text-accent-text" : "bg-surface-sunken text-muted")}>
                  {NUM.format(t.count)}
                </span>
              ) : null}
              {selected ? <motion.span layoutId={`${baseId}-tab`} className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" transition={{ type: "spring", duration: 0.3, bounce: 0.1 }} /> : null}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${baseId}-${tab}-panel`} aria-labelledby={`${baseId}-${tab}`}>
        {tab === "lote" ? <LoteView query={lote} /> : <ReportsView history={history} />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------ */
/* Lote del dataset                                                                           */
/* ------------------------------------------------------------------------------------------ */

type SortKey = "tag" | "estado" | "boquillas" | "segundos";

function LoteView({ query }: { query: UseQueryResult<LoteRow[]> }) {
  const qc = useQueryClient();
  const rows = useMemo(() => query.data ?? [], [query.data]);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "estado", dir: 1 });
  const [limit, setLimit] = useState(PAGE);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) c[r.estado] = (c[r.estado] ?? 0) + 1;
    return c;
  }, [rows]);
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const list = rows.filter(
      (r) => (!state || r.estado === state) && (!term || r.tag.toLowerCase().includes(term) || (r.familia ?? "").toLowerCase().includes(term) || r.revision.toLowerCase().includes(term)),
    );
    const value = (r: LoteRow): number | string =>
      sort.key === "tag" ? r.tag : sort.key === "estado" ? ORDER.indexOf(r.estado) : sort.key === "boquillas" ? (r.boquillas ?? -1) : (r.segundos ?? -1);
    return list.sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      const primary = typeof va === "string" ? va.localeCompare(vb as string, "es", { numeric: true }) : va - (vb as number);
      return primary * sort.dir || a.tag.localeCompare(b.tag, "es", { numeric: true });
    });
  }, [rows, search, state, sort]);
  const retryable = filtered.filter((r) => RETRYABLE.has(r.estado));

  const retry = useMutation({
    mutationFn: (row: LoteRow) =>
      api("/admin/lote/reintentar", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ proyecto: row.proyecto, tag: row.tag, revision: row.revision }),
      }),
    onSuccess: (_, row) => {
      toast.success(`${row.tag} rev ${row.revision} en cola`);
      void qc.invalidateQueries({ queryKey: ["admin-lote"] });
    },
    onError: (e: Error, row) => toast.error(`${row.tag} rev ${row.revision}: ${e.message}`),
  });
  const retryAll = useMutation({
    mutationFn: async (list: LoteRow[]) => {
      let ok = 0;
      for (const row of list) {
        try {
          await api("/admin/lote/reintentar", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
            body: JSON.stringify({ proyecto: row.proyecto, tag: row.tag, revision: row.revision }),
          });
          ok++;
        } catch {
          /* Se cuenta abajo: la fila sigue marcada con su motivo. */
        }
      }
      return { ok, total: list.length };
    },
    onSuccess: ({ ok, total }) => {
      if (ok === total) toast.success(`${NUM.format(ok)} revisiones en cola`);
      else toast.warning(`${NUM.format(ok)} de ${NUM.format(total)} revisiones en cola; el resto conserva su motivo`);
      void qc.invalidateQueries({ queryKey: ["admin-lote"] });
    },
  });

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-[148px] rounded-[var(--radius-panel)]" />
        <Skeleton className="h-[420px] rounded-[var(--radius-panel)]" />
      </div>
    );
  }
  if (query.isError && !rows.length) {
    return (
      <Panel>
        <EmptyState icon={AlertTriangle} title="No se pudo leer el lote" action={<Button onClick={() => void query.refetch()}>Reintentar</Button>}>
          Comprueba la conexión con la API.
        </EmptyState>
      </Panel>
    );
  }
  if (!rows.length) {
    return (
      <Panel>
        <EmptyState icon={Database} title="Todavía no hay revisiones en el lote">
          Procesa el dataset con <code className="font-mono text-[12px]">trazia lote</code> y define TRAZIA_LOTE en la API para verlo aquí.
        </EmptyState>
      </Panel>
    );
  }

  const toggleSort = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === "tag" || key === "estado" ? 1 : -1 }));

  return (
    <div className="space-y-4">
      <LoteSummary rows={rows} counts={counts} stale={query.isError} />

      <Panel className="min-w-0 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <label className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <span className="sr-only">Buscar en el lote</span>
            <Icon icon={Search} size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setLimit(PAGE);
              }}
              placeholder="Equipo, revisión o familia"
              className="h-9 w-full rounded-[var(--radius-control)] border border-border bg-surface-sunken pr-3 pl-9 text-[13px] text-text placeholder:text-faint focus:border-accent focus:outline-none max-sm:min-h-11"
            />
          </label>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por estado">
            <FilterChip active={!state} onClick={() => setState(null)} label="Todas" count={rows.length} />
            {ORDER.filter((s) => counts[s]).map((s) => (
              <FilterChip
                key={s}
                active={state === s}
                onClick={() => {
                  setState(state === s ? null : s);
                  setLimit(PAGE);
                }}
                label={LOTE_STATE[s]!.label}
                count={counts[s]!}
                color={LOTE_STATE[s]!.color}
              />
            ))}
            {Object.keys(counts)
              .filter((s) => !LOTE_STATE[s])
              .map((s) => (
                <FilterChip key={s} active={state === s} onClick={() => setState(state === s ? null : s)} label={s} count={counts[s]!} />
              ))}
          </div>
          {retryable.length ? (
            <Button size="sm" variant="secondary" className="ml-auto" disabled={retryAll.isPending} onClick={() => retryAll.mutate(retryable)}>
              <Icon icon={RotateCcw} size={13} className={cn(retryAll.isPending && "motion-safe:animate-spin")} />
              {retryAll.isPending ? "Reintentando…" : `Reintentar ${NUM.format(retryable.length)} con fallo`}
            </Button>
          ) : null}
        </div>

        {filtered.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-left text-[13px]">
              <thead className="bg-surface-sunken/60 text-[11px] tracking-wide text-faint uppercase">
                <tr>
                  <SortHeader label="Equipo" active={sort.key === "tag"} dir={sort.dir} onClick={() => toggleSort("tag")} className="pl-5" />
                  <SortHeader label="Estado" active={sort.key === "estado"} dir={sort.dir} onClick={() => toggleSort("estado")} />
                  <th scope="col" className="px-3 py-2.5 font-medium">Familia</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Documentos</th>
                  <SortHeader label="Boquillas" active={sort.key === "boquillas"} dir={sort.dir} onClick={() => toggleSort("boquillas")} align="right" />
                  <th scope="col" className="px-3 py-2.5 font-medium">Campos</th>
                  <SortHeader label="Tiempo" active={sort.key === "segundos"} dir={sort.dir} onClick={() => toggleSort("segundos")} align="right" />
                  <th scope="col" className="py-2.5 pr-5 pl-3 text-right font-medium">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, limit).map((r) => (
                  <LoteTableRow key={`${r.proyecto}:${r.tag}:${r.revision}`} row={r} onRetry={() => retry.mutate(r)} retrying={retry.isPending && retry.variables === r} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={Search} title="Ninguna revisión coincide con los filtros" action={<Button size="sm" onClick={() => { setSearch(""); setState(null); }}>Quitar filtros</Button>} />
        )}
        {filtered.length > limit ? (
          <div className="flex items-center justify-between border-t border-border px-5 py-3 text-xs text-muted">
            <span>
              Mostrando {NUM.format(limit)} de {NUM.format(filtered.length)}
            </span>
            <Button size="sm" variant="ghost" onClick={() => setLimit(limit + PAGE)}>
              Mostrar {NUM.format(Math.min(PAGE, filtered.length - limit))} más
            </Button>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function LoteSummary({ rows, counts, stale }: { rows: LoteRow[]; counts: Record<string, number>; stale: boolean }) {
  const ok = counts.ok ?? 0;
  const active = (counts.running ?? 0) + (counts.queued ?? 0);
  const nozzles = rows.reduce((a, r) => a + (r.boquillas ?? 0), 0);
  const pending = rows.reduce((a, r) => a + (r.pendientes ?? 0), 0);
  const hasFields = rows.some((r) => r.campos != null);
  const time = median(rows.map((r) => r.segundos).filter((s): s is number => s != null && s > 0));
  const unresolved = rows.length - ok - active;
  return (
    <Panel className="grid gap-6 p-5 lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:items-center">
      <div className="flex items-center gap-4">
        <ProgressRing value={rows.length ? ok / rows.length : 0} size={96}>
          <span className="text-[20px] leading-none font-semibold text-strong tabular-nums">{Math.round((ok / rows.length) * 100)} %</span>
          <span className="mt-0.5 text-[10px] text-muted">con modelo</span>
        </ProgressRing>
        <div className="lg:hidden">
          <SummaryTitle ok={ok} total={rows.length} unresolved={unresolved} active={active} stale={stale} />
        </div>
      </div>
      <div className="min-w-0">
        <div className="hidden lg:block">
          <SummaryTitle ok={ok} total={rows.length} unresolved={unresolved} active={active} stale={stale} />
        </div>
        <SegmentBar
          className="mt-4"
          segments={[...ORDER, ...Object.keys(counts).filter((s) => !LOTE_STATE[s])]
            .filter((s) => counts[s])
            .map((s) => ({ key: s, label: LOTE_STATE[s]?.label ?? s, value: counts[s]!, color: LOTE_STATE[s]?.color ?? "var(--border-strong)" }))}
        />
      </div>
      <dl className="grid grid-cols-3 gap-3 lg:w-[360px] lg:border-l lg:border-border lg:pl-6">
        <MiniStat label="Boquillas" value={NUM.format(nozzles)} hint="detectadas en el lote" />
        <MiniStat label="Por revisar" value={hasFields ? NUM.format(pending) : "—"} hint="campos sin confirmar" />
        <MiniStat label="Mediana" value={duration(time)} hint="por revisión" />
      </dl>
    </Panel>
  );
}

function SummaryTitle({ ok, total, unresolved, active, stale }: { ok: number; total: number; unresolved: number; active: number; stale: boolean }) {
  return (
    <>
      <p className="text-[17px] font-semibold text-strong">
        {NUM.format(ok)} de {NUM.format(total)} revisiones tienen modelo IFC
      </p>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
        {unresolved ? <span>{NUM.format(unresolved)} sin resolver</span> : <span className="text-approved">Todo el lote resuelto</span>}
        {active ? (
          <span className="inline-flex items-center gap-1.5 text-text">
            <LiveDot /> {NUM.format(active)} procesándose ahora
          </span>
        ) : null}
        {stale ? <span className="text-warning">No se pudo actualizar; se muestran los últimos datos</span> : null}
      </p>
    </>
  );
}

function MiniStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-faint">{label}</dt>
      <dd className="mt-0.5 truncate text-[18px] leading-tight font-semibold text-strong tabular-nums">{value}</dd>
      <dd className="truncate text-[11px] text-muted">{hint}</dd>
    </div>
  );
}

function FilterChip({ active, onClick, label, count, color }: { active: boolean; onClick: () => void; label: string; count: number; color?: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors max-sm:min-h-11",
        active ? "border-accent/50 bg-accent-soft text-accent-text" : "border-border bg-surface text-muted hover:border-border-strong hover:text-text",
      )}
    >
      {color ? <span className="size-2 rounded-full" style={{ background: color }} aria-hidden /> : null}
      {label}
      <span className={cn("tabular-nums", active ? "text-accent-text" : "text-faint")}>{NUM.format(count)}</span>
    </button>
  );
}

function SortHeader({ label, active, dir, onClick, align = "left", className }: { label: string; active: boolean; dir: 1 | -1; onClick: () => void; align?: "left" | "right"; className?: string }) {
  return (
    <th scope="col" aria-sort={active ? (dir === 1 ? "ascending" : "descending") : "none"} className={cn("px-3 py-2.5 font-medium", align === "right" && "text-right", className)}>
      <button type="button" onClick={onClick} className={cn("inline-flex items-center gap-1 uppercase hover:text-text", active && "text-text")}>
        {label}
        <Icon icon={active && dir === -1 ? ArrowDown : ArrowUp} size={11} className={cn(!active && "opacity-0")} />
      </button>
    </th>
  );
}

function LoteTableRow({ row: r, onRetry, retrying }: { row: LoteRow; onRetry: () => void; retrying: boolean }) {
  const meta = LOTE_STATE[r.estado];
  const docs = r.documentos?.length ?? null;
  const broken = r.documentos_con_error ?? [];
  const warnings = r.avisos_documentos ?? [];
  const active = r.estado === "running" || r.estado === "queued";
  return (
    <tr className="group border-t border-border align-top transition-colors hover:bg-surface-sunken/50">
      <td className="py-3 pr-3 pl-5">
        <p className="flex items-center gap-2">
          <span className="font-mono font-medium text-strong">{r.tag}</span>
          <span className="rounded-[5px] border border-border px-1.5 font-mono text-[11px] text-muted">rev {r.revision}</span>
        </p>
        <p className="mt-0.5 text-[11px] text-faint">{r.proyecto}</p>
      </td>
      <td className="max-w-[340px] px-3 py-3">
        <Badge tone={meta?.tone ?? "neutral"}>
          {active ? <LiveDot className="mr-0.5" /> : null}
          {meta?.label ?? r.estado}
        </Badge>
        {r.error && r.estado !== "ok" ? (
          <Tip content={<span className="block max-w-[48ch] whitespace-pre-wrap">{r.error}</span>}>
            <p className="mt-1 line-clamp-2 cursor-help text-xs text-muted">{r.error}</p>
          </Tip>
        ) : null}
      </td>
      <td className="px-3 py-3">
        {r.familia ? (
          <>
            <p className="text-text">{r.familia.replaceAll("_", " ")}</p>
            {r.lod != null ? <p className="text-[11px] text-faint">nivel de detalle {r.lod}</p> : null}
          </>
        ) : (
          <span className="text-faint">—</span>
        )}
      </td>
      <td className="px-3 py-3">
        {docs == null ? (
          <span className="text-faint">—</span>
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <span className="tabular-nums">{NUM.format(docs)}</span>
            {broken.length || warnings.length ? (
              <Tip
                content={
                  <span className="block max-w-[48ch] space-y-1">
                    {broken.length ? <span className="block">Sin leer: {broken.join(", ")}</span> : null}
                    {warnings.map((w) => (
                      <span key={w} className="block text-muted">{w}</span>
                    ))}
                  </span>
                }
              >
                <span className={cn("inline-flex items-center gap-0.5 text-xs", broken.length ? "text-danger" : "text-warning")}>
                  <Icon icon={AlertTriangle} size={13} />
                  {broken.length ? NUM.format(broken.length) : NUM.format(warnings.length)}
                </span>
              </Tip>
            ) : null}
          </span>
        )}
      </td>
      <td className="px-3 py-3 text-right font-medium tabular-nums">{r.boquillas != null ? NUM.format(r.boquillas) : <span className="text-faint">—</span>}</td>
      <td className="px-3 py-3">
        {r.campos ? (
          <div className="w-28">
            <p className="text-xs text-muted">
              <span className="font-medium text-text tabular-nums">{NUM.format(r.campos - (r.pendientes ?? 0))}</span>/{NUM.format(r.campos)} revisados
            </p>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-surface-sunken">
              <div className="h-full rounded-full bg-approved" style={{ width: `${((r.campos - (r.pendientes ?? 0)) / r.campos) * 100}%` }} />
            </div>
          </div>
        ) : (
          <span className="text-faint">—</span>
        )}
      </td>
      <td className="px-3 py-3 text-right text-muted tabular-nums">{r.segundos ? duration(r.segundos) : "—"}</td>
      <td className="py-3 pr-5 pl-3 text-right whitespace-nowrap">
        {RETRYABLE.has(r.estado) ? (
          <Button size="sm" variant="secondary" disabled={retrying} onClick={onRetry}>
            <Icon icon={RotateCcw} size={13} className={cn(retrying && "motion-safe:animate-spin")} />
            Reintentar
          </Button>
        ) : r.job_id ? (
          <Link
            href={`/pipeline?trabajo=${encodeURIComponent(r.job_id)}`}
            className="inline-flex h-7 items-center gap-1 rounded-[var(--radius-control)] px-2 text-xs font-medium text-accent-text hover:bg-accent-soft max-sm:min-h-11"
          >
            Ver trabajo <Icon icon={ArrowUpRight} size={13} />
          </Link>
        ) : null}
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------------------------------ */
/* Informes y exportaciones                                                                   */
/* ------------------------------------------------------------------------------------------ */

function ReportsView({ history }: { history: UseQueryResult<ExportRow[]> }) {
  const rows = useEquipmentRows();
  const withModel = (rows.data ?? []).filter((r) => r.project_id && r.equipment_id);
  const [key, setKey] = useState("");
  const equipment = withModel.find((r) => `${r.project_id}:${r.tag}` === key) ?? withModel[0];
  const [chosen, setChosen] = useState("");
  const labels = equipment?.revisions ?? [];
  const label = labels.includes(chosen) ? chosen : (labels[labels.length - 1] ?? "");
  const previousLabel = labels[labels.indexOf(label) - 1] ?? null;
  const revisionId = equipment && label ? identity(equipment, label) : null;
  const previousId = equipment && previousLabel ? identity(equipment, previousLabel) : null;
  const qc = useQueryClient();

  const summary = useQuery({
    queryKey: ["export-resumen", revisionId],
    enabled: !!revisionId,
    queryFn: () => api<RevisionSummary>(`/admin/revisiones/${encodeURIComponent(revisionId!)}/resumen`),
  });

  const exportFile = useMutation({
    mutationFn: async (format: Format) => {
      const recorded = await api<ExportRow>("/admin/exportaciones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ formato: format, revision_id: revisionId, previous_id: format === "BCF" ? previousId : null }),
      });
      const link = document.createElement("a");
      link.href = apiURL(`/admin/exportaciones/${recorded.archivo}/archivo`);
      link.download = recorded.nombre ?? "";
      document.body.append(link);
      link.click();
      link.remove();
      return recorded;
    },
    onSuccess: (row) => {
      toast.success(`${row.formato} exportado`, { description: `${row.alcance} · ${row.estado === "Aprobado" ? "APROBADO" : "DRAFT"}` });
      void qc.invalidateQueries({ queryKey: ["exportaciones"] });
      void qc.invalidateQueries({ queryKey: ["export-resumen", revisionId] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "No se pudo exportar"),
  });

  if (rows.isLoading) return <Skeleton className="h-[520px] rounded-[var(--radius-panel)]" />;

  return (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,1fr)] xl:items-start">
      <Panel className="min-w-0">
        <PanelHeader title="Nuevo informe" description="Elige la revisión y el formato. Cada fichero queda registrado con la huella de sus datos." />
        {!withModel.length ? (
          <EmptyState icon={Layers3} title="No hay revisiones con modelo">
            Procesa un equipo en el pipeline para poder exportarlo.
          </EmptyState>
        ) : (
          <div className="space-y-5 px-5 pb-5">
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[200px] flex-1 sm:max-w-xs">
                <span className="mb-1 block text-xs font-medium text-muted">Equipo</span>
                <span className="relative block">
                  <select
                    value={equipment ? `${equipment.project_id}:${equipment.tag}` : ""}
                    onChange={(e) => {
                      setKey(e.target.value);
                      setChosen("");
                    }}
                    className="h-9 w-full appearance-none rounded-[var(--radius-control)] border border-border bg-surface-sunken pr-8 pl-3 font-mono text-[13px] text-text focus:border-accent focus:outline-none max-sm:min-h-11"
                  >
                    {withModel.map((r) => (
                      <option key={`${r.project_id}:${r.tag}`} value={`${r.project_id}:${r.tag}`}>
                        {r.tag} · {r.project_id}
                      </option>
                    ))}
                  </select>
                  <Icon icon={ChevronDown} size={14} className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-faint" />
                </span>
              </label>
              {labels.length ? (
                <div>
                  <span className="mb-1 block text-xs font-medium text-muted">Revisión</span>
                  <Segmented<string> label="Revisión" value={label} onChange={setChosen} options={labels.map((l) => ({ value: l, label: `rev ${l}` }))} />
                </div>
              ) : null}
            </div>

            <RevisionCard query={summary} />

            <div>
              <p className="mb-2 text-xs font-medium text-muted">Formato</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {FORMATS.map((f) => {
                  const blocked = f.id === "BCF" && !previousId;
                  const pending = exportFile.isPending && exportFile.variables === f.id;
                  const approved = Boolean(summary.data?.aprobacion);
                  return (
                    <div
                      key={f.id}
                      className={cn(
                        "lift flex flex-col rounded-[var(--radius-card)] border border-border bg-surface-raised p-4",
                        blocked && "opacity-70",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <IconTile icon={f.icon} tone="sky" shape="tile" size="sm" />
                        <div className="min-w-0 flex-1">
                          <p className="flex items-center gap-2 text-[14px] font-semibold text-strong">
                            {f.title}
                            <span className="font-mono text-[11px] font-normal text-faint">{f.ext}</span>
                          </p>
                          <p className="mt-0.5 text-xs text-muted">{f.text}</p>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-2">
                        {blocked ? (
                          <span className="text-[11px] text-warning">Necesita una revisión anterior del mismo equipo</span>
                        ) : f.id === "BCF" ? (
                          <span className="text-[11px] text-faint">rev {previousLabel} → {label}</span>
                        ) : (
                          <span className={cn("text-[11px] font-medium", approved ? "text-approved" : "text-warning")}>{approved ? "Sale como APROBADO" : "Sale como DRAFT"}</span>
                        )}
                        <Button size="sm" variant={f.id === "IFC" ? "primary" : "secondary"} disabled={!revisionId || blocked || exportFile.isPending} onClick={() => exportFile.mutate(f.id)}>
                          <Icon icon={Download} size={13} className={cn(pending && "motion-safe:animate-bounce")} />
                          {pending ? "Generando…" : "Exportar"}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </Panel>

      <HistoryPanel query={history} focus={summary.data ? { id: summary.data.id, label: `${summary.data.tag} rev ${summary.data.revision}` } : null} />
    </div>
  );
}

function RevisionCard({ query }: { query: UseQueryResult<RevisionSummary> }) {
  const [copied, setCopied] = useState(false);
  const data = query.data;
  if (query.isLoading) return <Skeleton className="h-[188px] rounded-[var(--radius-card)]" />;
  if (query.isError || !data) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border p-4 text-[13px] text-muted">
        No se pudo leer el resumen de la revisión. {query.error instanceof Error ? query.error.message : ""}
      </div>
    );
  }
  const reviewed = data.campos - data.pendientes;
  const last = data.ultima_exportacion;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.huella);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      toast.error("No se pudo copiar la huella");
    }
  };
  return (
    <div className="overflow-hidden rounded-[var(--radius-card)] border border-border">
      {data.aprobacion ? (
        <div className="flex items-start gap-3 bg-approved-soft px-4 py-3 text-[13px]">
          <Icon icon={ShieldCheck} size={18} className="mt-0.5 text-approved" />
          <p className="text-text">
            <span className="font-semibold text-approved">Aprobada</span> por {data.aprobacion.revisor} · {DATETIME.format(new Date(data.aprobacion.fecha))}
            <span className="block text-xs text-muted">La aprobación está ligada a esta huella: los ficheros salen como APROBADO tras verificar los originales.</span>
          </p>
        </div>
      ) : (
        <div className="flex items-start gap-3 border-b border-warning-border bg-warning-bg px-4 py-3 text-[13px]">
          <Icon icon={AlertTriangle} size={18} className="mt-0.5 text-warning" />
          <p className="flex-1 text-text">
            <span className="font-semibold text-warning">Borrador</span> · los ficheros salen marcados como DRAFT.
            <span className="block text-xs text-muted">
              {data.pendientes ? `${NUM.format(data.pendientes)} campos esperan revisión humana antes de poder aprobarla.` : "Todos los campos están revisados: falta la aprobación."}
            </span>
          </p>
          <Link href="/revision" className="shrink-0 self-center text-xs font-medium text-accent-text hover:underline">
            Revisar
          </Link>
        </div>
      )}
      <dl className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
        <Fact label="Campos trazados" value={NUM.format(data.campos)} />
        <Fact label="Revisados">
          <span className="text-[17px] font-semibold text-strong tabular-nums">{data.campos ? Math.round((reviewed / data.campos) * 100) : 0} %</span>
          <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-surface-sunken">
            <motion.span
              className="block h-full rounded-full bg-approved"
              initial={{ width: 0 }}
              animate={{ width: `${data.campos ? (reviewed / data.campos) * 100 : 0}%` }}
              transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
            />
          </span>
        </Fact>
        <Fact label="Confianza media">
          {data.confianza_media != null ? <ConfidenceBar value={data.confianza_media} className="mt-1" /> : <span className="text-faint">—</span>}
        </Fact>
        <Fact label="Documentos fuente" value={NUM.format(data.documentos)} />
      </dl>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border px-4 py-2.5 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <Icon icon={Fingerprint} size={14} />
          Huella
          <code className="font-mono text-text">{data.huella}</code>
          <Tip content={copied ? "Copiada" : "Copiar huella"}>
            <button type="button" onClick={() => void copy()} aria-label="Copiar huella" className="inline-flex size-6 items-center justify-center rounded-[5px] hover:bg-surface-sunken hover:text-text">
              <Icon icon={copied ? Check : Copy} size={12} className={cn(copied && "text-approved")} />
            </button>
          </Tip>
        </span>
        {data.dataset === "synthetic" ? <Badge tone="warning">ilustrativo</Badge> : null}
        <span className="ml-auto inline-flex items-center gap-1.5">
          <Icon icon={History} size={13} />
          {last ? (
            <>
              Última exportación {ago(last.fecha)} ·{" "}
              {last.vigente ? <span className="text-approved">vigente</span> : <span className="text-revision">datos cambiados después</span>}
            </>
          ) : (
            "Sin exportaciones previas"
          )}
        </span>
      </div>
    </div>
  );
}

function Fact({ label, value, children }: { label: string; value?: string; children?: React.ReactNode }) {
  return (
    <div className="bg-surface px-4 py-3">
      <dt className="text-[11px] text-faint">{label}</dt>
      <dd className="mt-0.5">{value != null ? <span className="text-[17px] font-semibold text-strong tabular-nums">{value}</span> : children}</dd>
    </div>
  );
}

function HistoryPanel({ query, focus }: { query: UseQueryResult<ExportRow[]>; focus: { id: string; label: string } | null }) {
  const [format, setFormat] = useState<"all" | Format>("all");
  const [onlyFocus, setOnlyFocus] = useState(false);
  const all = query.data ?? [];
  const list = all.filter((e) => (format === "all" || e.formato === format) && (!onlyFocus || !focus || e.revision_id === focus.id));
  const groups = useMemo(() => {
    const map = new Map<string, ExportRow[]>();
    for (const e of list) {
      const g = dayGroup(e.fecha);
      map.set(g, [...(map.get(g) ?? []), e]);
    }
    return [...map.entries()];
  }, [list]);
  const stale = all.filter((e) => e.vigente === false).length;

  return (
    <Panel className="flex min-w-0 flex-col xl:sticky xl:top-4 xl:max-h-[calc(100dvh-var(--topbar-height)-2rem)]">
      <PanelHeader
        title="Historial"
        description={stale ? `${NUM.format(stale)} ficheros ya no coinciden con los datos actuales.` : "Cada fichero guarda la huella de los datos con que se generó."}
      />
      <div className="flex flex-wrap items-center gap-2 px-5 pb-3">
        <Segmented<"all" | Format>
          label="Formato"
          value={format}
          onChange={setFormat}
          options={[{ value: "all", label: "Todos" }, ...FORMATS.map((f) => ({ value: f.id, label: f.id }))]}
        />
        {focus ? <FilterChip active={onlyFocus} onClick={() => setOnlyFocus(!onlyFocus)} label={`Solo ${focus.label}`} count={all.filter((e) => e.revision_id === focus.id).length} /> : null}
      </div>
      {query.isLoading ? (
        <div className="space-y-2 px-5 pb-5">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}
        </div>
      ) : !list.length ? (
        <EmptyState icon={History} title={all.length ? "Nada con estos filtros" : "Todavía no se ha exportado nada"}>
          {all.length ? null : "Los ficheros que generes aparecerán aquí, listos para volver a descargarlos."}
        </EmptyState>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {groups.map(([group, items]) => (
            <section key={group} className="mb-2">
              <h3 className="sticky top-0 z-[1] bg-surface px-2 py-1.5 text-[11px] font-medium tracking-wide text-faint uppercase">{group}</h3>
              <ul className="space-y-0.5">
                {items.map((e, i) => (
                  <li key={`${e.fecha}-${e.archivo ?? i}`} className="group flex items-center gap-3 rounded-[var(--radius-control)] px-2 py-2 transition-colors hover:bg-surface-sunken">
                    <IconTile icon={FORMAT_ICON[e.formato] ?? FileText} tone={e.estado === "Aprobado" ? "approved" : "neutral"} shape="tile" size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px]">
                        <span className="truncate font-medium text-text">{e.alcance}</span>
                        <span className="font-mono text-[10px] text-faint">{e.formato}</span>
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-faint">
                        <time dateTime={e.fecha} title={DATETIME.format(new Date(e.fecha))}>
                          {ago(e.fecha)}
                        </time>
                        {e.usuario ? <span>· {e.usuario}</span> : null}
                        <span>·</span>
                        <code className="font-mono">{e.huella}</code>
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {e.vigente === false ? (
                        <Tip content="Los datos de la revisión han cambiado desde que se generó este fichero">
                          <span>
                            <Badge tone="revision">Desactualizado</Badge>
                          </span>
                        </Tip>
                      ) : (
                        <Badge tone={e.estado === "Aprobado" ? "approved" : "neutral"}>{e.estado === "Aprobado" ? "Aprobado" : "DRAFT"}</Badge>
                      )}
                      {e.archivo ? (
                        <Tip content={`Descargar ${e.nombre ?? e.formato}`}>
                          <a
                            href={apiURL(`/admin/exportaciones/${e.archivo}/archivo`)}
                            download={e.nombre}
                            aria-label={`Descargar ${e.nombre ?? e.formato}`}
                            className="inline-flex size-8 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-surface hover:text-accent-text max-sm:size-11"
                          >
                            <Icon icon={Download} size={15} />
                          </a>
                        </Tip>
                      ) : (
                        <Tip content="Sin copia guardada">
                          <span className="inline-flex size-8 items-center justify-center text-faint">
                            <Icon icon={Download} size={15} className="opacity-40" />
                          </span>
                        </Tip>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Panel>
  );
}

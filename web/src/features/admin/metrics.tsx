"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BrainCircuit,
  CheckCircle2,
  CircleGauge,
  FileText,
  Layers3,
  Pause,
  Play,
  RefreshCw,
  ScanText,
  ShieldCheck,
  Timer,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Stagger } from "@/components/motion/reveal";
import { PageHeader } from "@/components/shell/page-header";
import { Segmented, Tip } from "@/components/ui/controls";
import { Badge, Button, EmptyState, Icon, LiveDot, Panel, PanelHeader, Skeleton, type Tone } from "@/components/ui/primitives";
import { STAGE_ICON } from "@/features/pipeline/stage-meta";
import { apiEnabled } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { STAGES } from "@/lib/mock/pipeline";

import { Delta, MiniBars, ProgressRing, SegmentBar, SeriesSwatch, StatCard, TrendChart, type TrendSeries } from "./charts";
import { DATETIME, EUR, NUM, ago, api, compact, duration, initials, sum } from "./format";

type Job = { id: string; equipo: string; tipo: string; estado: string; fecha: string; autor: string | null };
type Revision = { id: string; equipo: string; proyecto: string; revision: string; accion: string; fecha: string; autor: string | null };
type Provider = {
  llamadas: number;
  tokens_in: number | null;
  tokens_out: number | null;
  coste_eur: number | null;
  coste_serie: (number | null)[];
  tokens_serie: (number | null)[];
  p50_s: number | null;
};
type Failure = { id: string; equipo: string; tipo?: string; estado: string; motivo: string | null; fecha?: string };
type Metrics = {
  generado: string;
  intervalos: string[];
  trabajos: {
    total: number;
    activos: number;
    en_cola: number;
    en_ejecucion: number;
    por_estado: Record<string, number>;
    p50_s: number | null;
    p95_s: number | null;
    por_hora: number[];
    finalizados_por_hora: number[];
    errores_por_hora: number[];
    recientes: Job[];
    cache: number;
  };
  /** Ausente con una API anterior: las tarjetas muestran «sin referencia». */
  anterior?: { trabajos: number; finalizados: number; errores: number; p50_s: number | null; llamadas: number };
  errores: Failure[];
  duraciones: Record<string, number[]>;
  etapas: Record<string, Record<string, number>>;
  revisiones: { total: number; aprobadas: number; recientes: Revision[] };
  modelos: { llamadas: number; envios_externos: number; por_proveedor: Record<string, Provider>; por_hora: number[] };
};

type Range = "1h" | "24h" | "7d";
const RANGES: { value: Range; label: string; step: number; previous: string }[] = [
  { value: "1h", label: "1 h", step: 5 / 60, previous: "la hora anterior" },
  { value: "24h", label: "24 h", step: 1, previous: "las 24 h anteriores" },
  { value: "7d", label: "7 días", step: 24, previous: "la semana anterior" },
];

const JOB_STATE: Record<string, { label: string; color: string; tone: Tone }> = {
  done: { label: "Finalizados", color: "var(--approved)", tone: "approved" },
  running: { label: "En ejecución", color: "var(--accent-strong)", tone: "accent" },
  queued: { label: "En cola", color: "var(--text-faint)", tone: "neutral" },
  error: { label: "Error", color: "var(--danger)", tone: "danger" },
  timeout: { label: "Tiempo agotado", color: "var(--warning-text)", tone: "warning" },
  cancelled: { label: "Cancelados", color: "var(--border-strong)", tone: "neutral" },
};
const JOB_KIND: Record<string, string> = {
  pipeline: "Pipeline",
  design_preview: "Borrador de diseño",
  ga_drawing: "Plano GA",
  study: "Estudio",
};
const REVISION_VERB: Record<string, string> = { creada: "generó", actualizada: "editó", aprobada: "aprobó" };
const DURATION_BINS = ["< 1 s", "1–5 s", "5–15 s", "15–60 s", "≥ 60 s"];

/** Nombre e icono de cada etapa, en el orden del pipeline; las que no conoce van al final. */
const STAGE_META: Record<string, { name: string; icon: LucideIcon; order: number }> = Object.fromEntries([
  ...STAGES.map((s, i) => [s.code, { name: s.name, icon: STAGE_ICON[s.id], order: i }] as const),
  ["extract", { name: "Lectura", icon: ScanText, order: 2.5 }],
  ["drawing", { name: "Plano GA", icon: FileText, order: 99 }],
]);

export function MetricsDashboard() {
  if (!apiEnabled)
    return (
      <EmptyState icon={Activity} title="Las métricas necesitan la API">
        Conecta la API para consultar la actividad registrada.
      </EmptyState>
    );
  return <Dashboard />;
}

function Dashboard() {
  const [range, setRange] = useState<Range>("24h");
  const [live, setLive] = useState(true);
  const query = useQuery({
    queryKey: ["admin-metricas", range],
    refetchInterval: live ? 15_000 : false,
    refetchOnWindowFocus: live,
    queryFn: ({ signal }) => api<Metrics>(`/admin/metricas?rango=${range}`, { signal }),
  });
  const data = query.data;
  const period = RANGES.find((r) => r.value === range)!;

  return (
    <div className="mx-auto w-full max-w-[1600px]">
      <PageHeader
        title="Métricas"
        description="Salud de la plataforma en directo: cola de trabajos, calidad del pipeline por etapa, modelos de lenguaje y revisiones."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <LiveStatus live={live} onToggle={() => setLive(!live)} updatedAt={query.dataUpdatedAt} />
            <Segmented<Range> label="Periodo" value={range} onChange={setRange} options={RANGES.map((r) => ({ value: r.value, label: r.label }))} />
            <Tip content="Actualizar ahora">
              <Button size="sm" variant="secondary" aria-label="Actualizar ahora" onClick={() => void query.refetch()} disabled={query.isFetching} className="w-8 px-0">
                <Icon icon={RefreshCw} size={14} className={cn(query.isFetching && "motion-safe:animate-spin")} />
              </Button>
            </Tip>
          </div>
        }
      />
      {query.isError && !data ? (
        <Panel>
          <EmptyState icon={AlertTriangle} title="No se pudieron leer las métricas" action={<Button onClick={() => void query.refetch()}>Reintentar</Button>}>
            Comprueba la conexión con la API y que tu cuenta sea de administración.
          </EmptyState>
        </Panel>
      ) : !data ? (
        <Loading />
      ) : (
        <Content key={range} data={data} step={period.step} previousLabel={period.previous} />
      )}
    </div>
  );
}

function LiveStatus({ live, onToggle, updatedAt }: { live: boolean; onToggle: () => void; updatedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);
  const seconds = updatedAt ? Math.max(0, Math.round((now - updatedAt) / 1000)) : null;
  return (
    <Tip content={live ? "Se actualiza cada 15 s. Pulsa para pausar." : "Pulsa para reanudar la actualización automática."}>
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={live}
        className="inline-flex h-8 items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs text-muted transition-colors hover:text-text max-sm:min-h-11"
      >
        {live ? <LiveDot /> : <Icon icon={Pause} size={12} />}
        <span className="font-medium text-text">{live ? "En directo" : "En pausa"}</span>
        {seconds !== null ? <span className="hidden sm:inline">· {seconds < 5 ? "ahora" : `hace ${seconds} s`}</span> : null}
        <Icon icon={live ? Pause : Play} size={12} className="opacity-60" />
      </button>
    </Tip>
  );
}

function Loading() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[150px] rounded-[var(--radius-panel)]" />)}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Skeleton className="h-[330px] rounded-[var(--radius-panel)]" />
        <Skeleton className="h-[330px] rounded-[var(--radius-panel)]" />
      </div>
    </div>
  );
}

function Content({ data, step, previousLabel }: { data: Metrics; step: number; previousLabel: string }) {
  const { trabajos, anterior, modelos, revisiones } = data;
  const done = sum(trabajos.finalizados_por_hora);
  const failed = sum(trabajos.errores_por_hora);
  const rate = done + failed ? done / (done + failed) : null;
  const previousRate = anterior && anterior.finalizados + anterior.errores ? anterior.finalizados / (anterior.finalizados + anterior.errores) : null;
  const providers = Object.entries(modelos.por_proveedor ?? {});
  const costs = providers.map(([, p]) => p.coste_eur);
  const knownCost = sum(costs);
  const partialCost = costs.some((c) => c == null);
  const tokens = sum(providers.flatMap(([, p]) => [p.tokens_in, p.tokens_out]));

  return (
    <div className="space-y-4">
      <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" itemClassName="[&>*]:h-full" step={0.05}>
        <StatCard
          icon={Workflow}
          label="Trabajos lanzados"
          value={trabajos.total}
          delta={<Delta current={trabajos.total} previous={anterior?.trabajos ?? null} />}
          context={
            trabajos.activos ? (
              <span className="inline-flex items-center gap-1.5">
                <LiveDot /> {NUM.format(trabajos.en_ejecucion)} en ejecución · {NUM.format(trabajos.en_cola)} en cola
              </span>
            ) : (
              "Cola vacía ahora mismo"
            )
          }
          spark={trabajos.por_hora}
        />
        <StatCard
          icon={failed ? AlertTriangle : CheckCircle2}
          label="Tasa de éxito"
          value={rate == null ? null : Math.round(rate * 1000) / 10}
          decimals={rate != null && rate < 1 ? 1 : 0}
          suffix=" %"
          alert={rate != null && rate < 0.8}
          delta={<Delta current={rate} previous={previousRate} better="up" mode="points" />}
          context={rate == null ? "Ningún trabajo ha terminado en el periodo" : `${NUM.format(done)} finalizados · ${NUM.format(failed)} con fallo`}
          spark={trabajos.finalizados_por_hora}
          sparkColor="var(--approved)"
        />
        <StatCard
          icon={Timer}
          label="Tiempo mediano por trabajo"
          value={trabajos.p50_s}
          display={duration(trabajos.p50_s)}
          delta={<Delta current={trabajos.p50_s} previous={anterior?.p50_s ?? null} better="down" />}
          context={trabajos.p95_s != null ? `El 95 % termina en menos de ${duration(trabajos.p95_s)}` : "Sin trabajos medidos en el periodo"}
        />
        <StatCard
          icon={BrainCircuit}
          label="Llamadas a modelos"
          value={modelos.llamadas}
          delta={<Delta current={modelos.llamadas} previous={anterior?.llamadas ?? null} />}
          context={
            providers.length
              ? `${EUR.format(knownCost)}${partialCost ? "+" : ""} · ${compact(tokens)} tokens`
              : "Sin llamadas en el periodo"
          }
          spark={modelos.por_hora}
        />
      </Stagger>
      <p className="-mt-1 text-right text-[11px] text-faint">Variaciones frente a {previousLabel} · lectura de {DATETIME.format(new Date(data.generado))}</p>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <FlowPanel data={data} step={step} />
        <NowPanel data={data} />
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        <StagesPanel etapas={data.etapas} duraciones={data.duraciones} />
        <ModelsPanel providers={providers} externos={modelos.envios_externos} />
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <FailuresPanel failures={data.errores} />
        <ActivityPanel jobs={trabajos.recientes} revisions={revisiones.recientes} />
      </div>
    </div>
  );
}

function FlowPanel({ data, step }: { data: Metrics; step: number }) {
  const series: TrendSeries[] = [
    { key: "finalizados", label: "Finalizados", color: "var(--accent-strong)", values: data.trabajos.finalizados_por_hora, mark: "area" },
    { key: "iniciados", label: "Iniciados", color: "var(--text-muted)", values: data.trabajos.por_hora, mark: "line" },
    { key: "fallidos", label: "Con fallo", color: "var(--danger)", values: data.trabajos.errores_por_hora, mark: "bar" },
  ];
  return (
    <Panel className="min-w-0">
      <PanelHeader
        title="Flujo de trabajos"
        description="Lo que entra en la cola frente a lo que termina bien o falla, por intervalo."
        actions={
          data.trabajos.cache ? (
            <Tip content="Trabajos resueltos con un resultado idéntico ya calculado">
              <span>
                <Badge tone="sky">{NUM.format(data.trabajos.cache)} desde caché</Badge>
              </span>
            </Tip>
          ) : null
        }
      />
      <ul className="flex flex-wrap gap-x-5 gap-y-1 px-5 pb-2 text-xs text-muted">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <SeriesSwatch mark={s.mark} color={s.color} />
            {s.label}
            <span className="font-semibold text-text tabular-nums">{NUM.format(sum(s.values))}</span>
          </li>
        ))}
      </ul>
      <div className="px-3 pb-3">
        <TrendChart intervals={data.intervalos} stepHours={step} series={series} />
      </div>
    </Panel>
  );
}

function NowPanel({ data }: { data: Metrics }) {
  const { trabajos, revisiones } = data;
  const states = Object.entries(trabajos.por_estado ?? {}).sort(([a], [b]) => Object.keys(JOB_STATE).indexOf(a) - Object.keys(JOB_STATE).indexOf(b));
  const approved = revisiones.total ? revisiones.aprobadas / revisiones.total : 0;
  return (
    <Panel className="flex min-w-0 flex-col">
      <PanelHeader title="Ahora mismo" description="Cola en vivo y estado de las revisiones." />
      <div className="grid grid-cols-2 gap-3 px-5">
        <QueueTile label="En ejecución" value={trabajos.en_ejecucion} live={trabajos.en_ejecucion > 0} />
        <QueueTile label="En cola" value={trabajos.en_cola} />
      </div>
      <div className="px-5 pt-5">
        <p className="mb-2 text-xs font-medium text-muted">Trabajos del periodo por resultado</p>
        {states.length ? (
          <SegmentBar
            segments={states.map(([state, value]) => ({
              key: state,
              label: JOB_STATE[state]?.label ?? state,
              value,
              color: JOB_STATE[state]?.color ?? "var(--border-strong)",
            }))}
          />
        ) : (
          <p className="text-[13px] text-faint">Sin trabajos en el periodo.</p>
        )}
      </div>
      <div className="mt-auto flex items-center gap-4 border-t border-border px-5 py-4">
        <ProgressRing value={approved} size={72}>
          <span className="text-[15px] font-semibold text-strong tabular-nums">{Math.round(approved * 100)} %</span>
        </ProgressRing>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-strong">Revisiones aprobadas</p>
          <p className="text-xs text-muted">
            {NUM.format(revisiones.aprobadas)} de {NUM.format(revisiones.total)} · {NUM.format(revisiones.total - revisiones.aprobadas)} pendientes de revisión humana
          </p>
          <Link href="/revision" className="mt-1 inline-flex items-center gap-0.5 text-xs font-medium text-accent-text hover:underline">
            Ir a revisión <Icon icon={ArrowUpRight} size={12} />
          </Link>
        </div>
      </div>
    </Panel>
  );
}

function QueueTile({ label, value, live }: { label: string; value: number; live?: boolean }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface-sunken/60 px-3.5 py-3">
      <p className="flex items-center gap-1.5 text-xs text-muted">
        {live ? <LiveDot /> : <span className="size-2 rounded-full bg-border-strong" aria-hidden />}
        {label}
      </p>
      <p className="mt-1 text-[26px] leading-none font-semibold text-strong tabular-nums">{NUM.format(value)}</p>
    </div>
  );
}

function StagesPanel({ etapas, duraciones }: { etapas: Record<string, Record<string, number>>; duraciones: Record<string, number[]> }) {
  const rows = Object.entries(etapas ?? {})
    .filter(([stage]) => stage !== "job")
    .map(([stage, counts]) => {
      const ok = counts.ok ?? 0;
      const error = counts.error ?? 0;
      const skipped = counts.omitido ?? 0;
      const meta = STAGE_META[stage];
      return { stage, ok, error, skipped, total: ok + error + skipped, meta, bins: duraciones?.[stage] };
    })
    .sort((a, b) => (a.meta?.order ?? 50) - (b.meta?.order ?? 50));
  const worst = rows.reduce<(typeof rows)[number] | null>((w, r) => (r.error && (!w || r.error / r.total > w.error / w.total) ? r : w), null);
  return (
    <Panel className="min-w-0">
      <PanelHeader
        title="Salud por etapa"
        description="Resultado de cada etapa del pipeline y cuánto tarda."
        actions={worst ? <Badge tone="danger">Más fallos: {worst.meta?.name ?? worst.stage}</Badge> : rows.length ? <Badge tone="approved">Sin fallos</Badge> : null}
      />
      {rows.length ? (
        <ul className="divide-y divide-border px-5 pb-2">
          {rows.map((r) => {
            const health = r.ok + r.error ? r.ok / (r.ok + r.error) : null;
            return (
              <li key={r.stage} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 py-2.5 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto]">
                <span className="flex min-w-0 items-center gap-2 text-[13px] font-medium text-text">
                  <Icon icon={r.meta?.icon ?? Layers3} size={15} className="text-muted" />
                  <span className="truncate">{r.meta?.name ?? r.stage}</span>
                </span>
                <div className="order-3 col-span-2 min-w-0 sm:order-none sm:col-span-1">
                  <SegmentBar
                    legend={false}
                    segments={[
                      { key: "ok", label: "Correctas", value: r.ok, color: "var(--accent-strong)" },
                      { key: "omitido", label: "Omitidas", value: r.skipped, color: "var(--border-strong)" },
                      { key: "error", label: "Con error", value: r.error, color: "var(--danger)" },
                    ]}
                  />
                  <p className="mt-1 flex gap-3 text-[11px] text-faint">
                    <span>{NUM.format(r.ok)} correctas</span>
                    {r.skipped ? <span>{NUM.format(r.skipped)} omitidas</span> : null}
                    {r.error ? <span className="text-danger">{NUM.format(r.error)} con error</span> : null}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {r.bins?.some(Boolean) ? <MiniBars values={r.bins} labels={DURATION_BINS} /> : null}
                  <span className={cn("w-12 text-right text-[13px] font-semibold tabular-nums", health == null ? "text-faint" : health >= 0.95 ? "text-approved" : health >= 0.7 ? "text-warning" : "text-danger")}>
                    {health == null ? "—" : `${Math.round(health * 100)} %`}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState icon={CircleGauge} title="Sin etapas ejecutadas en el periodo">
          Cuando el pipeline procese documentos verás aquí el resultado de cada etapa.
        </EmptyState>
      )}
    </Panel>
  );
}

function ModelsPanel({ providers, externos }: { providers: [string, Provider][]; externos: number }) {
  const sorted = [...providers].sort(([, a], [, b]) => b.llamadas - a.llamadas);
  const max = Math.max(1, ...sorted.map(([, p]) => p.llamadas));
  return (
    <Panel className="flex min-w-0 flex-col">
      <PanelHeader title="Modelos de lenguaje" description="Uso, latencia y coste por proveedor en el periodo." />
      {sorted.length ? (
        <div className="overflow-x-auto px-3">
          <table className="w-full min-w-[480px] text-left text-[13px]">
            <thead className="text-[11px] tracking-wide text-faint uppercase">
              <tr>
                <th scope="col" className="px-2 py-2 font-medium">Proveedor</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">Llamadas</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">Tokens</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">Latencia p50</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">Coste</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(([name, p]) => {
                const tokens = p.tokens_in == null || p.tokens_out == null ? null : p.tokens_in + p.tokens_out;
                return (
                  <tr key={name} className="border-t border-border">
                    <td className="px-2 py-2.5">
                      <p className="font-medium text-text">{name}</p>
                      <div className="mt-1 h-1 w-full max-w-[160px] overflow-hidden rounded-full bg-surface-sunken">
                        <div className="h-full rounded-full bg-accent-strong" style={{ width: `${(p.llamadas / max) * 100}%` }} />
                      </div>
                    </td>
                    <td className="px-2 py-2.5 text-right font-medium tabular-nums">{NUM.format(p.llamadas)}</td>
                    <td className="px-2 py-2.5 text-right text-muted tabular-nums">
                      {tokens == null ? <Tip content="Algún registro no informa de tokens"><span>parcial</span></Tip> : compact(tokens)}
                    </td>
                    <td className="px-2 py-2.5 text-right text-muted tabular-nums">{duration(p.p50_s)}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums">
                      {p.coste_eur == null ? <Tip content="El proveedor no publica el coste de alguna llamada"><span className="text-faint">desconocido</span></Tip> : EUR.format(p.coste_eur)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState icon={BrainCircuit} title="Sin llamadas a modelos en el periodo" />
      )}
      <p className="mt-auto flex items-center gap-2 border-t border-border px-5 py-3 text-xs text-muted">
        <Icon icon={ShieldCheck} size={14} className={externos ? "text-warning" : "text-approved"} />
        {externos
          ? `${NUM.format(externos)} envíos de documentos a servicios externos, registrados por la política de datos.`
          : "Ningún documento ha salido a servicios externos en el periodo."}
      </p>
    </Panel>
  );
}

function FailuresPanel({ failures }: { failures: Failure[] }) {
  return (
    <Panel className="min-w-0">
      <PanelHeader
        title="Incidencias"
        description="Trabajos que han fallado o agotado el tiempo en el periodo."
        actions={failures.length ? <Badge tone="danger">{NUM.format(failures.length)}</Badge> : null}
      />
      {failures.length ? (
        <ul className="max-h-[360px] space-y-1 overflow-y-auto px-3 pb-3">
          {failures.map((f) => (
            <li key={f.id}>
              <Link
                href={`/pipeline?trabajo=${encodeURIComponent(f.id)}`}
                className="group flex gap-3 rounded-[var(--radius-control)] px-2 py-2.5 transition-colors hover:bg-surface-sunken"
              >
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", f.estado === "timeout" ? "bg-warning" : "bg-danger")} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 text-[13px]">
                    <span className="font-mono font-medium text-text">{f.equipo}</span>
                    <span className="text-xs text-faint">{JOB_KIND[f.tipo ?? ""] ?? f.tipo ?? "Trabajo"}</span>
                    <Badge tone={f.estado === "timeout" ? "warning" : "danger"} className="h-5">
                      {JOB_STATE[f.estado]?.label ?? f.estado}
                    </Badge>
                  </span>
                  <span className="mt-0.5 line-clamp-2 block text-xs text-muted">{f.motivo ?? "Sin motivo registrado"}</span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-1 text-[11px] text-faint">
                  {f.fecha ? <time dateTime={f.fecha}>{ago(f.fecha)}</time> : null}
                  <Icon icon={ArrowUpRight} size={14} className="opacity-0 transition-opacity group-hover:opacity-100" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon={CheckCircle2} title="Sin incidencias en el periodo">
          Ningún trabajo ha fallado ni ha agotado el tiempo.
        </EmptyState>
      )}
    </Panel>
  );
}

type Feed = { key: string; when: string; who: string | null; text: React.ReactNode; badge?: React.ReactNode; href: string };

function ActivityPanel({ jobs, revisions }: { jobs: Job[]; revisions: Revision[] }) {
  const [type, setType] = useState<"all" | "revisions" | "jobs">("all");
  const items = useMemo<Feed[]>(() => {
    const fromRevisions = revisions.map((r) => ({
      key: `rev:${r.id}`,
      when: r.fecha,
      who: r.autor,
      href: `/resultados/${encodeURIComponent(r.id)}`,
      text: (
        <>
          {REVISION_VERB[r.accion] ?? r.accion} <strong className="font-medium text-text">{r.equipo} · rev {r.revision}</strong>
        </>
      ),
      badge: r.accion === "aprobada" ? <Badge tone="approved" className="h-5">Aprobada</Badge> : null,
    }));
    const fromJobs = jobs.map((j) => ({
      key: `job:${j.id}`,
      when: j.fecha,
      who: j.autor,
      href: `/pipeline?trabajo=${encodeURIComponent(j.id)}`,
      text: (
        <>
          lanzó {(JOB_KIND[j.tipo] ?? j.tipo).toLowerCase()} de <strong className="font-medium text-text">{j.equipo}</strong>
        </>
      ),
      badge: <Badge tone={JOB_STATE[j.estado]?.tone ?? "neutral"} className="h-5">{JOB_STATE[j.estado]?.label.replace(/s$/, "") ?? j.estado}</Badge>,
    }));
    return [...(type !== "jobs" ? fromRevisions : []), ...(type !== "revisions" ? fromJobs : [])].sort((a, b) => b.when.localeCompare(a.when)).slice(0, 8);
  }, [jobs, revisions, type]);

  return (
    <Panel className="min-w-0">
      <PanelHeader
        title="Actividad reciente"
        description="Quién ha hecho qué en la plataforma."
        actions={
          <Segmented
            label="Filtrar actividad"
            value={type}
            onChange={setType}
            options={[
              { value: "all", label: "Todo" },
              { value: "revisions", label: "Revisiones" },
              { value: "jobs", label: "Trabajos" },
            ]}
          />
        }
      />
      {items.length ? (
        <ol className="relative px-5 pb-4">
          {items.map((item, i) => (
            <li key={item.key} className="relative flex gap-3 pb-3 last:pb-0">
              {i < items.length - 1 ? <span className="absolute top-8 bottom-0 left-[13px] w-px bg-border" aria-hidden /> : null}
              <span className="relative z-[1] inline-flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-surface-raised text-[10px] font-semibold text-muted">
                {initials(item.who)}
              </span>
              <Link href={item.href} className="min-w-0 flex-1 rounded-[var(--radius-control)] px-1 py-0.5 hover:bg-surface-sunken">
                <p className="text-[13px] text-muted">
                  <span className="font-medium text-text">{item.who ?? "Alguien"}</span> {item.text}
                </p>
                <p className="mt-0.5 flex items-center gap-2 text-[11px] text-faint">
                  <time dateTime={item.when} title={DATETIME.format(new Date(item.when))}>
                    {ago(item.when)}
                  </time>
                  {item.badge}
                </p>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState icon={Activity} title="Sin actividad para este filtro" />
      )}
    </Panel>
  );
}

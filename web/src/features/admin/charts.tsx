"use client";

import { ArrowDownRight, ArrowUpRight, Minus, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { CountUp } from "@/components/motion/count-up";
import { Tip } from "@/components/ui/controls";
import { Icon, Panel, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

import { DEC, NUM, tick } from "./format";

const EASE = [0.23, 1, 0.32, 1] as const;

/** Ancho real del contenedor, para dibujar el SVG a escala 1:1 (trazos y puntos nítidos). */
function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => entry && setWidth(Math.max(120, entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Escala «bonita»: 4 tramos con paso 1, 2, 2,5 o 5 × 10ⁿ. */
function niceScale(max: number, steps = 4) {
  if (max <= 0) return { top: steps, ticks: Array.from({ length: steps + 1 }, (_, i) => i) };
  const raw = max / steps;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
  const unit = Number.isInteger(max) && step < 1 ? 1 : step;
  const top = Math.ceil(max / unit) * unit;
  const ticks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += unit) ticks.push(Number(v.toFixed(6)));
  return { top, ticks };
}

/** Curva monótona (Fritsch–Carlson): suave sin pasar por debajo de cero ni inventar picos. */
function monotone(points: [number, number][]): string {
  const n = points.length;
  if (n === 0) return "";
  if (n === 1) return `M${points[0]![0]},${points[0]![1]}`;
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(points[i + 1]![0] - points[i]![0]);
    slope.push((points[i + 1]![1] - points[i]![1]) / (dx[i] || 1));
  }
  const tangent = points.map((_, i) => {
    if (i === 0) return slope[0]!;
    if (i === n - 1) return slope[n - 2]!;
    const a = slope[i - 1]!;
    const b = slope[i]!;
    return a * b <= 0 ? 0 : (3 * (dx[i - 1]! + dx[i]!)) / ((2 * dx[i]! + dx[i - 1]!) / a + (dx[i]! + 2 * dx[i - 1]!) / b);
  });
  let d = `M${points[0]![0].toFixed(1)},${points[0]![1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = points[i]!;
    const [x1, y1] = points[i + 1]!;
    const h = dx[i]! / 3;
    d += ` C${(x0 + h).toFixed(1)},${(y0 + tangent[i]! * h).toFixed(1)} ${(x1 - h).toFixed(1)},${(y1 - tangent[i + 1]! * h).toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return d;
}

export type TrendSeries = {
  key: string;
  label: string;
  /** Variable CSS del color (siempre un token del tema). */
  color: string;
  values: number[];
  mark: "area" | "line" | "bar";
};

/**
 * Gráfica temporal con una sola escala: área para el resultado principal, línea discontinua para
 * la referencia y barras para los fallos (forma distinta, no solo color). Cursor con tooltip al
 * pasar el ratón y con las flechas del teclado.
 */
export function TrendChart({
  intervals,
  stepHours,
  series,
  height = 232,
  unit = "",
}: {
  intervals: string[];
  stepHours: number;
  series: TrendSeries[];
  height?: number;
  unit?: string;
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [box, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const n = intervals.length;
  const pad = { left: 34, right: 8, top: 14, bottom: 26 };
  const innerW = Math.max(1, width - pad.left - pad.right);
  const base = height - pad.bottom;
  const band = innerW / Math.max(1, n);
  const { top, ticks } = niceScale(Math.max(0, ...series.flatMap((s) => s.values)));
  const x = (i: number) => pad.left + band * (i + 0.5);
  const y = (v: number) => base - ((base - pad.top) * v) / top;
  const empty = series.every((s) => !s.values.some(Boolean));
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(innerW / 76))));
  const bars = series.filter((s) => s.mark === "bar");
  const barW = Math.max(3, Math.min(14, (band * 0.55) / Math.max(1, bars.length)));

  const move = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect || !n) return;
    setActive(Math.max(0, Math.min(n - 1, Math.floor((clientX - rect.left - pad.left) / band))));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!n) return;
    const current = active ?? n - 1;
    const next = event.key === "ArrowLeft" ? current - 1 : event.key === "ArrowRight" ? current + 1 : event.key === "Home" ? 0 : event.key === "End" ? n - 1 : null;
    if (next === null) return;
    event.preventDefault();
    setActive(Math.max(0, Math.min(n - 1, next)));
  };
  const summary = (i: number) => `${tick(intervals[i]!, stepHours)}: ${series.map((s) => `${s.label} ${NUM.format(s.values[i] ?? 0)}`).join(", ")}`;
  const tipLeft = active === null ? 0 : x(active);
  const flip = tipLeft > width * 0.6;

  return (
    <div
      ref={box}
      tabIndex={0}
      role="group"
      aria-label="Gráfica temporal. Usa las flechas para recorrer los intervalos."
      onKeyDown={onKey}
      onPointerMove={(e) => move(e.clientX)}
      onPointerLeave={() => setActive(null)}
      onBlur={() => setActive(null)}
      className="relative select-none rounded-[var(--radius-control)] outline-none focus-visible:ring-2 focus-visible:ring-accent"
      style={{ height }}
    >
      <svg width={width} height={height} className="block overflow-visible" aria-hidden>
        <defs>
          {series.filter((s) => s.mark === "area").map((s) => (
            <linearGradient key={s.key} id={`${uid}-${s.key}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={s.color} stopOpacity="0.32" />
              <stop offset="1" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeDasharray={v ? "2 4" : undefined} />
            <text x={pad.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-[var(--text-faint)] text-[10px]">
              {NUM.format(v)}
            </text>
          </g>
        ))}
        {intervals.map((iso, i) =>
          i % labelEvery === 0 || i === n - 1 ? (
            <text key={iso} x={x(i)} y={height - 6} textAnchor="middle" className="fill-[var(--text-faint)] text-[10px]">
              {tick(iso, stepHours)}
            </text>
          ) : null,
        )}
        {active !== null ? <rect x={pad.left + band * active} y={pad.top} width={band} height={base - pad.top} fill="var(--text)" opacity="0.035" rx="4" /> : null}
        {!empty
          ? series.map((s, si) => {
              if (s.mark === "bar") {
                const offset = (bars.indexOf(s) - (bars.length - 1) / 2) * (barW + 2);
                return (
                  <g key={s.key}>
                    {s.values.map((v, i) => {
                      if (!v) return null;
                      const bx = x(i) + offset - barW / 2;
                      const by = y(v);
                      const r = Math.min(3, (base - by) / 2, barW / 2);
                      const d = `M${bx},${base} V${by + r} Q${bx},${by} ${bx + r},${by} H${bx + barW - r} Q${bx + barW},${by} ${bx + barW},${by + r} V${base} Z`;
                      return (
                        <motion.path
                          key={i}
                          d={d}
                          fill={s.color}
                          initial={{ opacity: 0, scaleY: 0 }}
                          animate={{ opacity: active === null || active === i ? 0.9 : 0.45, scaleY: 1 }}
                          style={{ originY: 1, transformBox: "fill-box" }}
                          transition={{ duration: 0.5, delay: 0.25 + i * 0.012, ease: EASE }}
                        />
                      );
                    })}
                  </g>
                );
              }
              const points = s.values.map((v, i) => [x(i), y(v)] as [number, number]);
              const flat = points.map(([px]) => [px, base] as [number, number]);
              const line = monotone(points);
              const lineFrom = monotone(flat);
              const first = points[0]?.[0] ?? 0;
              const last = points[points.length - 1]?.[0] ?? 0;
              const close = ` L${last},${base} L${first},${base} Z`;
              return (
                <g key={s.key}>
                  {s.mark === "area" ? (
                    <motion.path
                      initial={{ d: lineFrom + close }}
                      animate={{ d: line + close }}
                      transition={{ duration: 0.7, delay: si * 0.05, ease: EASE }}
                      fill={`url(#${uid}-${s.key})`}
                    />
                  ) : null}
                  <motion.path
                    initial={{ d: lineFrom }}
                    animate={{ d: line }}
                    transition={{ duration: 0.7, delay: si * 0.05, ease: EASE }}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={s.mark === "area" ? 2 : 1.5}
                    strokeDasharray={s.mark === "line" ? "4 4" : undefined}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </g>
              );
            })
          : null}
        {active !== null && !empty
          ? series
              .filter((s) => s.mark !== "bar")
              .map((s) => (
                <circle key={s.key} cx={x(active)} cy={y(s.values[active] ?? 0)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
              ))
          : null}
      </svg>
      {empty ? (
        <span className="pointer-events-none absolute inset-x-0 top-[40%] text-center text-[13px] text-muted">Sin actividad en el periodo</span>
      ) : null}
      {active !== null && !empty ? (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-[168px] rounded-[var(--radius-control)] border border-border bg-surface-raised/95 px-3 py-2 text-xs shadow-[var(--shadow-pop)] backdrop-blur"
          style={{ left: tipLeft, transform: `translateX(${flip ? "calc(-100% - 14px)" : "14px"})` }}
        >
          <p className="mb-1.5 font-medium text-strong">{tick(intervals[active]!, stepHours)}</p>
          {series.map((s) => (
            <p key={s.key} className="flex items-center justify-between gap-4 py-0.5 text-muted">
              <span className="flex items-center gap-1.5">
                <SeriesSwatch mark={s.mark} color={s.color} />
                {s.label}
              </span>
              <span className="font-medium text-text tabular-nums">
                {NUM.format(s.values[active] ?? 0)}
                {unit}
              </span>
            </p>
          ))}
        </div>
      ) : null}
      <p className="sr-only" aria-live="polite">
        {active !== null ? summary(active) : ""}
      </p>
    </div>
  );
}

/** Muestra de la serie con la misma forma que en la gráfica (área, línea discontinua o barra). */
export function SeriesSwatch({ mark, color }: { mark: TrendSeries["mark"]; color: string }) {
  if (mark === "bar") return <span className="inline-block h-2.5 w-1.5 rounded-[2px]" style={{ background: color }} aria-hidden />;
  if (mark === "line")
    return (
      <svg width="14" height="4" aria-hidden className="shrink-0">
        <line x1="1" x2="13" y1="2" y2="2" stroke={color} strokeWidth="2" strokeDasharray="3 3" strokeLinecap="round" />
      </svg>
    );
  return <span className="inline-block h-1 w-3.5 rounded-full" style={{ background: color }} aria-hidden />;
}

/** Micrográfica de área que ocupa todo el ancho de su tarjeta. */
export function SparkArea({ values, color = "var(--accent-strong)", className }: { values: number[]; color?: string; className?: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  if (values.length < 2 || !values.some(Boolean)) return <div className={cn("h-9", className)} />;
  const w = 200;
  const h = 36;
  const max = Math.max(...values) || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 3 - (v / max) * (h - 6)] as [number, number]);
  const line = monotone(pts);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn("h-9 w-full overflow-visible", className)} aria-hidden>
      <defs>
        <linearGradient id={uid} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.25" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <motion.path d={`${line} L${w},${h} L0,${h} Z`} fill={`url(#${uid})`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, delay: 0.3 }} />
      <motion.path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.8, ease: [0.65, 0, 0.35, 1] }}
      />
    </svg>
  );
}

/**
 * Variación frente al periodo anterior. `better` dice qué dirección es buena; con «neutral» el
 * cambio se muestra sin juicio (más trabajos no es mejor ni peor).
 */
export function Delta({
  current,
  previous,
  better = "neutral",
  mode = "percent",
}: {
  current: number | null;
  previous: number | null;
  better?: "up" | "down" | "neutral";
  mode?: "percent" | "points";
}) {
  if (current == null || previous == null) return <span className="text-xs text-faint">sin referencia</span>;
  const diff = current - previous;
  if (mode === "percent" && previous === 0) {
    return current === 0 ? <DeltaChip tone="flat" icon={Minus} text="igual" /> : <DeltaChip tone="flat" icon={ArrowUpRight} text="nuevo" />;
  }
  const value = mode === "percent" ? (diff / previous) * 100 : diff * 100;
  if (Math.abs(value) < 0.5) return <DeltaChip tone="flat" icon={Minus} text="igual" />;
  const up = value > 0;
  const tone = better === "neutral" ? "flat" : (better === "up") === up ? "good" : "bad";
  const text = `${DEC.format(Math.abs(value))}${mode === "percent" ? " %" : " pp"}`;
  return <DeltaChip tone={tone} icon={up ? ArrowUpRight : ArrowDownRight} text={text} label={up ? "sube" : "baja"} />;
}

function DeltaChip({ tone, icon, text, label }: { tone: "good" | "bad" | "flat"; icon: LucideIcon; text: string; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-0.5 rounded-full px-1.5 text-[11px] font-medium",
        tone === "good" && "bg-approved-soft text-approved",
        tone === "bad" && "bg-danger-soft text-danger",
        tone === "flat" && "bg-surface-sunken text-muted",
      )}
      title="Frente al periodo anterior"
    >
      <Icon icon={icon} size={12} />
      {label ? <span className="sr-only">{label}</span> : null}
      {text}
    </span>
  );
}

/** Tarjeta de indicador: etiqueta, cifra grande, variación, contexto y micrográfica. */
export function StatCard({
  icon,
  label,
  value,
  decimals = 0,
  suffix = "",
  display,
  delta,
  context,
  spark,
  sparkColor,
  loading,
  alert,
}: {
  icon: LucideIcon;
  label: string;
  value: number | null;
  decimals?: number;
  suffix?: string;
  /** Texto en lugar de la cifra animada (duraciones, «—»). */
  display?: string;
  delta?: ReactNode;
  context?: ReactNode;
  spark?: number[];
  sparkColor?: string;
  loading?: boolean;
  alert?: boolean;
}) {
  return (
    <Panel className={cn("group relative flex h-full min-w-0 flex-col overflow-hidden p-4 pb-3", alert && "border-danger/40")}>
      <div className="flex items-center gap-2 text-[13px] text-muted">
        <span className={cn("inline-flex size-7 items-center justify-center rounded-[var(--radius-control)]", alert ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent-text")}>
          <Icon icon={icon} size={15} />
        </span>
        {label}
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-8 w-28" />
      ) : (
        <div className="mt-2.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span className={cn("text-[30px] leading-none font-semibold tracking-tight tabular-nums", alert ? "text-danger" : "text-strong")}>
            {display ?? (value == null ? "—" : <CountUp value={value} decimals={decimals} suffix={suffix} />)}
          </span>
          {delta}
        </div>
      )}
      <div className="mt-1.5 min-h-[18px] text-xs text-muted">{context}</div>
      {spark ? <SparkArea values={spark} color={sparkColor} className="mt-auto pt-2" /> : null}
    </Panel>
  );
}

export type Segment = { key: string; label: string; value: number; color: string };

/** Barra de partes de un todo: huecos de 2 px entre tramos, tooltip por tramo y leyenda con cifras. */
export function SegmentBar({ segments, legend = true, className }: { segments: Segment[]; legend?: boolean; className?: string }) {
  const total = segments.reduce((a, s) => a + s.value, 0);
  const visible = segments.filter((s) => s.value > 0);
  return (
    <div className={className}>
      <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full bg-surface-sunken" role="img" aria-label={visible.map((s) => `${s.label} ${s.value}`).join(", ") || "Sin datos"}>
        {visible.map((s, i) => (
          <Tip key={s.key} content={`${s.label}: ${NUM.format(s.value)} (${Math.round((s.value / total) * 100)} %)`}>
            <motion.span
              className="h-full first:rounded-l-full last:rounded-r-full"
              style={{ background: s.color }}
              initial={{ width: 0 }}
              animate={{ width: `${(s.value / total) * 100}%` }}
              transition={{ duration: 0.7, delay: i * 0.05, ease: EASE }}
            />
          </Tip>
        ))}
      </div>
      {legend && visible.length ? (
        <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          {visible.map((s) => (
            <li key={s.key} className="flex items-center justify-between gap-2 text-muted">
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="size-2 shrink-0 rounded-full" style={{ background: s.color }} aria-hidden />
                <span className="truncate">{s.label}</span>
              </span>
              <span className="font-medium text-text tabular-nums">{NUM.format(s.value)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Anillo de progreso con la cifra en el centro. */
export function ProgressRing({ value, size = 88, color = "var(--approved)", children }: { value: number; size?: number; color?: string; children?: ReactNode }) {
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-sunken)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ type: "spring", stiffness: 120, damping: 22 }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  );
}

/** Histograma mínimo (tramos de duración de una etapa). */
export function MiniBars({ values, labels, color = "var(--accent-strong)" }: { values: number[]; labels: string[]; color?: string }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex h-6 items-end gap-[2px]" role="img" aria-label={values.map((v, i) => `${labels[i]}: ${v}`).join(", ")}>
      {values.map((v, i) => (
        <Tip key={i} content={`${labels[i]}: ${NUM.format(v)}`}>
          <motion.span
            className="w-2 rounded-t-[2px]"
            style={{ background: v ? color : "var(--border)" }}
            initial={{ height: 2 }}
            animate={{ height: v ? Math.max(3, (v / max) * 24) : 2 }}
            transition={{ duration: 0.5, delay: i * 0.04, ease: EASE }}
          />
        </Tip>
      ))}
    </div>
  );
}

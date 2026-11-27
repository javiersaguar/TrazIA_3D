"use client";

import { Box, ChevronDown, FileText, GripHorizontal, ScanLine, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useCallback, useLayoutEffect, useRef, useSyncExternalStore } from "react";
import { Icon } from "@/components/ui/primitives";
import { fieldLabel } from "@/lib/field-labels";
import { formatValue } from "@/lib/format";
import type { PreparedProduct } from "./model-resource";
import { elementLabel } from "./semantic";
import { ifcTraces } from "./ifc-trace";
import styles from "./viewer.module.css";

export type InspectorSubject = Pick<PreparedProduct, "semanticId" | "ifcType" | "globalId" | "name" | "psets"> & { label?: string };
type InspectorPosition = { x: number; y: number };
const disclosure = "flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 py-2 font-medium text-text hover:bg-surface-raised";

const INSET = 10;
const arrowOffsets = new Map<string, InspectorPosition>([
  ["ArrowLeft", { x: -1, y: 0 }],
  ["ArrowRight", { x: 1, y: 0 }],
  ["ArrowUp", { x: 0, y: -1 }],
  ["ArrowDown", { x: 0, y: 1 }],
]);
const subscribeFullscreen = (change: () => void) => {
  document.addEventListener("fullscreenchange", change);
  return () => document.removeEventListener("fullscreenchange", change);
};

export function IfcInspector({ id, anchorId, open, product, description, onClose }: {
  id: string;
  anchorId: string;
  open: boolean;
  product?: InspectorSubject;
  description?: string;
  onClose(): void;
}) {
  const panel = useRef<HTMLElement>(null);
  const handle = useRef<HTMLButtonElement>(null);
  const position = useRef<InspectorPosition | null>(null);
  const drag = useRef<{ id: number; start: InspectorPosition; x: number; y: number } | null>(null);
  const host = useSyncExternalStore(subscribeFullscreen, () => {
    const fullscreen = document.fullscreenElement;
    if (fullscreen instanceof HTMLElement && fullscreen.contains(document.getElementById(anchorId))) return fullscreen;
    return document.body;
  }, () => null);
  const move = useCallback(({ x, y }: InspectorPosition) => {
    const target = panel.current;
    if (!target) return;
    const width = document.documentElement.clientWidth;
    const height = window.innerHeight;
    const clamp = (value: number, edge: number) => Math.max(INSET, Math.min(value, edge - INSET));
    const next = { x: clamp(x, width - target.offsetWidth), y: clamp(y, height - target.offsetHeight) };
    position.current = next;
    target.style.translate = `${next.x}px ${next.y}px`;
  }, []);

  useLayoutEffect(() => {
    const target = panel.current;
    if (!open || !host || !target) return;
    const anchor = document.getElementById(anchorId)?.getBoundingClientRect();
    const narrow = window.matchMedia("(max-width: 640px)").matches;
    move(position.current ?? {
      x: (anchor?.right ?? window.innerWidth) - target.offsetWidth - 2 * INSET,
      y: narrow ? window.innerHeight - target.offsetHeight - 2 * INSET : (anchor?.top ?? 0) + 48,
    });
    handle.current?.focus({ preventScroll: true });
    const fit = () => { if (position.current) move(position.current); };
    const observer = new ResizeObserver(fit);
    observer.observe(target);
    window.addEventListener("resize", fit);
    return () => {
      drag.current = null;
      observer.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [anchorId, host, move, open]);

  if (!open || !host) return null;

  const traces = product ? Object.entries(ifcTraces(product.psets)) : [];
  const sets = product ? Object.entries(product.psets) : [];
  const label = product ? product.label ?? elementLabel(product.semanticId) : "";

  return createPortal(
    <aside id={id} ref={panel} role="dialog" aria-modal={false} aria-labelledby={`${id}-title`}
      className={`${styles.inspector} flex min-h-0 min-w-0 flex-col bg-surface text-xs`}
      onKeyDown={event => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        onClose();
      }}>
      <header className="flex shrink-0 items-center gap-1 border-b border-border bg-surface-raised p-1.5">
        <button type="button" ref={handle} aria-label="Mover Inspector IFC" aria-describedby={`${id}-drag-help`}
          className={`${styles.inspectorHandle} flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left`}
          onPointerDown={event => {
            const start = position.current;
            if (!start || !event.isPrimary || event.button !== 0) return;
            drag.current = { id: event.pointerId, start, x: event.clientX, y: event.clientY };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={event => {
            const active = drag.current;
            if (!active || active.id !== event.pointerId) return;
            move({ x: active.start.x + event.clientX - active.x, y: active.start.y + event.clientY - active.y });
          }}
          onLostPointerCapture={() => { drag.current = null; }}
          onKeyDown={event => {
            const current = position.current;
            const direction = arrowOffsets.get(event.key);
            if (!current || !direction) return;
            event.preventDefault();
            event.stopPropagation();
            const step = event.shiftKey ? 48 : 12;
            move({ x: current.x + direction.x * step, y: current.y + direction.y * step });
          }}>
          <Icon icon={ScanLine} size={17} className="text-accent-text" />
          <span id={`${id}-title`} className="min-w-0 flex-1 text-sm font-semibold text-strong">Inspector IFC</span>
          <Icon icon={GripHorizontal} size={17} className="text-muted" />
        </button>
        <span className="sr-only" id={`${id}-drag-help`}>Arrastra la cabecera o usa las flechas para mover la ventana.</span>
        <button type="button" aria-label="Cerrar inspector IFC" onClick={onClose}
          className="grid size-10 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-sunken hover:text-text">
          <Icon icon={X} size={17} />
        </button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-3 [overflow-wrap:anywhere]">
        {product ? <>
          <section className="space-y-2 rounded-xl border border-border bg-surface-raised p-2.5">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <h4 className="text-sm font-semibold text-strong">{label}</h4>
              <span className="rounded-md bg-accent-soft px-1.5 py-0.5 font-mono text-[11px] text-accent-text">{product.ifcType}</span>
            </div>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2.5 gap-y-1 border-t border-border pt-2">
              <dt className="text-muted">GlobalId</dt>
              <dd><code data-testid="inspector-guid">{product.globalId}</code></dd>
              {product.name !== label ? <><dt className="text-muted">Nombre IFC</dt><dd>{product.name}</dd></> : null}
            </dl>
            {description ? <p className="leading-relaxed text-muted">{description}</p> : null}
          </section>
          {product.psets.Pset_TrazIA?.Origen ? (
            <p className="rounded-lg border border-warning-border bg-warning-bg px-2.5 py-2 text-warning" data-testid="derived-origin">
              Detalle derivado · no leído del plano{product.psets.Pset_TrazIA.ClaseOrigen === "supuesto_visual" ? " · clase supuesta" : ""}
            </p>
          ) : null}
          {traces.length ? (
            <section aria-label="Fuentes y confianza">
              <h4 className="mb-1.5 flex items-center gap-1.5 font-semibold text-strong"><Icon icon={FileText} size={14} className="text-accent-text" /> Fuentes y confianza</h4>
              <ul className="divide-y divide-border rounded-xl border border-border">
                {traces.map(([path, trace]) => {
                  const { source } = trace;
                  const location = [source.document_id, source.page && `pág. ${source.page}`, source.sheet, source.cell].filter(Boolean).join(" · ");
                  const confidence = source.confidence.toLocaleString("es-ES", { style: "percent", maximumFractionDigits: 1 });
                  return <li key={path} className="space-y-1 px-2.5 py-2">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium leading-snug text-text" title={path}>{fieldLabel(path)}</p>
                      <span className="shrink-0 rounded-md bg-surface-sunken px-1.5 py-0.5 tabular-nums text-muted" aria-label={`Confianza ${confidence}`}>{confidence}</span>
                    </div>
                    <p className="font-semibold text-strong">{formatValue(trace.value, trace.unit)}</p>
                    <p className="leading-snug text-muted">{location}</p>
                    {source.locator ? <p className="leading-snug text-muted">{source.locator}</p> : null}
                  </li>;
                })}
              </ul>
            </section>
          ) : null}
          {sets.length ? <details className="rounded-xl border border-border">
            <summary className={disclosure}>Propiedades IFC <Icon icon={ChevronDown} size={14} /></summary>
            <div className="divide-y divide-border border-t border-border">
              {sets.map(([name, values]) => (
                <details key={name}>
                  <summary className={`${disclosure} font-mono`}>{name}<Icon icon={ChevronDown} size={13} /></summary>
                  <dl className="divide-y divide-border px-2.5 pb-2">
                    {Object.entries(values).map(([key, value]) => (
                      <div key={key} className="grid grid-cols-[1fr_1.2fr] gap-2 py-1.5">
                        <dt className="text-muted">{key}</dt><dd>{value === null ? "—" : String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              ))}
            </div>
          </details> : null}
        </> : (
          <p className="flex items-center gap-2 rounded-xl border border-dashed border-border-strong p-3 leading-relaxed text-muted">
            <Icon icon={Box} size={17} className="text-accent-text" /> Elige una pieza en el modelo o en Elementos.
          </p>
        )}
      </div>
    </aside>,
    host,
  );
}

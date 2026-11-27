"use client";

import { Check, Pencil, CircleHelp, FileText, Undo2, X, Zap } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef } from "react";
import { Tip } from "@/components/ui/controls";
import { ConfidenceBar } from "@/components/ui/data";
import { FieldStatusBadge } from "@/components/ui/status";
import { Badge, Button, Icon, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { formatInterval, formatValue } from "@/lib/format";
import { isAutoApproved, isDesignValue, isPreliminary, riskLevel, type FieldStatus, type ReviewField } from "@/lib/mock/fields";
import { CorrectionEditor as EditValue } from "./correction-editor";
import type { FieldOptions } from "@/lib/mock/api";
import type { Document } from "@/lib/types/revision";
import type { FieldFilter } from "./queue-header";

const WIDE_COLUMNS = "@3xl:grid-cols-[minmax(0,1.1fr)_minmax(8rem,.5fr)_minmax(0,.8fr)_minmax(6.5rem,auto)] @3xl:gap-x-5";

type Props = {
  busy?: boolean;
  filter: FieldFilter;
  fields: ReviewField[] | undefined;
  documents: Document[] | undefined;
  failed: boolean;
  onRetry: () => void;
  selectedPath: string | null;
  hoveredId: string | null;
  editingPath: string | null;
  onSelect: (f: ReviewField) => void;
  onHover: (f: ReviewField | null) => void;
  onAction: (f: ReviewField, status: FieldStatus, value?: number | string, options?: FieldOptions) => void | Promise<boolean>;
  onEdit: (path: string, open: boolean) => void;
  onReachEnd: () => void;
};

export function FieldQueue({ busy = false, filter, fields, documents, failed, onRetry, selectedPath, hoveredId, editingPath, onSelect, onHover, onAction, onEdit, onReachEnd }: Props) {
  const list = useRef<HTMLDivElement>(null);
  const lastScrollTop = useRef(0);
  const originals = documents?.filter(document => document.role !== "orden_diseno");

  useEffect(() => {
    if (!selectedPath || !list.current) return;
    const row = list.current.querySelector<HTMLElement>(`[data-row="${CSS.escape(selectedPath)}"]`);
    if (!row) return;
    const viewport = list.current.getBoundingClientRect();
    const target = row.getBoundingClientRect();
    if (target.height > viewport.height || target.top < viewport.top) list.current.scrollTop += target.top - viewport.top;
    else if (target.bottom > viewport.bottom) list.current.scrollTop += target.bottom - viewport.bottom;
    // El desplazamiento hasta el campo seleccionado no es un gesto de cierre.
    lastScrollTop.current = list.current.scrollTop;
  }, [selectedPath, filter, editingPath]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={list} role="listbox" aria-label="Campos por revisar"
        className="@container min-h-0 flex-1 overflow-y-auto overscroll-contain p-1.5 sm:p-2"
        onScroll={event => {
          const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
          const scrollingDown = scrollTop > lastScrollTop.current;
          lastScrollTop.current = scrollTop;
          if (scrollingDown && fields?.length && !editingPath && !busy && scrollHeight - clientHeight - scrollTop <= 1) {
            onReachEnd();
          }
        }}>
        {failed && !fields ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-sunken px-3 py-2.5">
            <p className="text-sm text-muted" role="status">No se pudieron cargar los campos.</p>
            <Button size="sm" onClick={onRetry}>Reintentar</Button>
          </div>
        ) : !fields
          ? Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="mb-1.5 h-14 w-full" />)
          : fields.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted" role="status">
              {filter === "pending" ? "No quedan campos por revisar." : "Esta revisión no tiene campos."}
            </p>
          ) : fields.map((f) => (
              <FieldRow
                busy={busy}
                key={f.path}
                field={f}
                documents={originals}
                selected={f.path === selectedPath}
                related={f.path !== selectedPath && f.elementId === hoveredId}
                editing={f.path === editingPath}
                onSelect={() => onSelect(f)}
                onHover={(h) => onHover(h ? f : null)}
                onAction={(status, value, options) => onAction(f, status, value, options)}
                onEdit={(on) => onEdit(f.path, on)}
              />
            ))}
      </div>
    </div>
  );
}

function FieldRow({
  busy,
  field,
  documents,
  selected,
  related,
  editing,
  onSelect,
  onHover,
  onAction,
  onEdit,
}: {
  busy: boolean;
  field: ReviewField;
  documents: Document[] | undefined;
  selected: boolean;
  related: boolean;
  editing: boolean;
  onSelect: () => void;
  onHover: (h: boolean) => void;
  onAction: (status: FieldStatus, value?: number | string, options?: FieldOptions) => void | Promise<boolean>;
  onEdit: (on: boolean) => void;
}) {
  const level = riskLevel(field);
  const row = useRef<HTMLDivElement>(null);
  const shownValue = field.correctedValue ?? field.value;
  const s = field.source;
  const location = s.page ? `pág. ${s.page}` : s.sheet && s.cell ? `${s.sheet} · ${s.cell}` : s.locator;
  const where = `${s.document_id} · ${location}`;
  const pending = field.status === "candidate";
  const preliminary = isPreliminary(field);
  const design = isDesignValue(field);
  const auto = isAutoApproved(field);
  const interval =
    pending && field.interval && typeof field.value === "number" ? formatInterval(field.value, field.interval, field.unit) : null;

  return (
    <div
      ref={row}
      data-row={field.path}
      role="option"
      aria-selected={selected}
      tabIndex={0}
      onKeyDown={event => {
        if (event.target !== event.currentTarget || !["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        onSelect();
      }}
      onClick={onSelect}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      className={cn(
        "mb-0.5 cursor-default rounded-lg border px-2.5 py-1.5 sm:px-3",
        "transition-[background-color,border-color] duration-[var(--dur-fast)] ease-[var(--ease-out)]",
        selected ? "border-accent/45 bg-accent-soft/65"  : related ? "border-border bg-surface-sunken" : "border-transparent hover:bg-surface-sunken",
      )}
    >
      <div className={cn("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1", WIDE_COLUMNS)}>
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className={cn("size-1.5 shrink-0 rounded-full", level === "alto" ? "bg-danger" : level === "medio" ? "bg-warning" : "bg-faint")}
            title={`Impacto ${level}`}
          />
          <div className="min-w-0">
            <p className="text-[16px] leading-tight font-semibold text-strong [overflow-wrap:anywhere]" title={field.path}>{field.label}</p>
            <p className="truncate text-[13px] leading-snug text-muted">{field.group}</p>
          </div>
        </div>
          <div className="min-w-0 text-right @3xl:text-left">
            <motion.p
              key={String(shownValue)}
              initial={{ opacity: 0.4 }}
              animate={{ opacity: 1 }}
              className={cn("text-[17px] leading-tight font-semibold tabular-nums [overflow-wrap:anywhere]", field.status === "corrected" ? "text-accent-text" : "text-text")}
            >
              {formatValue(shownValue, field.unit)}
            </motion.p>
            {interval ? (
              <p className="text-xs text-muted" title="Intervalo conforme: contiene el valor verdadero con esa probabilidad">
                {interval}
              </p>
            ) : null}
          </div>
          <p className="col-start-1 flex min-w-0 items-center gap-1.5 pl-4 text-[13px] text-muted @3xl:col-start-auto @3xl:pl-0" title={where}>
            <FileText aria-hidden size={13} className="shrink-0" />
            <span className="truncate">{where}</span>
          </p>
          <div className="justify-self-end">
          {preliminary ? <Badge tone="warning">Preliminar</Badge> : auto ? (
            <span title="Confianza alta y valor encontrado en el original: no necesita revisión. Se puede revocar.">
              <Badge tone="approved"><Icon icon={Zap} size={12} /> Aprobado automáticamente</Badge>
            </span>
          ) : !pending ? (
            <FieldStatusBadge status={field.status} />
          ) : field.conflict ? <Badge tone="warning">Fuentes en conflicto</Badge> : field.abstained ? (
            <span title={`Confianza ${field.confidence.toFixed(2).replace(".", ",")} por debajo del umbral de revisión`}>
              <Badge tone="warning">{field.explanation?.startsWith("Rechazado") ? "Rechazado" : "Confírmelo"}</Badge>
            </span>
          ) : (
            <ConfidenceBar value={field.confidence} calibrated={field.calibrated} />
          )}
          </div>
      </div>

      {selected ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.16 }}
          className={cn("mt-1.5 grid items-center gap-2 border-t border-border/70 pt-1.5", !editing && "@3xl:flex @3xl:justify-end")}>
          {!editing && (field.explanation || field.status === "corrected" && field.correctedValue !== undefined && field.correctedValue !== field.value) ? (
            <div className="min-w-0 flex-1 space-y-0.5 text-[13px] leading-snug text-muted [overflow-wrap:anywhere]">
              {field.status === "corrected" && field.correctedValue !== undefined && field.correctedValue !== field.value ? (
                <p>Valor leído: {formatValue(field.value, field.unit)}</p>
              ) : null}
              {field.explanation ? <p>{field.explanation}</p> : null}
            </div>
          ) : null}
          {editing && documents ? (
            <EditValue
              busy={busy}
              field={field}
              documents={documents}
              onCancel={() => { row.current?.focus({ preventScroll: true }); onEdit(false); }}
              onSave={async (v, options) => {
                const saved = await onAction("corrected", v, options);
                if (saved !== false) onEdit(false);
              }}
            />
          ) : (
            <fieldset disabled={busy} className="flex min-w-0 flex-wrap gap-1 disabled:opacity-60 @3xl:shrink-0 @3xl:justify-end [&_button]:min-h-8 [&_button]:px-2.5 [&_button]:text-[13px]">
              {auto ? (
                <Tip content="Quita la aprobación automática y devuelve el campo a la cola de revisión">
                  <Button
                    size="sm"
                    onClick={(e) => (e.stopPropagation(), onAction("candidate", undefined, { explanation: "Aprobación automática revocada; pendiente de revisión." }))}
                  >
                    <Icon icon={Undo2} size={14} /> Revocar aprobación
                  </Button>
                </Tip>
              ) : null}
              {!preliminary ? <Tip content={design ? "Revisión técnica de la orden" : "Coincide con el plano"} shortcut={["A"]}>
                <Button size="sm" variant="primary" onClick={(e) => (e.stopPropagation(), onAction("accepted"))}>
                  <Icon icon={Check} size={14} /> Aceptar
                </Button>
              </Tip> : null}
              {!design ? <Tip content="Escribir el valor correcto" shortcut={["E"]}>
                <Button size="sm" disabled={!documents?.length} onClick={(e) => (e.stopPropagation(), onEdit(true))}>
                  <Icon icon={Pencil} size={14} /> Corregir
                </Button>
              </Tip> : null}
              {!preliminary && !design ? <><Button size="sm" variant="ghost" onClick={(e) => (e.stopPropagation(), onAction("candidate", undefined, { action: "reject" }))}>
                <Icon icon={X} size={14} /> Rechazar
              </Button>
              <Tip content="El plano no lo da; se usa el valor como supuesto" shortcut={["S"]}>
                <Button size="sm" variant="ghost" onClick={(e) => (e.stopPropagation(), onAction("assumed"))}>
                  <Icon icon={CircleHelp} size={14} /> Supuesto
                </Button>
              </Tip></> : null}
            </fieldset>
          )}
        </motion.div>
      ) : null}
    </div>
  );
}

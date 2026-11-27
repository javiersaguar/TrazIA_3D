import { FileText, X } from "lucide-react";
import { Badge, Icon } from "@/components/ui/primitives";
import { FieldStatusBadge } from "@/components/ui/status";
import { dimensionValue } from "./annotations";
import type { Annotation } from "./types";
import styles from "./viewer.module.css";

export function AnnotationDetails({ id, annotation, pinned, onClose }: {
  id: string; annotation: Annotation; pinned: boolean; onClose(): void;
}) {
  const context = annotation.label.split(/\s*·\s*/);
  const title = context.pop() ?? annotation.label;
  const source = annotation.source;
  const value = dimensionValue(annotation);
  const confidence = annotation.confidence.toLocaleString("es-ES", { style: "percent", maximumFractionDigits: 1 });
  const locator = source?.locator?.trim();
  const excerpt = source?.text_original?.trim();
  const amountLabels = [value, String(annotation.drawingValue ?? annotation.value)];
  const visibleLocator = locator && !amountLabels.includes(locator) ? locator : null;
  const visibleExcerpt = excerpt && excerpt !== locator && !amountLabels.includes(excerpt) ? excerpt : null;
  const state = annotation.state;

  return (
    <section id={id} aria-label={`Fuente y confianza de ${title}`} className={styles.dimensionDetails} data-pinned={pinned || undefined}
      onKeyDown={event => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        onClose();
      }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {context.length ? <p className="text-[11px] font-medium text-muted">{context.join(" / ")}</p> : null}
          <h3 className="font-semibold text-strong">{title}</h3>
        </div>
        {pinned ? <button type="button" aria-label="Cerrar detalle de la cota" onClick={onClose}
          className="grid size-7 shrink-0 place-items-center rounded-md text-muted hover:bg-surface-sunken hover:text-text">
          <Icon icon={X} size={15} />
        </button> : null}
      </div>
      <div className="my-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <p className="text-lg font-semibold tabular-nums text-strong">{state === "assumed" ? "≈ " : ""}{value}</p>
        {state === "candidate" || state === "accepted" || state === "corrected" || state === "assumed" ? (
          <FieldStatusBadge status={state} />
        ) : state === "conflict" || state === "abstained" ? (
          <Badge tone="warning">{state === "conflict" ? "Fuentes en conflicto" : "Por confirmar"}</Badge>
        ) : null}
      </div>
      <div className="space-y-1 border-t border-border pt-1.5 text-xs leading-snug text-muted">
        <div className="flex items-start justify-between gap-x-2 gap-y-1">
          <p className="flex min-w-0 items-start gap-1.5">
            <FileText aria-hidden size={13} className="mt-0.5 shrink-0 text-accent-text" />
            <span>{source ? <><span className="font-medium text-text">{source.document_id}</span>
              {source.page ? <span className="ml-1.5 inline-block">Pág. {source.page}</span> : null}
              {source.sheet ? <span className="ml-1.5 inline-block">{source.sheet}</span> : null}
              {source.cell ? <span className="ml-1.5 inline-block">{source.cell}</span> : null}</>
              : "Consulta el Inspector IFC"}</span>
          </p>
          <span className="shrink-0 whitespace-nowrap tabular-nums">Confianza {confidence}</span>
        </div>
        {visibleLocator ? <p>{visibleLocator}</p> : null}
        {visibleExcerpt ? <p className="text-text">«{visibleExcerpt}»</p> : null}
        {annotation.explanation ? <p>{annotation.explanation}</p> : null}
        {annotation.nominalSize !== undefined ? <p>Tamaño nominal de la conexión.</p> : null}
      </div>
    </section>
  );
}

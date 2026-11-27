"use client";

import { ChevronDown, ScanLine } from "lucide-react";
import { Icon } from "@/components/ui/primitives";
import { apiEnabled } from "@/lib/api/config";
import type { RevisionId } from "@/lib/mock/api";
import type { MarkReport, RevisionMark } from "./revision-marks";
import { fieldLabel } from "@/lib/field-labels";

export function RevisionMarksNotice({ revision, data, error, loading, onRetry, onSelect, onMark }: {
  revision: RevisionId; data?: MarkReport; error: Error | null; loading: boolean;
  onRetry(): void; onSelect(path: string): void; onMark(mark: RevisionMark): void;
}) {
  if (revision === "A") return null;
  if (!apiEnabled) return <p className="text-xs text-muted">Cruce de marcas: conecta la API para leer los originales.</p>;
  if (error) return <div role="alert" className="text-xs text-warning">{error.message}.
    <button type="button" className="ml-2 underline" onClick={onRetry}>Reintentar marcas</button></div>;
  if (loading || !data) return <p role="status" className="text-xs text-muted">Leyendo marcas de revisión…</p>;
  const count = data.unmarked_changes.length + data.marks_without_change.length;
  const incomplete = data.status !== "ok" && data.status !== "not_applicable";
  return <details className="group/marks rounded-xl border border-border bg-surface text-xs" data-testid="revision-mark-checks">
    <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl bg-surface-raised px-3 py-2 font-semibold text-strong">
      <Icon icon={ScanLine} size={15} className="text-accent-text" />
      <span className="min-w-0 flex-1">Cruce de marcas de revisión
        <span className="block font-normal text-muted">{count} {count === 1 ? "discrepancia" : "discrepancias"}{incomplete ? " · lectura parcial" : ""}</span>
      </span>
      <Icon icon={ChevronDown} size={15} className="text-muted group-open/marks:rotate-180" />
    </summary>
    <div className="px-3 pb-3">
      <p className="mt-2 text-muted">Se compara A → B. Las marcas son pistas: una nube o un Δ no confirma un cambio, y su ausencia no demuestra que no lo haya.</p>
      <ul className="mt-2 space-y-2">{data.documents.map(doc => <li key={doc.document_id}>
        <span className="text-text">{doc.filename}: {doc.marks.length} marcas candidatas.</span>
        {doc.unread_pages.length ? <span className="text-warning"> Sin lectura de marcas en páginas {doc.unread_pages.join(", ")}.</span> : null}
        {!["ok", "sin_marcas", "parcial", "sin_lectura"].includes(doc.status) ? <span className="text-warning"> Original no verificable o no disponible.</span> : null}
        {doc.pages_truncated ? <span className="text-warning"> Lectura limitada a 100 páginas.</span> : null}
        <div className="mt-1 flex flex-wrap gap-2">{doc.marks.map(mark => <button type="button" key={mark.id}
          onClick={() => onMark(mark)} className="text-accent-text underline underline-offset-2">
          {mark.kind === "delta" ? "Δ" : "Nube"}{mark.label ? ` ${mark.label}` : ""} · pág. {mark.page}
        </button>)}</div>
      </li>)}</ul>
      {data.unmarked_changes.length ? <div className="mt-3"><strong className="text-warning">Cambios sin marca próxima</strong>
        <ul>{data.unmarked_changes.map(c => <li key={`${c.document_id}-${c.path}`}><button type="button" className="text-accent-text underline underline-offset-2"
          onClick={() => onSelect(c.path)}>{fieldLabel(c.path)} · {c.document_id}</button></li>)}</ul></div> : null}
      {data.marks_without_change.length ? <div className="mt-3"><strong className="text-warning">Marcas sin cambio detectado</strong>
        <ul>{data.marks_without_change.map(mark => <li key={mark.id}><button type="button" className="text-accent-text underline underline-offset-2" onClick={() => onMark(mark)}>
          {mark.kind === "delta" ? "Δ" : "Nube"} · {mark.document_id}, página {mark.page}
        </button></li>)}</ul></div> : null}
      {data.unlocated_changes.length ? <p className="mt-2 text-muted">Sin ubicación en el plano nuevo: {data.unlocated_changes.join(", ")}. No se juzgan por sus cajas antiguas.</p> : null}
    </div>
  </details>;
}

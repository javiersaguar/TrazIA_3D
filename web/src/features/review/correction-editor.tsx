"use client";

import { Check, Link2, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button, Icon } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { displayUnit } from "@/lib/format";
import type { FieldOptions } from "@/lib/mock/api";
import { isPreliminary, type ReviewField } from "@/lib/mock/fields";
import type { Document } from "@/lib/types/revision";
import { isSpreadsheet, parseReviewNumber, parseReviewRegion } from "./review-value";

const inputClass = "h-9 w-full min-w-0 rounded-lg border border-border bg-surface px-2.5 text-sm text-text placeholder:text-muted aria-invalid:border-danger";
const inlineLabel = "flex h-9 min-w-0 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 focus-within:border-accent has-[[aria-invalid=true]]:border-danger";

function validPage(page: number, document: Document) {
  return Number.isSafeInteger(page) && page > 0 && (document.page_count == null || page <= document.page_count);
}

export function CorrectionEditor({ field: openedField, documents, busy, onSave, onCancel }: {
  field: ReviewField; documents: readonly Document[]; busy: boolean;
  onSave: (value: number | string, options: FieldOptions) => void | Promise<void>;
  onCancel: () => void;
}) {
  const [field] = useState(openedField);
  const current = field.correctedValue ?? field.value;
  const numeric = typeof current === "number";
  const unit = displayUnit(field.unit);
  const original = field.source;
  const originalDocument = documents.find(document => document.id === original.document_id);
  const preliminary = isPreliminary(field);
  const needsEvidence = preliminary || !originalDocument || !original.locator.trim() ||
    (isSpreadsheet(originalDocument) ? !original.sheet?.trim() || !original.cell?.trim() : !validPage(original.page ?? 0, originalDocument));
  const [draft, setDraft] = useState(() => numeric
    ? current.toLocaleString("es-ES", { useGrouping: false, maximumSignificantDigits: 21 })
    : String(current));
  const [note, setNote] = useState("");
  const [replaceEvidence, setReplaceEvidence] = useState(false);
  const useNewEvidence = needsEvidence || replaceEvidence;
  const [documentId, setDocumentId] = useState(original.document_id);
  const [page, setPage] = useState(String(preliminary ? "" : original.page ?? ""));
  const [sheet, setSheet] = useState(preliminary ? "" : original.sheet ?? "");
  const [cell, setCell] = useState(preliminary ? "" : original.cell ?? "");
  const [locator, setLocator] = useState(needsEvidence ? "" : original.locator);
  const [region, setRegion] = useState(needsEvidence ? "" : original.bbox?.join(" ") ?? "");
  const [submitted, setSubmitted] = useState(false);
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus({ preventScroll: true });
    input.current?.select();
  }, []);

  const document = documents.find(item => item.id === documentId);
  const spreadsheet = document ? isSpreadsheet(document) : false;
  const pageNumber = Number(page);
  const parsed = numeric ? parseReviewNumber(draft) : draft.trim();
  const bbox = spreadsheet ? null : parseReviewRegion(region);
  let issue: { name: string; message: string } | undefined;
  if (typeof parsed === "number" ? !Number.isFinite(parsed) : !parsed) {
    issue = { name: "draft", message: numeric ? "Introduce un número válido." : "Introduce el valor corregido." };
  } else if (useNewEvidence) {
    if (!document) issue = { name: "document", message: "Selecciona un documento original de esta revisión." };
    else if (spreadsheet && !sheet.trim()) issue = { name: "sheet", message: "Indica el nombre de la hoja." };
    else if (spreadsheet && !cell.trim()) issue = { name: "cell", message: "Indica la celda, por ejemplo B12." };
    else if (!spreadsheet && !validPage(pageNumber, document)) {
      const count = document.page_count;
      const message = count === 1 ? "Indica la página 1. Es la única del documento."
        : count ? `Indica una página entre 1 y ${count}.` : "Indica un número entero de página, a partir de 1.";
      issue = { name: "page", message };
    }
    else if (!locator.trim()) issue = { name: "locator", message: "Describe dónde aparece el valor en el original." };
    else if (!spreadsheet && region.trim() && !bbox) issue = { name: "region", message: "Introduce cuatro coordenadas ordenadas entre 0 y 1: x₀, y₀, x₁ e y₁." };
  }
  const sourceControl = (name: string) => ({
    name,
    "aria-invalid": submitted && issue?.name === name || undefined,
    "aria-describedby": submitted && issue?.name === name ? `${id}-error` : undefined,
  });

  return (
    <form noValidate aria-label={`Corregir ${field.label}`} onClick={event => event.stopPropagation()}
      onKeyDown={event => {
        event.stopPropagation();
        if (event.key === "Escape" && !busy) {
          event.preventDefault();
          onCancel();
        }
      }}
      onSubmit={event => {
        event.preventDefault();
        if (busy) return;
        setSubmitted(true);
        if (issue) {
          event.currentTarget.querySelector<HTMLElement>(`[name="${issue.name}"]`)?.focus();
          return;
        }
        void onSave(parsed, {
          action: "correct",
          explanation: note.trim() || (preliminary || field.abstained ? null : undefined),
          source: useNewEvidence && document ? {
            document_id: document.id, locator: locator.trim(),
            page: spreadsheet ? null : pageNumber, sheet: spreadsheet ? sheet.trim() : null,
            cell: spreadsheet ? cell.trim() : null, bbox,
            confidence: original.confidence, confidence_raw: original.confidence_raw, channel: "humano",
          } : undefined,
        });
      }}>
      <fieldset disabled={busy} className="space-y-2 text-sm">
        <div className="grid min-w-0 grid-cols-[minmax(0,.7fr)_minmax(0,1fr)] items-center gap-2 @2xl:grid-cols-[minmax(0,.72fr)_minmax(0,1fr)_auto]">
          <label className={inlineLabel}>
            <span className="font-medium text-muted">Valor</span>
            <input {...sourceControl("draft")} ref={input} required value={draft} onChange={event => setDraft(event.target.value)}
              inputMode={numeric ? "decimal" : "text"} aria-label={`Nuevo valor de ${field.label}`}
              className="w-full min-w-0 bg-transparent font-semibold text-strong outline-none! tabular-nums" />
            {unit ? <span aria-label={`Unidad: ${unit}`} className="shrink-0 text-muted">{unit}</span> : null}
          </label>
          <label className={inlineLabel}>
            <span className="font-medium text-muted">Nota</span>
            <input value={note} onChange={event => setNote(event.target.value)} maxLength={2000}
              aria-label="Nota de revisión (opcional)" placeholder="Opcional"
              className="w-full min-w-0 bg-transparent text-text outline-none! placeholder:text-muted" />
          </label>
          <div className="col-span-2 flex flex-wrap items-center justify-end gap-1.5 @2xl:col-span-1">
            {needsEvidence ? (
              <span className="mr-auto flex items-center gap-1.5 text-xs font-medium text-warning @2xl:mr-2">
                <Icon icon={Link2} size={15} /> Evidencia requerida
              </span>
            ) : (
              <Button variant={useNewEvidence ? "secondary" : "ghost"} aria-expanded={useNewEvidence} aria-controls={`${id}-source`}
                onClick={() => setReplaceEvidence(value => !value)}>
                <Icon icon={Link2} size={15} /> Cambiar evidencia
              </Button>
            )}
            <Button variant="ghost" onClick={onCancel} title="Cancelar (Esc)"><Icon icon={X} size={15} /> Cancelar</Button>
            <Button variant="primary" type="submit"><Icon icon={Check} size={15} /> {busy ? "Guardando…" : "Guardar"}</Button>
          </div>
        </div>
        {useNewEvidence ? (
          <div id={`${id}-source`} className={cn(
            "grid min-w-0 grid-cols-2 gap-x-2 gap-y-1.5 rounded-lg border border-border/80 bg-surface-sunken/55 px-2.5 py-2 text-[13px] text-muted",
            spreadsheet ? "@4xl:grid-cols-[minmax(0,1.2fr)_minmax(0,.8fr)_minmax(0,.55fr)_minmax(0,1.4fr)]"
              : "@4xl:grid-cols-[minmax(0,1.15fr)_minmax(4rem,.35fr)_minmax(0,1.45fr)_minmax(0,1fr)]",
          )}>
            <label className="col-span-2 min-w-0 space-y-0.5 @4xl:col-span-1">
              <span>Documento original</span>
              <select {...sourceControl("document")} className={inputClass} required value={document ? documentId : ""}
                onChange={event => {
                  setDocumentId(event.target.value);
                  setPage(""); setSheet(""); setCell(""); setLocator(""); setRegion("");
                }}>
                <option value="" disabled>Elige un documento</option>
                {documents.map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}
              </select>
            </label>
            {spreadsheet ? <>
              <label className="min-w-0 space-y-0.5"><span>Hoja</span>
                <input {...sourceControl("sheet")} className={inputClass} required value={sheet} onChange={event => setSheet(event.target.value)} />
              </label>
              <label className="min-w-0 space-y-0.5"><span>Celda</span>
                <input {...sourceControl("cell")} className={inputClass} required value={cell} onChange={event => setCell(event.target.value)} />
              </label>
            </> : (
              <label className="min-w-0 space-y-0.5"><span>Página{document?.page_count ? ` (máx. ${document.page_count})` : ""}</span>
                <input {...sourceControl("page")} className={inputClass} required type="number" min={1} max={document?.page_count ?? undefined}
                  step={1} value={page} onChange={event => {
                    setPage(event.target.value);
                    setRegion("");
                  }} />
              </label>
            )}
            <label className={cn("min-w-0 space-y-0.5 @4xl:col-span-1", spreadsheet && "col-span-2")}>
              <span>Localizador</span>
              <input {...sourceControl("locator")} className={inputClass} required value={locator} onChange={event => setLocator(event.target.value)}
                placeholder={spreadsheet ? "Fila o encabezado" : "Cota, vista o tabla"} />
            </label>
            {!spreadsheet ? (
              <label className="col-span-2 min-w-0 space-y-0.5 @4xl:col-span-1">
                <span>Región (opcional)</span>
                <input {...sourceControl("region")} className={inputClass} value={region} onChange={event => setRegion(event.target.value)}
                  placeholder="x₀ y₀ x₁ y₁" />
              </label>
            ) : null}
          </div>
        ) : null}
        {submitted && issue ? <p id={`${id}-error`} role="alert" className="text-[13px] font-medium text-danger">{issue.message}</p> : null}
      </fieldset>
    </form>
  );
}

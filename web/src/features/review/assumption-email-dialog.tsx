"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Copy, Mail, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/primitives";
import type { ReviewField } from "@/lib/mock/fields";
import type { Document } from "@/lib/types/revision";
import { assumptionMailto, draftAssumptionEmail } from "./assumption-email";

const input = "w-full rounded-lg border border-border bg-surface-sunken px-3 py-2 text-sm text-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

export function AssumptionEmailDialog({ scope, fields, documents, busy }: {
  scope: { tag: string; revision: string; project?: string };
  fields?: readonly ReviewField[];
  documents?: readonly Document[];
  busy: boolean;
}) {
  const [draft, setDraft] = useState<{ subject: string; body: string } | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const count = fields?.filter(field => field.status === "assumed").length ?? 0;
  if (!count || !fields) return null;

  const mailto = draft ? assumptionMailto(draft.subject, draft.body) : null;
  async function copy() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(`Asunto: ${draft.subject}\n\n${draft.body}`);
      setCopyStatus("Asunto y mensaje copiados.");
    } catch {
      setCopyStatus("Puedes seleccionar y copiar el asunto y el mensaje.");
    }
  }

  return (
    <Dialog.Root open={draft !== null} onOpenChange={open => {
      setCopyStatus("");
      setDraft(open ? draftAssumptionEmail(scope, fields, documents) : null);
    }}>
      <Dialog.Trigger asChild>
        <Button type="button" size="sm" disabled={busy}>
          <Mail size={15} aria-hidden /> Correo de supuestos ({count})
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="cmd-overlay fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px]" />
        <Dialog.Content className="cmd-content fixed top-1/2 left-1/2 z-50 flex max-h-[85dvh] w-[min(650px,calc(100%-24px))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-[var(--radius-panel)] border border-border bg-surface shadow-[var(--shadow-pop)]">
          <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
            <div>
              <Dialog.Title className="text-lg font-semibold text-strong">Solicitar confirmación de datos</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted">Revisa el borrador antes de abrirlo en tu aplicación de correo.</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="Cerrar borrador" className="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-raised hover:text-text">
                <X size={17} aria-hidden />
              </button>
            </Dialog.Close>
          </header>
          {draft && <div className="min-h-0 space-y-3 overflow-y-auto px-4 py-4 sm:px-5">
            <label className="block space-y-1 text-sm text-muted">
              <span>Asunto</span>
              <input className={input} value={draft.subject} onChange={event => setDraft({ ...draft, subject: event.target.value })} />
            </label>
            <label className="block space-y-1 text-sm text-muted">
              <span>Mensaje</span>
              <textarea rows={10} className={input} value={draft.body} onChange={event => setDraft({ ...draft, body: event.target.value })} />
            </label>
            {!mailto && <p className="text-sm text-muted">Copia el borrador para pegarlo en tu correo.</p>}
          </div>}
          <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-border px-4 py-3 sm:px-5">
            <p role="status" className="mr-auto text-sm text-muted">{copyStatus}</p>
            <Button type="button" size="sm" onClick={() => void copy()}><Copy size={15} aria-hidden /> Copiar borrador</Button>
            {mailto && <a href={mailto} className="inline-flex h-8 items-center rounded-lg bg-accent px-3 text-sm font-semibold text-accent-contrast hover:bg-accent/90">Abrir en mi correo</a>}
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

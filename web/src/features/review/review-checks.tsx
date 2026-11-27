"use client";

import { ClipboardCheck, X } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import { Button, Icon } from "@/components/ui/primitives";

export function ReviewChecks({ count, children }: {
  count: number;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  function close() { setOpen(false); trigger.current?.focus(); }

  return (
    <div onBlur={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }} onKeyDown={event => {
      if (event.key === "Escape" && open) { event.stopPropagation(); close(); }
    }}>
      <Button ref={trigger} type="button" size="sm" aria-expanded={open} aria-controls={id}
        onClick={() => setOpen(value => !value)}>
        <ClipboardCheck aria-hidden size={15} />
        Comprobaciones
        {count ? <span className="rounded-full bg-warning/15 px-1.5 text-xs font-semibold tabular-nums text-warning"
          aria-label={`${count} avisos`}>{count}</span> : null}
      </Button>
      {open ? <section id={id} aria-label="Comprobaciones de la revisión"
        className="absolute top-full right-0 mt-2 flex max-h-[min(65dvh,530px)] w-[min(410px,100%)] flex-col overflow-hidden rounded-2xl border border-border-strong bg-surface shadow-[var(--shadow-pop)]">
        <header className="flex shrink-0 items-center gap-2.5 border-b border-border bg-surface-raised px-3 py-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-text"><Icon icon={ClipboardCheck} size={16} /></span>
          <h2 className="min-w-0 flex-1 text-sm font-semibold text-strong">Comprobaciones de la revisión</h2>
          <button type="button" onClick={close} aria-label="Cerrar comprobaciones"
            className="grid size-8 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-sunken hover:text-text"><Icon icon={X} /></button>
        </header>
        <div className="min-h-0 space-y-2 overflow-y-auto overscroll-contain p-2.5">
          {children(() => setOpen(false))}
        </div>
      </section> : null}
    </div>
  );
}

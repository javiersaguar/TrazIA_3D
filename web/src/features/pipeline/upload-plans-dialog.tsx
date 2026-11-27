"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { FileUp, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Icon } from "@/components/ui/primitives";
import { usePipeline } from "@/stores/pipeline";
import { IntakeForm } from "./intake-form";

export function UploadPlansDialog() {
  const [open, setOpen] = useState(false);
  const uploading = usePipeline(state => state.running && !state.jobId);
  const router = useRouter();

  return (
    <Dialog.Root open={open} onOpenChange={next => { if (next || !uploading) setOpen(next); }}>
      <Dialog.Trigger asChild>
        <Button variant="primary">
          <Icon icon={Upload} size={16} /> Subir planos
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="cmd-overlay fixed inset-0 z-[60] bg-[var(--scrim)] backdrop-blur-[3px] motion-reduce:animate-none!"
          onDragOver={event => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); }}
          onDrop={event => event.preventDefault()} />
        <Dialog.Content className="cmd-content fixed top-1/2 left-1/2 z-[60] flex max-h-[calc(100dvh-24px)] w-[min(620px,calc(100%-24px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-border-strong bg-surface shadow-[var(--shadow-pop)] motion-reduce:animate-none!"
          onDragOver={event => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); }}
          onDrop={event => event.preventDefault()}>
          <header className="flex shrink-0 items-start gap-3 border-b border-border bg-surface-raised px-4 py-3.5 sm:px-6 sm:py-4">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent/20 bg-accent-soft text-accent-text sm:size-11">
              <Icon icon={FileUp} size={21} />
            </span>
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-xl leading-tight font-semibold text-strong sm:text-2xl">Subir planos</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm leading-snug text-muted">Añade los PDF de un mismo equipo y versión.</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" aria-label="Cerrar subida de planos" disabled={uploading} className="-mr-1 size-11 shrink-0 p-0">
                <Icon icon={X} size={19} />
              </Button>
            </Dialog.Close>
          </header>
          <IntakeForm onCancel={() => setOpen(false)} onSubmitted={id => {
            setOpen(false);
            router.push(`/pipeline?trabajo=${encodeURIComponent(id)}`);
          }} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Box } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { Button, Icon } from "@/components/ui/primitives";
import { loadDocument } from "./catalogue";

const IfcViewer = dynamic(() => import("@/features/viewer3d").then((m) => m.IfcViewer), {
  ssr: false,
  loading: () => <p role="status" className="p-4 text-sm text-muted">Cargando visor IFC…</p>,
});

export function SketchModelDialog({ tag, name, ifc, documentId, published = false, primary = false }: {
  tag: string; name: string; ifc?: string; documentId?: string; published?: boolean; primary?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [local, setLocal] = useState<{ id: string; url: string | null }>();
  useEffect(() => {
    if (!open || !documentId) return;
    let active = true;
    let url: string | null = null;
    void loadDocument(documentId).catch(() => undefined).then((file) => {
      if (!active) return;
      url = file ? URL.createObjectURL(file) : null;
      setLocal({ id: documentId, url });
    });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [open, documentId]);
  const localFile = local?.id === documentId ? local : undefined;
  const url = ifc ?? localFile?.url;

  return (
    <Dialog.Root open={open} onOpenChange={(next) => {
      setOpen(next);
      if (!next) setLocal(undefined);
    }}>
      <Dialog.Trigger asChild>
        {primary ? <Button variant="primary"><Icon icon={Box} size={16} /> Ver modelo 3D</Button> :
          <button type="button" aria-label={`Ver 3D de ${tag}`}
            className="shrink-0 rounded-md text-[12px] text-accent-text underline-offset-2 hover:underline">
            Ver 3D
          </button>}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[var(--scrim)]" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 flex max-h-[92dvh] w-[min(860px,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-auto rounded-xl border border-border bg-surface p-4 shadow-xl">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="font-semibold text-strong">{name}</Dialog.Title>
              <Dialog.Description className="text-sm text-muted">
                {tag} · {published ? "IFC publicado en el catálogo" : documentId ? "IFC guardado en el navegador" : "IFC4 conceptual sintético · DRAFT"}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild><Button size="sm">Cerrar</Button></Dialog.Close>
          </div>
          <div className="relative h-[min(54dvh,520px)] min-h-[280px] overflow-hidden rounded-lg border border-border">
            {url ? <IfcViewer ifcUrl={url} /> : localFile
              ? <p role="alert" className="p-4 text-sm text-danger">El IFC no está disponible en este navegador.</p>
              : <p role="status" className="p-4 text-sm text-muted">Cargando IFC…</p>}
          </div>
          {url ? <a href={url} download={documentId ? `${name.replace(/\.ifc$/i, "")}.ifc` : true}
            className="self-start text-sm text-accent-text underline-offset-2 hover:underline">
            Descargar IFC
          </a> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

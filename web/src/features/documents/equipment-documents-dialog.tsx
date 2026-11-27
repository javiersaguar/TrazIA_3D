"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Box, ExternalLink, FileText, X } from "lucide-react";
import Link from "next/link";
import { Badge, Button, Icon } from "@/components/ui/primitives";
import { modelHref } from "@/features/workspace/model-links";
import { apiURL } from "@/lib/api/config";
import { DeleteRevisionButton } from "@/features/revisions/delete-revision-button";
import type { GroupedRevision } from "./dataset-documents";
import { IfcThumbnail } from "./ifc-thumbnail";

/**
 * Historial de la ficha: cada revisión, de la más nueva a la más antigua, con sus PDF y hojas de
 * datos, el acceso a su IFC cuando existe y el borrado de esa revisión.
 */
export function EquipmentDocumentsDialog({ tag, project, revisions }: {
  tag: string; project?: string; revisions: GroupedRevision[];
}) {
  const history = [...revisions].reverse().filter(revision => revision.documents.length || revision.model);
  const files = history.reduce((total, revision) => total + revision.documents.length, 0);
  const newest = history.find(revision => revision.model)?.revision;
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <Button aria-label={`Planos y hojas de datos de ${tag} (${files})`}
          className="h-auto min-h-9 max-w-full py-1.5 text-left leading-snug whitespace-normal">
          <FileText aria-hidden size={15} className="shrink-0" />
          Planos y hojas de datos ({files})
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="cmd-overlay fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px]" />
        <Dialog.Content className="cmd-content fixed top-1/2 left-1/2 z-50 flex max-h-[min(85dvh,680px)] w-[min(640px,calc(100%-24px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[var(--radius-panel)] border border-border bg-surface shadow-[var(--shadow-pop)]">
          <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
            <div>
              <p className="font-mono text-xs font-medium text-accent-text">{tag}{project ? ` · ${project}` : ""}</p>
              <Dialog.Title className="mt-0.5 text-lg leading-tight font-semibold text-strong sm:text-xl">Planos y hojas de datos</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted">
                {history.length === 1 ? "1 versión" : `${history.length} versiones`}, de la más reciente a la más antigua.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="Cerrar planos"
                className="grid size-11 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-raised hover:text-text">
                <X aria-hidden size={18} />
              </button>
            </Dialog.Close>
          </div>
          <ol aria-label={`Versiones de ${tag}`} className="min-h-0 space-y-3 overflow-y-auto overscroll-contain px-3 py-3 sm:px-4">
            {history.map(revision => (
              <li key={revision.revision} className="rounded-xl border border-border">
                <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
                  {revision.model ? (
                    <div aria-hidden><IfcThumbnail name={tag} url={apiURL(revision.model.ifc)} size="row" /></div>
                  ) : null}
                  <span className="text-sm font-semibold text-strong">Rev. {revision.revision}</span>
                  {revision.revision === newest ? <Badge tone="accent">Última</Badge> : null}
                  {revision.model ? (revision.approved ? <Badge tone="approved">Aprobada</Badge> : <Badge tone="warning">Borrador</Badge>)
                    : <Badge>Sin modelo</Badge>}
                  <span className="ml-auto flex flex-wrap items-center gap-1">
                    {revision.model ? (
                      <Dialog.Close asChild>
                        <Link href={modelHref("revision", revision.model.identity)} prefetch={false}
                          className="inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-accent-text hover:bg-surface-raised">
                          <Icon icon={Box} size={13} /> Ver 3D
                        </Link>
                      </Dialog.Close>
                    ) : null}
                    {revision.model ? (
                      <DeleteRevisionButton identity={revision.model.identity} label={revision.revision}
                        version={revision.version} approved={revision.approved} />
                    ) : null}
                  </span>
                </header>
                <ul aria-label={`Documentos de la Rev. ${revision.revision}`} className="divide-y divide-border px-3">
                  {revision.documents.map(file => {
                    const original = file.id && file.model
                      ? apiURL(`/revisions/${encodeURIComponent(file.model.identity)}/documents/${encodeURIComponent(file.id)}`)
                      : undefined;
                    return (
                      <li key={file.filename} className="flex min-w-0 items-center gap-2 py-1.5">
                        <FileText aria-hidden size={15} className="shrink-0 text-muted" />
                        <span className="min-w-0 flex-1 text-sm text-strong [overflow-wrap:anywhere]">{file.filename}</span>
                        {original ? (
                          <a href={original} target="_blank" rel="noreferrer" title="Abrir original en una pestaña nueva"
                            aria-label={`Abrir original de ${file.filename} en una pestaña nueva`}
                            className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-accent-text hover:bg-surface-raised">
                            {file.filename.toLowerCase().endsWith(".pdf") ? "PDF" : "Abrir"} <ExternalLink aria-hidden size={13} />
                          </a>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ol>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

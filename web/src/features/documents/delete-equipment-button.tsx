"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, Trash2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Icon } from "@/components/ui/primitives";
import { REVISION_QUERIES } from "@/features/revisions/delete-revision-button";
import { useIsAdmin } from "@/lib/accounts";
import { ApiError, deleteFicha, retireFicha } from "@/lib/api/client";
import { apiEnabled } from "@/lib/api/config";
import type { GroupedRevision } from "./dataset-documents";

/**
 * Papelera de la tarjeta: borra todas las revisiones de la ficha (proyecto + equipo). Si alguna
 * está protegida la API no borra nada y explica por qué; entonces se puede retirar la ficha del
 * catálogo conservando su historial. Solo para administradores.
 */
export function DeleteEquipmentButton({ tag, project, equipmentId, revisions }: {
  tag: string; project: string; equipmentId: string; revisions: GroupedRevision[];
}) {
  const admin = useIsAdmin();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [blocked, setBlocked] = useState<string | null>(null);
  const saved = [...revisions].reverse().filter(revision => revision.model);
  const refresh = () => { for (const queryKey of REVISION_QUERIES) void client.invalidateQueries({ queryKey: [...queryKey] }); };
  const removal = useMutation({
    mutationFn: () => deleteFicha(project, equipmentId),
    onSuccess: () => { toast.success(`${tag} (${project}) borrado`); setOpen(false); refresh(); },
    onError: error => { if (error instanceof ApiError && error.status === 409) setBlocked(error.message); refresh(); },
  });
  const retirement = useMutation({
    mutationFn: () => retireFicha({ project_id: project, equipment_id: equipmentId || null, tag }),
    onSuccess: () => { toast.success(`${tag} (${project}) retirado del catálogo`); setOpen(false); refresh(); },
  });
  if (!apiEnabled || !admin) return null;
  const busy = removal.isPending || retirement.isPending;
  const error = [removal.error, retirement.error].find(item => item instanceof Error && !(item instanceof ApiError && item.status === 409));
  const canDelete = Boolean(saved.length && equipmentId);

  return (
    <Dialog.Root open={open} onOpenChange={next => { setOpen(next); if (next) { setBlocked(null); removal.reset(); retirement.reset(); } }}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Borrar ${tag} de ${project}`} title="Borrar este diseño"
          className="absolute top-0 right-0 size-9 p-0 text-muted hover:text-danger">
          <Icon icon={Trash2} size={15} />
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="cmd-overlay fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px]" />
        <Dialog.Content className="cmd-content fixed top-1/2 left-1/2 z-50 w-[min(480px,calc(100%-24px))] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-panel)] border border-border bg-surface shadow-[var(--shadow-pop)]">
          <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-3">
            <div>
              <p className="font-mono text-xs font-medium text-accent-text">{tag} · {project}</p>
              <Dialog.Title className="mt-0.5 text-lg font-semibold text-strong">
                {canDelete ? "Borrar este diseño" : "Retirar este diseño"}
              </Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="Cerrar" className="grid size-10 place-items-center rounded-lg text-muted hover:bg-surface-raised">
                <X aria-hidden size={18} />
              </button>
            </Dialog.Close>
          </div>
          <div className="space-y-3 px-5 py-4">
            <Dialog.Description className="text-sm text-text">
              {canDelete
                ? `${saved.length === 1 ? "Se borrará su revisión" : `Se borrarán sus ${saved.length} revisiones`} con su modelo y su historial de cambios. Las fichas con el mismo código en otros proyectos no se tocan.`
                : "No tiene revisiones guardadas. Retirarlo lo quita del catálogo; sus planos se conservan."}
            </Dialog.Description>
            {saved.length ? (
              <ul aria-label="Revisiones afectadas" className="divide-y divide-border rounded-lg border border-border">
                {saved.map(revision => (
                  <li key={revision.revision} className="flex items-center justify-between gap-2 px-3 py-1.5 text-sm">
                    <span className="text-strong">Rev. {revision.revision}</span>
                    {revision.approved ? <Badge tone="approved">Aprobada</Badge> : <Badge tone="warning">Borrador</Badge>}
                  </li>
                ))}
              </ul>
            ) : null}
            {blocked ? (
              <div role="alert" className="space-y-1 rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning">
                <p>{blocked}</p>
                <p className="text-xs">Retirarla la quita del catálogo y de las búsquedas, conserva todas sus revisiones y no vuelve al reiniciar la API.</p>
              </div>
            ) : null}
            {error instanceof Error ? <p role="alert" className="text-sm text-danger">{error.message}</p> : null}
          </div>
          <footer className="flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-3">
            <Dialog.Close asChild><Button variant="ghost" disabled={busy}>Cancelar</Button></Dialog.Close>
            {canDelete && !blocked ? (
              <Button variant="danger" disabled={busy} onClick={() => removal.mutate()}>
                <Icon icon={Trash2} size={14} />
                {removal.isPending ? "Borrando…" : saved.length === 1 ? "Borrar la revisión" : `Borrar las ${saved.length} revisiones`}
              </Button>
            ) : (
              <Button variant="primary" disabled={busy} onClick={() => retirement.mutate()}>
                <Icon icon={Archive} size={14} />
                {retirement.isPending ? "Retirando…" : "Retirar del catálogo"}
              </Button>
            )}
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

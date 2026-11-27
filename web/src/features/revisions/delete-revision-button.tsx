"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button, Icon } from "@/components/ui/primitives";
import { useCanEdit } from "@/lib/accounts";
import { deleteRevision } from "@/lib/api/client";
import { apiEnabled } from "@/lib/api/config";
import { qk } from "@/lib/queries";

/** Consultas que cambian al borrar una revisión: equipos, versiones, lote y documentos citados. */
export const REVISION_QUERIES = [qk.equipment(), ["version"], ["lote-resumen"], ["documents"]] as const;

/**
 * «Borrar revisión» con confirmación. La API decide si se puede: una revisión aprobada, usada por
 * un trabajo o enlazada por un cambio de diseño no se borra, y su motivo se muestra aquí.
 */
export function DeleteRevisionButton({ identity, label, version, approved = false }: {
  identity: string; label: string; version: number | null; approved?: boolean;
}) {
  const canEdit = useCanEdit();
  const client = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const removal = useMutation({
    mutationFn: () => deleteRevision(identity, version ?? 0, key),
    onSuccess: () => {
      toast.success(`Revisión ${label} borrada`);
      for (const queryKey of REVISION_QUERIES) void client.invalidateQueries({ queryKey: [...queryKey] });
    },
    onError: () => { setConfirming(false); setKey(crypto.randomUUID()); },
  });
  if (!apiEnabled || !canEdit || version === null) return null;
  const error = removal.error instanceof Error ? removal.error.message : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {confirming ? (
        <span className="inline-flex items-center gap-2" role="group" aria-label={`Confirmar borrado de la revisión ${label}`}>
          <span className="text-xs text-muted">¿Borrar Rev {label} y su historial de cambios?</span>
          <Button variant="danger" size="sm" disabled={removal.isPending} onClick={() => removal.mutate()}>
            {removal.isPending ? "Borrando…" : "Sí, borrar"}
          </Button>
          <Button variant="ghost" size="sm" disabled={removal.isPending} onClick={() => setConfirming(false)}>Cancelar</Button>
        </span>
      ) : (
        <Button variant="ghost" size="sm" aria-label={`Borrar revisión ${label}`}
          title={approved ? "Una revisión aprobada no se borra" : "Borrar esta revisión en borrador"}
          onClick={() => { removal.reset(); setConfirming(true); }}>
          <Icon icon={Trash2} size={13} /> Borrar revisión
        </Button>
      )}
      {error ? <span role="alert" className="basis-full text-xs text-danger">{error}</span> : null}
    </span>
  );
}

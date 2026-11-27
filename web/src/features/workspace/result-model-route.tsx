"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/primitives";
import { apiRevisionSnapshot, rememberRevision } from "@/lib/api/client";
import { apiEnabled } from "@/lib/api/config";
import { flattenRevision } from "@/lib/mock/fields";
import { qk, useEquipment as useEquipmentRows } from "@/lib/queries";
import { useEquipment } from "@/stores/equipment";
import { useSelection } from "@/stores/selection";
import { useUi } from "@/stores/ui";
import { modelTarget } from "./model-target";

export function ResultModelRoute({ identity, children }: { identity: string; children: ReactNode }) {
  const rows = useEquipmentRows();
  const cache = useQueryClient();
  const initialized = useRef(false);
  const revision = useQuery({
    queryKey: ["model-entry", identity],
    queryFn: () => apiRevisionSnapshot(identity),
    enabled: apiEnabled,
  });
  const result = useEquipment(state => state.openedResult);
  const setActive = useEquipment(state => state.setActive);
  const setRevision = useUi(state => state.setRevision);
  const select = useSelection(state => state.setSelected);
  const snapshot = revision.data;
  const record = snapshot?.record;
  const target = useMemo(
    () => record && !rows.isPending ? modelTarget(record, rows.data ?? []) : null,
    [record, rows.data, rows.isPending],
  );

  useEffect(() => {
    if (!target || !snapshot || initialized.current) return;
    initialized.current = true;
    select(null);
    setRevision(target.slot);
    setActive(target.equipment, identity);
    rememberRevision(target.slot, snapshot.record, snapshot.etag);
    cache.setQueryData(qk.revision(target.slot), snapshot.record);
    cache.setQueryData(qk.fields(target.slot), flattenRevision(snapshot.record));
  }, [cache, identity, target, snapshot, select, setRevision, setActive]);

  if (!apiEnabled) return <p>Configura la API para abrir este modelo.</p>;
  if (revision.isError && !record) return (
    <div className="space-y-3">
      <p role="alert">{revision.error.message}</p>
      <Button onClick={() => void revision.refetch()}>Reintentar</Button>
    </div>
  );
  if (result !== identity || !target) return <p role="status">Abriendo el modelo 3D…</p>;
  return children;
}

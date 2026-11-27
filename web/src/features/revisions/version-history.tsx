"use client";

import { useQueries } from "@tanstack/react-query";
import { CheckCircle2, Download, FileText, GitCompareArrows, Layers } from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge, Button, EmptyState, Icon, Panel, PanelHeader, Pill, Skeleton } from "@/components/ui/primitives";
import { AuthorName } from "@/components/shell/author";
import { cn } from "@/lib/cn";
import { getRevision, type RevisionId } from "@/lib/api";
import { apiRevisionById } from "@/lib/api/client";
import { apiEnabled, apiURL } from "@/lib/api/config";
import { DEMO } from "@/lib/mock/api";
import { useEquipment as useEquipmentRows } from "@/lib/queries";
import { modelHref } from "@/features/workspace/model-links";
import { modelTarget } from "@/features/workspace/model-target";
import { useEquipment } from "@/stores/equipment";
import { useUi } from "@/stores/ui";
import { DeleteRevisionButton } from "./delete-revision-button";
import { versionEntries, type VersionEntry } from "./version-list";

const date = (iso: string) => {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });
};

export const isSlot = (label: string): label is RevisionId => label === "A" || label === "B";

/** Versión con la URL del IFC lista para el visor. */
export type Version = VersionEntry & { ifc: string | null };

/** Versiones guardadas del equipo activo, de la más reciente a la primera. */
export function useVersions() {
  const active = useEquipment((s) => s.active);
  const setActive = useEquipment((s) => s.setActive);
  const setRevision = useUi((s) => s.setRevision);
  const rows = useEquipmentRows();
  const row = apiEnabled
    ? rows.data?.find((item) => item.project_id === active?.project_id && item.equipment_id === active?.equipment_id)
    : rows.data?.find((item) => item.tag === DEMO.tag);
  const labels = row?.revisions ?? [];
  const records = useQueries({
    queries: labels.map((label) => {
      const identity = row?.revision_meta?.[label]?.identity ?? `${row?.project_id ?? ""}:${row?.equipment_id ?? ""}:${label}`;
      return {
        queryKey: ["version", apiEnabled ? identity : label],
        queryFn: () => (apiEnabled ? apiRevisionById(identity) : getRevision(isSlot(label) ? label : "B")),
        enabled: apiEnabled || isSlot(label),
      };
    }),
  });
  const byLabel = Object.fromEntries(labels.map((label, i) => [label, records[i]?.data]));
  const versions: Version[] = row
    ? versionEntries(row, byLabel).map((entry) => ({
      ...entry,
      ifc: apiEnabled ? (entry.ifcUrl ? apiURL(entry.ifcUrl) : null) : isSlot(entry.label) ? DEMO.revisions[entry.label].ifc : null,
    }))
    : [];
  const loading = rows.isPending || records.some((query) => query.isPending && query.fetchStatus !== "idle");

  /** Deja la versión como revisión activa del equipo (Revisión y el formulario la usan de base). */
  function activate(label: string) {
    if (!apiEnabled) {
      if (isSlot(label)) setRevision(label);
      return;
    }
    const record = byLabel[label];
    if (!record || !rows.data) return;
    const target = modelTarget(record, rows.data);
    setActive(target.equipment);
    setRevision(target.slot);
  }

  return { versions, loading, activate };
}

/*
  Historial de versiones del equipo activo: cada revisión guardada (lectura de un plano o cambio
  de diseño confirmado), con su origen, su estado de aprobación y su IFC. Complementa al
  historial de cambios, que lista las acciones dentro de cada versión.
*/
export function VersionHistory({
  versions,
  loading,
  openLabel,
  comparing,
  onCompare,
  onActivate,
}: {
  versions: Version[];
  loading: boolean;
  openLabel?: string;
  /** Versiones que muestra ahora el comparador. */
  comparing?: { from: string; to: string } | null;
  onCompare(from: Version, to: Version): void;
  onActivate(label: string): void;
}) {
  const router = useRouter();
  return (
    <Panel data-testid="version-history">
      <PanelHeader
        title="Versiones"
        description="Cada versión guardada del equipo y si ya está aprobada."
        actions={versions.length ? <Pill>{versions.length} {versions.length === 1 ? "versión" : "versiones"}</Pill> : null}
      />
      <ol aria-label="Versiones del equipo" className="max-h-[560px] space-y-2 overflow-y-auto px-4 pb-4">
        {loading && !versions.length ? (
          [0, 1].map((i) => <li key={i}><Skeleton className="h-20 w-full" /></li>)
        ) : versions.length ? (
          versions.map((entry, index) => {
            const current = entry.label === openLabel;
            const previous = versions[index + 1];
            const shown = comparing?.to === entry.label && comparing.from === previous?.label;
            return (
              <li
                key={entry.label}
                aria-current={current ? "true" : undefined}
                className={cn("rounded-[var(--radius-control)] border px-3 py-2.5", shown ? "border-accent bg-accent/10" : "border-border")}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Icon icon={Layers} className={shown ? "text-accent" : "text-muted"} />
                  <span className="text-sm font-medium text-strong">Rev {entry.label}</span>
                  {index === 0 ? <Badge tone="accent">Última</Badge> : null}
                  {entry.approval ? <Badge tone="approved">Aprobada</Badge> : <Badge tone="warning">Borrador</Badge>}
                  {entry.dataset === "synthetic" ? <Badge>Sintética</Badge> : null}
                </div>
                <p className="mt-1 text-[13px]">{entry.origin}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {entry.approval ? (
                    <>
                      <Icon icon={CheckCircle2} size={12} className="mr-1 inline text-approved" />
                      Aprobada por <AuthorName name={entry.approval.reviewer} size={14} /> · {date(entry.approval.at)}
                    </>
                  ) : "Pendiente de revisar y aprobar."}
                </p>
                {apiEnabled && entry.documents.length ? (
                  <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                    {entry.documents.map((document) => (
                      <li key={document.id}>
                        <a
                          className="inline-flex items-center gap-1 text-xs text-accent-text hover:underline"
                          href={apiURL(`/revisions/${encodeURIComponent(entry.identity)}/documents/${encodeURIComponent(document.id)}`)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Icon icon={FileText} size={12} /> {document.filename}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {previous ? (
                    <Button variant={shown ? "primary" : "secondary"} size="sm" aria-pressed={shown} onClick={() => onCompare(previous, entry)}>
                      <Icon icon={GitCompareArrows} size={13} /> Comparar con Rev {previous.label}
                    </Button>
                  ) : null}
                  <Button variant="ghost" size="sm" onClick={() => { onActivate(entry.label); router.push(modelHref("revision")); }}>
                    Abrir en Revisión
                  </Button>
                  <DeleteRevisionButton identity={entry.identity} label={entry.label} version={entry.saves} approved={Boolean(entry.approval)} />
                  {entry.ifc ? (
                    <a href={entry.ifc} download className="ml-auto inline-flex items-center gap-1 text-xs text-accent-text underline underline-offset-2">
                      <Icon icon={Download} size={13} /> Descargar IFC
                    </a>
                  ) : null}
                </div>
              </li>
            );
          })
        ) : (
          <li>
            <EmptyState icon={Layers} title="Sin versiones guardadas">
              Las revisiones leídas de los planos y los cambios de diseño confirmados aparecerán aquí.
            </EmptyState>
          </li>
        )}
      </ol>
    </Panel>
  );
}

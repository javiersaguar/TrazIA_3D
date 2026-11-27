"use client";

import { useQueries } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, FileText, GitBranch, History, Pencil, Undo2, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { Button, EmptyState, Icon, Panel, PanelHeader, Pill, Skeleton } from "@/components/ui/primitives";
import { AuthorName } from "@/components/shell/author";
import { cn } from "@/lib/cn";
import { apiAudit, apiDiffBetween, apiProposals, revisionIfcUrl, type AuditAction, type ProposalSummary } from "@/lib/api/client";
import { apiEnabled } from "@/lib/api/config";
import type { DiffReport, FieldChange } from "@/lib/mock/diff-types";
import { flattenRevision } from "@/lib/mock/fields";
import { useChanges, useIfcUrl } from "@/lib/queries";
import type { Revision } from "@/lib/types/revision";
import { revisionIdentity, revisionLabel, useEquipment } from "@/stores/equipment";
import { downloadHistory, type HistoryExportEntry } from "./history-xlsx";
import { fieldLabel } from "@/lib/field-labels";

/*
  Historial de cambios del equipo activo, debajo de los visores del modelo. Cada entrada dice
  quién hizo el cambio y, al pulsarla, el visor anima ese cambio sobre el IFC:
  - el cambio entre revisiones del plano (lo lee TrazIA del GA nuevo);
  - las correcciones y aprobaciones guardadas en la auditoría de cada revisión;
  - las propuestas de diseño aplicadas, que crean una revisión nueva.
*/

type Kind = "plano" | "edicion" | "aprobacion" | "deshacer" | "propuesta";

export type ChangeEntry = HistoryExportEntry & {
  kind: Kind;
  /** Revisión de partida; las correcciones ocurren dentro de una misma revisión. */
  fromRevision?: string;
};

const KIND: Record<Kind, { label: string; icon: LucideIcon }> = {
  plano: { label: "Revisión del plano", icon: FileText },
  edicion: { label: "Corrección", icon: Pencil },
  aprobacion: { label: "Aprobación", icon: CheckCircle2 },
  deshacer: { label: "Deshecho", icon: Undo2 },
  propuesta: { label: "Cambio de diseño", icon: GitBranch },
};

const when = (seconds?: number) =>
  seconds ? new Date(seconds * 1000).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" }) : undefined;

const show = (v: { value: number | string; unit: string } | null) =>
  v ? `${typeof v.value === "number" ? v.value.toLocaleString("es-ES") : v.value}${v.unit && v.unit !== "1" ? ` ${v.unit}` : ""}` : "—";

function parse(json: string): Revision | null {
  try {
    return JSON.parse(json) as Revision;
  } catch {
    return null;
  }
}

/** El campo que tocó una acción de auditoría, antes y después, como un cambio del diff. */
export function auditChange(action: Pick<AuditAction, "path" | "before_json" | "after_json">): FieldChange | null {
  const before = parse(action.before_json), after = parse(action.after_json);
  if (!before || !after) return null;
  const find = (rev: Revision) => {
    try {
      return flattenRevision(rev).find((f) => f.path === action.path);
    } catch {
      return undefined;
    }
  };
  const a = find(before), b = find(after);
  if (!a && !b) return null;
  return {
    path: action.path,
    operation: !a ? "added" : !b ? "removed" : "modified",
    before: a ? { value: a.value, unit: a.unit } : null,
    after: b ? { value: b.value, unit: b.unit } : null,
    affects_geometry: true,
    impact: "",
    before_source: null,
    after_source: null,
  };
}

/** Campos que una aprobación automática pasó a aceptados, como cambios sin variación de valor. */
export function autoAccepted(action: Pick<AuditAction, "before_json" | "after_json">): FieldChange[] {
  const before = parse(action.before_json), after = parse(action.after_json);
  if (!before || !after) return [];
  try {
    const previous = new Map(flattenRevision(before).map((f) => [f.path, f]));
    return flattenRevision(after)
      .filter((f) => f.status === "accepted" && previous.get(f.path)?.status === "candidate")
      .map((f) => ({
        path: f.path,
        operation: "modified" as const,
        before: { value: f.value, unit: f.unit },
        after: { value: f.value, unit: f.unit },
        affects_geometry: false,
        impact: "Aprobado automáticamente",
        before_source: null,
        after_source: null,
      }));
  } catch {
    return [];
  }
}

function report(base: Pick<DiffReport, "project_id" | "equipment_id">, revision: string, changes: FieldChange[]): DiffReport {
  return {
    ...base,
    from_revision: revision,
    to_revision: revision,
    summary: { changes: changes.length, geometry_changes: changes.length, provenance_changes: 0, document_changes: 0 },
    changes,
    provenance_changes: [],
    document_changes: [],
    before_sha256: "",
    after_sha256: "",
  };
}

function auditEntry(action: AuditAction, identity: string, label: string): ChangeEntry | null {
  const url = revisionIfcUrl(identity);
  const base = { key: `audit:${identity}:${action.id}`, author: action.actor || "Sin autor", at: action.created_at, revision: label, fromUrl: url, toUrl: url };
  if (action.path === "$design" || action.path === "$reversion") return null; // Ya sale como propuesta.
  if (action.path === "$auto_accept") {
    const changes = autoAccepted(action);
    const [project_id = "", equipment_id = ""] = identity.split(":");
    return {
      ...base,
      kind: "aprobacion",
      title: `${changes.length} ${changes.length === 1 ? "campo aprobado" : "campos aprobados"} automáticamente`,
      detail: "Confianza alta y valor encontrado en el original. Se pueden revocar en Revisión.",
      ...(changes.length ? { changes: report({ project_id, equipment_id }, label, changes) } : {}),
    };
  }
  if (action.path === "$approval") {
    return { ...base, kind: "aprobacion", title: `Aprobada la revisión ${label}`, detail: "El modelo queda listo para emitir." };
  }
  const change = auditChange(action);
  const [project_id = "", equipment_id = ""] = identity.split(":");
  const ids = { project_id, equipment_id };
  const find = (json: string) => {
    const rev = parse(json);
    try {
      return rev ? flattenRevision(rev).find((f) => f.path === action.path) : undefined;
    } catch {
      return undefined;
    }
  };
  const prev = find(action.before_json), next = find(action.after_json);
  const name = next?.label ?? prev?.label ?? fieldLabel(action.path);
  const sameValue = change ? show(change.before) === show(change.after) : false;
  // Mismo valor y otro estado: es una decisión de revisión, no una corrección del dato.
  const decision = sameValue && prev && next && prev.status !== next.status
    ? next.status === "accepted" ? `Aceptado ${name}`
      : prev.status === "accepted" ? `Revocada la aprobación de ${name}`
        : next.status === "assumed" ? `${name} como supuesto` : `${name} pendiente de revisión`
    : undefined;
  return {
    ...base,
    kind: action.undo_of ? "deshacer" : decision && next?.status === "accepted" ? "aprobacion" : "edicion",
    title: action.undo_of ? `Deshecha la acción sobre ${name}` : decision ?? name,
    detail: change ? (sameValue ? `Valor ${show(change.after)}` : `${show(change.before)} → ${show(change.after)}`) : fieldLabel(action.path),
    ...(change ? { changes: report(ids, label, [change]) } : {}),
  };
}

function proposalEntry(p: ProposalSummary, label: string): ChangeEntry | null {
  if (p.status !== "applied" || !p.applied_revision_id) return null;
  return {
    key: `proposal:${p.id}`,
    kind: "propuesta",
    title: p.reason?.trim() || p.request_text?.trim() || `Revisión ${p.target_revision}`,
    detail: `Rev ${p.base.revision ?? label} → Rev ${p.target_revision}`,
    author: p.actor || "Sin autor",
    at: p.updated_at || p.created_at,
    revision: p.target_revision,
    fromRevision: p.base.revision ?? label,
    fromUrl: revisionIfcUrl(p.base.revision_id),
    toUrl: revisionIfcUrl(p.applied_revision_id),
    diff: { from: p.base.revision_id, to: p.applied_revision_id },
  };
}

function useHistory(): { entries: ChangeEntry[]; loading: boolean } {
  const equipment = useEquipment((s) => s.active);
  const { data: diff, isLoading } = useChanges();
  const ifcA = useIfcUrl("A"), ifcB = useIfcUrl("B");
  const revs = (["A", "B"] as const).filter((rev) => apiEnabled && equipment && (rev === "A" || equipment.revisions.length > 1));
  const ids = revs.map((rev) => ({ rev, identity: revisionIdentity(rev, equipment ?? undefined), label: equipment ? revisionLabel(rev, equipment) : rev }));
  const audits = useQueries({
    queries: ids.map(({ identity }) => ({ queryKey: ["audit", identity], queryFn: () => apiAudit(identity) })),
  });
  const proposals = useQueries({
    queries: ids.map(({ identity }) => ({ queryKey: ["change-proposals", identity], queryFn: () => apiProposals(identity) })),
  });

  const entries = (() => {
    const out: ChangeEntry[] = [];
    const hasPair = !apiEnabled || (equipment?.revisions.length ?? 0) > 1;
    if (diff && hasPair && ifcA && ifcB && diff.changes.length) {
      const from = apiEnabled && equipment ? revisionLabel("A", equipment) : "A";
      const to = apiEnabled && equipment ? revisionLabel("B", equipment) : "B";
      const geometry = diff.changes.filter((c) => c.affects_geometry).length;
      out.push({
        key: `plano:${from}:${to}`,
        kind: "plano",
        title: `Rev ${from} → Rev ${to} del plano GA`,
        detail: `${diff.changes.length} ${diff.changes.length === 1 ? "cambio leído" : "cambios leídos"}, ${geometry} con geometría`,
        author: "TrazIA · lectura automática del plano",
        revision: to,
        fromRevision: from,
        fromUrl: ifcA,
        toUrl: ifcB,
        changes: diff,
      });
    }
    ids.forEach(({ identity, label }, i) => {
      for (const action of audits[i]?.data?.actions ?? []) {
        const entry = auditEntry(action, identity, label);
        if (entry) out.push(entry);
      }
    });
    const seen = new Set<string>();
    ids.forEach(({ label }, i) => {
      for (const p of proposals[i]?.data?.proposals ?? []) {
        if (seen.has(p.id)) continue;
        seen.add(p.id);
        const entry = proposalEntry(p, label);
        if (entry) out.push(entry);
      }
    });
    // Lo más reciente arriba; el cambio del plano, que no tiene hora, al final como punto de partida.
    return out.sort((a, b) => (b.at ?? 0) - (a.at ?? 0));
  })();

  return { entries, loading: isLoading || audits.some((q) => q.isLoading) || proposals.some((q) => q.isLoading) };
}

/** Registro de acciones del equipo. Al pulsar una entrada, el comparador de debajo la anima en 3D. */
export function ChangeHistory({ activeKey, onSelect }: { activeKey?: string | null; onSelect(entry: ChangeEntry | null): void }) {
  const equipment = useEquipment((s) => s.active);
  const { entries, loading } = useHistory();
  const [exporting, setExporting] = useState(false);

  async function exportExcel() {
    if (!entries.length || exporting) return;
    setExporting(true);
    try {
      const full = await Promise.all(entries.map(async (entry) => {
        if (entry.changes || !entry.diff) return entry;
        try {
          return { ...entry, changes: await apiDiffBetween(entry.diff.from, entry.diff.to) };
        } catch (error) {
          return { ...entry, diffError: error instanceof Error ? error.message : "No se pudo leer el diff" };
        }
      }));
      downloadHistory(full, equipment?.tag ?? "equipo");
    } finally {
      setExporting(false);
    }
  }

  return (
    <Panel data-testid="change-history">
      <PanelHeader
        title="Cambios realizados"
        description="Quién cambió qué en este equipo. Pulsa uno para verlo en 3D."
        actions={
          <>
            {entries.length ? <Pill>{entries.length} {entries.length === 1 ? "cambio" : "cambios"}</Pill> : null}
            <Button variant="secondary" size="sm" disabled={!entries.length || loading || exporting} onClick={() => void exportExcel()}>
              <Icon icon={FileSpreadsheet} size={14} />
              {exporting ? "Exportando…" : "Exportar Excel"}
            </Button>
          </>
        }
      />
      <div className="px-4 pb-4">
        <ol className="max-h-[560px] space-y-1.5 overflow-y-auto pr-1" aria-label="Cambios del equipo">
          {loading && !entries.length ? (
            [0, 1, 2].map((i) => <li key={i}><Skeleton className="h-16 w-full" /></li>)
          ) : entries.length ? (
            entries.map((entry) => {
              const kind = KIND[entry.kind];
              const active = entry.key === activeKey;
              return (
                <li key={entry.key}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => onSelect(active ? null : entry)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-[var(--radius-control)] border px-3 py-2.5 text-left transition-colors active:scale-[0.99]",
                      active ? "border-accent bg-accent/10" : "border-border hover:bg-surface-sunken",
                    )}
                  >
                    <Icon icon={kind.icon} className={cn("mt-0.5 shrink-0", active ? "text-accent" : "text-muted")} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-strong">{entry.title}</span>
                      <span className="block truncate text-xs text-muted">{entry.detail}</span>
                      <span className="mt-1 block text-[11px] text-muted">
                        <AuthorName name={entry.author} size={14} />
                        {when(entry.at) ? ` · ${when(entry.at)}` : ""} · {kind.label} · Rev {entry.revision}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })
          ) : (
            <li>
              <EmptyState icon={History} title="Sin cambios todavía">
                Las correcciones, aprobaciones y cambios de diseño aparecerán aquí con su autor.
              </EmptyState>
            </li>
          )}
        </ol>
      </div>
    </Panel>
  );
}

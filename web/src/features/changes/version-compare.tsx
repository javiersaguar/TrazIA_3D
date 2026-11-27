"use client";

import { useQuery } from "@tanstack/react-query";
import { GitCompareArrows, Pause, Play } from "lucide-react";
import { useId, useMemo, useState, type ReactNode } from "react";
import { RevisionMorph } from "@/components/three";
import { Tip } from "@/components/ui/controls";
import { Badge, Button, EmptyState, Icon, Panel, PanelHeader, Pill, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { formatDelta, formatValue } from "@/lib/format";
import { apiDiffBetween } from "@/lib/api/client";
import type { DiffReport } from "@/lib/mock/diff-types";
import { groupChanges, type ChangeGroup } from "@/lib/mock/impact";
import { useSelection } from "@/stores/selection";
import type { Version } from "@/features/revisions/version-history";
import { parentElementId } from "@/features/viewer3d/semantic";

/** Lo que el comparador anima: dos IFC y los cambios de campos entre ellos. */
export type CompareTarget = {
  key: string;
  title: string;
  fromLabel: string;
  toLabel: string;
  fromUrl: string;
  toUrl: string;
  dataset: Version["dataset"];
  changes?: DiffReport;
  /** Identidades para pedir el diff a la API cuando no viene calculado. */
  diff?: { from: string; to: string };
};

const selectClass = "h-8 rounded-[var(--radius-control)] border border-border bg-surface px-2 text-[13px] text-text";

function fieldLine(group: ChangeGroup) {
  const field = group.fields[0];
  if (group.delta && field?.before && field.after) {
    return (
      <>
        <span className="font-semibold text-revision">{formatDelta(group.delta.value, group.delta.unit)}</span>
        <span className="text-muted"> · {formatValue(field.before.value, field.before.unit)} → {formatValue(field.after.value, field.after.unit)}</span>
      </>
    );
  }
  if (group.kind === "nuevo") return <span className="text-approved">Aparece en la versión nueva</span>;
  if (group.kind === "eliminado") return <span className="text-danger">Desaparece en la versión nueva</span>;
  return (
    <span className="text-muted">
      {group.fields.map((f) => `${f.before ? formatValue(f.before.value, f.before.unit) : "—"} → ${f.after ? formatValue(f.after.value, f.after.unit) : "—"}`).join(" · ")}
    </span>
  );
}

/*
  Comparador de versiones: el visor anima el paso de una versión a otra y deja las piezas
  modificadas con el color de revisión; el panel lateral lista los cambios y, al pulsar uno,
  la cámara va a esa pieza.
*/
export function VersionCompare({
  target,
  versions,
  onPick,
}: {
  target: CompareTarget | null;
  versions: Version[];
  onPick(from: Version, to: Version): void;
}) {
  const fromId = useId(), toId = useId();
  const [playing, setPlaying] = useState(true);
  const [split, setSplit] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const selectedId = useSelection((s) => s.selectedId);
  const setSelected = useSelection((s) => s.setSelected);
  const remote = useQuery({
    queryKey: ["diff", target?.diff?.from, target?.diff?.to],
    queryFn: () => apiDiffBetween(target!.diff!.from, target!.diff!.to),
    enabled: !!target && !target.changes && !!target.diff,
  });
  const changes = target?.changes ?? remote.data;
  const groups = useMemo(() => (changes ? groupChanges(changes.changes) : []), [changes]);
  const focused = playing && !split ? step : selectedId ? parentElementId(selectedId) : null;
  const pick = (from: string, to: string) => {
    const a = versions.find((v) => v.label === from), b = versions.find((v) => v.label === to);
    if (a && b) onPick(a, b);
  };
  const ordered = [...versions].reverse();

  return (
    <Panel data-testid="version-compare" className="overflow-hidden">
      <PanelHeader
        title="Comparar versiones"
        description={target
          ? "Las piezas que cambian quedan resaltadas al terminar la animación."
          : "Elige las dos versiones que quieres comparar."}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {ordered.length > 1 ? (
              <>
                <label htmlFor={fromId} className="text-xs text-muted">Desde</label>
                <select id={fromId} className={selectClass} value={target?.fromLabel ?? ""}
                  onChange={(e) => pick(e.target.value, target?.toLabel ?? ordered.at(-1)!.label)}>
                  {target && !versions.some((v) => v.label === target.fromLabel) ? <option value={target.fromLabel}>Rev {target.fromLabel}</option> : null}
                  {!target ? <option value="">—</option> : null}
                  {ordered.map((v) => <option key={v.label} value={v.label}>Rev {v.label}</option>)}
                </select>
                <label htmlFor={toId} className="text-xs text-muted">Hasta</label>
                <select id={toId} className={selectClass} value={target?.toLabel ?? ""}
                  onChange={(e) => pick(target?.fromLabel ?? ordered[0]!.label, e.target.value)}>
                  {target && !versions.some((v) => v.label === target.toLabel) ? <option value={target.toLabel}>Rev {target.toLabel}</option> : null}
                  {!target ? <option value="">—</option> : null}
                  {ordered.map((v) => <option key={v.label} value={v.label}>Rev {v.label}</option>)}
                </select>
              </>
            ) : null}
            {target ? (
              <>
                <Button variant="secondary" size="sm" onClick={() => { setPlaying(false); setSplit(!split); }}>
                  <Icon icon={GitCompareArrows} size={13} />{split ? "Ver animación" : "Ver lado a lado"}
                </Button>
                {!split ? (
                  <Tip content={playing ? "Pausar" : "Reproducir los cambios"}>
                    <Button variant="secondary" size="sm" disabled={!changes && !remote.isError} onClick={() => setPlaying((p) => !p)}
                      aria-label={playing ? "Pausar" : "Reproducir los cambios"}>
                      <Icon icon={playing ? Pause : Play} size={13} />{playing ? "Pausar" : "Reproducir"}
                    </Button>
                  </Tip>
                ) : null}
              </>
            ) : null}
          </div>
        }
      />
      <div className="grid gap-3 px-4 pb-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="h-[min(65vh,600px)] min-h-[360px] overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface-sunken" data-testid="version-compare-viewer">
          {!target ? (
            <div className="grid h-full place-items-center p-6 text-center text-sm text-muted">
              <EmptyState icon={GitCompareArrows} title="Nada que comparar todavía">
                Este equipo necesita al menos dos versiones guardadas para poder compararlas.
              </EmptyState>
            </div>
          ) : changes || remote.isError ? (
            <RevisionMorph
              key={target.key}
              fromUrl={target.fromUrl}
              toUrl={target.toUrl}
              fromLabel={`Rev ${target.fromLabel}`}
              toLabel={`Rev ${target.toLabel}`}
              realData={target.dataset !== "synthetic"}
              highlightChanges
              changes={changes}
              playing={playing && !split}
              split={split}
              onPlayingChange={setPlaying}
              onStep={(id) => setStep(id)}
              onComplete={() => setStep(null)}
            />
          ) : (
            <Skeleton className="h-full w-full" />
          )}
        </div>

        <aside aria-label="Cambios entre versiones" className="flex max-h-[min(65vh,600px)] min-h-0 flex-col rounded-[var(--radius-control)] border border-border">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
            <p className="text-sm font-medium text-strong">
              {target ? `Rev ${target.fromLabel} → Rev ${target.toLabel}` : "Cambios"}
            </p>
            {changes ? <Pill>{groups.length} {groups.length === 1 ? "cambio" : "cambios"}</Pill> : null}
          </div>
          <ol className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2" data-testid="version-compare-changes">
            {!target ? (
              <li className="p-3 text-[13px] text-muted">El detalle de cada cambio aparecerá aquí.</li>
            ) : remote.isError && !changes ? (
              <li role="alert" className="p-3 text-[13px] text-muted">No se han podido leer los cambios de campos entre estas versiones.</li>
            ) : !changes ? (
              [0, 1, 2].map((i) => <li key={i}><Skeleton className="h-16 w-full" /></li>)
            ) : groups.length ? (
              groups.map((group) => {
                const active = focused === group.elementId;
                return (
                  <li key={group.id}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => { setPlaying(false); setSelected(group.elementId, group.fields[0]?.path ?? null); }}
                      className={cn(
                        "w-full rounded-[var(--radius-control)] border px-3 py-2 text-left text-[13px] transition-colors",
                        active ? "border-revision/60 bg-revision-soft" : "border-border hover:bg-surface-sunken",
                      )}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium text-text">{group.title}</span>
                        {group.severity !== "baja" ? (
                          <Badge tone={group.severity === "alta" ? "danger" : "warning"}>Importancia {group.severity}</Badge>
                        ) : null}
                      </span>
                      <span className="mt-0.5 block">{fieldLine(group)}</span>
                      {group.disciplines.length ? (
                        <span className="mt-1 block text-[11px] text-muted">
                          Afecta a {group.disciplines.map((d) => <span key={d.code} title={d.reason} className="text-text">{d.code}</span>).reduce<ReactNode[]>((all, item, i) => (i ? [...all, ", ", item] : [item]), [])}
                        </span>
                      ) : null}
                    </button>
                  </li>
                );
              })
            ) : (
              <li className="p-3 text-[13px] text-muted">Sin diferencias de campos entre estas versiones.</li>
            )}
          </ol>
          <p className="border-t border-border px-3 py-2 text-[11px] text-muted">
            <span className="mr-1 inline-block size-2 rounded-full bg-revision align-middle" aria-hidden /> Pieza que cambia ·
            pulsa un cambio para verlo de cerca.
          </p>
        </aside>
      </div>
    </Panel>
  );
}

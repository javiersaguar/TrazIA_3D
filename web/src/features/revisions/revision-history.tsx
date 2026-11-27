"use client";

import dynamic from "next/dynamic";
import { useId, useState, type ReactNode } from "react";
import { Button, Panel, PanelHeader } from "@/components/ui/primitives";
import { apiEnabled } from "@/lib/api/config";
import { useEquipment } from "@/lib/queries";
import { projectModels, type ProjectModel } from "./project-models";
import { revisionsFor } from "./revision-states";

const ProjectComparison = dynamic(() => import("./project-comparison").then((module) => module.ProjectComparison), {
  ssr: false,
  loading: () => <p role="status" className="px-5">Preparando la comparación…</p>,
});

const selectClass = "mt-1 block h-10 w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm text-text";

export function RevisionHistory({
  projectId,
  current,
  realOnly = false,
  documents = [],
  children,
}: {
  projectId: string;
  current: ProjectModel;
  realOnly?: boolean;
  documents?: { filename: string; href: string }[];
  children?: ReactNode;
}) {
  const catalogue = useEquipment();
  const models = projectModels(catalogue.data ?? [], projectId, current, realOnly);
  const revisions = revisionsFor(projectId || current.tag);
  const [from, setFrom] = useState(0);
  const [to, setTo] = useState(revisions.length - 1);
  const [active, setActive] = useState<{ from: number; to: number; attempt: number } | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const fromId = useId();
  const toId = useId();

  return (
    <Panel data-testid="revision-history">
      <PanelHeader
        title="Historial de revisiones"
        description={`Cuatro estados de simulación${projectId ? ` del proyecto ${projectId}` : ""}, con autoría ficticia del equipo.`}
      />
      {documents.length ? (
        <div className="space-y-1 px-5 pb-5">
          <p className="text-xs text-muted">Documentos de la versión abierta</p>
          <ul className="flex flex-wrap gap-x-5 gap-y-2">
            {documents.map((document) => (
              <li key={document.href}>
                <a className="text-sm text-accent-text hover:underline" href={document.href} target="_blank" rel="noreferrer">{document.filename}</a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <ol aria-label="Revisiones simuladas" className="space-y-2 px-5 pb-5">
        {revisions.slice(1).map((revision) => (
          <li key={revision.index} className="rounded-[var(--radius-control)] border border-border px-3 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="text-sm font-medium text-strong">{revision.label} · {revision.title}</p>
              <p className="text-xs text-muted">Autor simulado · {revision.author}</p>
            </div>
            <p className="mt-1 text-[13px]">{revision.summary}</p>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-end gap-3 px-5 pb-5">
        <label className="min-w-40 text-xs text-muted" htmlFor={fromId}>
          Estado A
          <select id={fromId} className={selectClass} value={from} onChange={(event) => setFrom(Number(event.target.value))}>
            {revisions.map((revision) => <option key={revision.index} value={revision.index}>{revision.label} · {revision.title}</option>)}
          </select>
        </label>
        <label className="min-w-40 text-xs text-muted" htmlFor={toId}>
          Estado B
          <select id={toId} className={selectClass} value={to} onChange={(event) => setTo(Number(event.target.value))}>
            {revisions.map((revision) => <option key={revision.index} value={revision.index}>{revision.label} · {revision.title}</option>)}
          </select>
        </label>
        <Button
          variant="primary"
          disabled={from === to || (apiEnabled && catalogue.isPending)}
          onClick={() => setActive((previous) => ({ from, to, attempt: (previous?.attempt ?? 0) + 1 }))}
        >
          Comparar estados del proyecto
        </Button>
        {from === to ? <p className="self-end text-xs text-muted">Elige dos estados distintos.</p> : null}
      </div>
      {catalogue.isError && apiEnabled ? (
        <p role="status" className="px-5 pb-4 text-sm text-warning">El catálogo del proyecto no está disponible. Puedes comparar el equipo abierto.</p>
      ) : null}
      {active ? (
        <ProjectComparison
          key={active.attempt}
          models={models}
          initialId={current.id}
          from={revisions[active.from]!}
          to={revisions[active.to]!}
        />
      ) : null}
      {children ? (
        <details onToggle={event => setShowRegister(event.currentTarget.open)} className="group border-t border-border px-5 py-3">
          <summary className="cursor-pointer text-sm font-medium text-strong">Registro del equipo</summary>
          {showRegister ? <div className="pt-3">{children}</div> : null}
        </details>
      ) : null}
    </Panel>
  );
}

"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { RevisionMorph } from "@/components/three";
import { Button } from "@/components/ui/primitives";
import { useIfcModel, usePreparedModel } from "@/features/viewer3d/model-resource";
import type { ProjectModel } from "./project-models";
import type { RevisionState } from "./revision-states";
import { applyRevision, changesBetween, releaseSynthetic } from "./synthetic-revisions";
const colorKey = "rounded-md border border-border bg-surface-raised px-2 py-1";
const viewerHeight = "h-[min(65vh,600px)] min-h-[360px]";

export function ProjectComparison({ models, initialId, from, to }: {
  models: ProjectModel[];
  initialId: string;
  from: RevisionState;
  to: RevisionState;
}) {
  const [modelId, setModelId] = useState(initialId);
  const model = models.find((item) => item.id === modelId) ?? models[0]!;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({ block: "start" });
  }, []);

  return (
    <section className="space-y-3 border-t border-border px-5 py-5" aria-label="Comparación de estados" data-testid="project-comparison">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 ref={heading} tabIndex={-1} className="scroll-mt-20 font-semibold text-strong">Comparación de estados</h3>
          <p className="text-sm text-muted">
            {models.length} {models.length === 1 ? "equipo" : "equipos"} · IFC de partida de {model.tag}, versión {model.version}
          </p>
        </div>
        {models.length > 1 ? (
          <label className="text-xs text-muted">
            Equipo del proyecto
            <select className="ml-2 h-10 rounded-md border border-border bg-surface px-2 text-sm text-text"
              value={model.id} onChange={(event) => setModelId(event.target.value)}>
              {models.map((item) => <option key={item.id} value={item.id}>{item.tag}</option>)}
            </select>
          </label>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-muted">
        <span className={colorKey}>A · {from.label} · {from.title}</span>
        <span className={colorKey}>B · {to.label} · {to.title}</span>
      </div>
      <EquipmentComparison key={model.ifcUrl} model={model} from={from} to={to} />
    </section>
  );
}

function EquipmentComparison({ model, from, to }: { model: ProjectModel; from: RevisionState; to: RevisionState }) {
  const { model: ifc, error } = useIfcModel(model.ifcUrl);
  const products = usePreparedModel(ifc);
  const [stage, setStage] = useState(0);
  const reduced = useReducedMotion();
  const span = Math.abs(to.index - from.index);
  const split = stage >= span || !!reduced;
  const direction = Math.sign(to.index - from.index);
  const models = useMemo(() => Array.from({ length: span + 1 }, (_, index) =>
    applyRevision(products, from.index + index * direction, model.tag, model.horizontal)),
    [products, span, from.index, direction, model.tag, model.horizontal]);
  useEffect(() => () => models.forEach(releaseSynthetic), [models]);
  const before = models[split ? 0 : stage]!;
  const after = models[split ? span : stage + 1]!;
  const stageFrom = split ? from.index : from.index + stage * direction;
  const stageTo = split ? to.index : stageFrom + direction;
  const changes = useMemo(() => changesBetween(model.tag, from.index, to.index, products, model.horizontal),
    [model.tag, from.index, to.index, products, model.horizontal]);
  const animatedChanges = useMemo(() => changesBetween(model.tag, stageFrom, stageTo, products, model.horizontal),
    [model.tag, stageFrom, stageTo, products, model.horizontal]);

  if (error) return <p role="alert" className="text-sm text-danger">No se pudo abrir el IFC de {model.tag} para comparar.</p>;
  if (!ifc) return (
    <div className={`grid place-items-center ${viewerHeight}`}>
      <p role="status" className="text-sm text-muted">Cargando el IFC de {model.tag}…</p>
    </div>
  );
  if (!products.length) return <p role="status" className="text-sm text-muted">El IFC de {model.tag} no tiene geometría visible.</p>;

  return (
    <div className="space-y-2" data-testid="comparison-visualization" data-stage={split ? "split" : "animation"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status" className="text-xs text-muted">{split ? "Comparación lado a lado · Cámaras sincronizadas"
          : `Animación de las piezas modificadas · Paso ${stage + 1} de ${span}`}</p>
        {reduced ? null : (
          <Button size="sm" variant="secondary" onClick={() => setStage(split ? 0 : span)}>
            {split ? "Repetir animación" : "Ver lado a lado"}
          </Button>
        )}
      </div>
      <div className={viewerHeight}>
        <RevisionMorph
          key={split ? "split" : stage}
          fromUrl={model.ifcUrl}
          toUrl={model.ifcUrl}
          changes={animatedChanges}
          beforeProducts={before}
          afterProducts={after}
          fromLabel={`A · ${from.label}`}
          toLabel={`B · ${to.label}`}
          autoPlay={!split}
          split={split}
          onComplete={() => setStage((current) => current === stage ? stage + 1 : current)}
        />
      </div>
      <ul aria-label="Cambios del equipo entre los estados" className="flex flex-wrap gap-2 text-xs text-muted">
        {changes.changes.map((change) => (
          <li key={change.path} className={colorKey}>
            {change.impact} · {change.operation === "added" ? "Añadido" : change.operation === "removed" ? "Retirado"
              : `${Number(change.after?.value) - Number(change.before?.value) > 0 ? "+" : ""}${Number(change.after?.value) - Number(change.before?.value)} mm`}
          </li>
        ))}
      </ul>
    </div>
  );
}

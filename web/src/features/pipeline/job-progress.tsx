"use client";

import Link from "next/link";
import { modelHref } from "@/features/workspace/model-links";
import { useEffect } from "react";
import { Panel } from "@/components/ui/primitives";
import { apiEnabled } from "@/lib/api/config";
import { fieldLabel } from "@/lib/field-labels";
import { usePipeline } from "@/stores/pipeline";
import { splitPreliminary } from "./preliminary";

const steps = ["Recibir los planos", "Leer los datos", "Preparar el diseño", "Generar y comprobar el IFC"];
const stepForStage: Record<string, number> = { ingest: 0, classify: 1, extract: 1, reconcile: 2, family: 2, ifc: 3, validate: 3 };
export const primaryAction = "inline-flex min-h-12 items-center rounded-[var(--radius-control)] bg-accent px-5 font-semibold text-accent-contrast hover:underline";

export function JobProgress({ initialJobId }: { initialJobId?: string }) {
  const { error, events, follow, inputFiles, jobId, jobStatus, resultId, running, warnings } = usePipeline();

  useEffect(() => {
    if (apiEnabled && initialJobId && initialJobId !== jobId) follow(initialJobId);
  }, [follow, initialJobId, jobId]);

  const loading = Boolean(initialJobId && initialJobId !== jobId);
  const done = jobStatus === "done" && Boolean(resultId);
  const step = Math.max(0, ...events.filter(event => event.status !== "omitido").map(event => stepForStage[event.stage] ?? 0));
  const percent = done ? 100 : step * 25;
  const { preliminary, others } = splitPreliminary(warnings);
  const status = done ? (preliminary.length ? "Borrador listo · con valores preliminares" : "Borrador listo")
    : jobStatus === "queued" ? "En espera" : steps[step];

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="text-3xl font-semibold text-strong sm:text-4xl">Proceso</h1>
      <Panel className="space-y-5 p-4 sm:p-6">
        {!apiEnabled ? <p role="alert">Conecta la API local para ver el progreso.</p>
          : loading ? <p role="status">Abriendo el proceso…</p>
          : !jobId ? <>
            <p>Sube un PDF para comenzar.</p>
            <Link href="/documentos" className={primaryAction}>Subir planos</Link>
          </> : <>
            <div className="space-y-2" role="status">
              <div className="flex flex-wrap justify-between gap-2 font-semibold text-strong">
                <span>{error && !running ? "Proceso interrumpido" : status}</span>
                <span>{percent} %</span>
              </div>
              <progress aria-label="Progreso del trabajo" value={percent} max={100} className="block h-3 w-full accent-accent" />
            </div>
            <ol className="space-y-3">
              {steps.map((label, index) => {
                const completed = done || index < step;
                return <li key={label} aria-current={!done && index === step ? "step" : undefined} className="flex flex-wrap items-center justify-between gap-x-3 border-b border-border pb-2">
                  <span>{label}</span>
                  <span className={completed ? "text-live" : "text-muted"}>{completed ? "Completado" : index !== step || jobStatus === "queued" ? "Pendiente" : running ? "En curso" : "Interrumpido"}</span>
                </li>;
              })}
            </ol>
            {inputFiles.length ? <div>
              <h2 className="font-semibold text-strong">Archivos subidos</h2>
              <ul className="list-disc pl-6">{inputFiles.map((file, index) => <li className="break-all" key={`${file}-${index}`}>{file}</li>)}</ul>
            </div> : null}
            {error ? <p role="alert" className="text-danger">{running ? "Se interrumpió la conexión. El proceso intentará recuperarla." : `No se pudo terminar el proceso. Revisa los archivos y vuelve a subirlos. ${error}`}</p> : null}
            {preliminary.length ? <section aria-labelledby="preliminares" className="space-y-2 rounded-[var(--radius-card)] border border-warning-border bg-warning-bg p-4 text-warning">
              <h2 id="preliminares" className="font-semibold">Faltan datos en el plano</h2>
              <p>Se ha generado el modelo DRAFT con valores preliminares, marcados como supuestos y con confianza baja. No se podrá aprobar hasta que los completes.</p>
              <ul className="list-disc space-y-1 pl-6">{preliminary.map(path => <li key={path}>{fieldLabel(path)} <code className="text-xs opacity-80">{path}</code> · valor preliminar</li>)}</ul>
              {done && resultId ? <Link href={modelHref("revision", resultId)} className="inline-block font-semibold underline">Revisar y completar los valores</Link> : null}
            </section> : null}
            {others.length ? <div className="space-y-2">
              <h2 className="font-semibold text-strong">Datos por comprobar</h2>
              <ul className="list-disc space-y-1 pl-6">{others.map(warning => <li key={warning}>{warning}</li>)}</ul>
            </div> : null}
            {done && resultId ? <Link href={modelHref("revision", resultId)} className={primaryAction}>Ver diseño 3D</Link>
              : error && !running ? <Link href="/documentos" className={primaryAction}>Volver a subir planos</Link> : null}
          </>}
      </Panel>
    </div>
  );
}

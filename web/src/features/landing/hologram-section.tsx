"use client";

import { useInView, useScroll } from "motion/react";
import dynamic from "next/dynamic";
import { useRef } from "react";

import { realIfcUrl, useRealModels } from "./real-models";
import { ScrollPhases, useReducedPreference, type ScrollPhase } from "./scroll-phases";

/*
  Sección fijada mientras se hace scroll: el avance del scroll es el avance de la transformación
  holograma → modelo real (componente del Agente 2, ilustrativo).
*/

const HologramToReal = dynamic(() => import("@/features/hologram").then((m) => m.HologramToReal), {
  ssr: false,
  loading: () => null,
});

const PHASES: ScrollPhase[] = [
  {
    at: 0,
    title: "Lo que se ha leído",
    text: "Este holograma ilustra la fase de lectura. El equipo de esta sección es paramétrico y no procede de un plano real.",
  },
  {
    at: 0.38,
    title: "Lo que tiene evidencia",
    text: "El barrido explica el paso de borrador a modelo. La evidencia real de cada campo se consulta en Revisión.",
  },
  {
    at: 0.72,
    title: "Lo que se revisa",
    text: "El IFC y sus fuentes se revisan antes de aprobar una exportación. Puedes explorarlos en Modelo 3D.",
  },
];

const REAL_PHASES: ScrollPhase[] = [
  { at: 0, title: "Lo que se ha leído", text: "El holograma es la geometría leída de un plano del reto, antes de comprobar cada dato." },
  { at: 0.38, title: "Lo que tiene evidencia", text: "Cada cota del modelo apunta a la región del plano de la que sale. Se consulta en Revisión." },
  { at: 0.72, title: "Lo que se revisa", text: "Este IFC es un borrador hasta que una persona lo revisa y lo aprueba con la huella de sus datos." },
];

export function HologramSection({ enabled = true, real = false }: { enabled?: boolean; real?: boolean }) {
  const models = useRealModels(real);
  const rows = (models.data ?? []).filter(row => row.revision_meta?.[row.revisions.at(-1) ?? ""]?.dataset === "real");
  const model = rows.find((r) => r.kind === "vertical_vessel") ?? rows[0];
  const ifcUrl = real && model ? realIfcUrl(model) : null;
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedPreference();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const near = useInView(ref, { margin: "0px", amount: 0.05, once: true });

  return (
    <section ref={ref} aria-labelledby="holograma-titulo" className="relative h-[240vh]">
      <div className="sticky top-0 flex min-h-dvh items-center py-16">
        <div className="mx-auto grid w-full max-w-[1240px] items-center gap-10 px-5 md:px-8 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-14">
          <div>
            <h2 id="holograma-titulo" className="landing-display text-[clamp(32px,4.2vw,56px)] leading-[1] text-strong">
              Del holograma al modelo
            </h2>
            <ScrollPhases phases={ifcUrl ? REAL_PHASES : PHASES} progress={scrollYProgress} reduced={reduced} />
          </div>

          <div className="relative h-[min(62vh,560px)] overflow-hidden rounded-[16px] border border-border bg-surface-sunken">
            {/* El aviso «Ilustrativo» y el avance ya los pinta HologramToReal (arriba y abajo) */}
            {enabled && near ? (
              ifcUrl ? (
                <HologramToReal key={ifcUrl} pixelBudget={650_000} source="ifc" ifcUrl={ifcUrl} layout="side" progressValue={scrollYProgress} controls={false} callouts className="h-full w-full" />
              ) : (
                <HologramToReal pixelBudget={650_000} source="procedural" layout="side" progressValue={scrollYProgress} controls={false} callouts className="h-full w-full" />
              )
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

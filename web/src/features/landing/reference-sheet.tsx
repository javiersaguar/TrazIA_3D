"use client";

import { useInView } from "motion/react";
import dynamic from "next/dynamic";
import { useRef } from "react";

import { LANDING_REFERENCE, type ReferenceModel } from "./landing-reference";

export type { ReferenceModel };
const ReferenceScene = dynamic(() => import("./reference-scene").then(mod => mod.ReferenceScene), {
  ssr: false,
  loading: () => <p className="self-center justify-self-center text-sm text-muted" role="status">Preparando la vista 3D…</p>,
});

export function ReferenceSheet({ play, model = LANDING_REFERENCE }: { play: boolean; model?: ReferenceModel }) {
  const sheet = useRef<HTMLElement>(null);
  const visible = useInView(sheet, { once: true, margin: "0px 0px 120px 0px" });
  return (
    <figure ref={sheet} id="del-plano" aria-labelledby="reference-capt" data-testid="landing-reference"
      className="landing-paper grid h-[clamp(300px,72dvh,680px)] scroll-mt-20 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-[16px] border border-border bg-surface-sunken/70 shadow-[var(--shadow-pop)]">
      <figcaption id="reference-capt" className="flex flex-wrap items-end justify-between gap-x-3 gap-y-1 border-b border-border px-4 py-3 sm:px-5">
        <span className="font-mono text-[15px] font-semibold tracking-wide text-strong">{model.tag}</span>
        <span className="font-mono text-[11px] text-muted">{model.real ? "IFC de referencia · Técnicas Reunidas" : "IFC de demostración · datos sintéticos"}</span>
      </figcaption>
      {play && visible ? <ReferenceScene key={model.url} model={model} /> : <div className="row-span-2" />}
    </figure>
  );
}

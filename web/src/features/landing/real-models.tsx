"use client";

import { useQuery } from "@tanstack/react-query";
import { useInView } from "motion/react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { toActive } from "@/components/shell/equipment-picker";
import { IfcViewer } from "@/components/three";
import { API_BASE, apiURL } from "@/lib/api/config";
import type { EquipmentRow } from "@/lib/mock/api";
import type { DiffReport } from "@/lib/mock/diff-types";
import { elementForField, elementLabel } from "@/features/viewer3d/semantic";
import { useEquipment } from "@/stores/equipment";
import { useUi } from "@/stores/ui";

const FAMILY: Record<string, string> = {
  vertical_vessel: "Recipiente vertical",
  horizontal_vessel: "Recipiente horizontal",
  column: "Columna",
  tank: "Tanque",
};

/** Equipos del dataset del reto con modelo. Solo se pide con sesión iniciada: la API lo exige. */
export function useRealModels(enabled: boolean) {
  return useQuery({
    queryKey: ["landing-modelos"],
    enabled,
    queryFn: async ({ signal }) => {
      const response = await fetch(apiURL("/equipment"), { signal });
      if (!response.ok) throw new Error("No se pudieron leer los modelos del reto");
      return ((await response.json()) as EquipmentRow[]).filter((r) => r.project_id && r.equipment_id && r.ifcUrl && !r.illustrative);
    },
  });
}

export const realIfcUrl = (row: EquipmentRow) => row.ifcUrl.startsWith(`${API_BASE}/`)
  ? row.ifcUrl : apiURL(row.ifcUrl);
const equipmentKey = (row: EquipmentRow) => `${row.project_id}:${row.equipment_id}`;

function ModelPreview({ row, label, visible }: { row: EquipmentRow; label: string; visible: boolean }) {
  const [picked, setPicked] = useState("");
  const labels = row.revisions.slice(-2);
  const id = (revision: string) => `${row.project_id}:${row.equipment_id}:${revision}`;
  const diff = useQuery({
    queryKey: ["landing-cambios", row.project_id, row.equipment_id, ...labels, row.ifcUrl],
    enabled: visible && labels.length === 2,
    queryFn: async ({ signal }) => {
      const query = new URLSearchParams({ from: id(labels[0]!), to: id(labels[1]!) });
      const response = await fetch(apiURL(`/diff?${query}`), { signal });
      if (!response.ok) throw new Error("No se pudieron consultar los cambios.");
      return await response.json() as DiffReport;
    },
  });
  const elements = [...new Set(diff.data?.changes.filter(c => c.affects_geometry &&
    (label === labels[0] ? c.operation !== "added" : c.operation !== "removed")).map(c => elementForField(c.path)))];
  const selected = elements.includes(picked) ? picked : elements[0];
  const version = row.revision_meta?.[label]?.version;
  const url = label === labels.at(-1) ? realIfcUrl(row)
    : apiURL(`/revisions/${encodeURIComponent(id(label))}/ifc?draft=true${version == null ? "" : `&v=${version}`}`);
  return <div className="flex h-full flex-col">
    {row.revision_meta?.[label]?.dataset === "synthetic" ? <p className="px-2 py-1 text-xs text-warning">Modelo sintético</p> : null}
    {elements.length > 0 ? <label className="flex flex-wrap items-center gap-2 p-2 text-sm">Pieza con cambios
      <select className="min-h-11 rounded border border-border bg-surface px-2" value={selected}
        onChange={e => setPicked(e.target.value)}>{elements.map(element => <option key={element} value={element}>{elementLabel(element)}</option>)}</select>
    </label> : diff.isError ? <button className="min-h-11 text-sm underline" onClick={() => void diff.refetch()}>Reintentar la consulta de cambios</button>
      : diff.isSuccess ? <p className="p-2 text-sm text-muted">Sin piezas con cambios geométricos en esta revisión.</p> : null}
    <div className="min-h-0 flex-1">{visible && <IfcViewer ifcUrl={url} selectedId={selected} simple />}</div>
  </div>;
}

export function RealModels() {
  const models = useRealModels(true);
  const [picked, setPicked] = useState<string | null>(null);
  const [chosenRev, setChosenRev] = useState("");
  const frame = useRef<HTMLDivElement>(null);
  const visible = useInView(frame, { once: true, margin: "0px 0px 80px 0px" });
  const router = useRouter();
  const setActive = useEquipment((s) => s.setActive);
  const setRevision = useUi((s) => s.setRevision);
  const rows = models.data ?? [];
  const row = rows.find((r) => equipmentKey(r) === picked) ?? rows[0];
  const latest = row?.revisions.at(-1) ?? "";
  const label = row?.revisions.slice(-2).includes(chosenRev) ? chosenRev : latest;

  return (
    <section id="modelos-reales" aria-labelledby="modelos-titulo" className="relative border-y border-border/70 bg-surface-sunken/40">
      <div className="mx-auto grid w-full max-w-[1240px] gap-10 px-5 py-20 md:px-8 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)]">
        <div className="flex flex-col">
          <h2 id="modelos-titulo" className="landing-display text-[clamp(32px,4.2vw,56px)] leading-[1] text-strong">
            Modelos del reto
          </h2>
          <p className="mt-5 max-w-[44ch] text-[15px] leading-relaxed text-muted">
            Elige un equipo para ver su IFC y comparar las dos últimas revisiones disponibles.
          </p>
          {models.isError ? <p role="alert" className="mt-6 text-sm text-warning">{models.error.message}. <button className="min-h-11 underline" onClick={() => void models.refetch()}>Volver a intentar</button></p> : null}
          <ul className="mt-8 space-y-2" aria-label="Equipos con modelo">
            {rows.map((r) => {
              const active = r === row;
              return (
                <li key={`${r.project_id}:${r.tag}`}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => { setPicked(equipmentKey(r)); setChosenRev(""); }}
                    className={`flex w-full items-center justify-between gap-4 rounded-[12px] border px-4 py-3 text-left transition-[border-color,background-color] duration-[160ms] active:scale-[0.99] ${active ? "border-accent/70 bg-accent-soft" : "border-border hover:border-border-strong"}`}
                  >
                    <span>
                      <span className="block font-mono text-[17px] text-strong">{r.tag}</span>
                      <span className="text-[13px] text-muted">{FAMILY[r.kind] ?? r.kind}</span>
                    </span>
                    <span className="text-[13px] text-muted tabular-nums">rev {r.revisions.join(" · ")}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {row && row.revisions.length > 1 ? <div className="mt-4 flex gap-2" role="group" aria-label="Revisión del modelo">
            {row.revisions.slice(-2).map(rev => <button key={rev} aria-pressed={label === rev} onClick={() => setChosenRev(rev)}
              className="min-h-11 rounded border border-border px-3 aria-pressed:border-accent aria-pressed:text-accent-text">Revisión {rev}</button>)}
          </div> : null}
          {row ? (
            <button
              type="button"
              onClick={() => {
                setActive(toActive(row));
                setRevision(label === latest ? "B" : "A");
                router.push("/modelo");
              }}
              className="mt-6 inline-flex h-11 w-fit items-center rounded-[10px] bg-accent px-5 text-[14.5px] font-semibold text-accent-contrast transition-transform duration-[160ms] active:scale-[0.97]"
            >
              Revisar {row.tag} en Modelo
            </button>
          ) : null}
        </div>
        <div ref={frame} className="relative h-[min(64vh,560px)] overflow-hidden rounded-[16px] border border-border bg-surface-sunken">
          {row ? (
            <ModelPreview key={equipmentKey(row)} row={row} label={label} visible={visible} />
          ) : (
            <p role="status" className="p-6 text-sm text-muted">{models.isLoading ? "Cargando los modelos del reto…" : models.isError ? "Vista previa sin cargar." : "Aún no hay revisiones con un modelo disponible."}</p>
          )}
        </div>
      </div>
    </section>
  );
}

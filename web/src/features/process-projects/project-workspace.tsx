"use client";

import { ArrowLeft, Download, FileSpreadsheet, FileText, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { IfcViewer } from "@/components/three";
import { Badge, Button, Icon, Panel, PanelHeader } from "@/components/ui/primitives";
import { useProcessCopilotDraft } from "@/features/copilot/draft";
import type { ElementState } from "@/features/viewer3d/product-mesh";
import type { PlantProductInfo } from "@/features/viewer3d/types";
import { apiEnabled, apiURL } from "@/lib/api/config";
import { useCanEdit } from "@/lib/accounts";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { processAsset, type Parameter, type ProcessProject } from "./catalog";
import { ComponentInspector, parameters, type ChangeRecord, type Inputs } from "./component-inspector";
import { applyNominalEdits, linesToReview, type NominalField } from "./step-edit";
import { clearDraft, readDraft, saveDraft, type Adjustment, type SavedDraft } from "./draft-storage";
import { PlantReview } from "./plant-review";

const control = "h-9 rounded-[var(--radius-control)] border border-border bg-surface px-3 text-[13px] text-text";
const link = "inline-flex items-center gap-1 text-sm font-medium text-accent-text underline-offset-2 hover:underline";

export function ProcessProjectWorkspace({ project }: { project: ProcessProject }) {
  const canEdit = useCanEdit();
  const incoming = useProcessCopilotDraft(state => state.pending?.project === project.id ? state.pending : null);
  const [applied, setApplied] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [products, setProducts] = useState<PlantProductInfo[]>([]);
  const [dimensions, setDimensions] = useState(false);
  const [inputs, setInputs] = useState<Inputs>({});
  const [draft, setDraft] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<ChangeRecord[]>([]);
  const inflight = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => inflight.current?.abort();
  }, []);
  useEffect(() => {
    return () => { if (draft) URL.revokeObjectURL(draft); };
  }, [draft]);
  const [documentRevision, setDocumentRevision] = useState<"A" | "B">("A");
  const suffix = project.changes.map(change => applied.includes(change.tag) ? "1" : "0").join("");
  const revision = applied.length === 0 ? "A" : applied.length === project.changes.length ? "B" : null;
  const state = project.states[suffix]!;
  const url = draft ?? processAsset(project, state.file);
  const docs = project.documents[revision ?? documentRevision];
  const elementStates: Record<string, ElementState> = Object.fromEntries(
    [...applied, ...(draft ? history.map(record => record.tag) : [])].map(tag => [`element:${tag}`, "changed"]));
  // Rótulo Δ de la última previsualización, por equipo.
  const changeLabels = useMemo(() => {
    const step = history.at(-1)?.step, labels: Record<string, string[]> = {};
    const value = (v: number) => v.toLocaleString("es-ES", { maximumFractionDigits: 3 });
    for (const record of history.filter(item => item.step === step)) {
      const parameter = parameters[record.field];
      (labels[`element:${record.tag}`] ??= []).push(
        `${parameter.title.split(" ")[0]} ${record.before === undefined ? "" : `${value(record.before)} → `}${value(record.after)} ${parameter.unit}`);
    }
    return Object.fromEntries(Object.entries(labels).map(([id, items]) => [id, items.join(" · ")]));
  }, [history]);
  const byId = useMemo(() => new Map(products.map(item => [item.semanticId, item])), [products]);
  const current = byId.get(selected);
  const selectedTag = current?.tag ?? selected.replace(/^element:/, "");
  const info = project.equipment.find(item => item.tag === selectedTag);
  const route = project.lines.find(item => item.tag === selectedTag);
  const editTag = current?.parentId ? byId.get(current.parentId)?.tag : selectedTag;
  const editFields = project.equipment.find(item => item.tag === editTag)?.editFields
    ?? project.lines.find(item => item.tag === editTag)?.editFields;

  function resetDraft() {
    setDraft(undefined);
    setInputs({});
    setError("");
    setNotice("");
    setHistory([]);
    clearDraft(project.id);
  }

  /** Borrador sin API: el navegador reescribe el IFC de la variante cargada. */
  async function localPreview(adjustments: Adjustment[], appliedNow: string[], signal: AbortSignal) {
    const nominal = adjustments.filter((item): item is { tag: string; field: NominalField; value: number } =>
      ["length", "width", "height"].includes(item.field) && Number.isFinite(item.value) && item.value > 0);
    if (nominal.length !== adjustments.length) {
      setError("Sin API solo se ensayan largo, ancho y altura de equipos.");
      return false;
    }
    const base = project.states[project.changes.map(change => appliedNow.includes(change.tag) ? "1" : "0").join("")]!;
    const response = await fetch(processAsset(project, base.file), { signal });
    if (!response.ok) throw new Error("ifc");
    const families = Object.fromEntries(project.equipment.map(item => [item.tag, item.family]));
    const { text, changed } = applyNominalEdits(await response.text(), nominal, families);
    if (!changed.length) {
      setError("No se encontraron las cotas nominales de ese equipo en el IFC.");
      return false;
    }
    const review = linesToReview(project.lines, changed.map(item => item.tag));
    setNotice(review.length ? `Revisar conexiones: ${review.join(", ")}. Sus tuberías no se recalculan en el navegador.` : "");
    if (signal.aborted) return false;
    setDraft(URL.createObjectURL(new Blob([text], { type: "application/x-step" })));
    return true;
  }

  /** Lo que cambia respecto al modelo en pantalla: valor nominal actual de cada parámetro. */
  function pendingRecords(adjustments: { tag: string; field: string; value: number }[]) {
    return adjustments.flatMap(({ tag, field, value }) => {
      const parameter = parameters[field as Parameter];
      if (!parameter) return [];
      const current = byId.get(`element:${tag}`)?.psets.TrazIA_Traceability?.[parameter.prop];
      const before = typeof current === "number" ? current : undefined;
      return before !== undefined && Math.abs(before - value) < 1e-9 ? [] : [{ tag, field: field as Parameter, before, after: value }];
    });
  }

  /** Anota el ensayo y guarda el borrador para regenerarlo al recargar la página. */
  function record(changes: ReturnType<typeof pendingRecords>, adjustments: Adjustment[]) {
    const at = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const step = (history.at(-1)?.step ?? 0) + 1, start = history.at(-1)?.id ?? 0;
    const next = [...history, ...changes.map((change, i) => ({ ...change, id: start + i + 1, step, at }))];
    setHistory(next);
    if (next.length) saveDraft(project.id, { applied, adjustments, history: next });
  }

  /** Genera el IFC del borrador (API o navegador) con los parámetros dados. */
  async function generate(adjustments: Adjustment[], appliedNow: string[]): Promise<boolean> {
    if (inflight.current) return false;
    const controller = new AbortController();
    inflight.current = controller;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (!apiEnabled) return await localPreview(adjustments, appliedNow, controller.signal);
      const response = await fetch(apiURL(`/proyectos-proceso/${project.id}/borrador`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ applied: appliedNow, adjustments }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
        setError(typeof payload?.detail === "string" ? payload.detail : "No se pudo validar el borrador. Revisa las cotas.");
        return false;
      }
      const file = await response.blob();
      if (controller.signal.aborted) return false;
      setDraft(URL.createObjectURL(file));
      return true;
    } catch {
      if (!controller.signal.aborted) setError(apiEnabled ? "No se pudo conectar con la API. Puedes volver a previsualizar el borrador." : "No se pudo preparar el borrador en el navegador.");
      return false;
    } finally {
      inflight.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function preview() {
    const adjustments = Object.entries(inputs).flatMap(([tag, fields]) =>
      Object.entries(fields).filter(([, value]) => value.trim()).map(([field, value]) => ({ tag, field, value: Number(value) })));
    if (!adjustments.length || inflight.current) return;
    if (adjustments.length > 8) {
      setError("El borrador admite hasta ocho parámetros por ensayo.");
      return;
    }
    const changes = pendingRecords(adjustments);
    if (await generate(adjustments, applied)) record(changes, adjustments);
  }

  /** Al volver a la página: el historial guardado y su borrador, regenerado desde el IFC base. */
  async function restore(saved: SavedDraft) {
    setApplied(saved.applied);
    setHistory(saved.history);
    setInputs(saved.adjustments.reduce<Inputs>((all, { tag, field, value }) =>
      ({ ...all, [tag]: { ...all[tag], [field]: String(value) } }), {}));
    if (!await generate(saved.adjustments, saved.applied)) {
      setError(previous => previous || "No se pudo regenerar el borrador guardado. Vuelve a previsualizarlo.");
    }
  }
  const restoreSaved = useEffectEvent((saved: SavedDraft) => void restore(saved));
  useEffect(() => {
    const saved = readDraft(project.id);
    if (!saved) return;
    const frame = requestAnimationFrame(() => restoreSaved(saved));
    return () => cancelAnimationFrame(frame);
  }, [project.id]);

  function editInput(tag: string, field: Parameter, value: string) {
    setInputs(previous => ({ ...previous, [tag]: { ...previous[tag], [field]: value } }));
  }

  function loadRevision(next: "A" | "B") {
    resetDraft();
    setDocumentRevision(next);
    setApplied(next === "B" ? project.changes.map(change => change.tag) : []);
    setSelected("");
  }

  function importCopilotDraft() {
    if (!incoming || !canEdit || busy) return;
    if (revision !== incoming.revision) loadRevision(incoming.revision);
    setInputs(previous => {
      const next: Inputs = { ...previous };
      for (const adjustment of incoming.adjustments) {
        next[adjustment.tag] = { ...next[adjustment.tag], [adjustment.field]: String(adjustment.value) };
      }
      return next;
    });
    setSelected(`element:${incoming.adjustments[0]?.tag ?? ""}`);
    useProcessCopilotDraft.getState().setPending(null);
  }

  return <div className="space-y-5">
    <Link href="/documentos?vista=proyectos" className={link}><Icon icon={ArrowLeft} size={15} /> Proyectos</Link>
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted">{project.code}</span>
          <Badge tone="warning">Datos sintéticos</Badge>
        </div>
        <h1 className="text-2xl font-semibold text-strong">{project.name}</h1>
        <p className="text-sm text-muted">{project.description}</p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Revisión de planta">
        <Button size="sm" disabled={busy} aria-pressed={revision === "A" && !draft} onClick={() => loadRevision("A")}>Revisión A</Button>
        <Button size="sm" disabled={busy} aria-pressed={revision === "B" && !draft} onClick={() => loadRevision("B")}>Revisión B</Button>
      </div>
    </header>

    <PlantReview pdf={processAsset(project, docs.plan)} fieldsUrl={processAsset(project, docs.fields)}
      selected={selected} onSelect={setSelected} matchesModel={!!revision && !draft}>
      <Panel className="flex h-[clamp(330px,65dvh,730px)] min-w-0 flex-col overflow-hidden">
        <PanelHeader title="Modelo de planta"
          description={`${project.equipment.length} equipos · ${project.lines.length} líneas · ${draft ? "Borrador personalizado" : formatNumber(state.triangles) + " triángulos IFC"}`}
          actions={<a href={url} download={draft ? `${project.code}-ENSAYO-DRAFT.ifc` : state.file} className={link}><Icon icon={Download} size={15} /> Descargar IFC</a>} />
        <div className="min-h-0 flex-1 px-2 pb-2">
          <IfcViewer ifcUrl={url} ifcGzipUrl={draft ? undefined : processAsset(project, state.transport)}
            scenario={project.preset} holdPrevious animateChanges changeLabels={changeLabels}
            selectedId={selected}
            onSelect={setSelected} onProducts={setProducts} showSelectionDimensions={dimensions}
            elementStates={elementStates} />
        </div>
        <p className="min-h-9 px-4 pb-3 text-xs text-muted">
          {current?.parentId ? current.label ?? current.name : info ? `${info.tag} · ${info.name} · ${info.service}`
            : route ? `${route.tag} · ${route.fluid} · ${route.start} → ${route.end}`
              : "Selecciona un equipo o una tubería para consultar su tag y servicio."}
        </p>
      </Panel>
    </PlantReview>

    <div className="space-y-3">
      {incoming && canEdit ? <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-3 text-sm">
        <span>{incoming.adjustments.length} cambios propuestos para la rev. {incoming.revision}</span>
        <Button type="button" size="sm" disabled={busy} onClick={importCopilotDraft}>Cargar borrador del Copiloto</Button>
      </div> : null}
      <ComponentInspector products={byId} selected={selected} select={setSelected}
        editFields={canEdit ? editFields : undefined} inputs={inputs} onInput={editInput}
        dimensions={dimensions} setDimensions={setDimensions} onPreview={() => void preview()}
        onReset={resetDraft} busy={busy} error={error} draft={!!draft} notice={notice} history={history} />
    </div>

    <Panel className="space-y-4 p-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-semibold text-strong">Cambios por pieza</h2>
          <Badge tone={revision ? "neutral" : "warning"}>{revision ? `Rev. ${revision}` : "Ensayo parcial"}</Badge>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {project.changes.map(change => (
            <label key={change.tag} className={cn("flex cursor-pointer items-start gap-3 rounded-md border p-3",
              applied.includes(change.tag) ? "border-accent bg-accent-soft" : "border-border")}>
              <input type="checkbox" className="mt-1 accent-[var(--color-accent)]" disabled={busy} checked={applied.includes(change.tag)}
                onChange={event => {
                  resetDraft();
                  setSelected(`element:${change.tag}`);
                  setApplied(current => event.target.checked ? [...current, change.tag] : current.filter(tag => tag !== change.tag));
                }} />
              <span className="text-sm">
                <span className="block font-mono text-xs text-accent-text">{change.tag}</span>
                <span className="block font-medium">{change.label}</span>
                <span className="text-xs text-muted">{formatNumber(change.before)} → {formatNumber(change.after)} {change.unit}</span>
              </span>
            </label>
          ))}
        </div>
        {applied.length ? <Button size="sm" disabled={busy} onClick={() => loadRevision("A")}><Icon icon={RotateCcw} size={14} /> Restablecer A</Button> : null}
        {draft || !revision ? <p className="text-xs text-muted">Los planos y las hojas corresponden a la revisión documental A o B.</p> : null}
    </Panel>

    <Panel>
      <PanelHeader title="Planos y hojas de datos"
        description="GA acotado de la planta, planos de equipo y hojas de datos por revisión."
        actions={<label className="flex items-center gap-2 text-xs text-muted">Revisión documental
          <select className={control} disabled={busy} value={revision ?? documentRevision}
            onChange={event => {
              const next = event.target.value as "A" | "B";
              if (revision) loadRevision(next);
              else setDocumentRevision(next);
            }}>
            <option value="A">A</option><option value="B">B</option>
          </select>
        </label>} />
      <div className="flex flex-wrap gap-4 px-5 pb-4">
        <a className={link} href={processAsset(project, docs.plan)} target="_blank" rel="noreferrer"><Icon icon={FileText} size={16} /> GA de implantación</a>
        <a className={link} href={processAsset(project, docs.workbook)} download><Icon icon={FileSpreadsheet} size={16} /> Excel de equipos, líneas y cambios</a>
        <a className={link} href={processAsset(project, docs.archive)} download><Icon icon={Download} size={16} /> Descargar dossier ZIP</a>
      </div>
      <div className="overflow-x-auto px-5 pb-4">
        <table className="w-full min-w-[565px] text-left text-sm">
          <thead><tr>{["Equipo", "Servicio", "Plano", "Datos"].map(column => <th key={column} className="py-2 pr-3 text-xs font-medium text-muted" scope="col">{column}</th>)}</tr></thead>
          <tbody>
            {project.equipment.map(item => {
              const files = docs.equipment[item.tag]!;
              return <tr key={item.tag} className={cn("border-t border-border", selectedTag === item.tag && "bg-accent-soft")}>
                <th scope="row" className="py-2 pr-3">
                  <button type="button" onClick={() => setSelected(`element:${item.tag}`)} className="text-left hover:underline">
                    <span className="mr-2 font-mono text-xs text-accent-text">{item.tag}</span>{item.name}
                  </button>
                </th>
                <td className="py-2 pr-3 text-muted">{item.service}</td>
                <td className="py-2 pr-3"><a className={link} href={processAsset(project, files.plan)} target="_blank" rel="noreferrer" aria-label={`PDF de ${item.tag}`}>PDF</a></td>
                <td className="py-2"><a className={link} href={processAsset(project, files.workbook)} download aria-label={`XLSX de ${item.tag}`}>XLSX</a></td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  </div>;
}

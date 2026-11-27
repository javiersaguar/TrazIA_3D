"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, CircleAlert, CircleCheck, Eye, History, Info, MessageSquareText, PencilRuler, RotateCcw, Undo2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useEquipment as useActiveEquipment } from "@/stores/equipment";

import { IfcViewer } from "@/components/three";
import { FullscreenFrame } from "@/components/shell/fullscreen";
import { Segmented, Tip } from "@/components/ui/controls";
import { Badge, Button, EmptyState, Icon, Panel, PanelHeader, Skeleton } from "@/components/ui/primitives";
import { apiEnabled } from "@/lib/api/config";
import { ApiError, cancelJob, getJob, subscribeJob } from "@/lib/api/client";
import { editableElements } from "./elements";
import { convertDisplay } from "./display-value";
import { PartsEditor } from "./parts-editor";
import { draftKey, useDraftField, useDraftCache } from "./draft-store";
import { formatValue } from "@/lib/format";
import { useEquipment } from "@/lib/queries";
import { useDemoUser } from "@/lib/session";
import { useSelection } from "@/stores/selection";
import { sessionActor } from "@/lib/actor";

import {
  startDrawing, getDrawings, drawingDownloadUrl,
  STATUS_LABEL, applyProposal, designReportUrl, interpretRequest, createProposal, discardProposal, getCatalog, getProposal, listProposals,
  previewIfcUrl, replaceProposal, revertProposal, revisionIdentity, revisionIfcUrl, startPreview,
  type Datum, type Issue, type Proposal, type Target,
} from "./api";
import {
  clarifiedText, draftSignature, draftsFromOperations, elementStates, issuesFor,
  toOperations, unitsFor, type Drafts,
} from "./form";

const EDITABLE = new Set(["draft", "needs_clarification", "invalid", "ready", "previewed"]);
const DATUM_LABEL: Record<Datum, string> = {
  suelo: "desde el suelo", tangente_inferior: "desde la tangente inferior", interno: "según convenio interno", norte: "desde el Norte",
};
const control = "w-full rounded-[var(--radius-control)] border border-border bg-surface px-2 py-1.5 text-[13px] text-text";

function tone(status: Proposal["status"]) {
  return status === "previewed" || status === "applied" ? "approved"
    : status === "invalid" || status === "stale" ? "danger"
      : status === "needs_clarification" ? "warning" : "neutral";
}

/** K.4 · Proponer cambios de diseño desde Modelo: formulario → validar → previsualizar → confirmar. */
export function DesignEditWorkspace({ tag = "V-101" }: { tag?: string }) {
  if (!apiEnabled) {
    return <Panel><EmptyState icon={PencilRuler} title="La edición asistida necesita la API local">
      Arranca <code>uv run trazia serve</code> y define NEXT_PUBLIC_API_URL. Sin API no se simulan propuestas.
    </EmptyState></Panel>;
  }
  return <Workspace tag={tag} />;
}

function Workspace({ tag: initialTag }: { tag: string }) {
  // El equipo es el de la barra superior; lo guardado por el Copiloto solo sirve si aún no hay ninguno.
  const [savedTag] = useDraftField(draftKey("navigation","",""), "tag");
  const [savedProjectId] = useDraftField(draftKey("navigation","",""), "projectId");
  const qc = useQueryClient();
  const user = useDemoUser();
  const selectedId = useSelection((s) => s.selectedId);
  const select = useSelection((s) => s.setSelected);
  const equipment = useEquipment();
  const rows = equipment.data ?? [];
  const active = useActiveEquipment((s) => s.active);
  const selectedEquipment = rows.find(row => row.tag === active?.tag && (row.project_id ?? "") === active?.project_id)
    ?? rows.find(row => row.tag === savedTag && (row.project_id ?? "DEMO-PLANT") === savedProjectId)
    ?? rows.find(row => row.tag === initialTag) ?? rows[0];
  const tag = selectedEquipment?.tag ?? savedTag ?? initialTag;
  const projectId = selectedEquipment?.project_id ?? savedProjectId;
  const labels: string[] = selectedEquipment?.revisions ?? ["B"];
  const [chosenLabel, setLabel] = useDraftField(draftKey(projectId,tag,"selection"), "label");
  const label = labels.includes(chosenLabel) ? chosenLabel : labels[labels.length - 1] ?? "B";
  const identity = useQuery({ queryKey: ["design-identity", projectId, tag, label], queryFn: () => revisionIdentity(tag, label, projectId) });
  const catalog = useQuery({
    queryKey: ["design-catalog", identity.data?.identity, identity.data?.etag],
    queryFn: () => getCatalog(identity.data!.identity), enabled: !!identity.data,
  });
  const history = useQuery({
    queryKey: ["design-history", identity.data?.identity, identity.data?.etag],
    queryFn: () => listProposals(identity.data!.identity), enabled: !!identity.data,
  });

  const cacheKey = draftKey(projectId, tag, label);
  const [, setPendingJob] = useDraftField(cacheKey, "pendingJob");
  const [partForm, setPartForm] = useDraftField(cacheKey, "partForm");

  // El grupo sigue a la selección 3D salvo que la persona elija otro con esa misma selección.
  const [choice, setChoice] = useDraftField(cacheKey, "choice");
  const chosenGroup = choice && choice.selection === selectedId ? choice.group : null;
  const [drafts, setDrafts] = useDraftField(cacheKey, "drafts");
  const [partChanges,setPartChanges] = useDraftField(cacheKey, "partChanges");
  const [detailLevel,setDetailLevel] = useDraftField(cacheKey, "detailLevel");
  const [drawing,setDrawing] = useDraftField(cacheKey, "drawing");
  const [activeJob,setActiveJob] = useState<string|null>(null);
  const [reason, setReason] = useDraftField(cacheKey, "reason");
  const [actorInput, setActor] = useDraftField(cacheKey, "actor");
  const actor = actorInput ?? user ?? "";
  const name = actor.trim();
  const [proposal, setProposal] = useDraftField(cacheKey, "proposal");
  const [signature, setSignature] = useDraftField(cacheKey, "signature");
  const [steps, setSteps] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [side, setSide] = useDraftField(cacheKey, "side");
  const applyKey = useRef<{ id: string; key: string } | null>(null);
  const stopStream = useRef<(() => void) | null>(null);
  const [request, setRequest] = useDraftField(cacheKey, "request");
  const [useModel, setUseModel] = useDraftField(cacheKey, "useModel");
  const [intent, setIntent] = useDraftField(cacheKey, "intent");
  const [autoCheck, setAutoCheck] = useDraftField(cacheKey, "autoCheck");

  useEffect(() => () => stopStream.current?.(), []);

  useEffect(() => {
    const id = useDraftCache.getState().entries[cacheKey]?.proposal?.id;
    if (!id) return;
    let live = true;
    void getProposal(id).then(value => {
      if (live) useDraftCache.getState().update(cacheKey, "proposal", value);
    }).catch(error => {
      if (live && error instanceof ApiError && error.status===404) useDraftCache.getState().update(cacheKey,"proposal",null);
    });
    return () => { live = false; };
  }, [cacheKey]);

  useEffect(() => {
    const saved = useDraftCache.getState().entries[cacheKey]?.pendingJob;
    if (!saved) return;
    let live = true;
    let stop: (()=>void) | undefined;
    const finish = async (status: string) => {
      try {
        if (saved.kind === "preview") {
          const id = useDraftCache.getState().entries[cacheKey]?.proposal?.id;
          if (id) {
            const value = await getProposal(id);
            if (live) useDraftCache.getState().update(cacheKey,"proposal",value);
          }
        } else if (status === "done") {
          const value = await getDrawings(saved.revisionId);
          if (live) useDraftCache.getState().update(cacheKey,"drawing",value);
        }
      } finally {
        if (live) { useDraftCache.getState().update(cacheKey,"pendingJob",null); setBusy(null); setActiveJob(null); }
      }
    };
    void getJob(saved.id).then(job => {
      if (!live) return;
      if (["done","error","cancelled","timeout"].includes(job.status)) return finish(job.status);
      setActiveJob(saved.id); setBusy("seguir");
      stop = subscribeJob(saved.id,event=>setSteps(old=>[...old,event.detail]),status=>{void finish(status);},()=>{});
    }).catch(() => { if (live) {setBusy(null);setActiveJob(null);} });
    return () => {live=false;stop?.();};
  },[cacheKey]);

  // Cambiar de base empieza de cero: una propuesta pertenece a una revisión concreta.
  function changeBase(next: string, carried: Proposal | null = null) {
    setLabel(next); setSteps([]);
    if (carried) {
      const key = draftKey(projectId, tag, next);
      useDraftCache.getState().update(key, "proposal", carried);
    }
  }

  const targets = useMemo(() => catalog.data?.targets ?? [], [catalog.data]);
  const elements = useMemo(() => editableElements(targets, catalog.data?.kind ?? ""), [targets, catalog.data?.kind]);
  const group = (chosenGroup && elements.some(e => e.id === chosenGroup) ? chosenGroup : null)
    ?? elements.find(e => e.semantic && e.semantic === selectedId?.replace(/^detail:/, "").split("/")[0])?.id ?? "equipo";
  const currentElement = elements.find(e => e.id === group);
  const visible = targets.filter(t => currentElement?.targets.includes(t.target));
  const chooseElement = (id: string) => {
    const next = elements.find(e => e.id === id);
    select(next?.semantic ?? null); setChoice({group:id, selection:next?.semantic ?? null});
  };
  const operations = toOperations(drafts, targets);
  const currentSignature = draftSignature(operations, reason) + JSON.stringify([partChanges,detailLevel,name,intent?.clarifications,intent?.rejected]);
  const dirty = !!proposal && proposal.kind === "cambio_diseno" && signature !== currentSignature;
  const editable = !proposal || (proposal.kind === "cambio_diseno" && EDITABLE.has(proposal.status));
  const preview = proposal?.preview && !dirty ? proposal.preview : null;
  const issues = useMemo(() => proposal?.issues ?? [], [proposal]);
  const states = useMemo(() => elementStates(preview, dirty ? [] : issues), [preview, issues, dirty]);
  const base = proposal?.base ?? (identity.data && catalog.data
    ? { revision_id: identity.data.identity, version: catalog.data.version, revision: catalog.data.revision } : null);
  const ifcUrl = preview && side === "despues" ? previewIfcUrl(preview)
    : base ? revisionIfcUrl(base.revision_id, base.version) : "";
  const canValidate = editable && name.length >= 2 && reason.trim().length >= 3 && (operations.length > 0 || partChanges.length > 0) && !intent?.clarifications.length && !intent?.rejected.length && !busy;

  function setDraft(target: Target, patch: Partial<Drafts[string]>) {
    setDrafts((old) => ({ ...old, [target.target]: {
      value: old[target.target]?.value ?? String(target.current.value), unit: old[target.target]?.unit ?? target.unit,
      datum: old[target.target]?.datum ?? target.datums[0], ...patch,
    } }));
  }

  async function run<T>(step: string, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(step);
    try { return await action(); }
    catch (error) { toast.error(error instanceof Error ? error.message : "No se pudo completar la acción"); }
    finally { setBusy(null); }
  }

  const validate = () => run("validar", async () => {
    if (!identity.data) return;
    // Si el lote viene del chat se conserva la petición original; el contenido es el del formulario.
    const fromChat = !!intent && intent.request_text.trim() !== "";
    const body = {
      operations, part_changes: partChanges, detail_level: detailLevel, reason: reason.trim(), actor: name, origin: fromChat ? "chat" as const : "formulario" as const,
      request_text: fromChat ? intent?.request_text ?? null : null,
      clarifications: fromChat ? intent?.clarifications ?? [] : [],
    };
    const result = proposal && proposal.kind === "cambio_diseno" && EDITABLE.has(proposal.status)
      ? await replaceProposal(proposal.id, body)
      : await createProposal(identity.data.identity, identity.data.etag, body);
    setProposal(result); setSignature(currentSignature); setSteps([]);
    applyKey.current = null;
  });
  // Un cambio pedido al Copiloto llega comprobado: se ve el resumen sin pulsar nada. No se guarda
  // ninguna revisión hasta «Confirmar».
  const autoActor = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (!autoCheck) {
      autoActor.current = undefined;
      return;
    }
    if (autoActor.current === undefined) autoActor.current = actorInput;
    if (busy || !identity.data || !catalog.data) return;
    // Si la persona escribe su nombre al llegar, comprueba ella con el botón.
    if (actorInput !== autoActor.current) {
      setAutoCheck(false);
      return;
    }
    if (canValidate) {
      setAutoCheck(false);
      validate();
      return;
    }
    // Una duda pendiente o un nombre que la persona está escribiendo se dejan para el botón.
    if (intent?.clarifications.length || intent?.rejected.length || !editable) {
      setAutoCheck(false);
      return;
    }
    // La sesión puede tardar en dar el nombre de quien propone: se espera un momento.
    const timer = window.setTimeout(() => setAutoCheck(false), 4000);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoCheck, busy, identity.data, catalog.data, canValidate, actorInput]);

  const runPreview = () => run("previsualizar", async () => {
    if (!proposal) return;
    const job = await startPreview(proposal.id);
    setSteps([]);
    setActiveJob(job.job_id); setPendingJob({id:job.job_id,kind:"preview",revisionId:proposal.base.revision_id});
    setBusy("previsualizar");
    await new Promise<void>((resolve,reject) => {
      stopStream.current?.();
      stopStream.current = subscribeJob(job.job_id,
        (event) => { if (event.stage !== "job") setSteps((old) => [...old, event.detail]); },
        async (status) => {
          if (status !== "done") {
            const detail = (await getJob(job.job_id).catch(() => null))?.error;
            toast.error(detail ?? `Previsualización ${status}`, { description: "La revisión base no ha cambiado." });
          }
          try { setProposal(await getProposal(proposal.id)); resolve(); }
          catch (failure) { reject(failure); }
          finally { setActiveJob(null); setPendingJob(null); }
        },
        () => { toast.error("Seguimiento interrumpido; intentando reconectar. Puedes cancelar el trabajo."); });
    });
    setSide("despues");
  });

  const confirm = () => run("confirmar", async () => {
    if (!proposal?.preview) return;
    // Reintentar la misma confirmación usa la misma clave: nunca dos revisiones.
    if (applyKey.current?.id !== proposal.id + proposal.preview.ifc_sha256)
      applyKey.current = { id: proposal.id + proposal.preview.ifc_sha256, key: crypto.randomUUID() };
    const result = await applyProposal(proposal, name, applyKey.current.key);
    setProposal(result.proposal); setDrawing(null);
    toast.success(`Revisión ${result.proposal.target_revision} creada como DRAFT`, {
      description: "La revisión base se conserva. La aprobación técnica sigue siendo una acción posterior.",
    });
    await qc.invalidateQueries({ queryKey: ["equipment"] });
    await qc.invalidateQueries({ queryKey: ["design-history"] });
  });

  const ask = (text: string) => run("interpretar", async () => {
    if (!identity.data || !text.trim()) return;
    const result = await interpretRequest(identity.data.identity, text.trim(), selectedId, useModel);
    setIntent(result);
    setPartChanges(result.part_changes ?? []); setDetailLevel(result.detail_level ?? undefined);
    if (result.part_changes?.length && !reason.trim()) setReason(`Petición: «${text.trim().slice(0, 200)}»`);
    if (!result.operations.length) setDrafts({});
    if (result.operations.length) {
      const filled = draftsFromOperations(result.operations, targets);
      setDrafts(filled);
      const first = targets.find((t) => t.target in filled);
      if (first) setChoice({ group: first.group, selection: selectedId });
      if (!reason.trim()) setReason(`Petición: «${text.trim().slice(0, 200)}»`);
    }
  });

  const discard = () => run("descartar", async () => {
    if (!proposal) return;
    await discardProposal(proposal.id, name || sessionActor());
    setProposal(null); setSteps([]);
  });

  const undo = (applied: Proposal) => run("deshacer", async () => {
    const target = applied.target_revision;
    const current = await revisionIdentity(tag, target, projectId);
    const reversion = await revertProposal(applied.id, current.etag, name || applied.actor,
      `Deshacer la orden ${applied.id.slice(0, 8)} sobre ${applied.base.revision}`);
    // La propuesta de deshacer pertenece a la revisión derivada.
    changeBase(target, reversion);
  });

  const makeDrawing = () => run("plano", async () => {
    const target=proposal?.status==="applied"?proposal.target_revision:label;
    const current=await revisionIdentity(tag,target,projectId);
    const job=await startDrawing(current.identity,current.etag);
    setActiveJob(job.job_id);setPendingJob({id:job.job_id,kind:"drawing",revisionId:current.identity});setSteps([]);
    try {
      await new Promise<void>((resolve,reject)=>{
        stopStream.current?.();
        stopStream.current=subscribeJob(job.job_id,event=>setSteps(old=>[...old,event.detail]),status=>{
          if(status==="done")resolve();else reject(new Error(`Generación del plano: ${status}. La revisión no se ha modificado.`));
        },()=>toast.error("Seguimiento interrumpido; intentando reconectar."));
      });
      setDrawing(await getDrawings(current.identity));
      toast.success("Plano GA nuevo generado desde el IFC");
    } finally {setActiveJob(null);setPendingJob(null);}
  });

  if (identity.isLoading || catalog.isLoading) return <Skeleton className="h-[620px]" />;
  if (identity.error || catalog.error || !catalog.data)
    return <Panel><EmptyState icon={CircleAlert} title="No se pudo cargar el catálogo de operaciones">
      {(identity.error ?? catalog.error)?.message}
    </EmptyState></Panel>;

  const flow = [
    ((operations.length > 0 || partChanges.length > 0) && reason.trim().length >= 3) || (!!proposal && !dirty),
    !!proposal && !dirty && ["ready", "previewed", "applied"].includes(proposal.status),
    !!proposal && !dirty && ["previewed", "applied"].includes(proposal.status),
    proposal?.status === "applied",
  ];
  const index = elements.findIndex(e => e.id === group);
  const synthetic = catalog.data.dataset !== "real";

  return (
    <div className="space-y-4" data-testid="design-edit">
      <FlowSteps done={flow} />

      <FullscreenFrame
        title="Vista 3D"
        description={preview
          ? "Así quedaría el equipo con tu cambio. Todavía no está guardado."
          : "Así está ahora el equipo. Pulsa una pieza para editar sus medidas."}
        height="h-[min(50vh,520px)] min-h-[320px]"
        actions={<>
          {synthetic ? <Badge tone="warning">Datos sintéticos</Badge> : null}
          <Segmented<"antes" | "despues"> label="Revisión mostrada" value={preview ? side : "antes"} onChange={setSide}
            options={[{ value: "antes", label: `Antes · Rev ${base?.revision ?? label}` },
              { value: "despues", label: preview ? `Después · Rev ${preview.target_revision}` : "Después" }]} />
        </>}
      >
        {ifcUrl ? <IfcViewer ifcUrl={ifcUrl} selectedId={selectedId ?? undefined} onSelect={(id) => select(id)}
          elementStates={states} /> : <Skeleton className="h-full" />}
      </FullscreenFrame>

      <Panel className="flex min-h-0 flex-col">
        <PanelHeader title="Proponer un cambio"
          description={<span className="inline-flex flex-wrap items-center gap-1.5">
            Equipo <strong className="text-text">{tag}</strong>, a partir de la
            <select aria-label="Revisión base" className={`${control} w-auto py-0.5`} value={label}
              onChange={(e) => changeBase(e.target.value)} disabled={!!busy}>
              {labels.map((rev) => <option key={rev} value={rev}>Rev {rev}</option>)}
            </select>
          </span>}
          actions={proposal ? <Badge tone={tone(proposal.status)}>{STATUS_LABEL[proposal.status]}</Badge> : null} />
        <div className="space-y-5 px-4 pb-5 text-[13px] sm:px-5" data-testid="design-form">

          {!catalog.data.geometry_supported && <p className="rounded border border-warning-border bg-warning-bg p-2 text-warning">
            En este tipo de equipo solo se pueden cambiar datos; la forma 3D no se modifica.
          </p>}

          {editable && <section className="space-y-2 rounded-[var(--radius-card)] border border-border bg-surface-sunken/50 p-3" aria-label="Describir el cambio con tus palabras">
            <label className="block space-y-1.5">
              <span className="flex items-center gap-1.5 font-medium text-strong"><Icon icon={MessageSquareText} size={14} />Describir el cambio</span>
              <span className="block text-[12px] text-muted">Escríbelo como se lo dirías a un compañero y rellenamos los valores por ti.</span>
              <textarea className={control} rows={2} maxLength={2000} value={request} onChange={(e) => setRequest(e.target.value)}
                placeholder="Por ejemplo: alarga el recipiente hasta 7000 mm y sube la boquilla N3 a 4,2 m" />
            </label>
            <div className="flex justify-end">
              <Button size="sm" disabled={!!busy || !request.trim()} onClick={() => ask(request)}>
                {busy === "interpretar" ? "Preparando…" : "Preparar el cambio"}
              </Button>
            </div>
            {intent && <div className="space-y-1 text-[12px]" aria-live="polite">
              {intent.operations.length > 0 && <p className="text-approved">Hemos rellenado {intent.operations.length === 1 ? "1 valor" : `${intent.operations.length} valores`}. Revísalos abajo.</p>}
              {intent.notes.map((note, i) => <p key={`n${i}`} className="text-muted">{note}</p>)}
              {intent.rejected.map((message, i) => <p key={`r${i}`} role="alert" className="text-danger">{message}</p>)}
              {intent.clarifications.map((item, i) => <div key={`c${i}`} className="space-y-1">
                <p className="text-warning">{item.question}</p>
                {item.options.length > 0 && <div className="flex flex-wrap gap-1">
                  {item.options.map((option) => <Button key={option} size="sm" variant="secondary" disabled={!!busy} onClick={() => {
                    const text = clarifiedText(request, option); setRequest(text); void ask(text);
                  }}>{targets.find((t) => t.target === option)?.label ?? option}</Button>)}
                </div>}
              </div>)}
              <Button size="sm" variant="ghost" onClick={() => { setIntent(null); setDrafts({}); setPartChanges([]); }}>Borrar lo que se rellenó</Button>
            </div>}
          </section>}

          <section className="space-y-3" aria-label="Valores del cambio">
            <div className="flex flex-wrap items-end gap-2">
              <label className="min-w-[14rem] flex-1 space-y-1"><span className="font-medium text-strong">{editable ? "O cambia las medidas de una pieza" : "Pieza"}</span>
                <select aria-label="Pieza" className={control} value={group} onChange={(e) => chooseElement(e.target.value)}>
                  {elements.map(g => <option key={g.id} value={g.id}>{g.label}</option>)}
                </select>
              </label>
              <div className="flex items-center gap-1 text-xs text-muted">
                <Button size="sm" variant="secondary" aria-label="Pieza anterior" disabled={!!busy || index <= 0}
                  onClick={() => chooseElement(elements[index - 1]!.id)}><Icon icon={ChevronLeft} size={14} /></Button>
                <span className="w-12 text-center">{index + 1} / {elements.length}</span>
                <Button size="sm" variant="secondary" aria-label="Pieza siguiente" disabled={!!busy || index >= elements.length - 1}
                  onClick={() => chooseElement(elements[index + 1]!.id)}><Icon icon={ChevronRight} size={14} /></Button>
              </div>
            </div>

            <fieldset disabled={!editable || !!busy} className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3" data-testid="design-fields">
              {visible.length === 0 && <p className="text-muted">Esta pieza no tiene medidas que se puedan cambiar.</p>}
              {visible.map((target) => {
                const draft = drafts[target.target];
                const opIds = proposal?.operations.filter((o) => o.target === target.target).map((o) => o.id) ?? [];
                const own = dirty ? [] : issuesFor(target.target, target.path, issues, opIds);
                const operation = proposal?.operations.find((o) => o.target === target.target);
                const units = unitsFor(target);
                return (
                  <div key={target.target} className={`space-y-1.5 rounded-[var(--radius-card)] border p-3 ${draft ? "border-accent/60" : "border-border"}`}>
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-medium text-strong">{target.label}</span>
                      <Tip content={target.rule}>
                        <button type="button" aria-label={`Condiciones de ${target.label}`} className="text-muted hover:text-text"><Icon icon={Info} size={14} /></button>
                      </Tip>
                    </div>
                    <div className="flex gap-2">
                      <input className={control} value={draft?.value ?? String(target.current.value)}
                        inputMode={target.text ? "text" : "decimal"} aria-label={`Nuevo valor de ${target.label}`}
                        aria-invalid={own.some((i) => i.severity === "error")}
                        onChange={(e) => setDraft(target, { value: e.target.value })} />
                      {units.length > 0 && <select className={`${control} w-20`} aria-label={`Unidad de ${target.label}`}
                        value={draft?.unit ?? target.unit} onChange={(e) => setDraft(target, { unit: e.target.value, value: convertDisplay(draft?.value ?? String(target.current.value), draft?.unit ?? target.unit, e.target.value) })}>
                        {units.map((u) => <option key={u} value={u}>{u === "deg" ? "°" : u}</option>)}
                      </select>}
                    </div>
                    {target.datums.length > 1 && <select className={control} aria-label={`Referencia de ${target.label}`}
                      value={draft?.datum ?? target.datums[0]} onChange={(e) => {
                        const next = e.target.value as Datum, previous = draft?.datum ?? target.datums[0];
                        const mmText = convertDisplay(draft?.value ?? String(target.current.value), draft?.unit ?? target.unit, "mm");
                        const mm = mmText ? Number(mmText) : NaN;
                        const shift = Number(convertDisplay(drafts.skirt_height?.value ?? String(catalog.data?.datum.shell_bottom_mm ?? 0), drafts.skirt_height?.unit ?? "mm", "mm"));
                        const value = Number.isFinite(mm) ? String(mm + (previous === "tangente_inferior" ? shift : -shift)) : "";
                        setDraft(target, { datum: next, value: convertDisplay(value, "mm", draft?.unit ?? target.unit) });
                      }}>
                      {target.datums.map((d) => <option key={d} value={d}>Medida {DATUM_LABEL[d]}</option>)}
                    </select>}
                    <div className="flex min-h-6 items-center justify-between gap-2 text-[12px] text-muted">
                      <span>Ahora: {formatValue(target.current.value, target.current.unit)}</span>
                      {draft && <button type="button" className="text-accent-text hover:underline" onClick={() => setDrafts(old => {
                        const next = { ...old }; delete next[target.target]; return next;
                      })} aria-label={`Restablecer ${target.label}`}>Volver al valor actual</button>}
                    </div>
                    {operation?.resolution && !dirty && <p className="text-[12px] text-sky">{operation.resolution}</p>}
                    {own.map((issue, i) => <IssueLine key={i} issue={issue} />)}
                  </div>
                );
              })}
            </fieldset>

            <details className="rounded-[var(--radius-card)] border border-border p-3" data-testid="parts-section">
              <summary className="cursor-pointer font-medium text-strong">Añadir o quitar piezas {partChanges.length ? `· ${partChanges.length} en el cambio` : ""}</summary>
              <PartsEditor key={identity.data?.identity} catalog={catalog.data} form={partForm} onFormChange={setPartForm} changes={partChanges} onChange={setPartChanges} detailLevel={detailLevel} onDetailLevel={setDetailLevel} disabled={!editable || !!busy} />
            </details>
          </section>

          <fieldset disabled={!editable || !!busy} className="grid gap-3 @xl:grid-cols-[2fr_1fr]">
            <label className="block space-y-1"><span className="font-medium text-strong">Motivo del cambio (obligatorio)</span>
              <textarea className={control} rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Por ejemplo: aumentar capacidad según la hoja de proceso" />
            </label>
            <label className="block space-y-1"><span className="font-medium text-strong">Persona que propone</span>
              <input className={control} value={actor} maxLength={100} onChange={(e) => setActor(e.target.value)} />
            </label>
          </fieldset>

          {proposal && <Summary proposal={proposal} dirty={dirty} />}
          {busy && steps.length > 0 && <p className="text-[12px] text-muted" aria-live="polite">{steps.at(-1)}</p>}

          <div className="space-y-2 border-t border-border pt-4">
            <div className="flex flex-wrap items-center gap-2">
              {editable && <Button variant={proposal?.status === "ready" && !dirty ? "secondary" : "primary"} disabled={!canValidate} onClick={validate}>
                {busy === "validar" ? "Comprobando…" : proposal ? "Volver a comprobar" : "Comprobar cambios"}
              </Button>}
              {proposal && ["ready", "previewed"].includes(proposal.status) && !dirty &&
                <Button variant={proposal.status === "ready" ? "primary" : "secondary"} disabled={!!busy} onClick={runPreview}>
                  <Icon icon={Eye} size={14} />{busy === "previsualizar" ? "Generando el modelo…" : "Ver resultado en 3D"}
                </Button>}
              {proposal?.status === "previewed" && !dirty &&
                <Button variant="primary" disabled={!!busy || name.length < 2} onClick={confirm}>
                  <Icon icon={CircleCheck} size={14} />{busy === "confirmar" ? "Guardando…" : `Confirmar y crear Rev ${proposal.target_revision}`}
                </Button>}
              {proposal && proposal.status !== "applied" && proposal.status !== "discarded" &&
                <Button variant="ghost" disabled={!!busy} onClick={discard}>Descartar</Button>}
              {proposal?.status === "applied" && <>
                <Button variant="secondary" onClick={() => changeBase(proposal.target_revision)}>
                  Seguir trabajando sobre Rev {proposal.target_revision}
                </Button>
                {!proposal.reverted_by && proposal.kind === "cambio_diseno" &&
                  <Button variant="ghost" disabled={!!busy} onClick={() => undo(proposal)}><Icon icon={Undo2} size={14} />Deshacer</Button>}
              </>}
              {proposal?.status === "stale" && <Button variant="secondary" onClick={() => { setProposal(null); void identity.refetch(); }}>
                <Icon icon={RotateCcw} size={14} />Empezar de nuevo sobre la última versión
              </Button>}
              {activeJob && <Button size="sm" variant="ghost" onClick={() => void cancelJob(activeJob)}>Cancelar</Button>}
            </div>
            <p role="status" className="text-xs text-muted">{hint(proposal, dirty, canValidate, name, reason, operations.length + partChanges.length)}</p>
          </div>

          <details className="rounded-[var(--radius-card)] border border-border p-3" data-testid="more-options">
            <summary className="cursor-pointer font-medium text-strong">Más opciones</summary>
            <div className="space-y-4 pt-3">
              <section className="space-y-1.5" aria-label="Plano GA nuevo">
                <h3 className="font-medium text-strong">Generar un plano nuevo</h3>
                <p className="text-xs text-muted">Crea un plano A3 (alzado, perfil y planta) de la Rev {proposal?.status === "applied" ? proposal.target_revision : label}. Solo incluye cambios ya confirmados.</p>
                <Button size="sm" variant="secondary" disabled={!!busy} onClick={makeDrawing}>{busy === "plano" ? "Generando plano…" : "Generar plano"}</Button>
                {drawing && <div className="flex flex-wrap gap-3 text-sm">{Object.entries(drawing.files).map(([key, file]) => <a key={key} className="text-accent-text underline" href={drawingDownloadUrl(file.url)} download>Descargar {key.toUpperCase()}</a>)}</div>}
              </section>
              <HistoryList proposals={history.data ?? []} busy={!!busy} onUndo={undo} />
              <section className="space-y-1.5 text-xs text-muted" aria-label="Ajustes avanzados">
                <h3 className="text-[13px] font-medium text-strong">Ajustes avanzados</h3>
                <p>{catalog.data.datum.elevation} Azimut: {catalog.data.datum.azimuth}</p>
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={useModel} onChange={(e) => setUseModel(e.target.checked)} />Usar Groq para interpretar peticiones sintéticas
                </label>
                {intent && <p>Interpretado por {intent.provider}. {intent.notice}</p>}
                <p>
                  ¿El plano original está mal leído? Eso se arregla en <Link className="text-accent-text underline" href="/modelo?vista=revision">Revisión</Link>,
                  no aquí: los cambios de diseño no corrigen la lectura.
                </p>
              </section>
              {steps.length > 0 && <section aria-label="Registro del proceso">
                <h3 className="text-[13px] font-medium text-strong">Registro del proceso</h3>
                <ol className="mt-1 space-y-0.5 text-[12px] text-muted">{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              </section>}
            </div>
          </details>
        </div>
      </Panel>
    </div>
  );
}

const FLOW = ["Describe el cambio", "Compruébalo", "Míralo en 3D", "Confírmalo"];

/** Los cuatro pasos del formulario, para saber siempre qué toca ahora. */
function FlowSteps({ done }: { done: boolean[] }) {
  const current = done.findIndex((d) => !d);
  return (
    <ol aria-label="Pasos para proponer un cambio" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
      {FLOW.map((label, i) => {
        const finished = done[i];
        const now = i === current;
        return (
          <li key={label} aria-current={now ? "step" : undefined} className="flex items-center gap-2">
            {i > 0 ? <span aria-hidden className="h-px w-5 bg-border" /> : null}
            <span className={`grid size-6 place-items-center rounded-full border text-[12px] font-semibold ${
              finished ? "border-approved text-approved" : now ? "border-accent bg-accent text-white" : "border-border text-muted"}`}>
              {finished ? <Icon icon={Check} size={13} /> : i + 1}
            </span>
            <span className={now ? "font-medium text-strong" : "text-muted"}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Qué falta para el siguiente paso, en una frase. */
function hint(proposal: Proposal | null, dirty: boolean, canValidate: boolean, name: string, reason: string, changes: number) {
  if (!proposal || dirty) {
    if (canValidate) return "Pulsa «Comprobar cambios» para revisar que todo encaja.";
    if (!changes) return "Describe el cambio o modifica alguna medida.";
    if (reason.trim().length < 3) return "Escribe el motivo del cambio para poder comprobarlo.";
    if (name.length < 2) return "Indica quién propone el cambio.";
    return "Tu borrador se guarda en este navegador hasta que lo confirmes.";
  }
  switch (proposal.status) {
    case "ready": return "Todo encaja. Pulsa «Ver resultado en 3D» para ver cómo quedaría.";
    case "previewed": return "Revisa el resultado en la vista 3D (Antes / Después). Si es correcto, confírmalo.";
    case "applied": return "Cambio guardado como borrador. Alguien tendrá que revisarlo y aprobarlo.";
    case "needs_clarification": return "Falta algún dato: revisa los avisos en amarillo.";
    case "invalid": return "Hay valores que no son posibles: revisa los avisos en rojo.";
    case "stale": return "El equipo ha cambiado mientras tanto. Empieza de nuevo sobre la última versión.";
    default: return "Tu borrador se guarda en este navegador hasta que lo confirmes.";
  }
}

function IssueLine({ issue }: { issue: Issue }) {
  const color = issue.severity === "error" ? "text-danger" : issue.severity === "clarification" ? "text-warning" : "text-muted";
  return <p role={issue.severity === "error" ? "alert" : undefined} className={`text-[12px] ${color}`}>{issue.message}</p>;
}

function Summary({ proposal, dirty }: { proposal: Proposal; dirty: boolean }) {
  const general = proposal.issues.filter((i) => !i.path && !i.operation_id);
  const regenerated = proposal.effects.filter((e) => e.geometry_changed).map((e) => e.part);
  return (
    <section className="space-y-2 rounded-[var(--radius-card)] border border-border bg-surface-sunken p-3" aria-label="Resumen de la propuesta">
      <p className="font-medium text-strong">
        {proposal.kind === "reversion" ? "Deshacer un cambio" : "Resumen del cambio"}: Rev {proposal.base.revision} → nueva Rev {proposal.target_revision}
      </p>
      {dirty && <p className="text-warning">Has modificado algo después de comprobarlo: vuelve a comprobarlo.</p>}
      {proposal.stale_reason && <p className="text-danger">{proposal.stale_reason}</p>}
      {proposal.operations.length > 0 && <table className="w-full text-[12px]">
        <thead><tr className="text-left text-muted"><th className="font-normal">Medida</th><th className="font-normal">Antes</th><th className="font-normal">Después</th></tr></thead>
        <tbody>{proposal.operations.map((op) => <tr key={op.id}>
          <td className="pr-2">{op.label}</td>
          <td className="pr-2">{formatValue(op.before.value, op.before.unit)}</td>
          <td className="font-medium text-strong">{formatValue(op.after.value, op.after.unit)}</td>
        </tr>)}</tbody>
      </table>}
      {proposal.derived.total_height && <p className="text-[12px]">
        Altura total: {formatValue(proposal.derived.total_height.before, "mm")} → {formatValue(proposal.derived.total_height.after, "mm")}
      </p>}
      {regenerated.length > 0 && <p className="text-[12px] text-muted">Piezas que se redibujan: {regenerated.join(", ")}</p>}
      {general.map((issue, i) => <IssueLine key={i} issue={issue} />)}
      {proposal.issues.filter((i) => i.severity === "error" && (i.path || i.operation_id)).map((issue, i) =>
        <IssueLine key={`e${i}`} issue={issue} />)}
      {proposal.status === "applied" && <p className="text-approved">
        Guardado como Rev {proposal.target_revision}. Queda en borrador (DRAFT) hasta que alguien lo revise y apruebe.
      </p>}
      {proposal.status === "applied" && proposal.applied_revision_id && <a className="text-[12px] text-accent-text underline"
        href={designReportUrl(proposal.applied_revision_id)} download>
        Descargar el plano con el cambio marcado (PDF)
      </a>}
      {proposal.preview && !dirty && <details className="text-[12px] text-muted">
        <summary className="cursor-pointer">Detalles técnicos</summary>
        <p>
          IFC temporal {proposal.preview.ifc_sha256.slice(0, 12)} · versión de datos {proposal.base.version} ·
          {" "}{proposal.preview.validation.express_rules ? "esquema y reglas EXPRESS" : "esquema"} ·
          {" "}{proposal.preview.delta.changes.length} cambios · {Math.round((proposal.preview.timings_ms.total_ms ?? 0) / 100) / 10} s
        </p>
      </details>}
    </section>
  );
}

function HistoryList({ proposals, busy, onUndo }: { proposals: Proposal[]; busy: boolean; onUndo(p: Proposal): void }) {
  const applied = proposals.filter((p) => p.status === "applied");
  if (applied.length === 0) return null;
  return (
    <section className="space-y-2" aria-label="Historial de órdenes">
      <h3 className="flex items-center gap-1.5 font-medium text-strong"><Icon icon={History} size={14} />Cambios confirmados</h3>
      {applied.map((p) => <div key={p.id} className="flex items-center justify-between gap-2 text-[12px]">
        <span>{p.kind === "reversion" ? "Deshacer" : "Cambio"} Rev {p.base.revision} → Rev {p.target_revision} · {p.actor}
          {p.reverted_by ? " · deshecho" : ""}</span>
        {!p.reverted_by && p.kind === "cambio_diseno" &&
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onUndo(p)}>Deshacer</Button>}
      </div>)}
    </section>
  );
}

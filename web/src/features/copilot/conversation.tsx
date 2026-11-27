"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Box, ChevronDown, FilePenLine, GitCompareArrows, LoaderCircle, Ruler, Send } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { CopilotMark } from "@/components/brand/copilot-mark";
import { Badge, Button, Code, Icon } from "@/components/ui/primitives";
import { changesHref } from "@/features/changes/sections";
import { getCatalog, interpretRequest, type IntentDraft } from "@/features/design-edit/api";
import { draftKey, useDraftCache } from "@/features/design-edit/draft-store";
import { clarifiedText, draftsFromOperations, optionPhrase } from "@/features/design-edit/form";
import { ApiError, askCopilot, copilotScopes, prepareProcessDraft, type CopilotAnswer, type CopilotScope, type ProcessDraft } from "@/lib/api/client";
import { apiURL } from "@/lib/api/config";
import { fieldLabel } from "@/lib/field-labels";
import { formatValue } from "@/lib/format";
import type { RevisionId } from "@/lib/mock/api";
import type { ReviewField } from "@/lib/mock/fields";
import { revisionIdentity, useEquipment } from "@/stores/equipment";
import { useUi } from "@/stores/ui";
import { useProcessCopilotDraft, useQuestion } from "./draft";
import { DictationControls, useCopilotDictation } from "./dictation";
import { isChangeRequest, spokenOption, speakableOption } from "./intent";
import { ReadAnswer } from "./voice";
import { VoiceConversation, type VoiceDesignReply } from "./voice-conversation";

const scopeKey = (item: CopilotScope) => `${item.kind}:${item.id}`;
const control = "w-full rounded-[var(--radius-control)] border border-border bg-surface-sunken px-3 py-2 text-text";

export function CopilotConversation({ revision, field }: { revision: RevisionId; field?: ReviewField }) {
  const pathname = usePathname();
  const processId = pathname.match(/^\/proyectos-proceso\/([^/]+)$/)?.[1];
  const contexts = useQuery({ queryKey: ["copilot-scopes"], queryFn: ({signal}) => copilotScopes(signal), staleTime: 30_000 });
  const items = contexts.data ?? [];
  const active = useEquipment((s) => s.active);
  const [selection, setSelection] = useState<{ screen: string; scope: string } | null>(null);
  const screen = JSON.stringify([pathname, active?.project_id, active?.tag, revision]);
  const defaultScope = processId
    ? items.find(item => item.kind === "process" && item.id === processId)
    : items.find(item => item.kind === "revision" && (active
      ? item.id === revisionIdentity(revision, active)
      : item.project === "DEMO-PLANT" && item.tag === "V-101" && item.revision === revision));
  const scope = (selection?.screen === screen
    ? items.find(item => scopeKey(item) === selection.scope)
    : undefined) ?? defaultScope ?? items[0];
  const focused = scope?.kind === "revision" && scope.id === defaultScope?.id ? field : undefined;

  if (contexts.isError) return <div role="alert" className="space-y-3 p-4 text-sm">
    <p>{contexts.error.message}</p>
    <Button size="sm" onClick={() => void contexts.refetch()}>Volver a cargar proyectos</Button>
  </div>;
  if (!scope) return <p role="status" className="flex items-center gap-2 p-4 text-sm text-muted">
    {contexts.isPending ? <><Icon icon={LoaderCircle} className="motion-safe:animate-spin" /> Cargando la revisión…</>
      : "Selecciona un equipo y una revisión en la barra superior."}
  </p>;

  return <ScopedConversation key={`${scopeKey(scope)}:${focused?.path ?? ""}`}
    scope={scope} field={focused} contexts={items} chooseScope={key => setSelection({ screen, scope: key })} />;
}

type DraftReply = { kind: "revision"; draft: IntentDraft } | { kind: "process"; draft: ProcessDraft };

function ScopedConversation({ scope, field, contexts, chooseScope }: {
  scope: CopilotScope;
  field?: ReviewField;
  contexts: CopilotScope[];
  chooseScope: (key: string) => void;
}) {
  const [question, setQuestion] = useQuestion(scopeKey(scope), field?.path);
  const [voiceMode, setVoiceMode] = useState(false);
  const [processRevision, setProcessRevision] = useState<"A" | "B">("A");
  const [turns, setTurns] = useState<{ text: string; answer: CopilotAnswer }[]>([]);
  // «Ese valor» en una orden es el campo seleccionado o, si no hay, el último que citó el Copiloto.
  const lastPath = [...turns].reverse()
    .flatMap(turn => turn.answer.abstained ? [] : turn.answer.citations)
    .find(citation => citation.kind === "field" && citation.path)?.path ?? undefined;
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const feed = useRef<HTMLDivElement>(null);
  const latest = useRef<HTMLDivElement>(null);
  const dictatingDesign = useRef(false);
  const pendingOrder = useRef<{ text: string; options: string[] } | null>(null);
  const models = useQuery({
    queryKey: ["ajustes-modelos"],
    queryFn: async ({ signal }) => {
      const response = await fetch(apiURL("/ajustes/modelos"), { signal });
      if (!response.ok) throw new Error("No se pudieron consultar los modelos disponibles.");
      return await response.json() as { actual: string; opciones: { id: string; disponible: boolean }[] };
    },
    staleTime: 30_000,
  });
  const noCredentials = models.data?.opciones
    .filter(option => option.id === "azure" || option.id === "groq")
    .every(option => !option.disponible);
  const appendDictation = (text: string) => {
    const current = input.current?.value.trim() ?? "";
    const composed = [current, text].filter(Boolean).join(" ");
    if (composed.length > 2000) return false;
    updateQuestion(composed);
    input.current?.focus();
    // Una orden dictada se manda sin pulsar «Enviar cambio»: se prepara y se abre el editor.
    if (canPrepare && isChangeRequest(composed)) prepareText(composed);
    return true;
  };
  const queryClient = useQueryClient();
  const answer = useMutation({
    meta: { readOnly: true },
    mutationFn: ({ text, signal }: { text: string; signal: AbortSignal }) => askCopilot(scope, text, field?.path, signal, processRevision),
    onSuccess: (reply, { text }) => {
      setTurns(history => [...history, { text, answer: reply }]);
      setQuestion("");
    },
    onError: error => {
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["copilot-scopes"] });
      }
    },
  });
  const design = useMutation({
    async mutationFn(text: string): Promise<DraftReply> {
      if (scope.kind === "revision") return {kind: "revision", draft: await interpretRequest(scope.id, text, field?.elementId ?? null, true, field?.path ?? lastPath)};
      return {kind: "process", draft: await prepareProcessDraft(scope.id, text)};
    },
  });
  const router = useRouter();
  const close = useUi(state => state.setCopilotOpen);
  const handoff = useMutation({
    // La orden ya está en el editor: la caja queda vacía para el siguiente dictado.
    onSuccess: () => setQuestion(""),
    async mutationFn(result: DraftReply) {
      if (result.kind === "process") {
        useProcessCopilotDraft.getState().setPending({project: scope.id, revision: processRevision, adjustments: result.draft.adjustments});
        close(false);
        router.push(`/proyectos-proceso/${encodeURIComponent(scope.id)}`);
        return;
      }
      if (scope.kind !== "revision") return;
      const draft = result.draft;
      const catalog = await getCatalog(scope.id);
      if (catalog.version !== draft.version) throw new Error("La revisión ha cambiado. Vuelve a preparar el borrador.");
      const cache = useDraftCache.getState();
      const nav = draftKey("navigation", "", "");
      const key = draftKey(scope.project, scope.tag, scope.revision);
      cache.update(nav, "projectId", scope.project);
      cache.update(nav, "tag", scope.tag);
      cache.update(draftKey(scope.project, scope.tag, "selection"), "label", scope.revision);
      cache.update(key, "request", draft.request_text);
      cache.update(key, "intent", draft);
      cache.update(key, "drafts", existing => ({ ...existing, ...draftsFromOperations(draft.operations, catalog.targets) }));
      if (draft.part_changes.length) cache.update(key, "partChanges", existing => [
        ...existing.filter(old => !draft.part_changes.some(item => item.collection === old.collection && item.id === old.id)),
        ...draft.part_changes,
      ]);
      if (draft.detail_level) cache.update(key, "detailLevel", draft.detail_level ?? undefined);
      cache.update(key, "reason", existing => existing || `Petición: «${draft.request_text.slice(0,200)}»`);
      cache.update(key, "autoCheck", true);
      close(false);
      router.push(changesHref("proponer"));
    },
  });
  useEffect(() => () => controller.current?.abort(), []);
  const canPrepare = scope.kind === "revision" || scope.kind === "process";
  function updateQuestion(text: string) {
    setQuestion(text);
    if (design.data || design.error) {
      design.reset();
      handoff.reset();
    }
  }
  /** Con `go`, un borrador sin dudas abre el editor directamente: la orden se ejecuta sin más clics. */
  function prepareText(text: string, go = true) {
    answer.reset();
    design.reset();
    handoff.reset();
    design.mutate(text, { onSuccess: data => { if (go && draftSummary(data).ready) handoff.mutate(data); } });
  }
  function prepareDictatedDesign(text: string) {
    if (!canPrepare || text.length > 2000) return false;
    setQuestion(text);
    prepareText(text);
    return true;
  }
  /** En voz no hay tarjeta de borrador: se abre el editor o se pregunta lo que falta, en voz alta. */
  async function designFromVoice(said: string): Promise<VoiceDesignReply> {
    answer.reset();
    handoff.reset();
    // La respuesta a una aclaración («a 650 milímetros») completa la orden pendiente.
    // «Al primero», «lado positivo» o «lado guión y» eligen una de las opciones que se leyeron.
    const pending = pendingOrder.current;
    const text = pending && !isChangeRequest(said)
      ? clarifiedText(pending.text, spokenOption(said, pending.options) ?? said) : said;
    pendingOrder.current = null;
    const data = await design.mutateAsync(text);
    const summary = draftSummary(data);
    if (summary.ready) {
      await handoff.mutateAsync(data);
      return { reply: `Preparo ${summary.spoken}. Te llevo al editor para comprobarlo y confirmarlo.`, leaving: true };
    }
    const options = data.kind === "revision" ? data.draft.clarifications.flatMap(item => item.options ?? []).slice(0, 4) : [];
    const reply = (summary.questions.join(" ") || "No he podido preparar ese cambio. Dime el elemento, la magnitud y el valor final.")
      + (options.length ? ` Di ${options.map(option => `«${speakableOption(optionPhrase(option))}»`).join(" o ")}.` : "");
    pendingOrder.current = { text, options };
    setTurns(history => [...history, { text: said, answer: localAnswer(reply, scope) }]);
    return { reply, leaving: false };
  }
  const dictation = useCopilotDictation(scope, text => dictatingDesign.current
    ? prepareDictatedDesign(text) : appendDictation(text));
  const busy = answer.isPending || design.isPending || handoff.isPending;
  const composing = dictation.phase !== "idle";
  const submit = () => {
    if (!question.trim() || busy || composing) return;
    if (canPrepare && isChangeRequest(question)) {
      prepareText(question.trim());
      return;
    }
    design.reset(); handoff.reset();
    controller.current?.abort();
    controller.current = new AbortController();
    answer.mutate({ text: question.trim(), signal: controller.current.signal });
  };
  const prepare = () => {
    if (!question.trim() || busy || composing) return;
    prepareText(question.trim(), false);
  };
  const suggestions = scope.kind === "catalogue" ? ["¿Qué archivos hay publicados?"] : scope.kind === "project" ? ["¿Qué equipos y revisiones contiene el proyecto?"] : scope.kind === "process"
    ? ["Resume la planta y su inventario", "¿Qué cambia respecto a la revisión A?"]
    : field ? ["¿De dónde sale el valor seleccionado?", "¿Qué debo comprobar antes de aceptarlo?"]
      : ["¿Cuál es el diámetro?", "¿Qué cambia respecto a la revisión anterior?"];
  const error = answer.error ?? design.error ?? handoff.error;
  const pendingText = answer.isPending || answer.isError ? answer.variables?.text : undefined;
  const draftText = design.isPending || design.data || design.isError ? design.variables : undefined;
  const currentText = pendingText ?? draftText;
  const hasCurrent = Boolean(currentText || busy || error);
  useEffect(() => {
    const viewport = feed.current;
    const item = latest.current;
    if (viewport && item) {
      viewport.scrollTop += item.getBoundingClientRect().top - viewport.getBoundingClientRect().top - 12;
    }
  }, [turns.length, pendingText, draftText, design.data, busy, error, voiceMode]);

  return <div className="flex min-h-0 flex-1 flex-col text-sm">
    <div className="shrink-0 space-y-2 border-b border-border px-4 py-2.5">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <p data-testid="copilot-scope" className="flex min-w-0 items-start gap-1.5 font-medium text-text">
          <Icon icon={Box} size={15} className="mt-0.5 text-accent-text" />
          <span className="min-w-0 [overflow-wrap:anywhere]">{scope.project} · {scope.label}</span>
        </p>
        {noCredentials ? <details className="relative text-xs text-muted">
          <summary className="cursor-pointer list-none rounded-md bg-accent-soft px-2 py-1 font-medium text-accent-text">Reglas locales</summary>
          <p className="mt-1">Sin credenciales de proveedores. El Copiloto consulta las fuentes con reglas locales.</p>
        </details> : null}
      </div>
      {contexts.length > 1 ? <details className="text-xs text-muted">
        <summary className="cursor-pointer">Cambiar contexto</summary>
        <select aria-label="Contexto del Copiloto" className={control} value={scopeKey(scope)}
          disabled={busy || composing || voiceMode} onChange={event => chooseScope(event.target.value)}>
          {contexts.map(context => <option key={scopeKey(context)} value={scopeKey(context)}>
            {context.project} · {context.label}
          </option>)}
        </select>
      </details> : null}
      {scope.kind === "process" ? <label className="flex items-center gap-2 text-xs">
        <span className="font-medium text-muted">Revisión del complejo</span>
      <select className={`${control} !w-auto !px-2 !py-1`} value={processRevision} disabled={busy || composing || voiceMode} onChange={event => {
        setProcessRevision(event.target.value === "B" ? "B" : "A");
        answer.reset();
        design.reset();
        handoff.reset();
        setTurns([]);
      }}><option value="A">Rev. A</option><option value="B">Rev. B</option></select>
      </label> : null}
      {field ? <dl className="flex flex-wrap items-baseline gap-x-1.5 text-xs">
        <dt className="text-muted">{field.label}</dt><dd className="font-semibold text-strong">{formatValue(field.correctedValue ?? field.value, field.unit)}</dd>
      </dl> : null}
    </div>

    <div ref={feed} className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4" data-testid="copilot-thread">
      {voiceMode ? <VoiceConversation scope={scope} path={field?.path} revision={processRevision}
        onDesign={canPrepare ? designFromVoice : undefined} onClose={() => setVoiceMode(false)}
        onTurn={(text, reply) => setTurns(history => [...history, { text, answer: reply }])} turnCount={turns.length}>
        {turns.map(({ text, answer: reply }, index) => <div key={index} className="space-y-3">
          <UserMessage text={text} />
          <AnswerView answer={reply} />
        </div>)}
      </VoiceConversation> : <>
        {!turns.length && !pendingText && !draftText && !busy ? (
          <div className="space-y-3 pt-1">
            <h3 className="text-[16px] font-semibold text-strong">¿Qué necesitas revisar?</h3>
            <div className="grid gap-1.5">
              {suggestions.map((text, index) => (
                <button key={text} type="button" onClick={() => { updateQuestion(text); input.current?.focus(); }}
                  className="flex items-center gap-2.5 rounded-xl border border-border bg-surface-raised px-3 py-2.5 text-left leading-snug text-text transition-colors hover:border-accent/50 hover:bg-accent-soft">
                  <Icon icon={index === 0 ? Ruler : GitCompareArrows} size={16} className="text-accent-text" />
                  <span className="flex-1">{text}</span>
                  <Icon icon={ArrowUpRight} size={14} className="text-muted" />
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {turns.map(({ text, answer: reply }, index) => (
          <div key={index} ref={index === turns.length - 1 && !hasCurrent ? latest : null} className="space-y-3">
            <UserMessage text={text} />
            <AnswerView answer={reply} />
          </div>
        ))}
        {hasCurrent ? <div ref={latest} className="space-y-3">
          {currentText ? <UserMessage text={currentText} /> : null}
          {busy ? <p role="status" className="flex items-center gap-2 text-muted">
            <Icon icon={LoaderCircle} size={15} className="motion-safe:animate-spin text-accent-text" />
            {design.isPending ? "Preparando el borrador…" : handoff.isPending ? "Abriendo el editor…" : "Consultando las fuentes…"}
          </p> : null}
          {error ? <p role="alert" className="rounded-xl border border-warning-border bg-warning-bg p-3 text-warning">
            {error.name === "AbortError" ? "Consulta cancelada." : error.message}
          </p> : null}
          {design.data ? <DraftView result={design.data} apply={() => handoff.mutate(design.data)}
            clarify={option => {
              const text = clarifiedText(design.variables ?? question, option);
              setQuestion(text);
              prepareText(text);
            }} busy={busy} /> : null}
        </div> : null}
      </>}
    </div>
    {!voiceMode ? <form onSubmit={event => { event.preventDefault(); submit(); }} className="shrink-0 border-t border-border bg-surface-raised p-2.5">
      <div className="rounded-xl border border-border-strong bg-surface px-2.5 pt-2 focus-within:border-accent/70">
        <label htmlFor="copilot-question" className="sr-only">Tu mensaje</label>
        <textarea id="copilot-question" ref={input} value={question} disabled={busy || composing}
          onChange={event => updateQuestion(event.target.value)}
          onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          maxLength={2000} rows={2} placeholder={scope.kind === "process" ? "Pregunta por el complejo o describe un cambio" : "Pregunta por una cota o describe un cambio"}
          className="block w-full resize-none bg-transparent px-0.5 py-1 leading-snug text-text outline-none placeholder:text-muted disabled:opacity-70" />
        <div className="flex flex-wrap items-center justify-between gap-x-1.5 gap-y-1 border-t border-border py-1.5">
          <DictationControls dictation={dictation} disabled={busy}
            onStart={() => { dictatingDesign.current = false; void dictation.start(); }}
            onDesign={canPrepare ? () => { dictatingDesign.current = true; void dictation.start(); } : undefined}
            onConversation={() => setVoiceMode(true)} />
          <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
            {answer.isPending ? <Button type="button" size="sm" onClick={() => controller.current?.abort()}>Cancelar</Button> : <>
              {canPrepare ? <Button type="button" size="sm" variant="ghost" disabled={busy || composing || !question.trim()} onClick={prepare}>
                <Icon icon={FilePenLine} size={14} /> Preparar cambio
              </Button> : null}
              <Button type="submit" size="sm" variant="primary" disabled={busy || composing || !question.trim()}>
                <Icon icon={Send} size={14} /> {canPrepare && isChangeRequest(question) ? "Enviar cambio" : "Preguntar"}
              </Button>
            </>}
          </div>
        </div>
      </div>
    </form> : null}
  </div>;
}

function UserMessage({ text }: { text: string }) {
  return <p className="ml-auto w-fit max-w-[88%] rounded-xl rounded-tr-sm bg-accent-soft px-3 py-2.5 leading-relaxed whitespace-pre-wrap text-text [overflow-wrap:anywhere]">
    <span className="sr-only">Tú: </span>{text}
  </p>;
}

/** Lo que el borrador cambia y lo que falta por aclarar, para la tarjeta y para la voz. */
function draftSummary(result: DraftReply) {
  const items = result.kind === "revision"
    ? [...result.draft.operations.map(item => `${item.target} · ${item.value} ${item.unit ?? ""}`.trim()),
      ...result.draft.part_changes.map(item => `${item.action === "add" ? "Añadir" : "Eliminar"} ${item.id}`)]
    : result.draft.adjustments.map(item => `${item.tag} · ${item.field} · ${item.value} ${item.field === "dn" ? "mm" : "m"}`);
  const questions = result.kind === "revision" ? [...result.draft.clarifications.map(item => item.question), ...result.draft.rejected] : result.draft.questions;
  // Las operaciones derivadas (posición y dirección de una boca) no se leen en voz alta.
  const spokenItems = result.kind === "revision"
    ? [...result.draft.operations.filter(item => /^op-\d+$/.test(item.id))
      .map(item => `${fieldLabel(item.target).replace(" · ", " ").toLowerCase()} a ${item.value} ${unitWord(item.unit)}`.trim()),
      ...result.draft.part_changes.map(item => `${item.action === "add" ? "añadir" : "eliminar"} ${item.id}`)]
    : items;
  return { items, questions, ready: items.length > 0 && !questions.length, spoken: spokenItems.join(", ") || "el cambio" };
}

function unitWord(unit?: string | null) {
  return unit === "mm" ? "milímetros" : unit === "deg" ? "grados" : unit === "m" ? "metros" : unit ?? "";
}

function localAnswer(text: string, scope: CopilotScope): CopilotAnswer {
  return {
    mode: "conversation", abstained: false, statements: [{ text, citations: [] }], proposals: [], citations: [],
    read_only: true, model: "intérprete de órdenes", revision_id: scope.id, revision_version: 0,
    input_sha256: "", prompt_sha256: "", tools_used: [],
    run: { strategy: "copilot-design-intent", providers: [], seconds: 0, external_calls: 0 },
  };
}

function DraftView({ result, apply, clarify, busy }: {
  result: DraftReply; apply: () => void; clarify: (option: string) => void; busy: boolean;
}) {
  const { items, questions } = draftSummary(result);
  const sideOptions = result.kind === "revision" && result.draft.clarifications.length === 1
    ? (result.draft.clarifications[0]?.options ?? []).filter(option => /^lado [+-]Y$/.test(option))
    : [];
  return <section className="space-y-2 rounded-xl border border-accent/30 bg-accent-soft p-3 [overflow-wrap:anywhere]" aria-live="polite">
    <h3 className="flex items-center gap-2 font-semibold text-strong"><Icon icon={FilePenLine} className="text-accent-text" /> Borrador del Copiloto</h3>
    {items.length > 0 ? <ul className="list-disc pl-4">{items.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}
    {questions.map((item, index) => <p key={index} className="text-warning">{item}</p>)}
    {sideOptions.map(option => (
      <Button key={option} type="button" size="sm" disabled={busy} onClick={() => clarify(option)}>
        {option === "lado +Y" ? "Lado +Y" : "Lado −Y"}
      </Button>
    ))}
    {items.length > 0 && !questions.length ? <Button type="button" size="sm" variant="primary" disabled={busy} onClick={apply}>Abrir en el editor</Button> : null}
  </section>;
}

function AnswerView({ answer }: { answer: CopilotAnswer }) {
  const citations = answer.citations ?? [];
  const index = new Map(citations.map((citation, i) => [citation.id, i + 1]));
  const citationPrefix = useId();
  const spoken = answer.abstained ? "" : answer.statements.map(statement => statement.text).join("\n");
  function openCitation(number: number) {
    const detail = document.getElementById(`${citationPrefix}-${number}`);
    if (!(detail instanceof HTMLDetailsElement)) return;
    detail.open = true;
    detail.querySelector("summary")?.focus({ preventScroll: true });
    detail.scrollIntoView({ block: "nearest" });
  }
  function references(ids: string[]) {
    return ids.map(id => {
      const number = index.get(id);
      return number ? <button key={id} type="button" onClick={() => openCitation(number)}
        aria-label={`Abrir fuente ${number}`}
        className="ml-1 inline-flex min-w-5 items-center justify-center rounded bg-accent-soft px-1 align-baseline text-[11px] font-semibold text-accent-text hover:underline">
        {number}
      </button> : null;
    });
  }
  return <article className="space-y-2.5 [overflow-wrap:anywhere]" aria-label="Respuesta del Copiloto" data-testid="copilot-answer">
    <div className="flex items-center gap-2">
      <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent-soft"><CopilotMark className="size-4" /></span>
      <h3 className="text-xs font-semibold text-strong">Copiloto</h3>
      <div className="ml-auto"><ReadAnswer key={spoken} text={spoken} /></div>
    </div>
    {answer.abstained ? <div className="rounded-xl border border-warning-border bg-warning-bg p-3 text-warning" aria-live="polite">
      <p className="font-medium">Sin respuesta respaldada</p>
      <p className="mt-1">{answer.reason ?? "No hay evidencia suficiente para responder."}</p>
    </div> : <>
      <div className="space-y-2 leading-relaxed text-text" aria-live="polite">
        {answer.statements.map((statement, i) => <p key={i}>
          {statement.text}{references(statement.citations)}
        </p>)}
      </div>
      {answer.proposals.length ? <section><h4 className="mb-1.5 text-xs font-semibold text-strong">Comprobaciones propuestas</h4>
        <ul className="list-disc space-y-2 pl-4 text-muted">{answer.proposals.map((proposal, i) => <li key={i}>
          {proposal.text}{references(proposal.citations)}
        </li>)}</ul>
      </section> : null}
      {citations.length ? <section><h4 className="mb-1.5 text-xs font-semibold text-strong">Fuentes leídas · {citations.length}</h4>
        <div className="space-y-1.5">{citations.map((citation, i) => <details id={`${citationPrefix}-${i + 1}`} key={citation.id} className="group rounded-xl border border-border bg-surface-raised px-2.5 py-2">
          <summary className="flex cursor-pointer list-none items-start gap-2 leading-snug text-text">
            <span className="rounded bg-accent-soft px-1.5 py-0.5 text-[11px] font-semibold text-accent-text">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium">{citation.title}</span>
              {citation.page || citation.sheet ? <span className="mt-0.5 block text-xs text-muted">
                {citation.page ? `Página ${citation.page}` : [citation.sheet, citation.cell].filter(Boolean).join(" · ")}
              </span> : null}
            </span>
            <Icon icon={ChevronDown} size={15} className="text-muted group-open:rotate-180" />
          </summary>
          <div className="mt-2 space-y-2 text-xs leading-relaxed text-muted">
            <blockquote className="whitespace-pre-wrap border-l-2 border-accent pl-2">{citation.excerpt}</blockquote>
            {citation.original_verified ? <Badge tone="live">Original verificado por SHA-256</Badge> : null}
            {citation.sha256 ? <p>SHA-256 <Code>{citation.sha256.slice(0, 12)}…</Code></p> : null}
            {citation.bbox ? <p>Región: {citation.bbox.map(x => x.toFixed(3)).join(", ")}</p> : null}
          </div>
        </details>)}</div>
      </section> : null}
    </>}
    <p className="text-xs text-muted">
      {answer.mode === "conversation" ? "Conversación sin fuentes: no afirma datos del equipo · " : ""}
      {answer.model} · {answer.run.seconds.toFixed(2)} s
    </p>
  </article>;
}

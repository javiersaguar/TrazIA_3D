"use client";

import { usePreferences } from "@/stores/preferences";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { ArrowRight, FileText, Upload, X } from "lucide-react";
import { Button, Icon, Panel } from "@/components/ui/primitives";
import { matchEquipment, sameRevision, type UploadedDocument } from "@/lib/api/client";
import { apiEnabled } from "@/lib/api/config";
import { tagKey } from "@/features/documents/dataset-documents";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { usePipeline } from "@/stores/pipeline";
import { PROFILES, type Strategy } from "./graph-model";
import { fichaKey, NEW_FICHA, planUpload, sha256, type UploadPlan } from "./upload-target";

const field = "w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 py-2 text-sm";
const uploadField = "min-h-11 w-full min-w-0 rounded-lg border border-border bg-surface px-3 py-2 text-base text-text placeholder:text-muted sm:text-sm";
const maxFileCount = 30;
const maxFileBytes = 25 * 1024 * 1024;
const formats = /\.(pdf|xlsx|png|jpe?g)$/i;
const pdf = /\.pdf$/i;
const convention = /^(?:GAD|GA|HDM|VESOR|ESTRUCTURA)_(.+?)(?:_rev([^_.]+))?\.[^.]+$/i;

const mechanicalName = /^((?:BOMBA|COMPRESOR)-GA\d+)-Rev([^.]+)\.pdf$/i;

function suggestions(files: File[]) {
  const names = files.flatMap(file => {
    const machine = file.name.match(mechanicalName);
    if (machine?.[1]) return [{ tag: machine[1].toUpperCase(), revision: machine[2] }];
    const match = file.name.match(convention);
    return match ? [{ tag: match[1], revision: match[2] }] : [];
  });
  const tags = [...new Set(names.map(name => name.tag))];
  const revisions = [...new Set(names.flatMap(name => name.revision ? [name.revision] : []))];
  return { tag: tags.length === 1 ? tags[0] ?? "" : "", revision: revisions.length === 1 ? revisions[0] ?? "" : "",
    mixed: tags.length > 1 || revisions.length > 1 };
}

const fileKey = (file: File) => JSON.stringify([file.name, file.size, file.lastModified]);
const fileSize = (size: number) => size >= 1024 ** 2
  ? `${formatNumber(size / 1024 ** 2)} MiB` : `${formatNumber(size / 1024)} KiB`;

type IntakeProps = { strategy: Strategy; setStrategy: (value: Strategy) => void; onSubmitted?: never; onCancel?: never }
  | { strategy?: never; setStrategy?: never; onSubmitted: (id: string) => void; onCancel?: () => void };

export function IntakeForm({ strategy, setStrategy, onSubmitted, onCancel }: IntakeProps) {
  const defaultStrategy = usePreferences((s) => s.strategy);
  const simple = Boolean(onSubmitted);
  const running = usePipeline(state => state.running);
  const uploadError = usePipeline(state => state.jobId ? null : state.error);
  const uploaded = usePipeline(state => state.jobId ? state.inputFiles : null);
  const submit = usePipeline(state => state.submit);
  const [files, setFiles] = useState<File[]>([]);
  const [tag, setTag] = useState("");
  const [revision, setRevision] = useState("");
  const [equipmentId, setEquipmentId] = useState("");
  const [project, setProject] = useState("ENSAYO");
  const [choice, setChoice] = useState("");
  const [hashes, setHashes] = useState<string[] | null>(null);
  const [mixed, setMixed] = useState(false);
  const [error, setError] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [discrepancy, setDiscrepancy] = useState<{ input: string; selected: string; files: UploadedDocument[] } | null>(null);
  const dragDepth = useRef(0);
  const attempt = useRef<{ key: string; input: string } | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const code = tagKey(tag);
  const matches = useQuery({
    queryKey: ["equipment-match", code],
    queryFn: () => matchEquipment(tag),
    enabled: simple && apiEnabled && code.length >= 2,
  });
  const plan: UploadPlan = simple ? planUpload(matches.data ?? [], choice, revision, hashes) : { kind: "new" };
  const target = "ficha" in plan ? plan.ficha : null;


  const hashing = useRef(0);
  function replaceFiles(next: File[]) {
    const previous = suggestions(files);
    const detected = suggestions(next);
    setFiles(next);
    const run = ++hashing.current;
    setHashes(null);
    if (simple && next.length) {
      void Promise.all(next.map(sha256)).then(result => { if (hashing.current === run) setHashes(result); }).catch(() => undefined);
    }
    if (!simple || !tag || tag === previous.tag) setTag(detected.tag);
    if (!simple || !revision || revision === previous.revision) setRevision(detected.revision);
    setEquipmentId("");
    setMixed(detected.mixed);
    setError("");
    setDiscrepancy(null);
    setAttempted(false);
    attempt.current = null;
  }

  function choose(list: File[]) {
    if (!simple) {
      replaceFiles(list);
      return;
    }
    if (!list.length) return;
    const next = [...new Map([...files, ...list].map(file => [fileKey(file), file])).values()];
    if (next.length > maxFileCount || list.some(file => !pdf.test(file.name) || !file.size || file.size > maxFileBytes)) {
      setError("Elige hasta 30 archivos PDF de entre 1 byte y 25 MiB cada uno.");
      return;
    }
    replaceFiles(next);
  }

  async function process(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running) return;
    const data = new FormData(event.currentTarget);
    if (plan.kind === "choose") {
      setError("El código está en varias fichas. Elige a cuál se añade esta versión.");
      return;
    }
    if (plan.kind === "duplicate") {
      setError(`Estos archivos ya están en la Rev. ${plan.revision} de ${plan.ficha.tag}; no se duplican.`);
      return;
    }
    const id = target?.equipment_id ?? (equipmentId.trim() || tag.trim());
    const selectedRevision = revision.trim();
    const destination = "revision" in plan ? plan.revision : selectedRevision;
    if (mixed || !files.length || files.length > maxFileCount || files.some(file =>
      !(simple ? pdf : formats).test(file.name) || !file.size || file.size > maxFileBytes)) {
      setError(mixed ? "Se han detectado varios equipos o revisiones en los nombres. Selecciona solo los documentos de una revisión."
        : `Selecciona entre 1 y 30 archivos ${simple ? "PDF" : "PDF, XLSX, PNG o JPEG"}, de hasta 25 MiB cada uno.`);
      return;
    }
    if (!/^[A-Za-z0-9_-]+$/.test(id) || !destination || /[:/\\\r\n]/.test(destination) || !tag.trim()) {
      setError(simple ? "Usa letras, números, guiones o guiones bajos para el equipo, y una versión sin barras ni dos puntos."
        : "Indica el tag, un ID estable con letras, números, guiones o guiones bajos y una revisión sin barras ni dos puntos.");
      return;
    }
    const mechanical = files.some(file => mechanicalName.test(file.name));
    const input = {
      project_id: (target?.project_id ?? project).trim(), equipment_id: id,
      tag: tag.trim(), revision: destination, strategy: simple && mechanical ? "lectura" as const : strategy ?? defaultStrategy,
      dataset: data.get("dataset") === "real" ? "real" as const : "synthetic" as const,
    };
    const serialized = JSON.stringify({ ...input, selectedRevision });
    if (attempt.current?.input !== serialized) attempt.current = { key: crypto.randomUUID(), input: serialized };
    setError("");
    setAttempted(true);
    const result = await submit(
      { input, files, selectedRevision, confirmedRevision: discrepancy?.input === serialized },
      attempt.current.key,
    );
    if (result && "mismatches" in result) {
      setDiscrepancy({ input: serialized, selected: selectedRevision, files: result.mismatches });
    } else if (result?.jobId) {
      attempt.current = null;
      if (picker.current) picker.current.value = "";
      setFiles([]);
      setDiscrepancy(null);
      onSubmitted?.(result.jobId);
    }
  }

  const checkedMismatch = discrepancy?.selected === revision.trim() ? discrepancy : null;
  const nameRevision = suggestions(files).revision;
  const nameMismatch = revision.trim() && nameRevision && !sameRevision(nameRevision, revision);
  const revisionNotice = checkedMismatch || nameMismatch ? (
    <div role="status" className="rounded-lg border border-warning/40 bg-warning-bg px-3 py-2 text-sm text-warning">
      <p className="font-semibold">Revisión elegida «{revision.trim()}»</p>
      {checkedMismatch ? <ul className="mt-1 space-y-1">
        {checkedMismatch.files.map(file => {
          const detected = file.revision_detection;
          const drawing = detected?.drawing_revision;
          return <li key={file.id} className="[overflow-wrap:anywhere]">
            {file.filename}{detected?.filename_revision ? ` · Nombre del archivo «${detected.filename_revision}»` : ""}
            {drawing ? ` · Cajetín «${drawing.value}», pág. ${drawing.page} (${drawing.locator})` : " · Revisión del plano indeterminada"}
          </li>;
        })}
      </ul> : <p>El nombre del archivo indica «{nameRevision}».</p>}
    </div>
  ) : null;

  if (simple) {
    const feedback = error || (!apiEnabled ? "Conecta la API local para poder subir planos."
      : mixed ? "Elige PDF de un solo equipo y una sola versión."
      : attempted && uploadError ? `No se pudo iniciar el proceso. ${uploadError}` : "");
    const form = (
      <form aria-label="Subir planos" aria-busy={running} onSubmit={process} className="flex min-h-0 flex-col">
        <fieldset disabled={running} className="min-w-0 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6">
          <div data-testid="plan-dropzone" data-dragging={dragging || undefined}
            className={cn("flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-4 text-center transition-colors",
              dragging ? "border-accent bg-accent-soft ring-2 ring-accent/20" : "border-border-strong bg-surface-sunken/75")}
            onDragEnter={event => {
              if (running || !event.dataTransfer.types.includes("Files")) return;
              event.preventDefault();
              dragDepth.current += 1;
              setDragging(true);
            }}
            onDragOver={event => {
              if (!event.dataTransfer.types.includes("Files")) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = running ? "none" : "copy";
            }}
            onDragLeave={() => {
              dragDepth.current = Math.max(0, dragDepth.current - 1);
              if (dragDepth.current === 0) setDragging(false);
            }}
            onDrop={event => {
              event.preventDefault();
              dragDepth.current = 0;
              setDragging(false);
              if (!running) choose(Array.from(event.dataTransfer.files));
            }}>
            <span className="grid size-9 place-items-center rounded-lg bg-accent-soft text-accent-text"><Icon icon={Upload} size={19} /></span>
            <div>
              <p className="text-base font-semibold text-strong">{dragging ? "Suelta los PDF para añadirlos" : "Arrastra los PDF aquí"}</p>
              <p className="mt-0.5 text-xs text-muted">Hasta 30 archivos, 25 MiB por PDF</p>
            </div>
            <input ref={picker} type="file" multiple accept=".pdf,application/pdf" hidden
              onChange={event => {
                choose(Array.from(event.currentTarget.files ?? []));
                event.currentTarget.value = "";
              }} />
            <Button className="mt-0.5 min-h-10 px-4" onClick={() => picker.current?.click()}>Elegir PDF</Button>
          </div>
          {files.length ? (
            <ul aria-label="Archivos seleccionados" className="max-h-40 divide-y divide-border overflow-y-auto overscroll-contain rounded-xl border border-border bg-surface-raised">
              {files.map(file => (
                <li key={fileKey(file)} className="flex min-w-0 items-center gap-2.5 px-2.5 py-1.5">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-text"><Icon icon={FileText} size={17} /></span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm leading-snug font-medium text-strong [overflow-wrap:anywhere]">{file.name}</p>
                    <p className="mt-0.5 text-xs text-muted">{fileSize(file.size)}</p>
                  </div>
                  <Button variant="ghost" aria-label={`Quitar ${file.name}`} className="size-10 shrink-0 p-0"
                    onClick={() => replaceFiles(files.filter(current => fileKey(current) !== fileKey(file)))}>
                    <Icon icon={X} size={16} />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="grid grid-cols-2 gap-x-3 gap-y-3.5 text-sm font-medium text-text max-[360px]:grid-cols-1 sm:gap-x-4">
            <label className="grid min-w-0 gap-1">Equipo
              <input value={tag} required maxLength={120} onChange={event => setTag(event.target.value)} className={uploadField} />
            </label>
            <label className="grid min-w-0 gap-1">Versión
              <input value={revision} required maxLength={50} onChange={event => setRevision(event.target.value)} className={uploadField} />
            </label>
            <label className="grid min-w-0 gap-1">Proyecto
              <input name="project" required pattern="[A-Za-z0-9_\-]+" maxLength={80} className={uploadField}
                value={target?.project_id ?? project} readOnly={Boolean(target)} onChange={event => setProject(event.target.value)} />
            </label>
            <label className="grid min-w-0 gap-1">Origen
              <select name="dataset" defaultValue="synthetic" className={cn(uploadField, "max-sm:px-2")}>
                <option value="synthetic">Datos sintéticos</option>
                <option value="real">Datos reales</option>
              </select>
            </label>
          </div>
          <UploadTargetNotice plan={plan} fichas={matches.data ?? []} choice={choice} onChoose={setChoice} />
          {revisionNotice}
          {feedback ? <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{feedback}</p> : null}
        </fieldset>
        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-border bg-surface-raised px-4 py-3 sm:px-6">
          {onCancel ? <Button variant="ghost" className="min-h-11" onClick={onCancel} disabled={running && !uploaded}>Cancelar</Button> : null}
          <Button type="submit" variant="primary" className="min-h-11 px-4"
            disabled={running || !apiEnabled || !files.length || mixed || plan.kind === "choose" || plan.kind === "duplicate"}>
            {running && !uploaded ? "Subiendo archivos…" : checkedMismatch ? "Procesar con la revisión elegida" : "Subir y procesar"}
            <Icon icon={ArrowRight} size={16} />
          </Button>
        </footer>
      </form>
    );
    return onCancel ? form : (
      <div className="max-w-3xl space-y-5">
        <Panel className="overflow-hidden">{form}</Panel>
        {uploaded?.length ? <Panel className="space-y-2 p-4 sm:p-6">
          <h2 className="text-xl font-semibold text-strong">Archivos subidos</h2>
          <ul className="list-disc space-y-1 pl-6">{uploaded.map((file, index) => <li key={`${file}-${index}`} className="break-all">{file}</li>)}</ul>
        </Panel> : null}
      </div>
    );
  }

  return (
    <Panel className="p-5">
      <form aria-label="Procesar planos y hojas de datos" onSubmit={process}
        onDragOver={event => event.preventDefault()} onDrop={event => {
          event.preventDefault();
          if (!running) choose(Array.from(event.dataTransfer.files));
        }}>
        <h2 className="text-[15px] font-semibold text-strong">Procesar planos y hojas de datos</h2>
        <p className="mt-1 text-sm text-muted">Suelta los archivos de un equipo y una revisión. La API guarda los originales, ejecuta la lectura y genera un IFC DRAFT.</p>
        <fieldset disabled={running} className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="grid gap-1 text-sm md:col-span-2">Archivos de entrada
            <input ref={picker} aria-label="Documentos para procesar" type="file" multiple accept=".pdf,.xlsx,.png,.jpg,.jpeg"
              onChange={event => choose(Array.from(event.currentTarget.files ?? []))} className={field} />
          </label>
          <label className="grid gap-1 text-sm">Origen
            <select name="dataset" aria-label="Origen de documentos" defaultValue="synthetic" className={field}>
              <option value="synthetic">Sintéticos de prueba</option>
              <option value="real">Datos reales del reto</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm">Proyecto
            <input name="project" required pattern="[A-Za-z0-9_\-]+" value={project} onChange={event => setProject(event.target.value)} maxLength={80} className={field} />
          </label>
          <label className="grid gap-1 text-sm">Tag del equipo
            <input value={tag} required maxLength={120} onChange={event => setTag(event.target.value)} className={field} />
          </label>
          <label className="grid gap-1 text-sm">Revisión
            <input value={revision} required maxLength={50} onChange={event => setRevision(event.target.value)} className={field} />
          </label>
          <label className="grid gap-1 text-sm">ID estable del equipo
            <input value={equipmentId} placeholder={tag || "Igual al tag si se deja vacío"} maxLength={120}
              onChange={event => setEquipmentId(event.target.value)} className={field} />
          </label>
          <label className="grid gap-1 text-sm">Estrategia
            <select aria-label="Estrategia de lectura" value={strategy} onChange={event => setStrategy?.(event.target.value as Strategy)} className={field}>
              {Object.entries(PROFILES).map(([value, profile]) => <option key={value} value={value}>{profile.name}</option>)}
            </select>
          </label>
          <div className="flex items-end">
            <Button type="submit" variant="primary" disabled={!files.length || mixed}>{checkedMismatch ? "Procesar con la revisión elegida" : "Procesar documentos"}</Button>
          </div>
        </fieldset>
        {revisionNotice ? <div className="mt-3">{revisionNotice}</div> : null}
        {files.length ? <p className="mt-3 break-words text-xs text-muted">{files.map(file => file.name).join(" · ")}</p> : null}
        {mixed || error ? <p role="alert" className="mt-2 text-sm text-danger">{error || "Selecciona archivos de un solo equipo y una sola revisión."}</p> : null}
      </form>
    </Panel>
  );
}

/** Dónde se guardará la subida: versión de una ficha existente o ficha nueva. */
function UploadTargetNotice({ plan, fichas, choice, onChoose }: {
  plan: UploadPlan; fichas: { project_id: string; equipment_id: string; tag: string; revisions: { label: string }[] }[];
  choice: string; onChoose: (value: string) => void;
}) {
  if (!fichas.length) return null;
  const label = (ficha: (typeof fichas)[number]) =>
    `${ficha.tag} · ${ficha.project_id} (${ficha.revisions.length === 1 ? "1 versión" : `${ficha.revisions.length} versiones`})`;
  return (
    <div className="space-y-2 rounded-lg border border-border bg-surface-sunken/60 px-3 py-2.5 text-sm" aria-live="polite">
      {fichas.length > 1 || choice === NEW_FICHA ? (
        <label className="grid gap-1 font-medium text-text">Ficha de destino
          <select value={choice} onChange={event => onChoose(event.target.value)} className={uploadField}>
            {fichas.length > 1 ? <option value="" disabled>Elige una ficha…</option> : null}
            {fichas.map(ficha => <option key={fichaKey(ficha)} value={fichaKey(ficha)}>{label(ficha)}</option>)}
            <option value={NEW_FICHA}>Crear una ficha nueva</option>
          </select>
        </label>
      ) : null}
      {plan.kind === "choose" ? <p className="text-warning">Este código está en {fichas.length} fichas. Elige a cuál se añade la versión.</p>
        : plan.kind === "version" ? <p className="text-text">Se añadirá una versión a este equipo: <strong>{plan.ficha.tag} · {plan.ficha.project_id}</strong>, Rev. {plan.revision}.</p>
        : plan.kind === "renamed" ? <p className="text-text">La Rev. {plan.requested} de <strong>{plan.ficha.tag} · {plan.ficha.project_id}</strong> ya existe con otros archivos. Se guardará como <strong>Rev. {plan.revision}</strong> y se conserva la anterior.</p>
        : plan.kind === "duplicate" ? <p className="text-warning">Estos archivos ya están en la Rev. {plan.revision} de {plan.ficha.tag} · {plan.ficha.project_id}. No se duplican.</p>
        : <p className="text-muted">Se creará una ficha nueva aunque el código ya exista.</p>}
      {fichas.length === 1 && choice !== NEW_FICHA ? (
        <button type="button" className="text-xs text-accent-text underline-offset-2 hover:underline" onClick={() => onChoose(NEW_FICHA)}>
          Guardar como ficha nueva
        </button>
      ) : null}
    </div>
  );
}

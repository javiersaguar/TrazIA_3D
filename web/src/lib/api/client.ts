import type { Revision } from "@/lib/types/revision";
import type { BenchExtractor, EquipmentRow, FieldUpdate, RevisionId } from "../mock/api";
import type { BenchReport } from "../mock/bench-types";
import type { StudyResponse } from "../mock/estudio-types";
import type { DiffReport } from "../mock/diff-types";
import { flattenRevision, type ReviewField } from "../mock/fields";
import { activeEquipment, revisionIdentity, revisionLabel } from "@/stores/equipment";
import { apiURL, rememberVersion, revisionVersion } from "./config";
import { sessionActor } from "@/lib/actor";
import type { components } from "./schema";

type FieldInput = components["schemas"]["FieldInput"];
export type JobInput = components["schemas"]["JobInput"];
export type EquipmentJobInput = components["schemas"]["EquipmentJobInput"];
export type StageEvent = { id: number; job_id: string; stage: string; status: "ok" | "omitido" | "error"; file: string; detail: string; created_at: number };
export type JobStatus = { id: string; status: "queued" | "running" | "done" | "error" | "cancelled" | "timeout"; attempts: number; error: string | null; run: components["schemas"]["RunInfo"] | null; warnings: string[]; created_at: number; revision_id: string | null };
export type PipelineJob = JobStatus & { kind: string; tag: string; strategy?: string; documents?: string[] };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = "ApiError"; }
}

async function checked(response: Response) {
  if (response.ok) return response;
  const body = await response.json().catch(() => null);
  const issues = Array.isArray(body?.detail) ? body.detail.map((issue: { loc?: string[]; msg?: string }) =>
    [issue.loc?.slice(1).join("."), issue.msg].filter(Boolean).join(" — ")).join("; ") : "";
  throw new ApiError(response.status, typeof body?.detail === "string" ? body.detail : issues || `La API respondió ${response.status}`);
}

async function get<T>(path: string): Promise<T> {
  return (await checked(await fetch(apiURL(path)))).json() as Promise<T>;
}

export async function apiRevision(rev: RevisionId): Promise<Revision> {
  const equipment = activeEquipment();
  if (!equipment) throw new ApiError(404, "Elige un equipo en Documentos para abrir su modelo.");
  const query = new URLSearchParams({ project_id: equipment.project_id });
  const response = await checked(await fetch(apiURL(`/equipment/${encodeURIComponent(equipment.tag)}/revisions/${encodeURIComponent(revisionLabel(rev, equipment))}?${query}`)));
  const data = await response.json() as Revision;
  rememberRevision(rev, data, response.headers.get("ETag"));
  return data;
}

export async function apiFields(rev: RevisionId): Promise<ReviewField[]> {
  return flattenRevision(await apiRevision(rev));
}

export const apiRevisionById = (identity: string) => get<Revision>(`/revisions/${encodeURIComponent(identity)}`);

export async function apiRevisionSnapshot(identity: string) {
  const response = await checked(await fetch(apiURL(`/revisions/${encodeURIComponent(identity)}`)));
  return { record: await response.json() as Revision, etag: response.headers.get("ETag") };
}

export function rememberRevision(slot: RevisionId, record: Revision, etag: string | null) {
  const identity = `${record.project_id}:${record.equipment.id}:${record.revision}`;
  if (revisionIdentity(slot) !== identity) return;
  const pdfs = record.documents.filter(document => document.filename.toLowerCase().endsWith(".pdf"));
  const drawing = pdfs.find(document => /^GA/i.test(document.id))?.id ?? pdfs[0]?.id;
  rememberVersion(slot, identity, etag, drawing);
}

// Serializar las acciones de una revisión evita que dos pulsaciones rápidas usen el mismo ETag.
const writes = new Map<string, Promise<unknown>>();
export async function apiUpdate(update: FieldUpdate): Promise<ReviewField> {
  const body: FieldInput = {
    state: update.action === "reject" ? "abstained" : update.status,
    actor: update.actor ?? sessionActor(), seconds: update.seconds,
    review_session_id: update.reviewSessionId, action: update.action,
    expected: update.expected,
    explanation: update.explanation, source: update.source ? {
      ...update.source, bbox: update.source.bbox ? update.source.bbox.map(Number) as [number, number, number, number] : null,
    } : undefined,
  };
  if (update.correctedValue !== undefined) body.value = update.correctedValue;
  return writeField(update, "PATCH", `fields/${encodeURIComponent(update.path)}`, body);
}

export function apiUndo(update: FieldUpdate, auditId: number): Promise<ReviewField> {
  return writeField(update, "POST", `audit/${auditId}/undo`, {
    actor: update.actor ?? sessionActor(), seconds: update.seconds, review_session_id: update.reviewSessionId,
  });
}

async function writeField(update: FieldUpdate, method: "PATCH" | "POST", suffix: string, body: object): Promise<ReviewField> {
  const previous = writes.get(update.rev) ?? Promise.resolve();
  const action = previous.catch(() => undefined).then(async () => {
    if (!revisionVersion(update.rev)) await apiRevision(update.rev);
    const version = revisionVersion(update.rev);
    if (!version) throw new ApiError(428, "La API no ha devuelto la versión de la revisión");
    const raw = await fetch(apiURL(`/revisions/${encodeURIComponent(version.identity)}/${suffix}`), {
      method, headers: { "Content-Type": "application/json", "If-Match": version.etag, "Idempotency-Key": update.idempotencyKey },
      body: JSON.stringify(body),
    });
    if (raw.status === 412) await apiRevision(update.rev).catch(() => undefined);
    const pendingExport = raw.status === 503 ? await raw.clone().json().catch(() => null) : null;
    const response = pendingExport?.persisted && pendingExport?.revision
      ? new Response(JSON.stringify(pendingExport.revision), { status: 200, headers: raw.headers })
      : await checked(raw);
    const revision = await response.json() as Revision;
    rememberVersion(update.rev, version.identity, response.headers.get("ETag"));
    const field = flattenRevision(revision).find(f => f.path === update.path);
    if (!field) throw new ApiError(422, "La API no devolvió el campo modificado");
    const auditId = response.headers.get("X-Audit-Id");
    if (auditId) field.auditId = Number(auditId);
    if (pendingExport?.persisted) field.saveWarning = pendingExport.detail;
    return field;
  });
  writes.set(update.rev, action);
  try { return await action; } finally { if (writes.get(update.rev) === action) writes.delete(update.rev); }
}

export async function apiExportCorrections() {
  return checked(await fetch(apiURL("/correcciones/export"), { method: "POST" }));
}

export const apiChanges = () => get<DiffReport>(`/diff?${new URLSearchParams({ from: revisionIdentity("A"), to: revisionIdentity("B") })}`);
export const apiDiffBetween = (from: string, to: string) => get<DiffReport>(`/diff?${new URLSearchParams({ from, to })}`);
/** IFC de una revisión concreta por su identidad (`proyecto:equipo:revisión`). */
export const revisionIfcUrl = (identity: string) => apiURL(`/revisions/${encodeURIComponent(identity)}/ifc?draft=true`);

/** Una acción del registro de auditoría: quién cambió qué campo, con su valor antes y después. */
export type AuditAction = {
  id: number;
  revision_id: string;
  path: string;
  actor: string;
  before_json: string;
  after_json: string;
  undo_of: number | null;
  created_at: number;
};
export const apiAudit = (identity: string) =>
  get<{ actions: AuditAction[] }>(`/revisions/${encodeURIComponent(identity)}/audit`);

/** Propuesta de cambio de diseño; al aplicarse crea una revisión nueva. */
export type ProposalSummary = {
  id: string;
  status: string;
  actor: string;
  reason?: string | null;
  request_text?: string | null;
  base: { revision_id: string; revision?: string | null };
  target_revision: string;
  applied_revision_id: string | null;
  created_at: number;
  updated_at: number;
};
export const apiProposals = (identity: string) =>
  get<{ proposals: ProposalSummary[] }>(`/revisions/${encodeURIComponent(identity)}/change-proposals`);
export const apiStudy = () => get<StudyResponse>("/estudio");
export const apiBench = (extractor: BenchExtractor) => get<BenchReport>(`/bench?extractor=${extractor}`);
export async function apiEquipment(): Promise<EquipmentRow[]> {
  const rows = await get<EquipmentRow[]>("/equipment");
  const labels: Record<string, string> = { vertical_vessel: "Recipiente vertical", horizontal_vessel: "Recipiente horizontal", column: "Columna", tank: "Tanque", pump: "Bomba", compressor: "Compresor", generic: "Genérico" };
  return rows.map(row => ({ ...row, kind: labels[row.kind] ?? row.kind, ifcUrl: apiURL(row.ifcUrl) }));
}

export type RevisionDetection = {
  filename_revision: string | null;
  drawing_revision: { value: string; page: number; locator: string } | null;
};

export type UploadedDocument = {
  id: string;
  filename: string;
  sha256: string;
  revision_detection?: RevisionDetection;
};

export function sameRevision(a: string, b: string) {
  const normalize = (label: string) => label.trim().toUpperCase()
    .replace(/^REV(?:ISION)?[. _-]*(?=[A-Z]$|\d+$)/, "").replace(/^0+(?=\d)/, "");
  return normalize(a) === normalize(b);
}

export async function uploadDocument(file: File, documentId?: string, revision = "A", key: string = crypto.randomUUID(), inspectRevision = false): Promise<UploadedDocument> {
  const form = new FormData(); form.append("file", file);
  if (documentId) form.append("document_id", documentId);
  form.append("revision", revision);
  if (inspectRevision) form.append("inspect_revision", "true");
  return (await checked(await fetch(apiURL("/documents"), { method: "POST", body: form,
    headers: { "Idempotency-Key": key } }))).json();
}

/** Documento registrado; `cited_by` son las revisiones guardadas que citan su SHA-256. */
export type StoredDocument = {
  id: string; document_id: string; filename: string; revision: string; sha256: string; size: number;
  kind: string | null; equipment_tag: string | null; uploaded: boolean; cited_by: string[]; active_jobs: string[];
};
export const listDocuments = () => get<StoredDocument[]>("/documents");
/** Borra un documento subido. La API responde 409 si una revisión o un trabajo en curso lo usa. */
export async function deleteDocument(id: string, key: string = crypto.randomUUID()): Promise<{ id: string; blob_removed: boolean }> {
  return (await checked(await fetch(apiURL(`/documents/${encodeURIComponent(id)}`), {
    method: "DELETE", headers: { "Idempotency-Key": key } }))).json();
}

/** Borra una revisión en borrador. 409 si está aprobada, la usa un trabajo o la enlaza un cambio de diseño. */
export async function deleteRevision(identity: string, version: number, key: string = crypto.randomUUID()): Promise<{ id: string }> {
  return (await checked(await fetch(apiURL(`/revisions/${encodeURIComponent(identity)}`), {
    method: "DELETE", headers: { "Idempotency-Key": key, "If-Match": `"${version}"` } }))).json();
}

/** Ficha existente con el mismo código (sin mayúsculas ni espacios), con la huella de sus originales. */
export type MatchedFicha = {
  project_id: string; equipment_id: string; tag: string; dataset: string | null;
  revisions: { label: string; approved: boolean; documents: { filename: string; sha256: string }[] }[];
};
export const matchEquipment = (tag: string) => get<MatchedFicha[]>(`/equipment/match?tag=${encodeURIComponent(tag)}`);
/** Borra todas las revisiones de una ficha. 409 si alguna está protegida; nada se borra entonces. */
export async function deleteFicha(project: string, equipmentId: string, key: string = crypto.randomUUID()) {
  return (await checked(await fetch(apiURL(`/equipment/${encodeURIComponent(project)}/${encodeURIComponent(equipmentId)}`), {
    method: "DELETE", headers: { "Idempotency-Key": key } }))).json() as Promise<{ revisions: string[] }>;
}
/** Oculta la ficha del catálogo y conserva su historial. */
export async function retireFicha(body: { project_id: string; equipment_id: string | null; tag: string }, key: string = crypto.randomUUID()) {
  await checked(await fetch(apiURL("/equipment/retire"), { method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(body) }));
}

export async function startJob(body: EquipmentJobInput, key: string = crypto.randomUUID()): Promise<string> {
  const response = await checked(await fetch(apiURL("/jobs"), { method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(body) }));
  return (await response.json() as { job_id: string }).job_id;
}
export const getJob = (identity: string) => get<JobStatus>(`/jobs/${encodeURIComponent(identity)}`);
export const getPipelineJob = (identity: string) => get<PipelineJob>(`/jobs/${encodeURIComponent(identity)}`);
export async function cancelJob(identity: string) {
  await checked(await fetch(apiURL(`/jobs/${encodeURIComponent(identity)}/cancel`), { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() } }));
}

export function subscribeJob(identity: string, onStage: (event: StageEvent) => void, onComplete: (status: string) => void, onError: () => void) {
  let closed = false;
  const stream = new EventSource(apiURL(`/jobs/${encodeURIComponent(identity)}/events`));
  stream.addEventListener("stage", message => {
    try { onStage(JSON.parse((message as MessageEvent).data) as StageEvent); } catch { onError(); }
  });
  stream.addEventListener("complete", message => {
    const data = JSON.parse((message as MessageEvent).data) as { status: string };
    closed = true; stream.close(); onComplete(data.status);
  });
  stream.onerror = () => { if (!closed) onError(); }; // EventSource reanuda con Last-Event-ID; no se sustituyen eventos por mocks.
  return () => { closed = true; stream.close(); };
}


export type CopilotAnswer = components["schemas"]["CopilotAnswer"];
export type CopilotScope = { id: string; project: string; label: string } & (
  { kind: "revision"; tag: string; revision: string; previous_id: string | null }
  | { kind: "project" | "process" | "catalogue" }
);
export async function copilotScopes(signal?: AbortSignal): Promise<CopilotScope[]> {
  return (await checked(await fetch(apiURL("/copiloto/contexts"), { signal }))).json();
}

function voiceURL(scope: CopilotScope) {
  const params = new URLSearchParams({ kind: scope.kind, identity: scope.id });
  return apiURL(`/copiloto/voice?${params}`);
}

export async function copilotVoiceAvailable(scope: CopilotScope, signal: AbortSignal): Promise<boolean> {
  const response = await fetch(voiceURL(scope), { signal, cache: "no-store" });
  if (!response.ok) return false;
  const result = await response.json() as { available: boolean };
  return result.available === true;
}

export async function transcribeCopilot(scope: CopilotScope, audio: Blob, signal: AbortSignal): Promise<string> {
  const form = new FormData();
  form.append("file", audio, "dictado");
  const response = await checked(await fetch(voiceURL(scope), { method: "POST", body: form, signal }));
  const result = await response.json() as { text: string };
  return result.text;
}

export async function askCopilot(scope: CopilotScope, question: string, path?: string, signal?: AbortSignal, revision?: "A" | "B"): Promise<CopilotAnswer> {
  const body = scope.kind === "revision" ? { question, revision_id: scope.id, path,
    previous_id: scope.previous_id ?? undefined } : { question, kind: scope.kind, id: scope.id, revision };
  return (await checked(await fetch(apiURL(scope.kind === "revision" ? "/copiloto" : "/copiloto/project"), { method: "POST", signal,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }))).json() as Promise<CopilotAnswer>;
}

export type ProcessAdjustment = { tag: string; field: "length" | "width" | "height" | "dn" | "rack_z"; value: number };
export type ProcessDraft = { adjustments: ProcessAdjustment[]; questions: string[] };
export async function prepareProcessDraft(projectId: string, text: string): Promise<ProcessDraft> {
  return (await checked(await fetch(apiURL("/copiloto/process-drafts"), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({project_id: projectId, text}),
  }))).json();
}

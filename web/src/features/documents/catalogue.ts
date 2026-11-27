import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { accountRequest } from "@/lib/accounts";
import { accountsEnabled, apiURL } from "@/lib/api/config";
import { DOCUMENTS, FAMILIES as FAMILY_INFO, PROJECTS as SAMPLE_PROJECTS, type DocStage, type SketchFamily } from "@/lib/mock/bocetos";
import sketches from "./sketches.json";
import industrial from "./industrial-designs.json";

/*
  Catálogo de Documentos: familias, proyectos y diseños, guardado en este navegador.
  Los ejemplos (salvo DEMO-PLANT / V-101) son inventados y se marcan como tales en la interfaz.
*/

export type Family = { id: string; name: string; custom?: boolean };
export type ProjectStatus = "En revisión" | "Aprobado" | "Sin empezar";
export type ProjectStats = { equipment: number; withData: number; reviewed: number; status: ProjectStatus; updated: string };
export type Project = { id: string; name: string; code?: string; example?: boolean; stats?: ProjectStats; collection?: boolean };
export type DocKind = "Plano GA" | "Boceto GA" | "Hoja de datos" | "Lista de boquillas" | "Otro";
export type Design = {
  id: string;
  name: string;
  family: string;
  project: string;
  filename?: string;
  size?: number;
  /** Documento de V-101 que abre la demo del modelo. */
  demo?: boolean;
  /** Documento inventado para enseñar la pantalla. */
  example?: boolean;
  kind?: DocKind;
  tag?: string;
  rev?: string;
  pages?: number;
  stage?: DocStage;
  received?: string;
  shared?: boolean;
  publishedAt?: string;
};

export const FAMILIES: Family[] = [
  { id: "vertical", name: "Recipientes verticales" },
  { id: "horizontal", name: "Recipientes horizontales" },
  { id: "column", name: "Columnas" },
  { id: "exchanger", name: "Intercambiadores" },
  { id: "tank", name: "Tanques" },
  { id: "pump", name: "Bombas" },
  { id: "compressor", name: "Compresores" },
  { id: "generic", name: "Envolventes de reserva" },
  ...industrial.families.map(({ id, name }) => ({ id, name })),
];

const industrialFamilies = new Map(industrial.families.map((family) => [family.id, family]));

export function industrialFamily(id: string) {
  return industrialFamilies.get(id);
}

/** Ficha de cada familia: piezas, estado y campos de revisión. */
export type FamilyInfo = Omit<SketchFamily, "kind" | "name">;
const EXTRA_INFO: Record<string, FamilyInfo> = {
  compressor: { fields: null, parts: ["Carcasa", "Accionamiento", "Bancada"], status: "Planificada", phase: "—" },
  generic: { fields: null, parts: ["Envolvente LOD 1", "Boquillas"], status: "Disponible", phase: "F1" },
};
export function familyInfo(id: string): FamilyInfo | undefined {
  const known = FAMILY_INFO.find((f) => f.kind === id);
  if (known) return { fields: known.fields, parts: known.parts, status: known.status, phase: known.phase };
  return EXTRA_INFO[id];
}

const PROJECT_IDS: Record<string, string> = { "DEMO-PLANT": "demo", "EJ-HDT": "ej-hdt", "EJ-GNL": "ej-gnl", "EJ-DST": "ej-dst" };
const SEED_PROJECTS: Project[] = SAMPLE_PROJECTS.map((p) => ({
  id: PROJECT_IDS[p.code] ?? p.code.toLowerCase(),
  name: p.name,
  code: p.code,
  example: p.example,
  stats: { equipment: p.equipment, withData: p.withData, reviewed: p.reviewed, status: p.status, updated: p.updated },
}));
const SKETCH_PROJECT: Project = {
  id: "catalogo-bocetos",
  name: "Biblioteca de bocetos",
  code: "BOCETOS",
  example: true,
  collection: true,
};
SEED_PROJECTS.push(SKETCH_PROJECT);
/** Familias de los proyectos de ejemplo, aunque aún no tengan documentos en el catálogo. */
export const PROJECT_KINDS: Record<string, string[]> = Object.fromEntries(
  SAMPLE_PROJECTS.map((p) => [PROJECT_IDS[p.code] ?? p.code.toLowerCase(), p.kinds]),
);

const TAG_FAMILY: Record<string, [family: string, project: string]> = {
  "V-101": ["vertical", "demo"],
  "E-201": ["exchanger", "ej-hdt"],
  "T-301": ["tank", "ej-gnl"],
  "C-401": ["column", "ej-dst"],
};
const SEED_DESIGNS: Design[] = DOCUMENTS.map((d) => {
  const [family, project] = TAG_FAMILY[d.tag] ?? ["generic", "demo"];
  return {
    id: `seed-${d.name}`,
    name: d.name,
    filename: d.name,
    family,
    project,
    demo: !d.example,
    example: d.example,
    kind: d.kind,
    tag: d.tag,
    rev: d.rev,
    pages: d.pages,
    stage: d.stage,
    received: d.received,
  };
});
const sketchFiles = new Map<string, { pdf: string; ifc?: string }>();
for (const entry of [...sketches, ...industrial.designs]) {
  const { tag, family, name, filename } = entry;
  const id = `sketch-${tag}`;
  SEED_DESIGNS.push({ id, tag, family, name, filename, project: SKETCH_PROJECT.id,
    example: true, kind: "Boceto GA", rev: "A", pages: 1 });
  sketchFiles.set(id, "ifc" in entry
    ? { pdf: `/demo/industriales/${filename}`, ifc: `/demo/industriales/${entry.ifc}` }
    : { pdf: `/demo/bocetos/${filename}` });
}

export function sketchAssets(id: string) {
  return sketchFiles.get(id);
}

/** Equipo leído del nombre del archivo (GAD_V-101_revB.pdf → V-101), si lo trae. */
export function tagFromFilename(filename: string): string | undefined {
  return filename.match(/(?:^|[_\s-])([A-Z]{1,3}-?\d{2,4}[A-Z]?)(?=[_\s.-]|$)/)?.[1];
}
export function kindFromFilename(filename: string): DocKind {
  const f = filename.toUpperCase();
  if (f.startsWith("GAD") || f.includes("_GA")) return "Plano GA";
  if (f.startsWith("DS") || f.endsWith(".XLSX") || f.endsWith(".XLS")) return "Hoja de datos";
  if (f.startsWith("NOZ")) return "Lista de boquillas";
  return f.endsWith(".PDF") ? "Plano GA" : "Otro";
}

type Catalogue = {
  families: Family[];
  projects: Project[];
  designs: Design[];
  addFamily(name: string): string;
  addProject(name: string): string;
  addDesign(design: Design): void;
  assign(id: string, family: string, project: string): void;
};

type Persisted = Pick<Catalogue, "families" | "projects" | "designs">;

const useLocalCatalogue = create<Catalogue>()(
  persist(
    (set) => ({
      families: FAMILIES,
      projects: SEED_PROJECTS,
      designs: SEED_DESIGNS,
      addFamily: (name) => {
        const id = crypto.randomUUID();
        set((s) => ({ families: [...s.families, { id, name: name.trim(), custom: true }] }));
        return id;
      },
      addProject: (name) => {
        const id = crypto.randomUUID();
        set((s) => ({ projects: [...s.projects, { id, name: name.trim() }] }));
        return id;
      },
      addDesign: (design) => set((s) => ({ designs: [design, ...s.designs] })),
      assign: (id, family, project) =>
        set((s) => ({ designs: s.designs.map((d) => (d.id === id ? { ...d, family, project } : d)) })),
    }),
    {
      name: "trazia.catalogue.v1",
      version: 5,
      // Añadir las nuevas fichas sin reemplazar documentos ni asignaciones guardadas.
      migrate: (stored, version) => {
        const s = stored as Persisted;
        const designs = version < 2 ? s.designs.filter((d) => d.id !== "demo-v101") : s.designs;
        const projects = version < 2
          ? s.projects.map((p) => SEED_PROJECTS.find((q) => q.id === p.id) ?? p)
          : s.projects;
        return {
          families: [...s.families, ...FAMILIES.filter((f) => !s.families.some((stored) => stored.id === f.id))],
          projects: [...projects, ...SEED_PROJECTS.filter((p) => !projects.some((q) => q.id === p.id))],
          designs: [...designs, ...SEED_DESIGNS.filter((d) => !designs.some((q) => q.id === d.id))],
        };
      },
    },
  ),
);

export const MAX_DOCUMENT_MB = accountsEnabled ? 25 : 50;
export const MAX_DOCUMENT_BYTES = MAX_DOCUMENT_MB * 1024 * 1024;
export const DOCUMENT_ACCEPT = ".pdf,.xlsx,.xls,.ifc,.png,.jpg,.jpeg";
const catalogueKey = ["shared-catalogue"];

type Destination = Pick<Design, "family" | "project" | "name">;

export function publishedFile(id: string) {
  return apiURL(`/catalogue/designs/${encodeURIComponent(id)}/file`);
}

export function useCatalogue() {
  const local = useLocalCatalogue();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: catalogueKey,
    queryFn: async () => await (await accountRequest("/catalogue")).json() as Persisted,
    enabled: accountsEnabled,
    retry: false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: catalogueKey });
  async function addGroup(kind: "family" | "project", name: string) {
    if (!accountsEnabled) return kind === "family" ? local.addFamily(name) : local.addProject(name);
    const result = await accountRequest("/catalogue/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, name }),
    });
    const group = await result.json() as Family;
    await refresh();
    return group.id;
  }
  async function publish(file: File, destination: Destination) {
    if (!file.size) throw new Error("Selecciona un documento para el diseño.");
    if (file.size > MAX_DOCUMENT_BYTES) throw new Error(`El documento supera ${MAX_DOCUMENT_MB} MB.`);
    if (accountsEnabled) {
      const body = new FormData();
      body.append("file", file);
      for (const [key, value] of Object.entries(destination)) body.append(key, value);
      await accountRequest("/catalogue/designs", { method: "POST", body });
      await refresh();
      return;
    }
    const id = crypto.randomUUID();
    await saveDocument(id, file);
    local.addDesign({
      id, ...destination, filename: file.name, size: file.size, stage: "recibido",
      kind: kindFromFilename(file.name),
      tag: tagFromFilename(destination.name) ? undefined : tagFromFilename(file.name),
      received: new Date().toLocaleDateString("es-ES"),
    });
  }
  async function assign(id: string, family: string, project: string) {
    if (!accountsEnabled) {
      local.assign(id, family, project);
      return;
    }
    await accountRequest(`/catalogue/designs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ family, project }),
    });
    await refresh();
  }
  return {
    families: accountsEnabled ? [...FAMILIES, ...(query.data?.families ?? [])] : local.families,
    projects: accountsEnabled ? [...SEED_PROJECTS, ...(query.data?.projects ?? [])] : local.projects,
    designs: accountsEnabled ? [
      ...(query.data?.designs ?? []).map(design => ({
        ...design,
        kind: design.filename ? kindFromFilename(design.filename) : undefined,
        tag: design.filename ? tagFromFilename(design.filename) : undefined,
        received: design.publishedAt ? new Date(design.publishedAt).toLocaleDateString("es-ES") : undefined,
      })),
      ...SEED_DESIGNS,
    ] : local.designs,
    loading: accountsEnabled && query.isPending,
    error: accountsEnabled ? query.error : null,
    reload: query.refetch,
    addFamily: (name: string) => addGroup("family", name),
    addProject: (name: string) => addGroup("project", name),
    publish,
    assign,
  };
}

async function database() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("trazia.documents.v1", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("files");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
export async function saveDocument(id: string, file: File) {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("files", "readwrite");
      tx.objectStore("files").put(file, id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
export async function loadDocument(id: string): Promise<Blob | undefined> {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction("files", "readonly").objectStore("files").get(id);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

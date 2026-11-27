export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
export const apiEnabled = API_BASE.length > 0;
export const accountsEnabled = API_BASE === "/api/trazia";

type RevisionVersion = { identity: string; etag: string; drawing?: string };
const versions = new Map<string, RevisionVersion>();

export function apiURL(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export function rememberVersion(revision: string, identity: string, etag: string | null, drawing?: string) {
  const current = versions.get(revision);
  if (current?.identity === identity && etag && Number(etag.replace(/"/g, "")) < Number(current.etag.replace(/"/g, ""))) return;
  if (etag) versions.set(revision, { identity, etag, drawing: drawing ?? (current?.identity === identity ? current.drawing : undefined) });
}

/** Al cambiar de equipo, las versiones recordadas dejan de valer. */
export function forgetVersions() {
  versions.clear();
}

export function revisionVersion(revision: string) {
  return versions.get(revision);
}

export function revisionResource(revision: "A" | "B", resource: "ifc" | "pdf") {
  if (!apiEnabled) return resource === "ifc" ? `/demo/ifc/rev_${revision.toLowerCase()}.ifc`
    : `/demo/docs/GAD_V-101_rev${revision}.pdf`;
  const version = versions.get(revision);
  const id = encodeURIComponent(version?.identity ?? revision);
  const cacheVersion = version?.etag.replace(/^"(.*)"$/, "$1") ?? "0";
  return resource === "ifc" ? apiURL(`/revisions/${id}/ifc?draft=true&v=${encodeURIComponent(cacheVersion)}`)
    : apiURL(`/revisions/${id}/documents/${encodeURIComponent(version?.drawing ?? "GA")}`);
}

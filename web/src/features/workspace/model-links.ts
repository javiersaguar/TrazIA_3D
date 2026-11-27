export type ModelView = "revision" | "cambios";

/** Vistas antiguas de Modelo: «Modelo 3D» se ve en Revisión y «Proponer cambios» vive en Cambios. */
export const LEGACY_VIEWS: Record<string, ModelView> = { "3d": "revision", editar: "cambios" };

export function modelHref(view: ModelView, identity?: string) {
  const query = new URLSearchParams({ vista: view });
  if (identity) query.set("resultado", identity);
  return `/modelo?${query}`;
}

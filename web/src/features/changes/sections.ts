/** Secciones de la pestaña Cambios; la elegida viaja en `?seccion=`. */
export type ChangesSection = "comparar" | "proponer" | "historial";

export const CHANGES_SECTIONS: { value: ChangesSection; label: string }[] = [
  { value: "comparar", label: "Qué ha cambiado" },
  { value: "proponer", label: "Proponer un cambio" },
  { value: "historial", label: "Historial" },
];

/** La vista antigua `?vista=editar` abre directamente el formulario. */
export function changesSection(raw: string | null, view?: string | null): ChangesSection {
  if (CHANGES_SECTIONS.some(({ value }) => value === raw)) return raw as ChangesSection;
  return view === "editar" ? "proponer" : "comparar";
}

/** Enlace a una sección de Cambios. */
export const changesHref = (section: ChangesSection) => `/modelo?vista=cambios&seccion=${section}`;

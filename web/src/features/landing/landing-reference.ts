/** IFC sintético que acompaña al inicio de sesión de la versión pública. */
export const LANDING_REFERENCE = {
  tag: "V-101",
  url: "/demo/ifc/rev_b.ifc",
  real: false,
} as const;

export type ReferenceModel = { tag: string; url: string; real: boolean };

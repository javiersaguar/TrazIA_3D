/** Aviso del backend (`trazia.families.preliminares.AVISO`) con las rutas que faltan en el plano. */
export const PRELIMINARY_PREFIX = "Valores preliminares (faltan en el plano, revísalos y complétalos): ";

/** Separa el aviso de valores preliminares del resto de avisos del trabajo. */
export function splitPreliminary(warnings: string[]): { preliminary: string[]; others: string[] } {
  const preliminary: string[] = [];
  const others: string[] = [];
  for (const warning of warnings) {
    if (!warning.startsWith(PRELIMINARY_PREFIX)) { others.push(warning); continue; }
    for (const path of warning.slice(PRELIMINARY_PREFIX.length).replace(/\.$/, "").split(", ")) {
      if (path && !preliminary.includes(path)) preliminary.push(path);
    }
  }
  return { preliminary, others };
}

import type { PropertySets } from "@/workers/ifc-protocol";

/*
  Soldaduras leídas del IFC: un IfcFastener (WELD) por unión con el pset TrazIA_Soldadura
  (plan 7.5, M5). La web no las redibuja: usa la geometría y los datos que trae el propio IFC.
*/

export type WeldSource = { document: string; page?: number; locator?: string };

export type WeldInfo = {
  id: string;
  kind: string;
  joins: string[];
  state: string;
  rule?: string;
  size?: string;
  note?: string;
  /** Cota desde la tangente inferior; ausente si el plano no la da. */
  elevationMm?: number;
  /** La unión está en el modelo pero sin geometría: no hay cota ni boquilla colocada. */
  withoutGeometry: boolean;
  needsReview: boolean;
  sources: WeldSource[];
};

const KINDS: Record<string, string> = {
  circumferential: "Costura circunferencial",
  longitudinal: "Costura longitudinal",
  nozzle: "Boquilla–virola",
  attachment: "Accesorio",
};

const text = (value: unknown) => (typeof value === "string" && value.trim() ? value.trim() : undefined);

export function isWeld(product: { ifcType: string; psets: PropertySets }): boolean {
  return product.ifcType.toUpperCase() === "IFCFASTENER" && !!product.psets.TrazIA_Soldadura;
}

export function weldInfo(id: string, psets: PropertySets): WeldInfo | undefined {
  const set = psets.TrazIA_Soldadura;
  if (!set) return undefined;
  const sources: WeldSource[] = [];
  const raw = set.CitasJSON;
  if (typeof raw === "string") {
    try {
      const cites: unknown = JSON.parse(raw);
      if (cites && typeof cites === "object" && !Array.isArray(cites)) {
        const seen = new Set<string>();
        for (const cite of Object.values(cites)) {
          if (!cite || typeof cite !== "object") continue;
          const source = cite as { document_id?: unknown; page?: unknown; locator?: unknown };
          const document = text(source.document_id);
          if (!document) continue;
          const page = typeof source.page === "number" ? source.page : undefined;
          const locator = text(source.locator);
          const key = `${document}|${page ?? ""}|${locator ?? ""}`;
          if (seen.has(key)) continue;
          seen.add(key);
          sources.push({ document, ...(page ? { page } : {}), ...(locator ? { locator } : {}) });
        }
      }
    } catch {
      // Una cita ilegible no oculta la soldadura: queda sin fuentes.
    }
  }
  const elevation = typeof set.CotaDesdeTL_mm === "number" && set.CotaDesdeTL_mm >= 0 ? set.CotaDesdeTL_mm : undefined;
  const rule = text(set.Regla);
  const size = text(set.Tamano);
  const note = text(set.Nota);
  return {
    id,
    kind: String(set.Tipo ?? ""),
    joins: String(set.Une ?? "").split("|").filter(Boolean),
    state: String(set.Estado ?? ""),
    ...(rule ? { rule } : {}),
    ...(size ? { size } : {}),
    ...(note ? { note } : {}),
    ...(elevation !== undefined ? { elevationMm: elevation } : {}),
    withoutGeometry: set.SinGeometria === true,
    needsReview: set.RequiereVerificacion === true,
    sources,
  };
}

export function weldKindLabel(kind: string): string {
  return KINDS[kind] ?? (kind ? `Soldadura ${kind}` : "Soldadura");
}

/** «Une A1 y la virola», para el pie del visor y el lector de pantalla. */
export function weldSummary(info: WeldInfo): string {
  const piece = (name: string) => (name.toUpperCase() === "SHELL" ? "la virola" : name);
  const joins = info.joins.length === 2
    ? `une ${piece(info.joins[0]!)} y ${piece(info.joins[1]!)}`
    : info.joins.length ? `une ${info.joins.map(piece).join(", ")}` : "sin piezas identificadas";
  const where = info.elevationMm !== undefined ? ` · cota ${info.elevationMm.toLocaleString("es-ES")} mm desde T.L.` : "";
  const source = info.sources[0];
  const cite = source
    ? ` · ${source.document}${source.page ? `, p. ${source.page}` : ""}`
    : info.rule ? ` · regla ${info.rule}` : "";
  const state = info.needsReview ? " · inferida, a verificar" : "";
  return `${weldKindLabel(info.kind)}: ${joins}${where}${cite}${state}`;
}

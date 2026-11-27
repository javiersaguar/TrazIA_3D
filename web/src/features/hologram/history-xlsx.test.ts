import { describe, expect, it } from "vitest";
import type { DiffReport, FieldChange } from "@/lib/mock/diff-types";
import type { Source } from "@/lib/types/revision";
import { historyFilename, historySheets, historyXlsx, type HistoryExportEntry } from "./history-xlsx";

const source = {
  document_id: "doc-ga",
  page: 2,
  sheet: "H1",
  cell: "C4",
  locator: "boquillas/N1",
  bbox: [10, 20, 30, 40] as [number, number, number, number],
  confidence: 0.91,
  reviewed: false,
  confidence_raw: 0.88,
  channel: "tabla",
  strategy: "hdm",
  model: "lector",
  prompt_sha256: "abc123",
  grounded: true,
  text_original: "6\"",
  unit_original: "in",
  design: { kind: "cambio_diseno" as const, proposal_id: "prop-1", operation_id: "op-9" },
} satisfies Source;

const change: FieldChange = {
  path: "nozzles.N1.size_nps",
  operation: "modified",
  before: { value: 8, unit: "in" },
  after: { value: 6, unit: "in" },
  affects_geometry: true,
  impact: "Cambia el cuello de la boquilla",
  before_source: source,
  after_source: { ...source, cell: "C5", text_original: "8\"" },
};

const report: DiffReport = {
  project_id: "proy",
  equipment_id: "eq-1",
  from_revision: "1",
  to_revision: "2",
  summary: { changes: 1, geometry_changes: 1, provenance_changes: 1, document_changes: 1 },
  changes: [change],
  provenance_changes: [{ path: "nozzles.N1.size_nps", note: "otra lectura" }],
  document_changes: [{
    id: "doc-ga",
    before: { id: "doc-ga", filename: "GA-rev1.pdf", revision: "1", sha256: "aaa", page_count: 3 },
    after: { id: "doc-ga", filename: "GA-rev2.pdf", revision: "2", sha256: "bbb", page_count: 4 },
  }],
  before_sha256: "sha-antes",
  after_sha256: "sha-despues",
};

const entries: HistoryExportEntry[] = [
  {
    key: "plano:1:2",
    kind: "plano",
    title: "Rev 1 → Rev 2 del plano GA",
    detail: "1 cambio leído",
    author: "TrazIA · lectura automática del plano",
    at: 1_700_000_000,
    revision: "2",
    fromUrl: "/ifc/rev1.ifc",
    toUrl: "/ifc/rev2.ifc",
    changes: report,
  },
  {
    key: "proposal:p1",
    kind: "propuesta",
    title: "Subir el faldón",
    detail: "Rev 1 → Rev 2",
    author: "Ana Ruiz",
    at: 1_700_000_100,
    revision: "2",
    fromUrl: "/ifc/a.ifc",
    toUrl: "/ifc/b.ifc",
    diff: { from: "proy:eq:1", to: "proy:eq:2" },
    diffError: "No se pudo leer el diff",
  },
];

function rowsOf(name: string, entriesIn: HistoryExportEntry[] = entries): string[][] {
  const found = historySheets(entriesIn).find((sheet) => sheet.name === name);
  if (!found) throw new Error(name);
  return found.rows;
}

describe("excel del historial", () => {
  it("conserva la entrada, el campo, la fuente, el documento y la procedencia", () => {
    const entradas = rowsOf("Entradas");
    const campos = rowsOf("Campos");
    const documentos = rowsOf("Documentos");
    const procedencia = rowsOf("Procedencia");
    expect(entradas[0]).toEqual(expect.arrayContaining([
      "clave", "autor", "fecha_iso", "fecha_unix", "ifc_antes", "ifc_despues",
      "diff_desde", "diff_hasta", "error_diff", "sha256_antes", "json_entrada",
    ]));
    expect(entradas[1]).toEqual(expect.arrayContaining([
      "plano:1:2", "TrazIA · lectura automática del plano", "/ifc/rev1.ifc", "sha-antes",
    ]));
    expect(entradas[2]).toEqual(expect.arrayContaining(["proposal:p1", "Ana Ruiz", "proy:eq:1", "No se pudo leer el diff"]));
    expect(entradas[2]?.at(-1)).toContain("Subir el faldón");

    const header = campos[0] ?? [];
    for (const name of ["ruta", "operacion", "valor_antes", "unidad_antes", "valor_despues", "antes_localizador", "antes_prompt_sha256", "antes_diseno_propuesta", "despues_celda", "despues_texto_original", "json_cambio", "antes_json_fuente"]) {
      expect(header.some((column) => column === name || column.startsWith(`${name}`))).toBe(true);
    }
    expect(header).toEqual(expect.arrayContaining(["antes_json_fuente", "despues_json_fuente"]));
    expect(campos[1]).toEqual(expect.arrayContaining([
      "plano:1:2", "nozzles.N1.size_nps", "modified", "8", "6", "boquillas/N1", "abc123", "prop-1", "C5", "8\"",
    ]));
    expect((campos[1] ?? []).join("\n")).toContain("Cambia el cuello de la boquilla");

    expect(documentos[1]).toEqual(expect.arrayContaining(["doc-ga", "GA-rev1.pdf", "aaa", "GA-rev2.pdf", "bbb"]));
    expect((procedencia[1] ?? []).join("")).toContain("otra lectura");
    expect(campos).toHaveLength(2);
  });

  it("no corta un texto que supera el límite de una celda de Excel", () => {
    const long = "x".repeat(32_000) + "FIN-DEL-IMPACTO";
    const base = entries[0];
    if (!base) throw new Error("falta la entrada");
    const campos = rowsOf("Campos", [{
      ...base,
      changes: { ...report, changes: [{ ...change, impact: long }] },
    }]);
    expect(campos.flat().join("")).toContain("FIN-DEL-IMPACTO");
    expect((campos[0] ?? []).some((column) => column.startsWith("impacto"))).toBe(true);
    expect(Math.max(0, ...(campos[1] ?? []).map((cell) => cell.length))).toBeLessThanOrEqual(32_000);
  });

  it("escribe un xlsx con las cuatro hojas y el nombre del equipo", () => {
    const bytes = historyXlsx(entries);
    const xml = new TextDecoder().decode(bytes);
    expect(String.fromCharCode(bytes[0] ?? 0, bytes[1] ?? 0)).toBe("PK");
    expect(xml).toContain("name=\"Entradas\"");
    expect(xml).toContain("name=\"Campos\"");
    expect(xml).toContain("name=\"Documentos\"");
    expect(xml).toContain("name=\"Procedencia\"");
    expect(xml).toContain("nozzles.N1.size_nps");
    expect(xml).toContain("prompt_sha256");
    expect(xml).toContain("Ana Ruiz");
    expect(historyFilename("BP-T-710")).toBe("historial-BP-T-710.xlsx");
    expect(historyFilename("tag con espacios")).toBe("historial-tag_con_espacios.xlsx");
  });
});

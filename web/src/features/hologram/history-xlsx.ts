/*
  Libro Excel (.xlsx, OOXML sin comprimir) del historial de cambios.
  Cada entrada, cada campo y cada fuente van en hojas propias, y además
  el JSON completo, partido si una celda pasa el límite de Excel.
*/
import type { DiffReport, DocumentSnapshot, FieldChange } from "@/lib/mock/diff-types";
import type { Source } from "@/lib/types/revision";

export type HistoryExportEntry = {
  key: string;
  kind: string;
  title: string;
  detail: string;
  author: string;
  at?: number;
  revision: string;
  fromUrl: string;
  toUrl: string;
  changes?: DiffReport;
  diff?: { from: string; to: string };
  diffError?: string;
};

const CELL_LIMIT = 32000;

const KIND_LABEL: Record<string, string> = {
  plano: "Revisión del plano",
  edicion: "Corrección",
  aprobacion: "Aprobación",
  deshacer: "Deshecho",
  propuesta: "Cambio de diseño",
};

function clean(value: string): string {
  return value.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
}

function text(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return clean(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return clean(JSON.stringify(value) ?? "");
}

function expand(header: string[], data: string[][]): string[][] {
  const chunks = header.map((_, col) =>
    Math.max(1, ...data.map((row) => Math.ceil((row[col]?.length ?? 0) / CELL_LIMIT) || 1)),
  );
  const width = (col: number) => chunks[col] ?? 1;
  const head = header.flatMap((name, col) =>
    Array.from({ length: width(col) }, (_, i) => (i === 0 ? name : `${name} (${i + 1})`)),
  );
  const body = data.map((row) =>
    header.flatMap((_, col) => {
      const cell = row[col] ?? "";
      const parts: string[] = [];
      for (let i = 0; i < width(col); i++) parts.push(cell.slice(i * CELL_LIMIT, (i + 1) * CELL_LIMIT));
      return parts;
    }),
  );
  return [head, ...body];
}

function sourceCells(source: Source | null): string[] {
  const design = source?.design;
  return [
    text(source?.document_id),
    text(source?.page),
    text(source?.sheet),
    text(source?.cell),
    text(source?.locator),
    text(source?.bbox),
    text(source?.confidence),
    text(source?.reviewed),
    text(source?.confidence_raw),
    text(source?.channel),
    text(source?.strategy),
    text(source?.model),
    text(source?.prompt_sha256),
    text(source?.grounded),
    text(source?.text_original),
    text(source?.unit_original),
    text(design?.kind),
    text(design?.proposal_id),
    text(design?.operation_id),
    text(source),
  ];
}

const SOURCE_HEADERS = [
  "documento",
  "pagina",
  "hoja",
  "celda",
  "localizador",
  "bbox",
  "confianza",
  "revisado",
  "confianza_bruta",
  "canal",
  "estrategia",
  "modelo",
  "prompt_sha256",
  "grounded",
  "texto_original",
  "unidad_original",
  "diseno_tipo",
  "diseno_propuesta",
  "diseno_operacion",
  "json_fuente",
];

function snapshotCells(prefix: string, snap: DocumentSnapshot | null): { header: string[]; cells: string[] } {
  return {
    header: [`${prefix}_id`, `${prefix}_fichero`, `${prefix}_revision`, `${prefix}_sha256`, `${prefix}_paginas`, `${prefix}_json`],
    cells: [text(snap?.id), text(snap?.filename), text(snap?.revision), text(snap?.sha256), text(snap?.page_count), text(snap)],
  };
}

function whenIso(seconds?: number): string {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function whenLocal(seconds?: number): string {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("es-ES", { dateStyle: "short", timeStyle: "medium" });
}

/** Hojas del libro: entradas, campos, documentos citados y procedencia. */
export function historySheets(entries: HistoryExportEntry[]): { name: string; rows: string[][] }[] {
  const entradasHeader = [
    "clave",
    "tipo",
    "tipo_etiqueta",
    "titulo",
    "detalle",
    "autor",
    "fecha_unix",
    "fecha_iso",
    "fecha",
    "revision",
    "ifc_antes",
    "ifc_despues",
    "diff_desde",
    "diff_hasta",
    "error_diff",
    "proyecto",
    "equipo",
    "revision_origen",
    "revision_destino",
    "resumen_cambios",
    "resumen_geometria",
    "resumen_procedencia",
    "resumen_documentos",
    "sha256_antes",
    "sha256_despues",
    "json_entrada",
  ];
  const entradas = entries.map((entry) => {
    const report = entry.changes;
    return [
      entry.key,
      entry.kind,
      KIND_LABEL[entry.kind] ?? entry.kind,
      entry.title,
      entry.detail,
      entry.author,
      text(entry.at),
      whenIso(entry.at),
      whenLocal(entry.at),
      entry.revision,
      entry.fromUrl,
      entry.toUrl,
      entry.diff?.from ?? "",
      entry.diff?.to ?? "",
      entry.diffError ?? "",
      report?.project_id ?? "",
      report?.equipment_id ?? "",
      report?.from_revision ?? "",
      report?.to_revision ?? "",
      text(report?.summary.changes),
      text(report?.summary.geometry_changes),
      text(report?.summary.provenance_changes),
      text(report?.summary.document_changes),
      report?.before_sha256 ?? "",
      report?.after_sha256 ?? "",
      text(entry),
    ];
  });

  const camposHeader = [
    "clave_entrada",
    "indice",
    "ruta",
    "operacion",
    "valor_antes",
    "unidad_antes",
    "valor_despues",
    "unidad_despues",
    "afecta_geometria",
    "impacto",
    ...SOURCE_HEADERS.map((name) => `antes_${name}`),
    ...SOURCE_HEADERS.map((name) => `despues_${name}`),
    "json_cambio",
  ];
  const campos: string[][] = [];
  const documentosHeader = [
    "clave_entrada",
    "indice",
    "id",
    ...snapshotCells("antes", null).header,
    ...snapshotCells("despues", null).header,
    "json_documento",
  ];
  const documentos: string[][] = [];
  const procedenciaHeader = ["clave_entrada", "indice", "json_procedencia"];
  const procedencia: string[][] = [];

  for (const entry of entries) {
    const report = entry.changes;
    if (!report) continue;
    report.changes.forEach((change, index) => {
      campos.push(changeRow(entry.key, index, change));
    });
    report.document_changes.forEach((doc, index) => {
      documentos.push([
        entry.key,
        String(index + 1),
        doc.id,
        ...snapshotCells("antes", doc.before).cells,
        ...snapshotCells("despues", doc.after).cells,
        text(doc),
      ]);
    });
    report.provenance_changes.forEach((item, index) => {
      procedencia.push([entry.key, String(index + 1), text(item)]);
    });
  }

  return [
    { name: "Entradas", rows: expand(entradasHeader, entradas) },
    { name: "Campos", rows: expand(camposHeader, campos) },
    { name: "Documentos", rows: expand(documentosHeader, documentos) },
    { name: "Procedencia", rows: expand(procedenciaHeader, procedencia) },
  ];
}

function changeRow(key: string, index: number, change: FieldChange): string[] {
  return [
    key,
    String(index + 1),
    change.path,
    change.operation,
    text(change.before?.value),
    change.before?.unit ?? "",
    text(change.after?.value),
    change.after?.unit ?? "",
    change.affects_geometry ? "sí" : "no",
    change.impact,
    ...sourceCells(change.before_source),
    ...sourceCells(change.after_source),
    text(change),
  ];
}

function colName(index: number): string {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function xmlEscape(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function sheetXml(rows: string[][]): string {
  const body = rows
    .map((row, r) => {
      const cells = row
        .map((value, c) => `<c r="${colName(c)}${r + 1}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value)}</t></is></c>`)
        .join("");
      return `<row r="${r + 1}">${cells}</row>`;
    })
    .join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${body}</sheetData></worksheet>`;
}

function crc32(data: Uint8Array): number {
  let crc = ~0;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return ~crc >>> 0;
}

function buildZip(items: { name: string; data: Uint8Array }[]): Uint8Array {
  const encoder = new TextEncoder();
  const locals: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const item of items) {
    const name = encoder.encode(item.name);
    const crc = crc32(item.data);
    const local = new Uint8Array(30 + name.length);
    const view = new DataView(local.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(8, 0, true);
    view.setUint32(14, crc, true);
    view.setUint32(18, item.data.length, true);
    view.setUint32(22, item.data.length, true);
    view.setUint16(26, name.length, true);
    local.set(name, 30);
    locals.push(local, item.data);
    const cen = new Uint8Array(46 + name.length);
    const cenView = new DataView(cen.buffer);
    cenView.setUint32(0, 0x02014b50, true);
    cenView.setUint16(4, 20, true);
    cenView.setUint16(6, 20, true);
    cenView.setUint32(16, crc, true);
    cenView.setUint32(20, item.data.length, true);
    cenView.setUint32(24, item.data.length, true);
    cenView.setUint16(28, name.length, true);
    cenView.setUint32(42, offset, true);
    cen.set(name, 46);
    central.push(cen);
    offset += local.length + item.data.length;
  }
  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, items.length, true);
  endView.setUint16(10, items.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  const out = new Uint8Array(offset + centralSize + end.length);
  let cursor = 0;
  for (const part of locals) {
    out.set(part, cursor);
    cursor += part.length;
  }
  for (const part of central) {
    out.set(part, cursor);
    cursor += part.length;
  }
  out.set(end, cursor);
  return out;
}

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>`;

/** Fichero .xlsx con las cuatro hojas del historial. El XML va sin comprimir para que Excel lo abra igual. */
export function historyXlsx(entries: HistoryExportEntry[]): Uint8Array {
  const sheets = historySheets(entries);
  const encoder = new TextEncoder();
  const sheetParts = sheets.map((sheet, index) => ({
    name: `xl/worksheets/sheet${index + 1}.xml`,
    data: encoder.encode(sheetXml(sheet.rows)),
  }));
  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>${sheets.map((sheet, index) => `<sheet name="${xmlEscape(sheet.name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join("")}</sheets>
</workbook>`;
  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  ${sheets.map((_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`).join("")}
  <Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  ${sheets.map((_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")}
</Types>`;
  const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;
  return buildZip([
    { name: "[Content_Types].xml", data: encoder.encode(contentTypes) },
    { name: "_rels/.rels", data: encoder.encode(rootRels) },
    { name: "xl/workbook.xml", data: encoder.encode(workbook) },
    { name: "xl/_rels/workbook.xml.rels", data: encoder.encode(rels) },
    { name: "xl/styles.xml", data: encoder.encode(STYLES) },
    ...sheetParts,
  ]);
}

export function historyFilename(tag: string): string {
  const safe = tag.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "equipo";
  return `historial-${safe}.xlsx`;
}

export function downloadHistory(entries: HistoryExportEntry[], tag: string) {
  const bytes = historyXlsx(entries);
  const blob = new Blob([Uint8Array.from(bytes)], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = historyFilename(tag);
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

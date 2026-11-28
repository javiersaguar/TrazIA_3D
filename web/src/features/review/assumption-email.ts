import type { ReviewField } from "@/lib/mock/fields";
import type { Document } from "@/lib/types/revision";

type Assumption = Pick<ReviewField, "label" | "status" | "value" | "correctedValue" | "unit" | "source">;

export function draftAssumptionEmail(scope: { tag: string; revision: string; project?: string },
  fields: readonly Assumption[], documents: readonly Pick<Document, "id" | "filename">[] = []) {
  const context = [scope.project, scope.tag, `rev. ${scope.revision}`].filter(Boolean).join(" · ");
  const numbers = new Intl.NumberFormat("es-ES", { maximumSignificantDigits: 21 });
  const details = fields.filter(field => field.status === "assumed").map(field => {
    const value = field.correctedValue ?? field.value;
    const unit = field.unit === "1" || !field.unit ? "" : ` ${field.unit}`;
    const document = documents.find(doc => doc.id === field.source.document_id);
    const reference = document ? ` (${document.filename}${field.source.page ? `, pág. ${field.source.page}` : ""})` : "";
    return `- ${field.label}: ${typeof value === "number" ? numbers.format(value) : value}${unit}${reference}.`;
  });
  return {
    subject: `Confirmación de datos de plano · ${context}`,
    body: [
      "Hola,",
      `Estamos revisando ${context}. La documentación disponible no permite confirmar los siguientes datos. Estos son los valores provisionales utilizados en el modelo IFC en borrador:`,
      details.join("\n"),
      "¿Podéis confirmar o corregir estos valores y enviarnos el plano, el detalle o la hoja de datos que los justifique? Si procede, indicad la unidad y la referencia desde la que se mide la cota.",
      "Gracias.",
    ].join("\n\n"),
  };
}

export function assumptionMailto(subject: string, body: string) {
  const href = `mailto:?subject=${encodeURIComponent(subject.replace(/[\r\n]+/g, " "))}&body=${encodeURIComponent(body.replace(/\r?\n/g, "\r\n"))}`;
  return href.length <= 2000 ? href : null;
}

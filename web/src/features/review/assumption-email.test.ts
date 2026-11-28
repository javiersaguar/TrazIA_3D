import { describe, expect, it } from "vitest";
import { flattenRevision } from "@/lib/mock/fields";
import type { Revision } from "@/lib/types/revision";
import sample from "../../../public/demo/json/vessel_rev_b.json";
import { assumptionMailto, draftAssumptionEmail } from "./assumption-email";

describe("correo de supuestos", () => {
  it("incluye solo supuestos de la revisión, con valores efectivos y fuentes disponibles", () => {
    const revision = sample as unknown as Revision;
    const fields = flattenRevision(revision);
    const diameter = fields.find(field => field.path === "diameter")!;
    const length = fields.find(field => field.path === "height")!;
    const draft = draftAssumptionEmail(
      { tag: "V-101", revision: "B", project: "DEMO-PLANT" },
      [
        { ...diameter, status: "assumed", correctedValue: 2200 },
        { ...length, status: "accepted" },
        { ...diameter, label: "Tipo de apoyo", status: "assumed", unit: "1", value: "Faldón", source: { ...diameter.source, document_id: "REGLA" } },
      ],
      revision.documents,
    );
    expect(draft.subject).toContain("DEMO-PLANT · V-101 · rev. B");
    expect(draft.body).toContain(`${diameter.label}: 2200 mm (GAD_V-101_revB.pdf, pág. 1)`);
    expect(draft.body).toContain("Tipo de apoyo: Faldón.");
    expect(draft.body).not.toContain(length.label);
    expect(draft.body).not.toContain("REGLA");
    expect(draft.body).toContain("¿Podéis confirmar o corregir");
  });

  it("abre un borrador sin destinatario y deja copiable un texto largo", () => {
    expect(assumptionMailto("Revisión\r\nBcc: otro", "Cota & dato\nGracias."))
      .toBe("mailto:?subject=Revisi%C3%B3n%20Bcc%3A%20otro&body=Cota%20%26%20dato%0D%0AGracias.");
    expect(assumptionMailto("Asunto", "á".repeat(1000))).toBeNull();
  });
});

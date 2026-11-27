import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { auditChange, autoAccepted } from "./change-history";

// Recipiente sintético de los ejemplos del repositorio (V-101); no hay datos de TR.
const before = JSON.parse(readFileSync(new URL("../../../../examples/vessel_rev_a.json", import.meta.url), "utf8"));

describe("historial de cambios", () => {
  it("convierte una corrección de la auditoría en el cambio que anima el visor", () => {
    const after = structuredClone(before);
    after.equipment.height.value = before.equipment.height.value + 250;
    const change = auditChange({ path: "height", before_json: JSON.stringify(before), after_json: JSON.stringify(after) });
    expect(change).toMatchObject({
      path: "height",
      operation: "modified",
      before: { value: before.equipment.height.value },
      after: { value: before.equipment.height.value + 250 },
    });
  });

  it("una acción ilegible no rompe el historial", () => {
    expect(auditChange({ path: "height", before_json: "{", after_json: "{}" })).toBeNull();
  });

  it("una aprobación automática lista los campos que pasaron a aceptados", () => {
    const pending = structuredClone(before);
    pending.equipment.height.state = "candidate";
    const after = structuredClone(pending);
    after.equipment.height.state = "accepted";
    after.equipment.height.explanation = "Aprobado automáticamente: confianza 0.95 ≥ 0.90.";
    const changes = autoAccepted({ before_json: JSON.stringify(pending), after_json: JSON.stringify(after) });
    expect(changes.map((c) => c.path)).toContain("height");
    expect(changes.find((c) => c.path === "height")?.before).toEqual(changes.find((c) => c.path === "height")?.after);
  });
});

import { describe, expect, it } from "vitest";
import type { ReviewField } from "@/lib/mock/fields";
import { drawingAnnotations } from "./drawing-annotations";

function field(path: string, value: number, rule: string, text: string, unit = "mm"): ReviewField {
  const source = { document_id: "GA-DEMO", page: 1, locator: text, confidence: .95, rule, text_original: text };
  return { path, value, unit, source, label: path, confidence: .95,
    group: "Envolvente", elementId: "shell", impact: 1, risk: 0, status: "candidate", abstained: false, calibrated: false };
}

describe("cotas citadas del plano", () => {
  it("mantiene las cotas al eje y a la tangente y el ángulo original", () => {
    const fields = [
      field("nozzles.N1.projection", 205, "virola.proyeccion_desde_eje", "615"),
      field("nozzles.N1.elevation", 2750, "virola.cota_desde_tangente", "EL.+ 1750"),
      field("nozzles.N1.azimuth", 0, "vertical.azimut_desde_norte", "N1 · 90° desde N en sentido horario", "deg"),
      field("nozzles.N2.projection", 615, "regla", "615"),
    ];
    expect(drawingAnnotations(fields, "detail:nozzle:N1/brida", false)).toMatchObject([
      { productId: "nozzle:N1", value: 205, drawingValue: 615 },
      { productId: "nozzle:N1", value: 2750, drawingValue: 1750 },
      { productId: "nozzle:N1", value: 0, drawingValue: 90, clockwise: true },
    ]);
  });

  it("conserva el diámetro interior citado y omite interpretaciones ambiguas", () => {
    const fields = [
      field("diameter", 1024, "vertical.diametro_exterior", "SHELL ØINT. 1000 mm · THK. 12"),
      { ...field("height", 3000, "regla", "L=3000"), conflict: true },
    ];
    expect(drawingAnnotations(fields, "shell", false)).toMatchObject([{ value: 1024, drawingValue: 1000 }]);
    expect(drawingAnnotations([field("nozzles.N1.projection", 205, "virola.proyeccion_desde_eje", "610 / 615")], "nozzle:N1", false)).toEqual([]);
  });
});

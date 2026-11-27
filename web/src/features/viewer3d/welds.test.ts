import { describe, expect, it } from "vitest";
import { elementLabel, semanticId } from "./semantic";
import { isWeld, weldInfo, weldSummary } from "./welds";

// Pset con la forma que escribe src/trazia/ifc.py (_welds); valores inventados, recipiente D-1.
const psets = {
  TrazIA_Soldadura: {
    Tipo: "nozzle",
    Une: "N1|SHELL",
    Estado: "assumed",
    Regla: "soldadura.boquilla_virola",
    Tamano: "",
    Nota: "",
    CotaDesdeTL_mm: 1200,
    SinGeometria: false,
    RequiereVerificacion: true,
    CitasJSON: JSON.stringify({
      kind: { document_id: "GA-D1", page: 1, locator: "N1" },
      elevation: { document_id: "GA-D1", page: 1, locator: "N1" },
    }),
  },
};

describe("soldaduras del IFC", () => {
  it("se identifican por su Tag y no se confunden con una boquilla", () => {
    const id = semanticId("D-1/W:N1|SHELL", "IFCFASTENER", psets, "W:N1|SHELL");
    expect(id).toBe("weld:W:N1|SHELL");
    expect(elementLabel(id)).toBe("Soldadura W:N1|SHELL");
    expect(isWeld({ ifcType: "IfcFastener", psets })).toBe(true);
    expect(isWeld({ ifcType: "IFCFASTENER", psets: {} })).toBe(false);
  });

  it("dicen qué unen, dónde y de qué plano salen", () => {
    const info = weldInfo("W:N1|SHELL", psets)!;
    expect(info.joins).toEqual(["N1", "SHELL"]);
    expect(info.elevationMm).toBe(1200);
    expect(info.sources).toEqual([{ document: "GA-D1", page: 1, locator: "N1" }]);
    expect(weldSummary(info)).toBe(
      "Boquilla–virola: une N1 y la virola · cota 1200 mm desde T.L. · GA-D1, p. 1 · inferida, a verificar",
    );
  });

  it("sin cota ni citas legibles sigue siendo una soldadura", () => {
    const info = weldInfo("W:C1|C2", {
      TrazIA_Soldadura: { Tipo: "circumferential", Une: "C1|C2", CotaDesdeTL_mm: -1, CitasJSON: "{", RequiereVerificacion: false },
    })!;
    expect(info.elevationMm).toBeUndefined();
    expect(info.sources).toEqual([]);
    expect(weldSummary(info)).toBe("Costura circunferencial: une C1 y C2");
  });
});

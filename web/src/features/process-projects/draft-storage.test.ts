import { describe, expect, it } from "vitest";
import { parseDraft } from "./draft-storage";

const change = { id: 1, step: 1, tag: "V-110", field: "length", before: 9, after: 9.9, at: "10:00:00" };

describe("borrador guardado en el navegador", () => {
  it("recupera el historial y los parámetros para regenerar el IFC", () => {
    const saved = parseDraft(JSON.stringify({
      version: 1, applied: ["P-150"], adjustments: [{ tag: "V-110", field: "length", value: 9.9 }], history: [change],
    }));
    expect(saved?.history).toEqual([change]);
    expect(saved?.adjustments).toEqual([{ tag: "V-110", field: "length", value: 9.9 }]);
    expect(saved?.applied).toEqual(["P-150"]);
  });

  it("descarta lo que no encaja sin romper la página", () => {
    expect(parseDraft(null)).toBeNull();
    expect(parseDraft("{no es json")).toBeNull();
    expect(parseDraft(JSON.stringify({ version: 2, applied: [], adjustments: [], history: [] }))).toBeNull();
    const saved = parseDraft(JSON.stringify({
      version: 1, applied: [], adjustments: [{ tag: "V-110", field: "length", value: 9.9 }],
      history: [change, { ...change, id: 2, field: "otra" }, { ...change, id: 3, after: "9" }],
    }));
    expect(saved?.history).toHaveLength(1);
  });
});

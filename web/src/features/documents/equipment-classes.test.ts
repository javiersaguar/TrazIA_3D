import { describe, expect, it } from "vitest";
import { classOf, familyKey, groupByClass, sameFamily } from "./equipment-classes";

describe("clases de equipo", () => {
  it("junta el id del catálogo, la clave del lote y la etiqueta de la API en la misma familia", () => {
    expect(familyKey("vertical_vessel")).toBe("vertical");
    expect(familyKey("Recipiente vertical")).toBe("vertical");
    expect(sameFamily("vertical", "vertical_vessel")).toBe(true);
    expect(sameFamily("vertical", "tank")).toBe(false);
  });

  it("agrupa por el código de la industria y deja al final lo que no tiene código", () => {
    const groups = groupByClass(
      [
        { id: "pump" },
        { id: "vertical" },
        { id: "tank" },
        { id: "propia" },
        { id: "column" },
        { id: "air-cooler" },
      ],
      (item) => item.id,
    );
    expect(groups.map((group) => group.cls.title)).toEqual([
      "Recipientes a presión",
      "Columnas",
      "Tanques de almacenamiento",
      "Transferencia de calor",
      "Equipos rotativos",
      "Envolventes y sin clasificar",
    ]);
    expect(classOf("tank").standard).toBe("API 650");
    expect(classOf("air-cooler").standard).toContain("API 661");
    expect(groups.at(-1)?.items.map((item) => item.id)).toEqual(["propia"]);
  });
});

import { describe, expect, it } from "vitest";
import { fieldLabel } from "./field-labels";

describe("fieldLabel", () => {
  it("nombra los campos de pieza con el mismo patrón", () => {
    expect(fieldLabel("nozzles.M1.rating")).toBe("Boquilla M1 · Clase de brida");
    expect(fieldLabel("shell.courses.V03.thickness")).toBe("Virola V03 · Espesor");
    expect(fieldLabel("column.sections.V11.diameter")).toBe("Tramo de columna V11 · Diámetro");
    expect(fieldLabel("tank.courses.2.thickness")).toBe("Virola 2 del tanque · Espesor");
    expect(fieldLabel("welds.W:K1|SHELL.kind")).toBe("Soldadura K1 – SHELL · Tipo");
    expect(fieldLabel("horizontal.saddle_positions.0")).toBe("Silleta 1 · Posición");
  });

  it("traduce atributos y dimensiones, y nunca devuelve la ruta en bruto", () => {
    expect(fieldLabel("attributes.weight_empty")).toBe("Peso en vacío");
    expect(fieldLabel("horizontal.length")).toBe("Longitud entre tangentes");
    expect(fieldLabel("attributes.otra_cosa")).toBe("Otra cosa");
    expect(fieldLabel("legs.algo_nuevo")).not.toContain(".");
  });
});

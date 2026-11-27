import { describe, expect, it } from "vitest";
import { PRELIMINARY_PREFIX, splitPreliminary } from "./preliminary";

describe("valores preliminares del trabajo", () => {
  it("saca las rutas del aviso y deja el resto de avisos", () => {
    const warnings = ["Tag tomado del nombre del archivo: BOMBA.", `${PRELIMINARY_PREFIX}diameter, height, horizontal.saddle_positions.0.`];
    expect(splitPreliminary(warnings)).toEqual({
      preliminary: ["diameter", "height", "horizontal.saddle_positions.0"],
      others: ["Tag tomado del nombre del archivo: BOMBA."],
    });
  });
  it("sin aviso no hay preliminares", () => {
    expect(splitPreliminary(["Otro aviso."]).preliminary).toEqual([]);
  });
});

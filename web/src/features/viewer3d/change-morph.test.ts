import { BoxGeometry } from "three";
import { describe, expect, it } from "vitest";
import type { Vec3 } from "@/workers/ifc-protocol";
import { changeMorph, MORPH_SECONDS, morphElapsed, morphProgress, morphTransform } from "./change-morph";

const shape = (globalId: string, min: Vec3, max: Vec3) => ({
  globalId, semanticId: `part:${globalId}`, bounds: { min, max },
  name: globalId, expressId: 0, ifcType: "IfcBuildingElementProxy", psets: {}, parts: [],
  geometries: [new BoxGeometry(max[0] - min[0], max[1] - min[1], max[2] - min[2])],
  center: min.map((v, i) => (v + max[i]!) / 2) as Vec3,
});

describe("transformación de un borrador en el visor de planta", () => {
  it("anima solo las piezas que cambian, desde su envolvente anterior", () => {
    const before = [shape("a", [0, 0, 0], [9, 4, 4]), shape("b", [20, 0, 0], [22, 2, 2])];
    const after = [shape("a", [-0.45, 0, 0], [9.45, 4, 4]), shape("b", [20, 0, 0], [22, 2, 2])];
    const morph = changeMorph(before, after, "draft")!;
    expect([...morph.from.keys()]).toEqual(["part:a"]);
    const from = morph.from.get("part:a")!;
    expect(from.scale[0]).toBeCloseTo(9 / 9.9, 6);
    expect(from.offset).toEqual([0, 0, 0]);
    // Empieza en la forma anterior y termina exacta en la del IFC nuevo.
    expect(morphTransform(from, 0).scale[0]).toBeCloseTo(9 / 9.9, 6);
    expect(morphTransform(from, 1).scale).toEqual([1, 1, 1]);
  });

  it("no anima cargas sin piezas comunes ni modelos idénticos", () => {
    const a = [shape("a", [0, 0, 0], [1, 1, 1])];
    expect(changeMorph(a, [shape("z", [0, 0, 0], [2, 2, 2])], "x")).toBeNull();
    expect(changeMorph(a, a, "x")).toBeNull();
  });

  it("recorre la curva en el tiempo previsto", () => {
    expect(morphProgress(0)).toBe(0);
    expect(morphProgress(MORPH_SECONDS)).toBe(1);
    const clock = { start: -1 };
    expect(morphElapsed(clock, 5)).toBe(0);
    expect(morphElapsed(clock, 6.5)).toBe(1.5);
  });
});

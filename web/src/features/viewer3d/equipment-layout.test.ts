import { describe, expect, it } from "vitest";
import type { Bounds, IfcPart, Vec3 } from "@/workers/ifc-protocol";
import { equipmentFrame, explosionOffsets, placedDimension } from "./equipment-layout";

function piece(semanticId: string, min: Vec3, max: Vec3) {
  const center = min.map((value, i) => (value + max[i]!) / 2) as Vec3;
  const positions = new Float32Array([min, max].flatMap(vertex => vertex.map((value, i) => value - center[i]!)));
  const part: IfcPart = { positions, normals: new Float32Array(), indices: new Uint32Array(), color: [1, 1, 1, 1] };
  return { semanticId, center, bounds: { min, max }, parts: [part] };
}

const horizontal = [
  piece("shell", [4, .5, 9.2], [8.8, 2.1, 10.8]),
  piece("head-bottom", [3.6, .5, 9.2], [4, 2.1, 10.8]),
  piece("head-top", [8.8, .5, 9.2], [9.2, 2.1, 10.8]),
  piece("element:saddle-1", [5, 0, 9.4], [5.4, .8, 10.6]),
  piece("nozzle:N1", [5.8, 2.1, 9.8], [6.2, 2.8, 10.2]),
  piece("nozzle:N2", [7.8, 2.1, 9.8], [8.2, 2.8, 10.2]),
  piece("detail:nozzle:N1/N1/flange", [5.7, 2.75, 9.7], [6.3, 2.9, 10.3]),
];
const bounds: Bounds = { min: [3.6, 0, 9.2], max: [9.2, 2.9, 10.8] };
const measure = (id: string, value: number, state = "candidate") => ({
  id, value, state, label: id, unit: "mm", confidence: .75,
});

describe("cotas y explosionado de un recipiente", () => {
  it("separa fondos, silleta y boquillas según el eje horizontal del IFC", () => {
    expect(equipmentFrame(horizontal)?.horizontal).toBe(true);
    const offsets = explosionOffsets(horizontal);
    expect(offsets.get("shell")).toEqual([0, 0, 0]);
    expect(offsets.get("head-top")?.[0]).toBeGreaterThan(.8);
    expect(offsets.get("head-bottom")?.[0]).toBeLessThan(-.8);
    expect(offsets.get("element:saddle-1")?.[1]).toBeLessThan(0);
    expect(offsets.get("nozzle:N1")?.[1]).toBeGreaterThan(.8);
    expect(offsets.get("nozzle:N1")?.[0]).toBe(0);
    expect(offsets.get("detail:nozzle:N1/N1/flange")).toEqual(offsets.get("nozzle:N1"));
  });

  it("mide las tangentes, la sección de virola y las tres cotas de una boquilla vertical", () => {
    const length = placedDimension(measure("horizontal.length", 4800), horizontal, bounds, 0);
    expect(length!.anchorTo[0] - length!.anchorFrom[0]).toBeCloseTo(4.8);
    const shell = placedDimension(measure("horizontal.diameter", 1600), horizontal, bounds, 0);
    expect(shell!.anchorTo[1] - shell!.anchorFrom[1]).toBeCloseTo(1.6);
    const diameter = placedDimension(measure("nozzles.N1.diameter", 400), horizontal, bounds, 0);
    expect(diameter!.anchorTo[0] - diameter!.anchorFrom[0]).toBeCloseTo(.4);
    expect(diameter!.anchorTo[1]).toBeCloseTo(diameter!.anchorFrom[1]);
    const projection = placedDimension(measure("nozzles.N1.projection", 700), horizontal, bounds, 0);
    expect(projection!.anchorTo[1] - projection!.anchorFrom[1]).toBeCloseTo(.7);
    const elevation = placedDimension(measure("nozzles.N1.elevation", 2100), horizontal, bounds, 0);
    expect(elevation!.anchorFrom[1]).toBeCloseTo(0);
    expect(elevation!.anchorTo[1]).toBeCloseTo(2.1);
  });

  it("omite coordenadas auxiliares, conflictos y números incompatibles con el IFC", () => {
    for (const annotation of [
      measure("nozzles.N1.position.y", 0), measure("nozzles.N1.projection", 0),
      measure("horizontal.length", 4800, "conflict"), measure("nozzles.N1.projection", 1600),
    ]) {
      expect(placedDimension(annotation, horizontal, bounds, 0)).toBeNull();
    }
  });

  it("conserva el explosionado axial y las boquillas radiales en recipientes verticales", () => {
    const upright = [
      piece("shell", [-1, 1, -1], [1, 5, 1]),
      piece("head-top", [-1, 5, -1], [1, 5.5, 1]),
      piece("head-bottom", [-1, .5, -1], [1, 1, 1]),
      piece("skirt", [-1, 0, -1], [1, 1, 1]),
      piece("nozzle:N5", [1, 2, -.2], [1.4, 2.4, .2]),
    ];
    const offsets = explosionOffsets(upright);
    expect(equipmentFrame(upright)?.horizontal).toBe(false);
    expect(offsets.get("head-top")).toEqual([0, 1.1, 0]);
    expect(offsets.get("skirt")?.[1]).toBeLessThan(0);
    expect(offsets.get("nozzle:N5")).toEqual([1.1, 0, 0]);
  });
});

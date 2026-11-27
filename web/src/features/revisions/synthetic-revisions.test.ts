import { BoxGeometry } from "three";
import { describe, expect, it, vi } from "vitest";
import type { PreparedProduct } from "@/features/viewer3d/model-resource";
import type { Vec3 } from "@/workers/ifc-protocol";
import type { EquipmentRow } from "@/lib/mock/api";
import { projectModels } from "./project-models";
import { revisionsFor } from "./revision-states";
import { applyRevision, changesBetween, releaseSynthetic } from "./synthetic-revisions";

function piece(id: string, semanticId: string, center: Vec3, size: Vec3 = [0.4, 0.4, 0.4]): PreparedProduct {
  return {
    expressId: 1,
    globalId: id,
    name: semanticId,
    ifcType: "IfcBuildingElementProxy",
    semanticId,
    psets: {},
    center,
    bounds: {
      min: center.map((value, i) => value - size[i]! / 2) as Vec3,
      max: center.map((value, i) => value + size[i]! / 2) as Vec3,
    },
    parts: [],
    geometries: [new BoxGeometry(...size)],
  };
}

const model = () => [
  piece("shell", "shell", [0, 4, 0], [2, 6, 2]),
  piece("skirt", "skirt", [0, 0.6, 0], [2.1, 1.2, 2.1]),
  piece("n1", "nozzle:N1", [1.2, 3, 0], [0.5, 0.3, 0.3]),
  piece("flange", "detail:nozzle:N1/flange", [1.45, 3, 0], [0.05, 0.35, 0.35]),
];

describe("estados simulados de un proyecto", () => {
  it("separa la base IFC de cuatro simulaciones firmadas a efectos de la demo", () => {
    const [base, ...simulated] = revisionsFor("INDESIAHACK");
    expect(base).toMatchObject({ index: 0, label: "Base IFC", author: null });
    expect(simulated.map((state) => state.label)).toEqual(["SIM-01", "SIM-02", "SIM-03", "SIM-04"]);
    expect(new Set(simulated.map((state) => state.author)).size).toBe(4);
  });

  it("mantiene el original, mueve la brida con la conexión y alarga la malla del apoyo", () => {
    const source = model();
    const snapshot = source.map((product) => product.center[1]);
    const item = applyRevision(source, 4, "80V01");
    const [shell, skirt, nozzle, flange] = item;
    const delta = Number(changesBetween("80V01", 0, 1, source).changes[0]?.after?.value) / 1000;
    expect(Math.abs(delta)).toBe(0.08);
    expect(applyRevision(source, 0, "80V01")).toBe(source);
    expect(source.map((product) => product.center[1])).toEqual(snapshot);
    expect(shell?.center[1]).toBeCloseTo(4.12);
    expect(nozzle?.center[1]).toBeCloseTo(3.12 + delta);
    expect(flange?.center[1]).toBeCloseTo(3.12 + delta);
    expect(skirt?.bounds.max[1]).toBeCloseTo(1.32);
    const geometry = skirt!.geometries[0]!;
    geometry.computeBoundingBox();
    expect(geometry.boundingBox!.max.y - geometry.boundingBox!.min.y).toBeCloseTo(1.32);
    expect(item.map((product) => product.semanticId)).toEqual(expect.arrayContaining(["simulation:nut", "simulation:reinforcement"]));
    const disposeSource = vi.spyOn(source[1]!.geometries[0]!, "dispose");
    const disposeCopy = vi.spyOn(geometry, "dispose");
    releaseSynthetic(item);
    expect(disposeCopy).toHaveBeenCalledOnce();
    expect(disposeSource).not.toHaveBeenCalled();
  });

  it("usa estación de conexión para un recipiente horizontal", () => {
    const source = [piece("shell", "shell", [0, 1, 0], [8, 2, 2]), piece("n1", "nozzle:N1", [0.5, 2.1, 0])];
    const moved = applyRevision(source, 1, "80V01", true)[1]!;
    expect(Math.abs(moved.center[0] - 0.5)).toBeCloseTo(0.08);
    expect(moved.center[1]).toBe(2.1);
    expect(changesBetween("80V01", 0, 1, source, true).changes[0]?.path).toBe("nozzles.N1.station");
  });

  it("usa cubierta, zócalo y placa cuando el IFC no trae boquillas ni apoyos", () => {
    const source = [
      piece("shell", "shell", [0, 1, 0], [4, 2, 4]),
      piece("roof", "element:roof", [0, 2.2, 0], [4, 0.4, 4]),
    ];
    const final = applyRevision(source, 4, "62T02");
    expect(final.find((product) => product.semanticId === "element:roof")?.bounds.max[1]).toBeCloseTo(2.6);
    expect(final.some((product) => product.semanticId === "simulation:plinth")).toBe(true);
    const change = changesBetween("62T02", 3, 2, source).changes[0];
    expect(change).toMatchObject({ path: "simulation.plate.piece", operation: "removed" });
    releaseSynthetic(final);
  });

  it("compara las versiones de referencia del mismo proyecto y mantiene aparte sus TAG homónimos", () => {
    const row: EquipmentRow = {
      tag: "80V01", kind: "Recipiente horizontal", project_id: "A", equipment_id: "80v01",
      area: "", illustrative: false, status: "draft", ifcUrl: "/latest.ifc", revisions: ["1", "2"],
      revision_meta: { "2": { version: 1, dataset: "real" } },
    };
    const rows: EquipmentRow[] = [
      row,
      { ...row, project_id: "B", equipment_id: "other", ifcUrl: "/different-project.ifc" },
      { ...row, tag: "81V01", equipment_id: "81v01", ifcUrl: "/peer.ifc" },
      { ...row, tag: "Ficticio", equipment_id: "ficticio", revision_meta: { "2": { version: 1, dataset: "synthetic" } } },
    ];
    const options = projectModels(rows, "A", {
      id: "80v01", tag: "80V01", ifcUrl: "/opened.ifc", version: "1", horizontal: true,
    }, true);
    expect(options.map((option) => [option.tag, option.ifcUrl, option.version])).toEqual([
      ["80V01", "/latest.ifc", "2"], ["81V01", "/peer.ifc", "2"],
    ]);
  });
});

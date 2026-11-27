import { describe, expect, it } from "vitest";
import { BoxGeometry, Quaternion, Vector3 } from "three";
import { changeSteps, segmentProgress, timelineAt, transformEase, dimensionText, clampProgress, pairByGlobalId } from "./morph.ts";
import { meshTransition } from "./mesh-transition.ts";
import { revisionTimeline } from "./revision-timeline.ts";
import { semanticId, parentElementId, elementLabel } from "../viewer3d/semantic.ts";

function product(globalId, center, geometry = new BoxGeometry(2, 6, 2), semanticId = `element:${globalId}`) {
  geometry.computeBoundingBox();
  const offset = new Vector3(...center);
  return { globalId, semanticId, center, geometries: [geometry], parts: [],
    bounds: { min: geometry.boundingBox.min.clone().add(offset).toArray(),
      max: geometry.boundingBox.max.clone().add(offset).toArray() } };
}
const match = (before, after) => meshTransition({ before, after });

describe("identidad y correspondencia IFC", () => {
  it("empareja por GUID aunque cambien el orden y el nombre", () => {
    const a = [{ globalId: "a", name: "N3" }, { globalId: "b", name: "Virola" }];
    const b = [{ globalId: "b", name: "Otro tag" }, { globalId: "a", name: "Nueva etiqueta" }];
    expect(pairByGlobalId(a, b).map(p => p.after.name)).toEqual(["Nueva etiqueta", "Otro tag"]);
  });
  it("preserva altas y bajas", () => {
    const pairs = pairByGlobalId([{ globalId: "removed" }], [{ globalId: "new" }]);
    expect(pairs[0].after).toBeNull(); expect(pairs[1].before).toBeNull();
  });
  it("rechaza identificadores ambiguos", () => {
    expect(() => pairByGlobalId([{ globalId: "a" }, { globalId: "a" }], [])).toThrow();
    expect(() => pairByGlobalId([], [{ globalId: "" }])).toThrow();
  });
  it("conserva el contrato semántico de las pantallas", () => {
    expect(semanticId("V-101", "IfcTank")).toBe("shell");
    expect(semanticId("V-101/top_head", "IfcBuildingElementProxy")).toBe("head-top");
    expect(semanticId("V-101/N3", "IfcPipeSegment")).toBe("nozzle:N3");
    expect(semanticId("etiqueta nueva", "IfcPipeSegment", { TrazIA_Identity: { ComponentId: "N4" } })).toBe("nozzle:N4");
  });
});

describe("interpolación de revisiones", () => {
  const mesh = new BoxGeometry(2, 6, 2);
  const a = product("stable", [0, 4.2, 0], mesh);
  it("conserva altas, bajas e identifica una malla idéntica regenerada", () => {
    expect(match(a, product("stable", a.center, mesh.clone())).kind).toBe("static");
    expect(match(a, null).kind).toBe("removed");
    expect(match(null, a).kind).toBe("added");
  });
  it("certifica la traslación y el cambio de cota por vértice", () => {
    const moved = product("stable", [0, 4.6, 0], mesh);
    expect(match(a, moved)).toMatchObject({ kind: "transform", transform: { scale: [1, 1, 1] } });
    const scaled = product("stable", moved.center, mesh.clone().scale(1, 1.25, 1));
    expect(match(a, scaled)).toMatchObject({ kind: "transform", transform: { scale: [1, 1.25, 1] } });
    expect(a.geometries[0].boundingBox.max.y).toBe(3);
  });
  it("conserva la forma cuando la pieza gira", () => {
    const angle = Math.PI / 3;
    const turned = product("stable", [1, 4, 0], mesh.clone().rotateZ(angle));
    const result = match(a, turned);
    expect(result.kind).toBe("transform");
    expect(result.transform.rotation.angleTo(new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), angle))).toBeCloseTo(0, 5);
  });
  it("detecta el cambio de forma aunque la envolvente no cambie", () => {
    const changed = mesh.clone();
    changed.attributes.position.setX(0, 0);
    const replacement = product("stable", a.center, changed);
    expect(replacement.bounds).toEqual(a.bounds);
    expect(match(a, replacement).kind).toBe("replace");
    expect([clampProgress(-1), clampProgress(2), clampProgress(NaN)]).toEqual([0, 1, 0]);
  });
  it("las etiquetas de cambio proceden del delta", () => {
    const steps = changeSteps({ changes: [{ path: "nozzles.N3.elevation", operation: "modified",
      before: { value: 3500, unit: "mm" }, after: { value: 3700, unit: "mm" }, affects_geometry: true }] });
    expect(steps[0]).toMatchObject({ elementId: "nozzle:N3", label: "+200 mm" });
    expect(changeSteps(undefined)).toEqual([]);
  });
});

describe("coreografía segmentada", () => {
  it("asocia el movimiento a la pieza real y separa los campos sin malla", () => {
    const shell = product("shell", [0, 2, 0], undefined, "shell");
    const flange = product("flange", [2, 3, 0], undefined, "detail:nozzle:N3/flange");
    const moved = product("flange", [2, 3.2, 0], flange.geometries[0], flange.semanticId);
    const addition = product("addition", [1, 1, 1]);
    const diff = { changes: [
      { path: "nozzles.N3.elevation", operation: "modified", before: { value: 3000, unit: "mm" }, after: { value: 3200, unit: "mm" }, affects_geometry: true },
      { path: "nozzles.K5.service", operation: "removed", before: { value: "Serv.", unit: "" }, after: null, affects_geometry: true },
    ] };
    const { pairs, steps } = revisionTimeline([shell, flange], [shell, moved, addition], diff, false);
    expect(steps.map(step => step.elementId)).toEqual(["nozzle:K5", "nozzle:N3", "element:addition"]);
    expect(steps[0].bounds).toBeNull();
    expect(steps[1].bounds).toEqual({ min: flange.bounds.min, max: moved.bounds.max });
    expect(pairs.map(entry => entry.index)).toEqual([-1, 1, 2]);
  });
  it("transforma solo el elemento de su segmento y permite retroceder", () => {
    expect(timelineAt(.4, 3).index).toBe(1);
    expect(segmentProgress(.4, 0, 3)).toBe(1);
    expect(segmentProgress(.4, 1, 3)).toBe(0);
    expect(segmentProgress(.4, 2, 3)).toBe(0);
    expect(timelineAt(1, 3)).toEqual({ index: 2, phase: 1 });
    expect(segmentProgress(0, 0, 3)).toBe(0);
    expect(segmentProgress(1, 2, 3)).toBe(1);
  });
  it("la curva conserva extremos, simetría y orden temporal", () => {
    const values=Array.from({length:21},(_,i)=>transformEase(i/20));
    expect(values[0]).toBe(0);expect(values[20]).toBe(1);
    expect(transformEase(.5)).toBeCloseTo(.5,3);
    expect(values.every((v,i)=>i===0||v>=values[i-1])).toBe(true);
  });
  it("la cota interpola valores reales del delta, sin inventar medidas", () => {
    const [step]=changeSteps([{path:"height",operation:"modified",before:{value:8200,unit:"mm"},after:{value:8600,unit:"mm"},affects_geometry:true}]);
    expect(dimensionText(step,.5).replace(/[.\s]/g,"")).toBe("8400mm");
  });
});

describe("detalle IFC con procedencia",()=>{
 it("conserva identidad de la brida y conecta sus campos a la boquilla",()=>{
   const id=semanticId("V-101/nozzle-N3/flange","IfcBuildingElementProxy",{TrazIA_Identity:{ComponentId:"nozzle-N3/flange",ParentComponentId:"N3"}});
   expect(id).toBe("detail:nozzle:N3/nozzle-N3/flange");
   expect(parentElementId(id)).toBe("nozzle:N3");expect(elementLabel(id)).toContain("Brida");
 });
});

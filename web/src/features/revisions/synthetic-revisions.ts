import { BoxGeometry, CylinderGeometry, Vector3, type BufferGeometry } from "three";
import { parentElementId } from "@/features/viewer3d/semantic";
import type { PreparedProduct } from "@/features/viewer3d/model-resource";
import type { Vec3 } from "@/workers/ifc-protocol";

import { hash } from "./revision-states";

const MOVE_M = 0.08;
const BASE_M = 0.12;
const syntheticGeometries = new WeakSet<BufferGeometry>();

export type FieldChange = {
  path: string;
  operation: "added" | "removed" | "modified";
  before: { value: number | string; unit: string } | null;
  after: { value: number | string; unit: string } | null;
  affects_geometry: boolean;
  impact: string;
};

function isSupport(product: PreparedProduct) {
  const key = parentElementId(product.semanticId);
  return key === "skirt" || /^element:(saddle|silleta|leg|pata)/i.test(key);
}

function width(product: PreparedProduct, axis: number) {
  return product.bounds.max[axis]! - product.bounds.min[axis]!;
}

function own(geometry: BufferGeometry) {
  syntheticGeometries.add(geometry);
  return geometry;
}

function resizeUp(product: PreparedProduct, value: number): PreparedProduct {
  const height = width(product, 1);
  if (height <= 1e-6) return product;
  return {
    ...product,
    center: [product.center[0], product.center[1] + value / 2, product.center[2]],
    bounds: { min: product.bounds.min, max: [product.bounds.max[0], product.bounds.max[1] + value, product.bounds.max[2]] },
    geometries: product.geometries.map((geometry) => own(geometry.clone().scale(1, 1 + value / height, 1))),
  };
}

function move(product: PreparedProduct, axis: number, delta: number): PreparedProduct {
  function translated(value: Vec3): Vec3 {
    const result: Vec3 = [...value];
    result[axis] = result[axis]! + delta;
    return result;
  }
  return { ...product, center: translated(product.center), bounds: {
    min: translated(product.bounds.min), max: translated(product.bounds.max),
  } };
}

function part(id: string, name: string, position: Vec3, geometry: BufferGeometry): PreparedProduct {
  geometry.computeBoundingBox();
  const box = geometry.boundingBox!;
  return {
    expressId: -1,
    globalId: `synthetic:${id}`,
    semanticId: `simulation:${id}`,
    name,
    ifcType: id === "nut" ? "IfcMechanicalFastener" : "IfcBuildingElementProxy",
    psets: {},
    center: position,
    bounds: {
      min: box.min.clone().add(new Vector3(...position)).toArray(),
      max: box.max.clone().add(new Vector3(...position)).toArray(),
    },
    geometries: [own(geometry)],
    parts: [],
  };
}

function smallPlate(anchor: PreparedProduct, reinforcement: boolean) {
  const onLeft = anchor.center[0] < 0;
  const edgeX = onLeft ? anchor.bounds.min[0] : anchor.bounds.max[0];
  const position: Vec3 = [edgeX, reinforcement ? anchor.bounds.min[1] + 0.15 : anchor.center[1], anchor.center[2]];
  return reinforcement
    ? part("reinforcement", "Refuerzo local", position, new BoxGeometry(0.026, 0.22, 0.15))
    : part("plate", "Placa de identificación", position, new BoxGeometry(0.008, 0.08, 0.16));
}

function flangeNut(nozzle: PreparedProduct, shell: PreparedProduct) {
  const outside = new Vector3(...nozzle.center).sub(new Vector3(...shell.center));
  const resolution = [0, 1, 2].map((axis) => Math.abs(outside.getComponent(axis)) / Math.max(width(shell, axis), 0.1));
  const axis = resolution.indexOf(Math.max(...resolution));
  const cross = axis === 1 ? 0 : 1;
  const sign = Math.sign(outside.getComponent(axis)) || 1;
  const position: Vec3 = [...nozzle.center];
  position[axis] = (sign > 0 ? nozzle.bounds.max[axis]! : nozzle.bounds.min[axis]!) + sign * 0.007;
  position[cross] = position[cross]! + width(nozzle, cross) * 0.32;
  const geometry = new CylinderGeometry(0.017, 0.017, 0.014, 6);
  if (axis === 0) geometry.rotateZ(Math.PI / 2);
  if (axis === 2) geometry.rotateX(Math.PI / 2);
  return part("nut", "Tuerca de brida", position, geometry);
}

function adjustment(products: PreparedProduct[], tag: string, horizontal: boolean) {
  const shell = products.find((product) => product.semanticId === "shell") ?? products[0];
  if (!shell) return null;
  const axis = horizontal ? (width(shell, 0) >= width(shell, 2) ? 0 : 2) : 1;
  const nozzles = products.filter((product) => product.semanticId.startsWith("nozzle:"))
    .sort((a, b) => a.semanticId.localeCompare(b.semanticId));
  const nozzle = nozzles.find((product) => {
    const [x, y, z] = product.center;
    return horizontal
      ? Math.abs(product.center[axis]! - shell.center[axis]!) < width(shell, axis) * 0.4
      : y > shell.bounds.min[1] + MOVE_M && y < shell.bounds.max[1] - MOVE_M
        && Math.hypot(x - shell.center[0], z - shell.center[2]) >= Math.max(width(shell, 0), width(shell, 2)) * 0.3;
  });
  const upper = products.find((product) => product.semanticId === "element:roof" || product.semanticId === "head-top") ?? shell;
  return { shell, nozzle, upper, axis, sign: hash(`${tag}:cota`) % 2 === 0 ? 1 : -1, horizontal, nut: nozzles[0] };
}

/** Copia visual acumulativa. Los buffers procedentes del IFC se comparten en solo lectura. */
export function applyRevision(products: PreparedProduct[], index: number, tag: string, horizontal = false): PreparedProduct[] {
  const plan = adjustment(products, tag, horizontal);
  if (index <= 0 || !plan) return products;
  const { shell, nozzle, upper, axis, sign, nut } = plan;
  let next = products.map((product) => {
    if (nozzle) {
      return parentElementId(product.semanticId) === nozzle.semanticId ? move(product, axis, sign * MOVE_M) : product;
    }
    return product === upper ? resizeUp(product, MOVE_M) : product;
  });
  if (index === 1) return next;

  const supports = next.filter(isSupport);
  next = next.map((product) => isSupport(product) ? resizeUp(product, BASE_M) : move(product, 1, BASE_M));
  if (!supports.length) {
    const bottom = Math.min(...products.map((product) => product.bounds.min[1]));
    const radius = Math.max(0.05, Math.min(width(shell, 0), width(shell, 2)) / 2);
    next.push(part("plinth", "Zócalo", [shell.center[0], bottom + BASE_M / 2, shell.center[2]],
      new CylinderGeometry(radius, radius, BASE_M, 64)));
  }
  if (index === 2) return next;

  const body = next.find((product) => product.globalId === shell.globalId)!;
  const flange = next.find((product) => product.globalId === nut?.globalId);
  next.push(flange ? flangeNut(flange, body) : smallPlate(body, false));
  if (index >= 4) next.push(smallPlate(next.find(isSupport) ?? body, true));
  return next;
}

export function releaseSynthetic(products: PreparedProduct[]) {
  for (const product of products) {
    for (const geometry of product.geometries) {
      if (syntheticGeometries.has(geometry)) geometry.dispose();
    }
  }
}

export function changesBetween(tag: string, from: number, to: number, products: PreparedProduct[], horizontal = false) {
  const plan = adjustment(products, tag, horizontal);
  const changes: FieldChange[] = [];
  if (!plan) return { changes };
  const low = Math.min(from, to), high = Math.max(from, to);
  const modified = (path: string, delta: number, impact: string): FieldChange => ({
    path, operation: "modified", before: { value: 0, unit: "mm" }, after: { value: delta, unit: "mm" },
    affects_geometry: true, impact,
  });
  const added = (id: string, value: string): FieldChange => ({
    path: `simulation.${id}.piece`, operation: "added", before: null, after: { value, unit: "" },
    affects_geometry: true, impact: value,
  });

  if (low < 1 && high >= 1) {
    changes.push(plan.nozzle
      ? modified(`nozzles.${plan.nozzle.semanticId.slice(7)}.${plan.horizontal ? "station" : "elevation"}`, plan.sign * 80,
        plan.horizontal ? "Estación de conexión" : "Elevación de conexión")
      : modified(`pieces.${plan.upper.semanticId}.profile`, 80, "Altura de la pieza"));
  }
  if (low < 2 && high >= 2) {
    changes.push(modified("base_height", 120, "Altura de apoyo"));
  }
  if (low < 3 && high >= 3) changes.push(plan.nut ? added("nut", "Tuerca de brida") : added("plate", "Placa de identificación"));
  if (low < 4 && high >= 4) changes.push(added("reinforcement", "Refuerzo local"));

  return {
    changes: to >= from ? changes : changes.reverse().map((change): FieldChange => ({
      ...change,
      operation: change.operation === "added" ? "removed" : change.operation === "removed" ? "added" : "modified",
      before: change.after,
      after: change.before,
    })),
  };
}

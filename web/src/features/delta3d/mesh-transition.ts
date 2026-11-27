import { Matrix4, Quaternion, Vector3 } from "three";
import type { Vec3 } from "@/workers/ifc-protocol";
import type { PreparedProduct } from "../viewer3d/model-resource";
import type { Pair } from "./morph";

// Metros. Absorbe el redondeo de los vértices float32 sin confundirlo con un cambio de cota.
const TOLERANCE = 0.00005;
const within = (a: number, b: number) => Math.abs(a - b) <= TOLERANCE;
type Transform = { scale: Vec3; rotation: Quaternion; offset: Vec3 };
export type MeshTransition = { kind: "static" | "added" | "removed" | "replace" } | { kind: "transform"; transform: Transform };

function sameTopology(a: PreparedProduct, b: PreparedProduct) {
  return a.geometries.length === b.geometries.length && a.geometries.every((geometry, i) => {
    const next = b.geometries[i]!;
    if (geometry === next) return true;
    if (geometry.getAttribute("position").count !== next.getAttribute("position").count) return false;
    // La preparación del BVH puede ordenar los índices de three. Los del IFC se conservan.
    const indicesA = a.parts[i]?.indices ?? geometry.index?.array;
    const indicesB = b.parts[i]?.indices ?? next.index?.array;
    return indicesA === indicesB || (indicesA?.length === indicesB?.length &&
      indicesA !== undefined && indicesA.every((index, j) => index === indicesB?.[j]));
  });
}

function matchesVertices(a: PreparedProduct, b: PreparedProduct, transform?: Transform) {
  const vertex = new Vector3();
  const factor = new Vector3(...(transform?.scale ?? [1, 1, 1]));
  const translation = new Vector3(...(transform?.offset ?? [0, 0, 0]));
  return a.geometries.every((geometry, i) => {
    const source = geometry.getAttribute("position");
    const target = b.geometries[i]!.getAttribute("position");
    for (let j = 0; j < source.count; j++) {
      if (!transform) {
        if (source.getX(j) !== target.getX(j) || source.getY(j) !== target.getY(j) || source.getZ(j) !== target.getZ(j)) return false;
        continue;
      }
      vertex.fromBufferAttribute(source, j).multiply(factor).applyQuaternion(transform.rotation).add(translation);
      if (!within(vertex.x, target.getX(j)) || !within(vertex.y, target.getY(j)) || !within(vertex.z, target.getZ(j))) return false;
    }
    return true;
  });
}

/** Deduce un giro rígido de tres vértices correspondientes y deja que la malla completa lo valide. */
function rigidTransform(a: PreparedProduct, b: PreparedProduct): Transform | null {
  for (const [i, geometry] of a.geometries.entries()) {
    const source = geometry.getAttribute("position");
    const target = b.geometries[i]!.getAttribute("position");
    if (source.count < 3) continue;
    const origin = new Vector3().fromBufferAttribute(source, 0);
    const point = new Vector3();
    let farthest = 0;
    let distance = 0;
    for (let j = 1; j < source.count; j++) {
      const d = point.fromBufferAttribute(source, j).distanceToSquared(origin);
      if (d > distance) { distance = d; farthest = j; }
    }
    if (distance <= TOLERANCE ** 2) continue;
    const x = new Vector3().fromBufferAttribute(source, farthest).sub(origin).normalize();
    let third = 0;
    distance = 0;
    for (let j = 1; j < source.count; j++) {
      const d = point.fromBufferAttribute(source, j).sub(origin).cross(x).lengthSq();
      if (d > distance) { distance = d; third = j; }
    }
    if (distance <= TOLERANCE ** 2) continue;
    const targetOrigin = new Vector3().fromBufferAttribute(target, 0);
    const targetX = new Vector3().fromBufferAttribute(target, farthest).sub(targetOrigin).normalize();
    const targetZ = new Vector3().fromBufferAttribute(target, third).sub(targetOrigin).cross(targetX).normalize();
    if (targetZ.lengthSq() === 0) continue;
    const z = point.fromBufferAttribute(source, third).sub(origin).cross(x).normalize();
    const from = new Matrix4().makeBasis(x, new Vector3().crossVectors(z, x), z);
    const to = new Matrix4().makeBasis(targetX, new Vector3().crossVectors(targetZ, targetX), targetZ);
    const rotation = new Quaternion().setFromRotationMatrix(to.multiply(from.transpose())).normalize();
    return { rotation, scale: [1, 1, 1], offset: targetOrigin.sub(origin.applyQuaternion(rotation)).toArray() };
  }
  return null;
}

/** Solo se transforma una malla cuando la misma transformación reproduce toda la geometría de B. */
export function meshTransition({ before: a, after: b }: Pair<PreparedProduct>): MeshTransition {
  if (!a) return { kind: "added" };
  if (!b) return { kind: "removed" };
  const identity: Transform = { scale: [1, 1, 1], rotation: new Quaternion(), offset: [0, 0, 0] };
  const shared = a.geometries.length === b.geometries.length &&
    a.geometries.every((geometry, i) => geometry === b.geometries[i]);
  if (!shared && !sameTopology(a, b)) return { kind: "replace" };
  if (shared || matchesVertices(a, b)) {
    return a.center.every((value, i) => value === b.center[i])
      ? { kind: "static" }
      : { kind: "transform", transform: identity };
  }
  const scale = a.bounds.min.map((min, i) => {
    const size = a.bounds.max[i]! - min;
    return size > TOLERANCE ? (b.bounds.max[i]! - b.bounds.min[i]!) / size : 1;
  }) as Vec3;
  const scaled = { ...identity, scale };
  if (scale.every(value => value > 0) && matchesVertices(a, b, scaled)) {
    return { kind: "transform", transform: scaled };
  }
  const rigid = rigidTransform(a, b);
  return rigid && matchesVertices(a, b, rigid) ? { kind: "transform", transform: rigid } : { kind: "replace" };
}

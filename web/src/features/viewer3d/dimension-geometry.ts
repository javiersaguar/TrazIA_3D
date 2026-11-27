import { Vector3 } from "three";
import type { Vec3 } from "@/workers/ifc-protocol";
import type { PreparedProduct } from "./model-resource";
import type { Annotation } from "./types";

type DimensionGeometry = { points: Vec3[]; anchors: [Vec3, Vec3]; label: Vec3 };
const average = (a: Vector3, b: Vector3) => a.clone().lerp(b, .5).toArray();

export function dimensionGeometry(annotation: Annotation, product: PreparedProduct, shell: PreparedProduct | undefined, index: number): DimensionGeometry | null {
  const value = annotation.drawingValue ?? annotation.value;
  if (!Number.isFinite(value) || value === 0 || annotation.state === "abstained" || annotation.state === "conflict") return null;
  if (value < 0 && !annotation.id.endsWith(".elevation") && !annotation.id.endsWith(".position.x")) return null;
  const { min, max } = product.bounds;
  const center = new Vector3(...product.center);
  const { id } = annotation;
  const longitudinal = annotation.horizontal ? 0 : 1;
  const transverse = annotation.horizontal ? 1 : 0;
  const offset = .24 + index * .24 + Math.min(.65, Math.max(...max.map((v, axis) => v - min[axis]!)) * .08);
  const measured = value / 1000;
  const nozzle = product.semanticId.startsWith("nozzle:");
  const axis = shell ? center.clone().sub(new Vector3(...shell.center)).setComponent(longitudinal, 0).normalize() : new Vector3();

  if (annotation.unit === "deg") {
    if (!nozzle || !shell || axis.lengthSq() === 0) return null;
    const pivot = center.clone().setComponent(transverse, shell.center[transverse]).setZ(shell.center[2]);
    const normal = annotation.horizontal ? new Vector3(-1, 0, 0) : new Vector3(0, annotation.clockwise ? -1 : 1, 0);
    const angle = value * Math.PI / 180;
    const radius = pivot.distanceTo(center) + offset;
    const pointAt = (t: number) => pivot.clone().addScaledVector(axis.clone().applyAxisAngle(normal, (t - 1) * angle), radius).toArray();
    const segments = Math.max(1, Math.ceil(Math.abs(angle) * 10));
    const points = Array.from({ length: segments + 1 }, (_, i) => pointAt(i / segments));
    return { points, anchors: [pivot.toArray(), pivot.toArray()], label: pointAt(.5) };
  }

  let start = center.clone(), end = center.clone();
  const shift = new Vector3();
  if (id.endsWith(".projection")) {
    if (axis.lengthSq() === 0) return null;
    let tip = -Infinity;
    for (const part of product.parts) {
      for (let i = 0; i < part.positions.length; i += 3) {
        tip = Math.max(tip, part.positions[i]! * axis.x + part.positions[i + 1]! * axis.y + part.positions[i + 2]! * axis.z);
      }
    }
    if (!Number.isFinite(tip)) return null;
    end.addScaledVector(axis, tip);
    start = end.clone().addScaledVector(axis, -measured);
    shift.setComponent(longitudinal, offset);
  } else if (id.endsWith(".elevation") || id.endsWith(".position.x") || id.includes(".saddle_positions.")) {
    const measuringAxis = id.endsWith(".elevation") ? 1 : 0;
    start.setComponent(measuringAxis, end.getComponent(measuringAxis) - measured);
    shift.setComponent(measuringAxis === 1 ? 0 : 1, offset);
  } else if (id.endsWith("diameter")) {
    const width = annotation.drawingValue !== undefined || !nozzle ? measured : max[transverse] - min[transverse];
    if (nozzle && axis.lengthSq() > 0) {
      const perpendicular = axis.clone().cross(new Vector3().setComponent(longitudinal, 1));
      let half = 0;
      for (const part of product.parts) for (let i = 0; i < part.positions.length; i += 3) {
        half = Math.max(half, Math.abs(part.positions[i]! * perpendicular.x + part.positions[i + 1]! * perpendicular.y + part.positions[i + 2]! * perpendicular.z));
      }
      start.addScaledVector(perpendicular, -half);
      end.addScaledVector(perpendicular, half);
      shift.copy(axis).multiplyScalar(offset);
    } else {
      start.setComponent(transverse, center.getComponent(transverse) - width / 2);
      end.setComponent(transverse, center.getComponent(transverse) + width / 2);
      shift.setComponent(longitudinal, (max[longitudinal] - min[longitudinal]) / 2 + offset);
    }
  } else if (id === "skirt_thickness") {
    start.set(max[0] - measured, max[1], center.z);
    end.set(max[0], max[1], center.z);
    shift.y = offset;
  } else {
    const measuringAxis = id === "skirt_height" || id === "legs.height" || id.endsWith(".support_height") ? 1 : longitudinal;
    const away = measuringAxis === 1 ? 0 : 1;
    start.setComponent(away, min[away]).setComponent(measuringAxis, min[measuringAxis]);
    end = start.clone().setComponent(measuringAxis, min[measuringAxis] + measured);
    if (id === "head_depth" && product.semanticId === "head-bottom") {
      end.setComponent(measuringAxis, max[measuringAxis]);
      start.setComponent(measuringAxis, max[measuringAxis] - measured);
    }
    shift.setComponent(away, -offset);
  }
  if (start.distanceToSquared(end) < 1e-10) return null;
  const from = start.clone().add(shift), to = end.clone().add(shift);
  return { points: [from.toArray(), to.toArray()], anchors: [start.toArray(), end.toArray()], label: average(from, to) };
}

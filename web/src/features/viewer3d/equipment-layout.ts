import { Vector3 } from "three";
import type { Bounds, IfcProduct, Vec3 } from "@/workers/ifc-protocol";
import { elementForField, parentElementId } from "./semantic";
import type { Annotation } from "./types";

type Piece = Pick<IfcProduct, "semanticId" | "center" | "bounds" | "parts">;
const point = (v: Vec3) => new Vector3(...v);
const vec3 = (v: Vector3): Vec3 => v.toArray();
const up = new Vector3(0, 1, 0);
const lateral = new Vector3(0, 0, 1);

export function equipmentFrame(products: Piece[]) {
  const shell = products.find(p => p.semanticId === "shell");
  if (!shell) return null;
  const positive = products.find(p => p.semanticId === "head-top");
  const negative = products.find(p => p.semanticId === "head-bottom");
  const axis = positive && negative ? point(positive.center).sub(point(negative.center)).normalize() : up.clone();
  if (axis.lengthSq() < .5) axis.copy(up);
  return { shell, axis, horizontal: Math.abs(axis.y) < .5 };
}
type Frame = NonNullable<ReturnType<typeof equipmentFrame>>;

function nozzleDirection(product: Piece, frame: Frame) {
  const outward = point(product.center).sub(point(frame.shell.center));
  const station = outward.dot(frame.axis);
  const radial = outward.clone().addScaledVector(frame.axis, -station);
  return radial.lengthSq() > 1e-8 ? radial.normalize() : frame.axis.clone().multiplyScalar(Math.sign(station) || 1);
}

/** Desplazamientos coherentes con el eje real, en las mismas coordenadas de las mallas IFC. */
export function explosionOffsets(products: Piece[]) {
  const frame = equipmentFrame(products);
  if (!frame) return new Map<string, Vec3>();
  const { axis, shell } = frame;
  const size = point(shell.bounds.max).sub(point(shell.bounds.min));
  const width = frame.horizontal ? size.y : Math.max(size.x, size.z);
  const gap = Math.max(.22, width * .55);
  const byId = new Map(products.map(p => [p.semanticId, p]));
  return new Map(products.map(product => {
    const id = parentElementId(product.semanticId);
    const parent = byId.get(id) ?? product;
    let offset = new Vector3();
    if (id === "head-top" || id === "head-bottom") {
      offset = axis.clone().multiplyScalar(id === "head-top" ? gap : -gap);
    } else if (id === "skirt" || /^element:(?:saddle|leg)(?:-|$)/.test(id)) {
      offset.y = -gap * .8;
    } else if (id.startsWith("nozzle:")) {
      offset = nozzleDirection(parent, frame).multiplyScalar(gap);
    }
    return [product.semanticId, vec3(offset)] as const;
  }));
}

function extent(product: Piece, axis: Vector3): [number, number] {
  let min = Infinity, max = -Infinity;
  for (const part of product.parts) {
    const vertices = part.positions;
    for (let i = 0; i < vertices.length; i += 3) {
      const d = axis.x * vertices[i]! + axis.y * vertices[i + 1]! + axis.z * vertices[i + 2]!;
      min = Math.min(min, d);
      max = Math.max(max, d);
    }
  }
  return [min, max];
}

type Dimension = { from: Vec3; to: Vec3; anchorFrom: Vec3; anchorTo: Vec3 };
const diameterPaths = new Set(["diameter", "horizontal.diameter", "tank.diameter"]);

export function isDimensionPath(path: string) {
  return diameterPaths.has(path) || [
    "height", "horizontal.length", "horizontal.head_depth", "horizontal.support_height", "head_depth",
    "skirt_height", "skirt_thickness", "tank.height",
  ].includes(path) || /^nozzles\.[^.]+\.(diameter|elevation|projection)$/.test(path);
}

export function placedDimension(
  annotation: Annotation, products: Piece[], bounds: Bounds, index: number, top = false,
): Dimension | null {
  const path = annotation.id;
  if (!isDimensionPath(path) || annotation.unit !== "mm" || !Number.isFinite(annotation.value)
    || annotation.value <= 0 || annotation.state === "conflict" || annotation.state === "abstained") return null;
  if (top && !diameterPaths.has(path)) return null;
  const frame = equipmentFrame(products);
  const id = elementForField(path);
  const piece = products.find(p => p.semanticId === id);
  if (!piece) return null;
  const center = point(piece.center);
  const direction = frame?.axis ?? up;
  const horizontal = frame?.horizontal ?? false;
  const radius = .38 + index * .24;
  let axis = direction;
  let offset = new Vector3(-radius, 0, 0);
  let origin = center;
  let span: [number, number] | undefined;

  if (id.startsWith("nozzle:")) {
    if (!frame) return null;
    const nozzle = nozzleDirection(piece, frame);
    if (path.endsWith(".elevation")) {
      const foot = center.clone().addScaledVector(nozzle, extent(piece, nozzle)[0]);
      origin = foot;
      axis = up;
      span = [bounds.min[1] - foot.y, 0];
      offset = new Vector3(radius, 0, 0);
    } else {
      axis = path.endsWith(".projection") ? nozzle
        : new Vector3().crossVectors(nozzle, Math.abs(nozzle.y) > .9 ? lateral : up).normalize();
      if (path.endsWith(".diameter")) {
        origin = center.clone().addScaledVector(nozzle, extent(piece, nozzle)[1]);
        offset = nozzle.clone().multiplyScalar(radius);
      } else {
        offset = Math.abs(nozzle.y) > .9 ? new Vector3(radius, 0, 0) : up.clone().multiplyScalar(radius);
      }
    }
  } else if (diameterPaths.has(path)) {
    axis = horizontal ? (top ? lateral : up) : new Vector3(1, 0, 0);
    offset = horizontal ? direction.clone().multiplyScalar(radius) : (top ? lateral : up).clone().multiplyScalar(radius);
  } else if (path === "horizontal.support_height") {
    axis = up;
    span = [bounds.min[1] - center.y, piece.bounds.min[1] - center.y];
    offset = new Vector3(radius, 0, 0);
  } else if (path === "skirt_thickness") {
    let inner = Infinity, outer = 0;
    for (const part of piece.parts) for (let i = 0; i < part.positions.length; i += 3) {
      const r = Math.hypot(part.positions[i]!, part.positions[i + 2]!);
      if (r > 1e-5) { inner = Math.min(inner, r); outer = Math.max(outer, r); }
    }
    axis = new Vector3(1, 0, 0);
    origin = center.clone();
    origin.y = piece.bounds.max[1];
    span = [inner, outer];
    offset = up.clone().multiplyScalar(radius);
  } else if (horizontal) {
    offset = up.clone().multiplyScalar(radius);
  }
  // Despeja la envolvente en la dirección que separa la línea de su referencia física.
  if (!id.startsWith("nozzle:") && path !== "skirt_thickness") {
    const extra = extent(piece, offset.clone().normalize())[1];
    offset.setLength(radius + Math.max(0, extra));
  }
  const [low, high] = span ?? extent(piece, axis);
  const metres = annotation.value / 1000;
  // La cifra trazada solo se dibuja si es compatible con el IFC de la revisión.
  if (!Number.isFinite(high - low) || Math.abs(high - low - metres) > Math.max(.003, metres * .015)) return null;
  const a = origin.clone().addScaledVector(axis, low);
  const b = origin.clone().addScaledVector(axis, high);
  return { anchorFrom: vec3(a), anchorTo: vec3(b), from: vec3(a.add(offset)), to: vec3(b.add(offset)) };
}

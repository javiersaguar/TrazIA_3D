import type { Vec3 } from "@/workers/ifc-protocol";
/**
 * Pose de cámara. En perspectiva `zoom` es el zoom ortográfico equivalente (misma altura visible a
 * la distancia del objetivo), para que el BCF y la cámara compartida sirvan en las dos proyecciones.
 */
export type CameraPose = { eye: Vec3; target: Vec3; zoom: number; projection?: "perspective" | "orthographic" };
/** Pose finita y no degenerada; descarta lo que no se puede restaurar en la cámara. */
export function validPose(value: unknown): value is CameraPose {
  if (!value || typeof value !== "object") return false;
  const pose = value as CameraPose;
  const vector = (v: unknown): v is [number, number, number] =>
    Array.isArray(v) && v.length === 3 && v.every(n => typeof n === "number" && Number.isFinite(n));
  // En perspectiva el zoom equivalente de una vista lejana puede quedar por debajo del mínimo ortográfico.
  const minimum = pose.projection === "perspective" ? 0.05 : 5;
  return vector(pose.eye) && vector(pose.target) && Number.isFinite(pose.zoom)
    && pose.zoom >= minimum && pose.zoom <= 650
    && pose.eye.some((v, i) => Math.abs(v - pose.target[i]!) > 1e-6);
}
/** Canal efímero entre los dos visores. No provoca renders de React. */
export class CameraLink {
  private listeners = new Map<symbol, (pose: CameraPose) => void>();
  private busy = false;
  subscribe(id: symbol, listener: (pose: CameraPose) => void) {
    this.listeners.set(id, listener); return () => { this.listeners.delete(id); };
  }
  publish(id: symbol, pose: CameraPose) {
    if (this.busy) return;
    this.busy = true;
    try { this.listeners.forEach((fn, key) => { if (key !== id) fn(pose); }); }
    finally { this.busy = false; }
  }
}

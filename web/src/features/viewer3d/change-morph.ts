import { Quaternion, Vector3 } from "three";
import type { Vec3 } from "@/workers/ifc-protocol";
import { clampProgress, transformEase } from "../delta3d/morph";
import { meshTransition } from "../delta3d/mesh-transition";
import type { PreparedProduct } from "./model-resource";

/** Duración de la transformación de un borrador, con la misma curva que «Visualizar cambios». */
export const MORPH_SECONDS = 2.4;
/** Más piezas cambiadas que esto es otra planta, no un ensayo: se carga sin animar. */
const MAX_MORPHED = 600;
/** Desde dónde parte cada pieza: desplazamiento y escala respecto a su geometría nueva. */
export type MorphFrom = { offset: Vec3; scale: Vec3; rotation: Quaternion };
export type ChangeMorph = {
  key: string;
  from: Map<string, MorphFrom>;
  /** Instante del reloj del lienzo en que empezó; lo fija el primer fotograma. */
  clock: { start: number };
};

/**
 * Piezas que cambian entre dos cargas del mismo proyecto, emparejadas por GlobalId: el visor las
 * dibuja con su geometría nueva cuando una transformación comprobada reproduce la anterior.
 */
export function changeMorph(before: readonly PreparedProduct[], after: readonly PreparedProduct[], key: string): ChangeMorph | null {
  if (!before.length || !after.length) return null;
  const previous = new Map(before.map(item => [item.globalId, item]));
  const from = new Map<string, MorphFrom>();
  for (const item of after) {
    const old = previous.get(item.globalId);
    if (!old) continue;
    const motion = meshTransition({ globalId: item.globalId, before: old, after: item });
    if (motion.kind !== "transform") continue;
    const rotation = motion.transform.rotation.clone().invert();
    const scale = motion.transform.scale.map(value => 1 / value) as Vec3;
    const localOffset = new Vector3(...motion.transform.offset).applyQuaternion(rotation).multiply(new Vector3(...scale));
    const offset = old.center.map((value, i) => (value - item.center[i]!) - localOffset.getComponent(i)) as Vec3;
    from.set(item.semanticId, { offset, scale, rotation });
  }
  return from.size && from.size <= MAX_MORPHED ? { key, from, clock: { start: -1 } } : null;
}

/** Avance 0–1 de la transformación: espera breve (pulso) y luego la curva de los cambios. */
export function morphProgress(elapsed: number) {
  return transformEase(clampProgress((elapsed / MORPH_SECONDS - 0.12) / 0.8));
}

/** Transformación local de una pieza en el avance `t`. */
export function morphTransform(from: MorphFrom, t: number): { position: Vec3; scale: Vec3 } {
  const k = clampProgress(t);
  return {
    position: from.offset.map(v => v * (1 - k)) as Vec3,
    scale: from.scale.map(v => v + (1 - v) * k) as Vec3,
  };
}

/** Segundos desde el inicio de la transformación; el primer fotograma que la ve fija el inicio. */
export function morphElapsed(clock: { start: number }, now: number) {
  if (clock.start < 0) clock.start = now;
  return now - clock.start;
}

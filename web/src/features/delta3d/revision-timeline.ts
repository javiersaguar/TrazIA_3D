import type { Bounds } from "@/workers/ifc-protocol";
import type { PreparedProduct } from "../viewer3d/model-resource";
import { elementLabel, parentElementId } from "../viewer3d/semantic";
import { meshTransition, type MeshTransition } from "./mesh-transition";
import { changeSteps, pairByGlobalId, type Pair } from "./morph";

export function unionBounds(a: Bounds, b: Bounds): Bounds {
  return {
    min: [Math.min(a.min[0], b.min[0]), Math.min(a.min[1], b.min[1]), Math.min(a.min[2], b.min[2])],
    max: [Math.max(a.max[0], b.max[0]), Math.max(a.max[1], b.max[1]), Math.max(a.max[2], b.max[2])],
  };
}

type TimelinePair = { pair: Pair<PreparedProduct>; motion: MeshTransition; index: number };

/** El diff describe el cambio. Los dos IFC determinan qué piezas se mueven y cuáles existen. */
export function revisionTimeline(a: PreparedProduct[], b: PreparedProduct[], changes: unknown, simulation: boolean) {
  const steps = changeSteps(changes).map((step) => ({
    ...step, bounds: null as Bounds | null, anchor: null as TimelinePair | null,
  }));
  const byElement = new Map(steps.map((step, i) => [step.elementId, i]));
  const support = simulation && steps.length === 1 && steps[0]?.fields.some((field) => field.path === "base_height");
  const pairs = pairByGlobalId(a, b).map((pair) => {
    const motion = meshTransition(pair);
    const { before, after } = pair;
    const product = (after ?? before)!;
    if (motion.kind === "static") return { pair, motion, index: -1 };

    const id = product.semanticId;
    const parent = parentElementId(id);
    let index = byElement.get(id) ?? byElement.get(parent);
    if (index === undefined && before && after) {
      index = byElement.get(before.semanticId) ?? byElement.get(parentElementId(before.semanticId));
    }
    // Elevar los apoyos en una simulación desplaza solidariamente el equipo que descansa en ellos.
    if (support) index = 0;
    if (index === undefined) {
      index = steps.length;
      byElement.set(parent, index);
      steps.push({
        id: parent, elementId: parent, fields: [],
        label: elementLabel(parent), narration: `${elementLabel(parent)}: cambio de geometría entre los dos IFC.`,
        bounds: null, anchor: null,
      });
    }
    const step = steps[index]!;
    const bounds = before && after ? unionBounds(before.bounds, after.bounds) : product.bounds;
    step.bounds = step.bounds ? unionBounds(step.bounds, bounds) : bounds;
    const entry = { pair, motion, index };
    if (step.elementId === id || !step.anchor) step.anchor = entry;
    return entry;
  });
  return { pairs, steps };
}

export type RevisionTimeline = ReturnType<typeof revisionTimeline>;

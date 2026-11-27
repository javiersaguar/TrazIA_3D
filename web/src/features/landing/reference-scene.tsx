"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import {
  BufferAttribute, BufferGeometry, Color, CylinderGeometry, EdgesGeometry, Float32BufferAttribute,
  Group, LineBasicMaterial, MeshStandardMaterial, Plane, SphereGeometry, Vector3,
} from "three";

import { BRAND } from "@/lib/brand";
import { useMotionPreference } from "@/lib/use-motion-preference";
import type { IfcModel, Vec3 } from "@/workers/ifc-protocol";
import { useIfcModel } from "@/features/viewer3d/model-resource";
import { CameraRig, SceneCanvas, Studio, useLightPage, type CameraHandle } from "@/features/viewer3d/stage";
import type { ReferenceModel } from "./reference-sheet";

const STEPS = ["Boceto del IFC", "Materializando", "Modelo 3D"] as const;
const runtime = 2.2;
/** Ø1100 interior, espesor de virola: el IFC de referencia solo trae la estructura auxiliar. */
const SHELL_RADIUS = 0.562;

function median(values: number[]) {
  const sorted = values.toSorted((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
}

/** Virola, faldón y casquete 2:1. El Tekla de la columna no exporta el cuerpo del recipiente. */
function vesselShell(height: number, x: number, z: number) {
  const head = SHELL_RADIUS * 0.5;
  const bodyHeight = Math.max(SHELL_RADIUS, height - head);
  const body = new CylinderGeometry(SHELL_RADIUS, SHELL_RADIUS, bodyHeight, 28);
  body.translate(x, -head / 2, z);
  const cap = new SphereGeometry(SHELL_RADIUS, 24, 8, 0, Math.PI * 2, 0, Math.PI / 2);
  cap.scale(1, 0.5, 1);
  cap.translate(x, bodyHeight / 2 - head / 2, z);
  const solid = mergeGeometries([body, cap])!;
  body.dispose();
  cap.dispose();
  const lines: number[] = [];
  const ring = (y: number) => {
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * Math.PI * 2, b = ((i + 1) / 24) * Math.PI * 2;
      lines.push(x + Math.cos(a) * SHELL_RADIUS, y, z + Math.sin(a) * SHELL_RADIUS,
        x + Math.cos(b) * SHELL_RADIUS, y, z + Math.sin(b) * SHELL_RADIUS);
    }
  };
  const bottom = -height / 2, top = height / 2;
  ring(bottom); ring(0); ring(top - head);
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * Math.PI * 2;
    const px = x + Math.cos(a) * SHELL_RADIUS, pz = z + Math.sin(a) * SHELL_RADIUS;
    lines.push(px, bottom, pz, px, top - head, pz);
  }
  const sketch = new BufferGeometry();
  sketch.setAttribute("position", new Float32BufferAttribute(lines, 3));
  return { solid, sketch };
}

function geometryOf(model: IfcModel, withShell: boolean) {
  const center = new Vector3(...model.bounds.min).lerp(new Vector3(...model.bounds.max), .5);
  const bounds = {
    min: new Vector3(...model.bounds.min).sub(center).toArray() as Vec3,
    max: new Vector3(...model.bounds.max).sub(center).toArray() as Vec3,
  };
  // La tornillería no entra en la portada: pesa en la lectura y tapa el cuerpo.
  const kept = model.products.filter(product => !/FASTENER|DISCRETEACCESSORY/i.test(product.ifcType));
  const steel = new Color(BRAND.steelDark);
  const parts = kept.flatMap(product => product.parts.map(part => ({
    part, outline: !/^(IfcMechanicalFastener|IfcFastener)$/i.test(product.ifcType),
    x: product.center[0] - center.x, y: product.center[1] - center.y, z: product.center[2] - center.z,
  })));
  const vertexCount = parts.reduce((total, { part }) => total + part.positions.length, 0);
  const positions = new Float32Array(vertexCount), normals = new Float32Array(vertexCount);
  const colors = new Float32Array(vertexCount);
  const indices = new Uint32Array(parts.reduce((total, { part }) => total + part.indices.length, 0));
  const outline = new Uint32Array(parts.reduce((total, item) => total + (item.outline ? item.part.indices.length : 0), 0));
  let vertexOffset = 0, faceOffset = 0, lineOffset = 0;
  for (const { part, outline: visible, x, y, z } of parts) {
    const color = new Color(part.color[0], part.color[1], part.color[2]).lerp(steel, .42);
    normals.set(part.normals, vertexOffset);
    for (let i = 0; i < part.positions.length; i += 3) {
      positions[vertexOffset + i] = part.positions[i]! + x;
      positions[vertexOffset + i + 1] = part.positions[i + 1]! + y;
      positions[vertexOffset + i + 2] = part.positions[i + 2]! + z;
      color.toArray(colors, vertexOffset + i);
    }
    for (const index of part.indices) {
      const shifted = index + vertexOffset / 3;
      indices[faceOffset++] = shifted;
      if (visible) outline[lineOffset++] = shifted;
    }
    vertexOffset += part.positions.length;
  }
  const position = new BufferAttribute(positions, 3);
  const solid = new BufferGeometry();
  solid.setAttribute("position", position);
  solid.setAttribute("normal", new BufferAttribute(normals, 3));
  solid.setAttribute("color", new BufferAttribute(colors, 3));
  solid.setIndex(new BufferAttribute(indices, 1));
  const source = new BufferGeometry();
  // Comparte los vértices de solo lectura durante el cálculo de aristas.
  source.setAttribute("position", position);
  source.setIndex(new BufferAttribute(outline.length ? outline : indices, 1));
  const edges = new EdgesGeometry(source, 29);
  const height = bounds.max[1] - bounds.min[1];
  const shell = withShell && kept.length > 0 && height > SHELL_RADIUS * 2
    ? vesselShell(height, median(kept.map(product => product.center[0] - center.x)), median(kept.map(product => product.center[2] - center.z)))
    : null;
  const sketch = shell ? joinedLines(edges, shell.sketch) : edges;
  if (shell) edges.dispose();
  return { bounds, solid, sketch, shell: shell?.solid ?? null };
}

function joinedLines(left: BufferGeometry, right: BufferGeometry) {
  const a = left.getAttribute("position"), b = right.getAttribute("position");
  const positions = new Float32Array(a.count * 3 + b.count * 3);
  positions.set(a.array as ArrayLike<number>);
  positions.set(b.array as ArrayLike<number>, a.count * 3);
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  right.dispose();
  return geometry;
}

function Assembly({ geometry, reduced, blueprint, onStep }: {
  geometry: ReturnType<typeof geometryOf>; reduced: boolean; blueprint: string; onStep(step: number): void;
}) {
  const { invalidate } = useThree();
  const paper = useRef<LineBasicMaterial>(null);
  const steel = useRef<MeshStandardMaterial>(null);
  const vessel = useRef<MeshStandardMaterial>(null);
  const group = useRef<Group>(null);
  const elapsed = useRef(0), lastStep = useRef(-1);
  const start = geometry.bounds.min[1], end = geometry.bounds.max[1];
  const sweep = useMemo(() => [new Plane(new Vector3(0, -1, 0), start - .001)], [start]);
  useFrame((_, delta) => {
    elapsed.current = reduced ? runtime : Math.min(runtime, elapsed.current + Math.min(delta, .05));
    const progress = elapsed.current / runtime;
    const rise = Math.max(0, (progress - .16) / .84);
    const eased = rise * rise * (3 - 2 * rise);
    const constant = start + (end - start + .01) * eased - .001;
    for (const material of [steel.current, vessel.current]) {
      const plane = material?.clippingPlanes?.[0];
      if (plane) plane.constant = constant;
    }
    if (paper.current) paper.current.opacity = reduced ? 0 : .92 * (1 - eased);
    if (group.current) {
      group.current.rotation.y = -.18 * (1 - eased);
      group.current.position.y = -(end - start) * .035 * (1 - eased);
    }
    const step = progress >= 1 ? 2 : rise > 0 ? 1 : 0;
    if (step !== lastStep.current) {
      lastStep.current = step;
      onStep(step);
    }
    if (progress < 1) invalidate();
  });
  return (
    <group ref={group}>
      <mesh geometry={geometry.solid}>
        <meshStandardMaterial ref={steel} vertexColors roughness={.42} metalness={.47} clippingPlanes={sweep} />
      </mesh>
      {geometry.shell ? <mesh geometry={geometry.shell}>
        <meshStandardMaterial ref={vessel} color={BRAND.steelDark} roughness={.4} metalness={.35} clippingPlanes={sweep} />
      </mesh> : null}
      <lineSegments geometry={geometry.sketch}>
        <lineBasicMaterial ref={paper} color={blueprint} transparent opacity={reduced ? 0 : .92} depthWrite={false} />
      </lineSegments>
    </group>
  );
}

function Turntable({ model, tag, shell }: { model: IfcModel; tag: string; shell: boolean }) {
  const reduce = useMotionPreference();
  const light = useLightPage();
  const geometry = useMemo(() => geometryOf(model, shell), [model, shell]);
  const camera = useRef<CameraHandle>(null);
  const [run, setRun] = useState(0), [step, setStep] = useState(0), [orbit, setOrbit] = useState(true);
  useEffect(() => () => {
    geometry.sketch.dispose();
    geometry.solid.dispose();
    geometry.shell?.dispose();
  }, [geometry]);
  const displayedStep = reduce ? 2 : step;
  const rotating = orbit && displayedStep === 2 && !reduce;
  return <>
    <div className="relative min-h-0 overflow-hidden" data-testid="landing-assembly" data-step={displayedStep}
      data-rotating={rotating} data-triangles={model.triangles}>
      <SceneCanvas label={`Boceto y modelo 3D de ${tag}`} rotationControl={false}
        pixelBudget={280_000} rotating={rotating} onRotationChange={setOrbit} transparent>
        <Studio effects={false} stage={false} />
        <CameraRig bounds={geometry.bounds} orbitCenter={[0, 0, 0]} handle={camera} framing={1.08} />
        <Assembly key={run} geometry={geometry} reduced={reduce} blueprint={light ? BRAND.skyDeep : BRAND.skyLight} onStep={setStep} />
      </SceneCanvas>
    </div>
    <div className="relative flex min-h-13 items-center justify-between gap-2 border-t border-border bg-surface/65 px-4 py-2 font-mono text-[11px] text-muted sm:px-5">
      <span aria-live="polite">{STEPS[displayedStep]}<span className="ml-2 text-faint">· {displayedStep + 1}/3</span></span>
      {!reduce ? <div className="flex items-center gap-2">
        {displayedStep === 2 ? <button type="button"
          aria-label={rotating ? "Pausar giro 3D" : "Reanudar giro 3D"}
          onClick={() => setOrbit(value => !value)}
          className="grid size-9 place-items-center rounded-md border border-border bg-surface text-text hover:border-accent">
          {rotating ? <Pause size={15} /> : <Play size={15} />}
        </button> : null}
        <button type="button" aria-label="Repetir animación del boceto" title="Repetir animación"
          onClick={() => { setStep(0); setOrbit(true); setRun(value => value + 1); }}
          className="grid size-9 place-items-center rounded-md border border-border bg-surface text-text hover:border-accent">
          <RotateCcw size={15} />
        </button>
      </div> : null}
    </div>
  </>;
}

export function ReferenceScene({ model }: { model: ReferenceModel }) {
  const { model: parsed, error } = useIfcModel(model.url);
  if (parsed?.triangles) return <Turntable model={parsed} tag={model.tag} shell={model.real} />;
  return <div role="status" className="row-span-2 self-center justify-self-center px-4 text-center text-sm text-muted">
    {error || parsed ? "No se pudo mostrar la geometría del IFC." : "Leyendo la geometría del IFC…"}
  </div>;
}

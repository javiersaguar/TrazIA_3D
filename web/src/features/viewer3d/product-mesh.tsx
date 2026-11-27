"use client";

import { BRAND } from "@/lib/brand";

import { Select } from "@react-three/postprocessing";
import { Edges } from "@react-three/drei";
import { animated, config, useSpring } from "@react-spring/three";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef } from "react";
import {
  BackSide,
  Color,
  EdgesGeometry,
  Group,
  LineSegments,
  type BufferGeometry,
  Mesh,
  OrthographicCamera,
  SRGBColorSpace,
  SphereGeometry,
  type Plane,
} from "three";
import { acceleratedRaycast } from "three-mesh-bvh";
import type { Vec3 } from "@/workers/ifc-protocol";
import type { PreparedProduct } from "./model-resource";
import { BasicMaterial, PlantMaterial, SteelMaterial } from "./materials";
import { surfaceFinish } from "./plant-materials";
import { morphElapsed, morphProgress, morphTransform, type MorphFrom } from "./change-morph";

/** Opacidad de lo que aún tapa el componente encuadrado. */
export const GHOST_OPACITY = 0.16;
/** Un clic tras arrastrar más de estos píxeles es una órbita, no una selección. */
const CLICK_SLOP_PX = 5;
const noRaycast = () => null;

export type ElementState =
  "draft" | "approved" | "assumed" | "changed" | "conflict";
export const STATE_COLORS: Record<ElementState, string> = {
  draft: BRAND.steel,
  approved: BRAND.approved,
  assumed: BRAND.skyLight,
  changed: BRAND.revision,
  conflict: BRAND.danger,
};

function HitTarget({
  radius,
  onClick,
  onOver,
  onOut,
  onFocus,
}: {
  radius: number;
  onClick(event: ThreeEvent<MouseEvent>): void;
  onOver(event: ThreeEvent<PointerEvent>): void;
  onOut(): void;
  onFocus(event: ThreeEvent<MouseEvent>): void;
}) {
  const ref = useRef<Mesh>(null),
    camera = useThree((state) => state.camera);
  const geometry = useMemo(() => new SphereGeometry(1, 10, 8), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useFrame(() => {
    ref.current?.scale.setScalar(
      Math.max(
        radius,
        camera instanceof OrthographicCamera ? 12 / camera.zoom : radius,
      ),
    );
  });
  return (
    <mesh
      ref={ref}
      geometry={geometry}
      scale={radius}
      dispose={null}
      onClick={onClick}
      onPointerOver={onOver}
      onPointerOut={onOut}
      onDoubleClick={onFocus}
    >
      <BasicMaterial
        transparent
        opacity={0}
        colorWrite={false}
        depthWrite={false}
      />
    </mesh>
  );
}

export function ProductMesh({
  product,
  position = product.center,
  scale = [1, 1, 1],
  opacity = 1,
  selected = false,
  hovered = false,
  state = "draft",
  mode = "solid",
  planes,
  wireframe = false,
  immediate = false,
  onSelect,
  onHover,
  onFocus,
  color,
  useIfcColors = false,
  ghost = false,
  dashed = false,
  morph,
}: {
  product: PreparedProduct;
  position?: Vec3;
  scale?: Vec3;
  opacity?: number;
  selected?: boolean;
  hovered?: boolean;
  state?: ElementState;
  mode?: "solid" | "xray" | "exploded";
  planes?: Plane[];
  wireframe?: boolean;
  immediate?: boolean;
  color?: string;
  /** Color y acabado PBR de cada geometría según su estilo IFC (escenarios de proceso). */
  useIfcColors?: boolean;
  /** Tapa el componente encuadrado: se atenúa, deja de escribir profundidad y no intercepta clics. */
  ghost?: boolean;
  /** Soldadura: trazo discontinuo encima del modelo, con el color del estilo IFC. */
  dashed?: boolean;
  /** Transformación desde la envolvente de la carga anterior (borradores y revisiones). */
  morph?: { from: MorphFrom; clock: { start: number } };
  onSelect?(id: string): void;
  onHover?(id: string | null): void;
  onFocus?(id: string): void;
}) {
  const reduced = useReducedMotion();
  const inner = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);
  const morphing = !!morph && !reduced;
  // La geometría ya es la nueva: el grupo interior la lleva desde la forma anterior hasta 1:1.
  useFrame((state) => {
    const group = inner.current;
    if (!group) return;
    if (!morph || reduced) {
      group.position.set(0, 0, 0);
      group.scale.set(1, 1, 1);
      group.quaternion.identity();
      return;
    }
    const t = morphProgress(morphElapsed(morph.clock, state.clock.elapsedTime));
    const { position, scale } = morphTransform(morph.from, t);
    group.position.set(...position);
    group.scale.set(...scale);
    group.quaternion.identity().slerp(morph.from.rotation, 1 - t);
    if (t < 1) invalidate();
  });
  const spring = useSpring({
    px: position[0],
    py: position[1],
    pz: position[2],
    sx: scale[0],
    sy: scale[1],
    sz: scale[2],
    opacity: mode === "xray" ? opacity * 0.22 : ghost ? Math.min(opacity, GHOST_OPACITY) : opacity,
    immediate: immediate || !!reduced || morphing,
    config: config.default,
  });
  const finishes = useMemo(
    () => (useIfcColors ? product.parts.map((part) => surfaceFinish(part.style, part.color)) : null),
    [useIfcColors, product.parts],
  );
  const tint = color ?? STATE_COLORS[state];
  const activeColor = tint;
  const click = (event: ThreeEvent<MouseEvent>) => {
    if (planes?.some(plane => plane.distanceToPoint(event.point) < 0)) return;
    event.stopPropagation();
    if (event.delta > CLICK_SLOP_PX) return;
    onSelect?.(product.semanticId);
  };
  const over = (event: ThreeEvent<PointerEvent>) => {
    if (planes?.some(plane => plane.distanceToPoint(event.point) < 0)) return;
    event.stopPropagation();
    onHover?.(product.semanticId);
  };
  const focus = (event: ThreeEvent<MouseEvent>) => {
    if (planes?.some(plane => plane.distanceToPoint(event.point) < 0)) return;
    event.stopPropagation();
    onFocus?.(product.semanticId);
  };
  const interactive = opacity > 0.05 && !wireframe && !!onSelect && !ghost;
  const depthWrite = mode !== "xray" && opacity >= 0.99 && !ghost;
  return (
    <Select enabled={selected || hovered}>
      <animated.group
        position-x={spring.px}
        position-y={spring.py}
        position-z={spring.pz}
        scale-x={spring.sx}
        scale-y={spring.sy}
        scale-z={spring.sz}
        dispose={null}
      >
        <group ref={inner}>
        {product.geometries.map((geometry, i) => {
          const part = product.parts[i];
          const paint = useIfcColors && state !== "changed" && part
            ? `#${new Color().setRGB(...part.color.slice(0, 3) as Vec3, SRGBColorSpace).getHexString()}`
            : activeColor;
          // Con acabados PBR el resaltado es un tinte leve: el contorno marca la selección sin lavar el material.
          const surface = {
            color: paint,
            emissive: selected || hovered ? BRAND.sky : BRAND.black,
            emissiveIntensity: useIfcColors ? (selected ? 0.05 : hovered ? 0.04 : 0) : selected ? 0.12 : hovered ? 0.05 : 0,
            transparent: true,
            opacity: spring.opacity,
            depthWrite,
            wireframe: wireframe || state === "assumed",
            clippingPlanes: planes ?? [],
          };
          return (
          <mesh
            key={i}
            geometry={geometry}
            castShadow={useIfcColors}
            receiveShadow={useIfcColors}
            raycast={ghost ? noRaycast : acceleratedRaycast}
            onClick={interactive ? click : undefined}
            onPointerOver={interactive ? over : undefined}
            onPointerOut={interactive ? () => onHover?.(null) : undefined}
            onDoubleClick={interactive ? focus : undefined}
          >
            {finishes?.[i] ? (
              <PlantMaterial finish={finishes[i]} {...surface} {...(wireframe ? { metalness: 0 } : {})} />
            ) : (
              <SteelMaterial
                {...surface}
                metalness={wireframe ? 0 : 0.85}
                roughness={0.34}
              />
            )}
            {dashed ? (
              <DashedEdges
                geometry={geometry}
                color={selected || hovered ? BRAND.skyPale : part
                  ? `#${new Color().setRGB(...part.color.slice(0, 3) as Vec3, SRGBColorSpace).getHexString()}`
                  : BRAND.weld}
                planes={planes}
              />
            ) : null}
            {(selected || hovered) && opacity > 0.01 && !ghost && !useIfcColors && !dashed ? (
              <Edges
                threshold={20}
                color={selected ? BRAND.skyPale : BRAND.skyLight}
                lineWidth={1.2}
              />
            ) : null}
          </mesh>
          );
        })}
        {selected && opacity > 0.01 && !ghost
          ? product.geometries.map((geometry, i) => (
              <mesh
                key={`outline-${i}`}
                geometry={geometry}
                scale={1.018}
                raycast={() => null}
              >
                <BasicMaterial
                  side={BackSide}
                  color={BRAND.skyPale}
                  transparent
                  opacity={0.8}
                  depthWrite={false}
                  clippingPlanes={planes ?? []}
                />
              </mesh>
            ))
          : null}
        </group>
        {product.semanticId.startsWith("nozzle:") && interactive ? (
          <HitTarget
            radius={Math.max(
              0.15,
              (product.bounds.max[1] - product.bounds.min[1]) * 0.8,
            )}
            onClick={click}
            onOver={over}
            onOut={() => onHover?.(null)}
            onFocus={focus}
          />
        ) : null}
      </animated.group>
    </Select>
  );
}

/** Aristas de la geometría IFC en discontinua, siempre visibles: la soldadura va sobre la chapa. */
function DashedEdges({ geometry, color, planes }: { geometry: BufferGeometry; color: string; planes?: Plane[] }) {
  const edges = useMemo(() => new EdgesGeometry(geometry, 25), [geometry]);
  useEffect(() => () => edges.dispose(), [edges]);
  const line = useRef<LineSegments>(null);
  // El discontinuo necesita la distancia acumulada de cada vértice de la línea.
  useEffect(() => {
    line.current?.computeLineDistances();
  }, [edges]);
  return (
    <lineSegments ref={line} geometry={edges} renderOrder={10} raycast={noRaycast}>
      <lineDashedMaterial
        color={color}
        dashSize={0.04}
        gapSize={0.03}
        depthTest={false}
        transparent
        clippingPlanes={planes ?? []}
      />
    </lineSegments>
  );
}

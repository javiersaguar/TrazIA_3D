"use client";

import { BRAND } from "@/lib/brand";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useReducedMotion } from "motion/react";
import { useMemo, useRef, type ComponentRef } from "react";
import { Vector3, type Group } from "three";
import type { Bounds, IfcModel, Vec3 } from "@/workers/ifc-protocol";
import type { PreparedProduct } from "./model-resource";
import { dimensionGeometry } from "./dimension-geometry";
import { placedDimension } from "./equipment-layout";
import { elementForField } from "./semantic";
import { ifcTraces } from "./ifc-trace";
import type { Annotation } from "./types";
import styles from "./viewer.module.css";
import { SceneLabel as Html } from "./stage";

const LINE_OPACITY = .64;
const ignoreRaycast = () => {};

export type DimensionInteraction = "preview" | "leave" | "toggle" | "close";

export function dimensionValue(annotation: Annotation) {
  const amount = (annotation.drawingValue ?? annotation.value).toLocaleString("es-ES", { maximumFractionDigits: 3 });
  return annotation.nominalSize !== undefined ? `NPS ${annotation.nominalSize}`
    : annotation.unit === "deg" ? `${amount}°`
    : `${annotation.id.endsWith("diameter") ? "Ø " : ""}${amount} ${annotation.unit}`;
}

function Dimension({ points, anchors, label, annotation, detailsId, detailsOpen, onDetails }: NonNullable<ReturnType<typeof dimensionGeometry>> & {
  annotation: Annotation;
  detailsId: string;
  detailsOpen: boolean;
  onDetails: (annotation: Annotation, interaction: DimensionInteraction) => void;
}) {
  const group = useRef<Group>(null);
  const elapsed = useRef(0);
  const reducedMotion = useReducedMotion();
  useFrame(({ invalidate }, delta) => {
    if (reducedMotion || elapsed.current >= .3 || !group.current) return;
    elapsed.current = Math.min(.3, elapsed.current + Math.min(delta, 1 / 30));
    const opacity = LINE_OPACITY * (1 - (1 - elapsed.current / .3) ** 3);
    for (const line of group.current.children as ComponentRef<typeof Line>[]) line.material.opacity = opacity;
    if (elapsed.current < .3) invalidate();
  });

  const color = annotation.confidence >= .9 ? BRAND.skyPale : annotation.confidence >= .6 ? BRAND.warning : BRAND.danger;
  const value = dimensionValue(annotation);
  const from = points[0]!, to = points.at(-1)!;
  const marks = [from, to].map((point, i) => {
    const inward = new Vector3(...(i === 0 ? points[1]! : points.at(-2)!)).sub(new Vector3(...point)).normalize();
    const across = inward.clone().cross(new Vector3(0, 0, 1));
    if (across.lengthSq() < 1e-6) across.set(0, 1, 0);
    const length = Math.min(.09, new Vector3(...from).distanceTo(new Vector3(...to)) / 4);
    const arrow = new Vector3(...point).addScaledVector(inward, length);
    across.normalize().multiplyScalar(length * .38);
    return [arrow.clone().add(across).toArray(), point, arrow.clone().sub(across).toArray()];
  });
  const lineProps = { color, transparent: true, opacity: reducedMotion ? LINE_OPACITY : 0, depthWrite: false, raycast: ignoreRaycast };

  return <group>
    <group ref={group}>
      <Line points={points} lineWidth={1.15} {...lineProps} />
      <Line points={[anchors[0], from]} lineWidth={.8} {...lineProps} />
      <Line points={[anchors[1], to]} lineWidth={.8} {...lineProps} />
      {marks.map((arrow, i) => <Line key={i} points={arrow} lineWidth={1.15} {...lineProps} />)}
    </group>
    <Html position={label} center style={{ pointerEvents: "none" }} zIndexRange={[8, 0]}>
      <button type="button" className={styles.dimensionInfo} style={{ color }}
        data-capture-label
        aria-label={`${annotation.label.replaceAll(" · ", ", ")}: ${value}${annotation.state === "assumed" ? " estimados" : ""}. Ver fuente y confianza`}
        aria-expanded={detailsOpen} aria-controls={detailsOpen ? detailsId : undefined}
        onPointerEnter={event => { if (event.pointerType !== "touch") onDetails(annotation, "preview"); }}
        onPointerLeave={() => onDetails(annotation, "leave")}
        onFocus={event => { if (event.currentTarget.matches(":focus-visible")) onDetails(annotation, "preview"); }}
        onBlur={() => onDetails(annotation, "leave")}
        onPointerDown={event => event.stopPropagation()}
        onClick={() => onDetails(annotation, "toggle")}
        onKeyDown={event => {
          if (event.key !== "Escape" || !detailsOpen) return;
          event.stopPropagation();
          onDetails(annotation, "close");
        }}>
        <span className={styles.dimensionValue}>{annotation.state === "assumed" ? "≈ " : ""}{value}</span>
      </button>
    </Html>
  </group>;
}

export function Dimensions({ annotations, products, bounds, top, detailsId, openAnnotation, onDetails }: {
  annotations: Annotation[]; products: PreparedProduct[]; bounds: Bounds; top: boolean;
  detailsId: string; openAnnotation?: Annotation;
  onDetails: (annotation: Annotation, interaction: DimensionInteraction) => void;
}) {
  const dimensions = useMemo(() => {
    const shell = products.find(product => product.semanticId === "shell");
    return annotations.flatMap((annotation, index) => {
      const id = annotation.productId ?? elementForField(annotation.id);
      const product = products.find(candidate => candidate.semanticId === id);
      if (!product) return [];
      const trace = annotation.source ? undefined : ifcTraces(product.psets)[annotation.id];
      const enriched = trace ? { ...annotation, source: trace.source, confidence: trace.source.confidence,
        state: trace.state, explanation: trace.explanation } : annotation;
      const aligned = enriched.drawingValue === undefined ? placedDimension(enriched, products, bounds, index, top) : null;
      const geometry = aligned ? {
        points: [aligned.from, aligned.to],
        anchors: [aligned.anchorFrom, aligned.anchorTo] as [Vec3, Vec3],
        label: new Vector3(...aligned.from).lerp(new Vector3(...aligned.to), .5).toArray(),
      } : dimensionGeometry(enriched, product, shell, index);
      return geometry ? [{ geometry, annotation: enriched }] : [];
    }).slice(0, 5);
  }, [annotations, products, bounds, top]);

  return <>{dimensions.map(({ geometry, annotation }) => (
    <Dimension key={`${annotation.productId ?? ""}:${annotation.id}`} {...geometry} annotation={annotation}
      detailsId={detailsId} detailsOpen={openAnnotation?.id === annotation.id && openAnnotation.productId === annotation.productId}
      onDetails={onDetails} />
  ))}</>;
}

export function AzimuthRing({ model }: { model: IfcModel }) {
  const shell = model.products.find(p => p.semanticId === "shell");
  const x = shell?.center[0] ?? 0, z = shell?.center[2] ?? 0, y = model.bounds.min[1] + .03;
  const radius = Math.max(Math.abs(model.bounds.max[0] - x), Math.abs(model.bounds.min[0] - x),
    Math.abs(model.bounds.max[2] - z), Math.abs(model.bounds.min[2] - z)) + .5;
  const ring = useMemo(() => Array.from({ length: 97 }, (_, i) => {
    const angle = i / 96 * Math.PI * 2;
    return [radius * Math.cos(angle), .03, -radius * Math.sin(angle)] as Vec3;
  }), [radius]);
  return <group position={[x, y - .03, z]}>
    <Line points={ring} color={BRAND.steelDark} lineWidth={1} />
    {Array.from({ length: 12 }, (_, i) => {
      const angle = i * Math.PI / 6;
      return <group key={i}>
        <Line points={[[radius * .96 * Math.cos(angle), .03, -radius * .96 * Math.sin(angle)],
          [radius * Math.cos(angle), .03, -radius * Math.sin(angle)]]} color={BRAND.textMuted} lineWidth={1} />
        <Html position={[(radius + .16) * Math.cos(angle), .03, -(radius + .16) * Math.sin(angle)]} center
          zIndexRange={[5, 0]} style={{ pointerEvents: "none", color: BRAND.textMuted, fontSize: 10 }}>{i * 30}°</Html>
      </group>;
    })}
    {model.products.filter(p => p.semanticId.startsWith("nozzle:")).map(product => {
      const angle = Math.atan2(-(product.center[2] - z), product.center[0] - x);
      const point: Vec3 = [radius * Math.cos(angle), .04, -radius * Math.sin(angle)];
      return <group key={product.globalId}>
        <Line points={[[0, .04, 0], point]} color={BRAND.skyLight} dashed dashSize={.08} gapSize={.07} lineWidth={.8} />
        <Html position={point} center zIndexRange={[6, 0]} style={{ pointerEvents: "none" }}>
          <span className={styles.label}>{product.semanticId.replace("nozzle:", "")} · {((angle * 180 / Math.PI + 360) % 360).toFixed(0)}°</span>
        </Html>
      </group>;
    })}
  </group>;
}

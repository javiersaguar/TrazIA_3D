"use client";

import { Edges } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Group, Mesh, MeshPhysicalMaterial, Quaternion, Vector3 } from "three";
import { BRAND } from "@/lib/brand";
import { brushedTextures, retainBrushedTextures } from "../viewer3d/brushed-textures";
import { segmentProgress, timelineAt } from "./morph";
import type { RevisionTimeline } from "./revision-timeline";

export type TimelineSnapshot = { value: number; playing: boolean; speed: number };

export function AnimatedPair({
  entry: { pair, motion, index },
  count,
  selected,
  hovered,
  highlightChanges,
  read,
  onSelect,
  onHover,
}: {
  entry: RevisionTimeline["pairs"][number];
  count: number;
  selected: boolean;
  hovered: boolean;
  highlightChanges: boolean;
  read(): TimelineSnapshot;
  onSelect(id: string): void;
  onHover(id: string | null): void;
}) {
  const source = useRef<Group>(null);
  const target = useRef<Group>(null);
  const product = (pair.after ?? pair.before)!;
  const materials = useMemo(() => {
    const source = new MeshPhysicalMaterial({
      color: BRAND.steel, metalness: 0.85, roughness: 0.34, clearcoat: 0.2, transparent: true, ...brushedTextures(),
    });
    return { source, target: source.clone() };
  }, []);
  useEffect(() => {
    const release = retainBrushedTextures();
    return () => {
      materials.source.dispose();
      materials.target.dispose();
      release();
    };
  }, [materials]);
  const pose = useMemo(() => {
    if (motion.kind !== "transform" || !pair.before || !pair.after) return null;
    const { scale, rotation, offset } = motion.transform;
    return {
      start: new Vector3(...pair.before.center),
      end: new Vector3(...pair.after.center).add(new Vector3(...offset)),
      scale: new Vector3(...scale),
      rotation,
      identity: new Quaternion(),
    };
  }, [motion, pair]);
  useFrame(() => {
    const progress = read().value;
    const t = segmentProgress(progress, index, count);
    const { index: activeIndex, phase } = timelineAt(progress, count);
    const pulse = activeIndex === index ? Math.sin(phase * Math.PI) ** 2 : 0;
    if (source.current && pose) {
      source.current.position.lerpVectors(pose.start, pose.end, t);
      source.current.scale.set(1, 1, 1).lerp(pose.scale, t);
      source.current.quaternion.slerpQuaternions(pose.identity, pose.rotation, t);
    }
    const from = pose ? Number(t < 1) : 1 - t;
    const to = pose ? Number(t === 1) : t;
    if (source.current) source.current.visible = from > 0;
    if (target.current) target.current.visible = to > 0;
    materials.target.color.set(highlightChanges && t === 1 ? BRAND.revision : BRAND.steel);
    for (const [material, opacity] of [[materials.source, from], [materials.target, to]] as const) {
      material.opacity = opacity;
      material.depthWrite = opacity === 1;
      material.emissive.set(BRAND.revision);
      material.emissiveIntensity = pulse * 0.35 + (hovered ? 0.11 : selected ? 0.06 : 0);
    }
  });
  const ids = { from: pair.before?.semanticId ?? product.semanticId, to: product.semanticId };
  return (
    <group dispose={null}>
      {([[pair.before, source, materials.source, ids.from], [pair.after, target, materials.target, ids.to]] as const).map(
        ([side, ref, material, id], index) => side && (
          <group
            key={index}
            ref={ref}
            position={side.center}
            visible={index === 0}
            onClick={(e) => { e.stopPropagation(); onSelect(id); }}
            onPointerOver={(e) => { e.stopPropagation(); onHover(id); }}
            onPointerOut={() => onHover(null)}
          >
            {side.geometries.map((geometry, i) => (
              <mesh key={i} geometry={geometry} material={material} raycast={function (this: Mesh, raycaster, hits) {
                if (ref.current?.visible) Mesh.prototype.raycast.call(this, raycaster, hits);
              }}>
                {selected || hovered ? <Edges color={BRAND.revision} threshold={20} /> : null}
              </mesh>
            ))}
          </group>
        ),
      )}
    </group>
  );
}

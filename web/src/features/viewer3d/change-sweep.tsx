"use client";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Box3, Group, Mesh } from "three";
import { Vector3 } from "three";
import { BRAND } from "@/lib/brand";
import type { Vec3 } from "@/workers/ifc-protocol";
import { MORPH_SECONDS, morphElapsed, morphProgress } from "./change-morph";
import { SceneLabel } from "./stage";
import styles from "./viewer.module.css";

/**
 * Aro que barre el equipo mientras se transforma y rótulo Δ con la cota que cambia, como en
 * «Visualizar cambios». Se apaga solo al terminar.
 */
export function ChangeSweep({ box, label, clock }: { box: Box3; label?: string; clock: { start: number } }) {
  const ring = useRef<Mesh>(null), group = useRef<Group>(null);
  const center = box.getCenter(new Vector3()), extent = box.getSize(new Vector3());
  const radius = Math.max(0.3, Math.hypot(extent.x, extent.z) * 0.55);
  const anchor: Vec3 = [box.max.x + Math.max(0.6, extent.x * 0.08), box.max.y + 0.4, center.z];
  useFrame((state) => {
    const elapsed = morphElapsed(clock, state.clock.elapsedTime);
    const t = morphProgress(elapsed);
    if (group.current) group.current.visible = elapsed < MORPH_SECONDS + 1.2;
    if (ring.current) {
      ring.current.visible = t > 0 && t < 1;
      ring.current.position.set(center.x, box.min.y + extent.y * t, center.z);
    }
  });
  return <group ref={group}>
    <mesh ref={ring} rotation={[Math.PI / 2, 0, 0]} visible={false} raycast={() => null}>
      <torusGeometry args={[radius, Math.max(0.02, radius * 0.012), 6, 72]} />
      <meshBasicMaterial color={BRAND.revision} transparent opacity={0.85} depthWrite={false} toneMapped={false} />
    </mesh>
    {label ? <>
      <Line points={[[center.x, box.max.y, center.z], anchor]} color={BRAND.revision} dashed dashSize={0.12} gapSize={0.08} />
      <SceneLabel position={anchor} center zIndexRange={[8, 0]} style={{ pointerEvents: "none" }}>
        <span className={styles.delta}>Δ {label}</span>
      </SceneLabel>
    </> : null}
  </group>;
}

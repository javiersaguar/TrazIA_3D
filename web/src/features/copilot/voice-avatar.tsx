"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useReducedMotion } from "motion/react";
import { useMemo, useRef } from "react";
import { Group, Mesh, Shape } from "three";
import { CopilotMark } from "@/components/brand/copilot-mark";
import type { AvatarState } from "./voice-conversation";
import styles from "./voice-conversation.module.css";

const colors: Record<AvatarState, string> = {
  idle: "#65a6d7",
  listening: "#52e6fa",
  thinking: "#ffc981",
  speaking: "#9befff",
};

function avatarProfile() {
  const shape = new Shape();
  shape.moveTo(-0.79, -0.41);
  shape.lineTo(-0.59, -0.54);
  shape.lineTo(-0.59, -0.82);
  shape.lineTo(-0.31, -0.54);
  shape.lineTo(0.33, -0.54);
  shape.lineTo(0.79, -0.18);
  shape.lineTo(0.79, 0.25);
  shape.lineTo(0.26, 0.65);
  shape.lineTo(-0.64, 0.65);
  shape.lineTo(-0.79, 0.5);
  shape.closePath();
  return shape;
}

function AvatarModel({ state, animated }: { state: AvatarState; animated: boolean }) {
  const head = useRef<Group>(null);
  const mouth = useRef<Mesh>(null);
  const ring = useRef<Mesh>(null);
  const shape = useMemo(() => avatarProfile(), []);
  const casing = useMemo(() => ({ depth: 0.28, bevelEnabled: true, bevelSegments: 3, bevelThickness: 0.08, bevelSize: 0.08 }), []);
  const visor = useMemo(() => ({ depth: 0.05, bevelEnabled: true, bevelSegments: 2, bevelThickness: 0.036, bevelSize: 0.03 }), []);
  const accent = colors[state];
  useFrame(({ clock }, delta) => {
    if (!animated || !head.current || !mouth.current || !ring.current) return;
    const time = clock.elapsedTime;
    const easing = 1 - Math.exp(-delta * 10);
    const turn = state === "thinking" ? 0.20 : state === "listening" ? -0.12 : 0.08;
    head.current.rotation.y += (turn + Math.sin(time * 1.75) * 0.09 - head.current.rotation.y) * easing;
    head.current.position.y += (Math.sin(time * 2.4) * 0.08 - head.current.position.y) * easing;
    const opening = state === "speaking" ? 0.035 + Math.abs(Math.sin(time * 16) * Math.cos(time * 7)) * 0.095 : 0.024;
    mouth.current.scale.y += (opening - mouth.current.scale.y) * easing;
    ring.current.rotation.z += delta * (state === "thinking" ? 1 : 0.22);
  });

  return <>
    <ambientLight intensity={1.15} />
    <directionalLight position={[-3, 4, 6]} intensity={3} color="#cceaff" />
    <pointLight position={[3, -1, 1]} intensity={14} color="#29a0ff" />
    <mesh ref={ring} rotation={[0.27, -0.16, 0]} position={[0, 0, -0.48]}>
      <torusGeometry args={[1.18, 0.012, 6, 64, Math.PI * 1.73]} />
      <meshBasicMaterial color={accent} transparent opacity={0.55} />
    </mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.04, -0.12]}>
      <ringGeometry args={[0.66, 0.70, 64]} />
      <meshBasicMaterial color={accent} transparent opacity={0.32} />
    </mesh>
    <group ref={head} rotation={[0.08, -0.10, 0]}>
      <mesh>
        <extrudeGeometry args={[shape, casing]} />
        <meshStandardMaterial color="#255684" metalness={0.53} roughness={0.31} />
      </mesh>
      <mesh position={[0, 0.02, 0.36]} scale={0.84}>
        <extrudeGeometry args={[shape, visor]} />
        <meshStandardMaterial color="#0b1927" roughness={0.26} metalness={0.27} />
      </mesh>
      {[-0.28, 0.26].map(x => <mesh key={x} position={[x, 0.17, 0.45]} scale={[0.087, 0.12, 0.033]}>
        <sphereGeometry args={[1, 16, 12]} />
        <meshBasicMaterial color={accent} />
      </mesh>)}
      <mesh ref={mouth} position={[-0.02, -0.18, 0.45]} scale={[0.18, state === "speaking" ? 0.065 : 0.024, 0.035]}>
        <sphereGeometry args={[1, 16, 12]} />
        <meshBasicMaterial color={accent} />
      </mesh>
    </group>
  </>;
}

export default function VoiceAvatar({ state }: { state: AvatarState }) {
  const reduced = useReducedMotion();
  const animated = !reduced && state !== "idle";
  return <Canvas
    aria-hidden="true"
    camera={{ position: [0, 0.27, 4.5], fov: 37 }}
    dpr={[1, 1.5]}
    frameloop={animated ? "always" : "demand"}
    fallback={<CopilotMark className={styles.placeholder} />}
    gl={{ alpha: true, antialias: true }}
  >
    <AvatarModel state={state} animated={animated} />
  </Canvas>;
}

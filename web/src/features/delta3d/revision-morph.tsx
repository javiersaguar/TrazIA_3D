"use client";

import { Grid, Line } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { Eye, LocateFixed, Pause, Play, SkipForward } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { Vector3 } from "three";
import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type Ref,
  type RefObject,
} from "react";
import type { Bounds } from "@/workers/ifc-protocol";
import { BRAND } from "@/lib/brand";
import { useSelection } from "@/stores/selection";
import { CameraLink } from "../viewer3d/camera-link";
import {
  useIfcModel,
  usePreparedModel,
  type PreparedProduct,
} from "../viewer3d/model-resource";
import { ProductMesh } from "../viewer3d/product-mesh";
import {
  CameraRig,
  CameraTools,
  LoadingState,
  SceneCanvas,
  SceneLabel,
  Studio,
  type CameraHandle,
} from "../viewer3d/stage";
import type { RevisionMorphProps } from "../viewer3d/types";
import { parentElementId } from "../viewer3d/semantic";
import { AnimatedPair, type TimelineSnapshot } from "./animated-pair";
import {
  clampProgress,
  dimensionText,
  segmentProgress,
  SEGMENT_SECONDS,
  timelineAt,
  type ChangeStep,
} from "./morph";
import { revisionTimeline, unionBounds, type RevisionTimeline } from "./revision-timeline";
import styles from "../viewer3d/viewer.module.css";
import deltaStyles from "./timeline.module.css";

type Playback = { seek(value: number): void; play(): void; pause(): void };
type Props = RevisionMorphProps & {
  showNarration?: boolean;
  playing?: boolean;
  autoPlay?: boolean;
  speed?: number;
  split?: boolean;
  realData?: boolean;
  highlightChanges?: boolean;
  /** Productos ya preparados. Si llegan los dos, no se usa la geometría cargada de las URL. */
  beforeProducts?: PreparedProduct[];
  afterProducts?: PreparedProduct[];
  fromLabel?: string;
  toLabel?: string;
  onStep?(id: string, index: number, count: number, narration: string): void;
  onPlayingChange?(value: boolean): void;
  onComplete?(): void;
};

function Dimension({
  step,
  anchor,
  read,
  index,
  count,
}: {
  step: ChangeStep;
  anchor: NonNullable<RevisionTimeline["steps"][number]["anchor"]>;
  read(): TimelineSnapshot;
  index: number;
  count: number;
}) {
  const label = useRef<HTMLSpanElement>(null),
    group = useRef<import("three").Group>(null);
  const { before, after } = anchor.pair;
  const product = (after ?? before)!;
  const { motion } = anchor;
  const start = useMemo(() => new Vector3(...(before ?? product).center), [before, product]);
  const end = useMemo(() => {
    const center = new Vector3(...product.center);
    return motion.kind === "transform" ? center.add(new Vector3(...motion.transform.offset)) : center;
  }, [motion, product]);
  const position = [
    product.bounds.max[0] - product.center[0] + 0.65,
    0,
    product.bounds.max[2] - product.center[2] + 0.3,
  ] as [number, number, number];
  useFrame(() => {
    const value = read().value,
      active = value > 0 && value < 1 && timelineAt(value, count).index === index;
    const t = segmentProgress(value, index, count);
    const visible = active && (before !== null || t > 0) && (after !== null || t < 1);
    if (group.current) {
      group.current.visible = visible;
      if (motion.kind === "transform") group.current.position.lerpVectors(start, end, t);
      else group.current.position.copy(t < 0.5 ? start : end);
    }
    if (label.current) {
      label.current.style.display = visible ? "block" : "none";
      label.current.textContent = dimensionText(step, t, motion.kind === "transform");
    }
  });
  return (
    <group ref={group}>
      <Line
        points={[[0, 0, 0], position]}
        color={BRAND.revision}
        dashed
        dashSize={0.07}
        gapSize={0.05}
      />
      <SceneLabel
        position={position}
        center
        zIndexRange={[8, 0]}
        style={{ pointerEvents: "none" }}
      >
        <span ref={label} className={styles.delta}>
          Δ {step.label}
        </span>
      </SceneLabel>
    </group>
  );
}

function TimelineScene({
  a,
  b,
  bounds,
  timeline,
  progress,
  playing,
  speed,
  ghost,
  follow,
  selectedId,
  hoveredId,
  onlyChanged,
  highlightChanges,
  playback,
  pending,
  camera,
  onTick,
  onStep,
  onStop,
  onComplete,
  onSelect,
  onHover,
}: {
  a: PreparedProduct[];
  b: PreparedProduct[];
  bounds: Bounds;
  timeline: RevisionTimeline;
  progress?: number;
  playing: boolean;
  speed: number;
  ghost: boolean;
  follow: boolean;
  selectedId: string | null;
  hoveredId: string | null;
  onlyChanged: boolean;
  highlightChanges: boolean;
  playback: Ref<Playback>;
  /** Valor pedido con el deslizador antes de que la escena existiera. */
  pending: RefObject<number | null>;
  camera: Ref<CameraHandle>;
  onTick(value: number): void;
  onStep(index: number): void;
  onStop(): void;
  onComplete?(): void;
  onSelect(id: string): void;
  onHover(id: string | null): void;
}) {
  const invalidate = useThree((s) => s.invalidate),
    reduced = useReducedMotion();
  const rig = useRef<CameraHandle>(null);
  const state = useRef<TimelineSnapshot>({
    value: progress ?? 0,
    playing,
    speed,
  });
  const last = useRef(-1),
    report = useRef(-1);
  const read = useCallback(() => state.current, []);
  const { pairs, steps } = timeline;
  const count = Math.max(1, steps.length);
  useEffect(() => {
    state.current.speed = speed;
  }, [speed]);
  // La escena se monta después del primer render del lienzo: aplica lo que se pidió mientras tanto
  useEffect(() => {
    const value = pending.current;
    if (value === null || progress !== undefined) return;
    state.current.value = clampProgress(value);
    state.current.playing = false;
    invalidate();
  }, [pending, progress, invalidate]);
  useEffect(() => {
    state.current.playing = playing;
    if (playing) last.current = -1;
    if (playing && state.current.value >= 1) state.current.value = 0;
    invalidate();
  }, [playing, invalidate]);
  useEffect(() => {
    if (progress !== undefined) {
      state.current.value = clampProgress(progress);
      state.current.playing = false;
      invalidate();
    }
  }, [progress, invalidate]);
  useEffect(() => {
    if (follow && !playing && selectedId) {
      const p =
        b.find((p) => p.semanticId === selectedId) ??
        a.find((p) => p.semanticId === selectedId);
      if (p) rig.current?.fit(p.bounds);
    }
  }, [follow, playing, selectedId, a, b]);
  useImperativeHandle(
    playback,
    () => ({
      seek(value) {
        state.current.value = clampProgress(value);
        state.current.playing = false;
        invalidate();
      },
      play() {
        if (state.current.value >= 1) state.current.value = 0;
        state.current.playing = true;
        invalidate();
      },
      pause() {
        state.current.playing = false;
        invalidate();
      },
    }),
    [invalidate],
  );
  useImperativeHandle(
    camera,
    () => ({
      view: (v) => rig.current?.view(v),
      fit: (v, n) => rig.current?.fit(v, n),
      zoom: (v) => rig.current?.zoom(v),
      capture: () => rig.current?.capture(),
    }),
    [],
  );
  useFrame((_, delta) => {
    const s = state.current;
    if (reduced && progress === undefined) {
      s.value = 1;
      if (s.playing) {
        s.playing = false;
        onStop();
      }
    } else if (s.playing)
      s.value = Math.min(
        1,
        s.value + (Math.min(delta, 0.2) * s.speed) / (SEGMENT_SECONDS * count),
      );
    const { index } = timelineAt(s.value, count);
    if (index !== last.current) {
      last.current = index;
      onStep(index);
      if (follow && (s.playing || s.value > 0)) {
        const focus = steps[index]?.bounds;
        if (focus) rig.current?.fit(focus);
      }
    }
    if (report.current !== s.value) {
      onTick(s.value);
      report.current = s.value;
    }
    if (s.playing) {
      if (s.value >= 1) {
        s.playing = false;
        onStop();
        onComplete?.();
      } else invalidate();
    }
  });
  return (
    <>
      <Studio />
      <CameraRig
        bounds={bounds}
        handle={rig}
        orbit={!playing}
        onUserControl={() => {
          state.current.playing = false;
          onStop();
        }}
      />
      <Grid
        position={[0, -0.02, 0]}
        args={[16, 16]}
        cellSize={0.5}
        sectionSize={2}
        cellColor={BRAND.surfaceRaised}
        sectionColor={BRAND.border}
        fadeDistance={18}
      />
      {ghost
        ? pairs
            .filter(({ motion }) => !onlyChanged || motion.kind !== "static")
            .flatMap(({ pair }) => pair.before ?? [])
            .map((p) => (
              <ProductMesh
                key={`ghost-${p.globalId}`}
                product={p}
                opacity={0.1}
                color={BRAND.skyDeep}
                wireframe
                immediate
              />
            ))
        : null}
      {pairs
        .filter(({ motion }) => !onlyChanged || motion.kind !== "static")
        .map((entry) => {
          const { pair, motion } = entry;
          const product = (pair.after ?? pair.before)!;
          const id = product.semanticId;
          if (motion.kind === "static") {
            return (
              <ProductMesh
                key={pair.globalId}
                product={product}
                selected={selectedId === id || selectedId === parentElementId(id)}
                hovered={hoveredId === id || hoveredId === parentElementId(id)}
                onSelect={onSelect}
                onHover={onHover}
                immediate
              />
            );
          }
          return (
            <AnimatedPair
              key={pair.globalId}
              entry={entry}
              count={count}
              highlightChanges={highlightChanges}
              selected={selectedId === id || selectedId === parentElementId(id)}
              hovered={hoveredId === id || hoveredId === parentElementId(id)}
              read={read}
              onSelect={onSelect}
              onHover={onHover}
            />
          );
        })}
      {steps.map((step, index) => {
        return step.anchor && step.fields.length ? (
          <Dimension
            key={step.id}
            step={step}
            anchor={step.anchor}
            read={read}
            index={index}
            count={count}
          />
        ) : null;
      })}
    </>
  );
}

export function RevisionMorph({
  fromUrl,
  toUrl,
  changes,
  progress,
  playing: externalPlaying,
  autoPlay = false,
  speed = 1,
  split = false,
  realData = false,
  highlightChanges = false,
  beforeProducts,
  afterProducts,
  fromLabel,
  toLabel,
  onProgress,
  onStep,
  onPlayingChange,
  onComplete,
  showNarration = true,
}: Props) {
  const before = useIfcModel(fromUrl),
    after = useIfcModel(toUrl),
    preparedA = usePreparedModel(beforeProducts ? null : before.model),
    preparedB = usePreparedModel(afterProducts ? null : after.model),
    a = beforeProducts ?? preparedA,
    b = afterProducts ?? preparedB;
  const [ownPlaying, setOwnPlaying] = useState(autoPlay),
    [follow, setFollow] = useState(true),
    [ghost, setGhost] = useState(false),
    [stepIndex, setStepIndex] = useState(0),
    [ownSpeed, setSpeed] = useState(speed);
  const playing = externalPlaying ?? ownPlaying;
  const root = useRef<HTMLDivElement>(null),
    camera = useRef<CameraHandle>(null),
    playback = useRef<Playback>(null),
    pending = useRef<number | null>(null),
    range = useRef<HTMLInputElement>(null),
    output = useRef<HTMLOutputElement>(null),
    badge = useRef<HTMLDivElement>(null);
  const selectedId = useSelection((s) => s.selectedId),
    setSelected = useSelection((s) => s.setSelected),
    hoveredId = useSelection((s) => s.hoveredId),
    setHovered = useSelection((s) => s.setHovered);
  const [onlyChanged, setOnlyChanged] = useState(false);
  const [orbiting, setOrbiting] = useState(true);
  const ready = beforeProducts && afterProducts ? a.length + b.length > 0 : !!before.model && !!after.model;
  const timeline = useMemo(
    () => ready ? revisionTimeline(a, b, changes, Boolean(beforeProducts)) : null,
    [a, b, changes, beforeProducts, ready],
  );
  const steps = timeline?.steps ?? [];
  const link = useMemo(() => new CameraLink(), []);
  const bounds = useMemo<Bounds>(() => {
    if (beforeProducts && afterProducts) {
      const lists = [beforeProducts, afterProducts];
      const min: Bounds["min"] = [Infinity, Infinity, Infinity];
      const max: Bounds["max"] = [-Infinity, -Infinity, -Infinity];
      for (const list of lists) {
        for (const product of list) {
          product.bounds.min.forEach((value, i) => {
            if (value < min[i]!) min[i] = value;
          });
          product.bounds.max.forEach((value, i) => {
            if (value > max[i]!) max[i] = value;
          });
        }
      }
      if (Number.isFinite(min[0])) return { min, max };
    }
    if (before.model && after.model) return unionBounds(before.model.bounds, after.model.bounds);
    return { min: [0, 0, 0], max: [2, 8, 2] };
  }, [before.model, after.model, beforeProducts, afterProducts]);
  const modifiedIds = useMemo(() => new Set(
    timeline?.pairs.filter(({ motion }) => motion.kind !== "static").map(({ pair }) => pair.globalId),
  ), [timeline]);
  const setPlaying = (v: boolean) => {
    if (v) pending.current = null;
    setOwnPlaying(v);
    onPlayingChange?.(v);
  };
  const stop = () => setPlaying(false);
  const seek = (value: number) => {
    stop();
    pending.current = value;
    playback.current?.seek(value);
    onProgress?.(value);
  };
  const provenance = realData ? "" : " · sintético";
  const error = before.error ?? after.error;
  const tick = (value: number) => {
    if (range.current) range.current.value = String(value);
    if (output.current)
      output.current.textContent = `${Math.round(value * 100)} %`;
    root.current?.setAttribute("data-progress", value.toFixed(3));
    if (badge.current)
      badge.current.textContent = beforeProducts
        ? "Simulación · Modelo IFC de referencia"
        : `${value === 1 ? "IFC B exacto" : value === 0 ? "IFC A exacto" : "Transición entre los IFC"}${provenance}`;
  };
  const step = steps[stepIndex];
  return (
    <div
      ref={root}
      className={styles.frame}
      data-testid="revision-morph"
      data-phase={ready ? "ready" : error ? "error" : "loading"}
      data-progress="0"
      data-geometry-changes={modifiedIds.size}
    >
      {timeline ? (
        split ? (
          <div className={deltaStyles.split}>
            {[a, b].map((products, i) => (
              <div key={i} className={deltaStyles.half}>
                <span className={deltaStyles.revision}>
                  {(i ? toLabel : fromLabel) ?? `rev ${i ? "B" : "A"} · IFC exacto`}
                </span>
                <SceneCanvas
                  label={`IFC ${i ? "B" : "A"}, cámaras sincronizadas`}
                  rotating={orbiting}
                  onRotationChange={setOrbiting}
                >
                  <Studio />
                  <CameraRig
                    bounds={bounds}
                    handle={i ? null : camera}
                    link={link}
                    orbit={i === 0}
                    onUserControl={() => setOrbiting(false)}
                  />
                  {products
                    .filter(
                      (p) => !onlyChanged || modifiedIds.has(p.globalId),
                    )
                    .map((p) => (
                      <ProductMesh
                        key={p.globalId}
                        product={p}
                        state={(beforeProducts || highlightChanges && i === 1) && modifiedIds.has(p.globalId) ? "changed" : "draft"}
                        selected={p.semanticId === selectedId}
                        hovered={p.semanticId === hoveredId}
                        onSelect={(id) => setSelected(id)}
                        onHover={setHovered}
                      />
                    ))}
                </SceneCanvas>
              </div>
            ))}
          </div>
        ) : (
          <SceneCanvas label="Comparación de revisiones IFC por identificador de pieza">
            <TimelineScene
              a={a}
              b={b}
              bounds={bounds}
              timeline={timeline}
              progress={progress}
              playing={playing}
              speed={ownSpeed}
              ghost={ghost}
              follow={follow}
              selectedId={selectedId}
              hoveredId={hoveredId}
              onlyChanged={onlyChanged}
              highlightChanges={highlightChanges}
              playback={playback}
              pending={pending}
              camera={camera}
              onTick={tick}
              onStep={(i) => {
                setStepIndex(i);
                const s = steps[i];
                if (s) {
                  onStep?.(s.elementId, i, steps.length, s.narration);
                  if (playing) setSelected(s.bounds ? s.elementId : null);
                }
              }}
              onStop={stop}
              onComplete={onComplete}
              onSelect={(id) => {
                stop();
                setSelected(id);
              }}
              onHover={setHovered}
            />
          </SceneCanvas>
        )
      ) : (
        <LoadingState error={error} />
      )}
      <CameraTools handle={camera} container={root} />
      <div
        className={styles.selectors}
        role="group"
        aria-label="Cámara de revisiones"
      >
        <button
          className={styles.button}
          aria-pressed={split || !follow}
          onClick={() => {
            setFollow(false);
            camera.current?.view("iso");
          }}
        >
          <Eye /> Vista general
        </button>
        {!split ? <button
          className={styles.button}
          aria-pressed={follow}
          onClick={() => setFollow((v) => !v)}
        >
          <LocateFixed /> Seguir el cambio
        </button> : null}
        <button
          className={styles.button}
          aria-pressed={onlyChanged}
          onClick={() => setOnlyChanged((v) => !v)}
        >
          Solo modificados
        </button>
        {!split ? <button
          className={styles.button}
          aria-pressed={ghost}
          onClick={() => setGhost((v) => !v)}
        >
          Fantasma A
        </button> : null}
      </div>
      {ready ? <div ref={badge} className={styles.badge}>
        {beforeProducts ? "Simulación · Modelo IFC de referencia" : `${split ? "IFC A | B exactos" : "IFC A exacto"}${provenance}`}
      </div> : null}
      {!split ? (
        <div className={deltaStyles.transport}>
          <div className={deltaStyles.marks}>
            {steps.map((s, i) => (
              <button
                key={s.id}
                aria-label={`Ir al cambio ${i + 1}: ${s.narration}`}
                onClick={() => seek(i / steps.length)}
                title={s.narration}
              >
                {i + 1}
              </button>
            ))}
          </div>
          <label className={deltaStyles.scrub}>
            A
            <input
              ref={range}
              className={styles.range}
              type="range"
              min="0"
              max="1"
              step=".001"
              defaultValue={progress ?? 0}
              aria-label="Interpolación IFC de A a B"
              disabled={!ready}
              onInput={(e) => seek(Number(e.currentTarget.value))}
            />
            B<output ref={output}>0 %</output>
          </label>
          {showNarration ? (
            <div className={deltaStyles.narration}>
              <button
                className={styles.button}
                disabled={!ready}
                aria-label={playing ? "Pausar morph" : "Reproducir morph"}
                onClick={() => {
                  if (playing) playback.current?.pause();
                  else playback.current?.play();
                  setPlaying(!playing);
                }}
              >
                {playing ? <Pause /> : <Play />}
              </button>
              <p>
                <strong>
                  {step
                    ? `Cambio ${stepIndex + 1} de ${steps.length}`
                    : "Revisiones A → B"}
                </strong>
                {step?.narration ??
                  "Arrastra el avance para comparar las dos revisiones IFC."}
              </p>
              <label className={deltaStyles.speed}>
                Velocidad
                <select
                  aria-label="Velocidad de los cambios"
                  value={ownSpeed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                >
                  {[0.5, 1, 2].map((v) => (
                    <option key={v} value={v}>
                      {v.toLocaleString("es-ES")}×
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={styles.button}
                aria-label="Siguiente cambio"
                onClick={() =>
                  seek(Math.min(1, (stepIndex + 1) / Math.max(1, steps.length)))
                }
              >
                <SkipForward />
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

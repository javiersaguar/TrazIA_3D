import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { IfcAPI } from "web-ifc";
import wasmUrl from "web-ifc/web-ifc.wasm?url";
import ifcUrl from "../../../web/public/demo/ifc/rev_b.ifc?url";
import { EXPORT } from "./modo.js";

// El IFC se lee una vez por sesión y se guarda la geometría ya fundida.
let cache;
async function leerTorre() {
  if (cache) return cache;
  cache = (async () => {
    const api = new IfcAPI();
    await api.Init((path) => (path.endsWith(".wasm") ? wasmUrl : path), true);
    const buffer = new Uint8Array(await (await fetch(ifcUrl)).arrayBuffer());
    const id = api.OpenModel(buffer);
    const pos = [];
    const idx = [];
    const m = new THREE.Matrix4();
    const p = new THREE.Vector3();
    let piezas = 0;
    api.StreamAllMeshes(id, (mesh) => {
      piezas++;
      for (let i = 0; i < mesh.geometries.size(); i++) {
        const placed = mesh.geometries.get(i);
        const g = api.GetGeometry(id, placed.geometryExpressID);
        const v = api.GetVertexArray(g.GetVertexData(), g.GetVertexDataSize());
        const ix = api.GetIndexArray(g.GetIndexData(), g.GetIndexDataSize());
        m.fromArray(placed.flatTransformation);
        const base = pos.length / 3;
        for (let j = 0; j < v.length; j += 6) {
          p.set(v[j], v[j + 1], v[j + 2]).applyMatrix4(m);
          pos.push(p.x, p.y, p.z);
        }
        for (let j = 0; j < ix.length; j++) idx.push(ix[j] + base);
        g.delete();
      }
    });
    api.CloseModel(id);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setIndex(idx);
    geo.computeBoundingBox();
    const bb = geo.boundingBox;
    const c = new THREE.Vector3();
    bb.getCenter(c);
    geo.translate(-c.x, -bb.min.y, -c.z);
    geo.computeBoundingBox();
    geo.computeBoundingSphere();
    const aristas = new THREE.EdgesGeometry(geo, 28);
    const b = geo.boundingBox;
    const radio = Math.max(Math.hypot(b.max.x, b.max.z), Math.hypot(b.min.x, b.min.z));
    return { geo, aristas, piezas, alto: bb.max.y - bb.min.y, radio };
  })();
  return cache;
}

/**
 * Recipiente sintético V-101 leído de su IFC. Se dibuja con líneas ocultas,
 * crece de abajo arriba y gira despacio. La cota roja mide su altura real en el modelo.
 */
export function Torre({ ancho = 820, alto = 880, onListo }) {
  const host = useRef(null);
  const [info, setInfo] = useState(null);
  const [cota, setCota] = useState(null);

  useEffect(() => {
    let vivo = true;
    let raf = 0;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: EXPORT });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(ancho, alto);
    renderer.localClippingEnabled = true;
    host.current.appendChild(renderer.domElement);

    leerTorre().then(({ geo, aristas, piezas, alto: h, radio }) => {
      if (!vivo) return;
      const scene = new THREE.Scene();
      const corte = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
      const caras = new THREE.Mesh(
        geo,
        new THREE.MeshBasicMaterial({
          color: 0x0f1317, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, clippingPlanes: [corte],
        }),
      );
      const lineas = new THREE.LineSegments(
        aristas,
        new THREE.LineBasicMaterial({ color: 0xe8ebee, transparent: true, opacity: 0.82, clippingPlanes: [corte] }),
      );
      const modelo = new THREE.Group();
      modelo.add(caras, lineas);
      scene.add(modelo);

      const r = geo.boundingSphere.radius;
      const fov = 18;
      const camera = new THREE.PerspectiveCamera(fov, ancho / alto, r * 0.2, r * 20);
      // Encaje por altura: la torre es mucho más alta que ancha.
      const dist = (h * 0.5 * 1.12) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) + radio;
      const elev = THREE.MathUtils.degToRad(12);
      const centro = new THREE.Vector3(0, h * 0.5, 0);
      camera.position.set(0, centro.y + Math.sin(elev) * dist, Math.cos(elev) * dist);
      camera.lookAt(centro);
      camera.updateMatrixWorld();

      // Cota de altura, fija en el mundo a la derecha del modelo: no gira con él.
      const x = radio * 1.25;
      const proj = (y) => {
        const v = new THREE.Vector3(x, y, 0).project(camera);
        return { x: (v.x + 1) * 0.5 * ancho, y: (1 - v.y) * 0.5 * alto };
      };
      setCota({ arriba: proj(h), abajo: proj(0) });
      setInfo({ alto: h, piezas });

      const t0 = performance.now();
      const crece = 2600;
      const frame = (t) => {
        const k = EXPORT ? 1 : Math.min(1, (t - t0) / crece);
        const e = 1 - Math.pow(1 - k, 3);
        corte.constant = -0.02 * h + e * h * 1.04;
        modelo.rotation.y = EXPORT ? -0.6 : -0.9 + (t - t0) * 0.00007;
        renderer.render(scene, camera);
        if (EXPORT) {
          onListo?.();
          return;
        }
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);
    });

    return () => {
      vivo = false;
      cancelAnimationFrame(raf);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [ancho, alto, onListo]);

  const metros = info
    ? new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(info.alto)
    : null;

  return (
    <div style={{ position: "relative", width: ancho, height: alto }}>
      <div ref={host} style={{ position: "absolute", inset: 0 }} />
      {cota && (
        <svg width={ancho} height={alto} style={{ position: "absolute", inset: 0, overflow: "visible" }} aria-hidden>
          <g className="cota-torre" style={{ color: "var(--cota)" }}>
            <line x1={cota.abajo.x - 22} y1={cota.abajo.y} x2={cota.abajo.x + 22} y2={cota.abajo.y} stroke="currentColor" strokeWidth={1.5} />
            <line x1={cota.arriba.x - 22} y1={cota.arriba.y} x2={cota.arriba.x + 22} y2={cota.arriba.y} stroke="currentColor" strokeWidth={1.5} />
            <line x1={cota.abajo.x} y1={cota.abajo.y - 16} x2={cota.arriba.x} y2={cota.arriba.y + 16} stroke="currentColor" strokeWidth={2} />
            <path d={`M${cota.arriba.x} ${cota.arriba.y} l-5.5 16 h11 Z`} fill="currentColor" />
            <path d={`M${cota.abajo.x} ${cota.abajo.y} l-5.5 -16 h11 Z`} fill="currentColor" />
            <text
              x={0} y={0}
              transform={`translate(${cota.abajo.x - 16} ${(cota.abajo.y + cota.arriba.y) / 2}) rotate(-90)`}
              textAnchor="middle" fill="currentColor"
              style={{ font: "560 34px var(--font)", fontStretch: "125%", fontVariantNumeric: "tabular-nums" }}
            >
              {metros} m
            </text>
          </g>
        </svg>
      )}
    </div>
  );
}

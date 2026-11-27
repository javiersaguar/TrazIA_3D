import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { IfcAPI } from "web-ifc";
import wasmUrl from "web-ifc/web-ifc.wasm?url";
import { EXPORT } from "./modo.js";

/*
  Visor del IFC para la presentación. Lee el archivo con web-ifc y agrupa la geometría por el
  GUID de cada pieza, de modo que dos revisiones se comparan pieza a pieza: lo que solo está en B
  es nuevo, lo que cambia de caja está modificado y el resto es igual.
*/

let api;
async function ifcApi() {
  if (!api) {
    api = (async () => {
      const a = new IfcAPI();
      await a.Init((path) => (path.endsWith(".wasm") ? wasmUrl : path), true);
      return a;
    })();
  }
  return api;
}

const cache = new Map();
export function leerIfc(url) {
  if (!cache.has(url)) {
    cache.set(url, (async () => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Sin IFC en ${url}`);
      const buf = new Uint8Array(await res.arrayBuffer());
      if (new TextDecoder().decode(buf.slice(0, 13)) !== "ISO-10303-21;") throw new Error(`No es un IFC: ${url}`);
      const a = await ifcApi();
      const id = a.OpenModel(buf);
      const piezas = new Map();
      const m = new THREE.Matrix4();
      const p = new THREE.Vector3();
      a.StreamAllMeshes(id, (mesh) => {
        let guid = String(mesh.expressID);
        let nombre = "";
        try {
          const linea = a.GetLine(id, mesh.expressID);
          guid = linea?.GlobalId?.value ?? guid;
          nombre = linea?.Name?.value ?? "";
        } catch {
          /* pieza sin atributos legibles: se agrupa por su id */
        }
        const pieza = piezas.get(guid) ?? { guid, nombre, pos: [], idx: [] };
        for (let i = 0; i < mesh.geometries.size(); i++) {
          const placed = mesh.geometries.get(i);
          const g = a.GetGeometry(id, placed.geometryExpressID);
          const v = a.GetVertexArray(g.GetVertexData(), g.GetVertexDataSize());
          const ix = a.GetIndexArray(g.GetIndexData(), g.GetIndexDataSize());
          m.fromArray(placed.flatTransformation);
          const base = pieza.pos.length / 3;
          for (let j = 0; j < v.length; j += 6) {
            p.set(v[j], v[j + 1], v[j + 2]).applyMatrix4(m);
            pieza.pos.push(p.x, p.y, p.z);
          }
          for (let j = 0; j < ix.length; j++) pieza.idx.push(ix[j] + base);
          g.delete();
        }
        piezas.set(guid, pieza);
      });
      a.CloseModel(id);
      const salida = [];
      for (const pz of piezas.values()) {
        if (!pz.idx.length) continue;
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.Float32BufferAttribute(pz.pos, 3));
        geo.setIndex(pz.idx);
        geo.computeVertexNormals();
        geo.computeBoundingBox();
        salida.push({ guid: pz.guid, nombre: pz.nombre, geo });
      }
      return salida;
    })());
  }
  return cache.get(url);
}

const COLOR = { base: 0xdde5eb, borde: 0x5f7997, nuevo: 0x74d1e0, cambiado: 0x469ba9 };

function caja(piezas) {
  const b = new THREE.Box3();
  for (const p of piezas) b.union(p.geo.boundingBox);
  return b;
}


// Piezas opacas: la transición A → B se hace con un plano de corte, no con transparencias,
// que se ordenan mal y hacen parpadear el modelo.
function grupo(piezas, color = () => COLOR.base, corte = []) {
  const g = new THREE.Group();
  for (const p of piezas) {
    const c = color(p);
    const mat = new THREE.MeshLambertMaterial({ color: c, side: THREE.DoubleSide, clippingPlanes: corte, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(p.geo, mat);
    const lineas = new THREE.LineSegments(
      new THREE.EdgesGeometry(p.geo, 35),
      new THREE.LineBasicMaterial({ color: c === COLOR.base ? COLOR.borde : c, transparent: true, opacity: c === COLOR.base ? 0.45 : 0.9, clippingPlanes: corte }),
    );
    const pieza = new THREE.Group();
    pieza.add(mesh, lineas);
    pieza.userData = { guid: p.guid, color: c };
    g.add(pieza);
  }
  return g;
}

const suave = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

/**
 * Modelo 3D en directo.
 * - modo "gira": una revisión girando despacio.
 * - modo "cambio": alterna A y B; en B, lo nuevo en aguamarina y lo modificado en turquesa.
 */
export function Visor({ urls, respaldo, modo = "gira", ancho, alto, elevacion = 18, zoom = 1, modificados = [], onEstado, onListo }) {
  const host = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let vivo = true;
    let raf = 0;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: EXPORT });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(ancho, alto);
    renderer.localClippingEnabled = true;
    host.current.appendChild(renderer.domElement);

    const cargar = async () => {
      try {
        return { piezas: await Promise.all(urls.map(leerIfc)), respaldo: false };
      } catch (e) {
        if (!respaldo) throw e;
        return { piezas: await Promise.all(respaldo.map(leerIfc)), respaldo: true };
      }
    };

    cargar().then(({ piezas, respaldo: usado }) => {
      if (!vivo) return;
      onEstado?.({ respaldo: usado });
      const scene = new THREE.Scene();
      scene.add(new THREE.HemisphereLight(0xffffff, 0xc9d4dc, 2.2));
      const sol = new THREE.DirectionalLight(0xffffff, 1.6);
      sol.position.set(3, 5, 4);
      scene.add(sol);

      const [A, B] = piezas;
      const todas = B ? [...A, ...B] : A;
      const bb = caja(todas);
      const centro = new THREE.Vector3();
      const tam = new THREE.Vector3();
      bb.getCenter(centro);
      bb.getSize(tam);

      const raiz = new THREE.Group();
      raiz.position.set(-centro.x, -centro.y, -centro.z);
      const pivote = new THREE.Group();
      pivote.add(raiz);
      scene.add(pivote);

      let gA;
      let gB;
      // Corte horizontal: por debajo se ve B y por encima A. y en coordenadas del mundo.
      const yMin = bb.min.y - centro.y;
      const yMax = bb.max.y - centro.y;
      const sobre = new THREE.Plane(new THREE.Vector3(0, 1, 0), -yMin);
      const bajo = new THREE.Plane(new THREE.Vector3(0, -1, 0), yMin);
      let anillo;
      if (modo === "cambio" && B) {
        const porGuid = new Map(A.map((p) => [p.guid, p]));
        gA = grupo(A, undefined, [sobre]);
        // Nuevo: el GUID no existía en A. Modificado: las piezas que señala el delta de la revisión.
        const marcadas = new Set(modificados);
        gB = grupo(B, (p) => {
          if (!porGuid.has(p.guid)) return COLOR.nuevo;
          return marcadas.has(p.nombre) ? COLOR.cambiado : COLOR.base;
        }, [bajo]);
        raiz.add(gA, gB);
        const radio = Math.max(tam.x, tam.z) * 0.62;
        const puntos = Array.from({ length: 97 }, (_, i) => {
          const a = (i / 96) * Math.PI * 2;
          return new THREE.Vector3(Math.cos(a) * radio, 0, Math.sin(a) * radio);
        });
        anillo = new THREE.Line(new THREE.BufferGeometry().setFromPoints(puntos),
          new THREE.LineBasicMaterial({ color: COLOR.nuevo, transparent: true, opacity: 0 }));
        scene.add(anillo);
      } else {
        gA = grupo(A);
        raiz.add(gA);
      }

      const r = tam.length() / 2;
      const fov = 24;
      const camera = new THREE.PerspectiveCamera(fov, ancho / alto, r / 50, r * 50);
      const ajuste = Math.max(r, (r * ancho) / alto * 0.62);
      const dist = (ajuste * 1.08) / Math.sin(THREE.MathUtils.degToRad(fov / 2)) / zoom;
      const el = THREE.MathUtils.degToRad(elevacion);
      camera.position.set(0, Math.sin(el) * dist, Math.cos(el) * dist);
      camera.lookAt(0, 0, 0);

      const t0 = performance.now();
      // A 3 s, barrido hacia B 1,8 s, B 4 s, barrido de vuelta 1,6 s.
      const tramos = [3000, 1800, 4000, 1600];
      const ciclo = tramos.reduce((a, b) => a + b, 0);
      const corteEn = (h) => {
        sobre.constant = -h;
        bajo.constant = h;
        if (anillo) anillo.position.y = h;
      };
      const frame = (t) => {
        const dt = t - t0;
        pivote.rotation.y = EXPORT ? -0.75 : -0.9 + dt * 0.00012;
        if (gB) {
          // kB: parte del equipo que ya es B, de abajo arriba.
          let kB;
          let barriendo = false;
          if (EXPORT) kB = 1;
          else {
            const c = dt % ciclo;
            const [a, sube, b] = tramos;
            if (c < a) kB = 0;
            else if (c < a + sube) { kB = suave((c - a) / sube); barriendo = true; }
            else if (c < a + sube + b) kB = 1;
            else { kB = 1 - suave((c - a - sube - b) / tramos[3]); barriendo = true; }
          }
          const margen = (yMax - yMin) * 0.02;
          corteEn(yMin - margen + kB * (yMax - yMin + 2 * margen));
          if (anillo) anillo.material.opacity = barriendo ? 0.95 : 0;
          const estado = kB > 0.5 ? "B" : "A";
          if (frame.estado !== estado) {
            frame.estado = estado;
            onEstado?.({ respaldo: usado, revision: estado });
          }
        }
        renderer.render(scene, camera);
        if (EXPORT) {
          onListo?.();
          return;
        }
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);
    }).catch((e) => {
      if (vivo) {
        setError(e.message);
        onListo?.();
      }
    });

    return () => {
      vivo = false;
      cancelAnimationFrame(raf);
      renderer.dispose();
      renderer.domElement.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urls.join("|"), modo, ancho, alto]);

  return (
    <div style={{ position: "relative", width: ancho, height: alto }}>
      <div ref={host} style={{ position: "absolute", inset: 0 }} />
      {error && (
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--pizarra)", fontSize: 24 }}>
          Modelo no disponible en este equipo
        </div>
      )}
    </div>
  );
}

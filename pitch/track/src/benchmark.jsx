import { motion } from "motion/react";
import data from "./model-benchmark.json";
import { EXPORT, entra } from "./modo.js";

/*
  Comparación de modelos del enrutador, con los datos de model-benchmark.json
  (medición sintética en Azure del 26/11). Dos dispersiones por
  tarea: acierto frente a coste por tarea (escala logarítmica) y frente a tiempo. La línea discontinua
  une la frontera: los modelos que nadie supera en acierto sin gastar más.
*/

const fmt = (v, d = 1) => new Intl.NumberFormat("es-ES", { maximumFractionDigits: d }).format(v);
const acierto = (p) => (p.correct / p.fields) * 100;

const tareas = {
  vision: { nombre: "Lectura compleja", unidad: "recortes" },
  texto: { nombre: "Normalización corta", unidad: "fragmentos" },
};
const metricas = {
  usd: { titulo: "Acierto y coste", eje: "USD por tarea, escala logarítmica", tick: (v) => fmt(v, 5) },
  seconds: { titulo: "Acierto y tiempo", eje: "Segundos por tarea", tick: (v) => fmt(v, 2) },
};

const W = 820;
const H = 378;
const P = { izq: 74, der: W - 30, arr: 30, abj: H - 74 };

/** Eje vertical de cada tarea: de un múltiplo de 5 bajo el peor acierto hasta 100. */
function ejeY(puntos) {
  const peor = Math.min(...puntos.filter((p) => p.fields).map(acierto));
  const suelo = Math.max(0, Math.min(95, Math.floor((peor - 0.5) / 5) * 5));
  const paso = 100 - suelo <= 5 ? 1 : 100 - suelo <= 10 ? 2 : 5;
  const ticks = [];
  for (let t = 100; t >= suelo; t -= paso) ticks.push(t);
  return { suelo, ticks };
}

/** Eje horizontal: logarítmico para el coste; para el tiempo, solo el tramo donde caen los puntos. */
function ejeX(puntos, metrica) {
  const v = puntos.flatMap((p) => (p[metrica] > 0 ? [p[metrica]] : []));
  if (metrica === "usd") {
    const a = Math.floor(Math.log10(Math.min(...v)));
    const b = Math.max(a + 1, Math.ceil(Math.log10(Math.max(...v))));
    return { ticks: Array.from({ length: b - a + 1 }, (_, i) => 10 ** (a + i)), f: (x) => (Math.log10(x) - a) / (b - a) };
  }
  const min = Math.min(...v);
  const max = Math.max(...v);
  const paso = [0.25, 0.5, 1, 2, 5, 10].find((s) => Math.ceil(max / s) - Math.floor(min / s) <= 5) ?? 10;
  let lo = Math.floor(min / paso) * paso;
  let hi = Math.ceil(max / paso) * paso;
  if (min - lo < paso * 0.3) lo -= paso;
  if (hi - max < paso * 0.3) hi += paso;
  lo = Math.max(0, lo);
  const n = Math.round((hi - lo) / paso);
  return { ticks: Array.from({ length: n + 1 }, (_, i) => lo + i * paso), f: (x) => (x - lo) / (hi - lo) };
}

const LINEA = 25;
const ancho = (nombre) => 10.6 * nombre.length + 8;

/*
  Rótulos sin solapes: los puntos que caen casi en el mismo sitio se rotulan juntos, un nombre por
  línea. Cada rótulo prueba a la derecha, a la izquierda, arriba y abajo de su punto, y después
  más lejos con una línea guía, hasta encontrar un hueco que no pise otro rótulo ni otro punto.
*/
function rotulos(puntos) {
  const grupos = [];
  for (const p of puntos) {
    const g = grupos.find((q) => Math.hypot(q.x - p.x, q.y - p.y) < 16);
    if (g) g.miembros.push(p);
    else grupos.push({ x: p.x, y: p.y, miembros: [p] });
  }
  const cajas = [];
  const choca = (c) =>
    c.x < P.izq + 4 || c.x + c.w > W + 40 || c.y < 0 || c.y + c.h > P.abj + 4 || (c.x < P.izq + 110 && c.y < 18) ||
    cajas.some((o) => c.x < o.x + o.w + 6 && o.x < c.x + c.w + 6 && c.y < o.y + o.h + 2 && o.y < c.y + c.h + 2) ||
    puntos.some((p) => p.x > c.x - 10 && p.x < c.x + c.w + 10 && p.y > c.y - 10 && p.y < c.y + c.h + 10);
  return grupos
    .sort((a, b) => a.y - b.y || a.x - b.x)
    .map((g) => {
      const w = Math.max(...g.miembros.map((m) => ancho(m.name)));
      const h = g.miembros.length * LINEA;
      const opciones = [];
      for (const d of [0, 34, 68, 102]) {
        opciones.push({ x: g.x + 16 + d, y: g.y - h / 2 });
        opciones.push({ x: g.x - 16 - w - d, y: g.y - h / 2 });
        opciones.push({ x: g.x - w / 2, y: g.y - 16 - h - d });
        opciones.push({ x: g.x - w / 2, y: g.y + 16 + d });
        opciones.push({ x: g.x + 16 + d, y: g.y + 12 + d / 2 });
        opciones.push({ x: g.x + 16 + d, y: g.y - h - 12 - d / 2 });
      }
      const c = { w, h, ...(opciones.find((o) => !choca({ ...o, w, h })) ?? opciones[0]) };
      cajas.push(c);
      const cx = Math.max(c.x, Math.min(c.x + c.w, g.x));
      const cy = Math.max(c.y, Math.min(c.y + c.h, g.y));
      return { ...g, caja: c, guia: Math.hypot(cx - g.x, cy - g.y) > 22 ? { x: cx, y: cy } : null };
    });
}

function Dispersion({ tarea, metrica }) {
  const m = metricas[metrica];
  const validos = tarea.points.filter((p) => p[metrica] !== null && p.fields > 0);
  const { ticks, f } = ejeX(validos, metrica);
  const { suelo, ticks: ticksY } = ejeY(tarea.points);
  const x = (v) => P.izq + f(v) * (P.der - P.izq);
  const y = (v) => P.abj - ((v - suelo) / (100 - suelo)) * (P.abj - P.arr);
  const puntos = validos.map((p) => ({ ...p, x: x(p[metrica]), y: y(acierto(p)), elegido: tarea.selected === p.id }));
  const grupos = rotulos(puntos);
  let mejor = -1;
  const frontera = [...puntos].sort((a, b) => a.x - b.x || a.y - b.y).filter((p) => {
    const q = acierto(p);
    if (q <= mejor) return false;
    mejor = q;
    return true;
  });
  return (
    <figure style={{ margin: 0 }}>
      <figcaption style={{ fontSize: 32, fontWeight: 300, marginBottom: 10 }}>{m.titulo}</figcaption>
      <svg width={W} height={H} style={{ overflow: "visible", display: "block" }} role="img"
        aria-label={`${m.titulo}. ${puntos.map((p) => `${p.name}: ${fmt(acierto(p))} %, ${m.tick(p[metrica])}`).join(". ")}`}>
        <text x={P.izq} y={12} fill="var(--pizarra)" style={{ font: "400 19px var(--font)" }}>Acierto, %</text>
        {ticksY.map((t) => (
          <g key={`y${t}`}>
            <line x1={P.izq} x2={P.der} y1={y(t)} y2={y(t)} stroke="var(--linea)" />
            <text x={P.izq - 12} y={y(t) + 6} textAnchor="end" fill="var(--pizarra)" style={{ font: "300 18px var(--font)" }}>{t}</text>
          </g>
        ))}
        {ticks.map((t) => (
          <g key={`x${t}`}>
            <line x1={x(t)} x2={x(t)} y1={P.arr} y2={P.abj} stroke="var(--linea)" />
            <text x={x(t)} y={P.abj + 28} textAnchor="middle" fill="var(--pizarra)" style={{ font: "300 18px var(--font)" }}>{m.tick(t)}</text>
          </g>
        ))}
        <path d={`M${P.izq} ${P.arr}V${P.abj}H${P.der}`} fill="none" stroke="var(--linea-2)" strokeWidth={1.5} />
        <text x={(P.izq + P.der) / 2} y={H - 4} textAnchor="middle" fill="var(--pizarra)" style={{ font: "400 19px var(--font)" }}>{m.eje}</text>
        {frontera.length > 1 && (
          <polyline points={frontera.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke="var(--turquesa)" strokeOpacity={0.7} strokeWidth={2} strokeDasharray="6 7" />
        )}
        {grupos.map((g) => g.guia && <line key={`g${g.miembros[0].id}`} x1={g.x} y1={g.y} x2={g.guia.x} y2={g.guia.y} stroke="var(--pizarra-2)" strokeOpacity={0.6} />)}
        {puntos.map((p, i) => (
          <motion.g key={p.id} {...(EXPORT ? { initial: false } : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { delay: 0.5 + i * 0.08, duration: 0.35 } })}
            transform={`translate(${p.x} ${p.y})`}>
            {p.elegido && <circle r={17} fill="var(--agua)" fillOpacity={0.25} stroke="var(--turquesa)" strokeOpacity={0.6} />}
            <circle r={p.elegido ? 8 : 6.5} fill={p.elegido ? "var(--turquesa)" : "#9aaabb"} stroke="#fff" strokeWidth={2} />
          </motion.g>
        ))}
        {grupos.map((g) => g.miembros.map((p, k) => (
          <text key={`t${p.id}`} x={g.caja.x} y={g.caja.y + (k + 1) * LINEA - 6}
            fill={p.elegido ? "var(--turquesa)" : "var(--tinta)"} stroke="#fff" strokeWidth={4} paintOrder="stroke"
            style={{ font: `${p.elegido ? 500 : 400} 20px var(--font)` }}>{p.name}</text>
        )))}
      </svg>
    </figure>
  );
}

const linea = (p) => `${p.correct} de ${p.fields} aciertos, ${fmt(p.usd, 5)} USD y ${fmt(p.seconds, 2)} s por tarea`;

export function Benchmark({ id = "vision" }) {
  const tarea = data.tasks[id];
  const t = tareas[id];
  const elegido = tarea.points.find((p) => p.id === tarea.selected);
  const opus = tarea.points.find((p) => p.id === "claude-opus-5-5");
  return (
    <>
      <motion.div {...entra(0.3)} style={{ position: "absolute", top: 118, left: 0, right: 0, display: "flex", alignItems: "center", gap: 36 }}>
        <span style={{ font: "400 30px var(--font)", paddingBottom: 4, borderBottom: "3px solid var(--agua)" }}>{t.nombre}</span>
        <span className="sintetico" style={{ marginLeft: "auto" }}>
          {tarea.points[0].calls} {t.unidad} sintéticos, {tarea.points[0].fields} valores evaluables
        </span>
      </motion.div>
      <div style={{ position: "absolute", top: 196, left: 0, right: 0, display: "flex", justifyContent: "space-between" }}>
        <Dispersion tarea={tarea} metrica="usd" />
        <Dispersion tarea={tarea} metrica="seconds" />
      </div>
      <motion.div {...entra(1.2)} style={{ position: "absolute", left: 0, right: 0, bottom: -10, display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderTop: "1px solid var(--linea-2)", paddingTop: 18 }}>
        <div>
          <div style={{ fontSize: 34, fontWeight: 400, color: "var(--turquesa)" }}>{elegido.name}, la elección del equipo</div>
          <div className="texto" style={{ fontSize: 24, marginTop: 6 }}>{linea(elegido)}</div>
          {opus && <div className="texto" style={{ fontSize: 22, marginTop: 4, color: "var(--pizarra-2)" }}>Opus 5.5: {linea(opus)}</div>}
        </div>
        {opus && elegido.usd < opus.usd && (
          <div style={{ textAlign: "right" }}>
            <div className="cifra turquesa" style={{ fontSize: 76 }}>{fmt((1 - elegido.usd / opus.usd) * 100, 0)} % menos</div>
            <div className="texto" style={{ fontSize: 22, marginTop: 6 }}>de coste por tarea que Opus 5.5, a precio de lista</div>
          </div>
        )}
      </motion.div>
    </>
  );
}

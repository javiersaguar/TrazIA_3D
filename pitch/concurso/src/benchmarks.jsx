import { motion } from "motion/react";
import { Cota, Cuenta } from "./cota.jsx";
import { EXPORT, entra } from "./modo.js";

/*
  Hoja de benchmarks: tres tarjetas con una sola idea cada una. Arriba, la cifra dibujada como
  cota; debajo, la gráfica que la demuestra y la etiqueta de qué datos son. Nuestra marca va en
  rojo de cota y el resto en gris de segundo plano.
*/

const GRIS = "#5c6670";
const ease = [0.2, 0.8, 0.2, 1];
const aparece = (t) => (EXPORT ? { initial: false } : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { delay: t, duration: 0.35 } });
const crece = (t) => (EXPORT ? { initial: false } : { initial: { scaleX: 0 }, animate: { scaleX: 1 }, transition: { delay: t, duration: 0.8, ease } });

function barra(x0, x1, y, alto, r = 4) {
  const w = Math.max(0, x1 - x0);
  if (w <= 0) return "";
  const rr = Math.min(r, w, alto / 2);
  return `M${x0} ${y} H${x1 - rr} Q${x1} ${y} ${x1} ${y + rr} V${y + alto - rr} Q${x1} ${y + alto} ${x1 - rr} ${y + alto} H${x0} Z`;
}

/* Cota inventada: barras de valores sin respaldo en el plano. Un rango se pinta con el tramo
   seguro macizo y el resto rayado. Nuestro cero se marca con un punto rojo sobre el eje. */
function Inventadas({ filas, max, ancho, delay }) {
  const etq = 0;
  const fila = 82;
  const grueso = 22;
  const plot = ancho - 70;
  const x = (v) => etq + (v / max) * plot;
  return (
    <svg width={ancho} height={filas.length * fila + 30} style={{ display: "block", overflow: "visible" }} role="img"
      aria-label={filas.map((f) => `${f.etiqueta}: ${f.texto}`).join(". ")}>
      <defs>
        <pattern id="rayado" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill={GRIS} fillOpacity={0.35} />
          <line x1="0" y1="0" x2="0" y2="7" stroke={GRIS} strokeWidth="3" />
        </pattern>
      </defs>
      {[0, 5, 10].map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={0} y2={filas.length * fila} stroke="var(--hair)" />
          <text x={x(t)} y={filas.length * fila + 24} textAnchor="middle" fill="var(--aux)" style={{ font: "400 17px var(--font)" }}>{t} %</text>
        </g>
      ))}
      {filas.map((f, i) => {
        const y = i * fila + 34;
        const t = delay + i * 0.2;
        const hasta = f.rango ? f.rango[1] : f.valor;
        const desde = f.rango ? f.rango[0] : f.valor;
        return (
          <g key={f.etiqueta}>
            <text x={etq} y={y - 10} fill={f.nuestro ? "var(--trazo)" : "var(--trazo-2)"} style={{ font: `${f.nuestro ? 640 : 400} 21px var(--font)` }}>
              {f.etiqueta}
            </text>
            {f.nuestro ? (
              <motion.g {...aparece(t + 0.6)}>
                <circle cx={x(0) + 9} cy={y + grueso / 2} r={9} fill="var(--cota)" />
                <text x={x(0) + 30} y={y + grueso / 2 + 8} fill="var(--cota)" style={{ font: "640 23px var(--font)", fontStretch: "108%" }}>{f.texto}</text>
              </motion.g>
            ) : (
              <>
                <motion.g style={{ transformBox: "fill-box", originX: 0 }} {...crece(t)}>
                  <path d={barra(x(0), x(hasta), y, grueso)} fill={f.rango ? "url(#rayado)" : GRIS} />
                  <path d={barra(x(0), x(desde), y, grueso, f.rango ? 0 : 4)} fill={GRIS} />
                </motion.g>
                <motion.text {...aparece(t + 0.7)} x={x(hasta) + 12} y={y + grueso / 2 + 8} fill="var(--trazo-2)"
                  style={{ font: "420 22px var(--font)", fontStretch: "108%" }}>{f.texto}</motion.text>
              </>
            )}
          </g>
        );
      })}
      <line x1={x(0)} x2={x(0)} y1={0} y2={filas.length * fila} stroke="var(--hair-2)" />
    </svg>
  );
}

/* El modelo justo: por tarea, coste por tarea del modelo más grande frente al que elegimos, en
   escala lineal con el grande a todo el ancho. En la punta, el acierto y, en la nuestra, el ahorro. */
function Enrutador({ tareas, ancho, delay }) {
  const grueso = 22;
  const etq = 124;
  const plot = ancho - etq - 150;
  const fila = 40;
  return (
    <div style={{ display: "grid", gap: 26 }}>
      {tareas.map((t, i) => {
        const d = delay + i * 0.5;
        return (
          <div key={t.tarea}>
            <div style={{ fontSize: 21, color: "var(--trazo-2)", marginBottom: 12 }}>{t.tarea}</div>
            <svg width={ancho} height={2 * fila} style={{ display: "block", overflow: "visible" }} role="img"
              aria-label={`${t.tarea}: ${t.grande.nombre} ${t.grande.texto}, ${t.elegido.nombre} ${t.elegido.texto}, ${t.ahorro}`}>
              {[t.grande, t.elegido].map((m, k) => {
                const y = k * fila + (fila - grueso) / 2;
                const fin = etq + Math.max(5, (m.usd / t.grande.usd) * plot);
                const nuestro = k === 1;
                return (
                  <g key={m.nombre}>
                    <text x={0} y={y + grueso / 2 + 7} fill={nuestro ? "var(--trazo)" : "var(--trazo-2)"}
                      style={{ font: `${nuestro ? 640 : 400} 20px var(--font)` }}>{m.nombre}</text>
                    <motion.path d={barra(etq, fin, y, grueso)} fill={nuestro ? "var(--cota)" : GRIS}
                      style={{ transformBox: "fill-box", originX: 0 }} {...crece(d + k * 0.25)} />
                    <motion.text {...aparece(d + k * 0.25 + 0.6)} x={fin + 12} y={y + grueso / 2 + 7}
                      fill="var(--aux)" style={{ font: "400 19px var(--font)" }}>
                      {m.texto}
                      {nuestro && <tspan fill="var(--cota)" style={{ fontWeight: 640, fontSize: 23 }}>{"  "}{t.ahorro}</tspan>}
                    </motion.text>
                  </g>
                );
              })}
              <line x1={etq} x2={etq} y1={0} y2={2 * fila} stroke="var(--hair-2)" />
            </svg>
          </div>
        );
      })}
    </div>
  );
}

/* Aprobación automática con planos reales: una barra con todos los datos juzgables. En rojo lo que
   se aprueba solo (macizo si coincide con el oro, rayado si no) y en gris lo que va a una persona. */
function Automatico({ r, ancho, delay }) {
  const alto = 52;
  const y = 92;
  const hueco = 6;
  const k = (ancho - hueco) / r.total;
  const xBien = r.bien * k;
  const xSolos = r.solos * k;
  const xPersona = xSolos + hueco;
  const tramo = (x0, x1, t, fill) => (
    <motion.rect x={x0} y={y} width={Math.max(0, x1 - x0)} height={alto} fill={fill}
      style={{ transformBox: "fill-box", originX: 0 }} {...crece(t)} />
  );
  return (
    <svg width={ancho} height={250} style={{ display: "block", overflow: "visible" }} role="img"
      aria-label={`${r.total} datos: ${r.solos} se aprueban solos, ${r.bien} correctos y ${r.solos - r.bien} no; ${r.total - r.solos} van a una persona`}>
      <defs>
        <pattern id="rayado-rojo" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill="var(--cota)" fillOpacity={0.3} />
          <line x1="0" y1="0" x2="0" y2="7" stroke="var(--cota)" strokeWidth="3" />
        </pattern>
      </defs>
      <text x={0} y={22} fill="var(--trazo-2)" style={{ font: "400 21px var(--font)" }}>{r.total} datos de planos reales</text>
      {/* Llave sobre lo que se aprueba solo */}
      <motion.g {...aparece(delay + 0.9)}>
        <path d={`M1 ${y - 12} V${y - 22} H${xSolos - 1} V${y - 12}`} fill="none" stroke="var(--cota)" strokeWidth={1.5} />
        <text x={0} y={y - 34} fill="var(--trazo)" style={{ font: "640 21px var(--font)" }}>
          {r.solos} se aprueban solos
        </text>
      </motion.g>
      {tramo(0, xBien, delay, "var(--cota)")}
      {tramo(xBien, xSolos, delay + 0.5, "url(#rayado-rojo)")}
      {tramo(xPersona, ancho, delay + 0.7, GRIS)}
      <motion.g {...aparece(delay + 1.2)}>
        <text x={6} y={y + alto + 32} fill="var(--trazo)" style={{ font: "560 20px var(--font)" }}>
          {r.bien} bien
          <tspan fill="var(--aux)" style={{ fontWeight: 400 }}>{` · ${r.solos - r.bien} mal`}</tspan>
        </text>
        <line x1={xSolos - 3} x2={xSolos - 3} y1={y + alto + 4} y2={y + alto + 14} stroke="var(--cota)" strokeWidth={1.5} />
        <text x={ancho} y={y + alto + 32} textAnchor="end" fill="var(--trazo)" style={{ font: "560 20px var(--font)" }}>
          {r.total - r.solos} a una persona
        </text>
        <text x={ancho} y={y + alto + 58} textAnchor="end" fill="var(--aux)" style={{ font: "400 18px var(--font)" }}>lo dudoso, primero</text>
      </motion.g>
    </svg>
  );
}

function Tarjeta({ i, k, ancho, children }) {
  const t = 0.5 + i * 0.6;
  return (
    <div style={{ width: ancho, display: "flex", flexDirection: "column" }}>
      <Cota ancho={ancho} alto={150} delay={t}>
        <span className="cifra" style={{ fontSize: 104, whiteSpace: "nowrap" }}>
          {k.prefijo}
          <Cuenta valor={k.valor} desde={k.desde ?? 0} decimales={k.decimales ?? 0} delay={t + 0.4} />
          <span style={{ fontSize: 54, fontStretch: "100%", letterSpacing: 0 }}>{k.sufijo}</span>
        </span>
      </Cota>
      <motion.div {...entra(t + 0.5)} style={{ fontSize: 29, fontWeight: 620, fontStretch: "106%", lineHeight: 1.18, marginTop: 22, minHeight: 70, letterSpacing: "-0.005em" }}>
        {k.titulo}
      </motion.div>
      <motion.div {...entra(t + 0.8)} style={{ marginTop: 22, flex: 1 }}>{children}</motion.div>
      <motion.div {...entra(t + 1.0)} style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10, fontSize: 17, color: "var(--aux)", fontStretch: "92%" }}>
        <i style={{ width: 8, height: 8, border: "1.5px solid var(--aux)", borderRadius: "50%", flex: "none" }} />
        {k.datos}
      </motion.div>
    </div>
  );
}

export function Benchmarks({ hoja }) {
  const [a, b, c] = hoja.tarjetas;
  const ancho = 512;
  return (
    <>
      <h1 className="titular estira">{hoja.titular}</h1>
      <div style={{ position: "absolute", top: 170, left: 0, right: 0, bottom: 20, display: "flex", justifyContent: "space-between" }}>
        <Tarjeta i={0} k={a} ancho={ancho}>
          <Inventadas filas={a.filas} max={12} ancho={ancho} delay={1.6} />
        </Tarjeta>
        <Tarjeta i={1} k={b} ancho={ancho}>
          <Automatico r={b.reparto} ancho={ancho} delay={2.2} />
        </Tarjeta>
        <Tarjeta i={2} k={c} ancho={ancho}>
          <Enrutador tareas={c.tareas} ancho={ancho} delay={2.8} />
        </Tarjeta>
      </div>
    </>
  );
}

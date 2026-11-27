import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { EXPORT } from "./modo.js";

/*
  Hoja «En qué nos diferenciamos»: cuatro escenas que se reproducen solas, una tras otra, con el
  lenguaje del plano (trazo blanco, cota roja, verde de lo comprobado). En exportación todo
  aparece en su estado final.
  - Cita: la longitud entre tangentes del 80V01 rev. 2, 5.700 mm, leída con su cita.
  - Cambio A → B: V-101 SINTÉTICO, N3 sube 200 mm y conserva su GUID; N4 es nueva.
  - Voz: la orden «Sube la boquilla N1 200 mm» sobre la elevación de N1 del 80V01, 2.580 mm.
  - Firma: si cambia un dato aprobado, la aprobación cae y vuelve a borrador.
*/

const ease = [0.2, 0.8, 0.2, 1];
const W = 400;
const H = 290;

/** Aparece en t segundos; en exportación ya está. */
const en = (t, desde = { opacity: 0 }) =>
  EXPORT ? { initial: false } : { initial: desde, animate: { opacity: 1, x: 0, y: 0, scale: 1 }, transition: { delay: t, duration: 0.5, ease } };
/** Traza una línea en t segundos. */
const traza = (t, d = 0.6) => (EXPORT ? { initial: false } : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { delay: t, duration: d, ease } });

/** Pasa a true en t segundos (en exportación, desde el principio). */
function useDesde(t) {
  const [ya, setYa] = useState(EXPORT);
  useEffect(() => {
    if (EXPORT) return undefined;
    const id = setTimeout(() => setYa(true), t * 1000);
    return () => clearTimeout(id);
  }, [t]);
  return ya;
}

/** Texto que se escribe solo, letra a letra, con cursor. */
function Teclea({ texto, desde, cps = 22 }) {
  const [n, setN] = useState(EXPORT ? texto.length : 0);
  useEffect(() => {
    if (EXPORT) return undefined;
    let id;
    const inicio = setTimeout(() => {
      id = setInterval(() => setN((k) => (k >= texto.length ? (clearInterval(id), k) : k + 1)), 1000 / cps);
    }, desde * 1000);
    return () => { clearTimeout(inicio); clearInterval(id); };
  }, [texto, desde, cps]);
  const escribiendo = !EXPORT && n > 0 && n < texto.length;
  return (
    <>
      {texto.slice(0, n)}
      {escribiendo && <span style={{ display: "inline-block", width: 2, height: "1em", background: "currentColor", marginLeft: 2, verticalAlign: "-0.12em" }} />}
    </>
  );
}

function Flecha({ x, y, dir }) {
  const f = 12 * dir;
  return <path d={`M${x} ${y} l${f} -4.5 v9 Z`} fill="var(--cota)" />;
}

function Chip({ x, y, children, color = "var(--boquilla)" }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle cx={0} cy={0} r={5} fill={color} />
      <text x={14} y={6} fill="var(--trazo)" style={{ font: "400 17px var(--font)" }}>{children}</text>
    </g>
  );
}

/* 1 · Cada cifra con su cita: se dibuja la cota y la lectura la enmarca y la cita. */
function Cita({ t }) {
  const y0 = 70;
  const tan = [96, 304];
  const yc = 170;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      {/* Recipiente horizontal: virola y fondos */}
      <path d={`M${tan[0]} ${y0} H${tan[1]} A36 40 0 0 1 ${tan[1]} ${y0 + 80} H${tan[0]} A36 40 0 0 1 ${tan[0]} ${y0} Z`}
        fill="none" stroke="var(--trazo-2)" strokeWidth={1.5} />
      {tan.map((x) => <line key={x} x1={x} x2={x} y1={y0 - 14} y2={yc + 8} stroke="var(--aux)" strokeWidth={1} strokeDasharray="6 4 1.5 4" />)}
      {/* Cota entre tangentes */}
      <motion.g {...en(t + 0.2)}>
        <line x1={tan[0] + 12} x2={tan[1] - 12} y1={yc} y2={yc} stroke="var(--cota)" strokeWidth={1.5} />
        <Flecha x={tan[0]} y={yc} dir={1} />
        <Flecha x={tan[1]} y={yc} dir={-1} />
        <text x={(tan[0] + tan[1]) / 2} y={yc - 10} textAnchor="middle" fill="var(--cota)" style={{ font: "500 19px var(--font)", fontStretch: "88%" }}>
          5700 (T.L. TO T.L.)
        </text>
      </motion.g>
      {/* La lectura enmarca el texto y lo cita */}
      <motion.rect x={110} y={yc - 36} width={180} height={36} rx={3} fill="rgba(65,214,154,0.12)" stroke="var(--boquilla)" strokeWidth={2}
        {...(EXPORT ? { initial: false } : { initial: { opacity: 0, scale: 1.5 }, animate: { opacity: 1, scale: 1 }, transition: { delay: t + 1.1, duration: 0.45, ease } })}
        style={{ transformBox: "fill-box", originX: 0.5, originY: 0.5 }} />
      <motion.g {...en(t + 1.6, { opacity: 0, y: 8 })}>
        <line x1={200} x2={200} y1={yc} y2={yc + 28} stroke="var(--boquilla)" strokeWidth={1.5} />
        <rect x={40} y={yc + 28} width={320} height={70} rx={6} fill="var(--film)" stroke="var(--hair-2)" />
        <text x={58} y={yc + 56} fill="var(--trazo)" style={{ font: "620 20px var(--font)" }}>Longitud entre tangentes</text>
        <text x={58} y={yc + 84} fill="var(--trazo-2)" style={{ font: "400 17px var(--font)" }}>5.700 mm · GA-80V01, página 1</text>
      </motion.g>
    </svg>
  );
}

/* 2 · Revisión B: N3 sube 200 mm y sigue siendo N3; N4 aparece como pieza nueva. */
function Cambio({ t }) {
  const sube = useDesde(t + 0.9);
  const x0 = 150;
  const x1 = 240;
  const yA = 186;
  const yB = 136;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      {/* Recipiente vertical con faldón */}
      <path d={`M${x0} 70 A45 26 0 0 1 ${x1} 70 V236 A45 26 0 0 1 ${x0} 236 Z`} fill="none" stroke="var(--trazo-2)" strokeWidth={1.5} />
      <path d={`M${x0 + 6} 252 L${x0 + 2} 278 M${x1 - 6} 252 L${x1 - 2} 278 M${x0 - 14} 278 H${x1 + 14}`} stroke="var(--trazo-2)" strokeWidth={1.5} fill="none" />
      {/* Posición en la revisión A */}
      <g opacity={0.5}>
        <rect x={x1} y={yA - 9} width={36} height={18} fill="none" stroke="var(--aux)" strokeDasharray="4 3" />
        <text x={x1 + 46} y={yA + 6} fill="var(--aux)" style={{ font: "400 16px var(--font)" }}>rev. A</text>
      </g>
      {/* N3, que sube en la revisión B */}
      <motion.g
        {...(EXPORT ? { initial: false, style: { y: yB - yA } } : { initial: { y: 0 }, animate: { y: sube ? yB - yA : 0 }, transition: { duration: 0.9, ease } })}>
        <rect x={x1} y={yA - 9} width={36} height={18} fill="var(--film-2)" stroke="var(--trazo)" strokeWidth={1.5} />
        <rect x={x1 + 36} y={yA - 15} width={6} height={30} fill="var(--trazo)" />
        <text x={x1 + 54} y={yA - 2} fill="var(--trazo)" style={{ font: "620 20px var(--font)" }}>N3</text>
        <motion.text {...en(t + 2.0)} x={x1 + 54} y={yA + 20} fill="var(--boquilla)" style={{ font: "400 16px var(--font)" }}>mismo GUID</motion.text>
      </motion.g>
      {/* Cota del cambio */}
      <motion.g {...en(t + 1.7)}>
        <line x1={x1 + 18} x2={x1 + 18} y1={yB + 12} y2={yA - 12} stroke="var(--cota)" strokeWidth={1.5} />
        <path d={`M${x1 + 18} ${yB + 10} l-4.5 10 h9 Z`} fill="var(--cota)" />
        <text x={x1 - 10} y={(yA + yB) / 2 + 7} textAnchor="end" fill="var(--cota)" style={{ font: "560 20px var(--font)", fontStretch: "110%" }}>+200</text>
      </motion.g>
      {/* N4, nueva */}
      <motion.g {...en(t + 2.4, { opacity: 0, scale: 0.6 })} style={{ transformBox: "fill-box", originX: 1, originY: 0.5 }}>
        <rect x={x0 - 36} y={100} width={36} height={18} fill="var(--film-2)" stroke="var(--boquilla)" strokeWidth={1.5} />
        <rect x={x0 - 42} y={94} width={6} height={30} fill="var(--boquilla)" />
        <text x={x0 - 52} y={106} textAnchor="end" fill="var(--boquilla)" style={{ font: "620 20px var(--font)" }}>N4</text>
        <text x={x0 - 52} y={126} textAnchor="end" fill="var(--boquilla)" style={{ font: "400 16px var(--font)" }}>nueva</text>
      </motion.g>
      <motion.g {...en(t + 2.8)}>
        <text x={W - 14} y={30} textAnchor="end" fill="var(--aux)" style={{ font: "400 15px var(--font)" }}>V-101, sintético</text>
      </motion.g>
    </svg>
  );
}

/* 3 · Por voz: se dicta el cambio y queda en borrador para comprobar. */
function Voz({ t }) {
  const barras = [0.35, 0.7, 1, 0.55, 0.85, 0.4, 0.95, 0.6, 0.3, 0.75, 0.5, 0.9, 0.45, 0.65, 0.8, 0.4];
  return (
    <div style={{ position: "absolute", inset: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 18, height: 64 }}>
        <div style={{ position: "relative", width: 56, height: 56, flex: "none" }}>
          {!EXPORT && [0, 1].map((k) => (
            <motion.span key={k} initial={{ scale: 1, opacity: 0 }} animate={{ scale: [1, 1.9], opacity: [0.45, 0] }}
              transition={{ delay: t + 0.3 + k * 0.6, duration: 1.2, repeat: 2, ease: "easeOut" }}
              style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "var(--cota)" }} />
          ))}
          <div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "var(--cota)", display: "grid", placeItems: "center" }}>
            <svg width="22" height="28" viewBox="0 0 24 30" aria-hidden>
              <rect x="7" y="2" width="10" height="17" rx="5" fill="#fff" />
              <path d="M3 14a9 9 0 0 0 18 0M12 23v5" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" />
            </svg>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, height: 48 }}>
          {barras.map((b, i) => (
            <motion.i key={i}
              style={{ display: "block", width: 5, height: 46, borderRadius: 3, background: "var(--trazo-2)", transformOrigin: "center", ...(EXPORT ? { transform: `scaleY(${b * 0.6})` } : {}) }}
              {...(EXPORT ? { initial: false } : { initial: { scaleY: 0.12 }, animate: { scaleY: [0.12, b, 0.25, b * 0.8, 0.3] }, transition: { delay: t + 0.3 + i * 0.04, duration: 0.9, repeat: 2, ease: "easeInOut" } })} />
          ))}
        </div>
      </div>
      <div style={{ marginTop: 16, fontSize: 25, fontStyle: "italic", minHeight: 34 }}>
        «<Teclea texto="Sube la boquilla N1 200 mm" desde={t + 0.6} />»
      </div>
      <motion.div {...en(t + 2.2, { opacity: 0, y: 10 })}
        style={{ marginTop: 16, padding: "12px 18px", background: "var(--film)", border: "1px solid var(--hair-2)", borderRadius: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 19, color: "var(--trazo-2)" }}>N1 · elevación</span>
          <span style={{ fontSize: 15, color: "var(--trazo-2)", padding: "2px 10px", borderRadius: 999, border: "1.5px solid var(--hair-2)" }}>Borrador</span>
        </div>
        <div className="cifra" style={{ fontSize: 30, marginTop: 8, fontWeight: 500, whiteSpace: "nowrap" }}>
          2.580 <span style={{ color: "var(--aux)", fontStretch: "100%" }}>→</span> <span className="rojo">2.780 mm</span>
        </div>
      </motion.div>
    </div>
  );
}

/* 4 · Firma: el sello cae; cambia un dato y la aprobación caduca. */
function Firma({ t }) {
  const cambia = useDesde(t + 2.6);
  const filas = [
    ["Diámetro exterior", cambia ? "1.930 mm" : "1.920 mm", true],
    ["Long. entre tangentes", "5.700 mm"],
    ["Pernos de anclaje", "4 × M24"],
  ];
  return (
    <div style={{ position: "absolute", inset: 24 }}>
      {filas.map(([k, v, vivo], i) => (
        <motion.div key={k} {...en(t + 0.2 + i * 0.15)}
          style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "11px 2px", borderBottom: "1px solid var(--hair)", fontSize: 20 }}>
          <span style={{ color: "var(--trazo-2)" }}>{k}</span>
          <span style={{ fontWeight: 560, padding: "0 6px", borderRadius: 3, transition: "background .4s, color .4s", ...(vivo && cambia ? { background: "rgba(255,90,78,0.18)", color: "var(--cota)" } : {}) }}>{v}</span>
        </motion.div>
      ))}
      <motion.div
        {...(EXPORT
          ? { initial: false, animate: { opacity: 0.35, rotate: -8, scale: 1 } }
          : { initial: { opacity: 0, scale: 1.8, rotate: -2 }, animate: cambia ? { opacity: 0.35, scale: 1, rotate: -8 } : { opacity: 1, scale: 1, rotate: -8 }, transition: { delay: cambia ? 0 : t + 1.0, duration: cambia ? 0.6 : 0.35, ease: [0.3, 1.6, 0.5, 1] } })}
        style={{ position: "absolute", left: 20, top: 162, padding: "4px 16px", border: "3.5px solid var(--boquilla)", borderRadius: 6, color: "var(--boquilla)", fontSize: 32, fontWeight: 640, fontStretch: "112%", letterSpacing: "0.06em" }}>
        APROBADO
        {cambia && <motion.i initial={EXPORT ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.4 }}
          style={{ position: "absolute", left: -8, right: -8, top: "50%", height: 3.5, background: "var(--cota)", transformOrigin: "left" }} />}
      </motion.div>
      {cambia && (
        <motion.div {...en(EXPORT ? 0 : 0.5, { opacity: 0, y: 10 })}
          style={{ position: "absolute", right: 0, bottom: 0, fontSize: 18, color: "var(--trazo)", padding: "4px 14px", borderRadius: 999, border: "1.5px solid var(--cota)", background: "var(--film)" }}>
          Vuelve a borrador
        </motion.div>
      )}
    </div>
  );
}

const ESCENAS = { cita: Cita, cambio: Cambio, voz: Voz, firma: Firma };

function Tarjeta({ t, n, titulo, texto, children }) {
  return (
    <motion.div {...en(t, { opacity: 0, y: 18 })} style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ position: "relative", height: H, background: "var(--film-2)", border: "1px solid var(--hair)", overflow: "hidden" }}>
        <span style={{ position: "absolute", left: 12, top: 8, fontSize: 15, color: "var(--aux)", fontStretch: "80%" }}>{String(n).padStart(2, "0")}</span>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>{children}</div>
      </div>
      <div style={{ fontSize: 30, fontWeight: 640, fontStretch: "108%", letterSpacing: "-0.01em", marginTop: 22, lineHeight: 1.1 }}>{titulo}</div>
      <div style={{ fontSize: 22, lineHeight: 1.35, color: "var(--trazo-2)", marginTop: 10 }}>{texto}</div>
    </motion.div>
  );
}

export function Diferencias({ escenas }) {
  const paso = 2.0;
  return (
    <div style={{ position: "absolute", top: 160, left: 0, right: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 32 }}>
      {escenas.map((e, i) => {
        const Escena = ESCENAS[e.id];
        const t = 0.6 + i * paso;
        return (
          <Tarjeta key={e.id} t={t - 0.3} n={i + 1} titulo={e.titulo} texto={e.texto}>
            <Escena t={t} />
          </Tarjeta>
        );
      })}
    </div>
  );
}

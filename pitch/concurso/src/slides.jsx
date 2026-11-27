import { motion } from "motion/react";
import { useLayoutEffect, useRef, useState } from "react";
import { LogoMultiplica, LogoTR, LogoTrazIA, WordmarkTrazIA } from "./brand.jsx";
import { Benchmarks } from "./benchmarks.jsx";
import { Diferencias } from "./escenas.jsx";
import { Cota, Cuenta } from "./cota.jsx";
import { TARIFA_HORA, deck, eur } from "./content.js";
import { EXPORT, entra } from "./modo.js";
import { Torre } from "./torre.jsx";

const ease = [0.2, 0.8, 0.2, 1];

function Titular({ children, style }) {
  return <h1 className="titular estira" style={style}>{children}</h1>;
}

/* ---------- 2. Portada ---------- */
export function Portada({ onListo }) {
  return (
    <>
      <div style={{ position: "absolute", left: 0, top: 8, width: 900 }}>
        <motion.div {...entra(0.1)} style={{ display: "flex", alignItems: "center", gap: 36 }}>
          <LogoTrazIA style={{ height: 150, width: "auto" }} />
          <span className="aux" style={{ fontSize: 44, fontWeight: 300 }}>×</span>
          <LogoTR style={{ height: 96, width: "auto" }} />
          <span style={{ alignSelf: "stretch", width: 1, margin: "28px 0", background: "var(--hair-2)" }} />
          <LogoMultiplica style={{ height: 40, width: "auto" }} />
        </motion.div>
        <h1 className="titular estira" style={{ fontSize: 124, marginTop: 96, maxWidth: 900 }}>
          Del plano al modelo 3D.
        </h1>
        <motion.p className="entradilla" {...entra(0.9)} style={{ maxWidth: 760 }}>
          Cada cifra con su cita en el plano. Cada modelo con la firma del ingeniero.
        </motion.p>
      </div>
      <div style={{ position: "absolute", right: 260, top: -48 }}>
        <Torre ancho={640} alto={880} onListo={onListo} />
      </div>
    </>
  );
}

/* ---------- 3. Problema ---------- */
export function Problema({ hoja }) {
  return (
    <>
      <Titular>Hoy, cada plano se vuelve a dibujar en 3D. A mano.</Titular>
      <div style={{ position: "absolute", top: 250, left: 0, display: "flex", alignItems: "flex-end", gap: 44 }}>
        {hoja.factores.map((f, i) => (
          <motion.div key={f.texto} {...entra(0.7 + i * 0.35)} style={{ display: "flex", alignItems: "flex-end", gap: 44 }}>
            {i > 0 && <span className="aux" style={{ fontSize: 64, fontWeight: 300, lineHeight: 1.2 }}>×</span>}
            <div>
              <div className="cifra" style={{ fontSize: 96 }}>{f.valor}</div>
              <div style={{ fontSize: 26, color: "var(--trazo-2)", marginTop: 10 }}>{f.texto}</div>
            </div>
          </motion.div>
        ))}
      </div>
      <Cota ancho={1696} alto={210} delay={1.9} style={{ position: "absolute", top: 450, left: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
          <span className="cifra" style={{ fontSize: 132 }}>
            <Cuenta valor={hoja.horas.min} delay={2.4} /> – <Cuenta valor={hoja.horas.max} delay={2.4} /> h
          </span>
          <span style={{ fontSize: 30, color: "var(--trazo-2)" }}>por proyecto</span>
        </div>
      </Cota>
      <motion.div {...entra(3.6)} style={{ position: "absolute", top: 700, left: 0, display: "flex", alignItems: "baseline", gap: 28 }}>
        <span className="cifra rojo" style={{ fontSize: 76 }}>
          hasta {eur(hoja.euros.max)} €
        </span>
        <span style={{ fontSize: 28, color: "var(--trazo-2)" }}>
          {`por proyecto a ${TARIFA_HORA} €/h, en redibujar lo que ya está dibujado`}
        </span>
      </motion.div>
    </>
  );
}

/* ---------- 4. Por qué es difícil ---------- */
export function Dificil({ hoja }) {
  return (
    <>
      <Titular style={{ maxWidth: 1400 }}>Parece fácil. Por eso nadie lo ha llevado a producto.</Titular>
      <div style={{ position: "absolute", top: 270, left: 0, right: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)" }}>
        {hoja.muros.map((m, i) => (
          <motion.div key={m.titulo} {...entra(0.8 + i * 0.3)}
            style={{ padding: "8px 40px 0", borderLeft: i ? "1px solid var(--hair-2)" : 0, paddingLeft: i ? 40 : 0 }}>
            <div className="cifra" style={{ fontSize: 56, fontStretch: "106%", whiteSpace: "nowrap" }}>{m.cifra}</div>
            <div style={{ fontSize: 30, fontWeight: 620, marginTop: 28, lineHeight: 1.15 }}>{m.titulo}</div>
            <div style={{ fontSize: 24, lineHeight: 1.4, color: "var(--trazo-2)", marginTop: 14 }}>{m.texto}</div>
          </motion.div>
        ))}
      </div>
      <motion.p {...entra(2.4)} className="rojo"
        style={{ position: "absolute", top: 650, left: 0, margin: 0, maxWidth: 1400, fontSize: 48, lineHeight: 1.18, fontWeight: 520, fontStretch: "104%", letterSpacing: "-0.01em" }}>
        Una cota inventada no es una mala respuesta. Es una tubería que no encaja en obra.
      </motion.p>
    </>
  );
}

/* ---------- 5. Cómo ---------- */
function Caja({ x, y, w, h, children, color = "var(--hair-2)", destaca }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} fill="var(--film)" stroke={color} strokeWidth={1.5} />
      {destaca}
      <foreignObject x={x} y={y} width={w} height={h}>
        <div style={{ height: "100%", display: "grid", placeItems: "center", textAlign: "center", padding: "0 8px", fontSize: 22, lineHeight: 1.15 }}>
          {children}
        </div>
      </foreignObject>
    </g>
  );
}

export function Como({ hoja }) {
  const L = { x0: 320, w: 138, gap: 16, y: 150, h: 84 };
  const cx = (i) => L.x0 + i * (L.w + L.gap) + L.w / 2;
  const finCascada = L.x0 + 6 * L.w + 5 * L.gap;
  const SX = finCascada + 64;
  const rail = L.y - 46;
  return (
    <>
      <Titular style={{ maxWidth: 1500 }}>Reglas primero. IA solo donde falta. Firma humana.</Titular>
      <svg width={1696} height={420} style={{ position: "absolute", top: 230, left: 0, overflow: "visible" }}>
        {hoja.entradas.map((e, i) => {
          const y = 70 + i * 92;
          return (
            <g key={e}>
              <path d={`M0 ${y} h196 l20 20 v44 h-216 Z`} fill="none" stroke="var(--hair-2)" strokeWidth={1.5} />
              <path d={`M196 ${y} v20 h20`} fill="none" stroke="var(--hair-2)" strokeWidth={1.5} />
              <text x={18} y={y + 41} fill="var(--trazo)" style={{ font: "400 23px var(--font)" }}>{e}</text>
              <path d={`M216 ${y + 32} C 270 ${y + 32}, 270 ${L.y + L.h / 2}, ${L.x0 - 6} ${L.y + L.h / 2}`} fill="none" stroke="var(--hair-2)" strokeWidth={1.5} />
            </g>
          );
        })}
        {/* Raíl por el que viaja cada dato */}
        <line x1={L.x0} y1={rail} x2={finCascada} y2={rail} stroke="var(--hair)" strokeWidth={1.5} strokeDasharray="6 8" />
        {hoja.lectores.map((n, i) => {
          const x = L.x0 + i * (L.w + L.gap);
          const caso = hoja.casos.findIndex((c) => c.lector === i);
          const t = 1.0 + caso * 2.2 + 1.0;
          return (
            <g key={n}>
              {i > 0 && <line x1={x - L.gap} y1={L.y + L.h / 2} x2={x} y2={L.y + L.h / 2} stroke="var(--hair-2)" strokeWidth={1.5} />}
              <Caja x={x} y={L.y} w={L.w} h={L.h}
                destaca={caso >= 0 && (
                  <motion.rect x={x} y={L.y} width={L.w} height={L.h} fill="none" stroke="var(--cota)" strokeWidth={2.5}
                    {...(EXPORT ? { initial: false } : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { delay: t, duration: 0.3 } })} />
                )}>
                <span style={{ color: n === "Visión IA" ? "var(--trazo)" : "var(--trazo)", fontWeight: n === "Visión IA" ? 620 : 450 }}>{n}</span>
              </Caja>
            </g>
          );
        })}
        <line x1={finCascada} y1={L.y + L.h / 2} x2={SX - 8} y2={L.y + L.h / 2} stroke="var(--hair-2)" strokeWidth={1.5} />
        <path d={`M${SX} ${L.y + L.h / 2} l-14 -6 v12 Z`} fill="var(--trazo-2)" />
        {/* Casos: cada dato baja en el primer lector que lo resuelve */}
        {hoja.casos.map((c, k) => {
          const t = 1.0 + k * 2.2;
          const destino = cx(c.lector);
          const anim = EXPORT
            ? { initial: false, animate: { x: destino, opacity: 0 } }
            : {
                initial: { x: L.x0, opacity: 0 },
                animate: { x: [L.x0, destino, destino], opacity: [1, 1, 0] },
                transition: { delay: t, duration: 1.4, times: [0, 0.72, 1], ease: "easeInOut" },
              };
          return (
            <g key={c.cifra}>
              <motion.g {...anim} style={{ y: rail }}>
                <circle r={9} fill="var(--cota)" />
              </motion.g>
              <motion.g {...(EXPORT ? { initial: false } : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { delay: t + 1.05, duration: 0.4 } })}>
                <line x1={destino} y1={L.y + L.h} x2={destino} y2={L.y + L.h + 34} stroke="var(--cota)" strokeWidth={1.5} />
                <text x={destino} y={L.y + L.h + 72} textAnchor="middle" fill="var(--cota)" style={{ font: "560 30px var(--font)", fontStretch: "120%" }}>{c.cifra}</text>
              </motion.g>
            </g>
          );
        })}
        {/* Salida y firma */}
        <rect x={SX} y={L.y - 38} width={1696 - SX} height={160} fill="none" stroke="var(--trazo-2)" strokeWidth={1.5} />
        <foreignObject x={SX} y={L.y - 38} width={1696 - SX} height={160}>
          <div style={{ padding: "24px 30px", fontSize: 25, lineHeight: 1.5 }}>
            {hoja.salidas.map((s) => <div key={s}>{s}</div>)}
          </div>
        </foreignObject>
        <motion.g {...(EXPORT ? { initial: false } : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { delay: 7.8, duration: 0.5 } })}>
          <line x1={SX + 30} y1={L.y + 122} x2={SX + 30} y2={L.y + 158} stroke="var(--boquilla)" strokeWidth={1.5} />
          <foreignObject x={SX} y={L.y + 166} width={1696 - SX} height={110}>
            <div style={{ padding: "0 0 0 30px", fontSize: 24, lineHeight: 1.35, color: "var(--boquilla)" }}>{hoja.firma}</div>
          </foreignObject>
        </motion.g>
      </svg>
      <div style={{ position: "absolute", top: 690, left: 0, right: 0, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 48, borderTop: "1px solid var(--hair-2)", paddingTop: 26 }}>
        {hoja.garantias.map((g, i) => (
          <motion.div key={g} {...entra(0.6 + i * 0.2)} style={{ fontSize: 26, lineHeight: 1.38, color: "var(--trazo-2)" }}>{g}</motion.div>
        ))}
      </div>
    </>
  );
}

/* ---------- 6. Pruebas con datos reales ---------- */
export function Pruebas({ hoja }) {
  return (
    <>
      <Titular style={{ maxWidth: 1500 }}>Ya funciona con planos reales de Técnicas Reunidas.</Titular>
      <div style={{ position: "absolute", top: 370, left: 0, right: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 56 }}>
        {hoja.kpis.map((k, i) => (
          <div key={k.texto}>
            <Cota ancho={380} alto={170} delay={0.7 + i * 0.35}>
              <span className="cifra" style={{ fontSize: 100, whiteSpace: "nowrap" }}>
                <Cuenta valor={k.valor} decimales={k.decimales ?? 0} delay={1.2 + i * 0.35} />
                <span style={{ fontSize: 46, fontStretch: "100%", letterSpacing: 0 }}>{k.sufijo}</span>
              </span>
            </Cota>
            <motion.div {...entra(1.4 + i * 0.35)}>
              <div style={{ fontSize: 27, lineHeight: 1.32, marginTop: 26 }}>{k.texto}</div>
            </motion.div>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---------- 7. Benchmarks: benchmarks.jsx ---------- */

/* ---------- 8. En qué nos diferenciamos ---------- */
export function Diferencia({ hoja }) {
  return (
    <>
      <Titular>En qué nos diferenciamos.</Titular>
      <Diferencias escenas={hoja.escenas} />
      <motion.div {...entra(8.8)} style={{ position: "absolute", top: 632, left: 0, right: 0, borderTop: "1px solid var(--hair-2)", paddingTop: 34 }}>
        <div style={{ fontSize: 64, fontWeight: 640, fontStretch: "110%", letterSpacing: "-0.02em", lineHeight: 1.05 }}>{hoja.cierre}</div>
        <div className="verde" style={{ fontSize: 40, fontWeight: 560, fontStretch: "106%", letterSpacing: "-0.01em", marginTop: 18 }}>{hoja.cierre2}</div>
      </motion.div>
    </>
  );
}

/* ---------- 9. La interfaz, en vídeo a toda la lámina ---------- */
export function Interfaz({ hoja }) {
  const ref = useRef(null);
  const [falta, setFalta] = useState(false);
  useLayoutEffect(() => {
    // La exportación espera a que el vídeo tenga su primer fotograma (data-video="listo").
    document.body.dataset.video = "cargando";
    return () => { delete document.body.dataset.video; delete document.body.dataset.videoMs; };
  }, []);
  const listo = () => {
    const v = ref.current;
    if (!v) return;
    document.body.dataset.videoMs = String(Math.round(v.duration * 1000));
    document.body.dataset.video = "listo";
  };
  return (
    <div style={{ position: "absolute", left: -112, top: -104, width: 1920, height: 1080, background: "var(--film)", zIndex: 5 }}>
      {!falta && (
        <video ref={ref} src={`${import.meta.env.BASE_URL}${hoja.video}`} autoPlay={!EXPORT} muted playsInline preload="auto"
          onLoadedData={listo} onError={() => { setFalta(true); document.body.dataset.video = "falta"; }}
          style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
      )}
      {falta && (
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center", color: "var(--aux)", fontSize: 28 }}>
          Falta el vídeo de la interfaz: copia el .mp4 en pitch/concurso/public/{hoja.video}
        </div>
      )}
    </div>
  );
}

/* ---------- 1. Equipo ---------- */
export function Equipo() {
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center" }}>
      <motion.div {...entra(0.1)}>
        <WordmarkTrazIA style={{ height: 120, width: "auto" }} />
      </motion.div>
      <motion.ul {...entra(0.7)}
        style={{ listStyle: "none", margin: "88px 0 0", padding: 0, display: "flex", gap: 72, fontSize: 34, fontWeight: 460, color: "var(--trazo)" }}>
        {deck.equipo.map((n) => <li key={n}>{n}</li>)}
      </motion.ul>
    </div>
  );
}

export const componentes = {
  equipo: Equipo,
  portada: Portada,
  problema: Problema,
  dificil: Dificil,
  como: Como,
  pruebas: Pruebas,
  benchmarks: Benchmarks,
  diferencia: Diferencia,
  interfaz: Interfaz,
};

export { TARIFA_HORA, ease };

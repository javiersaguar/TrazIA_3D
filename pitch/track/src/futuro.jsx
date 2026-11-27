import { motion } from "motion/react";
import { useEffect, useState } from "react";
import gaSintetico from "./ga-sintetico.webp?url";
import { hojas } from "./content.js";
import { EXPORT } from "./modo.js";

/*
  Última hoja: lo que ya nos diferencia, en cuatro escenas que se reproducen solas, y lo siguiente,
  en una banda discontinua. En exportación todo aparece en su estado final.
  Datos reales del 80V01: la cota de 5.700 (con el recorte de la hoja de la cita) y la elevación de
  N1, 2.580 mm, a la que la orden dictada suma 200.
*/

const ease = [0.65, 0, 0.35, 1];
const local = (f) => `${import.meta.env.BASE_URL}local/${f}`;
const cita = hojas.find((h) => h.id === "cita").cita;

/** Aparece en t segundos; en exportación ya está. */
const en = (t, desde = { opacity: 0 }) =>
  EXPORT ? { initial: false } : { initial: desde, animate: { opacity: 1, x: 0, y: 0, scale: 1 }, transition: { delay: t, duration: 0.5, ease: [0.2, 0.8, 0.2, 1] } };

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
function Teclea({ texto, desde, cps = 26 }) {
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

function Tarjeta({ t, titulo, texto, children }) {
  return (
    <motion.div {...en(t, { opacity: 0, y: 18 })} style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ position: "relative", height: 300, borderRadius: 10, background: "var(--niebla)", overflow: "hidden" }}>{children}</div>
      <div style={{ fontSize: 29, fontWeight: 400, color: "var(--turquesa)", marginTop: 16 }}>{titulo}</div>
      <div className="texto" style={{ fontSize: 23, lineHeight: 1.3, marginTop: 4 }}>{texto}</div>
    </motion.div>
  );
}

/* 1 · Copiloto: la pregunta se escribe y la respuesta llega con su cita en el plano. */
function Copiloto({ t }) {
  const [sint, setSint] = useState(false);
  const ancho = 370;
  const alto = Math.round((ancho * 156) / 1676);
  return (
    <div style={{ position: "absolute", inset: 22, display: "flex", flexDirection: "column", gap: 12 }}>
      <motion.div {...en(t + 0.3, { opacity: 0, y: 8 })}
        style={{ alignSelf: "flex-end", maxWidth: 300, padding: "10px 16px", borderRadius: "16px 16px 4px 16px", background: "#fff", boxShadow: "0 0 0 1px var(--linea)", fontSize: 22 }}>
        <Teclea texto="¿De dónde sale el 5.700?" desde={t + 0.5} />
      </motion.div>
      <motion.div {...en(t + 1.9, { opacity: 0, y: 8 })}
        style={{ alignSelf: "flex-start", padding: "10px 16px", borderRadius: "16px 16px 16px 4px", background: "var(--agua-suave)", fontSize: 21, lineHeight: 1.3 }}>
        <div style={{ fontWeight: 400 }}>Longitud entre tangentes</div>
        <div style={{ color: "var(--pizarra)" }}>GA-80V01, página 1</div>
      </motion.div>
      <motion.div {...en(t + 2.5)} style={{ position: "relative", width: ancho, height: alto, borderRadius: 4, overflow: "hidden", background: "#fff", boxShadow: "0 0 0 1px var(--linea)" }}>
        <img src={sint ? gaSintetico : local("cita-80v01.webp")} alt="Cota del plano" onError={() => setSint(true)}
          style={{ width: "100%", height: "100%", objectFit: sint ? "cover" : "fill", display: "block" }} />
        {!sint && (
          <motion.div {...(EXPORT ? { initial: false } : { initial: { opacity: 0, scale: 1.6 }, animate: { opacity: 1, scale: 1 }, transition: { delay: t + 3.0, duration: 0.45, ease } })}
            style={{ position: "absolute", left: `${cita.caja.left}%`, top: `${cita.caja.top}%`, width: `${cita.caja.width}%`, height: `${cita.caja.height}%`, outline: "2px solid var(--turquesa)", outlineOffset: 2, background: "rgba(116,209,224,0.25)", borderRadius: 2 }} />
        )}
      </motion.div>
      {sint && <span className="sintetico" style={{ fontSize: 16, alignSelf: "flex-start" }}>Plano de ejemplo sintético</span>}
    </div>
  );
}

/* 2 · Cambio dictado: micrófono, onda, transcripción y borrador con el valor nuevo. */
function Dictado({ t }) {
  const barras = [0.35, 0.7, 1, 0.55, 0.85, 0.4, 0.95, 0.6, 0.3, 0.75, 0.5, 0.9, 0.45, 0.65];
  const habla = !EXPORT;
  return (
    <div style={{ position: "absolute", inset: 22 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 18, height: 70 }}>
        <div style={{ position: "relative", width: 58, height: 58, flex: "none" }}>
          {habla && [0, 1].map((k) => (
            <motion.span key={k} initial={{ scale: 1, opacity: 0 }} animate={{ scale: [1, 1.9], opacity: [0.5, 0] }}
              transition={{ delay: t + 0.4 + k * 0.6, duration: 1.2, repeat: 2, ease: "easeOut" }}
              style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "var(--agua)" }} />
          ))}
          <div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "var(--turquesa)", display: "grid", placeItems: "center" }}>
            <svg width="24" height="30" viewBox="0 0 24 30" aria-hidden>
              <rect x="7" y="2" width="10" height="17" rx="5" fill="#fff" />
              <path d="M3 14a9 9 0 0 0 18 0M12 23v5" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" />
            </svg>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, height: 50 }}>
          {barras.map((b, i) => (
            <motion.i key={i} style={{ display: "block", width: 6, height: 50, borderRadius: 3, background: "var(--turquesa)", opacity: 0.75, transformOrigin: "center" }}
              {...(habla
                ? { initial: { scaleY: 0.12 }, animate: { scaleY: [0.12, b, 0.25, b * 0.8, b * 0.5] }, transition: { delay: t + 0.4 + i * 0.04, duration: 0.9, repeat: 2, ease: "easeInOut" } }
                : { initial: false, style: { display: "block", width: 6, height: 50, borderRadius: 3, background: "var(--turquesa)", opacity: 0.75, transform: `scaleY(${b * 0.6})` } })} />
          ))}
        </div>
      </div>
      <div style={{ marginTop: 18, fontSize: 25, fontStyle: "italic", minHeight: 34 }}>
        «<Teclea texto="Sube la boquilla N1 200 mm" desde={t + 0.8} cps={20} />»
      </div>
      <motion.div {...en(t + 2.6, { opacity: 0, y: 10 })}
        style={{ marginTop: 18, padding: "12px 16px", background: "#fff", borderRadius: 8, boxShadow: "0 0 0 1px var(--linea)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 20, color: "var(--pizarra)" }}>N1 · elevación</span>
          <span style={{ fontSize: 17, fontWeight: 400, color: "var(--pizarra)", padding: "2px 10px", borderRadius: 999, boxShadow: "inset 0 0 0 1.5px var(--pizarra-2)" }}>Borrador</span>
        </div>
        <div style={{ fontSize: 28, marginTop: 4 }}>
          2.580 <span style={{ color: "var(--pizarra-2)" }}>→</span> <span className="turquesa" style={{ fontWeight: 400 }}>2.780 mm</span>
        </div>
      </motion.div>
    </div>
  );
}

/* 3 · Aprobación: el sello cae; cambia un dato y el sello se retira. */
function Aprobacion({ t }) {
  const cambia = useDesde(t + 3.0);
  const filas = [
    ["Diámetro exterior", cambia ? "1.930 mm" : "1.920 mm", true],
    ["Longitud entre tangentes", "5.700 mm"],
    ["Pernos de anclaje", "4 × M24"],
  ];
  return (
    <div style={{ position: "absolute", inset: 22 }}>
      {filas.map(([k, v, vivo], i) => (
        <motion.div key={k} {...en(t + 0.3 + i * 0.15)}
          style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "11px 2px", borderBottom: "1px solid var(--linea)", fontSize: 21 }}>
          <span className="texto" style={{ fontSize: 21 }}>{k}</span>
          <span style={{ fontWeight: 400, padding: "0 6px", borderRadius: 4, transition: "background .4s, color .4s", ...(vivo && cambia ? { background: "#fde8c8", color: "#9a5b00" } : {}) }}>{v}</span>
        </motion.div>
      ))}
      <motion.div
        {...(EXPORT
          ? { initial: false, animate: { opacity: 0.28, rotate: -9, scale: 1 } }
          : { initial: { opacity: 0, scale: 1.8, rotate: -2 }, animate: cambia ? { opacity: 0.28, scale: 1, rotate: -9 } : { opacity: 1, scale: 1, rotate: -9 }, transition: { delay: cambia ? 0 : t + 1.2, duration: cambia ? 0.6 : 0.35, ease: [0.3, 1.6, 0.5, 1] } })}
        style={{ position: "absolute", left: 30, top: 172, padding: "6px 18px", border: "4px solid var(--lima)", borderRadius: 8, color: "#6f8f00", fontSize: 34, fontWeight: 500, letterSpacing: "0.06em" }}>
        APROBADO
        {cambia && <motion.i initial={EXPORT ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.4 }}
          style={{ position: "absolute", left: -8, right: -8, top: "50%", height: 4, background: "#9a5b00", transformOrigin: "left" }} />}
      </motion.div>
      {cambia && (
        <motion.div {...en(EXPORT ? 0 : 0.5, { opacity: 0, y: 10 })}
          style={{ position: "absolute", right: 0, bottom: 0, fontSize: 20, fontWeight: 400, color: "var(--pizarra)", padding: "4px 14px", borderRadius: 999, boxShadow: "inset 0 0 0 1.5px var(--pizarra-2)", background: "#fff" }}>
          Vuelve a borrador
        </motion.div>
      )}
    </div>
  );
}

/* 4 · Vuestra nube: el perímetro se dibuja alrededor de los datos y nada sale fuera. */
function Nube({ t }) {
  const doc = (x, y) => (
    <g transform={`translate(${x} ${y})`}>
      <path d="M0 0h26l10 10v36H0z" fill="#fff" stroke="var(--pizarra-2)" strokeWidth="1.5" />
      <path d="M6 18h22M6 25h22M6 32h16" stroke="var(--linea-2)" strokeWidth="2" />
    </g>
  );
  const dibuja = (d) => (EXPORT ? { initial: false } : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { delay: t + d, duration: 1.4, ease } });
  return (
    <svg width="100%" height="100%" viewBox="0 0 414 300" style={{ position: "absolute", inset: 0 }} aria-hidden>
      <motion.rect x="20" y="30" width="270" height="240" rx="16" fill="none" stroke="var(--turquesa)" strokeWidth="2.5" strokeDasharray="8 6" {...dibuja(0.3)} />
      <motion.g {...en(t + 0.6)}>
        <text x="38" y="52" fill="var(--turquesa)" style={{ font: "400 19px var(--font)" }}>Azure de la organización</text>
        {doc(44, 76)}{doc(92, 76)}{doc(140, 76)}
        <rect x="44" y="150" width="70" height="36" rx="8" fill="var(--agua-suave)" />
        <text x="79" y="174" textAnchor="middle" fill="var(--turquesa)" style={{ font: "500 18px var(--font)" }}>IA</text>
        <rect x="128" y="150" width="84" height="36" rx="8" fill="#fff" stroke="var(--linea-2)" />
        <text x="170" y="174" textAnchor="middle" fill="var(--tinta)" style={{ font: "400 18px var(--font)" }}>IFC</text>
      </motion.g>
      <motion.path d="M200 118 H286" stroke="var(--pizarra-2)" strokeWidth="2.5" fill="none" {...dibuja(1.8)} />
      <motion.g {...en(t + 2.9, { opacity: 0, scale: 0.4 })} style={{ transformOrigin: "290px 118px" }}>
        <circle cx="290" cy="118" r="15" fill="#fff" stroke="#c94a4a" strokeWidth="2.5" />
        <path d="M283 111l14 14M297 111l-14 14" stroke="#c94a4a" strokeWidth="2.5" strokeLinecap="round" />
      </motion.g>
      <motion.g {...en(t + 2.4)}>
        <circle cx="358" cy="118" r="26" fill="none" stroke="var(--linea-2)" strokeWidth="2" />
        <path d="M332 118h52M358 92c-12 14-12 38 0 52M358 92c12 14 12 38 0 52" stroke="var(--linea-2)" strokeWidth="1.6" fill="none" />
        <text x="358" y="170" textAnchor="middle" fill="var(--pizarra-2)" style={{ font: "400 16px var(--font)" }}>Fuera</text>
      </motion.g>
    </svg>
  );
}

/* Lo siguiente: los planos entran solos por una cola de eventos y se reparten entre workers. */
function Siguiente({ t, puntos }) {
  const docs = [0, 1, 2, 3, 4, 5];
  const x0 = 250;
  const x1 = 820;
  const enCola = (i) => x0 + 30 + i * ((x1 - x0 - 60) / (docs.length - 1));
  return (
    <motion.div {...en(t)} style={{ position: "absolute", left: 0, right: 0, top: 600 }}>
      <svg width="1728" height="150" style={{ display: "block", overflow: "visible" }} aria-hidden>
        <text x="0" y="22" fill="var(--pizarra)" style={{ font: "400 30px var(--font)" }}>Lo siguiente</text>
        <rect x="0" y="52" width="210" height="72" rx="10" fill="#fff" stroke="var(--pizarra-2)" strokeWidth="1.5" strokeDasharray="6 5" />
        <text x="105" y="84" textAnchor="middle" fill="var(--tinta)" style={{ font: "400 21px var(--font)" }}>Gestor</text>
        <text x="105" y="108" textAnchor="middle" fill="var(--tinta)" style={{ font: "400 21px var(--font)" }}>documental</text>
        <line x1="210" y1="88" x2={x1 + 30} y2="88" stroke="var(--pizarra-2)" strokeWidth="2" strokeDasharray="6 6" />
        <text x={(x0 + x1) / 2} y="58" textAnchor="middle" fill="var(--pizarra)" style={{ font: "400 20px var(--font)" }}>{puntos[0].titulo} · cola de eventos, tipo Kafka</text>
        {docs.map((i) => (
          <motion.g key={i}
            {...(EXPORT
              ? { initial: false, transform: `translate(${enCola(i)} 76)` }
              : { initial: { x: x0, y: 76, opacity: 0 }, animate: { x: [x0, x1], opacity: [0, 1, 1, 0] }, transition: { delay: t + 0.4 + i * 0.55, duration: 3.3, repeat: Infinity, repeatDelay: 0, ease: "linear", times: [0, 0.1, 0.9, 1] } })}>
            <rect width="18" height="24" rx="2" fill="var(--agua-suave)" stroke="var(--turquesa)" strokeWidth="1.5" />
          </motion.g>
        ))}
        {[0, 1, 2].map((k) => (
          <g key={k} transform={`translate(${x1 + 40} ${44 + k * 32})`}>
            <rect width="250" height="24" rx="6" fill="#fff" stroke="var(--pizarra-2)" strokeWidth="1.5" strokeDasharray="5 4" />
            {[0, 1, 2, 3, 4, 5].map((p) => {
              const cambia = (p + k * 2) % 5 === 1;
              return (
                <motion.rect key={p} x={12 + p * 38} y="6" width="28" height="12" rx="2"
                  fill={cambia ? "var(--agua)" : "var(--linea)"}
                  {...(EXPORT || !cambia ? {} : { animate: { opacity: [0.35, 1, 0.35] }, transition: { delay: t + 1 + k * 0.4, duration: 1.6, repeat: Infinity } })} />
              );
            })}
          </g>
        ))}
        <text x={x1 + 165} y="150" textAnchor="middle" fill="var(--pizarra)" style={{ font: "400 20px var(--font)" }}>{puntos[1].titulo}: solo se relee lo que cambió</text>
        {puntos.slice(2).map((p, i) => (
          <g key={p.titulo} transform={`translate(1230 ${52 + i * 44})`}>
            <rect width="498" height="34" rx="17" fill="#fff" stroke="var(--pizarra-2)" strokeWidth="1.5" strokeDasharray="6 5" />
            <circle cx="22" cy="17" r="5" fill="var(--pizarra-2)" />
            <text x="40" y="24" fill="var(--tinta)" style={{ font: "400 20px var(--font)" }}>{p.corto}</text>
          </g>
        ))}
      </svg>
    </motion.div>
  );
}

export function Futuro({ hoja }) {
  const escenas = [Copiloto, Dictado, Aprobacion, Nube];
  const paso = 2.2;
  return (
    <>
      <h1 className="titular barrido">Más que un lector de planos.</h1>
      <div style={{ position: "absolute", top: 120, left: 0, right: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 24 }}>
        {hoja.ya.map((p, i) => {
          const Escena = escenas[i];
          const t = 0.6 + i * paso;
          return (
            <Tarjeta key={p.titulo} t={t - 0.3} titulo={p.titulo} texto={p.corto}>
              <Escena t={t} />
            </Tarjeta>
          );
        })}
      </div>
      <Siguiente t={0.6 + 4 * paso} puntos={hoja.siguiente} />
    </>
  );
}

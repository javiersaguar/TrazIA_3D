import { animate, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { LogoMultiplica, LogoTR, LogoTrazIA } from "../../concurso/src/brand.jsx";
import gaSintetico from "./ga-sintetico.webp?url";
import ifcA from "../../../web/public/demo/ifc/rev_a.ifc?url";
import ifcB from "../../../web/public/demo/ifc/rev_b.ifc?url";
import { deck } from "./content.js";
import { EXPORT, entra } from "./modo.js";
import { Benchmark } from "./benchmark.jsx";
import { Visor } from "./visor.jsx";
import { Futuro } from "./futuro.jsx";

const ease = [0.65, 0, 0.35, 1];
const local = (f) => `${import.meta.env.BASE_URL}local/${f}`;
const IFC_80V01 = local("80v01-rev2.ifc");

function Titular({ children, style }) {
  return <h1 className="titular barrido" style={style}>{children}</h1>;
}

/** Imagen del material local del reto; si no está en este equipo, muestra el ejemplo sintético. */
function Imagen({ src, respaldo, onRespaldo, style, alt }) {
  const [url, setUrl] = useState(src);
  return (
    <img src={url} alt={alt} style={{ display: "block", ...style }}
      onError={() => { if (respaldo && url !== respaldo) { setUrl(respaldo); onRespaldo?.(); } }} />
  );
}

/** Línea aguamarina que barre una zona de izquierda a derecha, como el lector sobre el plano. */
function Barrido({ delay = 0, duracion = 1.6 }) {
  if (EXPORT) return null;
  return (
    <motion.div aria-hidden
      initial={{ left: "0%", opacity: 1 }} animate={{ left: "100%", opacity: [1, 1, 0] }}
      transition={{ delay, duration: duracion, ease, times: [0, 0.85, 1] }}
      style={{ position: "absolute", top: 0, bottom: 0, width: 3, background: "var(--agua)", boxShadow: "0 0 22px var(--agua)", zIndex: 2 }} />
  );
}

/** Revela su contenido de izquierda a derecha al ritmo del barrido. */
function Revela({ delay = 0, duracion = 1.6, children, style }) {
  return (
    <motion.div style={{ position: "relative", ...style }}
      {...(EXPORT ? { initial: false } : { initial: { clipPath: "inset(0 100% 0 0)" }, animate: { clipPath: "inset(0 0% 0 0)" }, transition: { delay, duration: duracion, ease } })}>
      {children}
    </motion.div>
  );
}

function Cuenta({ valor, delay = 0, decimales = 0 }) {
  const [n, setN] = useState(EXPORT ? valor : 0);
  useEffect(() => {
    if (EXPORT) return undefined;
    const c = animate(0, valor, { delay, duration: 1.6, ease: [0.16, 1, 0.3, 1], onUpdate: setN });
    return () => c.stop();
  }, [valor, delay]);
  return <>{new Intl.NumberFormat("es-ES", { minimumFractionDigits: decimales, maximumFractionDigits: decimales, useGrouping: "always" }).format(n)}</>;
}

function Sintetico({ children }) {
  return <span className="sintetico">{children}</span>;
}

/* ---------- Portada ---------- */
export function Portada({ hoja, onListo }) {
  const [sint, setSint] = useState(false);
  return (
    <>
      <div style={{ position: "absolute", left: 0, top: 70, width: 800 }}>
        <h1 className="titular barrido" style={{ fontSize: 132, lineHeight: 0.98 }}>Del plano al modelo.</h1>
        <motion.p className="texto" {...entra(1.0)} style={{ marginTop: 40, fontSize: 34, maxWidth: 700 }}>{hoja.lema}</motion.p>
        <motion.div {...entra(1.4)} style={{ marginTop: 92, display: "flex", alignItems: "center", gap: 40 }}>
          <LogoTR color="var(--pizarra)" style={{ height: 74, width: "auto" }} />
          <span style={{ width: 1, height: 56, background: "var(--linea-2)" }} />
          <LogoMultiplica color="var(--pizarra)" style={{ height: 34, width: "auto" }} />
        </motion.div>
        <motion.p {...entra(1.6)} style={{ marginTop: 26, fontSize: 24, color: "var(--pizarra)" }}>{deck.reto}, {deck.evento}</motion.p>
      </div>
      <div style={{ position: "absolute", right: -40, top: -20, width: 940, height: 820 }}>
        <Imagen src={local("plano-80v01.webp")} respaldo={gaSintetico} onRespaldo={() => setSint(true)} alt="Plano GA"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", opacity: 0.32, filter: "grayscale(1)" }} />
        <Revela delay={0.6} duracion={2.2} style={{ position: "absolute", inset: 0 }}>
          <Visor urls={[IFC_80V01]} respaldo={[ifcB]} ancho={940} alto={820} elevacion={20}
            onEstado={(e) => e.respaldo && setSint(true)} onListo={onListo} />
        </Revela>
        <div style={{ position: "absolute", inset: 0 }}><Barrido delay={0.6} duracion={2.2} /></div>
        {sint && <div style={{ position: "absolute", right: 40, bottom: 20 }}><Sintetico>Ejemplo sintético</Sintetico></div>}
      </div>
    </>
  );
}

/* ---------- Así se hace hoy ---------- */
function Paso({ children, delay, ancho, style }) {
  return (
    <motion.div {...entra(delay, { opacity: 0, x: -16 })}
      style={{ width: ancho, height: 168, padding: 18, borderRadius: 8, background: "var(--niebla)", display: "flex", flexDirection: "column", justifyContent: "space-between", ...style }}>
      {children}
    </motion.div>
  );
}

function Flecha({ delay }) {
  return (
    <motion.svg {...entra(delay)} width={56} height={20} viewBox="0 0 56 20" aria-hidden style={{ flex: "none" }}>
      <path d="M2 10 H48 M40 3 L50 10 L40 17" fill="none" stroke="var(--pizarra-2)" strokeWidth={2} />
    </motion.svg>
  );
}

export function Coste({ hoja }) {
  return (
    <>
      <Titular>Así se hace hoy.</Titular>
      <div style={{ position: "absolute", top: 128, left: 0, right: 0, display: "flex", alignItems: "center", gap: 22 }}>
        <Paso delay={0.6} ancho={250}>
          <div style={{ height: 92, borderRadius: 4, overflow: "hidden", background: "#fff", boxShadow: "0 0 0 1px var(--linea)" }}>
            <Imagen src={local("plano-80v01.webp")} respaldo={gaSintetico} alt="Plano GA" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
          <div style={{ fontSize: 26, fontWeight: 400 }}>Plano GA</div>
        </Paso>
        <motion.span {...entra(0.8)} style={{ fontSize: 44, fontWeight: 200, color: "var(--pizarra-2)" }}>+</motion.span>
        <Paso delay={0.9} ancho={250}>
          <div style={{ height: 92, borderRadius: 4, overflow: "hidden", background: "#fff", boxShadow: "0 0 0 1px var(--linea)" }}><MiniTabla /></div>
          <div style={{ fontSize: 26, fontWeight: 400 }}>Hoja de datos</div>
        </Paso>
        <Flecha delay={1.2} />
        <Paso delay={1.3} ancho={560} style={{ background: "var(--agua-suave)" }}>
          <div style={{ fontSize: 30, fontWeight: 400, lineHeight: 1.2 }}>Un ingeniero los lee y vuelve a dibujar el equipo en 3D</div>
          <div className="turquesa" style={{ fontSize: 26, fontWeight: 400 }}>En cada revisión del plano</div>
        </Paso>
        <Flecha delay={1.6} />
        <Paso delay={1.7} ancho={250}>
          <svg viewBox="0 0 120 80" height={92} aria-hidden>
            <path d="M30 20 L60 6 L90 20 L90 58 L60 72 L30 58 Z M30 20 L60 34 L90 20 M60 34 V72" fill="none" stroke="var(--pizarra)" strokeWidth={2.5} strokeLinejoin="round" />
          </svg>
          <div style={{ fontSize: 26, fontWeight: 400 }}>Modelo 3D</div>
        </Paso>
      </div>
      <div style={{ position: "absolute", top: 380, left: 0, display: "flex", alignItems: "flex-end", gap: 48 }}>
        {hoja.factores.map((f, i) => (
          <motion.div key={f.texto} {...entra(2.2 + i * 0.3, { opacity: 0, y: 16 })} style={{ display: "flex", alignItems: "flex-end", gap: 48 }}>
            {i > 0 && <span style={{ fontSize: 52, fontWeight: 200, color: "var(--pizarra-2)", lineHeight: 1.3 }}>×</span>}
            <div>
              <div className="cifra turquesa" style={{ fontSize: 92 }}>{f.valor}</div>
              <div className="texto" style={{ fontSize: 25, marginTop: 6 }}>{f.texto}</div>
            </div>
          </motion.div>
        ))}
      </div>
      <div style={{ position: "absolute", top: 590, left: 0, right: 0 }}>
        <motion.div {...entra(3.2)} style={{ display: "flex", alignItems: "baseline", gap: 28 }}>
          <span className="cifra" style={{ fontSize: 140 }}>
            <Cuenta valor={hoja.horas.min} delay={3.2} />–<Cuenta valor={hoja.horas.max} delay={3.2} /> h
          </span>
          <span className="texto" style={{ fontSize: 34 }}>de redibujo por proyecto</span>
        </motion.div>
        <motion.div style={{ height: 4, background: "var(--agua)", marginTop: 20, transformOrigin: "left" }}
          {...(EXPORT ? { initial: false } : { initial: { scaleX: 0 }, animate: { scaleX: 1 }, transition: { delay: 3.4, duration: 1.4, ease } })} />
      </div>
    </>
  );
}

/* ---------- Entrada ---------- */
function MiniTabla() {
  return (
    <div style={{ display: "grid", gap: 7, padding: "6px 4px" }}>
      {Array.from({ length: 7 }, (_, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 7 }}>
          {[0, 1, 2].map((j) => <i key={j} style={{ height: 8, borderRadius: 2, background: i === 0 ? "var(--pizarra-2)" : "var(--linea)" }} />)}
        </div>
      ))}
    </div>
  );
}

export function Entrada({ hoja }) {
  const [sint, setSint] = useState(false);
  const t0 = 1.2;
  const columnas = "290px 410px 300px 1fr";
  return (
    <>
      <Titular style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Leemos el plano como quien lo dibuja.</Titular>
      <div style={{ position: "absolute", top: 130, left: 0, width: 360, display: "grid", gap: 22 }}>
        {hoja.documentos.map((d, i) => (
          <motion.div key={d.id} {...entra(0.5 + i * 0.3, { opacity: 0, x: -20 })}
            style={{ padding: 18, background: "var(--niebla)", borderRadius: 8 }}>
            <div style={{ height: d.id === "GA" ? 300 : 120, background: "#fff", borderRadius: 4, overflow: "hidden", display: "grid", alignItems: "center", boxShadow: "0 0 0 1px var(--linea)" }}>
              {d.id === "GA"
                ? <Imagen src={local("plano-80v01.webp")} respaldo={gaSintetico} onRespaldo={() => setSint(true)} alt="Plano GA" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                : <MiniTabla />}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginTop: 14 }}>
              <span style={{ fontSize: 28, fontWeight: 400 }}>{d.nombre}</span>
              <span className="texto" style={{ fontSize: 22 }}>{d.paginas}</span>
            </div>
          </motion.div>
        ))}
        {sint && <Sintetico>Plano de ejemplo sintético</Sintetico>}
      </div>
      <div style={{ position: "absolute", top: 130, left: 420, right: 0 }}>
        <motion.div {...entra(0.9)}
          style={{ display: "grid", gridTemplateColumns: columnas, gap: 24, paddingBottom: 12, borderBottom: "2px solid var(--agua)", fontSize: 22, fontWeight: 400, color: "var(--pizarra)" }}>
          <span>80V01, revisión 2</span><span>En el documento</span><span>Valor</span><span>Cómo</span>
        </motion.div>
        {hoja.lecturas.map((l, i) => (
          <motion.div key={l.dato} {...entra(t0 + i * 0.35, { opacity: 0, x: 24 })}
            style={{ display: "grid", gridTemplateColumns: columnas, gap: 24, alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--linea)" }}>
            <div>
              <div style={{ fontSize: 25, fontWeight: 400, lineHeight: 1.15 }}>{l.dato}</div>
              <div style={{ fontSize: 19, fontWeight: 400, color: "var(--pizarra-2)", marginTop: 4 }}>{l.doc}</div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {l.texto.map((t) => (
                <code key={t} style={{ fontFamily: "Consolas, 'Cascadia Mono', monospace", fontSize: 21, color: "var(--tinta)", background: "var(--niebla)", boxShadow: "inset 0 0 0 1px var(--linea)", borderRadius: 4, padding: "4px 10px" }}>{t}</code>
              ))}
            </div>
            <span className="turquesa" style={{ fontSize: 30, fontWeight: 400 }}>{l.valor}</span>
            <span style={{ justifySelf: "start", fontSize: 21, fontWeight: 400, padding: "5px 14px", borderRadius: 999,
              ...(l.revisar
                ? { color: "var(--pizarra)", boxShadow: "inset 0 0 0 1.5px var(--pizarra-2)" }
                : { color: "var(--turquesa)", background: "var(--agua-suave)" }) }}>
              {l.como}
            </span>
          </motion.div>
        ))}
        <motion.div {...entra(t0 + hoja.lecturas.length * 0.35 + 0.4)}
          style={{ marginTop: 22, display: "flex", alignItems: "center", gap: 16, fontSize: 28, fontWeight: 300 }}>
          <i style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--lima)" }} />
          {hoja.cierre}
        </motion.div>
      </div>
    </>
  );
}

/* ---------- Cita ---------- */
export function Cita({ hoja }) {
  const c = hoja.cita;
  const [sint, setSint] = useState(false);
  const ancho = 1728;
  const alto = Math.round((ancho * 156) / 1676);
  const cx = ((c.caja.left + c.caja.width / 2) / 100) * ancho;
  const yCaja = ((c.caja.top + c.caja.height) / 100) * alto;
  const filas = [
    ["Texto en el plano", `«${c.texto}»`],
    ["Documento", `${c.documento}, página ${c.pagina}`],
    ["Regla", c.regla],
    ["Confianza", c.confianza],
  ];
  return (
    <>
      <Titular>Cada cifra guarda su origen.</Titular>
      <div style={{ position: "absolute", top: 140, left: 0, width: ancho, height: alto }}>
        <Imagen src={local("cita-80v01.webp")} respaldo={gaSintetico} onRespaldo={() => setSint(true)} alt="Cota del plano"
          style={{ width: "100%", height: "100%", objectFit: sint ? "cover" : "fill" }} />
        <Barrido delay={0.5} duracion={1.4} />
        {!sint && (
          <motion.div {...(EXPORT ? { initial: false } : { initial: { opacity: 0, scale: 1.3 }, animate: { opacity: 1, scale: 1 }, transition: { delay: 1.6, duration: 0.5, ease } })}
            style={{ position: "absolute", left: `${c.caja.left}%`, top: `${c.caja.top}%`, width: `${c.caja.width}%`, height: `${c.caja.height}%`, outline: "3px solid var(--agua)", outlineOffset: 4, borderRadius: 3, background: "rgba(116,209,224,0.16)" }} />
        )}
      </div>
      {!sint && (
        <svg width={ancho} height={200} style={{ position: "absolute", top: 140, left: 0, overflow: "visible", pointerEvents: "none" }} aria-hidden>
          <motion.path d={`M${cx} ${yCaja + 8} V${alto + 80}`} stroke="var(--agua)" strokeWidth={2} fill="none"
            {...(EXPORT ? { initial: false } : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { delay: 2.0, duration: 0.5 } })} />
        </svg>
      )}
      <motion.div {...entra(2.4, { opacity: 0, y: 20 })}
        style={{ position: "absolute", top: 140 + alto + 80, left: cx - 330, width: 700, padding: "30px 36px", background: "var(--niebla)", borderRadius: 10, borderTop: "4px solid var(--agua)" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <span className="texto" style={{ fontSize: 24 }}>{c.campo}</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10, fontSize: 22, fontWeight: 400 }}>
            <i style={{ width: 12, height: 12, borderRadius: "50%", background: "var(--lima)" }} />Aceptada, revocable
          </span>
        </div>
        <div className="cifra turquesa" style={{ fontSize: 96, margin: "10px 0 16px" }}>{c.valor}</div>
        {filas.map(([k, v]) => (
          <div key={k} style={{ display: "grid", gridTemplateColumns: "220px 1fr", padding: "7px 0", borderTop: "1px solid var(--linea)", fontSize: 24 }}>
            <span className="texto" style={{ fontSize: 24 }}>{k}</span>
            <span style={{ fontWeight: 400 }}>{v}</span>
          </div>
        ))}
      </motion.div>
      <motion.div {...entra(3.2)} style={{ position: "absolute", top: 140 + alto + 100, left: cx + 470, right: 0 }}>
        <div className="cifra" style={{ fontSize: 150 }}><Cuenta valor={hoja.aceptados.valor} decimales={1} delay={3.2} /> %</div>
        <div className="texto" style={{ marginTop: 18, maxWidth: 560 }}>
          de lo que el sistema da por bueno solo coincide con lo que un ingeniero sacó a mano: <span className="fuerte">{hoja.aceptados.aciertos} de {hoja.aceptados.total} datos</span>.
        </div>
        <div className="texto" style={{ marginTop: 22, maxWidth: 520 }}>Lo dudoso va a revisión, primero lo que más impacta.</div>
      </motion.div>
      {sint && <div style={{ position: "absolute", top: 140 + alto + 20, left: 0 }}><Sintetico>Plano de ejemplo sintético</Sintetico></div>}
    </>
  );
}

/* ---------- El plano pasa a 3D ---------- */
export function Modelo({ hoja, onListo }) {
  const [sint, setSint] = useState(false);
  const grupos = [["plano", "En el plano"], ["lectura", "Nuestra lectura"]];
  return (
    <>
      <Titular>El plano pasa a 3D.</Titular>
      <Revela delay={0.4} duracion={1.6} style={{ position: "absolute", top: 120, left: 0, width: 960, height: 679, borderRadius: 8, overflow: "hidden", boxShadow: "0 0 0 1px var(--linea)" }}>
        <Imagen src={local("plano-marcado-80v01.webp")} respaldo={gaSintetico} onRespaldo={() => setSint(true)} alt="Plano marcado"
          style={{ width: "100%", height: "100%", objectFit: "contain", background: "#fff" }} />
      </Revela>
      <div style={{ position: "absolute", top: 120, left: 0, width: 960, height: 679, pointerEvents: "none" }}><Barrido delay={0.4} duracion={1.6} /></div>
      {sint && <div style={{ position: "absolute", top: 136, left: 16 }}><Sintetico>Ejemplo sintético</Sintetico></div>}
      <motion.div {...entra(1.6)} style={{ position: "absolute", top: 70, left: 1010, right: 0 }}>
        <Visor urls={[IFC_80V01]} respaldo={[ifcB]} ancho={718} alto={380} elevacion={22} zoom={1.7} onEstado={(e) => e.respaldo && setSint(true)} onListo={onListo} />
      </motion.div>
      <div style={{ position: "absolute", top: 450, left: 1010, right: 0, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28 }}>
        {grupos.map(([g, nombre], gi) => (
          <motion.div key={g} {...entra(2.0 + gi * 0.4)}>
            <div style={{ fontSize: 22, fontWeight: 400, color: "var(--pizarra)", marginBottom: 10 }}>{nombre}</div>
            {hoja.leyenda.filter((l) => l.de === g).map((l) => (
              <div key={l.texto} style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 23, lineHeight: 1.25, padding: "6px 0" }}>
                <i style={{ flex: "none", width: 26, height: 6, borderRadius: 3, background: l.color }} />{l.texto}
              </div>
            ))}
          </motion.div>
        ))}
      </div>
      <motion.div {...entra(2.8)} style={{ position: "absolute", top: 660, left: 1010, right: 0, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28, borderTop: "1px solid var(--linea-2)", paddingTop: 20 }}>
        {hoja.cifras.map((c) => (
          <div key={c.texto}>
            <div className="cifra turquesa" style={{ fontSize: 64 }}>{c.valor}</div>
            <div className="texto" style={{ fontSize: 22, marginTop: 6, lineHeight: 1.3 }}>{c.texto}</div>
          </div>
        ))}
      </motion.div>
    </>
  );
}

/* ---------- De A a B ---------- */
export function Cambio({ hoja, onListo }) {
  const [rev, setRev] = useState(EXPORT ? "B" : "A");
  return (
    <>
      <Titular style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Revisión B: el modelo se actualiza.</Titular>
      <div style={{ position: "absolute", top: 110, left: 0, width: 820, height: 640 }}>
        <Visor urls={[ifcA, ifcB]} modo="cambio" modificados={hoja.modificados} ancho={820} alto={640} elevacion={14}
          onEstado={(e) => e.revision && setRev(e.revision)} onListo={onListo} />
        <div style={{ position: "absolute", left: 0, top: 10, display: "flex", alignItems: "baseline", gap: 18 }}>
          <span className="texto" style={{ fontSize: 28 }}>Revisión</span>
          <span className="cifra" style={{ fontSize: 96, color: rev === "B" ? "var(--turquesa)" : "var(--tinta)", transition: "color .4s" }}>{rev}</span>
        </div>
        <div style={{ position: "absolute", left: 0, bottom: 0, display: "flex", flexWrap: "wrap", gap: 18, alignItems: "center" }}>
          <Sintetico>{hoja.sintetico}</Sintetico>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10, fontSize: 22 }}><i style={{ width: 16, height: 16, borderRadius: 4, background: "var(--agua)" }} />Pieza nueva</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10, fontSize: 22 }}><i style={{ width: 16, height: 16, borderRadius: 4, background: "var(--turquesa)" }} />Pieza que cambia</span>
        </div>
      </div>
      <div style={{ position: "absolute", top: 130, left: 900, right: 0 }}>
        <motion.div {...entra(0.6)} style={{ fontSize: 28, fontWeight: 400, paddingBottom: 12, borderBottom: "2px solid var(--agua)" }}>Qué cambia de A a B en el ejemplo</motion.div>
        {hoja.cambios.map((c, i) => (
          <motion.div key={c.campo} {...entra(0.8 + i * 0.25, { opacity: 0, x: 24 })}
            style={{ display: "grid", gridTemplateColumns: "1fr 290px 130px", alignItems: "baseline", gap: 16, padding: "14px 0", borderBottom: "1px solid var(--linea)" }}>
            <span className="texto" style={{ fontSize: 26 }}>{c.campo}</span>
            <span style={{ fontSize: 28, fontWeight: 300 }}>{c.antes} <span style={{ color: "var(--pizarra-2)" }}>→</span> <span style={{ fontWeight: 400 }}>{c.despues}</span></span>
            <span className="turquesa" style={{ justifySelf: "end", fontSize: 26, fontWeight: 400 }}>{c.delta}</span>
          </motion.div>
        ))}
        <motion.div {...entra(2.2)} style={{ marginTop: 40 }}>
          <div style={{ fontSize: 28, fontWeight: 400, paddingBottom: 12, borderBottom: "2px solid var(--agua)" }}>En el 80V01 real, de la revisión 1 a la 2</div>
          {hoja.real.map((c) => (
            <div key={c.campo} style={{ display: "grid", gridTemplateColumns: "1fr 380px", padding: "14px 0", borderBottom: "1px solid var(--linea)", alignItems: "baseline" }}>
              <span className="texto" style={{ fontSize: 26 }}>{c.campo}</span>
              <span style={{ fontSize: 28 }}>{c.antes} <span style={{ color: "var(--pizarra-2)" }}>→</span> <span style={{ fontWeight: 400 }}>{c.despues}</span></span>
            </div>
          ))}
        </motion.div>
        <motion.div {...entra(2.8)} className="texto" style={{ marginTop: 30, fontSize: 28 }}>
          Cada pieza conserva su identidad: es el mismo modelo, actualizado. Los cambios se abren en vuestro visor.
        </motion.div>
      </div>
    </>
  );
}

/* ---------- Arquitectura ---------- */
export function Arquitectura({ hoja }) {
  const n = hoja.lectores.length;
  const x0 = 60;
  const paso = 205;
  const y = 230;
  const cx = (i) => x0 + i * paso;
  return (
    <>
      <Titular>Reglas primero. Un modelo solo si falta algo.</Titular>
      <svg width={1728} height={560} style={{ position: "absolute", top: 210, left: 0, overflow: "visible" }}>
        <line x1={cx(0)} y1={y} x2={cx(n - 1)} y2={y} stroke="var(--linea-2)" strokeWidth={2} />
        <motion.line x1={cx(0)} y1={y} x2={cx(n - 1)} y2={y} stroke="var(--agua)" strokeWidth={4} style={{ transformOrigin: `${cx(0)}px ${y}px` }}
          {...(EXPORT ? { initial: false } : { initial: { scaleX: 0 }, animate: { scaleX: 1 }, transition: { delay: 0.6, duration: 1.4, ease } })} />
        {hoja.lectores.map((l, i) => {
          const caso = hoja.casos.find((c) => c.lector === i);
          const k = hoja.casos.indexOf(caso);
          const t = 1.6 + k * 0.9;
          return (
            <g key={l}>
              <circle cx={cx(i)} cy={y} r={16} fill="#fff" stroke={i === n - 1 ? "var(--turquesa)" : "var(--pizarra-2)"} strokeWidth={3} />
              <text x={cx(i)} y={y - 46} textAnchor="middle" fill="var(--tinta)" style={{ font: `${i === n - 1 ? 400 : 300} 27px var(--font)` }}>{l}</text>
              {caso && (
                <motion.g {...(EXPORT ? { initial: false } : { initial: { opacity: 0, y: -14 }, animate: { opacity: 1, y: 0 }, transition: { delay: t, duration: 0.5 } })}>
                  <circle cx={cx(i)} cy={y} r={9} fill="var(--agua)" />
                  <line x1={cx(i)} y1={y + 22} x2={cx(i)} y2={y + 76} stroke="var(--agua)" strokeWidth={2} />
                  <text x={cx(i)} y={y + 120} textAnchor="middle" fill="var(--turquesa)" style={{ font: "300 40px var(--font)" }}>{caso.cifra}</text>
                </motion.g>
              )}
            </g>
          );
        })}
        <line x1={cx(n - 1) + 30} y1={y} x2={1330} y2={y} stroke="var(--linea-2)" strokeWidth={2} />
        <path d={`M1340 ${y} l-14 -7 v14 Z`} fill="var(--pizarra-2)" />
      </svg>
      <motion.div {...entra(2.4)} style={{ position: "absolute", top: 210 + y - 92, left: 1370, right: 0 }}>
        {hoja.salida.map((s) => <div key={s} style={{ fontSize: 30, fontWeight: 300, padding: "6px 0" }}>{s}</div>)}
      </motion.div>
      <motion.div {...entra(3.2)} style={{ position: "absolute", top: 660, left: 0, display: "flex", alignItems: "center", gap: 16, fontSize: 32, fontWeight: 300 }}>
        <i style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--lima)" }} />
        Al final, una persona aprueba con su nombre. Si cambia un dato, la aprobación cae.
      </motion.div>
    </>
  );
}

/* ---------- Anexo: modelos ---------- */
export function Modelos({ hoja }) {
  return (
    <>
      <Titular>Por qué estos modelos.</Titular>
      <Benchmark id={hoja.tarea} />
    </>
  );
}

/* ---------- Demo en vídeo, a toda la lámina ---------- */
export function Demo({ hoja }) {
  const ref = useRef(null);
  const [falta, setFalta] = useState(false);
  useEffect(() => {
    const v = ref.current;
    if (!v || EXPORT) return;
    // Con sonido si el navegador lo deja (al pasar de hoja con el mando ya hubo interacción);
    // si no, en silencio, para que arranque igualmente.
    v.muted = false;
    v.play().catch(() => { v.muted = true; v.play().catch(() => {}); });
  }, []);
  return (
    <div style={{ position: "absolute", left: -96, top: -150, width: 1920, height: 1080, background: "#000", zIndex: 5 }}>
      {!falta && (
        <video ref={ref} src={`${import.meta.env.BASE_URL}${hoja.video}`} playsInline preload="auto"
          onError={() => setFalta(true)}
          style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
      )}
      {falta && (
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center", color: "#fff", fontSize: 28 }}>
          Falta el vídeo de la demo: copia el .mp4 en pitch/track/public/{hoja.video}
        </div>
      )}
    </div>
  );
}

/* ---------- Cierre ---------- */
export function Gracias() {
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      <h1 className="titular barrido" style={{ display: "inline-block", fontSize: 200, lineHeight: 1 }}>Gracias</h1>
      <motion.div {...entra(1.0)} style={{ marginTop: 110, display: "flex", alignItems: "center", gap: 64 }}>
        <LogoTrazIA style={{ height: 130, width: "auto" }} />
        <span style={{ width: 1, height: 80, background: "var(--linea-2)" }} />
        <LogoTR color="var(--pizarra)" style={{ height: 84, width: "auto" }} />
        <span style={{ width: 1, height: 80, background: "var(--linea-2)" }} />
        <LogoMultiplica color="var(--pizarra)" style={{ height: 38, width: "auto" }} />
      </motion.div>
    </div>
  );
}

export const componentes = {
  demo: Demo,
  gracias: Gracias,
  portada: Portada,
  coste: Coste,
  entrada: Entrada,
  cita: Cita,
  modelo: Modelo,
  cambio: Cambio,
  arquitectura: Arquitectura,
  futuro: Futuro,
  "modelos-vision": Modelos,
  "modelos-texto": Modelos,
};

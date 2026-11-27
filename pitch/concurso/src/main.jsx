import "@fontsource-variable/archivo/standard.css";
import "./styles.css";
import { motion } from "motion/react";
import { StrictMode, useCallback, useEffect, useLayoutEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { LogoTR } from "./brand.jsx";
import { deck, hojas, totalSegundos } from "./content.js";
import { EXPORT } from "./modo.js";
import { componentes } from "./slides.jsx";

const params = new URLSearchParams(window.location.search);
const inicial = Math.min(hojas.length - 1, Math.max(0, (parseInt(params.get("hoja"), 10) || 1) - 1));
if (EXPORT) document.body.classList.add("export");

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function useEscala() {
  const [k, setK] = useState(1);
  useLayoutEffect(() => {
    if (EXPORT) return undefined;
    const fit = () => setK(Math.min(window.innerWidth / 1920, window.innerHeight / 1080));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  return k;
}

function Cajetin({ n, hoja }) {
  return (
    <div className="cajetin">
      <div><small>Proyecto</small><b>{deck.proyecto}</b></div>
      <div><small>Cliente</small><LogoTR style={{ height: 34 }} /></div>
      <div><small>Lámina</small><b>{hoja.titulo}</b></div>
      <div><small>Hoja</small><b>{n + 1} de {hojas.length}</b></div>
      <div><small>Rev.</small><b>{deck.revision}</b></div>
    </div>
  );
}

function App() {
  const [i, setI] = useState(inicial);
  const [notas, setNotas] = useState(false);
  const [reloj, setReloj] = useState({ corriendo: false, base: 0, desde: 0 });
  const [ahora, setAhora] = useState(0);
  const [entrada, setEntrada] = useState(0);
  const k = useEscala();
  const hoja = hojas[i];
  const Slide = componentes[hoja.id];

  const ir = useCallback((d) => setI((x) => Math.min(hojas.length - 1, Math.max(0, x + d))), []);

  useEffect(() => {
    setEntrada(performance.now());
    if (!EXPORT) {
      const u = new URL(window.location.href);
      u.searchParams.set("hoja", String(i + 1));
      window.history.replaceState(null, "", u);
    }
  }, [i]);

  useEffect(() => {
    const onKey = (e) => {
      if (["ArrowRight", "PageDown", " ", "Enter"].includes(e.key)) { e.preventDefault(); ir(1); }
      else if (["ArrowLeft", "PageUp", "Backspace"].includes(e.key)) { e.preventDefault(); ir(-1); }
      else if (e.key === "Home") { setI(0); setReloj({ corriendo: false, base: 0, desde: 0 }); }
      else if (e.key === "End") setI(hojas.length - 1);
      else if (e.key === "n" || e.key === "N") setNotas((v) => !v);
      else if (e.key === "f" || e.key === "F") {
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen();
        setReloj((r) => (r.corriendo ? r : { corriendo: true, base: r.base, desde: performance.now() }));
      } else if (e.key === "t" || e.key === "T") {
        setReloj((r) => r.corriendo
          ? { corriendo: false, base: r.base + (performance.now() - r.desde) / 1000, desde: 0 }
          : { corriendo: true, base: r.base, desde: performance.now() });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ir]);

  useEffect(() => {
    if (!reloj.corriendo) return undefined;
    const id = setInterval(() => setAhora(performance.now()), 250);
    return () => clearInterval(id);
  }, [reloj.corriendo]);

  const transcurrido = reloj.base + (reloj.corriendo ? (Math.max(ahora, reloj.desde) - reloj.desde) / 1000 : 0);
  const objetivo = hojas.slice(0, i + 1).reduce((s, h) => s + h.segundos, 0);
  const enHoja = reloj.corriendo ? Math.max(0, (ahora - entrada) / 1000) : 0;

  const listo = useCallback(() => { document.body.dataset.ifc = "1"; }, []);
  useEffect(() => {
    if (hoja.id !== "portada") document.body.dataset.ifc = "1";
    document.fonts.ready.then(() => { document.body.dataset.fuentes = "1"; });
  }, [hoja.id]);

  return (
    <div className="escenario" onClick={(e) => { if (!EXPORT && e.target.closest(".lamina")) ir(e.clientX > window.innerWidth / 2 ? 1 : -1); }}>
      <div className="lamina" style={EXPORT ? undefined : { position: "absolute", left: "50%", top: "50%", transform: `translate(-50%, -50%) scale(${k})` }}>
        <div className="marco" />
        <div key={i} className="contenido lamina-in">
          <Slide hoja={hoja} onListo={listo} />
        </div>
        {!hoja.sinCajetin && <Cajetin n={i} hoja={hoja} />}
        {!EXPORT && reloj.corriendo && (
          <>
            <motion.div key={`r${i}`} className="ritmo" style={{ width: 1856 }}
              initial={{ scaleX: 0 }} animate={{ scaleX: Math.min(1, enHoja / hoja.segundos) }} transition={{ duration: 0.25, ease: "linear" }} />
            <div className={`reloj${transcurrido > objetivo ? " tarde" : ""}`}>
              {mmss(transcurrido)} de {mmss(totalSegundos)}
            </div>
          </>
        )}
        {!EXPORT && notas && (
          <div className="notas">
            <small>Guion de la hoja {i + 1}, unos {hoja.segundos} s. Acaba en {mmss(objetivo)}.</small>
            {hoja.notas}
          </div>
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode><App /></StrictMode>);

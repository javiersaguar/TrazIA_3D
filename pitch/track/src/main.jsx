import "@fontsource/kanit/200.css";
import "@fontsource/kanit/300.css";
import "@fontsource/kanit/400.css";
import "@fontsource/kanit/500.css";
import "./styles.css";
import { motion } from "motion/react";
import { StrictMode, useCallback, useEffect, useLayoutEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { WordmarkTrazIA } from "../../concurso/src/brand.jsx";
import { capitulos, hojas, totalSegundos } from "./content.js";
import { EXPORT } from "./modo.js";
import { componentes } from "./slides.jsx";

const CON_VISOR = new Set(["portada", "modelo", "cambio"]);
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

/** Los seis bloques del enunciado: dónde va la charla. */
function Capitulos({ i }) {
  const hoja = hojas[i];
  const activo = capitulos.findIndex((c) => c.id === hoja.capitulo);
  return (
    <div className="capitulos">
      {capitulos.map((c, k) => {
        const delCap = hojas.filter((h) => h.capitulo === c.id);
        const dentro = delCap.findIndex((h) => h === hoja);
        const lleno = k < activo ? 1 : k > activo ? 0 : (dentro + 1) / delCap.length;
        return (
          <div key={c.id} className={`capitulo${k === activo ? " activo" : ""}`}>
            <span>{c.nombre}</span>
            <div className="pista">
              <motion.i initial={false} animate={{ scaleX: lleno }} transition={{ duration: EXPORT ? 0 : 0.6, ease: [0.65, 0, 0.35, 1] }} />
            </div>
          </div>
        );
      })}
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

  // El reloj arranca solo al pasar la primera hoja (o con F o T).
  const ir = useCallback((d) => {
    setI((x) => Math.min(hojas.length - 1, Math.max(0, x + d)));
    setReloj((r) => (r.corriendo || r.base ? r : { corriendo: true, base: 0, desde: performance.now() }));
  }, []);

  useEffect(() => {
    setEntrada(performance.now());
    if (EXPORT) return;
    const u = new URL(window.location.href);
    u.searchParams.set("hoja", String(i + 1));
    window.history.replaceState(null, "", u);
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
  const enHoja = reloj.corriendo ? Math.max(0, (Math.max(ahora, entrada) - entrada) / 1000) : 0;

  const listo = useCallback(() => { document.body.dataset.visor = "1"; }, []);
  useEffect(() => {
    if (!CON_VISOR.has(hoja.id)) document.body.dataset.visor = "1";
    document.fonts.ready.then(() => { document.body.dataset.fuentes = "1"; });
  }, [hoja.id]);

  return (
    <div className="escenario" onClick={(e) => { if (!EXPORT && e.target.closest(".lamina")) ir(e.clientX > window.innerWidth / 2 ? 1 : -1); }}>
      <div className="lamina" style={EXPORT ? undefined : { position: "absolute", left: "50%", top: "50%", transform: `translate(-50%, -50%) scale(${k})` }}>
        {!hoja.sinMarca && <WordmarkTrazIA className="marca" />}
        <div key={i} className="contenido lamina-in">
          <Slide hoja={hoja} onListo={listo} />
        </div>
        {hoja.capitulo && <Capitulos i={i} />}
        {!EXPORT && (
          <div className="reloj">
            <span className={transcurrido > objetivo ? "tarde" : undefined}>{mmss(transcurrido)} de {mmss(totalSegundos)}</span>
            {hoja.segundos > 0 && (
              <span className={enHoja > hoja.segundos ? "tarde" : undefined}> · hoja {mmss(enHoja)} de {mmss(hoja.segundos)}</span>
            )}
          </div>
        )}
        {!EXPORT && notas && (
          <div className="notas" style={{ whiteSpace: "pre-line" }}>
            <small>Hoja {i + 1}{hoja.voz ? `, habla ${hoja.voz}` : ""}, unos {hoja.segundos} s. Acaba en {mmss(objetivo)}.</small>
            {hoja.notas}
          </div>
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode><App /></StrictMode>);

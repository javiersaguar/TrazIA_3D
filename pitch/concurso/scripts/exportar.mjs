// Exporta el pitch a PowerPoint: compila, captura cada hoja a 1920 × 1080 en su estado final
// y escribe salida/TrazIA-3D-pitch.pptx con el guion en las notas del orador.
// Cada hoja lleva además su animación de entrada grabada en vídeo (scripts/animaciones.mjs):
// arranca sola al entrar en la hoja y se queda en el último fotograma. Debajo queda la captura
// final, que es lo que se ve si el programa no reproduce vídeo.
// Uso: corepack pnpm@10.18.0 export   (necesita Google Chrome; PW_CHANNEL=msedge para Edge)
//      --sin-animaciones: solo imágenes, como antes.
//      --reusar-animaciones: monta el .pptx con los vídeos ya grabados en salida/animaciones.
import { spawn, execSync } from "node:child_process";
import fs, { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { chromium } from "playwright-core";
import PptxGenJS from "pptxgenjs";
import { deck, hojas } from "../src/content.js";
import { grabarHoja } from "./animaciones.mjs";

// jszip llega con pptxgenjs: sirve para retocar el XML de las diapositivas.
const require = createRequire(import.meta.url);
const JSZip = require(require.resolve("jszip", { paths: [dirname(require.resolve("pptxgenjs"))] }));
const conAnimaciones = !process.argv.includes("--sin-animaciones");
const reusar = process.argv.includes("--reusar-animaciones"); // no vuelve a grabar los vídeos que ya están

const raiz = resolve(import.meta.dirname, "..");
const salida = resolve(raiz, "salida");
mkdirSync(salida, { recursive: true });
const soloCapturas = process.argv.includes("--capturas");

// Vite directamente: en Windows el envoltorio de corepack puede cerrarse tras compilar.
const vite = resolve(raiz, "node_modules/vite/bin/vite.js");
if (!process.argv.includes("--sin-build")) execSync(`"${process.execPath}" "${vite}" build --logLevel warn`, { cwd: raiz, stdio: "inherit" });

const puerto = Number(process.env.PUERTO_EXPORT ?? 4193);
const server = spawn(process.execPath, [vite, "preview", "--port", String(puerto), "--strictPort", "--host", "127.0.0.1"], { cwd: raiz, stdio: "pipe" });
await new Promise((ok, ko) => {
  server.stdout.on("data", (d) => { if (String(d).includes(String(puerto))) ok(); });
  server.on("exit", (c) => ko(new Error(`vite preview terminó con ${c}`)));
});

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "chrome", args: ["--use-angle=default", "--ignore-gpu-blocklist"] });
const capturas = [];
const videos = [];
const propios = [];
try {
  for (let n = 1; n <= hojas.length; n++) {
    // Una página por hoja: el contexto WebGL de la portada no se arrastra a las siguientes.
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    page.on("pageerror", (e) => console.error(`Error en la hoja ${n}:`, e.message));
    await page.goto(`http://127.0.0.1:${puerto}/?export&hoja=${n}`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.body.dataset.fuentes === "1" && document.body.dataset.ifc === "1" && document.body.dataset.video !== "cargando", null, { timeout: 60_000 });
    await page.waitForTimeout(400);
    const archivo = resolve(salida, `hoja-${String(n).padStart(2, "0")}.png`);
    await page.screenshot({ path: archivo });
    capturas.push(archivo);
    // Hoja con un vídeo propio (la interfaz): va al .pptx tal cual, con su primer fotograma de portada.
    const h = hojas[n - 1];
    if (h.video) {
      const estado = await page.evaluate(() => ({ v: document.body.dataset.video, ms: Number(document.body.dataset.videoMs) }));
      if (estado.v === "listo") propios[n - 1] = { video: resolve(raiz, "public", h.video), portada: `data:image/png;base64,${fs.readFileSync(archivo).toString("base64")}`, ms: estado.ms };
      else console.warn(`Hoja ${n}: falta public/${h.video}; sale sin vídeo.`);
    }
    await page.close();
    console.log(`Hoja ${n}: ${hojas[n - 1].titulo}`);
  }
  if (conAnimaciones && !soloCapturas) {
    const dir = resolve(salida, "animaciones");
    mkdirSync(dir, { recursive: true });
    for (let n = 1; n <= hojas.length; n++) {
      if (hojas[n - 1].video) {
        videos.push(propios[n - 1]);
        continue;
      }
      const destino = resolve(dir, `hoja-${String(n).padStart(2, "0")}.mp4`);
      if (reusar && fs.existsSync(`${destino}.json`)) {
        videos.push(JSON.parse(fs.readFileSync(`${destino}.json`, "utf8")));
        continue;
      }
      videos.push(await grabarHoja({ browser, base: `http://127.0.0.1:${puerto}`, n, total: hojas.length, id: hojas[n - 1].id, destino }));
      fs.writeFileSync(`${destino}.json`, JSON.stringify(videos[n - 1]));
      console.log(`Animación ${n}: ${(videos[n - 1].ms / 1000).toFixed(1)} s`);
    }
  }
} finally {
  await browser.close();
  server.kill();
}

if (!soloCapturas) {
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.title = `${deck.proyecto} · ${deck.reto}`;
  pptx.company = deck.proyecto;
  hojas.forEach((h, k) => {
    const s = pptx.addSlide();
    s.background = { color: "0F1317" };
    s.addImage({ path: capturas[k], x: 0, y: 0, w: 13.333, h: 7.5 });
    if (videos[k]) s.addMedia({ type: "video", path: videos[k].video, cover: videos[k].portada, x: 0, y: 0, w: 13.333, h: 7.5 });
    s.addNotes(`${h.titulo} · ${h.segundos} s\n\n${h.notas}`);
  });
  // Si el .pptx está abierto en PowerPoint, se escribe una copia con la hora en el nombre.
  let destino = resolve(salida, "TrazIA-3D-pitch.pptx");
  try {
    fs.closeSync(fs.openSync(destino, "a"));
  } catch (e) {
    if (e.code !== "EBUSY" && e.code !== "EPERM") throw e;
    const hora = new Date().toTimeString().slice(0, 5).replace(":", "");
    destino = resolve(salida, `TrazIA-3D-pitch-${hora}.pptx`);
    console.log("El .pptx está abierto: se escribe una copia.");
  }
  const zip = await JSZip.loadAsync(await pptx.write({ outputType: "nodebuffer" }));
  for (let k = 0; k < hojas.length; k++) {
    const ruta = `ppt/slides/slide${k + 1}.xml`;
    zip.file(ruta, animarDiapositiva(await zip.file(ruta).async("string"), videos[k]?.ms));
  }
  // Sin la barra de controles al pasar el ratón por un vídeo («Mostrar controles multimedia»):
  // al presentar, las hojas se ven como diapositivas, no como vídeos.
  if (videos.length) {
    zip.file("ppt/presProps.xml",
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n` +
      `<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">` +
      `<p:showPr showNarration="1"><p:sldAll/><p:penClr><a:prstClr val="red"/></p:penClr>` +
      `<p:extLst><p:ext uri="{2FDB2607-1784-4EEB-B798-7EB5836EED8A}"><p14:showMediaCtrls xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" val="0"/></p:ext></p:extLst>` +
      `</p:showPr></p:presentationPr>`);
  }
  fs.writeFileSync(destino, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log(`PowerPoint: ${destino}`);
}

/**
 * Fundido corto al entrar en la diapositiva y, si lleva vídeo, que arranque solo (lo que PowerPoint
 * escribe con «Iniciar: automáticamente»). Se le quita el clic de reproducir/pausar para que un clic
 * sobre la lámina pase de hoja, como en la presentación web.
 */
function animarDiapositiva(xml, ms) {
  let timing = "";
  if (ms) {
    const m = xml.match(/<p:cNvPr id="(\d+)" name="([^"]*)"><a:hlinkClick r:id="" action="ppaction:\/\/media"\/><\/p:cNvPr>/);
    if (!m) throw new Error("No encuentro el vídeo en la diapositiva");
    xml = xml.replace(m[0], `<p:cNvPr id="${m[1]}" name="${m[2]}"/>`);
    const id = m[1];
    timing =
      `<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>` +
      `<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>` +
      `<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>` +
      `<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>` +
      `<p:par><p:cTn id="5" presetID="1" presetClass="mediacall" presetSubtype="0" fill="hold" nodeType="afterEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>` +
      `<p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr><p:cTn id="6" dur="${ms}" fill="hold"/><p:tgtEl><p:spTgt spid="${id}"/></p:tgtEl></p:cBhvr></p:cmd>` +
      `</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>` +
      `</p:childTnLst></p:cTn>` +
      `<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>` +
      `<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>` +
      `<p:video><p:cMediaNode vol="80000"><p:cTn id="7" fill="hold" display="0"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="${id}"/></p:tgtEl></p:cMediaNode></p:video>` +
      `</p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>`;
  }
  const transicion = `<p:transition spd="fast"><p:fade/></p:transition>`;
  const fin = xml.includes("<p:extLst>") && xml.lastIndexOf("<p:extLst>") > xml.lastIndexOf("</p:cSld>") ? xml.lastIndexOf("<p:extLst>") : xml.lastIndexOf("</p:sld>");
  return xml.slice(0, fin) + transicion + timing + xml.slice(fin);
}

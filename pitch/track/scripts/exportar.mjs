// Exporta el pitch del track a PowerPoint: compila, captura cada hoja a 1920 × 1080 en su estado final
// y escribe salida/TrazIA-3D-track.pptx con el guion en las notas del orador.
// Uso: corepack pnpm@10.18.0 export   (necesita Google Chrome; PW_CHANNEL=msedge para Edge)
import { spawn, execSync } from "node:child_process";
import fs, { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright-core";
import PptxGenJS from "pptxgenjs";
import { deck, hojas } from "../src/content.js";

const raiz = resolve(import.meta.dirname, "..");
const salida = resolve(raiz, "salida");
mkdirSync(salida, { recursive: true });
const soloCapturas = process.argv.includes("--capturas");

// Vite directamente: en Windows el envoltorio de corepack puede cerrarse tras compilar.
const vite = resolve(raiz, "node_modules/vite/bin/vite.js");
if (!process.argv.includes("--sin-build")) execSync(`"${process.execPath}" "${vite}" build --logLevel warn`, { cwd: raiz, stdio: "inherit" });

const puerto = Number(process.env.PUERTO_EXPORT ?? 4196);
const server = spawn(process.execPath, [vite, "preview", "--port", String(puerto), "--strictPort", "--host", "127.0.0.1"], { cwd: raiz, stdio: "pipe" });
await new Promise((ok, ko) => {
  server.stdout.on("data", (d) => { if (String(d).includes(String(puerto))) ok(); });
  server.on("exit", (c) => ko(new Error(`vite preview terminó con ${c}`)));
});

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "chrome", args: ["--use-angle=default", "--ignore-gpu-blocklist"] });
const capturas = [];
try {
  for (let n = 1; n <= hojas.length; n++) {
    // Una página por hoja: el contexto WebGL de la portada no se arrastra a las siguientes.
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    page.on("pageerror", (e) => console.error(`Error en la hoja ${n}:`, e.message));
    await page.goto(`http://127.0.0.1:${puerto}/?export&hoja=${n}`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.body.dataset.fuentes === "1" && document.body.dataset.visor === "1", null, { timeout: 60_000 });
    await page.waitForTimeout(400);
    const archivo = resolve(salida, `hoja-${String(n).padStart(2, "0")}.png`);
    await page.screenshot({ path: archivo });
    capturas.push(archivo);
    await page.close();
    console.log(`Hoja ${n}: ${hojas[n - 1].titulo}`);
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
    s.addNotes(`${h.titulo} · ${h.segundos} s\n\n${h.notas}`);
  });
  // Si el .pptx está abierto en PowerPoint, se escribe una copia con la hora en el nombre.
  let destino = resolve(salida, "TrazIA-3D-track.pptx");
  try {
    fs.closeSync(fs.openSync(destino, "a"));
  } catch (e) {
    if (e.code !== "EBUSY" && e.code !== "EPERM") throw e;
    const hora = new Date().toTimeString().slice(0, 5).replace(":", "");
    destino = resolve(salida, `TrazIA-3D-track-${hora}.pptx`);
    console.log("El .pptx está abierto: se escribe una copia.");
  }
  await pptx.writeFile({ fileName: destino });
  console.log(`PowerPoint: ${destino}`);
}

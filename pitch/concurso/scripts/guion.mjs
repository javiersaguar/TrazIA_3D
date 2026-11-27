// Guion del pitch en PDF, generado desde src/content.js y las capturas de salida/.
// Uso: corepack pnpm@10.18.0 guion   (después de exportar, para que las miniaturas estén al día)
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { deck, hojas, totalSegundos } from "../src/content.js";

const raiz = resolve(import.meta.dirname, "..");
const salida = resolve(raiz, "salida");
mkdirSync(salida, { recursive: true });

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const fuente = pathToFileURL(resolve(raiz, "node_modules/@fontsource-variable/archivo/files/archivo-latin-standard-normal.woff2")).href;

// Datos que se dicen o se pueden preguntar, y que no aparecen en la lámina.
function datos(h) {
  const d = [];
  if (h.fuente) d.push(h.fuente);
  const num = (k) => new Intl.NumberFormat("es-ES", { minimumFractionDigits: k.decimales ?? 0, maximumFractionDigits: k.decimales ?? 0 }).format(k.valor);
  for (const k of h.kpis ?? []) if (k.nota) d.push(`${num(k)}${k.sufijo}: ${k.nota.replace(/^./, (c) => c.toLowerCase())}.`);
  for (const g of [h.calidad, h.dispersion].filter(Boolean)) if (g.medida) d.push(`${g.titulo}: ${g.medida}`);
  return d;
}

let t = 0;
const filas = hojas.map((h, i) => {
  const desde = t;
  t += h.segundos;
  return { h, i, desde, hasta: t };
});

const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Guion · ${esc(deck.proyecto)}</title>
<style>
@font-face { font-family: Archivo; src: url(${fuente}) format("woff2-variations"); font-weight: 100 900; font-stretch: 62% 125%; }
@page { size: A4; margin: 16mm 16mm 18mm; }
* { box-sizing: border-box; }
body { font-family: Archivo, system-ui, sans-serif; color: #16191d; font-size: 10.5pt; line-height: 1.5; margin: 0; }
h1 { font-size: 26pt; font-stretch: 112%; font-weight: 650; letter-spacing: -0.02em; line-height: 1.05; margin: 0 0 4mm; }
.intro { color: #4a525b; max-width: 150mm; margin: 0 0 7mm; }
table { border-collapse: collapse; width: 100%; margin-bottom: 4mm; }
th, td { text-align: left; padding: 1.6mm 2mm; border-bottom: 0.3mm solid #d9dde1; vertical-align: top; }
th { font-weight: 600; color: #4a525b; font-size: 9pt; }
td.n { font-variant-numeric: tabular-nums; white-space: nowrap; }
.teclas { color: #4a525b; font-size: 9.5pt; }
section { break-inside: avoid; border-top: 0.6mm solid #16191d; padding-top: 4mm; margin-top: 7mm; }
.cab { display: flex; justify-content: space-between; align-items: baseline; gap: 6mm; }
h2 { font-size: 15pt; font-stretch: 110%; font-weight: 640; margin: 0; }
.tiempo { font-variant-numeric: tabular-nums; color: #c2382d; font-weight: 600; white-space: nowrap; }
.cuerpo { display: grid; grid-template-columns: 62mm 1fr; gap: 6mm; margin-top: 3mm; }
img { width: 62mm; display: block; border: 0.3mm solid #d9dde1; }
.dice { font-size: 11.5pt; line-height: 1.55; margin: 0; }
.datos { margin: 3mm 0 0; padding: 0; list-style: none; color: #4a525b; font-size: 9pt; line-height: 1.45; }
.datos li { margin-top: 1.4mm; padding-left: 3mm; border-left: 0.5mm solid #ff5a4e; }
.datos b { color: #16191d; font-weight: 600; }
</style></head><body>
<h1>Guion del pitch<br>${esc(deck.proyecto)} en ${mmss(totalSegundos)}</h1>
<p class="intro">${esc(deck.reto)}, ${esc(deck.evento)}. Lo que va en cada hoja, el texto que se dice y los datos que no salen en la lámina, por si el jurado pregunta. Generado desde la presentación: si cambia una cifra allí, cambia aquí.</p>
<table>
<thead><tr><th>Hoja</th><th>Lámina</th><th>Empieza</th><th>Acaba</th><th>Duración</th></tr></thead>
<tbody>${filas.map(({ h, i, desde, hasta }) => `<tr><td class="n">${i + 1}</td><td>${esc(h.titulo)}</td><td class="n">${mmss(desde)}</td><td class="n">${mmss(hasta)}</td><td class="n">${h.segundos} s</td></tr>`).join("")}</tbody>
</table>
<p class="teclas">En la presentación: F, pantalla completa y reloj. Flechas o clic, avanzar y retroceder. N, el guion de la hoja. Inicio, volver al principio.</p>
${filas.map(({ h, i, desde, hasta }) => {
  const png = resolve(salida, `hoja-${String(i + 1).padStart(2, "0")}.png`);
  const d = datos(h);
  return `<section>
  <div class="cab"><h2>${i + 1}. ${esc(h.titulo)}</h2><span class="tiempo">${mmss(desde)}–${mmss(hasta)} · ${h.segundos} s</span></div>
  <div class="cuerpo">
    ${existsSync(png) ? `<img src="${pathToFileURL(png).href}" alt="Hoja ${i + 1}">` : "<div></div>"}
    <div>
      <p class="dice">${esc(h.notas)}</p>
      ${d.length ? `<ul class="datos"><li><b>Datos y fuentes</b></li>${d.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    </div>
  </div>
</section>`;
}).join("\n")}
</body></html>`;

const archivoHtml = resolve(salida, "guion.html");
writeFileSync(archivoHtml, html);
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? "chrome" });
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(archivoHtml).href);
  await page.evaluate(() => document.fonts.ready);
  let destino = resolve(salida, "TrazIA-3D-guion.pdf");
  try {
    if (existsSync(destino)) writeFileSync(destino, readFileSync(destino));
  } catch {
    destino = resolve(salida, `TrazIA-3D-guion-${Date.now()}.pdf`);
  }
  await page.pdf({
    path: destino,
    format: "A4",
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: `<div style="width:100%;font-size:8px;color:#7d8792;padding:0 16mm;display:flex;justify-content:space-between;font-family:sans-serif"><span>${esc(deck.proyecto)} · guion del pitch</span><span class="pageNumber"></span></div>`,
    margin: { top: "16mm", bottom: "18mm", left: "16mm", right: "16mm" },
  });
  console.log(`Guion: ${destino}`);
} finally {
  await browser.close();
}

// Copia a public/local/ el material real del reto que la presentación usa y que no se publica:
// los planos del 80V01, guardados en generated/pitch-medios/, y su IFC del lote local.
// public/local/ está en .gitignore. Si falta algo, la lámina que lo usa muestra el ejemplo sintético.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const raiz = resolve(import.meta.dirname, "..");
const repo = resolve(raiz, "../..");
const destino = resolve(raiz, "public/local");
mkdirSync(destino, { recursive: true });

const lote = process.env.LOTE_TR ?? "lote_a3_f61e613";
const medios = [
  ["generated/pitch-medios/plano-80v01.webp", "plano-80v01.webp"],
  ["generated/pitch-medios/plano-reto.webp", "plano-marcado-80v01.webp"],
  ["generated/pitch-medios/cita-80v01.webp", "cita-80v01.webp"],
  [`generated/${lote}/80V01/rev2/modelo.ifc`, "80v01-rev2.ifc"],
];

let faltan = 0;
for (const [origen, nombre] of medios) {
  const ruta = resolve(repo, origen);
  if (existsSync(ruta)) copyFileSync(ruta, resolve(destino, nombre));
  else {
    faltan++;
    console.warn(`Falta ${origen}: la lámina que lo usa mostrará el ejemplo sintético.`);
  }
}
console.log(`Material local: ${medios.length - faltan} de ${medios.length} archivos en public/local/.`);

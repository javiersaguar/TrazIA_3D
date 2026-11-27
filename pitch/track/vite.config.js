import { resolve } from "node:path";
import { defineConfig } from "vite";

// Los logos y el IFC de BF-C-0008 se importan desde web/, sin copiarlos.
export default defineConfig({
  // brand.jsx se importa de pitch/concurso: una sola copia de React para toda la presentación.
  resolve: { dedupe: ["react", "react-dom", "motion"] },
  base: "./",
  server: { port: 4182, fs: { allow: [resolve(import.meta.dirname, "../..")] } },
  preview: { port: 4182 },
  build: { chunkSizeWarningLimit: 2000, assetsInlineLimit: 0 },
});

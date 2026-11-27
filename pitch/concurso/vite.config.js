import { resolve } from "node:path";
import { defineConfig } from "vite";

// Los logos y el IFC de BF-C-0008 se importan desde web/, sin copiarlos.
export default defineConfig({
  base: "./",
  server: { port: 4180, fs: { allow: [resolve(import.meta.dirname, "../..")] } },
  preview: { port: 4180 },
  build: { chunkSizeWarningLimit: 2000, assetsInlineLimit: 0 },
});

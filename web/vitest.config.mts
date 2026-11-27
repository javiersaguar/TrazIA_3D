import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Solo pruebas unitarias junto al código; las de navegador viven en tests/e2e (Playwright).
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    include: ["src/**/*.test.{ts,tsx,mjs}"],
    environment: "node",
  },
});

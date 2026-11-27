import { defineConfig } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";
const connected = Boolean(process.env.NEXT_PUBLIC_API_URL);
const cpuOnly = process.env.PW_CPU_ONLY === "1";
const port = Number(process.env.PW_PORT ?? (connected ? 3100 : 3200));
const accounts = process.env.NEXT_PUBLIC_API_URL === "/api/trazia";
const apiURL = accounts ? process.env.TRAZIA_API_ORIGIN : process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
if (!apiURL) throw new Error("Configura TRAZIA_API_ORIGIN para probar las cuentas con la API local.");
if (connected && !["localhost", "127.0.0.1", "[::1]"].includes(new URL(apiURL).hostname)) {
  throw new Error("Las pruebas de escritura necesitan una API local con datos sintéticos.");
}
if (accounts && !process.env.PW_EXTERNAL_API) process.env.PW_TEST_SECRET ??= randomBytes(32).toString("hex");
const root = resolve(__dirname, "..");

/*
  Usa el Google Chrome instalado en el sistema (channel "chrome") para no descargar navegadores.
  Si no tienes Chrome: PW_CHANNEL=msedge pnpm test:e2e
  - humo: recorre las pantallas y las interacciones clave.
  - capturas: guarda capturas de cada pantalla en oscuro y claro en docs/capturas/.
  - guion: las capturas de docs/GUION_DEMO.md (1920×1080) en ../docs/capturas/producto/.
*/
export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: `../generated/pruebas-web/${port}`,
  timeout: 45_000,
  expect: { timeout: cpuOnly || connected ? 15_000 : 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${port}`,
    channel: process.env.PW_CHANNEL ?? "chrome",
    viewport: { width: 1600, height: 940 },
    locale: "es-ES",
    trace: "retain-on-failure",
    launchOptions: cpuOnly ? { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] } : undefined,
  },
  projects: [
    ...(accounts ? [{ name: "roles", testMatch: /roles\.spec\.ts/, use: { trace: "off" as const } }] : []),
    { name: "humo", testMatch: /(?:humo|api|study|3d|producto|k8|fluidez|intro|planta)\.spec\.ts/ },
    { name: "capturas", testMatch: /capturas\.spec\.ts/ },
    { name: "guion", testMatch: /guion\.spec\.ts/ },
    { name: "video", testMatch: /video-respaldo\.spec\.ts/ },
    { name: "miniaturas", testMatch: /miniaturas\.spec\.ts/ },
  ],
  webServer: [
    ...(connected && !process.env.PW_EXTERNAL_API ? [{
      command: "uv run --frozen --inexact --extra api python tests/playwright_api.py", cwd: root,
      url: `${apiURL}/health`, reuseExistingServer: false, timeout: 120_000,
      env: { TRAZIA_DATA: `${root}/generated/e2e-api-${process.pid}`,
        TRAZIA_ROOT: root, TRAZIA_PORT: new URL(apiURL).port || "8000", TRAZIA_QUEUE: "process",
        TRAZIA_CORS_ORIGINS: `http://localhost:${port},http://127.0.0.1:${port}`,
        TRAZIA_LOTE: "", TRAZIA_DATABASE_URL: "", TRAZIA_AUTH: accounts ? "1" : "0",
        AZURE_OPENAI_API_KEY: "", GROQ_API_KEY: "", GROQ_VOICE_FREE_API_KEY: "",
        ...(accounts ? { TRAZIA_AUTH_COOKIE_SECURE: "0", TRAZIA_ADMIN_PASSWORD_FILE: "", TRAZIA_ADMIN_PASSWORD: process.env.PW_TEST_SECRET! } : {}),
        TRAZIA_REGISTRO_LLM: `${root}/generated/e2e-api-${process.pid}/llm.jsonl`,
        TRAZIA_REGISTRO_ENVIOS: `${root}/generated/e2e-api-${process.pid}/envios.jsonl`,
        TRAZIA_CORRECTIONS_FILE: `${root}/generated/e2e-api-${process.pid}/correcciones.jsonl` },
    }] : []),
    ...(!process.env.PW_EXTERNAL_WEB ? [{
      command: process.env.PW_USE_BUILD ? `corepack pnpm exec next start --port ${port}` : `corepack pnpm@10.18.0 dev --port ${port}`,
      url: `http://localhost:${port}/`, reuseExistingServer: false, timeout: 120_000,
    }] : []),
  ],
});

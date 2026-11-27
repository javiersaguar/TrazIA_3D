import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const filename = "GAD_V-101_revA.pdf";
const plan = resolve(__dirname, "../../../examples/documents", filename);
// Sin cuentas (demo) se ve todo; con cuentas, Lotes e informes y Métricas solo para admin.
const menu = ["Documentos", "Modelo", "Pipeline", "Lotes e informes", "Métricas"];

test("Documentos muestra una miniatura cuadrada del IFC y distingue los equipos sin modelo", async ({ page }) => {
  test.skip(!process.env.NEXT_PUBLIC_API_URL, "Las miniaturas del lote requieren la API conectada");
  await page.route("**/lote/resumen", route => route.fulfill({ json: [{
    tag: "SOLO-PLANO", revision: "A", documentos: ["GAD.pdf"], estado: "pendiente",
    error: null, familia: null, boquillas: null, segundos: null,
  }] }));
  await page.goto("/documentos");
  const image = page.getByRole("img", { name: "Vista 3D de V-101", exact: true });
  await expect(image).toBeVisible({ timeout: 30_000 });
  const box = await image.boundingBox();
  expect(box?.width).toBeGreaterThan(0);
  expect(box?.width).toBe(box?.height);
  await page.getByRole("textbox", { name: "Buscar equipo o documento" }).fill("SOLO-PLANO");
  await expect(page.getByTestId("ifc-thumbnail")).toHaveAttribute("data-phase", "missing");
  await expect(page.getByText("Sin IFC", { exact: true })).toBeVisible();
});

test("W1 permite arrastrar un PDF y muestra los apartados en móvil", async ({ page }) => {
  test.skip(!process.env.NEXT_PUBLIC_API_URL, "La subida de planos vive en Documentos con la API conectada");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/documentos");
  await page.getByRole("button", { name: "Abrir navegación" }).click();
  const navigation = page.getByRole("navigation", { name: "Navegación principal" });
  await expect(navigation.getByRole("link")).toHaveText(menu);
  for (const link of await navigation.getByRole("link").all()) {
    expect((await link.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
  await navigation.getByRole("link", { name: "Documentos", exact: true }).click();
  await expect(navigation).toHaveCount(0);
  await expect(page.locator("body")).toHaveCSS("font-size", "18px");

  await page.getByRole("button", { name: "Subir planos", exact: true }).click();
  const form = page.getByRole("form", { name: "Subir planos" });
  const transfer = await page.evaluateHandle(({ bytes, filename }) => {
    const data = new DataTransfer();
    data.items.add(new File([new Uint8Array(bytes)], filename, { type: "application/pdf" }));
    return data;
  }, { bytes: [...await readFile(plan)], filename });
  await form.getByTestId("plan-dropzone").dispatchEvent("drop", { dataTransfer: transfer });
  await expect(page.getByRole("list", { name: "Archivos seleccionados" })).toContainText(filename);
  await expect(form.getByLabel("Equipo", { exact: true })).toHaveValue("V-101");
  await expect(page.getByLabel("Versión", { exact: true })).toHaveValue("A");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("W1 sube el plano sintético y muestra el IFC generado por la API", async ({ page, request }) => {
  test.skip(!process.env.NEXT_PUBLIC_API_URL, "Requiere una API local conectada");
  test.setTimeout(90_000);
  await page.goto("/documentos");
  await expect(page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link")).toHaveText(menu);
  await page.getByRole("button", { name: "Subir planos", exact: true }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Elegir PDF" }).click();
  await (await chooser).setFiles(plan);
  await expect(page.getByRole("list", { name: "Archivos seleccionados" })).toContainText(filename);
  await page.getByLabel("Proyecto", { exact: true }).fill(`W1-${randomUUID().slice(0, 8)}`);

  const document = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/documents"));
  const job = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/jobs"));
  const sse = page.waitForResponse(r => /\/jobs\/[^/]+\/events$/.test(new URL(r.url()).pathname));
  await page.getByRole("button", { name: "Subir y procesar" }).click();
  expect((await document).status()).toBe(201);
  expect((await job).status()).toBe(202);
  expect((await sse).status()).toBe(200);
  await expect(page).toHaveURL(/\/pipeline\?trabajo=/);
  await expect(page.getByRole("heading", { level: 1, name: "Proceso" })).toBeVisible();
  await expect(page.getByText("Archivos subidos", { exact: true })).toBeVisible();
  await expect(page.getByText(filename, { exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Progreso del trabajo" })).toHaveAttribute("value", "100", { timeout: 45_000 });
  await expect(page.getByText("Borrador listo")).toBeVisible();
  const jobStatus = new URL((await sse).url());
  jobStatus.pathname = jobStatus.pathname.replace(/\/events$/, "");
  const finished = await request.get(jobStatus.toString());
  expect(finished.ok()).toBe(true);
  expect(await finished.json()).toMatchObject({ status: "done", run: { external_calls: 0 } });
  await page.reload();
  await expect(page.getByRole("progressbar", { name: "Progreso del trabajo" })).toHaveAttribute("value", "100");

  const ifc = page.waitForResponse(r => {
    const url = new URL(r.url());
    return /\/revisions\/[^/]+\/ifc$/.test(url.pathname) && url.searchParams.get("draft") === "true";
  });
  await page.getByRole("link", { name: "Ver diseño 3D" }).click();
  const response = await ifc;
  expect(response.status()).toBe(200);
  expect((await response.text()).startsWith("ISO-10303-21;")).toBe(true);
  await expect(page.getByRole("heading", { name: "V-101 · Versión A" })).toBeVisible();
  const viewer = page.getByTestId("ifc-viewer");
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await expect(viewer).toHaveAttribute("data-provenance", "Datos sintéticos");
  expect(Number(await viewer.getAttribute("data-triangles"))).toBeGreaterThan(0);
  await expect(viewer.locator("canvas")).toBeVisible();
  await viewer.getByRole("button", { name: "De frente" }).click();
  await expect(viewer.getByRole("button", { name: "De frente" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Ver soldaduras" })).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  const canvas = await viewer.locator("canvas").boundingBox();
  expect(canvas).toBeTruthy();
  for (const button of await viewer.getByRole("button").all()) {
    const bounds = await button.boundingBox();
    expect(bounds?.height).toBeGreaterThanOrEqual(44);
    expect((bounds?.y ?? 0) + (bounds?.height ?? 0)).toBeLessThanOrEqual(canvas?.y ?? 0);
  }
});

import { expect, test, type Locator } from "@playwright/test";

/*
  Encuadre por selección en los escenarios de proceso (contrato C2): al elegir un equipo la cámara
  queda en perspectiva, elevada, mirando a su caja y a una distancia proporcionada a su tamaño;
  Esc vuelve a la vista general.
*/

type Vec = [number, number, number];
const vector = (raw: string | null): Vec => (raw ?? "").split(",").map(Number) as Vec;

async function pose(viewer: Locator) {
  const canvas = viewer.locator("canvas");
  const eye = vector(await canvas.getAttribute("data-camera-position"));
  const target = vector(await canvas.getAttribute("data-camera-target"));
  const [dx, dy, dz] = [eye[0] - target[0], eye[1] - target[1], eye[2] - target[2]];
  return {
    eye,
    target,
    distance: Math.hypot(dx, dy, dz),
    elevation: (Math.atan2(dy, Math.hypot(dx, dz)) * 180) / Math.PI,
  };
}

/** Espera a que la cámara deje de moverse y devuelve su pose. */
async function settled(viewer: Locator) {
  let previous = await pose(viewer);
  for (let i = 0; i < 40; i++) {
    await viewer.page().waitForTimeout(150);
    const current = await pose(viewer);
    if (current.eye.every((v, k) => Math.abs(v - previous.eye[k]!) < 1e-3)) return current;
    previous = current;
  }
  return previous;
}

test("los cuatro enlaces de Documentos abren sus proyectos de proceso con la API conectada", async ({ page }) => {
  test.skip(!process.env.NEXT_PUBLIC_API_URL, "Reproduce el acceso desde Documentos con la API conectada.");
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const projects = [
    ["Plataforma marina de producción", "plataforma-marina"],
    ["Planta de tratamiento de gas", "planta-desierto"],
    ["Terminal costera de almacenamiento", "terminal-costera"],
    ["Ampliación de una refinería", "refineria-activa"],
  ];
  for (const [name, id] of projects) {
    await page.goto("/documentos?vista=proyectos");
    await page.getByRole("link", { name: new RegExp(name!) }).click();
    await expect(page).toHaveURL(new RegExp(`/proyectos-proceso/${id}$`));
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    await expect(page.getByTestId("ifc-viewer")).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  }
});

test("al elegir P-150 la cámara lo encuadra en perspectiva y Esc vuelve a la vista general", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "El catálogo sintético de plantas solo se abre en la demo sin API.");
  test.setTimeout(90_000);
  await page.goto("/proyectos-proceso/plataforma-marina");
  const viewer = page.getByTestId("ifc-viewer");
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  const canvas = viewer.locator("canvas");
  await expect(canvas).toHaveAttribute("data-camera-projection", "perspective");
  const general = await settled(viewer);
  expect(general.elevation).toBeGreaterThan(10);

  await page.locator("tbody th button", { hasText: "P-150" }).first().click();
  await expect(viewer).toHaveAttribute("data-selection", "element:P-150");
  await expect(viewer).toHaveAttribute("data-selection-bounds", /.+/);
  await expect.poll(async () => (await pose(viewer)).distance, { timeout: 10_000 }).toBeLessThan(general.distance * 0.5);
  const shot = await settled(viewer);
  const bounds = (await viewer.getAttribute("data-selection-bounds"))!.split(",").map(Number);
  const [min, max] = [bounds.slice(0, 3), bounds.slice(3, 6)];
  const diagonal = Math.hypot(max[0]! - min[0]!, max[1]! - min[1]!, max[2]! - min[2]!);

  expect(shot.elevation).toBeGreaterThanOrEqual(15);
  expect(shot.elevation).toBeLessThanOrEqual(65);
  shot.target.forEach((value, axis) => {
    expect(value).toBeGreaterThanOrEqual(min[axis]! - 0.05);
    expect(value).toBeLessThanOrEqual(max[axis]! + 0.05);
  });
  expect(shot.distance / diagonal).toBeGreaterThan(1);
  expect(shot.distance / diagonal).toBeLessThan(4);
  await expect(canvas).toHaveAttribute("data-camera-projection", "perspective");
  // Objetivo de rendimiento del encuadre (muestreo + rayos BVH + oclusión): < 40 ms.
  expect(Number(await viewer.getAttribute("data-framing-ms"))).toBeLessThan(40);

  await page.keyboard.press("Escape");
  await expect(viewer).toHaveAttribute("data-selection", "");
  await expect.poll(async () => (await pose(viewer)).distance, { timeout: 10_000 }).toBeGreaterThan(general.distance * 0.9);
  const back = await settled(viewer);
  back.eye.forEach((value, axis) => expect(value).toBeCloseTo(general.eye[axis]!, 0));
  await expect(canvas).toHaveAttribute("data-camera-projection", "perspective");
});

test("Alzado y Planta fuerzan la ortográfica y Perspectiva alterna la vista general", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "El catálogo sintético de plantas solo se abre en la demo sin API.");
  await page.goto("/proyectos-proceso/plataforma-marina");
  const viewer = page.getByTestId("ifc-viewer");
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  const canvas = viewer.locator("canvas");
  await expect(canvas).toHaveAttribute("data-camera-projection", "perspective");
  await viewer.getByRole("button", { name: "Alzado" }).click();
  await expect(canvas).toHaveAttribute("data-camera-projection", "orthographic");
  await viewer.getByRole("button", { name: "Planta" }).click();
  await expect(canvas).toHaveAttribute("data-camera-projection", "orthographic");
  await viewer.getByRole("button", { name: "General" }).click();
  await expect(canvas).toHaveAttribute("data-camera-projection", "perspective");
  const toggle = viewer.getByRole("button", { name: "Perspectiva" });
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await toggle.click();
  await expect(canvas).toHaveAttribute("data-camera-projection", "orthographic");
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
});

test("el GA de planta sincroniza una cota, el PDF multipágina y su pieza IFC", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Usa la demo sintética sin sesión.");
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/proyectos-proceso/plataforma-marina");
  const pdf = page.getByTestId("pdf-panel");
  const viewer = page.getByTestId("ifc-viewer");
  await expect(pdf).toHaveAttribute("data-pdf-page", "1");
  await expect(pdf.getByRole("button", { name: "Evidencia de Largo total X" })).toBeVisible();
  await page.getByRole("button", { name: "Campos", exact: true }).click();
  await page.getByRole("searchbox", { name: "Buscar equipo, pieza o cota" }).fill("V-110 · Largo nominal");
  await page.getByRole("button", { name: /V-110 · Largo nominal/ }).click();
  await expect(pdf).toHaveAttribute("data-pdf-page", "2");
  await expect(viewer).toHaveAttribute("data-selection", "element:V-110");
  await expect(pdf.getByRole("button", { name: "Evidencia de V-110 · Largo nominal" })).toBeVisible();
  await page.getByRole("button", { name: "Revisión B", exact: true }).click();
  await expect(page.getByRole("link", { name: "Descargar plano GA" })).toHaveAttribute("href", /GA_SIM-MAR_revB\.pdf$/);
  await expect(viewer).toHaveAttribute("data-ifc-url", /SIM-MAR-B\.ifc$/);
});

test("sin API la ficha escala el equipo en el navegador y avisa de las líneas que revisar", async ({ page }) => {
  test.skip(!!process.env.NEXT_PUBLIC_API_URL, "Con API el borrador lo genera el servidor");
  test.setTimeout(95_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/proyectos-proceso/plataforma-marina");
  const viewer = page.getByTestId("ifc-viewer");
  const sheet = page.getByRole("region", { name: "Ficha de componente" });
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await sheet.getByRole("button", { name: /^V-110 ·/ }).click();
  await expect(sheet.getByText(/navegador escala la geometría IFC/)).toBeVisible();
  await sheet.getByLabel(/Largo nominal/).fill("9.9");
  await sheet.getByRole("button", { name: "Previsualizar borrador" }).click();
  await expect(viewer).toHaveAttribute("data-ifc-url", /^blob:/, { timeout: 45_000 });
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await expect(sheet.getByText("Actual 9,9", { exact: true })).toBeVisible();
  await expect(sheet.getByText(/Revisar conexiones: .*OL-05/)).toBeVisible();
  const history = sheet.getByRole("region", { name: "Cambios realizados" });
  await expect(history.getByRole("button", { name: /V-110.*Ensayo 1.*Largo nominal.*9 → 9,9 m/ })).toBeVisible();
  await sheet.getByLabel(/Ancho o diámetro/).fill("4.2");
  await sheet.getByRole("button", { name: "Previsualizar borrador" }).click();
  await expect(history.getByRole("button", { name: /Ensayo 2.*Ancho o diámetro.*4,2 m/ })).toBeVisible({ timeout: 45_000 });
  await expect(history.getByRole("button")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "Descargar IFC", exact: true })).toHaveAttribute("download", "SIM-MAR-ENSAYO-DRAFT.ifc");
  // Al recargar vuelven el historial y el borrador, regenerado desde el IFC base.
  await page.reload();
  await expect(history.getByRole("button")).toHaveCount(2, { timeout: 30_000 });
  await expect(viewer).toHaveAttribute("data-ifc-url", /^blob:/, { timeout: 45_000 });
  await sheet.getByRole("button", { name: /V-110.*Ensayo 1/ }).click();
  await expect(sheet.getByText("Actual 9,9", { exact: true })).toBeVisible({ timeout: 30_000 });
  await sheet.getByRole("button", { name: "Descartar borrador" }).click();
  await expect(viewer).toHaveAttribute("data-ifc-url", /SIM-MAR-A\.ifc$/);
  await expect(history).toHaveCount(0);
  await page.reload();
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await expect(history).toHaveCount(0);
});

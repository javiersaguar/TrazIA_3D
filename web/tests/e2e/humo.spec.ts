import { expect, test, type Page } from "@playwright/test";

const connected = Boolean(process.env.NEXT_PUBLIC_API_URL);

test("el espacio de trabajo termina de hidratar una sola copia de la página", async ({ page }) => {
  await page.goto("/proyecto");
  await expect(page.getByTestId("app-workspace")).toBeVisible();
  await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator('[id^="S:"]').filter({ hasText: /\S/ })).toHaveCount(0);
  await expect(page.getByTestId("app-workspace")).toHaveCount(1);
});
const SCREENS = [
  { path: "/proyecto", title: "Resumen" },
  { path: "/pipeline?vista=detalle", title: "Pipeline" },
  { path: "/revision", title: "Modelo" },
  { path: "/cambios", title: "Modelo" },
  { path: "/bench", title: "Bench" },
  { path: "/impacto", title: "Impacto" },
  { path: "/estudio", title: "Bench" },
];

function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("response", (r) => r.status() >= 400 && errors.push(`${r.status()} ${r.url()}`));
  return errors;
}

test("las 7 pantallas cargan sin errores", async ({ page }) => {
  const errors = trackErrors(page);
  for (const s of SCREENS) {
    await page.goto(s.path);
    await expect(page.getByRole("heading", { level: 1, name: connected && ["/proyecto", "/bench", "/impacto", "/estudio"].includes(s.path) ? "Documentos" : s.title })).toBeVisible();
    // La barra ya no rotula la fuente ni el pipeline: solo se comprueba que está.
    await expect(page.getByRole("banner")).toBeVisible();
  }
  expect(errors, errors.join("\n")).toEqual([]);
});

const SKETCHES = [
  { path: "/proyectos", title: "Documentos" },
  { path: "/documentos?vista=documentos", title: "Documentos" },
  { path: "/modelo?vista=revision", title: "Modelo" },
  { path: "/familias", title: "Documentos" },
  { path: "/lote", title: "Lotes e informes" },
  { path: "/informes", title: "Lotes e informes" },
  { path: "/auditoria", title: "Documentos" },
  { path: "/ajustes", title: "Ajustes" },
];

test("las secciones en boceto cargan sin errores", async ({ page }) => {
  const errors = trackErrors(page);
  for (const s of SKETCHES) {
    await page.goto(s.path);
    await expect(page.getByRole("heading", { level: 1, name: s.title })).toBeVisible();
  }
  expect(errors, errors.join("\n")).toEqual([]);
});

test("la portada pide acceso, «Iniciar» entra sin validar y «Salir» vuelve a la portada", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_API_URL === "/api/trazia", "El acceso real se cubre en roles.spec.ts");
  const errors = trackErrors(page);
  await page.emulateMedia({ reducedMotion: "reduce" }); // sin la intro del logo
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: /Del plano al modelo 3D/ })).toBeVisible();
  const form = page.getByRole("form", { name: "Entra en la demo" });
  await expect(form.getByLabel("Usuario")).toBeVisible();
  await expect(form.getByLabel("Contraseña", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Iniciar", exact: true }).click();
  await expect(page).toHaveURL(/\/documentos$/);
  await expect(page.getByRole("heading", { level: 1, name: "Documentos" })).toBeVisible();
  await page.getByRole("button", { name: "Salir", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("form", { name: "Entra en la demo" })).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("la demo abre el IFC del V-101 y permite repetir su animación", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await page.getByRole("button", { name: /Saltar intro/ }).click();
  const ifc = page.waitForResponse(response => response.url().endsWith("/demo/ifc/rev_b.ifc") && response.ok());
  await page.getByRole("link", { name: "Abrir demo V-101" }).click();
  await expect(page).toHaveURL(/\/demo\/v-101$/);
  await expect(page.getByRole("heading", { name: "Recipiente V-101" })).toBeVisible();
  await ifc;
  const model = page.getByTestId("landing-assembly");
  await expect(model.locator("canvas")).toBeVisible({ timeout: 45_000 });
  await expect(model).toHaveAttribute("data-step", "2", { timeout: 20_000 });
  await page.getByRole("button", { name: "Pausar giro 3D" }).click();
  await expect(model).toHaveAttribute("data-rotating", "false");
  await page.getByRole("button", { name: "Repetir animación del boceto" }).click();
  await expect(model).toHaveAttribute("data-step", /^[01]$/);
  await page.getByRole("link", { name: "Volver al inicio" }).click();
  await expect(page.getByLabel("Usuario")).toBeVisible();
});

test("la barra lateral navega entre pantallas", async ({ page }) => {
  await page.goto("/proyecto");
  await page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link", { name: "Modelo", exact: true }).click();
  await expect(page).toHaveURL(/\/modelo(?:\?.*)?$/);
  await expect(page.getByRole("heading", { level: 1, name: "Modelo", exact: true })).toBeVisible();
});

test("en móvil la navegación vive en un panel que se cierra al elegir pantalla", async ({ page }) => {
  const errors = trackErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/proyecto");
  await expect(page.getByRole("heading", { level: 1, name: connected ? "Documentos" : "Resumen" })).toBeVisible();
  // La barra fija no se ve; la página no se desplaza en horizontal
  await expect(page.getByRole("navigation", { name: "Navegación principal" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

  await page.getByRole("button", { name: "Abrir navegación" }).click();
  const sheet = page.getByRole("dialog", { name: "Navegación" });
  await sheet.getByRole("link", { name: "Modelo", exact: true }).click();
  await expect(page).toHaveURL(/\/modelo$/);
  await expect(page.getByRole("heading", { level: 1, name: "Modelo" })).toBeVisible();
  await expect(sheet).toBeHidden();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("revisión por teclado: J selecciona, A acepta y Ctrl+Z deshace", async ({ page }) => {
  test.skip(connected, "En modo API, api.spec.ts comprueba las acciones por teclado y su persistencia.");
  await page.goto("/revision");
  await page.getByRole("button", { name: /^Cola de revisión/ }).click();
  const queue = page.getByRole("listbox", { name: "Campos por revisar" });
  await expect(queue.getByRole("option").first()).toBeVisible();

  await page.keyboard.press("j");
  await expect(queue.getByRole("option", { selected: true })).toContainText("Diámetro de la virola");

  await page.keyboard.press("a");
  await expect(page.getByText("Campo aceptado")).toBeVisible();
  await expect(queue.getByText("Aceptado")).toBeVisible();
  await expect(page.getByText("1 de 22")).toBeVisible();

  await page.keyboard.press("Control+z");
  await expect(page.getByText("0 de 22")).toBeVisible();
});

test("la corrección de un valor preliminar requiere evidencia y Esc conserva la cola", async ({ page }) => {
  test.skip(connected, "Usa una revisión sintética interceptada");
  await page.route("**/vessel_rev_a.json", async route => {
    const response = await route.fetch();
    const revision = await response.json();
    const diameter = revision.equipment.diameter;
    diameter.state = "assumed";
    diameter.source.rule = "preliminar.diametro";
    diameter.explanation = "Valor preliminar de prueba";
    await route.fulfill({ json: revision });
  });
  await page.goto("/revision");
  const drawer = page.getByRole("button", { name: /^Cola de revisión/ });
  await drawer.click();
  const row = page.locator('[data-row="diameter"]');
  await row.click();
  await expect(row.getByText("Preliminar", { exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Aceptar", exact: true })).toHaveCount(0);
  await row.getByRole("button", { name: "Corregir", exact: true }).click();
  await expect(row.getByText("Evidencia requerida", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(row.getByRole("alert")).toContainText("Indica la página 1");
  await row.getByRole("textbox", { name: "Nota de revisión (opcional)" }).press("Escape");
  await expect(drawer).toHaveAttribute("aria-expanded", "true");
  await expect(row.getByRole("button", { name: "Guardar", exact: true })).toHaveCount(0);
  await expect(row).toBeFocused();
});

test("el menú de comandos lleva a una boquilla", async ({ page }) => {
  await page.goto("/proyecto");
  await page.keyboard.press("Control+k");
  const input = page.getByPlaceholder("Ir a una pantalla, boquilla o campo…");
  await expect(input).toBeVisible();
  await input.fill("boquilla N3");
  await expect(page.getByRole("option", { name: "Boquilla N3", selected: true })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/modelo\?vista=revision$/);
});

test("el pipeline repite el recorrido y registra eventos", async ({ page }) => {
  await page.goto("/pipeline?vista=detalle");
  if (connected) {
    await page.getByLabel("Estrategia de lectura").selectOption("b_reglas");
    await page.getByRole("button", { name: "Procesar demo", exact: true }).click();
  }
  await expect(page.getByRole("cell", { name: "GAD_V-101_revA.pdf" }).first()).toBeVisible();
});

test("los cambios se reproducen paso a paso", async ({ page }) => {
  await page.goto("/cambios");
  await expect(page.getByText("Longitud entre tangentes").first()).toBeVisible();
  await page.getByRole("button", { name: "Reproducir los cambios" }).click();
  await expect(page.getByText(/Paso 1 de \d+/)).toBeVisible();
});


test("el laboratorio 3D sigue leyendo los productos enriquecidos del IFC", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/lab/3d");
  if (connected) {
    await expect(page).toHaveURL(/\/documentos$/);
    return;
  }
  await expect(page.getByRole("heading", { level: 1, name: "Laboratorio 3D" })).toBeVisible();
  await expect(page.locator('[data-testid="ifc-viewer"]').first()).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await expect(page.locator('[data-testid="ifc-viewer"]').first()).toHaveAttribute("data-products", "73");
  expect(errors, errors.join("\n")).toEqual([]);
});


test("el panel del copiloto conserva las reglas en modo offline", async ({ page }) => {
  test.skip(connected, "El modo API tiene pruebas de respuesta y error propias");
  await page.goto("/revision");
  await page.getByRole("button", { name: /^Cola de revisión/ }).click();
  await expect(page.getByRole("listbox", { name: "Campos por revisar" }).getByRole("option").first()).toBeVisible();
  await page.keyboard.press("j");
  await page.getByRole("button", { name: "Copiloto", exact: true }).click();
  await expect(page.getByText("Reglas sobre el JSON extraído · modo offline")).toBeVisible();
  await expect(page.getByText("Qué pasa si está mal", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Tu pregunta" })).toHaveCount(0);
});

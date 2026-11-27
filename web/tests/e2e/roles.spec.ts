import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

async function entrar(page: Page, username: string) {
  const password = process.env.PW_TEST_SECRET;
  if (!password) throw new Error("Falta la contraseña temporal de la API de prueba.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("form").getByRole("button", { name: "Iniciar", exact: true }).click();
  await expect(page).toHaveURL(/\/documentos/, { timeout: 30_000 });
}

test("el revisor trabaja en Documentos y queda fuera de administración", async ({ page }, info) => {
  test.setTimeout(90_000);
  await entrar(page, "revisor");
  const nav = page.getByRole("navigation", { name: "Navegación principal" });
  for (const name of ["Documentos", "Modelo"]) {
    await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("link", { name: "Ajustes", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Ajustes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ajustes", level: 1 })).toBeVisible();
  await expect(page.getByRole("group", { name: "Rol activo" })).toHaveCount(0);
  for (const label of ["Lotes", "Métricas"]) {
    await expect(page.getByRole("link", { name: label, exact: true })).toHaveCount(0);
  }
  for (const [ruta, recurso] of [["/lote", "exportaciones"], ["/metricas", "metricas"]] as const) {
    await page.goto(ruta);
    await expect(page.getByRole("heading", { name: "Solo para administradores" })).toBeVisible();
    expect((await page.request.get(`/api/trazia/admin/${recurso}`)).status()).toBe(403);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/documentos");
  const abrir = page.getByRole("button", { name: "Abrir navegación" });
  expect((await abrir.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await abrir.focus();
  await expect(abrir).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(nav.getByRole("link")).toHaveText(["Documentos", "Modelo"]);
  await page.keyboard.press("Escape");
  await expect(abrir).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.goto("/modelo?vista=revision");
  await expect(page.getByRole("radio", { name: "Proponer cambios" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Cambios", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Iniciar sesión manual" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Cola de revisión/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: info.outputPath("revisor-modelo-390.png") });
});

test("Javier alterna la interfaz y los permisos desde Ajustes", async ({ page }) => {
  test.setTimeout(90_000);
  await entrar(page, "javier.saguar");
  await page.goto("/ajustes");
  const perfil = page.getByRole("group", { name: "Rol activo" });
  const admin = perfil.getByRole("radio", { name: /^Administrador/ });
  const usuario = perfil.getByRole("radio", { name: /^Usuario/ });
  const ruta = "/api/trazia/admin/metricas";
  const nav = page.getByRole("navigation", { name: "Navegación principal" });
  await expect(admin).toBeChecked();
  await expect(nav.getByRole("link", { name: "Métricas" })).toBeVisible();

  await perfil.getByText("Usuario", { exact: true }).click();
  await expect(usuario).toBeChecked();
  await expect(nav.getByRole("link", { name: "Métricas" })).toHaveCount(0);
  expect((await page.request.get(ruta)).status()).toBe(403);
  await page.reload();
  await expect(usuario).toBeChecked();

  await perfil.getByText("Administrador", { exact: true }).click();
  await expect(admin).toBeChecked();
  await expect(nav.getByRole("link", { name: "Métricas" })).toBeVisible();
  expect((await page.request.get(ruta)).status()).toBe(200);
});

test("el equipo rota de cuenta, conserva su foto y alterna permisos", async ({ page }) => {
  test.setTimeout(120_000);
  const login = await page.request.post("/api/trazia/auth/login", {
    data: { username: "iria.lozano", password: process.env.PW_TEST_SECRET },
  });
  expect(login.ok()).toBe(true);
  await page.goto("/ajustes");
  const avatar = page.locator('img[src*="/auth/avatar/iria.lozano"]');
  await expect(page.getByRole("button", { name: "Cambiar foto de perfil" })).toBeEnabled();
  await page.locator('input[type="file"][accept*="image/png"]').setInputFiles({
    name: "perfil-ensayo.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGPUy5vBwMDAxAAGAA4wATh4IIv4AAAAAElFTkSuQmCC", "base64"),
  });
  await expect(avatar.first()).toBeVisible();
  await expect.poll(() => avatar.first().evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);

  const form = page.getByRole("form", { name: "Cambiar de cuenta" });
  const perfil = page.getByRole("group", { name: "Rol activo" });
  const metrics = page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link", { name: "Métricas" });
  const session = () => page.request.get("/api/trazia/auth/session").then(response => response.json());
  const admin = () => page.request.get("/api/trazia/admin/metricas").then(response => response.status());

  await form.getByLabel("Integrante del equipo").selectOption("miguel.vera");
  await form.getByLabel("Contraseña de la cuenta").fill("contraseña incorrecta");
  await form.getByRole("button", { name: "Iniciar con esta cuenta" }).click();
  await expect(form.getByRole("alert")).toBeVisible();
  expect((await session()).username).toBe("iria.lozano");

  for (const username of ["miguel.vera", "alejandro.cuevas", "javier.saguar", "iria.lozano"]) {
    await form.getByLabel("Integrante del equipo").selectOption(username);
    await form.getByLabel("Contraseña de la cuenta").fill(process.env.PW_TEST_SECRET!);
    await form.getByRole("button", { name: "Iniciar con esta cuenta" }).click();
    await expect.poll(async () => (await session()).username).toBe(username);
    await expect(form.getByLabel("Integrante del equipo")).toHaveValue("");
    await expect(form.getByLabel("Integrante del equipo").locator("option")).toHaveCount(4);
    await expect(perfil.getByRole("radio", { name: /^Administrador/ })).toBeChecked();
    await expect(perfil.getByRole("radio", { name: /^Usuario/ })).toBeEnabled();
    await perfil.getByText("Usuario", { exact: true }).click();
    await expect(perfil.getByRole("radio", { name: /^Usuario/ })).toBeChecked();
    await expect.poll(admin).toBe(403);
    await expect(metrics).toHaveCount(0);
    await expect(perfil.getByRole("radio", { name: /^Administrador/ })).toBeEnabled();
    await perfil.getByText("Administrador", { exact: true }).click();
    await expect(perfil.getByRole("radio", { name: /^Administrador/ })).toBeChecked();
    await expect.poll(admin).toBe(200);
    await expect(metrics).toBeVisible();
  }
  await expect(avatar.first()).toBeVisible();
});

test("el administrador descarga los cuatro formatos y conserva su historial", async ({ page }) => {
  test.setTimeout(90_000);
  await entrar(page, "javier.saguar");
  await page.getByRole("link", { name: "Lotes", exact: true }).first().click();
  const firmas = { IFC: "ISO-10303-21", BCF: "PK", CSV: "confianza", PDF: "%PDF" };
  for (const [formato, firma] of Object.entries(firmas)) {
    const esperando = page.waitForEvent("download");
    await page.getByRole("button", { name: `Exportar ${formato}`, exact: true }).click();
    const descarga = await esperando;
    expect(await descarga.failure()).toBeNull();
    expect((await readFile((await descarga.path())!)).toString("latin1", 0, 200)).toContain(firma);
    const fila = page.getByRole("row").filter({ has: page.getByRole("cell", { name: formato, exact: true }) });
    await expect(fila.first()).toContainText("javier.saguar");
  }
  await page.reload();
  for (const formato of Object.keys(firmas)) {
    await expect(page.getByRole("cell", { name: formato, exact: true }).first()).toBeVisible();
  }
  const [copia] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Descargar PDF", exact: true }).first().click(),
  ]);
  expect((await readFile((await copia.path())!)).toString("latin1", 0, 5)).toBe("%PDF-");
});

test("las métricas permiten cambiar de periodo y pausar en ambos temas", async ({ page }, info) => {
  test.setTimeout(90_000);
  await entrar(page, "javier.saguar");
  await page.goto("/metricas");
  const semana = page.waitForResponse(r => r.url().includes("/admin/metricas?rango=7d"));
  await page.getByLabel("Periodo").selectOption("7d");
  expect((await semana).ok()).toBe(true);
  await page.getByRole("button", { name: "Pausar refresco" }).click();
  await expect(page.getByRole("button", { name: "Reanudar refresco" })).toHaveAttribute("aria-pressed", "true");
  for (const tema of ["dark", "light"]) {
    await page.evaluate(value => { document.documentElement.dataset.theme = value; }, tema);
    await expect(page.getByRole("heading", { name: "Flujo de trabajos" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Últimas 5 actividades" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Errores recientes" })).toHaveCount(0);
    await page.getByRole("group", { name: "Filtrar actividad" }).getByRole("button", { name: "Revisiones" }).click();
    await expect(page.getByRole("group", { name: "Filtrar actividad" }).getByRole("button", { name: "Revisiones" })).toHaveAttribute("aria-pressed", "true");
    await page.screenshot({ path: info.outputPath(`metricas-${tema}.png`) });
  }
});

test("la portada carga el IFC y los cambios al acercar el visor tras iniciar sesión", async ({ page }, info) => {
  test.setTimeout(90_000);
  const llamadas: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/trazia/")) llamadas.push(request.url()); });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("form")).toBeVisible();
  expect(llamadas).toEqual([]);
  await entrar(page, "revisor");
  llamadas.length = 0;
  await page.goto("/");
  const modelos = page.getByRole("region", { name: "Modelos del reto" });
  await expect(modelos.getByRole("button", { name: "Revisión B", exact: true })).toBeAttached();
  expect(llamadas.some(url => url.includes("/ifc?"))).toBe(false);
  await modelos.scrollIntoViewIfNeeded();
  const visor = modelos.getByTestId("ifc-viewer");
  await expect(visor).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await expect(modelos.getByLabel("Pieza con cambios")).toBeVisible();
  const anterior = modelos.getByRole("button", { name: "Revisión A", exact: true });
  await anterior.click();
  await expect(anterior).toHaveAttribute("aria-pressed", "true");
  await expect(visor).toHaveAttribute("data-ifc-url", /%3AA\/ifc/);
  await expect(visor).toHaveAttribute("data-phase", "ready");
  await expect(modelos.getByText("Modelo sintético")).toBeVisible();
  await modelos.getByRole("button", { name: "Revisión B", exact: true }).click();
  await expect(visor).toHaveAttribute("data-ifc-url", /%3AB\/ifc/);
  await expect(visor).toHaveAttribute("data-phase", "ready");
  expect(llamadas.filter(url => /%3AB\/ifc\?/.test(url))).toHaveLength(1);
  await modelos.screenshot({ path: info.outputPath("modelos-portada.png") });
});

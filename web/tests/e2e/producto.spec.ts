import { expect, test } from "@playwright/test";

test("Documentos abre la subida en un diálogo y acepta PDF arrastrados o elegidos", async ({ page }) => {
  test.skip(!process.env.NEXT_PUBLIC_API_URL, "La subida se ofrece en el catálogo conectado.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/documentos?vista=equipos");
  const trigger = page.getByRole("button", { name: "Subir planos", exact: true });
  const search = page.locator('input[placeholder="Buscar por TAG o documento"]');
  const before = await search.boundingBox();
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Subir planos", exact: true });
  await expect(dialog).toBeVisible();
  expect(await search.boundingBox()).toEqual(before);
  const form = dialog.getByRole("form", { name: "Subir planos" });
  const zone = form.getByTestId("plan-dropzone");
  const submit = form.getByRole("button", { name: "Subir y procesar" });
  await expect(submit).toBeDisabled();

  const dataTransfer = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(new File(["%PDF-1.4"], "GAD_V-101_revA.pdf", { type: "application/pdf" }));
    return data;
  });
  await zone.dispatchEvent("dragenter", { dataTransfer });
  await expect(zone).toHaveAttribute("data-dragging", "true");
  await zone.dispatchEvent("drop", { dataTransfer });
  await expect(zone).not.toHaveAttribute("data-dragging", "true");
  const list = form.getByRole("list", { name: "Archivos seleccionados" });
  await expect(list).toContainText("GAD_V-101_revA.pdf");
  await expect(form.getByLabel("Equipo", { exact: true })).toHaveValue("V-101");
  await expect(form.getByLabel("Versión", { exact: true })).toHaveValue("A");

  const chooser = page.waitForEvent("filechooser");
  await form.getByRole("button", { name: "Elegir PDF" }).click();
  await (await chooser).setFiles({ name: "GAD_V-101_revB.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") });
  await expect(list.getByRole("listitem")).toHaveCount(2);
  await expect(form.getByRole("alert")).toContainText("una sola versión");
  await expect(submit).toBeDisabled();
  await form.getByRole("button", { name: "Quitar GAD_V-101_revB.pdf" }).click();
  await expect(submit).toBeEnabled();

  await page.setViewportSize({ width: 390, height: 680 });
  const bounds = await dialog.boundingBox();
  expect(bounds?.width).toBeLessThan(390);
  expect((bounds?.y ?? -1) + (bounds?.height ?? 0)).toBeLessThan(680);
  await expect(submit).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(list).toHaveCount(0);
  await dialog.getByRole("button", { name: "Cancelar" }).click();
  await expect(dialog).toBeHidden();
});

test("los proyectos de proceso conservan el entorno y aplican cambios IFC por pieza", async ({ page, request }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
  test.setTimeout(90_000);
  await page.goto("/documentos?vista=proyectos");
  const cards = page.getByRole("region", { name: "Proyectos 3D de petróleo y gas" });
  await expect(cards.getByRole("link")).toHaveCount(4);
  await cards.getByRole("link", { name: /Plataforma marina de producción/ }).click();
  const viewer = page.getByTestId("ifc-viewer");
  await expect(viewer).toHaveAttribute("data-ifc-url", /SIM-MAR-A\.ifc$/, { timeout: 30_000 });
  await expect(viewer).toHaveAttribute("data-scenario", "ocean");
  await expect(viewer).toHaveAttribute("data-environment-motion", "on");
  await expect(page.getByLabel("Entorno del visor")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Animación del entorno" })).toHaveCount(0);
  await page.reload();
  await expect(viewer).toHaveAttribute("data-scenario", "ocean");
  await page.getByRole("checkbox", { name: /Ampliar la virola/ }).check();
  await expect(viewer).toHaveAttribute("data-ifc-url", /Ensayo-10\.ifc$/, { timeout: 30_000 });
  await expect(page.getByText(/El PDF es la referencia documental/)).toBeVisible();
  await page.getByRole("checkbox", { name: /Elevar el tramo/ }).check();
  await expect(viewer).toHaveAttribute("data-ifc-url", /SIM-MAR-B\.ifc$/, { timeout: 30_000 });
  await expect(page.getByText(/El PDF es la referencia documental/)).toHaveCount(0);
  const drawing = await page.getByRole("link", { name: "PDF de V-110", exact: true }).getAttribute("href");
  expect(drawing).toMatch(/GAD_V-110_revB\.pdf$/);
  expect((await request.get(drawing!)).headers()["content-type"]).toContain("application/pdf");
  const zip = await page.getByRole("link", { name: "Descargar dossier ZIP" }).getAttribute("href");
  expect(zip).toMatch(/dossier-B\.zip$/);
  expect((await request.get(zip!)).ok()).toBe(true);
});

test("el visor de proceso respeta la preferencia de movimiento reducido", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/proyectos-proceso/plataforma-marina");
  await expect(page.getByTestId("ifc-viewer")).toHaveAttribute("data-environment-motion", "off");
  await expect(page.getByRole("button", { name: "Animación del entorno" })).toHaveCount(0);
});

test("los ajustes siguen accesibles por URL", async ({page})=>{
 await page.goto("/ajustes");
 await page.getByRole("radio",{name:"Claro",exact:true}).click();
 await expect(page.locator("html")).toHaveAttribute("data-theme","light");
 await expect(page.getByRole("heading",{name:"Estrategia por defecto",exact:true})).toBeVisible();
});

test("familias, proyectos y archivos sobreviven a recargar",async({page})=>{
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
 await page.goto("/documentos?vista=documentos");
 await page.getByRole("button",{name:"Nueva familia",exact:true}).click();
 await page.getByRole("form",{name:"Nueva familia"}).getByLabel("Nombre").fill("Separadores del piloto");
 await page.getByRole("button",{name:"Guardar",exact:true}).click();
 await page.getByRole("button",{name:"Nuevo proyecto",exact:true}).click();
 await page.getByRole("form",{name:"Nuevo proyecto"}).getByLabel("Nombre").fill("Proyecto piloto");
 await page.getByRole("button",{name:"Guardar",exact:true}).click();
 await page.getByRole("button",{name:"Añadir diseño",exact:true}).click();
 const form=page.getByRole("form",{name:"Añadir diseño"});
 await form.getByLabel("Nombre").fill("V-202");
 await form.getByLabel("Familia",{exact:true}).selectOption({label:"Separadores del piloto"});
 await form.getByLabel("Proyecto",{exact:true}).selectOption({label:"Proyecto piloto"});
 await form.getByLabel("Documento",{exact:true}).setInputFiles({name:"GAD_V202.pdf",mimeType:"application/pdf",buffer:Buffer.from("synthetic test document")});
 await page.getByRole("button",{name:"Guardar",exact:true}).click();
 await expect(page.getByText("V-202",{exact:true})).toBeVisible();
 await page.reload();
 await expect(page.getByText("V-202",{exact:true})).toBeVisible();
 const download=page.waitForEvent("download");
 await page.getByRole("button",{name:"GAD_V202.pdf",exact:true}).click();
 expect((await download).suggestedFilename()).toBe("GAD_V202.pdf");
});

test("la portada es el inicio de sesión y no se desplaza",async({page})=>{
 await page.emulateMedia({reducedMotion:"reduce"});
 await page.goto("/");
 await expect(page.getByRole("heading",{name:/Del plano al modelo 3D/})).toBeVisible();
 await expect(page.getByRole("button",{name:"Iniciar",exact:true})).toBeVisible();
 await expect(page.getByTestId("landing-reference")).toBeVisible();
 for (const name of ["Del holograma al modelo","Cómo funciona","Cuatro maneras de leer un plano","Abre la demo con el recipiente V-101."]) {
  await expect(page.getByRole("heading",{name,exact:true})).toHaveCount(0);
 }
 for (const viewport of [{width:1600,height:940},{width:1366,height:768},{width:1280,height:720}]) {
  await page.setViewportSize(viewport);
  await expect(page.getByRole("form")).toBeInViewport({ratio:1});
  const fits=await page.evaluate(()=>document.documentElement.scrollHeight<=document.documentElement.clientHeight+1);
  expect(fits).toBe(true);
 }
 await page.mouse.move(700,350);
 await expect(page.getByTestId("landing-spotlight")).toHaveCSS("position","fixed");
 await page.setViewportSize({width:390,height:844});
 await expect(page.getByRole("form")).toBeInViewport({ratio:1});
 await expect(page.getByRole("link",{name:"Abrir demo V-101"})).toBeInViewport({ratio:1});
 const hasHorizontalScroll=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth);
 expect(hasHorizontalScroll).toBe(false);
});

test("revisión, cambios y geometría comparten una sola ruta",async({page})=>{
 await page.emulateMedia({reducedMotion:"reduce"});
 await page.goto("/modelo?vista=revision");
 await expect(page.getByRole("heading",{name:"Modelo",exact:true})).toBeVisible();
 await page.getByRole("radio",{name:"Cambios",exact:true}).click();
 await expect(page).toHaveURL(/vista=cambios/);
 await expect(page.getByTestId("changes-hub")).toBeVisible();
 await expect(page.getByRole("radio",{name:"Modelo 3D",exact:true})).toHaveCount(0);
 await expect(page.getByTestId("version-compare").getByTestId("revision-morph")).toBeVisible({timeout:30_000});
 await page.getByRole("radio",{name:"Revisión",exact:true}).click();
 await expect(page).toHaveURL(/vista=revision/);
});

test("la cola de revisión se abre sobre los visores y admite arrastre y teclado", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/modelo?vista=revision");
  const main = page.getByTestId("review-workspace");
  const tabs = page.getByRole("banner").getByRole("radiogroup", { name: "Espacio del modelo" });
  await expect(tabs.getByRole("radio", { name: "Revisión", exact: true })).toBeChecked();
  const queue = main.getByRole("listbox", { name: "Campos por revisar" });
  const toggle = main.getByRole("button", { name: /^Cola de revisión/ });
  const drawer = main.getByTestId("review-drawer");
  const pane = main.getByTestId("pdf-panel");
  await expect(queue).toBeHidden();
  await expect(pane).toBeVisible();
  const before = await pane.boundingBox();
  await toggle.click();
  await expect(queue.getByRole("option").first()).toBeVisible();
  const headerControls = drawer.locator("header").getByRole("group", { name: "Filtro de campos" });
  const initialCount = await queue.getByRole("option").count();
  await headerControls.getByRole("button", { name: "Por revisar" }).click();
  await expect(headerControls.getByRole("button", { name: "Por revisar" })).toHaveAttribute("aria-pressed", "true");
  expect(await queue.getByRole("option").count()).toBeLessThanOrEqual(initialCount);
  await headerControls.getByRole("button", { name: "Todos" }).click();
  await expect(drawer.locator("header").getByRole("progressbar", { name: "Campos revisados" })).toBeVisible();
  const grip = drawer.getByRole("slider", { name: "Altura de la cola de revisión" });
  const start = await grip.boundingBox();
  expect(start).not.toBeNull();
  const x = start!.x + start!.width / 2, y = start!.y + start!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y - 95, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => Number(await grip.getAttribute("aria-valuenow"))).toBeGreaterThan(43);
  expect((await pane.boundingBox())?.height).toBe(before?.height);
  await grip.focus();
  await page.keyboard.press("Home");
  await expect(grip).toHaveAttribute("aria-valuenow", "28");
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await expect(queue).toBeHidden();

  await toggle.click();
  await queue.hover();
  await page.mouse.wheel(0, 80);
  await expect.poll(() => queue.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.mouse.wheel(0, await queue.evaluate(element => element.scrollHeight));
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();

  await toggle.click();
  await queue.getByRole("option").last().evaluate(row => (row as HTMLElement).click());
  await expect.poll(() => queue.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await expect(queue.getByRole("option").last()).toHaveAttribute("aria-selected", "true");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const gripAtMinimum = (await grip.boundingBox())!;
  const dragX = gripAtMinimum.x + gripAtMinimum.width / 2;
  const dragY = gripAtMinimum.y + gripAtMinimum.height / 2;
  await page.mouse.move(dragX, dragY);
  await page.mouse.down();
  await page.mouse.move(dragX, dragY + 80, { steps: 5 });
  await page.mouse.up();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");

  await page.getByRole("radiogroup", { name: "Foco de revisión" }).getByRole("radio", { name: "Campos" }).click();
  await expect(grip).toHaveAttribute("aria-valuenow", "88");
  await toggle.click();

  await page.setViewportSize({ width: 390, height: 844 });
  const header = await page.getByRole("banner").boundingBox();
  const workspace = await main.boundingBox();
  expect(header!.height).toBeGreaterThan(80);
  expect(workspace!.y).toBeGreaterThanOrEqual(header!.y + header!.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test("el plano conserva la imagen al cambiar de foco y de zoom", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Usa el plano sintético servido por la web");
  await page.goto("/modelo?vista=revision");
  const panel = page.getByTestId("pdf-panel");
  const canvas = panel.getByLabel(/^Plano, página/);
  await expect.poll(() => canvas.evaluate(element => (element as HTMLCanvasElement).width)).toBeGreaterThan(0);

  const resize = (name: string) => canvas.evaluate(async (element, control) => {
    const drawing = element as HTMLCanvasElement;
    const start = drawing.getBoundingClientRect().width;
    const raster = drawing.width;
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(candidate =>
      candidate.getAttribute("aria-label") === control ||
      (candidate.closest('[aria-label="Foco de revisión"]') && candidate.textContent?.trim() === control));
    if (!button) throw new Error(`Falta el control ${control}`);
    button.click();
    const started = performance.now();
    let continuous = true;
    do {
      await new Promise(requestAnimationFrame);
      continuous &&= drawing.isConnected && drawing.width > 0 && getComputedStyle(drawing).visibility === "visible";
    } while (performance.now() - started < 3500 && (drawing.width === raster || performance.now() - started < 400));
    return { continuous, cssRatio: drawing.getBoundingClientRect().width / start, rasterChanged: drawing.width !== raster };
  }, name);

  const full = await resize("Plano");
  expect(full).toMatchObject({ continuous: true, rasterChanged: true });
  expect(full.cssRatio).toBeGreaterThan(2);
  const zoomed = await resize("Acercar");
  expect(zoomed).toMatchObject({ continuous: true, rasterChanged: true });
  expect(zoomed.cssRatio).toBeCloseTo(1.5, 1);
  const split = await resize("Todo");
  expect(split).toMatchObject({ continuous: true, rasterChanged: true });
  expect(split.cssRatio).toBeLessThan(.5);
});

test("una pieza muestra sus cotas citadas en Revisión", async ({ page }) => {
  test.setTimeout(90_000);
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Usa las cotas del ejemplo sintético");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/modelo?vista=revision");
  const viewer = page.getByTestId("ifc-viewer").first();
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  await viewer.getByRole("button", { name: "Elementos", exact: true }).click();
  await viewer.getByRole("button", { name: "Virola", exact: true }).click();
  const diameter = viewer.getByRole("button", { name: /^Diámetro de la virola: Ø 2000 mm/ });
  const value = diameter.getByText("Ø 2000 mm", { exact: true });
  await expect(value).toHaveCSS("opacity", "0.86");
  await expect(value).toHaveCSS("animation-duration", "0.3s");
});

test("movimiento reducido deja el inicio de sesión visible sin la intro",async({page})=>{
 await page.emulateMedia({reducedMotion:"reduce"});
 await page.goto("/",{waitUntil:"networkidle"});
 await expect(page.getByLabel("Usuario")).toBeVisible();
 await expect(page.getByRole("button",{name:/Saltar intro/})).toHaveCount(0);
});

test("Documentos reúne documentos, proyectos y familias y acepta soltar archivos",async({page})=>{
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
 await page.goto("/documentos?vista=documentos");
 await expect(page.getByText("Suelta aquí los planos GA y las hojas de datos")).toBeVisible();
 await page.getByLabel("Familia de destino").selectOption({label:"Intercambiadores"});
 await page.getByTestId("document-dropzone").evaluate(zone=>{
  const dt=new DataTransfer();dt.items.add(new File(["synthetic"],"GAD_E-210_revA.pdf",{type:"application/pdf"}));
  zone.dispatchEvent(new DragEvent("drop",{dataTransfer:dt,bubbles:true,cancelable:true}));
 });
 await expect(page.getByRole("button",{name:"GAD_E-210_revA.pdf",exact:true})).toBeVisible();
 await expect(page.getByLabel("Familia de GAD_E-210_revA")).toHaveValue("exchanger");
 await page.getByRole("button",{name:"elígelos en tu equipo"}).waitFor();
 await page.getByLabel("Elegir documentos").setInputFiles({name:"DS_P-501_revA.pdf",mimeType:"application/pdf",buffer:Buffer.from("synthetic")});
 await expect(page.getByRole("button",{name:"DS_P-501_revA.pdf",exact:true})).toBeVisible();
 await page.getByRole("radio",{name:"Proyectos",exact:true}).click();
 await expect(page).toHaveURL(/vista=proyectos/);
 await expect(page.getByText("Unidad de hidrotratamiento",{exact:true})).toBeVisible();
 await page.getByRole("navigation",{name:"Familias de documentos"}).getByRole("button",{name:/Tanques/}).click();
 await expect(page.getByText("Terminal de GNL",{exact:true})).toBeVisible();
 await expect(page.getByText("Unidad de hidrotratamiento",{exact:true})).toHaveCount(0);
 await page.goto("/familias");
 await expect(page).toHaveURL(/vista=familias/);
 await expect(page.getByRole("heading",{name:"Recipientes verticales",level:3})).toBeVisible();
 await expect(page.getByText("22 campos de revisión")).toBeVisible();
});

test("la biblioteca de bocetos añade los PDF sin desplazar documentos ya guardados", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
  await page.addInitScript(() => {
    const key = "trazia.catalogue.v1";
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, JSON.stringify({
      version: 4,
      state: {
        families: [{ id: "custom", name: "Familia propia" }, { id: "pump", name: "Bombas" }],
        projects: [{ id: "custom-project", name: "Proyecto propio" }],
        designs: [{ id: "custom-design", name: "Mi diseño", family: "custom", project: "custom-project" }],
      },
    }));
  });
  await page.goto("/documentos?vista=documentos");
  const links = page.getByRole("link", { name: /Abrir PDF de BC-/ });
  await expect(links).toHaveCount(72);
  await expect(page.getByText("Mi diseño", { exact: true })).toBeVisible();
  await page.reload();
  await expect(links).toHaveCount(72);
  await expect(page.getByLabel("Familia de Mi diseño")).toHaveValue("custom");

  const classification = page.getByRole("banner").getByRole("radiogroup", { name: "Clasificación de documentos" });
  await classification.getByRole("radio", { name: "Proyectos", exact: true }).click();
  await expect(classification.getByRole("radio", { name: "Proyectos", exact: true })).toBeChecked();
  await page.getByRole("button", { name: /Biblioteca de bocetos/ }).click();
  await expect(classification.getByRole("radio", { name: "Equipos", exact: true })).toBeChecked();
  await expect(links).toHaveCount(72);
  await expect(page.getByText("Mi diseño", { exact: true })).toHaveCount(0);
  await page.getByRole("navigation", { name: "Familias de documentos" }).getByRole("button", { name: /Bombas/ }).click();
  await expect(links).toHaveCount(4);
  for (const link of await links.all()) {
    const url = await link.getAttribute("href");
    expect(url).toMatch(/^\/demo\/(?:bocetos\/BOC_BC-P10[12]_revA|industriales\/BC-P10[34]-A)\.pdf$/);
    const pdf = await page.request.get(url!);
    expect(pdf.ok()).toBe(true);
    expect(pdf.headers()["content-type"]).toContain("application/pdf");
    expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  }
});

test("las 18 fichas de familia muestran sus cuatro diseños sin cambiar de pestaña", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/documentos?vista=familias");
  const galleries = page.locator("details").filter({ has: page.locator("ul[aria-label^='Diseños de ']") });
  await expect(galleries).toHaveCount(18);
  for (const gallery of await galleries.all()) {
    await gallery.locator("summary").click();
    const links = gallery.getByRole("link", { name: /Abrir PDF de BC-/ });
    await expect(links).toHaveCount(4);
    await expect(links.last()).toBeVisible();
    await gallery.locator("summary").click();
  }
  await expect(page).toHaveURL(/vista=familias/);
});

test("los separadores ciclónicos se abren como modelos IFC conceptuales", async ({ page }) => {
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/documentos?vista=familias");
  const family = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Separadores ciclónicos" }) });
  await expect(family.getByText("Conceptual 3D")).toBeVisible();
  await family.getByText("Ver 4 diseños", { exact: true }).click();
  await expect(family.getByRole("link", { name: /Abrir PDF de BC-CY/ })).toHaveCount(4);
  const trigger = family.getByRole("button", { name: "Ver 3D de BC-CY104" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Ciclón con tolva de recogida" });
  const viewer = dialog.getByTestId("ifc-viewer");
  await expect(viewer).toHaveAttribute("data-phase", "ready", { timeout: 25_000 });
  await expect(viewer).toHaveAttribute("data-products", "7");
  await expect(viewer).toHaveAttribute("data-provenance", "Datos sintéticos");
  await expect(viewer.locator("canvas")).toBeVisible();
  const download = dialog.getByRole("link", { name: "Descargar IFC" });
  await expect(download).toHaveAttribute("href", "/demo/industriales/BC-CY104-A.ifc");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("el Laboratorio 3D sigue accesible por URL",async({page})=>{
  test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "Esta prueba comprueba el catálogo o laboratorio de la demo sin API.");
 await page.goto("/lab/3d");
 await expect(page.getByRole("heading",{level:1,name:"Laboratorio 3D"})).toBeVisible();
 await page.goto("/lab/firma");
 await expect(page).toHaveURL(/\/#del-plano$/);
});

test("en la portada, la recipiente de demostración se ve sin bajar",async({page})=>{
 await page.emulateMedia({reducedMotion:"reduce"});
 await page.goto("/");
 await expect(page.getByTestId("landing-reference")).toContainText("V-101");
 await expect(page.getByTestId("landing-signature")).toHaveCount(0);
});

test("/reiniciar vacía lo guardado en el navegador y vuelve a Documentos",async({page})=>{
 test.skip(Boolean(process.env.NEXT_PUBLIC_API_URL), "El catálogo de la demo sin API guarda sus familias en el navegador.");
 await page.goto("/documentos?vista=documentos");
 await page.getByRole("button",{name:"Nueva familia",exact:true}).click();
 await page.getByRole("form",{name:"Nueva familia"}).getByLabel("Nombre").fill("Familia para reiniciar");
 await page.getByRole("button",{name:"Guardar",exact:true}).click();
 await expect(page.getByText("Familia para reiniciar").first()).toBeVisible();
 await page.goto("/reiniciar?destino=/documentos");
 await expect(page.getByRole("status")).toContainText("Demo reiniciada");
 await page.waitForURL("**/documentos");
 await page.goto("/documentos?vista=documentos");
 await expect(page.getByText("Familia para reiniciar")).toHaveCount(0);
 expect(await page.evaluate(()=>window.localStorage.getItem("trazia-design-edits"))).toBeNull();
});

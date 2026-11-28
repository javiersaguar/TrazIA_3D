import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const base = process.env.NEXT_PUBLIC_API_URL;
test.skip(!base, "Requiere modo API; la demo offline se comprueba en humo.spec.ts");

test("conserva un error recuperable y deshace valor y evidencia", async ({ page, request }) => {
  const originalResponse = await request.get(`${base}/equipment/V-101/revisions/A`);
  const original = (await originalResponse.json()).equipment.diameter;
  await page.goto("/revision");
  await page.getByRole("button", { name: /^Cola de revisión/ }).click();
  const row = page.locator('[data-row="diameter"]');
  await expect(row).toBeVisible();
  await row.click();
  await row.getByRole("button", { name: "Corregir", exact: true }).click();
  const input = row.getByRole("textbox", { name: /Nuevo valor/ });
  const save = row.getByRole("button", { name: "Guardar", exact: true });
  const note = row.getByRole("textbox", { name: "Nota de revisión (opcional)" });
  const changeSource = row.getByRole("button", { name: "Cambiar evidencia", exact: true });
  const controls = await Promise.all([input.boundingBox(), note.boundingBox(), changeSource.boundingBox(), save.boundingBox()]);
  const centers = controls.map(box => box ? box.y + box.height / 2 : -100);
  expect(Math.max(...centers) - Math.min(...centers)).toBeLessThan(2);
  await input.clear();
  await save.click();
  await expect(row.getByRole("alert")).toHaveText("Introduce un número válido.");
  await expect(input).toBeFocused();
  await input.fill("-1");
  await save.click();
  await expect(page.getByText(/No se ha guardado el cambio/)).toBeVisible();
  await expect(input).toBeVisible();
  await input.fill(String(original.value + 10));
  await note.fill("Nota de prueba de revisión");
  await changeSource.click();
  const document = row.getByRole("combobox", { name: "Documento original" });
  await document.selectOption("HDM-V101");
  await save.click();
  await expect(row.getByRole("alert")).toHaveText("Indica el nombre de la hoja.");
  await row.getByRole("textbox", { name: "Hoja", exact: true }).fill("Equipo");
  await save.click();
  await expect(row.getByRole("alert")).toHaveText(/Indica la celda/);
  await document.selectOption("GA-V101");
  const pageNumber = row.getByRole("spinbutton", { name: /^Página/ });
  await pageNumber.fill("2");
  await save.click();
  await expect(row.getByRole("alert")).toHaveText("Indica la página 1. Es la única del documento.");
  await pageNumber.fill("1");
  await save.click();
  await expect(row.getByRole("alert")).toHaveText("Describe dónde aparece el valor en el original.");
  await row.getByRole("textbox", { name: "Localizador", exact: true }).fill("Ensayo automatizado de la interfaz");
  const region = row.getByRole("textbox", { name: "Región (opcional)" });
  await region.fill("0,4 0,2 0,3 0,5");
  await save.click();
  await expect(row.getByRole("alert")).toContainText("cuatro coordenadas ordenadas");
  await region.fill("0,2 0,3 0,4 0,5");
  await save.click();
  await expect.poll(async () => (await (await request.get(`${base}/equipment/V-101/revisions/A`)).json()).equipment.diameter).toMatchObject({
    value: original.value + 10, explanation: "Nota de prueba de revisión",
    source: { document_id: "GA-V101", page: 1, locator: "Ensayo automatizado de la interfaz", bbox: [0.2, 0.3, 0.4, 0.5], channel: "humano" },
  });
  await expect(input).toHaveCount(0);
  await page.keyboard.press("Control+z");
  await expect.poll(async () => (await (await request.get(`${base}/equipment/V-101/revisions/A`)).json()).equipment.diameter).toEqual(original);
  const audits = (await (await request.get(`${base}/revisions/A/audit`)).json()).actions as { id: number; undo_of?: number | null }[];
  const undo = audits.at(-1)!;
  expect(audits.some((a) => a.id === undo.undo_of)).toBe(true);
});

test("la revisión persiste al recargar y se puede devolver a candidate", async ({ page, request }) => {
  await page.goto("/revision");
  await page.getByRole("button", { name: /^Cola de revisión/ }).click();
  await expect(page.getByRole("listbox", { name: "Campos por revisar" }).getByRole("option").first()).toBeVisible();
  await page.keyboard.press("j");
  await page.keyboard.press("a");
  await expect.poll(async () => (await (await request.get(`${base}/equipment/V-101/revisions/A`)).json()).equipment.diameter.state).toBe("accepted");
  await page.reload();
  await expect(page.getByText("1 de 22")).toBeVisible();
  const current = await request.get(`${base}/equipment/V-101/revisions/A`);
  const restored = await request.patch(`${base}/revisions/A/fields/diameter`, { headers: {
    "If-Match": current.headers()["etag"]!, "Idempotency-Key": `cleanup-${Date.now()}`,
  }, data: { state: "candidate", actor: "Prueba local" } });
  expect(restored.ok()).toBe(true);
  await page.reload();
  await expect(page.getByText("0 de 22")).toBeVisible();
});

test("el visor carga el IFC de la API y conserva sus productos", async ({ page }) => {
  const download = page.waitForResponse(response => response.url().startsWith(base!) && response.url().includes("/ifc?"));
  await page.goto("/revision");
  expect((await download).status()).toBe(200);
  await expect(page.locator('[data-testid="ifc-viewer"][data-phase="ready"]')).toHaveAttribute("data-products", "73");
});

test("un enlace directo abre la revisión exacta del modelo en un navegador nuevo", async ({ page, request }) => {
  test.setTimeout(100_000);
  test.skip(base === "/api/trazia", "Usa la API local de pruebas sin cuentas");
  const rows = await (await request.get(`${base}/equipment`)).json() as { tag: string; project_id: string; equipment_id: string; revisions: string[] }[];
  const model = rows.find((row) => row.tag === "80V01") ?? rows.find((row) => row.tag === "V-101")!;
  const label = model.revisions[0];
  const identity = `${model.project_id}:${model.equipment_id}:${label}`;
  await page.goto(`/modelo?resultado=${encodeURIComponent(identity)}`);
  await expect(page.getByRole("radio", { name: "Revisión", exact: true })).toBeChecked();
  await expect(page.getByRole("button", { name: /^Cola de revisión/ })).toBeVisible({ timeout: 45_000 });
  await page.getByRole("radio", { name: "Cambios", exact: true }).click();
  await page.getByRole("radio", { name: "Historial", exact: true }).click();
  const versions = page.getByTestId("version-history");
  await expect(versions.getByRole("link", { name: "IFC" }).first()).toHaveAttribute("href", /\/ifc\?draft=true/);
});

test("Documentos muestra los planos en un diálogo y conserva sus revisiones", async ({ page, request }) => {
  test.setTimeout(90_000);
  test.skip(base === "/api/trazia", "Usa la API local de pruebas sin cuentas");
  const rows = await (await request.get(`${base}/equipment`)).json() as {
    tag: string; project_id: string; revisions: string[];
    revision_meta: Record<string, { identity: string; documents?: { id: string; filename: string }[] }>;
  }[];
  const model = rows.find(row => row.tag === "80V01") ?? rows.find(row => row.tag === "V-101")!;
  const older = model.revision_meta[model.revisions[0]!];
  const file = older!.documents!.find(document => /^GAD.*\.pdf$/i.test(document.filename))!;
  await page.goto("/documentos");
  const classification = page.getByRole("radiogroup", { name: "Clasificación de documentos" });
  await expect(page.getByRole("banner").getByRole("radiogroup", { name: "Clasificación de documentos" })).toBeVisible();
  await expect(classification.getByRole("radio", { name: "Equipos", exact: true })).toBeChecked();
  await expect(page.getByRole("main").getByRole("radiogroup", { name: "Clasificación de documentos" })).toHaveCount(0);
  await classification.getByRole("radio", { name: "Proyectos", exact: true }).click();
  await expect(page).toHaveURL(/vista=proyectos/);
  await classification.getByRole("radio", { name: "Familias", exact: true }).click();
  await expect(page).toHaveURL(/vista=familias/);
  await classification.getByRole("radio", { name: "Equipos", exact: true }).click();

  const card = page.getByRole("listitem", { includeHidden: true }).filter({
    has: page.getByRole("button", { name: `Borrar ${model.tag} de ${model.project_id}`, exact: true, includeHidden: true }),
  });
  const trigger = card.getByRole("button", { name: new RegExp(`Planos y hojas de datos de ${model.tag} `) });
  const dialog = page.getByRole("dialog", { name: "Planos y hojas de datos" });
  await expect(trigger).toBeVisible();
  const before = await card.boundingBox();
  await trigger.click();
  await expect(dialog).toBeVisible();
  expect((await card.boundingBox())?.height).toEqual(before?.height);
  // Una entrada por versión, de la más reciente a la más antigua, cada una con sus documentos.
  const listing = dialog.getByRole("list", { name: `Versiones de ${model.tag}` });
  await expect(listing.locator(":scope > li")).toHaveCount(model.revisions.length);
  await expect(listing.locator(":scope > li").first()).toContainText(`Rev. ${model.revisions.at(-1)}`);
  const olderFiles = dialog.getByRole("list", { name: `Documentos de la Rev. ${model.revisions[0]}` });
  await expect(olderFiles).toContainText(file.filename);
  const modelLink = dialog.locator(`a[href="/modelo?vista=revision&resultado=${encodeURIComponent(older!.identity)}"]`);
  await expect(modelLink).toHaveText(/Ver 3D/);
  const pdf = dialog.getByRole("link", { name: `Abrir original de ${file.filename} en una pestaña nueva` });
  const source = await request.get((await pdf.getAttribute("href"))!);
  expect(source.ok()).toBe(true);
  expect(source.headers()["content-type"]).toContain("application/pdf");

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await trigger.click();
  await expect(dialog).toBeVisible();
  const bounds = (await dialog.boundingBox())!;
  expect(bounds.x).toBeGreaterThan(0);
  expect(bounds.x + bounds.width).toBeLessThan(390);
  expect(Math.abs(bounds.y + bounds.height / 2 - 422)).toBeLessThan(4);
  const thumb = modelLink.locator("xpath=ancestor::li[1]").getByTestId("ifc-thumbnail");
  await expect(thumb).toHaveCSS("width", "44px");
  await expect(thumb).toHaveCSS("height", "44px");
  await modelLink.click();
  await expect(page).toHaveURL(new RegExp(encodeURIComponent(older!.identity)));
  await expect(page.getByRole("radio", { name: "Revisión", exact: true })).toBeChecked();
});

test("Documentos abre el modelo y Cambios compara sus versiones en 3D", async ({ page, request }) => {
  test.setTimeout(155_000);
  test.skip(base === "/api/trazia", "Usa la API local de pruebas sin cuentas");
  const rows = await (await request.get(`${base}/equipment`)).json() as { tag: string; project_id: string; revisions: string[] }[];
  const model = rows.find((row) => row.tag === "80V01") ?? rows.find((row) => row.tag === "V-101")!;
  await page.goto("/documentos");
  await expect(page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link", { name: "Pipeline" })).toHaveCount(0);
  // La tarjeta más interior del equipo: el modo sintético repite el TAG en varias revisiones.
  const card = page.getByRole("heading", { name: model.tag, exact: true }).first().locator("xpath=ancestor::li[1]");
  await card.getByRole("button", { name: "Ver modelo 3D" }).click();
  await expect(page.getByRole("radio", { name: "Revisión", exact: true })).toBeChecked();
  await expect(page.getByRole("button", { name: /^Cola de revisión/ })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("radio", { name: "Modelo 3D", exact: true })).toHaveCount(0);
  await page.getByRole("radio", { name: "Cambios", exact: true }).click();
  await page.getByRole("radio", { name: "Proponer un cambio", exact: true }).click();
  await expect(page.getByTestId("design-form")).toBeVisible({ timeout: 45_000 });
  await page.getByRole("radio", { name: "Historial", exact: true }).click();
  const versions = page.getByTestId("version-history").getByRole("list", { name: "Versiones del equipo" });
  await expect(versions.locator(":scope > li")).toHaveCount(model.revisions.length);
  if (model.revisions.length > 1) {
    const [previous, latest] = model.revisions.slice(-2);
    await versions.getByRole("button", { name: `Comparar con Rev ${previous}` }).click();
    const compare = page.getByTestId("version-compare");
    await expect(compare.getByRole("combobox", { name: "Hasta" })).toHaveValue(latest!);
    const morph = compare.getByTestId("revision-morph");
    await expect(morph).toHaveAttribute("data-phase", "ready", { timeout: 60_000 });
    await morph.getByRole("slider").fill("1");
    await expect(morph).toHaveAttribute("data-progress", "1.000");
    await expect(compare.getByRole("complementary", { name: "Cambios entre versiones" })).toContainText(`Rev ${previous} → Rev ${latest}`);
    await compare.getByRole("button", { name: "Ver lado a lado" }).click();
    await expect(morph.locator("canvas")).toHaveCount(2);
  }
});

test("Pipeline consume SSE y no utiliza el temporizador simulado", async ({ page, request }) => {
  await page.goto("/pipeline?vista=detalle");
  await page.getByLabel("Estrategia de lectura").selectOption("b_reglas");
  const events = page.waitForResponse(response => response.url().startsWith(base!) && response.url().endsWith("/events"));
  await page.getByRole("button", { name: "Procesar demo", exact: true }).click();
  expect((await events).status()).toBe(200);
  await expect(page.getByRole("cell", { name: /IFC4 DRAFT almacenado/ })).toBeVisible({ timeout: 30_000 });
  const identity = (await page.getByText(/Trabajo [0-9a-f-]+/).innerText()).replace("Trabajo ", "");
  const job = await (await request.get(`${base}/jobs/${identity}`)).json();
  expect(job.status).toBe("done");
  expect(job.run.seconds).toBeGreaterThan(0);
  await expect(page.getByText("Repetición simulada", { exact: false })).toHaveCount(0);
});

test("carga un equipo nuevo, recupera su trabajo y consulta el IFC y su evidencia", async ({ page, request }, info) => {
  test.setTimeout(90_000);
  const fixture = info.outputPath("synthetic");
  execFileSync("uv", ["run", "--no-sync", "python", "-m", "synthetic", "--casos", "1", "--estilos", "rotulado", "--salida", fixture],
    { cwd: resolve(__dirname, "../../..") });
  const inputs = resolve(fixture, "rotulado");
  const [tag] = readdirSync(inputs);
  const pdf = resolve(inputs, tag!, `GAD_${tag}_rev1.pdf`);
  const xlsx = resolve(inputs, tag!, `HDM_${tag}_rev1.xlsx`);
  const project = `ENSAYO-${Date.now()}`;

  await page.goto("/pipeline?vista=detalle");
  await page.getByLabel("Estrategia de lectura").selectOption("b_reglas");
  await page.getByLabel("Documentos para procesar").setInputFiles([pdf, xlsx]);
  await expect(page.getByLabel("Tag del equipo")).toHaveValue(tag!);
  await expect(page.getByLabel("Revisión", { exact: true })).toHaveValue("1");
  await page.getByLabel("Proyecto", { exact: true }).fill(project);
  await page.getByRole("button", { name: "Procesar documentos", exact: true }).click();
  await expect(page).toHaveURL(/trabajo=[\da-f-]+/);
  await page.reload();
  const result = page.getByRole("link", { name: "Ver resultado IFC DRAFT" });
  await expect(result).toBeVisible({ timeout: 25_000 });
  await expect(page.getByRole("cell", { name: /IFC4 DRAFT almacenado/ })).toBeVisible();
  await result.click();
  await expect(page.getByRole("heading", { name: `${tag} · Versión 1` })).toBeVisible();
  const identity = `${project}:${tag}:1`;
  const record = await request.get(`${base}/revisions/${encodeURIComponent(identity)}`);
  expect(record.ok()).toBe(true);
  expect(record.headers()["etag"]).toBe('"1"');
  const revision = await record.json();
  expect(revision.dataset).toBe("synthetic");
  expect(revision.approval).toBeNull();
  const original = await request.get((await page.getByRole("link", { name: `GAD_${tag}_rev1.pdf`, exact: true }).first().getAttribute("href"))!);
  expect(await original.body()).toEqual(readFileSync(pdf));
  const ifc = await request.get((await page.getByRole("link", { name: "Descargar IFC en borrador" }).getAttribute("href"))!);
  expect(await ifc.text()).toContain("ISO-10303-21;");
  await expect(page.getByRole("heading", { name: "Datos extraídos" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /pág\. 1/ }).first()).toBeVisible();
  await page.getByRole("link", { name: "Ver modelo 3D" }).click();
  await expect(page.getByRole("radio", { name: "Revisión", exact: true })).toBeChecked();
  await expect(page.locator('[data-testid="ifc-viewer"][data-phase="ready"]')).toBeVisible({ timeout: 30_000 });
});


test("el copiloto muestra citas y escribir preguntas no modifica la revisión", async ({ page, request }) => {
  const before = await (await request.get(`${base}/equipment/V-101/revisions/A`)).json();
  await page.route("**/copiloto", async route => {
    const body = route.request().postDataJSON();
    expect(body.path).toBe("diameter");
    expect(body.question).toContain("aceptar");
    await route.fulfill({ json: {
      abstained: false, reason: null, read_only: true, model: "fixture de interfaz",
      revision_id: "DEMO-PLANT:vessel-001:A", revision_version: 1,
      input_sha256: "0".repeat(64), prompt_sha256: "1".repeat(64), tools_used: ["read_evidence"],
      statements: [{ text: "Respuesta de prueba de interfaz: diámetro 2000 mm.", citations: ["test-source"] }], proposals: [],
      citations: [{ id: "test-source", kind: "evidence", title: "Original de prueba · GAD_V-101_revA.pdf", excerpt: "DIAMETER = 2000 mm",
        path: "diameter", document_id: "GA-V101", filename: "GAD_V-101_revA.pdf", page: 1, bbox: [0.4, 0.2, 0.6, 0.3],
        sha256: "2".repeat(64), sheet: null, cell: null, original_verified: true }],
      run: { strategy: "fixture", providers: [], seconds: 0.1, external_calls: 0, cost_eur: 0, accounting_complete: true },
    } });
  });
  await page.goto("/revision");
  await page.getByRole("button", { name: /^Cola de revisión/ }).click();
  await expect(page.getByRole("listbox", { name: "Campos por revisar" }).getByRole("option").first()).toBeVisible();
  await page.keyboard.press("j");
  await page.getByRole("button", { name: "Copiloto", exact: true }).click();
  await page.getByRole("textbox", { name: "Tu mensaje" }).pressSequentially("Antes de aceptar, explica la fuente");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();
  await expect(page.getByTestId("copilot-answer")).toContainText("Respuesta de prueba de interfaz");
  await page.getByRole("button", { name: "Abrir fuente 1", exact: true }).click();
  await expect(page.getByText("DIAMETER = 2000 mm", { exact: true })).toBeVisible();
  await expect(page.getByText("Original verificado por SHA-256", { exact: true })).toBeVisible();
  expect(await (await request.get(`${base}/equipment/V-101/revisions/A`)).json()).toEqual(before);
});

test("un modelo no disponible muestra el error y no sustituye la respuesta por reglas", async ({ page }) => {
  await page.route("**/copiloto", route => route.fulfill({ status: 503, json: { detail: "Groq no disponible para esta prueba" } }));
  await page.goto("/revision");
  await page.getByRole("button", { name: /^Cola de revisión/ }).click();
  await expect(page.getByRole("listbox", { name: "Campos por revisar" }).getByRole("option").first()).toBeVisible();
  await page.keyboard.press("j");
  await page.getByRole("button", { name: "Copiloto", exact: true }).click();
  await page.getByRole("textbox", { name: "Tu mensaje" }).fill("Explica la fuente");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Copiloto" }).getByRole("alert")).toContainText("Groq no disponible");
  await expect(page.getByText("Qué pasa si está mal", { exact: true })).toHaveCount(0);
});

async function mockVoiceDevices(page: Page, speechDuration: number) {
  await page.addInitScript(duration => {
      navigator.mediaDevices.getUserMedia = async () => {
        const audio = new AudioContext();
        const destination = audio.createMediaStreamDestination();
        const tone = audio.createOscillator();
        tone.connect(destination);
        await audio.resume();
        const start = audio.currentTime + (duration ? 0.22 : 0);
        tone.start(start);
        if (duration) tone.stop(start + duration);
        const root = document.documentElement;
        root.dataset.micOpened = String(Number(root.dataset.micOpened ?? 0) + 1);
        return destination.stream;
      };
      const speech = window.speechSynthesis;
      Object.defineProperty(window, "SpeechSynthesisUtterance", {
        value: class { constructor(public text: string) {} },
      });
      speech.getVoices = () => [
        { lang: "es-ES", localService: false },
        { lang: "es-ES", localService: true },
      ] as SpeechSynthesisVoice[];
      let current: SpeechSynthesisUtterance | undefined;
      speech.speak = utterance => {
        current = utterance;
        document.documentElement.dataset.spoken = utterance.text;
        document.documentElement.dataset.localVoice = String(utterance.voice?.localService);
        utterance.onstart?.(new Event("start") as SpeechSynthesisEvent);
      };
      speech.cancel = () => {
        current = undefined;
        delete document.documentElement.dataset.spoken;
      };
      window.addEventListener("finish-test-speech", () => {
        const utterance = current;
        current = undefined;
        utterance?.onend?.(new Event("end") as SpeechSynthesisEvent);
      });
  }, speechDuration);
}

test("el chat manda la orden al editor con Enter", async ({ page, request }) => {
  const before = await (await request.get(`${base}/equipment/V-101/revisions/A`)).json();
  await page.route("**/copiloto", route => {
    throw new Error(`La orden llegó al servicio de consultas: ${route.request().url()}`);
  });
  await page.goto("/modelo?vista=revision");
  await page.getByRole("button", { name: "Copiloto", exact: true }).click();
  await expect(page.getByTestId("copilot-scope")).toContainText("V-101");
  const message = page.getByRole("textbox", { name: "Tu mensaje" });
  await message.fill("Quiero que el diámetro de la virola sea de 2110 mm, cámbialo");
  await expect(page.getByRole("button", { name: "Enviar cambio" })).toBeEnabled();
  await message.press("Enter");
  // Una orden completa se manda a hacer: se abre el editor con el valor rellenado, sin aplicarlo.
  await expect(page).toHaveURL(/\/modelo\?vista=cambios&seccion=proponer$/, { timeout: 15_000 });
  await expect(page.getByText("Hemos rellenado 1 valor", { exact: false })).toBeVisible();
  expect((await (await request.get(`${base}/equipment/V-101/revisions/A`)).json()).equipment).toEqual(before.equipment);
});

test.describe("voz del copiloto", () => {
  test("dicta en el dispositivo cuando la API de voz está desactivada", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "SpeechRecognition", {
        value: class {
          static async available(options: { langs: string[]; processLocally: boolean }) {
            return options.processLocally && options.langs.includes("es-ES") ? "available" : "unavailable";
          }
          processLocally = false;
          lang = "";
          onresult?: (event: { results: { transcript: string }[][] }) => void;
          onend?: () => void;
          start() {
            if (!this.processLocally || this.lang !== "es-ES") throw new Error("Se necesita el dictado local.");
          }
          stop() {
            this.onresult?.({ results: [[{ transcript: "Consulta el diámetro" }]] });
            this.onend?.();
          }
          abort() { this.onend?.(); }
        },
      });
    });
    let envios = 0;
    await page.route(/\/copiloto\/voice\?/, route => {
      if (route.request().method() === "POST") envios++;
      return route.fulfill({ json: { available: false } });
    });
    await page.goto("/modelo");
    await page.getByRole("button", { name: "Copiloto", exact: true }).click();
    await page.getByRole("button", { name: "Dictar", exact: true }).click();
    await page.getByRole("button", { name: "Terminar dictado" }).click();
    await expect(page.getByRole("textbox", { name: "Tu mensaje" })).toHaveValue("Consulta el diámetro");
    expect(envios).toBe(0);
  });

  test("una orden dictada con «Dictar» abre el editor sin pulsar «Enviar cambio»", async ({ page, request }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "SpeechRecognition", {
        value: class {
          static async available(options: { langs: string[]; processLocally: boolean }) {
            return options.processLocally && options.langs.includes("es-ES") ? "available" : "unavailable";
          }
          processLocally = false;
          lang = "";
          onresult?: (event: { results: { transcript: string }[][] }) => void;
          onend?: () => void;
          start() {
            if (!this.processLocally || this.lang !== "es-ES") throw new Error("Se necesita el dictado local.");
          }
          stop() {
            // Chrome escribe los millares con punto: «2.110 milímetros».
            this.onresult?.({ results: [[{ transcript: "Cambia el diámetro a 2.110 milímetros" }]] });
            this.onend?.();
          }
          abort() { this.onend?.(); }
        },
      });
    });
    await page.route(/\/copiloto\/voice\?/, route => route.fulfill({ json: { available: false } }));
    await page.route("**/copiloto", route => {
      throw new Error(`La orden llegó al servicio de consultas: ${route.request().url()}`);
    });
    const before = await (await request.get(`${base}/equipment/V-101/revisions/A`)).json();
    await page.goto("/modelo?vista=revision");
    await page.getByRole("button", { name: "Copiloto", exact: true }).click();
    await expect(page.getByTestId("copilot-scope")).toContainText("V-101");
    await page.getByRole("button", { name: "Dictar", exact: true }).click();
    await page.getByRole("button", { name: "Terminar dictado" }).click();
    await expect(page).toHaveURL(/\/modelo\?vista=cambios&seccion=proponer$/, { timeout: 15_000 });
    await expect(page.getByText("«2.110» se lee como 2110 mm", { exact: false })).toBeVisible();
    expect((await (await request.get(`${base}/equipment/V-101/revisions/A`)).json()).equipment).toEqual(before.equipment);
  });

  test("mantiene los accesos de voz durante la descarga del paquete de español", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "SpeechRecognition", {
        value: class {
          static async available() {
            return document.documentElement.dataset.spanishReady === "true" ? "available" : "downloading";
          }
          static async install() { return false; }
        },
      });
    });
    await page.route(/\/copiloto\/voice\?/, route => route.fulfill({ json: { available: false } }));
    await page.goto("/modelo");
    await page.getByRole("button", { name: "Copiloto", exact: true }).click();
    const dictate = page.getByRole("button", { name: "Dictar", exact: true });
    const voice = page.getByRole("button", { name: "Hablar por voz", exact: true });
    await expect(page.getByText("El navegador está descargando el paquete de español.")).toBeVisible();
    await expect(dictate).toBeVisible();
    await expect(dictate).toBeDisabled();
    await voice.click();
    const panel = page.getByRole("region", { name: "Conversación por voz" });
    const speak = panel.getByRole("button", { name: "Hablar", exact: true });
    await expect(speak).toBeDisabled();
    await page.evaluate(() => { document.documentElement.dataset.spanishReady = "true"; });
    await panel.getByRole("button", { name: "Comprobar dictado" }).click();
    await expect(speak).toBeEnabled();
    await panel.getByRole("button", { name: "Volver a texto" }).click();
    await expect(dictate).toBeEnabled();
  });

  test("deja el dictado editable y lee en voz alta solo al pulsar", async ({ page }) => {
    await mockVoiceDevices(page, 0);
    let questions = 0;
    await page.route(/\/copiloto\/voice\?/, async route => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({ json: { available: true } });
        return;
      }
      expect(route.request().headers()["content-type"]).toMatch(/^multipart\/form-data/);
      expect(route.request().postDataBuffer()?.length).toBeGreaterThan(250);
      await route.fulfill({ json: { text: "¿Cuál es el diámetro?" } });
    });
    const statement = "El diámetro de prueba es 2000 mm.";
    await page.route("**/copiloto", async route => {
      questions += 1;
      expect(route.request().postDataJSON().question).toBe("¿Cuál es el diámetro interior?");
      await route.fulfill({ json: {
        abstained: false, model: "fixture", statements: [{ text: statement, citations: [] }],
        proposals: [], citations: [], run: { seconds: 0 },
      } });
    });
    await page.goto("/proyecto");
    await page.getByRole("button", { name: "Copiloto", exact: true }).click();
    const message = page.getByRole("textbox", { name: "Tu mensaje" });
    await page.getByRole("button", { name: "Dictar", exact: true }).click();
    const recording = page.getByRole("button", { name: "Transcribir", exact: true });
    await expect(recording).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Grabando" })).toBeVisible();
    await recording.click();
    await expect(message).toHaveValue("¿Cuál es el diámetro?");
    expect(questions).toBe(0);
    await message.fill("¿Cuál es el diámetro interior?");
    await page.getByRole("button", { name: "Preguntar", exact: true }).click();
    const reading = page.getByRole("button", { name: "Escuchar respuesta" });
    await expect(reading).toBeVisible();
    const documentRoot = page.locator("html");
    await expect(documentRoot).not.toHaveAttribute("data-spoken");
    await reading.click();
    await expect(documentRoot).toHaveAttribute("data-spoken", statement);
    await expect(documentRoot).toHaveAttribute("data-local-voice", "true");
    await page.getByRole("button", { name: "Detener lectura" }).click();
    await expect(documentRoot).not.toHaveAttribute("data-spoken");
  });

  test("conversa con el avatar por turnos y deja el diálogo escrito en el chat", async ({ page }) => {
    await mockVoiceDevices(page, 1.1);
    let turns = 0;
    await page.route(/\/copiloto\/voice\?/, route => route.fulfill({ json: route.request().method() === "GET"
      ? { available: true } : { text: "¿Cuál es el diámetro del recipiente?" } }));
    const answer = "El diámetro interior es de dos metros.";
    await page.route("**/copiloto", async route => {
      turns += 1;
      expect(route.request().postDataJSON().question).toBe("¿Cuál es el diámetro del recipiente?");
      await route.fulfill({ json: {
        abstained: false, model: "fixture", statements: [{ text: answer, citations: [] }],
        proposals: [], citations: [], run: { seconds: 0 },
      } });
    });

    await page.goto("/proyecto");
    await page.getByRole("button", { name: "Copiloto", exact: true }).click();
    const message = page.getByRole("textbox", { name: "Tu mensaje" });
    await message.fill("Mi borrador escrito");
    await page.getByRole("button", { name: "Hablar por voz" }).click();
    const panel = page.getByRole("region", { name: "Conversación por voz" });
    const status = panel.getByRole("status");
    await expect(panel.locator("canvas")).toBeVisible();
    await expect(message).toHaveCount(0);
    await expect(panel.getByRole("button", { name: "Enviar turno" })).toHaveCount(0);
    // Escucha nada más entrar; el turno lo cierra una pausa de 3 s, sin pulsar nada.
    await expect(status).toHaveText("Te escucho");
    await expect(status).toHaveText("Respondiendo", { timeout: 10_000 });
    expect(turns).toBe(1);
    const documentRoot = page.locator("html");
    await expect(documentRoot).toHaveAttribute("data-spoken", answer);
    await expect(documentRoot).toHaveAttribute("data-mic-opened", "1");
    const thread = page.getByTestId("copilot-thread");
    await expect(thread).toContainText("¿Cuál es el diámetro del recipiente?");
    await expect(thread).toContainText(answer);

    await page.evaluate(() => window.dispatchEvent(new Event("finish-test-speech")));
    await expect(status).toHaveText("Te escucho");
    await expect(documentRoot).toHaveAttribute("data-mic-opened", "2");
    await panel.getByRole("button", { name: "Pausar" }).click();
    await expect(status).toHaveText("Micrófono en pausa");
    await panel.getByRole("button", { name: "Volver a texto" }).click();
    await expect(message).toHaveValue("Mi borrador escrito");
    await expect(thread).toContainText(answer);
    expect(turns).toBe(1);
  });
});

test("una orden dictada pasa por propuesta, IFC y confirmación DRAFT en la revisión activa", async ({ page, request }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => {
    let installed = false;
    let spoken = false;
    Object.defineProperty(window, "SpeechRecognition", {
      value: class {
        static async available(options: { langs: string[]; processLocally: boolean }) {
          if (!options.processLocally || options.langs[0] !== "es-ES") return "unavailable";
          return installed ? "available" : "downloadable";
        }
        static async install(options: { langs: string[] }) {
          installed = options.langs[0] === "es-ES";
          return installed;
        }
        processLocally = false;
        continuous = false;
        lang = "";
        onresult?: (event: { results: { transcript: string }[][] }) => void;
        onend?: () => void;
        start() {
          if (!installed || !this.processLocally || this.lang !== "es-ES") throw new Error("Se necesita el dictado local.");
          if (this.continuous) throw new Error("El modo voz usa el mismo reconocimiento por frases que el dictado.");
          // Una frase por sesión, como Chrome: la primera escucha la recibe y las siguientes solo oyen silencio.
          if (!spoken) {
            spoken = true;
            setTimeout(() => {
              this.onresult?.({ results: [[{ transcript: "Cambia el diámetro a 2100 mm" }]] });
              this.onend?.();
            }, 100);
          }
        }
        stop() {
          this.onresult?.({ results: [[{ transcript: "Cambia el diámetro a 2100 mm" }]] });
          this.onend?.();
        }
        abort() { this.onend?.(); }
      },
    });
  });
  await page.route(/\/copiloto\/voice\?/, route => {
    expect(route.request().method()).toBe("GET");
    return route.fulfill({ json: { available: false } });
  });
  await page.route("**/copiloto", route => {
    throw new Error(`Una orden de diseño no es una consulta: ${route.request().url()}`);
  });
  const project = process.env.PW_EXTERNAL_API ? "DEMO-PLANT" : "ENSAYO-VOZ";
  await page.goto("/modelo?vista=revision");
  await page.getByRole("banner").getByLabel("Equipo", { exact: true }).selectOption(`${project}:V-101`);
  await page.getByRole("button", { name: "Copiloto", exact: true }).click();
  const latestRadio = page.getByRole("main").getByRole("radiogroup", { name: "Revisión", exact: true }).getByRole("radio").last();
  const label = (await latestRadio.innerText()).replace(/^rev\.?\s+/i, "").trim();
  await latestRadio.click();
  await expect(page.getByTestId("copilot-scope")).toContainText(`${project} · V-101 · rev. ${label}`);
  const baseRevision = `${base}/equipment/V-101/revisions/${encodeURIComponent(label)}?project_id=${project}`;
  const before = await (await request.get(baseRevision)).json();
  await page.locator("summary").filter({ hasText: "Reglas locales" }).click();
  await expect(page.getByText(/Sin credenciales de proveedores/)).toBeVisible();
  await page.getByRole("button", { name: "Instalar dictado en español" }).click();
  await page.getByRole("button", { name: "Hablar por voz" }).click();
  const panel = page.getByRole("region", { name: "Conversación por voz" });
  await expect(panel.getByRole("status")).toHaveText("Te escucho");
  // En voz no hay tarjeta de borrador: la orden completa abre el editor sin más clics.
  await expect(page).toHaveURL(/\/modelo\?vista=cambios&seccion=proponer$/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Borrador del Copiloto" })).toHaveCount(0);
  await expect(page.getByText("Hemos rellenado 1 valor", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Revisión base")).toHaveValue(label);
  // Sin sesión no hay quien propone: se escribe y se comprueba con el botón.
  await page.getByLabel("Persona que propone").fill("Ensayo de voz");
  await page.getByRole("button", { name: "Comprobar cambios", exact: true }).click();
  await page.getByRole("button", { name: "Ver resultado en 3D", exact: true }).click();
  const confirm = page.getByRole("button", { name: /Confirmar y crear/ });
  await expect(confirm).toBeEnabled({ timeout: 60_000 });
  await expect(page.getByTestId("ifc-viewer")).toHaveAttribute("data-phase", "ready", { timeout: 30_000 });
  expect((await (await request.get(baseRevision)).json()).equipment.diameter.value).toBe(before.equipment.diameter.value);
  const applied = page.waitForResponse(r => r.url().endsWith("/apply") && r.request().method() === "POST");
  await confirm.click();
  const response = await applied;
  expect(response.ok()).toBe(true);
  const appliedRevision = await response.json();
  const model = await (await request.get(`${base}/revisions/${encodeURIComponent(appliedRevision.revision_id)}`)).json();
  expect(model.equipment.diameter.value).toBe(2100);
  expect(model.approval).toBeNull();
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => { vi.resetModules(); vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000"); });
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("borrado por la API", () => {
  it("borra una revisión con su ETag y una clave de idempotencia", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ id: "P:v:B" })));
    vi.stubGlobal("fetch", fetcher);
    const { deleteRevision } = await import("./client");
    await deleteRevision("P:v:B", 3, "clave");
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain(`/revisions/${encodeURIComponent("P:v:B")}`);
    expect(init.method).toBe("DELETE");
    expect(init.headers).toEqual({ "Idempotency-Key": "clave", "If-Match": '"3"' });
  });

  it("muestra el motivo del 409 tal como lo explica la API", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ detail: "No se puede borrar plano.pdf: lo cita la revisión guardada P:v:A." }), { status: 409 })));
    const { deleteDocument } = await import("./client");
    await expect(deleteDocument("doc-1")).rejects.toMatchObject({ status: 409, message: expect.stringContaining("lo cita la revisión") });
  });
});

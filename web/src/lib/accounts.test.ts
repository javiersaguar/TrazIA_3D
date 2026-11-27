import { afterEach, describe, expect, it, vi } from "vitest";
import { enterAccount } from "./accounts";

afterEach(() => vi.unstubAllGlobals());

describe("mensajes de inicio de sesión", () => {
  it("distingue un fallo del túnel de un fallo de credenciales", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response("<html>ngrok</html>", { status: 502 }))
      .mockResolvedValueOnce(Response.json({ detail: "Usuario o contraseña incorrectos." }, { status: 401 }));
    vi.stubGlobal("fetch", fetch);

    const credentials = { username: "prueba", password: "ficticia" };
    await expect(enterAccount(credentials)).rejects.toThrow("temporalmente fuera de línea");
    await expect(enterAccount(credentials)).rejects.toThrow("Usuario o contraseña incorrectos.");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

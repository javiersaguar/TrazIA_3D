import { describe, expect, it } from "vitest";
import type { MatchedFicha } from "@/lib/api/client";
import { NEW_FICHA, nextRevision, planUpload, sha256 } from "./upload-target";

const ficha = (project: string, revisions: [string, string[]][]): MatchedFicha => ({
  project_id: project, equipment_id: "ko-v-9207", tag: "KO-V-9207", dataset: "synthetic",
  revisions: revisions.map(([label, hashes]) => ({ label, approved: false, documents: hashes.map(sha256 => ({ filename: "a.pdf", sha256 })) })),
});

describe("destino de una subida", () => {
  it("propone la siguiente etiqueta libre", () => {
    expect(nextRevision(["0", "1"], "1")).toBe("2");
    expect(nextRevision(["A", "B"], "a")).toBe("C");
    expect(nextRevision(["P1"], "P1")).toBe("P1-2");
    expect(nextRevision(["0"], "3")).toBe("3");
  });

  it("añade una versión a la única ficha con ese código", () => {
    expect(planUpload([ficha("ENSAYO", [["0", ["h0"]]])], "", "1", ["h1"])).toMatchObject({ kind: "version", revision: "1" });
    expect(planUpload([], "", "0", null)).toEqual({ kind: "new" });
  });

  it("pide elegir cuando el código está en varios proyectos", () => {
    const fichas = [ficha("ENSAYO", []), ficha("OTRO", [])];
    expect(planUpload(fichas, "", "0", null).kind).toBe("choose");
    expect(planUpload(fichas, "OTRO:ko-v-9207", "0", null)).toMatchObject({ kind: "version", ficha: { project_id: "OTRO" } });
    expect(planUpload(fichas, NEW_FICHA, "0", null).kind).toBe("new");
  });

  it("no duplica el mismo archivo y conserva la versión anterior si cambia", () => {
    const fichas = [ficha("ENSAYO", [["0", ["h0", "h0b"]]])];
    expect(planUpload(fichas, "", "0", ["h0"])).toMatchObject({ kind: "duplicate", revision: "0" });
    expect(planUpload(fichas, "", "0", ["otro"])).toMatchObject({ kind: "renamed", requested: "0", revision: "1" });
  });

  it("calcula el SHA-256 como la API", async () => {
    expect(await sha256(new Blob(["abc"]))).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});

import { describe, expect, it } from "vitest";
import type { Revision } from "@/lib/types/revision";
import { versionEntries, versionOrigin } from "./version-list";

const record = (extra: Partial<Revision>) => ({ dataset: "real", documents: [], ...extra }) as unknown as Revision;

describe("historial de versiones", () => {
  it("explica el origen de cada revisión", () => {
    expect(versionOrigin(undefined)).toBe("Lectura del plano GA");
    expect(versionOrigin(record({ run: { strategy: "b_reglas" } as Revision["run"] }))).toBe("Lectura del plano GA · b_reglas");
    expect(versionOrigin(record({
      derived_from: { kind: "cambio_diseno", revision_id: "P:v-101:1", input_sha256: "0".repeat(64), proposal_id: "p1", order_document_id: "o1" },
    }))).toBe("Cambio de diseño sobre Rev 1");
    expect(versionOrigin(record({
      derived_from: { kind: "reversion", revision_id: "P:v-101:2", input_sha256: "0".repeat(64), proposal_id: "p2", order_document_id: "o2" },
    }))).toBe("Reversión desde Rev 2");
  });

  it("ordena de la última a la primera con aprobación y guardados", () => {
    const entries = versionEntries(
      {
        project_id: "P", equipment_id: "v-101", revisions: ["1", "2"],
        revision_meta: {
          "1": { version: 3, dataset: "real", identity: "P:v-101:1", ifcUrl: "/revisions/P%3Av-101%3A1/ifc?draft=true&v=3", documents: [{ id: "GA", filename: "ga.pdf" }] },
        },
      },
      { "1": record({ approval: { reviewer: "Revisora", timestamp: "2026-11-20T10:00:00Z", input_sha256: "0".repeat(64) } }) },
    );
    expect(entries.map((entry) => entry.label)).toEqual(["2", "1"]);
    expect(entries[0]).toMatchObject({ identity: "P:v-101:2", saves: null, approval: null, ifcUrl: null, documents: [] });
    expect(entries[1]).toMatchObject({ saves: 3, dataset: "real", approval: { reviewer: "Revisora" }, documents: [{ id: "GA" }] });
  });
});

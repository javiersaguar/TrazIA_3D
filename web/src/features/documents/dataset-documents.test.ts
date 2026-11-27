import { expect, it } from "vitest";
import type { EquipmentRow } from "@/lib/mock/api";
import { groupDatasetDocuments, homonymTags, type LotRow } from "./dataset-documents";

const lot: LotRow = {
  proyecto: "PROYECTO-A", tag: "V-101", revision: "B", documentos: ["plano-B.pdf", "vesor.pdf"],
  estado: "faltan_datos", error: null, familia: null, boquillas: null, segundos: null,
};

const equipment: EquipmentRow = {
  project_id: "PROYECTO-A", equipment_id: "v-101", tag: "V-101", kind: "vertical_vessel", area: "",
  revisions: ["A"], status: "draft", illustrative: false, ifcUrl: "/ifc-a",
  revision_meta: { A: { identity: "PROYECTO-A:v-101:A", dataset: "synthetic", version: 1,
    ifcUrl: "/ifc-a", documents: [{ id: "GA-A", filename: "plano-A.pdf" }] } },
};

it("muestra los documentos registrados aunque el resultado no figure en el resumen del lote", () => {
  const [group] = groupDatasetDocuments([lot], [equipment]);
  expect(group?.revisions).toMatchObject([
    { revision: "A", documents: [{ filename: "plano-A.pdf", id: "GA-A", model: { identity: "PROYECTO-A:v-101:A", ifc: "/ifc-a" } }] },
    { revision: "B", documents: [{ filename: "plano-B.pdf" }, { filename: "vesor.pdf" }] },
  ]);
  expect(group?.revisions[1]?.documents.every(document => !document.model)).toBe(true);
});

it("separa las fichas homónimas de otro proyecto y no mezcla su modelo", () => {
  const groups = groupDatasetDocuments([
    { ...lot, proyecto: "PROYECTO-B", revision: "A", documentos: ["plano-A.pdf"] },
    { ...lot, revision: "A", documentos: ["plano-A.pdf", "vesor.pdf"] },
  ], [equipment]);
  expect(groups.map(group => [group.project, group.tag])).toEqual([["PROYECTO-A", "V-101"], ["PROYECTO-B", "V-101"]]);
  const [own, other] = groups;
  expect(own?.revisions.find(r => r.revision === "A")?.documents.map(d => [d.filename, d.model?.identity ?? null]))
    .toEqual([["plano-A.pdf", "PROYECTO-A:v-101:A"], ["vesor.pdf", null]]);
  expect(other?.revisions.flatMap(r => r.documents.map(d => d.model ?? null))).toEqual([null]);
  expect([...homonymTags(groups)]).toEqual(["V-101"]);
});

it("une las filas del lote a su ficha aunque cambien mayúsculas o espacios", () => {
  const groups = groupDatasetDocuments([
    { ...lot, proyecto: "ENSAYO", tag: "KO-V-9207", revision: "0", documentos: ["a.pdf"] },
    { ...lot, proyecto: "ENSAYO", tag: " ko-v-9207", revision: "1", documentos: ["b.pdf"] },
  ], []);
  expect(groups).toHaveLength(1);
  expect(groups[0]?.revisions.map(revision => revision.revision)).toEqual(["0", "1"]);
  expect(homonymTags(groups).size).toBe(0);
});

it("mantiene separadas dos fichas del mismo código en el mismo proyecto", () => {
  const twin: EquipmentRow = { ...equipment, equipment_id: "v-101-bis", revision_meta: {} };
  const groups = groupDatasetDocuments([], [equipment, twin]);
  expect(groups.map(group => group.equipmentId)).toEqual(["v-101", "v-101-bis"]);
});

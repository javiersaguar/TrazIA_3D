"use client";

import { useSearchParams } from "next/navigation";
import { Segmented } from "@/components/ui/controls";

type DocumentsView = "equipos" | "proyectos" | "familias";
const options = [
  { value: "equipos", label: "Equipos" },
  { value: "proyectos", label: "Proyectos" },
  { value: "familias", label: "Familias" },
] as const;

export function useDocumentsNavigation() {
  const params = useSearchParams();
  const view = options.find(({ value }) => value === params.get("vista"))?.value ?? "equipos";
  const family = params.get("familia") ?? "all";
  const project = params.get("proyecto");

  function go(next: DocumentsView, selectedFamily = next === "equipos" ? "all" : family) {
    const query = new URLSearchParams({ vista: next });
    if (selectedFamily !== "all") query.set("familia", selectedFamily);
    if (project && next === "equipos") query.set("proyecto", project);
    window.history.replaceState(null, "", `/documentos?${query}`);
  }

  return { view, family, go };
}

export function DocumentsNavigation() {
  const { view, go } = useDocumentsNavigation();
  return (
    <Segmented<DocumentsView>
      label="Clasificación de documentos"
      value={view}
      onChange={go}
      options={[...options]}
      className="w-max flex-nowrap whitespace-nowrap [&_button]:min-h-9 [&_button]:px-3 [&_button]:sm:min-h-7"
    />
  );
}

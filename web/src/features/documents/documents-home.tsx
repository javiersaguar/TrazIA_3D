"use client";

import { useAccount } from "@/lib/accounts";
import { apiEnabled } from "@/lib/api/config";
import { DatasetLibrary } from "./dataset-library";
import { DocumentLibrary } from "./document-library";
import { useDocumentsNavigation } from "./documents-navigation";
import { FamiliesTab } from "./families-tab";
import { ProjectsTab } from "./projects-tab";

export function DocumentsHome() {
  const { view, family, go } = useDocumentsNavigation();
  const account = useAccount();

  if (!apiEnabled || account?.role === "guest") return <DocumentLibrary compact />;

  return (
    <>
      <h1 className="sr-only">Documentos</h1>
      {view === "equipos" ? (
        <DatasetLibrary />
      ) : view === "proyectos" ? (
        <ProjectsTab family={family} onOpenProject={(id) => {
          window.history.pushState(null, "", `/documentos?vista=equipos&proyecto=${encodeURIComponent(id)}`);
        }} />
      ) : (
        <FamiliesTab
          selected={family}
          onOpen={(id, next) => go(next === "documentos" ? "equipos" : "proyectos", id)}
        />
      )}
    </>
  );
}

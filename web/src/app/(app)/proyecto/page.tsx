import { redirect } from "next/navigation";
import { apiEnabled } from "@/lib/api/config";
import { PageHeader } from "@/components/shell/page-header";
import { PageTransition } from "@/components/shell/page-transition";
import { ProjectWorkspace } from "@/features/project/project-workspace";

export const metadata = { title: "Resumen" };

export default function ProyectoPage() {
  // Vista de la demo sintética: con la API (datos del reto) no se muestra.
  if (apiEnabled) redirect("/documentos");
  const item = { description: "Resumen del proyecto de la demo sintética." };
  return (
    <PageTransition>
      <PageHeader title="Resumen" description={item.description} />
      <ProjectWorkspace />
    </PageTransition>
  );
}

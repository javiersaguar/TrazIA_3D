import { redirect } from "next/navigation";
import { apiEnabled } from "@/lib/api/config";
import { PageHeader } from "@/components/shell/page-header";
import { PageTransition } from "@/components/shell/page-transition";
import { RoiCalculator } from "@/features/impact/roi-calculator";

export const metadata = { title: "Impacto" };

export default function ImpactoPage() {
  // Vista de la demo sintética: con la API (datos del reto) no se muestra.
  if (apiEnabled) redirect("/documentos");
  const item = { description: "Estimación del ahorro con la demo sintética." };
  return (
    <PageTransition>
      <PageHeader title="Impacto" description={item.description} />
      <RoiCalculator />
    </PageTransition>
  );
}

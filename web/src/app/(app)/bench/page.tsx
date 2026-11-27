import { redirect } from "next/navigation";
import { apiEnabled } from "@/lib/api/config";
import { Suspense } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { PageTransition } from "@/components/shell/page-transition";
import { BenchWorkspace } from "@/features/bench/bench-workspace";

export const metadata = { title: "Bench" };

export default function BenchPage() {
  // Vista de la demo sintética: con la API (datos del reto) no se muestra.
  if (apiEnabled) redirect("/documentos");
  const item = { description: "Mediciones del bench sobre la demo sintética." };
  return (
    <PageTransition>
      <PageHeader title="Bench" description={item.description} />
      <Suspense fallback={<p>Cargando métricas…</p>}><BenchWorkspace /></Suspense>
    </PageTransition>
  );
}

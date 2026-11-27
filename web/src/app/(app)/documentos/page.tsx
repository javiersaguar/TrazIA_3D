import { Suspense } from "react";
import { DocumentsHome } from "@/features/documents/documents-home";

export const metadata = { title: "Documentos" };

export default function Page() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted">Cargando documentos…</p>}>
      <DocumentsHome />
    </Suspense>
  );
}

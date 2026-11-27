"use client";

import { useRouter } from "next/navigation";
import { PageTransition } from "@/components/shell/page-transition";
import { DocumentLibrary } from "@/features/documents/document-library";
import { useCanEdit } from "@/lib/accounts";
import { IntakeForm } from "./intake-form";

export function UploadPlans() {
  const router = useRouter();
  const canEdit = useCanEdit();

  if (!canEdit) return <DocumentLibrary />;

  return (
    <PageTransition>
      <h1 className="mb-5 text-3xl font-semibold text-strong sm:text-4xl">Subir planos</h1>
      <IntakeForm onSubmitted={id => router.push(`/pipeline?trabajo=${encodeURIComponent(id)}`)} />
    </PageTransition>
  );
}

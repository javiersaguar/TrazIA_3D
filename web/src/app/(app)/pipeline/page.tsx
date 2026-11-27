import { PageTransition } from "@/components/shell/page-transition";
import { PipelineView } from "@/features/pipeline/pipeline-view";

export const metadata = { title: "Proceso" };

export default async function PipelinePage({ searchParams }: { searchParams: Promise<{ trabajo?: string | string[]; vista?: string | string[] }> }) {
  const { trabajo, vista } = await searchParams;
  return (
    <PageTransition>
      <PipelineView job={typeof trabajo === "string" ? trabajo : undefined} detail={vista === "detalle"} />
    </PageTransition>
  );
}

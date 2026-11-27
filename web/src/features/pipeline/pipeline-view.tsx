"use client";

import { PageHeader } from "@/components/shell/page-header";
import { useIsAdmin } from "@/lib/accounts";
import { JobProgress } from "./job-progress";
import dynamic from "next/dynamic";

const PipelineWorkspace = dynamic(() => import("./pipeline-workspace").then(module => module.PipelineWorkspace));

export function PipelineView({ job, detail }: { job?: string; detail?: boolean }) {
  if (!useIsAdmin() || (job && !detail)) return <JobProgress initialJobId={job} />;
  return <>
    <PageHeader title="Proceso" description="Etapas y eventos de cada ejecución, con su procedencia." />
    <PipelineWorkspace initialJobId={job} />
  </>;
}

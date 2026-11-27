"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/primitives";
import { useModelNavigation } from "./model-navigation";
import { ResultModelRoute } from "./result-model-route";

const loading = () => <Skeleton className="h-[min(65vh,620px)]" />;
const Review = dynamic(() => import("@/features/review/review-workspace").then((m) => m.ReviewWorkspace), { ssr: false, loading });
const Changes = dynamic(() => import("@/features/changes/changes-hub").then((m) => m.ChangesHub), { ssr: false, loading });

/** Revisión y Cambios; la navegación entre ambas vive en la barra superior. */
export function ModelWorkbench() {
  const { active, identity } = useModelNavigation();
  const content = active === "revision" ? <Review /> : <Changes />;

  return (
    <>
      <h1 className="sr-only">Modelo</h1>
      {identity ? <ResultModelRoute key={identity} identity={identity}>{content}</ResultModelRoute> : content}
    </>
  );
}

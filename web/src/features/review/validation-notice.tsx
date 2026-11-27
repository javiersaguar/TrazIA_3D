"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, ChevronDown, CircleCheck, TriangleAlert } from "lucide-react";
import { Icon } from "@/components/ui/primitives";
import { apiEnabled, apiURL } from "@/lib/api/config";
import { revisionIdentity, useEquipment } from "@/stores/equipment";
import type { RevisionId } from "@/lib/mock/api";
import { fieldLabel } from "@/lib/field-labels";
import type { NozzleReview } from "./nozzle-summary";

type Issue = { path: string; message: string; action: string };
export function useValidationIssues(revision: RevisionId) {
  const active = useEquipment((s) => s.active);
  const identity = active ? revisionIdentity(revision, active) : revision;
  return useQuery({
    queryKey: ["review-validation", identity], enabled: apiEnabled,
    queryFn: async () => {
      const response = await fetch(apiURL(`/revisions/${encodeURIComponent(identity)}/validation`));
      if (!response.ok) throw new Error("No se pudieron consultar las comprobaciones");
      return response.json() as Promise<{ issues: Issue[]; nozzles?: NozzleReview }>;
    },
  });
}

export function ValidationNotice({ query, onSelect }: {
  query: ReturnType<typeof useValidationIssues>;
  onSelect: (path: string) => void;
}) {
  const { data, error, isPending } = query;
  if (error) return <p role="alert" className="text-xs text-warning">{error.message}</p>;
  if (isPending) return <p role="status" className="text-xs text-muted">Consultando las comprobaciones…</p>;
  if (!data?.issues.length) return <p className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-xs text-muted">
    <Icon icon={CircleCheck} size={16} className="text-approved" /> Sin avisos de validación.
  </p>;
  const groups = new Map<string, Issue[]>();
  for (const issue of data.issues) {
    const group = groups.get(issue.action) ?? [];
    group.push(issue);
    groups.set(issue.action, group);
  }
  return <details open className="group/validation rounded-xl border border-border text-xs">
    <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl bg-surface-raised px-3 py-2 font-semibold text-strong">
      <Icon icon={TriangleAlert} size={16} className="text-warning" />
      Validación <span className="rounded-md bg-warning-bg px-1.5 py-0.5 font-medium text-warning">{data.issues.length} {data.issues.length === 1 ? "aviso" : "avisos"}</span>
      <Icon icon={ChevronDown} size={15} className="ml-auto text-muted group-open/validation:rotate-180" />
    </summary>
    <div className="space-y-2 px-2.5 pt-2 pb-2.5">
      {Array.from(groups, ([action, issues]) => <div key={action} className="overflow-hidden rounded-lg border border-border">
        {action ? <p className="bg-surface-raised px-2.5 py-2 leading-snug text-muted">{action}</p> : null}
        <ul className="divide-y divide-border">
          {issues.map((issue, i) => <li key={`${issue.path}-${i}`}>
            <button type="button" onClick={() => onSelect(issue.path)}
              className="flex w-full items-start gap-2 px-2.5 py-2 text-left transition-colors hover:bg-accent-soft focus-visible:outline-offset-[-2px]">
              <span className="min-w-0 flex-1 [overflow-wrap:anywhere]"><span className="block text-[13px] font-semibold text-strong">
                {/^nozzles\.[^.]+$/.test(issue.path) ? `Boquilla ${issue.path.slice("nozzles.".length)}` : fieldLabel(issue.path)}
              </span>
                <span className="mt-0.5 block leading-snug text-muted">{issue.message}</span></span>
              <Icon icon={ArrowUpRight} size={14} className="mt-0.5 text-accent-text" />
            </button>
          </li>)}
        </ul>
      </div>)}
      <p className="text-muted">Estas comprobaciones ayudan a revisar; no certifican conformidad normativa.</p>
    </div>
  </details>;
}

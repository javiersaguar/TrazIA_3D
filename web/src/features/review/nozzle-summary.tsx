import { ChevronDown } from "lucide-react";
import { Icon } from "@/components/ui/primitives";

export type NozzleEvidence = {
  document_id: string;
  filename: string;
  page: number;
  bbox: [number, number, number, number];
  locator: string;
  projection_reference: string | null;
};

export type NozzleReview = {
  identified: number;
  placed: number;
  pending: { mark: string; reasons: string[]; evidence: NozzleEvidence[] }[];
};

export function NozzleSummary({ inventory, onEvidence }: {
  inventory: NozzleReview;
  onEvidence: (mark: string, evidence: NozzleEvidence) => void;
}) {
  const { identified, placed, pending } = inventory;
  const counts = <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
    <span className="font-semibold text-strong">Boquillas</span>
    <span>{identified} {identified === 1 ? "identificada" : "identificadas"}</span>
    <span>{placed} {placed === 1 ? "colocada" : "colocadas"} en el IFC</span>
    <span className={pending.length ? "font-medium text-warning" : undefined}>{pending.length} {pending.length === 1 ? "pendiente" : "pendientes"}</span>
  </span>;
  const surface = "shrink-0 rounded-xl border border-border bg-surface-raised text-sm text-muted";
  if (!pending.length) return <div className={`${surface} px-3 py-2`} data-testid="nozzle-summary">{counts}</div>;
  return (
    <details className={`group/nozzles ${surface}`} data-testid="nozzle-summary">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-3 py-2 focus-visible:outline-offset-[-2px]">
        {counts}
        <Icon icon={ChevronDown} size={16} className="ml-auto shrink-0 group-open/nozzles:rotate-180" />
      </summary>
      <ul className="max-h-[min(34vh,18rem)] divide-y divide-border overflow-y-auto overscroll-contain border-t border-border">
        {pending.map(row => (
          <li key={row.mark} className="grid gap-1 px-3 py-2.5 sm:grid-cols-[4rem_1fr] sm:gap-x-4">
            <span className="font-semibold text-strong">{row.mark}</span>
            <div className="min-w-0">
              <p>{row.reasons.join(" · ")}</p>
              {row.evidence.map(evidence => (
                <div key={evidence.document_id} className="mt-1 text-xs">
                  {evidence.projection_reference ? <p>{evidence.projection_reference}</p> : null}
                  <button type="button" aria-label={`Ver fila de ${row.mark} en ${evidence.filename}, página ${evidence.page}`}
                    onClick={() => onEvidence(row.mark, evidence)}
                    className="text-left font-medium text-accent-text underline-offset-2 [overflow-wrap:anywhere] hover:underline">
                    {evidence.filename} · pág. {evidence.page}
                  </button>
                </div>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}

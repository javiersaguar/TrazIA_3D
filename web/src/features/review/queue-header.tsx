"use client";

import { Info } from "lucide-react";
import { Tip } from "@/components/ui/controls";
import styles from "./review.module.css";

export type FieldFilter = "all" | "pending";

export function QueueHeader({ filter, onFilter, reviewed, total }: {
  filter: FieldFilter; onFilter(filter: FieldFilter): void; reviewed: number; total: number;
}) {
  return (
    <div className={styles.queueHeader}>
      <div role="group" aria-label="Filtro de campos" className={styles.queueFilters}>
        {(["all", "pending"] as const).map(value => (
          <button key={value} type="button" aria-pressed={filter === value} onClick={() => onFilter(value)}>
            {value === "all" ? "Todos" : "Por revisar"}
          </button>
        ))}
      </div>
      <div className={styles.queueStatus}>
        <div role="progressbar" aria-label="Campos revisados" aria-valuenow={reviewed} aria-valuemin={0}
          aria-valuemax={Math.max(1, total)} aria-valuetext={`${reviewed} de ${total}`} className={styles.queueProgress}>
          <div style={{ width: `${total > 0 ? reviewed / total * 100 : 0}%` }} />
        </div>
        <span className="whitespace-nowrap tabular-nums text-muted">{reviewed} de {total}</span>
        <Tip content="Primero, campos por confirmar. Después, impacto × (1 − confianza).">
          <button type="button" aria-label="Cómo se ordena la cola" className={styles.queueHelp}>
            <Info aria-hidden size={17} />
          </button>
        </Tip>
      </div>
    </div>
  );
}

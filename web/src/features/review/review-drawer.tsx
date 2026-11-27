"use client";

import { ChevronDown, ChevronUp, ListChecks } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./review.module.css";

const MIN_HEIGHT = 28;
const MAX_HEIGHT = 88;
const clampHeight = (height: number) => Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.round(height)));

export function ReviewDrawer({ open, onOpenChange, expanded, reviewed, total, title = "Cola de revisión", mobileInline, header, children }: {
  open: boolean; onOpenChange(value: boolean): void; expanded: boolean;
  reviewed?: number; total: number; title?: string; mobileInline?: boolean; header?: ReactNode; children(close: () => void): ReactNode;
}) {
  const [height, setHeight] = useState(43);
  const root = useRef<HTMLDivElement>(null);
  const triggerId = useId();
  const contentId = useId();
  const drag = useRef<{ pointer: number; y: number; height: number; available: number } | null>(null);
  const visibleHeight = expanded ? MAX_HEIGHT : height;

  function close() {
    onOpenChange(false);
    document.getElementById(triggerId)?.focus({ preventScroll: true });
  }

  return (
    <div ref={root} className={cn(styles.drawerArea, mobileInline && styles.drawerInline)} onKeyDown={(event) => {
      if (event.key === "Escape" && open) { event.stopPropagation(); close(); }
    }}>
      <div
        className={cn(styles.drawer, open && styles.drawerOpen)}
        style={open ? { height: `${visibleHeight}%` } : undefined}
        data-testid="review-drawer"
      >
        {open ? <div
          role="slider"
          aria-label="Altura de la cola de revisión"
          aria-orientation="vertical"
          aria-valuemin={MIN_HEIGHT}
          aria-valuemax={MAX_HEIGHT}
          aria-valuenow={visibleHeight}
          aria-valuetext={`${visibleHeight} % del área de revisión`}
          tabIndex={0}
          className={styles.drawerGrip}
          onPointerDown={(event) => {
            if (!event.isPrimary || event.button !== 0 || !root.current) return;
            drag.current = { pointer: event.pointerId, y: event.clientY, height: visibleHeight, available: root.current.clientHeight };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const start = drag.current;
            if (!start || start.pointer !== event.pointerId || !start.available) return;
            onOpenChange(true);
            setHeight(clampHeight(start.height + (start.y - event.clientY) * 100 / start.available));
          }}
          onPointerUp={(event) => {
            const start = drag.current;
            if (!start || start.pointer !== event.pointerId || !start.available) return;
            const end = start.height + (start.y - event.clientY) * 100 / start.available;
            if (end < MIN_HEIGHT - 6) close();
          }}
          onLostPointerCapture={() => { drag.current = null; }}
          onKeyDown={(event) => {
            const next = { ArrowUp: visibleHeight + 5, ArrowDown: visibleHeight - 5, Home: MIN_HEIGHT, End: MAX_HEIGHT }[event.key];
            if (next === undefined) return;
            event.preventDefault();
            onOpenChange(true);
            setHeight(clampHeight(next));
          }}
        /> : null}
        <header className={styles.drawerHeader} data-filtered={open && !!header || undefined}>
          <button id={triggerId} type="button" aria-expanded={open} aria-controls={contentId}
            className={styles.drawerToggle} onClick={() => open ? close() : onOpenChange(true)}>
            <ListChecks aria-hidden size={18} />
            <span className="font-semibold">{title}</span>
            {!open || !header ? <span className="ml-auto whitespace-nowrap text-xs tabular-nums text-muted">
              {reviewed === undefined ? total : `${reviewed} de ${total}`}
            </span> : null}
            {open ? <ChevronDown aria-hidden size={16} /> : <ChevronUp aria-hidden size={16} />}
          </button>
          {open ? header : null}
        </header>
        <div id={contentId} hidden={!open} className={styles.drawerBody}>
          {open ? children(close) : null}
        </div>
      </div>
    </div>
  );
}

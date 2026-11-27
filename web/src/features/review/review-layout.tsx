"use client";

import { PanelsLeftRight } from "lucide-react";
import { useCallback, useState, useSyncExternalStore, type ReactNode } from "react";
import { Group, Panel, Separator, useDefaultLayout, useGroupRef, type LayoutStorage } from "react-resizable-panels";
import { Segmented } from "@/components/ui/controls";
import { Icon } from "@/components/ui/primitives";
import { QueueHeader, type FieldFilter } from "./queue-header";
import { ReviewDrawer } from "./review-drawer";
import styles from "./review.module.css";

const panelStorage: LayoutStorage = {
  getItem(key) { try { return window.localStorage.getItem(key); } catch { return null; } },
  setItem(key, value) { try { window.localStorage.setItem(key, value); } catch { /* Almacenamiento opcional. */ } },
};
const media = "(max-width:767px)";
const subscribe = (fn: () => void) => {
  const q = window.matchMedia(media);
  q.addEventListener("change", fn);
  return () => q.removeEventListener("change", fn);
};
const getMobile = () => window.matchMedia(media).matches;

type Focus = "all" | "pdf" | "model";
const SPLIT = { pdf: 50, model: 50 };

export function ReviewLayout({
  pdf, model, fields, revisions, actions, reviewed, total, editRequest, onCloseEditor, filter, onFilter, children, nozzleSummary,
}: {
  pdf: ReactNode; model: ReactNode; fields(close: () => void): ReactNode;
  revisions: ReactNode; actions: ReactNode; reviewed: number; total: number;
  editRequest: number; onCloseEditor(): void; filter: FieldFilter; onFilter(value: FieldFilter): void; children?: ReactNode;
  nozzleSummary?: (showDrawing: () => void) => ReactNode;
}) {
  const mobile = useSyncExternalStore(subscribe, getMobile, () => false);
  const viewsGroup = useGroupRef();
  const [focus, setFocus] = useState<Focus>("all");
  const [drawer, setDrawer] = useState({ open: false, expanded: false, dismissedEdit: 0 });
  const open = drawer.open || editRequest !== drawer.dismissedEdit;
  const views = useDefaultLayout({
    id: mobile ? "trazia.review.mobile.v2" : "trazia.review.views.v1",
    panelIds: ["pdf", "model"],
    onlySaveAfterUserInteractions: true,
    storage: panelStorage,
  });

  const toggleDrawer = useCallback((open: boolean) => {
    if (!open) onCloseEditor();
    setDrawer(current => current.open === open && !current.expanded && current.dismissedEdit === editRequest
      ? current : { open, expanded: false, dismissedEdit: editRequest });
  }, [editRequest, onCloseEditor]);

  function applyFocus(value: Focus | "fields") {
    if (value === "fields") {
      setDrawer({ open: true, expanded: true, dismissedEdit: editRequest });
      return;
    }
    toggleDrawer(false);
    setFocus(value);
    viewsGroup.current?.setLayout(value === "all"
      ? (views.defaultLayout ?? SPLIT)
      : { pdf: value === "pdf" ? 100 : 0, model: value === "model" ? 100 : 0 });
  }

  return (
    <div className={styles.workspace} data-testid="review-workspace">
      <div className={styles.toolbar}>
        <div className={styles.navigation}>
          {revisions}
          <div className={styles.navGroup}>
            <span aria-hidden className={styles.navLabel}><Icon icon={PanelsLeftRight} size={16} /> Foco</span>
            <Segmented<Focus | "fields">
              className={styles.navModes}
              label="Foco de revisión"
              value={open && drawer.expanded ? "fields" : focus}
              onChange={applyFocus}
              options={[
                { value: "all", label: "Todo" }, { value: "pdf", label: "Plano" },
                { value: "model", label: "Modelo" }, { value: "fields", label: "Campos" },
              ]}
            />
          </div>
        </div>
        <div className={styles.actions}>{actions}</div>
      </div>
      {nozzleSummary?.(() => applyFocus("all"))}
      <div className={styles.stage}>
        <div className={styles.panels}>
          <Group key={String(mobile)} id="review-views" groupRef={viewsGroup}
            orientation={mobile ? "vertical" : "horizontal"}
            defaultLayout={focus === "all" ? views.defaultLayout : { pdf: focus === "pdf" ? 100 : 0, model: focus === "model" ? 100 : 0 }}
            onLayoutChanged={views.onLayoutChanged}>
            <Panel id="pdf" defaultSize="50%" minSize="20%" collapsible className={styles.panel}>{pdf}</Panel>
            <Separator className={styles.separator} aria-label="Redimensionar plano y modelo" />
            <Panel id="model" defaultSize="50%" minSize="20%" collapsible className={styles.panel}>{model}</Panel>
          </Group>
          {focus === "all" ? children : null}
        </div>
        <ReviewDrawer open={open} onOpenChange={toggleDrawer} expanded={drawer.expanded}
          reviewed={reviewed} total={total}
          header={<QueueHeader filter={filter} onFilter={onFilter} reviewed={reviewed} total={total} />}>
          {fields}
        </ReviewDrawer>
      </div>
    </div>
  );
}

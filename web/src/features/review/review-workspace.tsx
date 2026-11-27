"use client";

import dynamic from "next/dynamic";
import { Box, Layers, Layers2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { isTyping } from "@/components/shell/global-keys";
import { IfcViewer } from "@/components/three";
import { Segmented } from "@/components/ui/controls";
import { Badge, Icon, Skeleton } from "@/components/ui/primitives";
import { DEMO, type RevisionId } from "@/lib/mock/api";
import { isDesignValue, isPreliminary, isResolved, type ReviewField } from "@/lib/mock/fields";
import { useReviewFields, useIfcUrl, useRevision } from "@/lib/queries";
import { drawingAnnotations } from "@/features/viewer3d/drawing-annotations";
import { useSelection } from "@/stores/selection";
import { useUi } from "@/stores/ui";
import { revisionIdentity, revisionLabel, useEquipment } from "@/stores/equipment";
import { parentElementId } from "@/features/viewer3d/semantic";
import { FieldQueue } from "./field-queue";
import { ApprovalButton } from "./approval-button";
import { useValidationIssues, ValidationNotice } from "./validation-notice";
import { ReviewChecks } from "./review-checks";
import styles from "./review.module.css";
import { useRevisionMarks, type RevisionMark } from "./revision-marks";
import { RevisionMarksNotice } from "./revision-marks-notice";
import { apiEnabled, apiURL, revisionVersion } from "@/lib/api/config";

import { EvidenceLink } from "./evidence-link";
import { useFieldAction } from "./use-field-action";
import type { FieldFilter } from "./queue-header";
import { NozzleSummary, type NozzleEvidence } from "./nozzle-summary";

const ReviewLayout = dynamic(
  () => import("./review-layout").then((m) => m.ReviewLayout),
  { ssr: false, loading: () => <Skeleton className="h-[620px]" /> },
);

// pdf.js solo en cliente y en diferido
const PdfPanel = dynamic(() => import("./pdf-panel").then((m) => m.PdfPanel), {
  ssr: false,
  loading: () => <Skeleton className="m-3 aspect-[1/1.414]" />,
});

export function ReviewWorkspace() {
  const revision = useUi((s) => s.revision);
  const equipment = useEquipment((s) => s.active);
  const setRevision = useUi((s) => s.setRevision);
  const { data: fields, dataUpdatedAt, isError: fieldsFailed, refetch: reloadFields } = useReviewFields(revision);
  const revisionData = useRevision(revision).data;
  const realData = revisionData?.dataset === "real";
  const horizontal = revisionData?.equipment.kind === "horizontal_vessel";
  const validation = useValidationIssues(revision);
  const reviewId = revisionIdentity(revision, equipment);
  const marks = useRevisionMarks(revision, dataUpdatedAt);
  const [markFocus, setMarkFocus] = useState<{ revision: RevisionId; mark: RevisionMark } | null>(null);
  const focusedMark = markFocus?.revision === revision ? markFocus.mark : undefined;
  const [rowFocus, setRowFocus] = useState<{ scope: string; row: NozzleEvidence & { mark: string } } | null>(null);
  const focusedRow = rowFocus?.scope === reviewId ? rowFocus.row : undefined;
  const { selectedId, hoveredId, selectedPath, setSelected, setHovered } =
    useSelection();
  const source = fields?.find(f => f.path === selectedPath)?.source;
  const ifcUrl = useIfcUrl(revision);
  const pdfDocument = focusedRow?.document_id ?? focusedMark?.document_id ?? (apiEnabled && source?.page ? source.document_id : apiEnabled ? (revisionVersion(revision)?.drawing ?? "GA") : "GA-V101");
  const pdfUrl = apiEnabled ? apiURL(`/revisions/${encodeURIComponent(revisionVersion(revision)?.identity ?? revision)}/documents/${encodeURIComponent(pdfDocument)}`) : DEMO.revisions[revision].pdf;
  const { apply, undoLast, busy } = useFieldAction(revision);
  const [filter, setFilter] = useState<FieldFilter>("all");
  const [editing, setEditing] = useState<{ scope: string; path: string } | null>(null);
  const editingPath = editing?.scope === reviewId && editing.path === selectedPath ? editing.path : null;
  const visibleFields = useMemo(() => filter === "pending"
    ? fields?.filter(f => !isResolved(f) || f.path === editingPath) : fields, [fields, filter, editingPath]);
  const [editRequest, setEditRequest] = useState(0);
  const [view, setView] = useState<"iso" | "front" | "top">("iso");
  const [mode, setMode] = useState<"solid" | "xray" | "exploded">("solid");

  const selectField = useCallback(
    (f: ReviewField) => {
      setMarkFocus(null);
      setRowFocus(null);
      setEditing(current => current?.path === f.path ? current : null);
      setSelected(f.elementId, f.path);
    },
    [setSelected],
  );

  // Al elegir un elemento en 3D se selecciona su campo de mayor riesgo.
  const onSelectElement = useCallback(
    (id: string) => {
      setMarkFocus(null);
      setRowFocus(null);
      const first = fields?.find((f) => f.elementId === parentElementId(id));
      setEditing(current => current?.path === first?.path ? current : null);
      if (first) setSelected(id, first.path);
      else setSelected(id);
    },
    [fields, setSelected],
  );

  const annotations = useMemo(() => drawingAnnotations(fields, selectedId, horizontal), [fields, selectedId, horizontal]);
  const cancelEditing = useCallback(() => setEditing(null), []);
  const changeEditing = useCallback((path: string, open: boolean) => {
    setEditing(current => open ? { scope: reviewId, path }
      : current?.scope === reviewId && current.path === path ? null : current);
  }, [reviewId]);

  // Teclado de revisión: J/K, A, E, S, Ctrl+Z
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editingPath || isTyping(e.target)) return;
      const ui = useUi.getState();
      if (ui.commandOpen || ui.shortcutsOpen) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undoLast();
        return;
      }
      if (!visibleFields?.length || e.ctrlKey || e.metaKey || e.altKey || busy) return;
      const index = visibleFields.findIndex((f) => f.path === selectedPath);
      const current = visibleFields[index];
      switch (e.key.toLowerCase()) {
        case "j": {
          const next = visibleFields[Math.min(visibleFields.length - 1, index + 1)];
          if (next) selectField(next);
          break;
        }
        case "k": {
          const prev = visibleFields[Math.max(0, index - 1)];
          if (prev) selectField(prev);
          break;
        }
        case "a":
          if (current && !isPreliminary(current)) {
            const next = visibleFields.slice(index + 1).find(f => !isResolved(f));
            void apply(current, "accepted").then(saved => {
              if (saved && next && useSelection.getState().selectedPath === current.path
                && revisionIdentity(useUi.getState().revision) === reviewId) selectField(next);
            });
          }
          break;
        case "e":
          if (current && !isDesignValue(current) && revisionData?.documents.some(document => document.role !== "orden_diseno")) {
            e.preventDefault();
            changeEditing(current.path, true);
            setEditRequest(value => value + 1);
          }
          break;
        case "s":
          if (current && !isPreliminary(current) && !isDesignValue(current)) apply(current, "assumed");
          break;
        default:
          return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visibleFields, editingPath, busy, selectedPath, selectField, apply, undoLast, reviewId, changeEditing, revisionData?.documents]);

  const selectCheck = (path: string) => {
    const field = fields?.find(f => f.path === path);
    if (field) selectField(field);
  };
  const selectMark = (mark: RevisionMark) => {
    setRowFocus(null);
    setMarkFocus({ revision, mark });
  };
  const nozzleInventory = validation.data?.nozzles;
  const checkCount = (validation.data?.issues.length ?? 0)
    + (marks.data?.unmarked_changes.length ?? 0) + (marks.data?.marks_without_change.length ?? 0);

  return (
      <ReviewLayout
        editRequest={editRequest}
        onCloseEditor={cancelEditing}
        filter={filter}
        onFilter={setFilter}
        reviewed={fields?.filter(isResolved).length ?? 0}
        total={fields?.length ?? 0}
        nozzleSummary={nozzleInventory ? showDrawing => (
          <NozzleSummary key={reviewId} inventory={nozzleInventory} onEvidence={(mark, evidence) => {
            cancelEditing();
            setMarkFocus(null);
            setSelected(null);
            setRowFocus({ scope: reviewId, row: { ...evidence, mark } });
            showDrawing();
          }} />
        ) : undefined}
        revisions={
          <div className={styles.navGroup}>
            <span aria-hidden className={styles.navLabel}><Icon icon={Layers2} size={16} /> Revisión</span>
            <Segmented<RevisionId> className={styles.navModes} label="Revisión" value={revision}
              onChange={value => { setRevision(value); cancelEditing(); }}
              options={(["A", "B"] as const).map(value => ({
                value,
                label: apiEnabled && equipment ? `Rev ${revisionLabel(value, equipment)}` : `Rev ${value}`,
              }))} />
            {revisionData && !realData ? <Badge tone="warning">Datos sintéticos</Badge> : null}
          </div>
        }
        actions={<>
          {apiEnabled ? <ReviewChecks count={checkCount}>{close => <>
            <ValidationNotice query={validation} onSelect={path => { selectCheck(path); close(); }} />
            <RevisionMarksNotice revision={revision} data={marks.data} error={marks.error} loading={marks.isFetching && !marks.data}
              onRetry={() => { void marks.refetch(); }}
              onSelect={path => { selectCheck(path); close(); }}
              onMark={mark => { selectMark(mark); close(); }} />
          </>}</ReviewChecks> : null}
          <ApprovalButton key={revision} revision={revision} fields={fields} />
        </>}
        pdf={
          fields ? (
            <PdfPanel
              key={`${revision}:${pdfDocument}`}
              url={pdfUrl}
              fields={fields.filter(f => f.source.document_id === pdfDocument)}
              marks={marks.data?.documents.find(d => d.document_id === pdfDocument)?.marks}
              focusedMark={focusedMark}
              focusedRow={focusedRow}
              onMark={selectMark}
              selectedPath={selectedPath}
              selectedId={selectedId}
              hoveredId={hoveredId}
              onSelect={selectField}
              onHover={(f) => setHovered(f?.elementId ?? null)}
            />
          ) : (
            <Skeleton className="m-3 aspect-[1/1.414]" />
          )
        }
        model={
          <div className="flex h-full min-h-0 flex-col">
            <div className={styles.modelTools}>
              <div className={styles.viewGroup}>
                <span aria-hidden className={styles.viewLabel}><Icon icon={Box} size={15} /> <span>Cámara</span></span>
                <Segmented className={styles.viewModes} label="Vista del modelo" value={view} onChange={setView}
                  options={[{ value: "iso", label: "Iso", title: "Vista isométrica" }, { value: "front", label: "Alzado" }, { value: "top", label: "Planta" }]} />
              </div>
              <div className={styles.viewGroup}>
                <span aria-hidden className={styles.viewLabel}><Icon icon={Layers} size={15} /> <span>Representación</span></span>
                <Segmented className={styles.viewModes} label="Modo del modelo" value={mode} onChange={setMode}
                  options={[{ value: "solid", label: "Sólido" }, { value: "xray", label: "Rayos X" }, { value: "exploded", label: "Explosionado" }]} />
              </div>
            </div>
            <div className="min-h-0 flex-1">
              <IfcViewer
                compact
                ifcUrl={ifcUrl ?? ""}
                selectedId={selectedId ?? undefined}
                hoveredId={hoveredId ?? undefined}
                onSelect={onSelectElement}
                onHover={setHovered}
                annotations={annotations}
                view={view}
                mode={mode}
              />
            </div>
          </div>
        }
        fields={close => (
          <FieldQueue
            filter={filter}
            onReachEnd={close}
            busy={busy}
            fields={visibleFields}
            documents={revisionData?.documents}
            failed={fieldsFailed}
            onRetry={() => { void reloadFields(); }}
            selectedPath={selectedPath}
            hoveredId={hoveredId}
            editingPath={editingPath}
            onSelect={selectField}
            onHover={(f) => setHovered(f?.elementId ?? null)}
            onAction={(f, status, value, options) => apply(f, status, value, options)}
            onEdit={changeEditing}
          />
        )}
      >
        <EvidenceLink
          key={selectedPath}
          path={selectedPath}
          elementId={selectedId}
        />
      </ReviewLayout>
  );
}

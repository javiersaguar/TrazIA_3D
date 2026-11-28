"use client";

import { ChevronLeft, ChevronRight, FileText, Minus, Plus, ScanLine } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Tip } from "@/components/ui/controls";
import { Code, EmptyState, Icon, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import type { ReviewField } from "@/lib/mock/fields";
import { DrawingCanvas } from "./drawing-canvas";
import type { RevisionMark } from "./revision-marks";
import type { NozzleEvidence } from "./nozzle-summary";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
type EvidenceField = Pick<ReviewField, "path" | "label" | "status"> & {
  elementId: string;
  source: Pick<ReviewField["source"], "page" | "bbox"> & { locator?: string };
};

type Props<T extends EvidenceField> = {
  url: string;
  fields: T[];
  selectedPath: string | null;
  selectedId: string | null;
  hoveredId: string | null;
  onSelect(field: T): void;
  onHover(field: T | null): void;
  compactNavigation?: boolean;
  marks?: RevisionMark[];
  focusedMark?: RevisionMark;
  focusedRow?: NozzleEvidence & { mark: string };
  onMark?(mark: RevisionMark): void;
};

export function PdfPanel<T extends EvidenceField>({
  url,
  fields,
  selectedPath,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
  compactNavigation = false,
  marks = [],
  focusedMark,
  focusedRow,
  onMark,
}: Props<T>) {
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0),
    [zoom, setZoom] = useState(1),
    [failed, setFailed] = useState(false),
    [pages, setPages] = useState(0);
  const [loadedPage, setLoadedPage] = useState(0);
  const [override, setOverride] = useState<{
    path: string | null;
    page: number;
  } | null>(null);
  const selected = fields.find((f) => f.path === selectedPath);
  const anchor = focusedRow ? `fila:${focusedRow.mark}` : focusedMark?.id ?? selectedPath;
  const page = Math.min(
    pages || 1,
    Math.max(
      1,
      override?.path === anchor
        ? override.page
        : (focusedRow?.page ?? focusedMark?.page ?? selected?.source.page ?? 1),
    ),
  );
  // Varios campos de una pieza comparten recuadro (nombre, origen y tamaño en una vista): uno solo.
  const groups = useMemo(() => {
    const byBox = new Map<string, T[]>();
    for (const f of fields) {
      if (!f.source.bbox || f.source.page !== page) continue;
      const key = `${f.elementId}|${f.source.bbox.join(",")}`;
      byBox.set(key, [...(byBox.get(key) ?? []), f]);
    }
    return [...byBox.values()];
  }, [fields, page]);
  // Un skid trae decenas de piezas: sin selección, solo el contorno para no tapar el plano.
  const dense = groups.length > 30;
  const boxes = useMemo(
    () => groups.map((g) => g.find((f) => f.path === selectedPath) ?? g[0]!),
    [groups, selectedPath],
  );
  const rowBox = focusedRow?.page === page ? focusedRow.bbox : undefined;
  const fileName = url.split("/").at(-1)?.split("?")[0];
  const drawingWidth = Math.max(80, width - (pages > 1 && !compactNavigation ? 84 : 0)) * zoom;
  const goTo = (page: number) => setOverride({ path: anchor, page });
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const available = Math.floor(entry?.contentRect.width ?? 0) - 24;
      if (available > 0) setWidth(Math.max(80, available));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    const viewport = frame.current;
    if ((!selectedPath && !focusedMark && !focusedRow) || !viewport) return;
    const box = viewport.querySelector<HTMLElement>(
      focusedRow ? "[data-nozzle-row]" : focusedMark ? `[data-mark-id="${CSS.escape(focusedMark.id)}"]` : `[data-path="${CSS.escape(selectedPath!)}"]`,
    );
    if (!box) return;
    const target = box.getBoundingClientRect();
    const frameRect = viewport.getBoundingClientRect();
    viewport.scrollTo({
      top: viewport.scrollTop + target.top - frameRect.top + (target.height - viewport.clientHeight) / 2,
      left: viewport.scrollLeft + target.left - frameRect.left + (target.width - viewport.clientWidth) / 2,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [selectedPath, focusedMark, focusedRow, zoom, page, loadedPage]);
  return (
    <div
      className="flex h-full min-h-0 flex-col"
      data-testid="pdf-panel"
      data-pdf-page={page}
    >
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-3">
        <Icon icon={FileText} className="text-muted" />
        <Code className="truncate text-text">{fileName}</Code>
        <span className="shrink-0 text-xs text-faint">
          pág. {page}
          {pages ? ` / ${pages}` : ""}
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <Tip content="Alejar">
            <button
              type="button"
              aria-label="Alejar"
              disabled={zoom <= 1}
              onClick={() => setZoom((z) => Math.max(1, z - 0.5))}
              className="rounded-md p-1.5 text-muted disabled:opacity-40"
            >
              <Icon icon={Minus} size={14} />
            </button>
          </Tip>
          <span className="w-10 text-center text-xs text-muted">
            {Math.round(zoom * 100)} %
          </span>
          <Tip content="Acercar">
            <button
              type="button"
              aria-label="Acercar"
              disabled={zoom >= 3}
              onClick={() => setZoom((z) => Math.min(3, z + 0.5))}
              className="rounded-md p-1.5 text-muted disabled:opacity-40"
            >
              <Icon icon={Plus} size={14} />
            </button>
          </Tip>
        </div>
      </div>
      {compactNavigation && pages > 1 ? <nav aria-label="Páginas del plano" className="flex shrink-0 items-center justify-between gap-1 border-b border-border px-3 py-1">
        <button type="button" disabled={page <= 1} onClick={() => goTo(page - 1)}
          className="inline-flex min-h-8 items-center gap-1 rounded px-1.5 text-xs text-muted hover:text-text disabled:opacity-40">
          <Icon icon={ChevronLeft} size={14} /> Anterior
        </button>
        <label className="flex items-center gap-2 text-xs text-muted">Página
          <select value={page} onChange={event => goTo(Number(event.target.value))} className="h-8 rounded border border-border bg-surface px-1.5 text-text">
            {Array.from({ length: pages }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
          </select>
        </label>
        <button type="button" disabled={page >= pages} onClick={() => goTo(page + 1)}
          className="inline-flex min-h-8 items-center gap-1 rounded px-1.5 text-xs text-muted hover:text-text disabled:opacity-40">
          Siguiente <Icon icon={ChevronRight} size={14} />
        </button>
      </nav> : null}
      <div
        ref={frame}
        data-evidence-scroll
        className="drafting-grid relative min-h-0 flex-1 overflow-auto p-3 [scrollbar-gutter:stable]"
      >
        {failed ? (
          <EmptyState icon={ScanLine} title="No se pudo abrir el plano">
            Comprueba la conexión y vuelve a cargar el documento.
          </EmptyState>
        ) : (
          <Document
            file={url}
            loading={<Skeleton className="aspect-[1/1.414] w-full" />}
            onLoadError={() => setFailed(true)}
            onLoadSuccess={({ numPages }) => setPages(numPages)}
            className="mx-auto flex w-fit items-start gap-3"
          >
            {pages > 1 && !compactNavigation ? (
              <nav
                className="sticky top-0 flex shrink-0 flex-col gap-2"
                aria-label="Páginas del plano"
              >
                {Array.from({ length: pages }, (_, i) => (
                  <button
                    key={i}
                    type="button"
                    aria-label={`Ver página ${i + 1}`}
                    aria-current={page === i + 1 ? "page" : undefined}
                    onClick={() => goTo(i + 1)}
                    className={cn(
                      "shrink-0 rounded-md border p-1 text-xs",
                      page === i + 1
                        ? "border-accent bg-accent-soft"
                        : "border-border bg-surface",
                    )}
                  >
                    <Page
                      pageNumber={i + 1}
                      width={64}
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                    />
                    <span className="block py-1">{i + 1}</span>
                  </button>
                ))}
              </nav>
            ) : null}
            {width > 0 ? (
              <div
                className="relative shrink-0 overflow-hidden rounded-[4px] shadow-lg"
                style={{ width: drawingWidth }}
                key={page}
              >
                <Page
                  pageNumber={page}
                  renderMode="none"
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                  onLoadSuccess={({ pageNumber }) => setLoadedPage(pageNumber)}
                  loading={<Skeleton className="aspect-[1/1.414]" />}
                >
                  <DrawingCanvas width={drawingWidth} />
                </Page>
                {boxes.map((f) => {
                  const [x0, y0, x1, y1] = f.source.bbox as [
                      number,
                      number,
                      number,
                      number,
                    ],
                    active = f.path === selectedPath,
                    related =
                      !active &&
                      (f.elementId === selectedId || f.elementId === hoveredId);
                  return (
                    <button
                      key={f.path}
                      type="button"
                      data-path={f.path}
                      aria-label={`Evidencia de ${f.label}`}
                      title={f.source.locator ? `${f.label}\n${f.source.locator}` : f.label}
                      onClick={() => onSelect(f)}
                      onMouseEnter={() => onHover(f)}
                      onMouseLeave={() => onHover(null)}
                      className="group absolute -m-1 p-1"
                      style={{
                        left: `${x0 * 100}%`,
                        top: `${y0 * 100}%`,
                        width: `calc(${(x1 - x0) * 100}% + 8px)`,
                        height: `calc(${(y1 - y0) * 100}% + 8px)`,
                      }}
                    >
                      <span
                        className={cn(
                          "block h-full w-full rounded-[3px] border transition-colors",
                          active
                            ? "border-accent-strong bg-accent/20 shadow-[0_0_0_3px_var(--accent-soft)]"
                            : related
                              ? "border-accent bg-accent/10"
                              : dense
                                ? "border-approved/25 group-hover:border-accent group-hover:bg-accent/10"
                                : f.status === "candidate"
                                ? "border-accent/40 bg-accent/5 group-hover:border-accent"
                                : "border-approved/50 bg-approved/10",
                        )}
                      />
                    </button>
                  );
                })}
                {marks.filter(mark => mark.page === page).map(mark => {
                  const [x0, y0, x1, y1] = mark.bbox;
                  return <button type="button" key={mark.id} data-mark-id={mark.id}
                    aria-label={`Marca candidata ${mark.kind === "delta" ? "Δ" : "nube"} · página ${mark.page}`}
                    title="Marca candidata de revisión; no confirma un cambio"
                    onClick={() => onMark?.(mark)}
                    className={cn("absolute border-2 border-warning bg-warning/10 text-[10px] text-warning", focusedMark?.id === mark.id && "ring-2 ring-warning ring-offset-2")}
                    style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}>
                    <span className="sr-only">{mark.kind === "delta" ? "Triángulo" : "Nube"} {mark.label}</span>
                  </button>;
                })}
                {rowBox ? <div data-nozzle-row role="img" aria-label={`Fila de ${focusedRow?.mark}`}
                  title={focusedRow?.locator}
                  className="pointer-events-none absolute rounded-sm border-2 border-accent-strong bg-accent/15"
                  style={{ left: `${rowBox[0] * 100}%`, top: `${rowBox[1] * 100}%`,
                    width: `${(rowBox[2] - rowBox[0]) * 100}%`, height: `${(rowBox[3] - rowBox[1]) * 100}%` }} /> : null}
              </div>
            ) : null}
          </Document>
        )}
      </div>
    </div>
  );
}

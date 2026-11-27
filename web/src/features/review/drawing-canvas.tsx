"use client";

import { useEffect, useRef, useState } from "react";
import { usePageContext } from "react-pdf";
import { Skeleton } from "@/components/ui/primitives";

const MAX_RASTER_EDGE = 4096;

export function DrawingCanvas({ width }: { width: number }) {
  const page = usePageContext()?.page;
  const canvas = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const visible = canvas.current;
    if (!visible || !page) return;
    let task: ReturnType<typeof page.render> | undefined;
    let cancelled = false;
    // Render offscreen. The last complete image stays visible and scales with the panel.
    const timer = window.setTimeout(() => {
      const original = page.getViewport({ scale: 1 });
      const scale = Math.min(width * window.devicePixelRatio / original.width,
        MAX_RASTER_EDGE / Math.max(original.width, original.height));
      const viewport = page.getViewport({ scale });
      const buffer = document.createElement("canvas");
      buffer.width = Math.ceil(viewport.width);
      buffer.height = Math.ceil(viewport.height);
      task = page.render({ canvas: buffer, viewport });
      void task.promise.then(() => {
        if (cancelled) return;
        const context = visible.getContext("2d", { alpha: false });
        if (!context) { setStatus("error"); return; }
        visible.width = buffer.width;
        visible.height = buffer.height;
        context.drawImage(buffer, 0, 0);
        setStatus("ready");
      }).catch(() => {
        if (!cancelled) setStatus("error");
      });
    }, visible.width ? 120 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      task?.cancel();
    };
  }, [page, width]);

  if (!page) return null;
  const base = page.getViewport({ scale: 1 });
  return (
    <div className="relative bg-white" style={{ aspectRatio: `${base.width} / ${base.height}` }}>
      {status === "loading" ? <Skeleton className="absolute inset-0" /> : null}
      {status === "error" ? <p role="alert" className="absolute inset-x-0 top-0 bg-surface p-3 text-sm">No se pudo dibujar esta página del plano.</p> : null}
      <canvas ref={canvas} width={0} height={0} className="absolute inset-0 block size-full select-none"
        aria-label={`Plano, página ${page.pageNumber}`} />
    </div>
  );
}

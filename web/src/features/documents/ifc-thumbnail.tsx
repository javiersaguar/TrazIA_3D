"use client";

import { Box } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { DEMO } from "@/lib/mock/api";
import { loadDocument, publishedFile, sketchAssets, type Design } from "./catalogue";

const THUMBNAIL_SIZE = { large: "size-24", card: "size-[4.5rem] sm:size-[5.5rem]", row: "size-11" } as const;

export function IfcThumbnail({ name, url, documentId, size = "large" }: {
  name: string; url?: string; documentId?: string; size?: keyof typeof THUMBNAIL_SIZE;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [result, setResult] = useState<{ source: string; image: string | null }>();
  const source = url ?? documentId;

  useEffect(() => {
    if (!source || !frame.current) return;
    let active = true;
    async function render() {
      let blobUrl: string | undefined;
      try {
        if (!url && documentId) {
          const file = await loadDocument(documentId);
          if (file && active) blobUrl = URL.createObjectURL(file);
        }
        const ifcUrl = url ?? blobUrl;
        const image = ifcUrl && active ? await (await import("./ifc-thumbnail-renderer")).ifcThumbnail(ifcUrl) : null;
        if (active) setResult({ source: source!, image });
      } catch {
        if (active) setResult({ source: source!, image: null });
      } finally {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
      }
    }
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      void render();
    });
    observer.observe(frame.current);
    return () => {
      active = false;
      observer.disconnect();
    };
  }, [source, url, documentId]);

  const current = result?.source === source ? result : undefined;
  const phase = !source ? "missing" : current?.image ? "ready" : current ? "error" : "loading";
  return (
    <div ref={frame} data-testid="ifc-thumbnail" data-phase={phase}
      className={cn("relative grid shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-surface-sunken", THUMBNAIL_SIZE[size])}>
      {current?.image ? (
        // eslint-disable-next-line @next/next/no-img-element -- Render local en memoria, sin optimizador de imágenes.
        <img src={current.image} alt={`Vista 3D de ${name}`} width={96} height={96} className="size-full object-contain" />
      ) : (
        <span className="flex flex-col items-center gap-1 px-1 text-center text-[10px] text-muted">
          <Icon icon={Box} size={20} />
          <span className={size === "row" ? "sr-only" : undefined}>
            {phase === "missing" ? "Sin IFC" : phase === "error" ? "Vista no disponible" : "Cargando 3D"}
          </span>
        </span>
      )}
    </div>
  );
}

export function DesignThumbnail({ design }: { design: Design }) {
  const isIfc = /\.ifc$/i.test(design.filename ?? "");
  const demo = design.demo && (design.rev === "A" || design.rev === "B") ? DEMO.revisions[design.rev].ifc : undefined;
  const url = sketchAssets(design.id)?.ifc ?? demo ?? (isIfc && design.shared ? publishedFile(design.id) : undefined);
  return <IfcThumbnail name={design.tag ?? design.name} url={url} documentId={isIfc && !design.shared ? design.id : undefined} />;
}

"use client";

import { Box, FileText } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

export function ModelThumbnail({ url }: { url?: string }) {
  const frame = useRef<HTMLSpanElement>(null);
  const [preview, setPreview] = useState<{ url: string; image: string }>();
  useEffect(() => {
    const element = frame.current;
    if (!element || !url) return;
    let active = true;
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      void import("@/features/viewer3d/ifc-thumbnail-renderer")
        .then(({ ifcThumbnail }) => active ? ifcThumbnail(url) : undefined)
        .then(image => { if (active && image) setPreview({ url, image }); })
        .catch(() => { /* El enlace al IFC sigue disponible si la imagen no se pudo dibujar. */ });
    }, { rootMargin: "160px" });
    observer.observe(element);
    return () => { active = false; observer.disconnect(); };
  }, [url]);

  return <span ref={frame} aria-hidden className={`grid h-14 w-[4.5rem] shrink-0 place-items-center overflow-hidden rounded-md border border-border ${url ? "bg-slate-950 text-slate-400" : "text-faint"}`}>
    {preview && preview.url === url ? <Image src={preview.image} alt="" width={176} height={132} unoptimized className="h-full w-full object-contain" />
      : url ? <Box size={20} /> : <FileText size={19} />}
  </span>;
}

"use client";

import Link from "next/link";
import { toast } from "sonner";

import { Badge } from "@/components/ui/primitives";
import { modelHref } from "@/features/workspace/model-links";
import { useCanEdit } from "@/lib/accounts";
import { DEMO } from "@/lib/mock/api";
import { useUi } from "@/stores/ui";
import { loadDocument, publishedFile, sketchAssets, type Design } from "./catalogue";
import { ModelThumbnail } from "./model-thumbnail";
import { SketchModelDialog } from "./sketch-model-dialog";

const action = "text-[12px] text-accent-text underline-offset-2 hover:underline";

async function download(id: string, filename: string) {
  try {
    const blob = await loadDocument(id);
    if (!blob) throw new Error("El documento no está disponible en este navegador. Vuelve a añadirlo.");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : "No se pudo abrir el documento");
  }
}

export function DocumentActions({ design }: { design: Design }) {
  const canEdit = useCanEdit();
  const setRevision = useUi(state => state.setRevision);
  const demoRevision = design.demo && (design.rev === "A" || design.rev === "B") ? design.rev : null;
  if (demoRevision) return <span className="flex flex-wrap gap-x-3">
    <a className={action} href={DEMO.revisions[demoRevision].pdf} target="_blank" rel="noreferrer">Abrir PDF</a>
    {canEdit ? <Link className={action} href={modelHref("revision")} onClick={() => setRevision(demoRevision)}>Abrir en Modelo</Link> : null}
  </span>;

  const assets = sketchAssets(design.id);
  if (assets) {
    const tag = design.tag ?? design.name;
    return (
      <span className="flex flex-wrap gap-x-3 gap-y-1">
        <a href={assets.pdf} target="_blank" rel="noopener" className={action}
          aria-label={`Abrir PDF de ${tag} (pestaña nueva)`}>
          Abrir PDF
        </a>
        {assets.ifc && <SketchModelDialog tag={tag} name={design.name} ifc={assets.ifc} />}
        {canEdit && design.tag && <Link className={action} href={`/modelo?vista=disenos&diseno=${encodeURIComponent(design.tag)}`}
          aria-label={`Abrir ${tag} en Modelo › Diseños`}>
          Editar en Modelo
        </Link>}
      </span>
    );
  }
  if (design.example) return <Badge tone="warning">ejemplo</Badge>;

  const { id, filename } = design;
  if (!filename) return null;
  if (design.shared) {
    const url = publishedFile(id);
    return <span className="flex flex-wrap items-center gap-x-3">
      <a href={url} download={filename} className={action}>{filename}</a>
      {/\.ifc$/i.test(filename) ? <SketchModelDialog tag={design.tag ?? design.name} name={design.name} ifc={url} published /> : null}
    </span>;
  }
  return (
    <button type="button" className={`max-w-full truncate font-mono ${action}`}
      onClick={() => void download(id, filename)}>
      {filename}
    </button>
  );
}

export function DocumentThumbnail({ design }: { design: Design }) {
  const ifc = design.demo && (design.rev === "A" || design.rev === "B") ? DEMO.revisions[design.rev].ifc : sketchAssets(design.id)?.ifc;
  if (!ifc) return /\.pdf$/i.test(design.filename ?? "") ? <ModelThumbnail /> : null;
  return <SketchModelDialog tag={design.tag ?? design.name} name={design.filename ?? design.name} ifc={ifc} thumbnail />;
}

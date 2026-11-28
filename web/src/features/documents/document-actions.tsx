"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Box } from "lucide-react";
import { toast } from "sonner";

import { Badge, Button, Icon } from "@/components/ui/primitives";
import { modelHref } from "@/features/workspace/model-links";
import { useCanEdit } from "@/lib/accounts";
import { DEMO } from "@/lib/mock/api";
import { useUi } from "@/stores/ui";
import { loadDocument, publishedFile, sketchAssets, type Design } from "./catalogue";
import type { CatalogueModel } from "./dataset-documents";
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

export function CatalogueModelButton({ model, tag, primary = false }: { model: CatalogueModel; tag: string; primary?: boolean }) {
  const router = useRouter();
  const canEdit = useCanEdit();
  const setRevision = useUi((state) => state.setRevision);
  if (model.demoRevision && canEdit) {
    const revision = model.demoRevision;
    return <Button variant={primary ? "primary" : "ghost"} size={primary ? undefined : "sm"}
      onClick={() => { setRevision(revision); router.push(modelHref("revision")); }}>
      <Icon icon={Box} size={primary ? 16 : 13} /> {primary ? "Ver modelo 3D" : "Ver 3D"}
    </Button>;
  }
  return <SketchModelDialog tag={tag} name={model.name} ifc={model.ifc} documentId={model.documentId}
    published={model.published} primary={primary} />;
}

export function DocumentActions({ design, showModel = true }: { design: Design; showModel?: boolean }) {
  const canEdit = useCanEdit();
  const setRevision = useUi(state => state.setRevision);
  const demoRevision = design.demo && (design.rev === "A" || design.rev === "B") ? design.rev : null;
  if (demoRevision) return <span className="flex flex-wrap gap-x-3">
    <a className={action} href={DEMO.revisions[demoRevision].pdf} target="_blank" rel="noreferrer">Abrir PDF</a>
    {showModel && canEdit ? <Link className={action} href={modelHref("revision")} onClick={() => setRevision(demoRevision)}>Abrir en Modelo</Link> : null}
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
        {showModel && assets.ifc ? <SketchModelDialog tag={tag} name={design.name} ifc={assets.ifc} /> : null}
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
      {showModel && /\.ifc$/i.test(filename) ? <SketchModelDialog tag={design.tag ?? design.name} name={design.name} ifc={url} published /> : null}
    </span>;
  }
  return (
    <button type="button" className={`max-w-full truncate font-mono ${action}`}
      onClick={() => void download(id, filename)}>
      {filename}
    </button>
  );
}

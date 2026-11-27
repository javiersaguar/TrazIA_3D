"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, CircleMinus } from "lucide-react";
import Link from "next/link";
import { Badge, Button, Panel, PanelHeader } from "@/components/ui/primitives";
import { apiRevisionById } from "@/lib/api/client";
import { apiEnabled, apiURL } from "@/lib/api/config";
import { formatValue } from "@/lib/format";
import { modelHref } from "@/features/workspace/model-links";
import { flattenRevision } from "@/lib/mock/fields";

const resourceLink = "text-sm font-medium text-accent-text underline underline-offset-2";

export function PipelineResult({ identity }: { identity: string }) {
  const revision = useQuery({
    queryKey: ["pipeline-result", identity], queryFn: () => apiRevisionById(identity), enabled: apiEnabled,
  });
  const record = revision.data;
  const root = `/revisions/${encodeURIComponent(identity)}`;
  const ifcUrl = apiURL(`${root}/ifc?draft=true`);
  const original = (documentId: string) => apiURL(`${root}/documents/${encodeURIComponent(documentId)}`);
  const documents = new Map(record?.documents.map(document => [document.id, document]));

  return (
    <div className="space-y-5">
      <Link href="/pipeline" className={resourceLink}>Volver al proceso</Link>
      {!apiEnabled ? <p>Configura la conexión con la API para abrir este resultado.</p> : null}
      {apiEnabled && revision.isPending ? <p role="status">Cargando resultado…</p> : null}
      {revision.isError ? <Panel className="space-y-3 p-4">
        <p role="alert">{revision.error.message}</p>
        <Button onClick={() => void revision.refetch()} className="min-h-11 text-[18px]">Reintentar</Button>
      </Panel> : null}
      {record ? <>
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-strong">{record.equipment.tag.value} · Versión {record.revision}</h1>
            <Badge tone="warning">Borrador</Badge>
          </div>
          <p className="text-muted">{record.dataset === "synthetic" ? "Datos sintéticos" : "Datos reales"} · {record.project_id}</p>
        </header>
        <Panel>
          <PanelHeader title="IFC de la versión"
            actions={<div className="flex flex-wrap items-center gap-3">
              <a href={ifcUrl} className={resourceLink}>Descargar IFC en borrador</a>
              <Link href={modelHref("revision", identity)} className={resourceLink}>Ver modelo 3D</Link>
            </div>} />
        </Panel>
        <Panel>
          <PanelHeader title="Documentos originales" description="La API verifica la huella del archivo al servirlo." />
            <ul className="space-y-2 px-5 pb-5">
              {record.documents.map(document => <li key={document.id}>
                <a className={resourceLink} href={original(document.id)} target="_blank" rel="noreferrer">{document.filename}</a>
              </li>)}
            </ul>
          </Panel>
          <Panel>
            <PanelHeader title="Datos extraídos" description="Valores y evidencias de esta versión. Compruébalos antes de utilizar el modelo." />
            <div className="overflow-x-auto px-5 pb-5">
              <table className="w-full text-left text-sm">
                <thead><tr className="text-muted">
                  {["Dato", "Valor", "Fiabilidad", "Evidencia"].map(label => <th key={label} scope="col" className="py-2 pr-3">{label}</th>)}
                </tr></thead>
                <tbody>
                  {flattenRevision(record).map(item => {
                    const document = documents.get(item.source.document_id);
                    const locator = [item.source.page ? `pág. ${item.source.page}` : "",
                      item.source.sheet, item.source.cell, item.source.locator].filter(Boolean).join(" · ");
                    return <tr key={item.path} className="border-t border-border">
                      <th scope="row" className="py-2 pr-3 font-medium">{item.label}</th>
                      <td className="py-2 pr-3">{formatValue(item.value, item.unit)}</td>
                      <td className="py-2 pr-3"><Reliability confidence={item.confidence} /></td>
                      <td className="py-2">
                        {document ? <a className={resourceLink} href={original(document.id)} target="_blank" rel="noreferrer">{document.filename}</a> : null}
                        {locator ? <span className="block text-xs text-muted">{locator}</span> : null}
                      </td>
                    </tr>;
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
      </> : null}
    </div>
  );
}

function Reliability({ confidence }: { confidence: number }) {
  const { label, Icon, tone } = confidence >= 0.9 ? { label: "Alta", Icon: CircleCheck, tone: "text-live" }
    : confidence >= 0.6 ? { label: "Media", Icon: CircleMinus, tone: "text-warning" }
    : { label: "Baja", Icon: CircleAlert, tone: "text-danger" };
  return <span className={`inline-flex items-center gap-1 ${tone}`}><Icon aria-hidden size={16} /> {label}</span>;
}

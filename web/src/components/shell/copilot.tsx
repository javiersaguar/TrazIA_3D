"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { MousePointerClick, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useRef } from "react";
import { CopilotMark } from "@/components/brand/copilot-mark";
import { CopilotConversation } from "@/features/copilot/conversation";
import { apiEnabled } from "@/lib/api/config";
import { Tip } from "@/components/ui/controls";
import { ConfidenceBar } from "@/components/ui/data";
import { Badge, EmptyState, Icon, Kbd } from "@/components/ui/primitives";
import { formatValue } from "@/lib/format";
import { cn } from "@/lib/cn";
import { riskLevel, type ReviewField } from "@/lib/mock/fields";
import { useReviewFields } from "@/lib/queries";
import { useSelection } from "@/stores/selection";
import { useUi } from "@/stores/ui";
import styles from "./copilot.module.css";

/** Consecuencias de un error por grupo de campo (reglas del roadmap, sin modelo de lenguaje). */
const CONSEQUENCE: Record<ReviewField["group"], string> = {
  Identificación: "El tag enlaza el modelo con la lista de equipos y con el resto de disciplinas.",
  Envolvente: "La envolvente fija la posición de las boquillas, las plataformas y la carga sobre la cimentación.",
  Soporte: "El faldón define la cota de las boquillas inferiores y la interfaz con civil.",
  Boquillas: "Una boquilla mal situada se propaga a piping: la tubería llegaría a un punto que no existe.",
  "Datos de diseño": "Los datos de diseño viajan como propiedades del IFC y los consultan mecánica y civil.",
};

export function CopilotTrigger({ floating = false, className }: { floating?: boolean; className?: string }) {
  const setOpen = useUi((s) => s.setCopilotOpen);
  const open = useUi((s) => s.copilotOpen);
  return (
    <Tip content={open ? "Cerrar Copiloto" : "Abrir Copiloto"} side={floating ? "left" : "bottom"}>
      <button
        type="button"
        aria-label={floating ? "Abrir copiloto" : "Copiloto"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? "copilot-panel" : undefined}
        onClick={() => setOpen(!open)}
        className={cn(
          "inline-flex shrink-0 items-center justify-center gap-1.5 border font-semibold transition-colors focus-visible:outline-offset-2",
          floating
            ? "copilot-launcher fixed right-5 bottom-5 z-30 size-[52px] rounded-2xl border-accent/40 bg-surface shadow-[var(--shadow-pop)]"
            : "h-9 min-w-10 rounded-[10px] px-2 text-[13px] sm:px-2.5",
          open ? "border-accent/55 bg-accent-soft text-accent-text" : "border-border-strong bg-surface-raised text-text hover:border-accent/60 hover:bg-accent-soft hover:text-accent-text",
          className,
        )}
      >
        <CopilotMark className={floating ? "size-7" : "size-[19px]"} />
        {floating ? null : <span className="hidden sm:inline">Copiloto</span>}
      </button>
    </Tip>
  );
}

export function CopilotLauncher() {
  const pathname = usePathname();
  if (pathname === "/modelo" || pathname === "/documentos" || pathname.startsWith("/revision") || pathname.startsWith("/cambios")) return null;
  return <CopilotTrigger floating />;
}

export function CopilotPanel() {
  const open = useUi((s) => s.copilotOpen);
  const setOpen = useUi((s) => s.setCopilotOpen);
  const revision = useUi((s) => s.revision);
  const selectedId = useSelection((s) => s.selectedId);
  const selectedPath = useSelection((s) => s.selectedPath);
  const { data: fields } = useReviewFields(revision);
  const pathname = usePathname();
  const tabbed = pathname === "/modelo" || pathname === "/documentos";
  const title = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  const field =
    fields?.find((f) => f.path === selectedPath) ?? fields?.find((f) => selectedId != null && f.elementId === selectedId);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen} modal={false}>
        <Dialog.Content
          id="copilot-panel"
          aria-label="Copiloto"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
            title.current?.focus({ preventScroll: true });
            title.current?.scrollIntoView({ block: "nearest" });
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            opener.current?.focus({ preventScroll: true });
          }}
          onInteractOutside={(e) => e.preventDefault()}
          data-testid="copilot-dock"
          className={cn(styles.dock,
            "fixed inset-x-2 bottom-[max(8px,env(safe-area-inset-bottom))] z-40 flex min-w-0 flex-col overflow-hidden rounded-[16px] border border-border-strong bg-surface shadow-[var(--shadow-pop)]",
            tabbed ? "top-[calc(var(--tabbed-topbar-height)+8px)]" : "top-[calc(var(--topbar-height)+8px)]",
            "md:relative md:inset-auto md:order-first md:mx-4 md:mt-3 md:h-[min(590px,74dvh)]",
            "xl:sticky xl:top-[calc(var(--topbar-height)+12px)] xl:order-last xl:mr-3 xl:ml-0 xl:h-[calc(100dvh-var(--topbar-height)-24px)] xl:w-[390px] xl:shrink-0",
          )}
        >
          <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface-raised px-4 py-2.5">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl border border-accent/25 bg-accent-soft">
              <CopilotMark className="size-6" />
            </span>
            <div className="min-w-0 flex-1">
              <Dialog.Title ref={title} tabIndex={-1} className="text-base leading-tight font-semibold text-strong outline-none">Copiloto</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted">{apiEnabled ? "Consultas y cambios de diseño" : "Evidencias de la revisión"}</Dialog.Description>
            </div>
            <Dialog.Close className="grid size-10 shrink-0 place-items-center rounded-lg text-muted hover:bg-surface-sunken hover:text-text" aria-label="Cerrar copiloto">
              <Icon icon={X} size={18} />
            </Dialog.Close>
          </header>

          {apiEnabled ? <CopilotConversation revision={revision} field={field} /> : (
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
              {field ? <Explanation field={field} /> : (
                <EmptyState icon={MousePointerClick} title="Selecciona un campo">
                  Elige un valor en la cola de revisión, una región del plano o un elemento del modelo para ver su fuente y su confianza.
                </EmptyState>
              )}
            </div>
          )}
        </Dialog.Content>
    </Dialog.Root>
  );
}

function Explanation({ field }: { field: ReviewField }) {
  const s = field.source;
  const where = s.page ? `página ${s.page}` : s.sheet && s.cell ? `hoja ${s.sheet}, celdas ${s.cell}` : s.locator;
  const level = riskLevel(field);
  return (
    <div className="space-y-5 text-[13px]">
      <div>
        <p className="text-xs text-muted">{field.group}</p>
        <p className="mt-0.5 text-[15px] font-semibold text-strong">{field.label}</p>
        <p className="mt-1 text-[22px] font-semibold text-text">{formatValue(field.correctedValue ?? field.value, field.unit)}</p>
      </div>

      <Section title="De dónde sale">
        Documento <span className="font-medium text-text">{s.document_id}</span>, {where}.
        {s.bbox ? " La región exacta está marcada en el plano." : " Viene de una celda de la hoja de datos."}
      </Section>

      <Section title="Por qué tiene esta confianza">
        <ConfidenceBar value={field.confidence} className="mb-1.5" />
        Lo ha leído el extractor de etiquetas: identifica el valor con una regla. El 0,75 marca que es un candidato, no una
        probabilidad calibrada; la calibración llegará con el bench.
      </Section>

      <Section title="Qué pasa si está mal">
        <Badge tone={level === "alto" ? "danger" : level === "medio" ? "warning" : "neutral"} className="mb-1.5">
          Riesgo {level}
        </Badge>
        <p>{CONSEQUENCE[field.group]}</p>
      </Section>

      <Section title="Qué puedes hacer">
        <ul className="space-y-1.5">
          <li className="flex items-center gap-2"><Kbd>A</Kbd> Aceptar si coincide con el plano.</li>
          <li className="flex items-center gap-2"><Kbd>E</Kbd> Corregir el valor.</li>
          <li className="flex items-center gap-2"><Kbd>S</Kbd> Marcarlo como supuesto si el plano no lo da.</li>
        </ul>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-medium text-faint">{title}</h3>
      <div className="leading-relaxed text-muted">{children}</div>
    </section>
  );
}

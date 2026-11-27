"use client";

import { ChevronRight, Database, Menu } from "lucide-react";
import { Suspense } from "react";
import { DocumentsNavigation } from "@/features/documents/documents-navigation";
import { ModelNavigation } from "@/features/workspace/model-navigation";
import { cn } from "@/lib/cn";
import { usePathname } from "next/navigation";
import { Tip } from "@/components/ui/controls";
import { Icon, Pill } from "@/components/ui/primitives";
import { apiEnabled } from "@/lib/api/config";
import { useApiSync } from "@/lib/api/use-api-sync";
import { navItemFor } from "@/lib/nav";
import { useUi } from "@/stores/ui";
import { useEquipment } from "@/stores/equipment";
import { CopilotTrigger } from "./copilot";
import { EquipmentPicker } from "./equipment-picker";

export function Topbar() {
  useApiSync();
  const pathname = usePathname();
  const item = navItemFor(pathname);
  const modelPage = pathname === "/modelo";
  const documentsPage = pathname === "/documentos";
  const tabbedPage = modelPage || documentsPage;
  const processProject = pathname.startsWith("/proyectos-proceso/");
  const inspectingJob = apiEnabled && (pathname === "/pipeline" || pathname.startsWith("/resultados/"));
  const setNavOpen = useUi((s) => s.setNavOpen);
  const project = useEquipment((s) => s.active?.project_id);

  return (
    <header
      style={{ viewTransitionName: "app-topbar" }}
      className={cn(
        "sticky top-0 z-30 flex items-center gap-2 border-b border-border bg-bg/95 px-3 backdrop-blur-md sm:gap-3",
        tabbedPage ? "h-[var(--tabbed-topbar-height)] flex-wrap content-center gap-y-0 md:flex-nowrap" : "h-[var(--topbar-height)] sm:px-5",
      )}
    >
      <button
        id="mobile-navigation-trigger"
        type="button"
        onClick={() => setNavOpen(true)}
        aria-label="Abrir navegación"
        className="-ml-1 flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface-raised hover:text-text lg:hidden"
      >
        <Icon icon={Menu} size={18} />
      </button>

      <nav aria-label="Ruta" className="flex min-w-0 items-center gap-1.5 text-[13px] whitespace-nowrap">
        {/* El proyecto solo cuando sobra sitio: a 1024 px con barra lateral, la pantalla va antes */}
        <span className="hidden font-mono text-[12px] text-faint xl:inline">{processProject ? "Proyectos" : project ?? "TrazIA"}</span>
        <Icon icon={ChevronRight} size={14} className="hidden text-faint xl:block" />
        {item ? <Icon icon={item.icon} size={15} className="text-muted" /> : null}
        <span className="truncate font-medium text-text">{processProject ? "Complejo de proceso" : item?.label ?? "Inicio"}</span>
      </nav>

      {tabbedPage ? (
        <div className="order-last min-w-0 basis-full overflow-x-auto md:order-none md:flex-1 md:basis-auto md:[&>div]:mx-auto md:[&>div]:flex">
          <Suspense>{modelPage ? <ModelNavigation /> : <DocumentsNavigation />}</Suspense>
        </div>
      ) : null}
      <div className="ml-auto flex shrink-0 items-center gap-2">
        {inspectingJob || processProject ? null : apiEnabled ? <span className={tabbedPage ? "[&_select]:max-w-[128px]" : "hidden md:inline-flex"}><EquipmentPicker /></span> : <Tip content="Equipo y revisión activos">
          <span className="hidden md:inline-flex">
            <Pill>
              <Icon icon={Database} size={14} />
              V-101
            </Pill>
          </span>
        </Tip>}
        <CopilotTrigger className={cn(!tabbedPage && "hidden md:inline-flex")} />
      </div>
    </header>
  );
}

export function WorkspaceTopbar() {
  useApiSync();
  const pathname = usePathname();
  const item = navItemFor(pathname);
  const setNavOpen = useUi(state => state.setNavOpen);

  return (
    <header style={{ viewTransitionName: "app-topbar" }}
      className="sticky top-0 z-30 flex h-[var(--topbar-height)] items-center gap-2 border-b border-border bg-bg/85 px-3 backdrop-blur-md sm:px-5 lg:hidden">
      <button id="mobile-navigation-trigger" type="button" onClick={() => setNavOpen(true)} aria-label="Abrir navegación"
        className="flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface-raised hover:text-text lg:hidden">
        <Icon icon={Menu} size={20} />
      </button>
      {item ? <span className="flex min-w-0 items-center gap-2 font-medium text-text">
        <Icon icon={item.icon} size={18} className="shrink-0 text-muted" />
        <span className="truncate">{item.label}</span>
      </span> : null}
    </header>
  );
}

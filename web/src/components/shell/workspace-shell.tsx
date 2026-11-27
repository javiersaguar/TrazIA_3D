"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { CommandMenu } from "./command-menu";
import { CopilotLauncher, CopilotPanel } from "./copilot";
import { useEnsureEquipment } from "./equipment-picker";
import { GlobalKeys } from "./global-keys";
import { ShortcutsDialog } from "./shortcuts-dialog";
import { MobileNav, Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function WorkspaceShell({ children }: { children: ReactNode }) {
  useEnsureEquipment();
  const pathname = usePathname();
  const modelPage = pathname === "/modelo";
  const documentsPage = pathname === "/documentos";
  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <div className="flex min-w-0 flex-1 flex-col gap-4 xl:flex-row" data-testid="app-workspace">
          <main className={cn("@container order-last mx-auto w-full min-w-0 flex-1 xl:order-first", modelPage ? "px-2 py-2 sm:px-3" : documentsPage ? "px-3 pt-2 pb-6 sm:px-4" : "max-w-[1520px] px-4 pt-5 pb-24 sm:px-6 sm:pt-6")}>{children}</main>
          <CopilotPanel />
        </div>
      </div>
      <MobileNav />
      <CommandMenu />
      <ShortcutsDialog />
      <CopilotLauncher />
      <GlobalKeys />
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge, Button } from "@/components/ui/primitives";
import { signOutAccount } from "@/lib/accounts";
import { DocumentsNavigation } from "@/features/documents/documents-navigation";

export function GuestWorkspace({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const visible = pathname === "/documentos" || pathname.startsWith("/proyectos-proceso/");
  useEffect(() => {
    if (!visible) router.replace("/documentos");
  }, [router, visible]);

  if (!visible) return null;
  return (
    <>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-[1520px] flex-wrap items-center gap-2 px-3 py-2 md:flex-nowrap md:gap-3">
          <Link href="/documentos" className="font-semibold text-strong">TrazIA-3D</Link>
          <Badge tone="neutral">Invitado · solo lectura</Badge>
          {pathname === "/documentos" ? (
            <div className="order-last basis-full md:order-none md:mx-auto md:basis-auto">
              <Suspense><DocumentsNavigation /></Suspense>
            </div>
          ) : null}
          <Button size="sm" className="ml-auto"
            onClick={() => void signOutAccount().catch(() => toast.error("No se pudo cerrar la sesión. Inténtalo de nuevo."))}>
            Salir
          </Button>
        </div>
      </header>
      <main className="@container mx-auto w-full max-w-[1520px] px-3 pt-2 pb-6 sm:px-4">{children}</main>
    </>
  );
}

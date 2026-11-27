"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useIsAdmin } from "@/lib/accounts";

/** Contenido solo para administradores; la API también lo comprueba en `/admin/*`. */
export function AdminOnly({ children }: { children: ReactNode }) {
  if (useIsAdmin()) return <>{children}</>;
  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <h1 className="text-xl font-semibold text-strong">Solo para administradores</h1>
      <p className="mt-2 text-sm text-muted">Esta sección la usan los administradores del proyecto. Tus diseños están en Documentos.</p>
      <Link href="/documentos" className="mt-5 inline-block text-sm text-accent-text underline">Ir a Documentos</Link>
    </div>
  );
}

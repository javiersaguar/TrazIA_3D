import type { Metadata } from "next";
import Link from "next/link";

import { LogoMark, LogoWordmark } from "@/components/brand/logo";
import { ReferenceSheet } from "@/features/landing/reference-sheet";

export const metadata: Metadata = { title: "Demo V-101" };

const vessel = { tag: "V-101", url: "/demo/ifc/rev_b.ifc", real: false } as const;

export default function VesselDemoPage() {
  return (
    <main className="min-h-dvh bg-bg px-5 pt-5 pb-6 text-text md:px-8">
      <div className="mx-auto max-w-[960px]">
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <Link href="/" aria-label="TrazIA 3D, inicio" className="flex items-center gap-3">
            <LogoMark className="size-9" />
            <LogoWordmark className="h-[15px] w-auto" />
          </Link>
          <Link href="/" className="rounded-[10px] border border-border-strong bg-surface-raised px-3.5 py-2 text-sm hover:border-accent">
            Volver al inicio
          </Link>
        </header>
        <h1 className="mb-4 text-2xl font-semibold tracking-tight text-strong">Recipiente V-101</h1>
        <ReferenceSheet play model={vessel} />
      </div>
    </main>
  );
}

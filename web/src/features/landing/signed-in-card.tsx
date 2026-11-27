"use client";

import Link from "next/link";
import { useState } from "react";

import { Avatar } from "@/components/shell/sidebar";
import { ROLE_LABEL, signOutAccount, type Account } from "@/lib/accounts";

export type LandingAccount = Pick<Account, "username" | "role" | "name" | "avatar">;

/** Sustituye al acceso cuando ya hay sesión: quién eres y entrar a la app. */
export function SignedInCard({ account }: { account: LandingAccount }) {
  const [leaving, setLeaving] = useState(false);
  const name = account.name ?? account.username;
  return (
    <div className="rounded-[16px] border border-border bg-surface/80 p-5 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <Avatar name={name} src={account.avatar} size={44} />
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold text-strong">{name}</p>
          <p className="text-[13px] text-muted">{ROLE_LABEL[account.role]}</p>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Link
          href="/documentos"
          className="inline-flex h-11 items-center rounded-[10px] bg-accent px-5 text-[14.5px] font-semibold text-accent-contrast transition-transform duration-[160ms] active:scale-[0.97]"
        >
          Ir a Documentos
        </Link>
        <button
          type="button"
          disabled={leaving}
          onClick={() => {
            setLeaving(true);
            void signOutAccount().catch(() => setLeaving(false));
          }}
          className="ml-auto text-[13px] text-faint hover:text-text"
        >
          {leaving ? "Saliendo…" : "Cerrar sesión"}
        </button>
      </div>
    </div>
  );
}

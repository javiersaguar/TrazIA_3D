"use client";

import { useAccount, type AccountProfile } from "@/lib/accounts";
import { cn } from "@/lib/cn";
import { Avatar } from "./sidebar";

const clave = (texto: string) => texto.normalize("NFD").replace(/\p{Diacritic}/gu, "").trim().toLowerCase();

/** Perfil del equipo que firma una acción: por nombre visible o por usuario. */
export function useAuthorProfile(author: string): AccountProfile | undefined {
  const account = useAccount();
  const buscado = clave(author);
  if (!buscado) return undefined;
  return [...(account?.profiles ?? []), ...(account?.team ?? [])].find(
    (profile) => clave(profile.username) === buscado || (profile.name ? clave(profile.name) === buscado : false),
  );
}

/** Nombre de quien hizo el cambio con su foto en pequeño; sin perfil conocido, solo el nombre. */
export function AuthorName({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  const profile = useAuthorProfile(name);
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1.5 align-middle text-text", className)}>
      {profile?.avatar ? <Avatar name={profile.name || name} src={profile.avatar} size={size} /> : null}
      <span className="truncate">{name}</span>
    </span>
  );
}

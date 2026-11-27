"use client";

import { createContext, useContext, type ReactNode } from "react";
import { accountsEnabled, apiURL } from "./api/config";
import { setSessionActor } from "./actor";

export type AccountProfile = { username: string; name?: string; avatar?: string | null };
export type Account = AccountProfile & { role: "admin" | "usuario" | "guest"; can_switch_role?: boolean; team?: AccountProfile[]; profiles?: AccountProfile[] };
const Session = createContext<Account | null>(null);

export function AccountProvider({ account, children }: { account: Account; children: ReactNode }) {
  setSessionActor(account.role === "guest" ? null : account.name || account.username);
  return <Session.Provider value={account}>{children}</Session.Provider>;
}

export const useAccount = () => useContext(Session);
export function useCanEdit() {
  const account = useAccount();
  return !accountsEnabled || account?.role === "admin" || account?.role === "usuario";
}
/** Sin cuentas (demo local) se muestra todo, como un administrador. */
export function useIsAdmin() {
  const account = useAccount();
  return !accountsEnabled || account?.role === "admin";
}
export const ROLE_LABEL: Record<Account["role"], string> = { admin: "Administrador", usuario: "Usuario", guest: "Invitado" };

export async function accountRequest(path: string, options?: RequestInit) {
  let response: Response;
  try {
    response = await fetch(apiURL(path), { ...options, cache: "no-store" });
  } catch (error) {
    if (error instanceof TypeError) throw new Error("No se pudo conectar con TrazIA‑3D. Revisa la conexión y vuelve a intentarlo.");
    throw error;
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (typeof data?.detail === "string") throw new Error(data.detail);
    if ([502, 503, 504].includes(response.status) || response.headers.has("ngrok-error-code")) {
      throw new Error("El servicio de TrazIA‑3D está temporalmente fuera de línea. Vuelve a intentarlo en unos segundos.");
    }
    throw new Error("El servidor no pudo completar la operación.");
  }
  return response;
}

export async function enterAccount(credentials?: { username: string; password: string }) {
  const response = await accountRequest(credentials ? "/auth/login" : "/auth/guest", credentials ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  } : { method: "POST" });
  return await response.json() as Account;
}

export async function switchTeamAccount(username: string, password: string) {
  await enterAccount({ username, password });
  reloadForAccount("/ajustes");
}

export async function signOutAccount() {
  await accountRequest("/auth/logout", { method: "POST" });
  reloadForAccount("/");
}

export async function switchSessionRole(role: "admin" | "usuario") {
  await accountRequest("/auth/session/role", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  reloadForAccount("/ajustes");
}

export function reloadForAccount(path: "/" | "/documentos" | "/ajustes") {
  // Se descartan la caché de navegación y los datos de la cuenta que se acaba de sustituir.
  window.location.replace(new URL(path, window.location.origin));
}

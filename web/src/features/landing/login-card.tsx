"use client";

import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Icon } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { startDemoSession } from "@/lib/session";
import { enterAccount, reloadForAccount } from "@/lib/accounts";
import { accountsEnabled, apiEnabled } from "@/lib/api/config";
import { queueGuidedTour } from "@/features/tour/guided-tour";

const field =
  "h-11 w-full rounded-[10px] border border-border bg-surface-sunken px-3.5 text-[15px] text-text placeholder:text-faint landing-compact:h-10 " +
  "transition-[border-color,box-shadow] duration-[var(--dur-base)] outline-none " +
  "focus-visible:border-accent focus-visible:shadow-[0_0_0_3px_var(--accent-soft)]";

export function LoginCard({ className }: { className?: string }) {
  const router = useRouter();
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState<"login" | "guest" | null>(null);
  const [error, setError] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (accountsEnabled) {
      void enter(false);
      return;
    }
    setBusy("login");
    startDemoSession(user);
    if (!apiEnabled) queueGuidedTour();
    setPassword("");
    // Un instante de respuesta antes de cambiar de pantalla
    window.setTimeout(() => router.push("/documentos"), 420);
  }

  async function enter(asGuest: boolean) {
    if (busy) return;
    setError("");
    setBusy(asGuest ? "guest" : "login");
    try {
      await enterAccount(asGuest ? undefined : { username: user, password });
      reloadForAccount("/documentos");
    } catch (error) {
      setError(error instanceof Error ? error.message : "No se pudo conectar con el servidor.");
      setPassword("");
      setBusy(null);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-labelledby="acceso-titulo"
      className={cn("surface-sheen rounded-[16px] border border-border bg-surface p-5 shadow-[var(--shadow-pop)] sm:p-6 landing-compact:p-4", className)}
    >
      <h2 id="acceso-titulo" className="text-[15px] font-semibold text-strong">
        {accountsEnabled ? "Iniciar sesión" : "Entra en la demo"}
      </h2>
      <p className="mt-1 text-[13px] text-muted">
        {accountsEnabled ? "Accede con tu cuenta de administrador o consulta los diseños como invitado." : "Demostración local con datos sintéticos."}
      </p>

      <div className="mt-5 space-y-3.5 landing-compact:mt-3 landing-compact:space-y-2">
        <div>
          <label htmlFor="acceso-usuario" className="mb-1.5 block text-[13px] text-muted landing-compact:mb-1">
            Usuario
          </label>
          <input
            id="acceso-usuario"
            name="usuario"
            autoComplete="username"
            spellCheck={false}
            maxLength={80}
            required={accountsEnabled}
            value={user}
            onChange={(e) => setUser(e.target.value)}
            placeholder="nombre.apellido"
            className={field}
          />
        </div>
        <div>
          <label htmlFor="acceso-contrasena" className="mb-1.5 block text-[13px] text-muted landing-compact:mb-1">
            Contraseña
          </label>
          <div className="relative">
            <input
              id="acceso-contrasena"
              name="contrasena"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              maxLength={256}
              required={accountsEnabled}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={cn(field, "pr-11")}
            />
            <button
              type="button"
              onClick={() => setShow((v) => !v)}
              aria-label={show ? "Ocultar contraseña" : "Mostrar contraseña"}
              aria-pressed={show}
              className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-[8px] text-faint transition-colors duration-[var(--dur-fast)] hover:bg-surface-raised hover:text-text"
            >
              <Icon icon={show ? EyeOff : Eye} size={16} />
            </button>
          </div>
        </div>
      </div>

      <button
        type="submit"
        disabled={busy !== null}
        className="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-accent text-[15px] font-semibold text-accent-contrast transition-[transform,background-color] duration-[160ms] ease-[var(--ease-out)] hover:bg-accent/90 active:scale-[0.98] disabled:opacity-80 landing-compact:mt-3 landing-compact:h-10"
      >
        {busy === "login" ? (
          <>
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
            Entrando
          </>
        ) : (
          "Iniciar"
        )}
      </button>
      {error ? <p role="alert" className="mt-3 text-sm text-danger">{error}</p> : null}
      {accountsEnabled ? (
        <button type="button" disabled={busy !== null} onClick={() => void enter(true)}
          className={cn(field, "mt-3 text-center font-medium hover:bg-surface-raised disabled:opacity-60 landing-compact:mt-2")}>
          {busy === "guest" ? "Entrando…" : "Entrar como invitado"}
        </button>
      ) : <p className="mt-3 text-[12px] text-faint" role="note">Las cuentas del equipo se activan con la API de acceso.</p>}
    </form>
  );
}

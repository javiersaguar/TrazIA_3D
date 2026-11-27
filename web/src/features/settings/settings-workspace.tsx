"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shell/page-header";
import { Avatar } from "@/components/shell/sidebar";
import { Badge, Button, Icon, Panel, PanelHeader } from "@/components/ui/primitives";
import { PROFILES, type Strategy } from "@/features/pipeline/graph-model";
import { ROLE_LABEL, accountRequest, switchSessionRole, switchTeamAccount, useAccount, type Account } from "@/lib/accounts";
import { accountsEnabled, apiEnabled, apiURL } from "@/lib/api/config";
import { cn } from "@/lib/cn";
import { useMounted } from "@/lib/use-mounted";
import { usePreferences, writeModelChoice, type ModelChoice } from "@/stores/preferences";

type ModelOption = { id: ModelChoice; nombre: string; detalle: string };
type ModelSettings = { actual: ModelChoice; opciones: ModelOption[] };
const modelSettingsKey = ["ajustes-modelos"] as const;

const ROLE_TEXT = {
  admin: "Ve y edita todo, incluidos Lotes e informes y Métricas.",
  usuario: "Sube planos, revisa los modelos y propone cambios.",
  guest: "Solo puede consultar el catálogo.",
} as const;

const THEMES = [
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Oscuro", icon: Moon },
  { value: "system", label: "Sistema", icon: Monitor },
] as const;

/** Ajustes: perfil, estrategia por defecto, modelo de lenguaje y apariencia. */
export function SettingsWorkspace() {
  return (
    <div className="space-y-5">
      <PageHeader title="Ajustes" description="Tu perfil y las preferencias con las que trabajas en la app." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Profile />
        <div className="space-y-4">
          <DefaultStrategy />
          <LanguageModel />
          <Appearance />
        </div>
      </div>
    </div>
  );
}

function Profile() {
  const account = useAccount();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const mounted = useMounted();
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      await accountRequest("/auth/avatar", { method: "PUT", body });
    },
    onSuccess: () => {
      toast.success("Foto de perfil actualizada");
      router.refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "No se pudo subir la foto"),
  });
  const roleSwitch = useMutation({ mutationFn: switchSessionRole });

  if (!accountsEnabled || !account) {
    return (
      <Panel className="p-5">
        <p className="text-[15px] font-semibold text-strong">Perfil</p>
        <p className="mt-1 text-[13px] text-muted">Las cuentas están desactivadas en esta instalación.</p>
      </Panel>
    );
  }
  const name = account.name ?? account.username;
  const canUpload = account.role !== "guest";
  return (
    <Panel className="flex flex-col items-center self-start p-6 text-center">
      <div className="relative">
        <Avatar name={name} src={account.avatar} size={112} />
        {canUpload ? (
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={!mounted || upload.isPending}
            aria-label="Cambiar foto de perfil"
            className="absolute right-0 bottom-0 flex size-9 items-center justify-center rounded-full border border-border-strong bg-surface text-text shadow-[var(--shadow-1)] transition-transform duration-150 hover:bg-surface-raised active:scale-[0.97]"
          >
            <Icon icon={Camera} size={16} />
          </button>
        ) : null}
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="sr-only"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
            e.target.value = "";
          }}
        />
      </div>
      <p className="mt-4 text-xl font-semibold text-strong">{name}</p>
      <p className="font-mono text-[12px] text-faint">{account.username}</p>
      <Badge tone={account.role === "admin" ? "accent" : "neutral"} className="mt-3">{ROLE_LABEL[account.role]}</Badge>
      <p className="mt-3 max-w-[32ch] text-[13px] text-muted">{ROLE_TEXT[account.role]}</p>
      {account.can_switch_role ? (
        <fieldset disabled={!mounted || roleSwitch.isPending} className="mt-5 grid w-full gap-2 border-t border-border pt-4 text-left">
          <legend className="sr-only">Rol activo</legend>
          <p className="font-semibold text-strong">Rol activo</p>
          <p className="text-[13px] text-muted">Prueba la interfaz y los permisos de este rol en tu sesión actual.</p>
          {(["admin", "usuario"] as const).map(role => (
            <Choice key={role} name="rol-activo" title={ROLE_LABEL[role]} text={ROLE_TEXT[role]}
              checked={account.role === role} onSelect={() => roleSwitch.mutate(role)} />
          ))}
          {roleSwitch.isPending ? <p role="status" className="text-sm text-muted">Cambiando de rol…</p> : null}
          {roleSwitch.isError ? <p role="alert" className="text-sm text-warning">{roleSwitch.error.message}</p> : null}
        </fieldset>
      ) : null}
      {account.team?.some(member => member.username !== account.username) ? <TeamAccountSwitch account={account} /> : null}
      {canUpload ? <p className="mt-4 text-[12px] text-faint">Foto en PNG, JPEG o WebP de hasta 1 MB.</p> : null}
    </Panel>
  );
}

function TeamAccountSwitch({ account }: { account: Account }) {
  const mounted = useMounted();
  const members = account.team?.filter(member => member.username !== account.username) ?? [];
  const [username, setUsername] = useState("");
  const member = members.find(profile => profile.username === username);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!member || pending) return;
    const form = event.currentTarget;
    const password = new FormData(form).get("password");
    if (typeof password !== "string" || !password) return;
    setError("");
    setPending(true);
    try {
      await switchTeamAccount(member.username, password);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "No se pudo cambiar de cuenta.");
      setPending(false);
    }
  }

  return (
    <form aria-label="Cambiar de cuenta" onSubmit={submit} className="mt-5 grid w-full gap-3 border-t border-border pt-4 text-left">
      <p className="font-semibold text-strong">Cambiar de cuenta</p>
      <label className="grid gap-1 text-sm text-muted">
        Integrante del equipo
        <select name="username" autoComplete="username" value={username}
          onChange={event => { setUsername(event.target.value); setError(""); }}
          required disabled={!mounted || pending} className="min-h-11 rounded-md border border-border bg-surface px-2 text-text">
          <option value="" disabled>Selecciona una cuenta</option>
          {members.map(profile => <option key={profile.username} value={profile.username}>{profile.name ?? profile.username}</option>)}
        </select>
      </label>
      {member ? (
        <div className="flex items-center gap-3 text-sm text-strong">
          <Avatar name={member.name ?? member.username} src={member.avatar} />
          <span>{member.name ?? member.username}</span>
        </div>
      ) : null}
      <label className="grid gap-1 text-sm text-muted">
        Contraseña de la cuenta
        <input key={username} name="password" type="password" autoComplete="current-password" required maxLength={256}
          disabled={!mounted || !member || pending} className="min-h-11 rounded-md border border-border bg-surface px-2 text-text" />
      </label>
      <Button type="submit" disabled={!mounted || !member || pending}>{pending ? "Cambiando de cuenta…" : "Iniciar con esta cuenta"}</Button>
      {error ? <p role="alert" className="text-sm text-warning">{error}</p> : null}
    </form>
  );
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Panel>
      <PanelHeader title={title} description={description} />
      <div className="px-5 pb-5">{children}</div>
    </Panel>
  );
}

function Choice({ checked, onSelect, title, text, name }: { checked: boolean; onSelect: () => void; title: string; text: string; name: string }) {
  return (
    <label
      className={cn(
        "block cursor-pointer rounded-[var(--radius-card)] border p-3 transition-[border-color,background-color] duration-[var(--dur-base)] has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent",
        checked ? "border-accent bg-accent-soft" : "border-border hover:border-border-strong",
      )}
    >
      <input type="radio" name={name} checked={checked} onChange={onSelect} className="sr-only" />
      <span className="flex items-center gap-2 text-[14px] font-medium text-strong">
        <span className={cn("size-3.5 shrink-0 rounded-full border", checked ? "border-[4px] border-accent" : "border-border-strong")} aria-hidden />
        {title}
      </span>
      <span className="mt-1 block text-[12.5px] text-muted">{text}</span>
    </label>
  );
}

function DefaultStrategy() {
  const strategy = usePreferences((s) => s.strategy);
  const setStrategy = usePreferences((s) => s.setStrategy);
  const mounted = useMounted();
  return (
    <Section title="Estrategia por defecto" description="La que se usa al leer los planos que subes. Puedes cambiarla en cada trabajo.">
      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend className="sr-only">Estrategia por defecto</legend>
        {(Object.entries(PROFILES) as [Strategy, (typeof PROFILES)[Strategy]][]).map(([value, profile]) => (
          <Choice
            key={value}
            name="estrategia"
            checked={mounted && strategy === value}
            onSelect={() => {
              setStrategy(value);
              toast.success(`Estrategia por defecto: ${profile.name}`);
            }}
            title={profile.name}
            text={profile.detail}
          />
        ))}
      </fieldset>
    </Section>
  );
}

function LanguageModel() {
  const queryClient = useQueryClient();
  const options = useQuery({
    queryKey: modelSettingsKey,
    enabled: apiEnabled,
    queryFn: async () => {
      const response = await fetch(apiURL("/ajustes/modelos"));
      if (!response.ok) throw new Error("No se pudieron leer los modelos disponibles");
      return (await response.json()) as ModelSettings;
    },
  });
  const choice = options.data?.actual ?? "auto";
  if (!apiEnabled) return null;
  return (
    <Section
      title="API utilizada"
      description="Preferencia para el Copiloto. Si la opción elegida no está disponible, se usa el respaldo permitido. Azure OpenAI es el único proveedor externo para datos del reto."
    >
      {options.isError ? <p className="mb-2 text-[13px] text-warning">{options.error.message}</p> : null}
      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend className="sr-only">Modelo de lenguaje</legend>
        {(options.data?.opciones ?? []).map((o) => {
          const local = o.id === "ninguno";
          const title = local ? "Modelo local" : o.nombre;
          return (
            <Choice
              key={o.id}
              name="modelo"
              checked={choice === o.id}
              onSelect={() => {
                writeModelChoice(o.id);
                queryClient.setQueryData<ModelSettings>(modelSettingsKey, current => current && { ...current, actual: o.id });
                toast.success(`Preferencia guardada: ${title}`);
              }}
              title={title}
              text={local ? "El Copiloto usa las reglas y fuentes locales." : o.detalle}
            />
          );
        })}
      </fieldset>
    </Section>
  );
}

function Appearance() {
  const { theme, setTheme } = useTheme();
  const mounted = useMounted();
  return (
    <Section title="Apariencia" description="Sistema sigue el modo claro u oscuro de tu equipo.">
      <div role="radiogroup" aria-label="Apariencia" className="grid grid-cols-3 gap-2">
        {THEMES.map((t) => {
          const active = mounted && theme === t.value;
          return (
            <Button
              key={t.value}
              role="radio"
              aria-checked={active}
              variant={active ? "primary" : "secondary"}
              onClick={() => setTheme(t.value)}
              className="w-full justify-center"
            >
              <Icon icon={t.icon} size={15} />
              {t.label}
            </Button>
          );
        })}
      </div>
    </Section>
  );
}

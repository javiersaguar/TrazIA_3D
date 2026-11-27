"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { LogOut, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { LogoMark, LogoWordmark } from "@/components/brand/logo";
import { Tip } from "@/components/ui/controls";
import { Icon } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { SETTINGS_ITEM, navFor, navItemFor, type NavItem } from "@/lib/nav";
import { endDemoSession, initialsOf, useDemoUser } from "@/lib/session";
import { ROLE_LABEL, useAccount, useIsAdmin, signOutAccount } from "@/lib/accounts";
import { accountsEnabled, apiURL } from "@/lib/api/config";
import { toast } from "sonner";
import { useUi } from "@/stores/ui";

/** Barra lateral fija desde 1024 px. Por debajo, la misma navegación vive en MobileNav. */
export function Sidebar() {
  const collapsed = useUi((s) => s.sidebarCollapsed);
  return (
    // El fondo ocupa toda la altura de la página; el contenido queda fijo al desplazarse
    <aside
      style={{ width: collapsed ? "var(--sidebar-collapsed)" : "var(--sidebar-width)" }}
      className="hidden shrink-0 border-r border-border bg-sidebar lg:block"
    >
      <div style={{ viewTransitionName: "app-sidebar" }} className="sticky top-0 flex h-dvh flex-col">
        <SidebarBody collapsed={collapsed} />
      </div>
    </aside>
  );
}

/** Panel que entra desde la izquierda en móvil y tableta vertical. */
export function MobileNav() {
  const open = useUi((s) => s.navOpen);
  const setOpen = useUi((s) => s.setNavOpen);

  // Si la ventana crece hasta mostrar la barra fija, el panel se cierra para no bloquear la página
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => mq.matches && setOpen(false);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [setOpen]);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="cmd-overlay fixed inset-0 z-50 bg-[var(--scrim)] lg:hidden" />
        <Dialog.Content
          aria-describedby={undefined}
          onCloseAutoFocus={event => {
            event.preventDefault();
            document.getElementById("mobile-navigation-trigger")?.focus();
          }}
          className="nav-sheet fixed inset-y-0 left-0 z-50 flex w-[min(232px,86vw)] flex-col border-r border-border bg-sidebar shadow-[var(--shadow-pop)] lg:hidden"
        >
          <Dialog.Title className="sr-only">Navegación</Dialog.Title>
          {/* Grupo propio: la píldora activa no salta desde la barra fija oculta */}
          <LayoutGroup id="nav-movil">
            <SidebarBody collapsed={false} onNavigate={() => setOpen(false)} />
          </LayoutGroup>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function SidebarBody({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = navItemFor(pathname)?.href;
  const toggle = useUi((s) => s.toggleSidebar);
  const mobile = onNavigate != null;
  const groups = navFor(useIsAdmin());
  const toggleLabel = collapsed ? "Desplegar barra lateral" : "Plegar barra lateral";

  return (
    <>
      <div className={cn("flex shrink-0 items-center gap-2 border-b border-border p-2", collapsed && "flex-col")}>
        <Link href="/documentos" onClick={onNavigate} aria-label="TrazIA 3D · Documentos"
          className={cn("flex min-h-11 flex-1 items-center gap-2 rounded-[var(--radius-control)]", collapsed && "min-w-11 justify-center")}>
          <LogoMark className="size-8 shrink-0" />
          {!collapsed ? <LogoWordmark className="h-[11px] w-auto" title="TrazIA 3D" /> : null}
        </Link>
        {mobile ? (
          <Dialog.Close aria-label="Cerrar navegación" className={footButton}>
            <Icon icon={X} size={20} />
          </Dialog.Close>
        ) : (
          <Tip content={toggleLabel} side="right">
            <button type="button" onClick={toggle} className={footButton} aria-label={toggleLabel}>
              <Icon icon={collapsed ? PanelLeftOpen : PanelLeftClose} size={20} />
            </button>
          </Tip>
        )}
      </div>

      <nav aria-label="Navegación principal" className="flex-1 overflow-y-auto p-2 pt-4">
        {groups.map(group => <div key={group.label} className="mb-4">
        {!collapsed && groups.length > 1 ? <p className="px-2.5 pb-1.5 text-[12px] text-faint">{group.label}</p> : null}
        <ul className="space-y-1">
          {group.items.map((item: NavItem) => {
            const isActive = item.href === active;
            return (
              <li key={item.href}>
                <Link href={item.href} onClick={onNavigate} aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "relative flex min-h-11 items-center gap-2.5 rounded-[9px] px-2.5 text-[15px]",
                    collapsed && "justify-center px-0",
                    isActive ? "font-semibold text-strong" : "text-muted hover:bg-surface-raised hover:text-text",
                  )}>
                  {isActive ? <motion.span layoutId="nav-active" className="nav-pill absolute inset-0 rounded-[10px]"
                    transition={{ type: "spring", duration: 0.35, bounce: 0.12 }} /> : null}
                  <Icon icon={item.icon} size={20} className={cn("relative shrink-0", isActive && "text-accent-text")} />
                  <span className={collapsed ? "sr-only" : "relative"}>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
        </div>)}
      </nav>
      <div className="border-t border-border p-2">
        <Link href={SETTINGS_ITEM.href} onClick={onNavigate} aria-current={active === SETTINGS_ITEM.href ? "page" : undefined}
          className={cn("mb-1 flex min-h-11 items-center gap-3 rounded-[10px] px-2.5 text-[15px] lg:min-h-10", collapsed && "justify-center px-0",
            active === SETTINGS_ITEM.href ? "font-semibold text-strong" : "text-muted hover:bg-surface-raised hover:text-text")}>
          <Icon icon={SETTINGS_ITEM.icon} size={18} className="shrink-0" />
          <span className={collapsed ? "sr-only" : undefined}>{SETTINGS_ITEM.label}</span>
        </Link>
        <UserRow collapsed={collapsed} onSignOut={onNavigate} />
      </div>
    </>
  );
}

/** Identidad de la cuenta y cierre de sesión. */
function UserRow({ collapsed, onSignOut }: { collapsed: boolean; onSignOut?: () => void }) {
  const demoUser = useDemoUser() ?? "demo";
  const account = useAccount();
  const user = account?.name ?? account?.username ?? demoUser;
  const label = account ? ROLE_LABEL[account.role] : "Sesión demo";
  const avatar = <Avatar name={user} src={account?.avatar} />;
  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-1">
        <Tip content={`${user} · ${label}`} side="right">
          <span className="flex size-9 items-center justify-center">{avatar}</span>
        </Tip>
        <SignOut onDone={onSignOut} />
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2.5 px-1">
      {avatar}
      <span className="min-w-0 flex-1 leading-tight">
        <span className="block truncate text-[13px] text-text">{user}</span>
        <span className="block truncate font-mono text-[10.5px] text-faint">{label}</span>
      </span>
      <SignOut onDone={onSignOut} />
    </div>
  );
}

/** Foto de perfil o, si no hay, las iniciales. */
export function Avatar({ name, src, size = 32 }: { name: string; src?: string | null; size?: number }) {
  return src ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={apiURL(src)} alt="" width={size} height={size} style={{ width: size, height: size }}
      className="shrink-0 rounded-full border border-border-strong object-cover" />
  ) : (
    <span style={{ width: size, height: size, fontSize: Math.round(size / 2.9) }}
      className="inline-flex shrink-0 items-center justify-center rounded-full border border-border-strong bg-surface-raised font-mono text-text">
      {initialsOf(name)}
    </span>
  );
}

const footButton =
  "flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors duration-[var(--dur-fast)] hover:bg-surface-raised hover:text-text";

function SignOut({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  return (
    <Tip content="Salir" side="top">
      <button
        type="button"
        aria-label="Salir"
        onClick={() => {
          onDone?.();
          if (accountsEnabled) {
            void signOutAccount().catch(() => toast.error("No se pudo cerrar la sesión. Inténtalo de nuevo."));
            return;
          }
          endDemoSession();
          router.push("/");
        }}
        className={footButton}
      >
        <Icon icon={LogOut} size={16} />
      </button>
    </Tip>
  );
}

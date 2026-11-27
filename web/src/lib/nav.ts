import { Activity, Box, FileStack, Layers, Settings, Workflow, type LucideIcon } from "lucide-react";
export type NavItem = { href: string; label: string; icon: LucideIcon; description: string; shortcut?: string; soon?: string; sketch?: boolean; admin?: boolean };
export type NavGroup = { label: string; items: NavItem[]; admin?: boolean };
export const SETTINGS_ITEM: NavItem = { href: "/ajustes", label: "Ajustes", icon: Settings, shortcut: "s", description: "Estrategia por defecto, API, apariencia y perfil." };
const PROCESS_ITEM: NavItem = { href: "/pipeline", label: "Proceso", icon: Workflow, description: "Etapas y eventos de cada ejecución, con su procedencia." };
export const NAV: NavGroup[] = [
 { label: "Trabajo", items: [
  { href: "/documentos", label: "Documentos", icon: FileStack, shortcut: "d", description: "Equipos del dataset, sus planos y su estado. Sube planos nuevos desde aquí." },
  { href: "/modelo", label: "Modelo", icon: Box, shortcut: "m", description: "Revisa la evidencia, compara revisiones y explora el IFC en un único espacio." },
 ]},
 { label: "Administración", admin: true, items: [
  { href: "/lote", label: "Lotes", icon: Layers, shortcut: "l", admin: true, description: "Procesamiento del dataset y exportaciones con la huella de sus datos." },
  { href: "/metricas", label: "Métricas", icon: Activity, shortcut: "k", admin: true, description: "Cómo está funcionando la app: trabajos, etapas, modelos de lenguaje y lote." },
 ]},
];
export const NAV_ITEMS = [...NAV.flatMap(g => g.items), SETTINGS_ITEM];
/** Apartados visibles para un rol: los de administración, solo para admin. */
export function navFor(isAdmin: boolean): NavGroup[] {
 if (isAdmin) return NAV;
 return NAV.filter(group => !group.admin).map(group => ({
   ...group, items: group.items.filter(item => !item.admin),
 }));
}
export const WORKSPACE_NAV = NAV_ITEMS.filter(item => ["/documentos", "/modelo"].includes(item.href));
export function navItemFor(pathname: string): NavItem | undefined {
 const aliases: Record<string,string> = { "/revision": "/modelo", "/cambios": "/modelo", "/proyectos": "/documentos", "/familias": "/documentos", "/informes": "/lote" };
 const path = aliases[pathname] ?? pathname;
 return [PROCESS_ITEM, ...NAV_ITEMS].find(i => path === i.href || path.startsWith(`${i.href}/`));
}

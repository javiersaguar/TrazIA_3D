import { apiURL } from "@/lib/api/config";

/** Formatos compartidos por Métricas y Lotes e informes. */
export const NUM = new Intl.NumberFormat("es-ES", { useGrouping: "always" });
export const DEC = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1, useGrouping: "always" });
export const EUR = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
const COMPACT = new Intl.NumberFormat("es-ES", { notation: "compact", maximumFractionDigits: 1 });
const RELATIVE = new Intl.RelativeTimeFormat("es-ES", { numeric: "auto" });
const DAY = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });
const DAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" });
const TIME = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });
export const DATETIME = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const compact = (n: number) => COMPACT.format(n);

/** «hace 3 min», «ayer», «hace 2 días». */
export function ago(iso: string, now = Date.now()): string {
  const seconds = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(seconds);
  if (abs < 45) return "ahora";
  if (abs < 3600) return RELATIVE.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return RELATIVE.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 7) return RELATIVE.format(Math.round(seconds / 86400), "day");
  return DAY.format(new Date(iso));
}

/** Duración legible: 0,4 s · 12 s · 3 min 5 s · 1 h 20 min. */
export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 10) return `${DEC.format(seconds)} s`;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s ? `${m} min ${s} s` : `${m} min`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Etiqueta de un instante del eje según el tamaño del cubo. */
export function tick(iso: string, stepHours: number): string {
  const date = new Date(iso);
  return stepHours >= 24 ? DAY.format(date) : TIME.format(date);
}

/** «Hoy», «Ayer» o la fecha larga, para agrupar listas por día. */
export function dayGroup(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((start(now) - start(date)) / 86400000);
  if (days === 0) return "Hoy";
  if (days === 1) return "Ayer";
  const label = DAY_LONG.format(date);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export const sum = (values: (number | null)[]) => values.reduce<number>((a, b) => a + (b ?? 0), 0);

/** Iniciales para el avatar de una persona («javier.saguar» → JS). */
export function initials(name: string | null): string {
  if (!name) return "·";
  const parts = name.match(/[\p{L}\p{N}]+/gu) ?? [];
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "·";
}

/**
 * Petición JSON a la API con el mensaje de error que devuelve. Las credenciales van por defecto
 * (mismo origen): con cuentas, la sesión viaja por el proxy `/api/trazia`; contra una API directa,
 * `include` haría que CORS rechazase la respuesta.
 */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiURL(path), { cache: "no-store", ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `La API respondió ${response.status}`);
  }
  return response.json() as Promise<T>;
}

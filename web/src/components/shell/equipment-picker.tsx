"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiEnabled } from "@/lib/api/config";
import { useEquipment as useEquipmentRows } from "@/lib/queries";
import { useEquipment, type ActiveEquipment } from "@/stores/equipment";
import type { EquipmentRow } from "@/lib/mock/api";

export function toActive(row: EquipmentRow): ActiveEquipment {
  return {
    project_id: row.project_id ?? "",
    equipment_id: row.equipment_id ?? row.tag.toLowerCase(),
    tag: row.tag,
    revisions: row.revisions,
  };
}

/** Si no hay equipo activo (o ya no existe en la API), se elige el primero con modelo. */
export function useEnsureEquipment() {
  const rows = useEquipmentRows();
  const active = useEquipment((s) => s.active);
  const setActive = useEquipment((s) => s.setActive);
  useEffect(() => {
    if (!apiEnabled || !rows.data?.length) return;
    // La ruta del modelo puede haber activado una revisión durante este mismo montaje.
    const current = useEquipment.getState().active;
    if (current?.revisionWindow) return;
    const match = rows.data.find((r) => r.tag === current?.tag && (r.project_id ?? "") === current?.project_id);
    const first = rows.data[0];
    if (!match) { if (first) setActive(toActive(first)); }
    else if (match.revisions.join() !== current?.revisions.join()) setActive(toActive(match));
  }, [rows.data, active, setActive]);
}

/** Equipo activo en la barra superior. La revisión se elige dentro de cada pantalla. */
export function EquipmentPicker() {
  const pathname = usePathname();
  const router = useRouter();
  const rows = useEquipmentRows();
  const active = useEquipment((s) => s.active);
  const setActive = useEquipment((s) => s.setActive);
  if (!apiEnabled || !rows.data?.length || !active) return null;
  return (
    <div className="flex items-center gap-2">
      <label className="sr-only" htmlFor="equipo-activo">Equipo</label>
      <select
        id="equipo-activo"
        value={`${active.project_id}:${active.tag}`}
        onChange={(e) => {
          const row = rows.data.find((r) => `${r.project_id ?? ""}:${r.tag}` === e.target.value);
          if (!row) return;
          setActive(toActive(row));
          if (pathname === "/modelo") {
            const query = new URLSearchParams(window.location.search);
            if (!query.has("resultado")) return;
            query.delete("resultado");
            if (!query.has("vista")) query.set("vista", "revision");
            router.replace(`/modelo?${query}`, { scroll: false });
          }
        }}
        className="h-8 rounded-[var(--radius-control)] border border-border bg-surface px-2 font-mono text-[12px] text-text"
      >
        {rows.data.map((r) => (
          <option key={`${r.project_id}:${r.tag}`} value={`${r.project_id ?? ""}:${r.tag}`}>
            {r.tag}
          </option>
        ))}
      </select>
    </div>
  );
}

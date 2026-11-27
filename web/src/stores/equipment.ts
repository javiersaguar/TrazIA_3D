"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { RevisionId } from "@/lib/mock/api";

/** Equipo del dataset que se está revisando. «A» es su revisión anterior y «B» la última. */
export type ActiveEquipment = {
  project_id: string;
  equipment_id: string;
  tag: string;
  revisions: string[];
  revisionWindow?: readonly [string, string];
};

type EquipmentState = {
  active: ActiveEquipment | null;
  openedResult: string | null;
  setActive: (equipment: ActiveEquipment, openedResult?: string) => void;
};

export const useEquipment = create<EquipmentState>()(
  persist(
    (set) => ({
      active: null,
      openedResult: null,
      setActive: (active, openedResult) => set({ active, openedResult: openedResult ?? null }),
    }),
    {
      name: "trazia-equipo",
      storage: createJSONStorage(() => window.localStorage),
      partialize: ({ active }) => ({ active }),
    },
  ),
);

export const activeEquipment = () => useEquipment.getState().active;

/** Etiqueta de la revisión (`1`, `2`…) que ocupa la posición A o B del equipo activo. */
export function revisionLabel(rev: RevisionId, equipment = activeEquipment()): string {
  const revisions = equipment?.revisionWindow ?? equipment?.revisions ?? [];
  if (!revisions.length) return rev;
  return (rev === "B" ? revisions[revisions.length - 1] : revisions[Math.max(0, revisions.length - 2)]) ?? rev;
}

/** Identidad de la revisión en la API: `proyecto:equipo:revisión`. */
export function revisionIdentity(rev: RevisionId, equipment = activeEquipment()): string {
  if (!equipment) return rev;
  return `${equipment.project_id}:${equipment.equipment_id}:${revisionLabel(rev, equipment)}`;
}

export const activeTag = () => activeEquipment()?.tag ?? "—";

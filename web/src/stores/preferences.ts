"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Strategy } from "@/features/pipeline/graph-model";

export type ModelChoice = "auto" | "azure" | "groq" | "ninguno";

type Preferences = {
  /** Estrategia con la que arranca el pipeline al subir planos. */
  strategy: Strategy;
  setStrategy: (strategy: Strategy) => void;
};

export const usePreferences = create<Preferences>()(
  persist(
    (set) => ({
      strategy: "lectura",
      setStrategy: (strategy) => set({ strategy }),
    }),
    { name: "trazia-preferencias", storage: createJSONStorage(() => window.localStorage) },
  ),
);

const MODEL_COOKIE = "trazia_modelo";

/** El modelo preferido viaja en una cookie para que la API lo aplique en el copiloto y la voz. */
export function writeModelChoice(choice: ModelChoice) {
  document.cookie = `${MODEL_COOKIE}=${choice}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
}

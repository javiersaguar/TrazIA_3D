"use client";

import { ClipboardCheck, GitCompareArrows } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Segmented } from "@/components/ui/controls";
import { Icon } from "@/components/ui/primitives";
import { LEGACY_VIEWS, modelHref, type ModelView } from "./model-links";

const LABELS: Record<ModelView, string> = {
  revision: "Revisión",
  cambios: "Cambios",
};

export function useModelNavigation() {
  const params = useSearchParams();
  const options = (Object.keys(LABELS) as ModelView[]).map(value => ({ value, label: LABELS[value] }));
  const identity = params.get("resultado") || undefined;
  const raw = params.get("vista") ?? "";
  const requested = options.find(({ value }) => value === raw)?.value ?? (Object.hasOwn(LEGACY_VIEWS, raw) ? LEGACY_VIEWS[raw] : undefined);
  return { identity, options, active: requested ?? ("revision" as const) };
}

export function ModelNavigation() {
  const { identity, options, active } = useModelNavigation();
  const router = useRouter();
  return (
    <Segmented<ModelView>
      label="Espacio del modelo"
      value={active}
      onChange={value => router.replace(modelHref(value, identity), { scroll: false })}
      options={options.map(({ value, label }) => ({
        value,
        label: <span className="inline-flex items-center gap-1.5">
          <Icon icon={value === "revision" ? ClipboardCheck : GitCompareArrows} size={15} /> {label}
        </span>,
      }))}
      className="w-max flex-nowrap rounded-lg border border-border bg-surface whitespace-nowrap sm:h-auto [&_button]:min-h-9 [&_button]:px-3 [&_button]:sm:min-h-8"
    />
  );
}

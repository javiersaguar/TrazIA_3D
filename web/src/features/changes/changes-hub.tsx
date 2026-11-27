"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Segmented } from "@/components/ui/controls";
import { DesignEditWorkspace } from "@/features/design-edit/design-edit";
import { ChangeHistory, type ChangeEntry } from "@/features/hologram/change-history";
import { VersionHistory, useVersions, type Version } from "@/features/revisions/version-history";
import { apiEnabled } from "@/lib/api/config";
import { useChanges, useRevision } from "@/lib/queries";
import { useUi } from "@/stores/ui";
import { CHANGES_SECTIONS, changesSection, type ChangesSection } from "./sections";
import { VersionCompare, type CompareTarget } from "./version-compare";

const INTRO: Record<ChangesSection, string> = {
  comparar: "Elige dos versiones del equipo y mira en 3D qué piezas han cambiado y cuánto.",
  proponer: "Escribe el cambio que quieres o ajusta los valores. Nada se guarda hasta que lo confirmes, y el original no se toca.",
  historial: "Todas las versiones guardadas del equipo y quién hizo cada cambio.",
};

/*
  Pestaña Cambios de Modelo, en tres secciones para no mezclarlo todo en una página:
  «Qué ha cambiado» (comparador 3D), «Proponer un cambio» (formulario) e «Historial»
  (versiones y actividad). Elegir algo en el historial abre el comparador con esa entrada.
*/
export function ChangesHub() {
  const params = useSearchParams();
  const router = useRouter();
  const section = changesSection(params.get("seccion"), params.get("vista"));
  const { versions, loading, activate } = useVersions();
  const revision = useUi((s) => s.revision);
  const open = useRevision(revision).data;
  const openLabel = open?.revision;
  const demoDiff = useChanges().data;
  const [chosen, setChosen] = useState<CompareTarget | null>(null);
  const [entryKey, setEntryKey] = useState<string | null>(null);

  const go = (next: ChangesSection) => {
    const query = new URLSearchParams(params.toString());
    query.set("seccion", next);
    router.replace(`/modelo?${query}`, { scroll: false });
  };

  function versionTarget(from: Version, to: Version): CompareTarget | null {
    if (!from.ifc || !to.ifc) return null;
    // Sin API solo existe el diff A → B de la demo.
    if (!apiEnabled && !(from.label === "A" && to.label === "B")) return null;
    return {
      key: `version:${from.identity}:${to.identity}`,
      title: `Versión ${from.label} → ${to.label}`,
      fromLabel: from.label,
      toLabel: to.label,
      fromUrl: from.ifc,
      toUrl: to.ifc,
      dataset: to.dataset ?? from.dataset,
      ...(apiEnabled ? { diff: { from: from.identity, to: to.identity } } : demoDiff ? { changes: demoDiff } : {}),
    };
  }

  // Sin elección, el comparador abre la última versión frente a la anterior.
  const fallback = versions.length > 1 ? versionTarget(versions[1]!, versions[0]!) : null;
  const target = chosen ?? fallback;

  const show = (next: CompareTarget | null, key: string | null) => {
    setChosen(next);
    setEntryKey(key);
    if (next) go("comparar");
  };

  const pickVersions = (from: Version, to: Version) => {
    const next = versionTarget(from, to);
    if (next) show(next, null);
  };

  const pickEntry = (entry: ChangeEntry | null) => {
    if (!entry) return show(null, null);
    show({
      key: entry.key,
      title: entry.title,
      fromLabel: entry.fromRevision ?? entry.revision,
      toLabel: entry.revision,
      fromUrl: entry.fromUrl,
      toUrl: entry.toUrl,
      dataset: open?.dataset ?? null,
      ...(entry.changes ? { changes: entry.changes } : {}),
      ...(entry.diff ? { diff: entry.diff } : {}),
    }, entry.key);
  };

  const comparing = target && !entryKey ? { from: target.fromLabel, to: target.toLabel } : null;

  return (
    <div className="space-y-5" data-testid="changes-hub">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <p className="max-w-2xl text-sm text-muted">{INTRO[section]}</p>
        <Segmented<ChangesSection>
          label="Sección de cambios"
          value={section}
          onChange={go}
          options={CHANGES_SECTIONS}
        />
      </div>

      {section === "comparar" ? (
        <VersionCompare key={target?.key ?? "empty"} target={target} versions={versions} onPick={pickVersions} />
      ) : section === "proponer" ? (
        <DesignEditWorkspace />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <VersionHistory
            versions={versions}
            loading={loading}
            openLabel={openLabel}
            comparing={comparing}
            onCompare={pickVersions}
            onActivate={activate}
          />
          <ChangeHistory activeKey={entryKey} onSelect={pickEntry} />
        </div>
      )}
    </div>
  );
}

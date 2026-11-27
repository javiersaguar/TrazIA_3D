"use client";

import { useQuery } from "@tanstack/react-query";
import {
  getBench,
  getChanges,
  getEquipment,
  getReviewFields,
  getRevision,
  getStudy,
  type BenchExtractor,
  type RevisionId,
} from "./api";
import { apiEnabled, revisionResource } from "./api/config";
import { DEMO } from "./mock/api";

export const qk = {
  revision: (rev: RevisionId) => ["revision", rev] as const,
  fields: (rev: RevisionId) => ["review-fields", rev] as const,
  changes: () => ["changes", "A", "B"] as const,
  equipment: () => ["equipment"] as const,
};

export const useRevision = (rev: RevisionId) => useQuery({ queryKey: qk.revision(rev), queryFn: () => getRevision(rev) });

export const useReviewFields = (rev: RevisionId) =>
  useQuery({ queryKey: qk.fields(rev), queryFn: () => getReviewFields(rev) });

export const useChanges = () => useQuery({ queryKey: qk.changes(), queryFn: getChanges });

export const useEquipment = (refetchOnMount?: "always") => useQuery({ queryKey: qk.equipment(), queryFn: getEquipment, refetchOnMount });

export const useBench = (extractor: BenchExtractor) =>
  useQuery({ queryKey: ["bench", extractor] as const, queryFn: () => getBench(extractor) });

export const useStudy = () => useQuery({ queryKey: ["estudio"] as const, queryFn: getStudy });

/** URL del IFC de la revisión A o B del equipo activo (la demo sin API). */
export function useIfcUrl(rev: RevisionId): string | null {
  const revision = useRevision(rev);
  if (!apiEnabled) return DEMO.revisions[rev].ifc;
  return revision.data ? revisionResource(rev, "ifc") : null;
}

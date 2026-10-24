// Data for the Brain screen, a note's page and a sheet's page. The older hooks in
// ../../api/hooks.ts already cover most reads (catalog, inventory, entry, history, versions,
// use, files, gaps, preview, live sheets), so they are reused as they are; what they do not
// cover lives here, built like ../api.ts.

import { useMutation, useQuery } from "@tanstack/react-query";

import { api, get, post, query } from "../../api/client";
import type {
  BrainDecision,
  BrainFiled,
  BrainGap,
  BrainPreview,
  DecisionOutcome,
  EntryVersion,
  SheetView,
  StateEvent,
} from "../../api/types";
import { useRefresh } from "../api";

export {
  useBrainCatalog,
  useBrainEntry,
  useBrainFiles,
  useBrainHistory,
  useBrainInventory,
  useBrainProjects,
  useEntryDetails,
  useEntryUse,
  useEntryVersions,
  useGoals,
  useLive,
  useSheet,
} from "../../api/hooks";

/** A gap as the server sends it now: `flagged` is an AI saying the Brain did not hold it. */
export type Gap = Omit<BrainGap, "kind"> & { kind: BrainGap["kind"] | "flagged" };

export const useGaps = (days = 30) =>
  useQuery({ queryKey: ["brain", "gaps", days], queryFn: () => get<Gap[]>(`/api/brain/gaps${query({ days })}`) });

export function useDismissGap() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (key: string) => post<null>("/api/brain/gaps/dismiss", { key }),
    onSuccess: () => refresh("brain"),
  });
}

/** The preview the server sends: the packet text plus how it was put together. */
export type Preview = BrainPreview & {
  skill_included?: string | null;
  must_holds?: { id: string; title: string; line: string; triggers: string[]; why: string }[];
  log?: string[];
  reason?: string;
  budget?: number | null;
};

/** What an AI would be handed for a request. Nothing is recorded or sent. */
export const usePreview = (request: string) =>
  useQuery({
    queryKey: ["brain", "preview", request],
    queryFn: () => get<Preview>(`/api/brain/preview${query({ request })}`),
    enabled: request.trim().length > 0,
    staleTime: 30_000,
  });

/** One version of an entry, exactly as it was (its body and details). */
export const useEntryVersion = (id: string, ref: string | null) =>
  useQuery({
    queryKey: ["brain", "entry", id, "version", ref],
    queryFn: () =>
      get<EntryVersion & { meta?: Record<string, unknown> }>(
        `/api/brain/entries/${encodeURIComponent(id)}/versions/${encodeURIComponent(ref ?? "")}`,
      ),
    enabled: Boolean(id && ref),
  });

/** Change an entry itself (edit, archive, restore, update its details): one undo point. */
export function useEntryDecide() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (decisions: BrainDecision[]) => post<DecisionOutcome>("/api/brain/decisions", { decisions }),
    onSuccess: () => refresh("brain", "home"),
  });
}

/** Teach the Brain something in your own words: it waits in Catch up like every proposal. */
export function useTeach() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { title: string; statement: string; kind?: string }) =>
      post<{ status: string; message: string; proposal_id: string | null }>("/api/brain/proposals", body),
    onSuccess: () => refresh("brain", "home"),
  });
}

export function useAddFile() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.set("file", file);
      return api<BrainFiled>("/api/brain/files", { method: "POST", form });
    },
    onSuccess: () => refresh("brain", "home"),
  });
}

export const fileUrl = (path: string) => `/api/brain/files/content${query({ path })}`;

/** The sheets the Brain keeps by itself. Your AIs read them through the Brain. */
export const DERIVED: Record<string, string> = { "project-status": "Project status", "open-loops": "Open loops this week" };

/** A derived sheet, when the app can show it (it may only be reachable through the Brain). */
export const useDerivedSheet = (id: string, enabled = true) =>
  useQuery({
    queryKey: ["live", "derived", id],
    queryFn: () => get<SheetView>(`/api/work/live/${encodeURIComponent(id)}`),
    enabled: enabled && Boolean(id),
    retry: false,
  });

/** One cell's history (one row's, without a column), newest first. */
export const useCellHistory = (sheet: string, row: string | null, column: string | null) =>
  useQuery({
    queryKey: ["live", "history", sheet, row, column],
    queryFn: () =>
      get<StateEvent[]>(`/api/work/live/${encodeURIComponent(sheet)}/history${query({ row: row ?? "", column: column ?? undefined })}`),
    enabled: Boolean(sheet && row),
  });

/** One State action (write, add_row, decide, create_sheet): the sheet comes back as it is now. */
export function useSheetAct() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { action: string; fields: Record<string, unknown> }) =>
      post<SheetView & { sheet: { id: string } }>("/api/work/live/act", body),
    onSuccess: () => refresh("live", "brain"),
  });
}

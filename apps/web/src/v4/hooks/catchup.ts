// Data for Catch up and card mode: the catch-up plan (GET /api/brain/catch-up: the recap,
// "Still true?" rechecks and decide-once offers), its seen, snooze and dismiss routes, and the
// wider decisions a clash needs (replace, keep both, mark disputed) or a recheck needs (verify,
// retire), each batch saved as one undo point by POST /api/brain/decisions.

import { useMutation, useQuery } from "@tanstack/react-query";

import { get, post } from "../../api/client";
import type { CatchUpPlan, Offer, Recap, UpkeepCard, WentIn } from "../../api/types";
import { useRefresh } from "../api";

export type { CatchUpPlan, Offer, Recap, UpkeepCard, WentIn };
export type Recheck = Extract<UpkeepCard, { type: "recheck" }>;

export const useCatchUpPlan = () => useQuery({ queryKey: ["brain", "catch-up"], queryFn: () => get<CatchUpPlan>("/api/brain/catch-up") });

/** The person caught up: the next recap starts from now. */
export function useCatchUpSeen() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: () => post<Record<string, unknown>>("/api/brain/catch-up/seen"), onSuccess: () => refresh("brain") });
}

/** Later (a few days), or set aside (for good, or for `days`). */
export function useSetAside() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ key, later, days }: { key: string; later?: boolean; days?: number }) =>
      post<Record<string, unknown>>(`/api/brain/catch-up/${later ? "snooze" : "dismiss"}`, days ? { key, days } : { key }),
    onSuccess: () => refresh("brain"),
  });
}

/** One decision of the wider kind: a proposal (approve, reject) or an entry (verify, archive, mark). */
export interface GovernDecision {
  action: "approve" | "reject" | "verify" | "archive" | "mark";
  proposal_id?: string;
  entry_id?: string;
  reason?: string;
  replaces?: string[];
  state?: "stale" | "disputed";
  body?: string;
  destination?: Record<string, string>;
}

export interface GovernResult {
  results: { id: string; ok: boolean; message: string }[];
  checkpoint?: { id: string };
}

/** Several decisions at once, saved as one undo point, with what the page showed (`source`). */
export function useGovern() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ decisions, label, source }: { decisions: GovernDecision[]; label?: string; source?: Record<string, string | number> }) =>
      post<GovernResult>("/api/brain/decisions", { decisions, ...(label ? { label } : {}), ...(source ? { source } : {}) }),
    onSuccess: () => refresh("brain", "captures", "home"),
  });
}

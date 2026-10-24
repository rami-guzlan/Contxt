// Data for Ask and Activity that the shared hooks do not cover: undoing an undo point together
// with the later ones that depend on it (M07), and the requests of the last days for the
// report. Everything else comes from ../api.ts and ../../api/hooks.ts.

import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError, get, post, query } from "../../api/client";
import type { AiRequests, BrainCheckpoint } from "../../api/types";
import { useRefresh } from "../api";

/** A later undo point that changed the same entries, as the server names it. */
export interface Dependent {
  id: string;
  label: string;
  at?: string;
}

/** What a refused undo said: its message, the later points it would also undo (when undoing
 * them together is possible) and what changed since (when it is not). */
export interface UndoRefusal {
  message: string;
  dependents: Dependent[];
  blocked: { path: string; what: string }[];
}

export function undoRefusal(error: unknown): UndoRefusal | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const d = error.details as { dependents?: unknown; blocked?: unknown };
  return {
    message: error.message,
    dependents: Array.isArray(d.dependents) ? (d.dependents as Dependent[]) : [],
    blocked: Array.isArray(d.blocked) ? (d.blocked as { path: string; what: string }[]) : [],
  };
}

/** Undo one point; `together` also undoes the later points that depend on it, newest first. */
export function useUndoPoint() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, together = false }: { id: string; together?: boolean }) =>
      post<{ undone: string; checkpoint: BrainCheckpoint | null }>(
        `/api/brain/checkpoints/${encodeURIComponent(id)}/undo${query({ together: together ? "true" : undefined })}`,
      ),
    onSuccess: () => refresh("brain", "captures", "home"),
  });
}

/** The latest requests from every app, for the report's per-app split. */
export const useRecentRequests = (limit = 200) =>
  useQuery({
    queryKey: ["brain", "requests", "recent", limit],
    queryFn: () => get<AiRequests>(`/api/brain/requests${query({ limit })}`),
  });

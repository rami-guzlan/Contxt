// Capture's data: the sources (notes and captures), where each one stands, bringing things in
// (text, a file, a recorded meeting) and starting a distill request for one source. Built like
// ../api.ts; the older hooks in ../../api/hooks.ts cover the list, one capture and its
// distill requests, so those are reused as they are.

import { useMutation, useQuery } from "@tanstack/react-query";

import { api, get, post, query } from "../../api/client";
import type { Note, Task } from "../../api/types";
import { type Proposal, type SourceStatus, useRefresh } from "../api";

export { useDistillRequests, useNote, useNotes, captureOriginalUrl } from "../../api/hooks";

const MOVING = ["analysis_pending", "retrying", "indexing", "partial"];

/** Where each source stands, looked at again while one of them is still moving. */
export const useStatuses = (ids: string[]) =>
  useQuery({
    queryKey: ["captures", "status", ids.join(",")],
    queryFn: () => get<Record<string, SourceStatus>>(`/api/captures/status${query({ ids: ids.join(",") })}`),
    enabled: ids.length > 0,
    refetchInterval: (q) => (Object.values(q.state.data ?? {}).some((s) => MOVING.includes(s.status)) ? 5000 : false),
  });

/** Write or paste: saved to Capture as a note, private until something is kept. */
export function useSaveText() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { title?: string; body: string }) => post<Note>("/api/notes", body),
    onSuccess: () => refresh("notes", "captures", "home"),
  });
}

/** Bring in a file (a document, a transcript or audio), or a recorded meeting. */
export function useUpload() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ file, title }: { file: File | Blob; title?: string }) => {
      const form = new FormData();
      if (file instanceof File) form.set("file", file);
      else form.set("file", file, file.type.includes("mp4") ? "meeting.m4a" : "meeting.webm");
      if (title) form.set("title", title);
      return api<Note>("/api/captures", { method: "POST", form });
    },
    onSuccess: () => refresh("notes", "captures", "home"),
  });
}

/** Ask the AI to read one source for what should last: a distill request. */
export function useDistill() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (itemId: string) => post<Task>("/api/brain/distill/requests", { item_ids: [itemId] }),
    onSuccess: () => refresh("brain", "captures", "notes", "tasks"),
  });
}

/** Turn a capture into text again after its transcription failed (not a model run). */
export function useRetryReading() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => post<Note>(`/api/captures/${encodeURIComponent(id)}/retry`),
    onSuccess: () => refresh("notes", "captures"),
  });
}

/** The waiting proposals that came from this source: by its reference, the ids its status
 * names, or the distill requests that read it. */
export function proposalsFrom(all: Proposal[] | undefined, id: string, status?: SourceStatus, taskIds: string[] = []): Proposal[] {
  const ref = `context_item:${id}`;
  const named = new Set(status?.proposal_ids ?? []);
  const tasks = new Set(taskIds);
  return (all ?? []).filter(
    (p) =>
      p.source?.id === ref ||
      named.has(p.id) ||
      (p.sources ?? []).includes(ref) ||
      (p.task_id ? tasks.has(p.task_id) : false),
  );
}

/** What a capture is, in the design's words (the Sources filters). */
export type SourceKind = "Meeting" | "Upload" | "Voice" | "Note";

export function sourceKind(note: Pick<Note, "capture">): SourceKind {
  switch (note.capture) {
    case "recording":
    case "transcript":
      return "Meeting";
    case "document":
      return "Upload";
    case "talk":
      return "Voice";
    default:
      return "Note";
  }
}

export const KIND_LABEL: Record<SourceKind, string> = { Meeting: "Meeting", Upload: "Upload", Voice: "Voice note", Note: "Note" };

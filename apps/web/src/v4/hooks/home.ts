// Data for Home: saving what the person tells it as a capture, the quick start's own per-viewer
// memory (dismissed, steps marked by hand, a receipt opened), and the auto-applied changes read
// from the undo points. Everything else Home shows comes from hooks that already exist.

import { useMutation } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import { post } from "../../api/client";
import type { BrainCheckpoint, Note } from "../../api/types";
import { useRefresh } from "../api";

// ------------------------------------------------------------------ Tell: a capture

/** A short title from what was said: its first line, cut at a word. */
export function titleFrom(text: string): string {
  const line = text.trim().split(/\r?\n/)[0]?.trim() ?? "";
  if (line.length <= 60) return line;
  const cut = line.slice(0, 60);
  const space = cut.lastIndexOf(" ");
  return `${space > 30 ? cut.slice(0, space) : cut}…`;
}

/** Save text as a capture (POST /api/notes): private until part of it is kept. */
export function useTell() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (text: string) => post<Note>("/api/notes", { title: titleFrom(text), body: text.trim() }),
    onSuccess: () => refresh("notes", "captures", "home", "events"),
  });
}

// ------------------------------------------------------------------ quick start memory

/** The quick start's five steps, in order (Release 1). */
export const QS_IDS = ["app", "capture", "catchup", "ask", "evidence"] as const;
export type QsId = (typeof QS_IDS)[number];

const QS_KEY = "gn.quickstart";
/** Set (to an ISO time) when the person opens an evidence receipt; read by the quick start. */
export const RECEIPT_OPENED_KEY = "gn.receipt-opened";

interface QsMemory {
  dismissed: boolean;
  done: Partial<Record<QsId, boolean>>;
}

function read(): QsMemory {
  try {
    const raw = window.localStorage.getItem(QS_KEY);
    const data = raw ? (JSON.parse(raw) as Partial<QsMemory>) : {};
    return { dismissed: Boolean(data.dismissed), done: data.done && typeof data.done === "object" ? data.done : {} };
  } catch {
    return { dismissed: false, done: {} };
  }
}

function write(memory: QsMemory) {
  try {
    window.localStorage.setItem(QS_KEY, JSON.stringify(memory));
  } catch {
    // Private windows and blocked storage: the quick start still works for this visit.
  }
}

/** Has this viewer opened an evidence receipt on this computer? */
export function receiptOpened(): boolean {
  try {
    return Boolean(window.localStorage.getItem(RECEIPT_OPENED_KEY));
  } catch {
    return false;
  }
}

/** Dismissed or not, and the steps marked done by hand: this viewer's, on this computer. */
export function useQuickStartMemory() {
  const [memory, setMemory] = useState<QsMemory>(read);
  const update = useCallback((change: (m: QsMemory) => QsMemory) => {
    setMemory((current) => {
      const next = change(current);
      write(next);
      return next;
    });
  }, []);
  const actions = useMemo(
    () => ({
      dismiss: () => update((m) => ({ ...m, dismissed: true })),
      reopen: () => update((m) => (m.dismissed ? { ...m, dismissed: false } : m)),
      mark: (id: QsId) => update((m) => ({ ...m, done: { ...m.done, [id]: true } })),
    }),
    [update],
  );
  return { dismissed: memory.dismissed, marked: memory.done, ...actions };
}

// ------------------------------------------------------------------ auto-applied changes

/** The label the Brain gives an undo point it made when a change went in on its own. */
export const AUTO_LABEL = "Went in on its own";

/** Undo points made by changes that went in on their own, newest first. */
export function autoApplied(points: BrainCheckpoint[]): BrainCheckpoint[] {
  return points.filter((p) => p.kind === "decisions" && p.label.startsWith(AUTO_LABEL));
}

/** In words, what one change did: Added, Updated, Retired or Changed. */
export function changeVerb(point: BrainCheckpoint): string {
  const kind = point.decisions.find((d) => d.kind)?.kind ?? "";
  if (kind === "note.create") return "Added";
  if (kind === "note.update") return "Updated";
  if (kind === "note.archive") return "Retired";
  return "Changed";
}

/** What it changed: the decision's title, else the label after its prefix. */
export function changeTitle(point: BrainCheckpoint): string {
  const titled = point.decisions.find((d) => d.title)?.title;
  if (titled) return titled;
  return point.label.startsWith(`${AUTO_LABEL}: `) ? point.label.slice(AUTO_LABEL.length + 2) : point.label;
}

/** Within the last 24 hours? */
export function lastDay(iso: string, now = Date.now()): boolean {
  const at = new Date(iso).getTime();
  return !Number.isNaN(at) && now - at <= 24 * 60 * 60 * 1000;
}

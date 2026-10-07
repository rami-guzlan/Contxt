// Pieces the Brain's pages share: how an entry is labelled, dates, and file helpers.

import { query } from "../../api/client";
import type { BrainEntrySummary, EntryOrigin, TaskStatus } from "../../api/types";
import { label } from "../../lib/format";

/** Distillation requests a model has yet to finish, a draft waiting for a model included. */
export const OPEN_STATUSES: TaskStatus[] = ["draft", "ready", "claimed", "in_progress", "review", "blocked"];

export function needsAttention(entry: BrainEntrySummary): boolean {
  return !!entry.stale_reason || entry.confidence === "disputed";
}

export function EntryChips({ entry }: { entry: BrainEntrySummary }) {
  return (
    <span className="chips">
      <span className={`chip chip-kind chip-${entry.kind}`}>{label(entry.kind)}</span>
      {entry.standing ? (
        <span className="chip chip-standing" title="Delivered with every task, not only when relevant">
          In every task
        </span>
      ) : null}
      {entry.partition ? (
        <span className="chip" title="Sealed: only work for this client or campaign sees it">
          {entry.partition}
        </span>
      ) : null}
      {entry.stale_reason ? (
        <span className="chip chip-stale" title={entry.stale_reason}>
          Stale
        </span>
      ) : null}
      {entry.confidence === "disputed" ? <span className="chip chip-stale">Disputed</span> : null}
      {entry.file ? (
        <span className="chip" title={entry.file}>
          File
        </span>
      ) : null}
    </span>
  );
}

/** A calendar date as people write it, without a time zone shifting the day. */
export function day(value: string | null | undefined): string {
  if (!value) return "";
  const [year, month, date] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !date) return value;
  return new Date(year, month - 1, date).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function TypeBadge({ name, text }: { name?: string; text?: string }) {
  const ext = text ?? (name?.includes(".") ? (name.split(".").pop() ?? "") : "").toUpperCase().slice(0, 4);
  return (
    <span className="type-badge" aria-hidden="true">
      {ext || "FILE"}
    </span>
  );
}

export const isImage = (mime: string) => mime.startsWith("image/");

export const isText = (path: string) => /\.(md|markdown|txt|csv|json|ya?ml|html?|py|js|mjs|ts|css|sh|ps1|toml|xml)$/i.test(path);

export function filesTab(path: string): "references" | "assets" | "skills" {
  if (path.startsWith("assets/")) return "assets";
  if (path.startsWith("skills/")) return "skills";
  return "references";
}

export const fileViewUrl = (path: string) => `/brain/files/view${query({ path })}`;

export const entryUrl = (id: string) => `/brain/entries/${encodeURIComponent(id)}`;

const ORIGINS: Record<EntryOrigin["kind"], string> = {
  conversation: "An AI conversation",
  workspace: "The workspace",
  work: "AI work",
  file: "A file",
  meeting: "A meeting",
  output: "An output",
  doc: "A doc",
  you: "You",
  import: "Imported",
  unknown: "Not recorded",
};

/** Whether a summary only repeats the title: older Brains title a note by its first line, so
 * the two can be the same text, or one a shortened copy of the other. */
export function repeats(title: string, summary: string): boolean {
  const t = title.trim().toLowerCase();
  const s = summary.trim().toLowerCase();
  const cut = (text: string) => text.replace(/(\.\.\.|…)$/, "").trim();
  if (!s || cut(t) === cut(s)) return true;
  if (cut(t) !== t && s.startsWith(cut(t))) return true;
  return cut(s) !== s && t.startsWith(cut(s));
}

/** "unused for 60 days", or, while use has been recorded for less, "unused since <day>". */
export function unusedLabel(since: string | undefined): string {
  const cutoff = new Date(Date.now() - 59 * 86_400_000).toISOString().slice(0, 10);
  return since && since > cutoff ? `unused since ${day(since)}` : "unused for 60 days";
}

/** Where an entry came from, as people say it. */
export function originText(origin: EntryOrigin): string {
  return ORIGINS[origin.kind] ?? label(origin.kind);
}

/** Who answers for an entry: "You" for the Brain's owner, else the scope's name. */
export function ownerName(scope: string, approver?: string): string {
  if (!scope) return "";
  if (approver && scope === approver) return "You";
  const name = scope.includes(":") ? scope.slice(scope.indexOf(":") + 1) : scope;
  return name
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

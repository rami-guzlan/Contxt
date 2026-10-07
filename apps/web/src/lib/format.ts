import type { Actor, WorkspaceEvent } from "../api/types";

export function when(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const moment = new Date(iso);
  const seconds = Math.round((now.getTime() - moment.getTime()) / 1000);
  const future = seconds < 0;
  const abs = Math.abs(seconds);
  const phrase =
    abs < 60
      ? "moments"
      : abs < 3600
        ? `${Math.round(abs / 60)} min`
        : abs < 86400
          ? `${Math.round(abs / 3600)} h`
          : abs < 86400 * 14
            ? `${Math.round(abs / 86400)} d`
            : "";
  if (!phrase) return moment.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  if (phrase === "moments") return future ? "in a moment" : "just now";
  return future ? `in ${phrase}` : `${phrase} ago`;
}

/** "1 to-do", "3 to-dos": a count with its noun, never "to-do(s)". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function label(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function bytes(size: number | null | undefined): string {
  if (!size) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

const VERBS: Record<string, string> = {
  "workspace.created": "created the workspace",
  "workspace.legacy_moved": "brought the earlier workspace into the Brain",
  "note.created": "started a note",
  "note.edited": "saved a new version of a note",
  "note.named": "named a version of a note",
  "note.archived": "set a note aside",
  "note.restored": "brought a note back",
  "note.filed": "added a note to the Brain",
  "task.created": "set up AI work",
  "task.ready": "started AI work",
  "task.claimed": "picked up AI work",
  "task.blocked": "is stuck on AI work",
  "task.review": "finished AI work; it waits for your review",
  "task.done": "finished AI work",
  "task.failed": "marked AI work failed",
  "task.cancelled": "cancelled AI work",
  "run.progress": "reported progress",
  "run.completed": "closed a run",
  "run.failed": "reported a failed run",
  "run.lease_expired": "released an expired claim",
  "brain.proposed": "suggested something for the Brain",
  "brain.approved": "added to the Brain",
  "brain.rejected": "rejected a Brain proposal",
  "brain.archived": "removed an entry from the Brain",
  "brain.edited": "edited a Brain entry",
  "brain.restored": "put back an earlier version of an entry",
  "brain.unarchived": "brought an entry back",
  "brain.updated": "changed an entry's details",
  "brain.verified": "confirmed an entry is still true",
  "brain.marked": "marked an entry as needing a look",
  "brain.undone": "took back a batch of decisions",
  "brain.filed": "filed a document in the Brain",
  "brain.project_started": "started a project",
  "brain.project_updated": "recorded progress on a project",
  "brain.policy_changed": "changed how the Brain is governed",
  "actor.connected": "connected a model",
  "actor.disabled": "disconnected a model",
  "credential.issued": "issued a token",
  "credential.revoked": "revoked a token",
};

/** "You approved an output: Launch post", "Claude Code finished AI work: Weekly posts". */
export function describeEvent(event: WorkspaceEvent, actors: Map<string, Actor>, meId?: string): string {
  const actor = actors.get(event.actor_id);
  const who =
    meId && event.actor_id === meId
      ? "You"
      : actor?.kind === "system"
        ? "The workspace"
        : (actor?.name ?? "Someone");
  const verb = VERBS[event.type] ?? event.type.replace(/[._]/g, " ");
  const title = typeof event.data.title === "string" ? `: ${event.data.title}` : "";
  const reason = event.reason ? ` (${event.reason})` : "";
  return `${who} ${verb}${title}${reason}`;
}

export function subjectLink(event: WorkspaceEvent): string | null {
  switch (event.subject_type) {
    case "context_item":
      return event.type.startsWith("note.") ? `/capture/${event.subject_id}` : null;
    case "brain_project":
      return `/projects/${encodeURIComponent(event.subject_id)}`;
    case "brain_entry":
      return `/brain/entries/${encodeURIComponent(event.subject_id)}`;
    case "brain_proposal":
      return "/review";
    default:
      return null;
  }
}

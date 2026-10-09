// Where things live in the app, so a move changes one line instead of every link.

export const WORK = "/work";
export const SKILLS = "/work/skills";
export const OUTPUTS = "/work/outputs";
export const AGENTS = "/work/agents";
export const WORKSPACE = "/work/workspace";

/** A skill's page in Work, on one of its tabs when given. */
export function skillUrl(name: string, tab?: string): string {
  return `${SKILLS}/${encodeURIComponent(name)}${tab ? `?tab=${tab}` : ""}`;
}

/** An agent's page in Work, on one of its tabs when given. */
export function agentUrl(name: string, tab?: string): string {
  return `${AGENTS}/${encodeURIComponent(name)}${tab ? `?tab=${tab}` : ""}`;
}

/** A doc (or link) in Work, Workspace. */
export function docUrl(id: string): string {
  return `${WORKSPACE}/${encodeURIComponent(id)}`;
}

/** Work, Workspace, showing what is linked to one project. */
export function workspaceFor(project: string): string {
  return `${WORKSPACE}?project=${encodeURIComponent(project)}`;
}

/** Where a note opens: what you wrote (docs and links) in Work, Workspace; what came in, in Capture. */
export function noteUrl(note: { id: string; capture?: string | null }): string {
  const kind = note.capture ?? "note";
  return kind === "note" || kind === "link" ? docUrl(note.id) : `/capture/${encodeURIComponent(note.id)}`;
}

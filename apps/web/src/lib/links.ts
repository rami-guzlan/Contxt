// Where things live in the app, so a move changes one line instead of every link.

export const WORK = "/work";
export const SKILLS = "/work/skills";
export const OUTPUTS = "/work/outputs";

/** A skill's page in Work, on one of its tabs when given. */
export function skillUrl(name: string, tab?: string): string {
  return `${SKILLS}/${encodeURIComponent(name)}${tab ? `?tab=${tab}` : ""}`;
}

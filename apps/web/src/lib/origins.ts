// Where a filed item came from, in the person's words: the groups Brain > Files shows, and the
// line an item's page says. An origin is `<kind>` or `<kind>:<which one>`, as its card keeps it.

export const ORIGIN_GROUPS = [
  { id: "capture", label: "Capture", what: "Recordings, transcripts, uploads and exports that came in through Capture" },
  { id: "project", label: "Projects", what: "Files filed for a project" },
  { id: "library", label: "Library", what: "Fetched from a page or a repository, or added to the Library" },
  { id: "run", label: "Made by runs", what: "What a skill, an agent or a workflow made" },
  { id: "movein", label: "Moved in", what: "Brought over from another workspace or AI" },
  { id: "upload", label: "Your uploads", what: "Filed by you in the app" },
  { id: "chat", label: "From your AIs", what: "Kept by an AI in a conversation" },
  { id: "folder", label: "Swept folders", what: "Found in a folder the Brain sweeps" },
  { id: "unknown", label: "Origin unknown", what: "Filed before the Brain kept where files came from: set it on the item's page" },
] as const;

export type OriginGroup = (typeof ORIGIN_GROUPS)[number]["id"];

const CAPTURE_WORDS: Record<string, string> = {
  recording: "a recording",
  transcript: "a transcript",
  document: "an uploaded document",
  talk: "something you said",
  export: "an export",
};

/** The group an origin falls in. */
export function originGroup(origin: string | null | undefined): OriginGroup {
  const kind = String(origin ?? "").split(":", 1)[0];
  return (ORIGIN_GROUPS.find((g) => g.id === kind)?.id ?? "unknown") as OriginGroup;
}

/** Where it came from, in a few words: "Capture: a recording", "Made by run run_123". */
export function originLine(origin: string | null | undefined): string {
  if (!origin) return "Not known";
  const [kind, ...rest] = origin.split(":");
  const which = rest.join(":");
  const group = ORIGIN_GROUPS.find((g) => g.id === kind);
  if (kind === "capture") return `Capture: ${CAPTURE_WORDS[which] ?? which ?? "something brought in"}`;
  if (!group) return origin;
  return which ? `${group.label}: ${which}` : group.label;
}

/** The origins the owner can set by hand on an item filed before origins were kept. */
export const SETTABLE_ORIGINS: { value: string; label: string }[] = [
  { value: "capture:recording", label: "Capture: a recording" },
  { value: "capture:transcript", label: "Capture: a transcript" },
  { value: "capture:document", label: "Capture: an uploaded document" },
  { value: "capture:export", label: "Capture: an export" },
  { value: "library", label: "Library" },
  { value: "project", label: "A project" },
  { value: "movein", label: "Moved in" },
  { value: "upload", label: "Your upload" },
  { value: "chat", label: "An AI in a conversation" },
  { value: "folder", label: "A swept folder" },
];

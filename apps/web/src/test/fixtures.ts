// Shared test data for the calm-governance pages: a catch-up plan, goals, AI apps and requests,
// in the shapes the server sends (see the server's own tests for where each comes from).

import type { AiApp, AiRequest, CatchUpPlan, Goals, JudgmentCard, QuickGroup } from "../api/types";

export const stamp = "2026-10-05T13:00:00.000000Z";

export const health = {
  score: 82,
  label: "good" as const,
  factors: [
    { key: "fresh" as const, label: "Fresh", score: 1, detail: "every note within its check", fix: null },
    { key: "tidy" as const, label: "Tidy", score: 0.8, detail: "1 to tidy", fix: { label: "Tidy up", to: "/review" } },
    { key: "used" as const, label: "Used", score: 0.6, detail: "60% reached an AI this month", fix: null },
  ],
  unsaved: [] as string[],
};

export const judgment: JudgmentCard = {
  key: "proposal:p1",
  proposal_id: "p1",
  goal: "what your Brain is for",
  project: { id: "q4-webinars", title: "Q4 webinars" },
  type: "conflict",
  kind: "fact",
  tag: "Might disagree with your note",
  shapes: false,
  title: "Webinars run 45 minutes",
  summary: "Each webinar runs 45 minutes.",
  body: "Each webinar runs 45 minutes.",
  source: "A chat",
  at: stamp,
  topic: "projects/q4-webinars",
  with: { id: "webinar-length", title: "Webinar length", body: "Each webinar runs 60 minutes.", score: 0.8 },
  duplicates: [],
  why: "Disagrees with your note “Webinar length”.",
  recommend: { action: "keep_mine", reason: "You confirmed your note on 2026-09-30." },
  actions: ["keep_mine", "use_this", "keep_both", "edit", "later"],
};

export const quick: QuickGroup = {
  key: "group:rule:brand",
  kind: "rule",
  area: "brand",
  title: "2 rules for Brand",
  detail: "nothing they disagree with",
  count: 2,
  proposal_ids: ["p2", "p3"],
  shapes: true,
  items: [
    { id: "p2", title: "No exclamation marks", summary: "", source: "Moved in", goal: null, project: null },
    { id: "p3", title: "Numerals for numbers", summary: "", source: "Moved in", goal: null, project: null },
  ],
  sources: ["Moved in"],
};

export function plan(overrides: Partial<CatchUpPlan> = {}): CatchUpPlan {
  return {
    seen_at: "2026-10-01T10:00:00Z",
    since: "2026-10-01T10:00:00Z",
    away_days: 4,
    recap_first: false,
    seconds: 150,
    minutes: 3,
    caught_up: false,
    counts: { judgment: 1, quick: 1, quick_items: 2, upkeep: 1, offers: 0, legacy: 0, handled: 1, snoozed: 0 },
    health,
    recap: {
      since: "2026-10-01T10:00:00Z",
      went_in: [],
      went_in_total: 1,
      decided: {},
      came_in: { total: 5, by_source: { chat: 3, files: 2, you: 0, ai_work: 0, moved_in: 0, other: 0 }, waiting: 3 },
      projects: [{ id: "q4-webinars", title: "Q4 webinars", updates: 2, last: { at: stamp, summary: "Registrations open" } }],
      gaps: 2,
    },
    handled: [
      {
        at: stamp,
        kind: "note.create",
        id: "decision-video",
        title: "Video stays",
        source: "your AI's chat",
        capture: "decision:chat",
        path: null,
        live: true,
        checkpoint: "cp-handled",
      },
    ],
    judgment: [judgment],
    quick: [quick],
    upkeep: [
      {
        key: "recheck:pricing",
        type: "recheck",
        id: "pricing",
        title: "Pricing",
        summary: "Courses cost 400 dollars a seat.",
        why: "past its 90-day check",
        uses: 4,
        last_used: stamp,
      },
    ],
    offers: [],
    legacy: null,
    nudges: [],
    preset: "careful",
    ...overrides,
  };
}

export const goals: Goals = {
  questions: [
    { id: "purpose", question: "What do you want this Brain to help you do?", why: "Everything you bring in is sifted against this.", required: true, example: "Keep our marketing on message." },
    { id: "work", question: "What do you work on, and for whom?", why: "So it can tell your work from everything else.", required: false, example: "Marketing for a training company." },
    { id: "in_motion", question: "What is in motion right now?", why: "One per line: each can start a project.", required: false, example: "Q4 webinars\nWebsite refresh" },
  ],
  answers: { purpose: "Run marketing without dropping follow-ups." },
  exists: true,
  id: "you-goals",
  starter: "empty",
  updated: "2026-10-01",
  purpose: "Run marketing without dropping follow-ups.",
  projects: [],
  text: "# What this Brain is for\n\nRun marketing without dropping follow-ups.",
};

export const apps: AiApp[] = [
  {
    client: "claude-code",
    label: "Claude Code",
    found: true,
    connected: true,
    last_request: { at: stamp, request: "Write a post" },
    setup: { client: "claude-code", label: "Claude Code", server: "contxt", command: "claude mcp add contxt -- python -m brainkit mcp", note: "Run once." },
  },
  {
    client: "cursor",
    label: "Cursor",
    found: true,
    connected: false,
    last_request: null,
    setup: { client: "cursor", label: "Cursor", server: "contxt", file: "~/.cursor/mcp.json", config: "{}", note: "Then reload Cursor." },
  },
];

export const request: AiRequest = {
  id: "pkt-1",
  session_id: "sess-1",
  at: stamp,
  request: "Write a LinkedIn post announcing the Q4 webinars",
  mode: "standard",
  app: "Claude Code",
  client: "claude-code 2.1",
  tokens: 640,
  share: 0.1,
  project: { id: "q4-webinars", title: "Q4 webinars" },
  skill: null,
  got: [
    { kind: "note", id: "linkedin-rules", tokens: 55, why: "score 0.61", title: "LinkedIn posting rules", note_kind: "rule", topic: "marketing/linkedin", live: true },
    { kind: "note", id: "audience", tokens: 80, why: "score 0.52", title: "Who we write for", note_kind: "fact", topic: "customers/who", live: true },
  ],
  kernel: true,
  opened: [],
  nothing: false,
  saved: [],
  engine: "abc123def456",
  old_engine: false,
};

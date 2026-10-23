import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type Call, mockApi, renderAt } from "../../test/render";
import type { Proposal } from "../api";
import { CardsPage, CatchUpPage } from "./CatchUp";

afterEach(() => vi.restoreAllMocks());

const prop = (over: Partial<Proposal>): Proposal => ({
  id: "prp_1",
  kind: "note.create",
  scope: "owner",
  route_key: "work/marketing",
  title: "",
  note_summary: "",
  summary: "",
  body: "Reminder emails go out two days before",
  current_body: null,
  created: "2026-10-20T10:00:00Z",
  proposer: "Claude Code",
  reason: "",
  similar: "",
  conflicts: "",
  source: { id: "cap_7", version: "v2", locator: "04:10", speaker: "unknown", excerpt: "two days before each session" },
  operation: "new note",
  statement_status: "stated",
  effective: "",
  destination: "Long-term memory › work",
  op_id: "",
  target: { area: "work", kind: "fact" },
  ...over,
});

const clash = prop({
  id: "prp_clash",
  kind: "note.update",
  body: "Always CC the reviewer on landing pages",
  current_body: "The reviewer approves customer-facing work and is not CC'd",
  conflicts: "rules-review",
  operation: "update",
});
const safeA = prop({ id: "prp_a", body: "Sessions run 45 minutes" });
const safeB = prop({ id: "prp_b", body: "Recordings go up the next day", proposer: "Cursor" });
const rule = prop({ id: "prp_rule", body: "No exclamation marks", target: { area: "rules", kind: "rule" } });
const task = prop({ id: "prp_task", kind: "task.create", body: "Send the run of show", destination: "To-do in a project", target: { project: "proj_q4" } });

const recap = { since: "2026-10-20T00:00:00Z", went_in: [], went_in_total: 0, decided: { approved: 4, rejected: 1 }, came_in: { total: 0, by_source: {}, waiting: 0 }, projects: [], gaps: 0 };
const plan = (over: Record<string, unknown> = {}) => ({
  seen_at: null,
  since: "2026-10-20T00:00:00Z",
  away_days: null,
  recap_first: false,
  seconds: 90,
  minutes: 2,
  caught_up: false,
  counts: { judgment: 0, quick: 0, quick_items: 0, upkeep: 0, offers: 0, legacy: 0, handled: 0, snoozed: 0 },
  health: { score: null, label: "new", factors: [] },
  recap,
  handled: [],
  judgment: [],
  quick: [],
  upkeep: [],
  offers: [],
  legacy: null,
  nudges: [],
  preset: "careful",
  ...over,
});
const recheck = { key: "recheck:note-pricing", type: "recheck", id: "note-pricing", title: "Pricing is per seat", summary: "Per seat, billed yearly", why: "Last checked 90 days ago", uses: 3, last_used: null };
const policy = (over: Record<string, unknown> = {}) => ({
  preset: "careful",
  presets: ["personal", "careful", "regulated"],
  auto_daily_cap: 50,
  auto_applied_today: 3,
  standing: [],
  retrieval_policy: "standard",
  retrieval_policies: ["relaxed", "standard", "careful"],
  learned: [],
  areas: ["work", "rules"],
  capture_types: ["fact", "decision", "rule"],
  capture_origins: ["chat", "folder", "app"],
  ...over,
});
const decided = (ids: string[]) => ({ results: ids.map((id) => ({ id, ok: true, message: "ok" })), checkpoint: { id: "cp_1" } });

function api(over: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/brain/proposals": [clash, safeA, safeB, rule, task],
    "GET /api/brain/catch-up": plan({ upkeep: [recheck] }),
    "GET /api/brain/policies": policy(),
    "POST /api/brain/decisions": (call: Call) => decided(((call.body as { decisions: { proposal_id?: string; entry_id?: string }[] }).decisions ?? []).map((d) => d.proposal_id ?? d.entry_id ?? "")),
    "POST /api/brain/checkpoints/cp_1/undo": { ok: true },
    "PUT /api/brain/policies": { policy: policy() },
    ...over,
  });
}

const bodyOf = (calls: ReturnType<typeof mockApi>, path: string) => calls.filter((c) => c.method !== "GET" && c.path.startsWith(path)).map((c) => c.body);

describe("Catch up", () => {
  it("shows what waits from the API: the clash first, then safe ones, changes in place and rule changes", async () => {
    api();
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    expect((await screen.findAllByText("Always CC the reviewer on landing pages")).length).toBeGreaterThan(0);
    expect(screen.getByText("Clashes with your Brain")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 today")).toBeInTheDocument();
    expect(screen.getByText("CURRENT · APPROVED")).toBeInTheDocument();
    expect(screen.getByText("The reviewer approves customer-facing work and is not CC'd")).toBeInTheDocument();
    expect(screen.getByText("prp_clash · ASSISTANT SUGGESTION · NOT APPROVED YET")).toBeInTheDocument();
    expect(screen.getByText("Safe to keep · 2")).toBeInTheDocument();
    expect(screen.getByText("1 from Claude Code")).toBeInTheDocument();
    expect(screen.getByText("Where they'd land · 1")).toBeInTheDocument();
    expect(screen.getByText("Rule changes · 1")).toBeInTheDocument();
    expect(screen.getByText(/2 need you · 2 safe to keep · 1 where they'd land · 1 saved for Sunday · about 2 minutes/)).toBeInTheDocument();
  });

  it("keeps all safe ones in one call, one decision each, then undoes them with one undo point", async () => {
    const calls = api();
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    fireEvent.click(await screen.findByRole("button", { name: "Keep all" }));
    await screen.findByText(/Kept 2 · indexing, not searchable yet/);
    expect(bodyOf(calls, "/api/brain/decisions")).toEqual([
      {
        decisions: [
          { action: "approve", proposal_id: "prp_a" },
          { action: "approve", proposal_id: "prp_b" },
        ],
      },
    ]);
    fireEvent.click(within(screen.getByRole("status")).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/checkpoints/cp_1/undo")).toBe(true));
  });

  it("asks about a clash: Keep current rejects it, and nothing newer wins on its own", async () => {
    const calls = api();
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    fireEvent.click(await screen.findByRole("button", { name: "Keep current" }));
    await screen.findByText(/Kept the current record/);
    expect(bodyOf(calls, "/api/brain/decisions")[0]).toEqual({
      decisions: [{ action: "reject", proposal_id: "prp_clash", reason: "Kept the current record" }],
      label: "Kept current over prp_clash",
      source: { catch_up: "proposal:prp_clash" },
    });
  });

  it("marks a clash disputed only with a reason, keeping the new one and marking the current one in one call", async () => {
    const calls = api();
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    const mark = await screen.findByRole("button", { name: /^Mark disputed/ });
    expect(mark).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText("A few words on why"), "Both were said");
    fireEvent.click(screen.getByRole("button", { name: /^Mark disputed/ }));
    await waitFor(() => expect(bodyOf(calls, "/api/brain/decisions")).toHaveLength(1));
    expect(bodyOf(calls, "/api/brain/decisions")[0]).toMatchObject({
      decisions: [
        { action: "approve", proposal_id: "prp_clash", reason: "Both were said" },
        { action: "mark", entry_id: "rules-review", state: "disputed", reason: "Both were said" },
      ],
    });
  });

  it("checks a note with Still true", async () => {
    const calls = api({ "GET /api/brain/proposals": [] });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    expect(await screen.findByText("Pricing is per seat")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Still true" }));
    await screen.findByText(/It stops being stale/);
    expect(bodyOf(calls, "/api/brain/decisions")[0]).toEqual({
      decisions: [{ action: "verify", entry_id: "note-pricing" }],
      label: "Still true: Pricing is per seat",
      source: { catch_up: "recheck:note-pricing" },
    });
  });

  it("snoozes a check with Later", async () => {
    const calls = api({ "GET /api/brain/proposals": [], "POST /api/brain/catch-up/snooze": {} });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    fireEvent.click(await screen.findByRole("button", { name: "Later" }));
    await waitFor(() => expect(bodyOf(calls, "/api/brain/catch-up/snooze")).toEqual([{ key: "recheck:note-pricing" }]));
  });

  it("says when nothing waits", async () => {
    api({ "GET /api/brain/proposals": [], "GET /api/brain/catch-up": plan() });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    expect(await screen.findByText("Your Brain is up to date.")).toBeInTheDocument();
    expect(screen.getByText("All caught up")).toBeInTheDocument();
    expect(screen.getByText("kept since you last looked").previousSibling).toHaveTextContent("4");
  });

  it("says what went wrong when the proposals can't load, with Try again", async () => {
    api({ "GET /api/brain/proposals": { status: 500, body: { error: { code: "error", message: "The Brain could not be read." } } } });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    expect(await screen.findByText("The Brain could not be read.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("adds a standing permission scoped to one kind, one origin and one area, and pauses one", async () => {
    const calls = api({ "GET /api/brain/policies": policy({ standing: [{ type: "decision", origin: "folder", area: "work", paused: false }] }) });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    await screen.findByText("Standing permissions · 1");
    const kind = screen.getByLabelText("Kind");
    expect(within(kind).queryByRole("option", { name: "rules" })).toBeNull();
    const add = screen.getByRole("button", { name: "Add" });
    fireEvent.change(kind, { target: { value: "fact" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "chat" } });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Area"), { target: { value: "work" } });
    fireEvent.click(add);
    await waitFor(() => expect(bodyOf(calls, "/api/brain/policies")).toHaveLength(1));
    expect(bodyOf(calls, "/api/brain/policies")[0]).toEqual({
      standing: [
        { type: "decision", origin: "folder", area: "work", paused: false },
        { type: "fact", origin: "chat", area: "work", paused: false },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(bodyOf(calls, "/api/brain/policies")).toHaveLength(2));
    expect(bodyOf(calls, "/api/brain/policies")[1]).toEqual({ standing: [{ type: "decision", origin: "folder", area: "work", paused: true }] });
  });

  it("filters everything in one list to the conflicts", async () => {
    api({ "GET /api/scout": { folders: [], formats: {}, last_inspection: null, last_error: null, files_seen: 0, differences: [], later: [] } });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    fireEvent.click(await screen.findByRole("button", { name: "Everything, in one list" }));
    const list = await screen.findByRole("region", { name: "Everything waiting" });
    expect(within(list).getAllByRole("article")).toHaveLength(5);
    fireEvent.click(within(list).getByRole("button", { name: "Conflicts · 1" }));
    expect(within(list).getAllByRole("article")).toHaveLength(1);
    expect(within(list).getByRole("article", { name: "Proposal prp_clash" })).toBeInTheDocument();
    expect(await within(list).findByRole("button", { name: "From Scout · 0" })).toBeInTheDocument();
  });

  it("lists what went in on its own, with undo", async () => {
    const at = new Date().toISOString();
    const calls = mockApi({
      "GET /api/brain/proposals": [],
      "GET /api/brain/catch-up": plan({
        handled: [{ at, kind: "fact", id: "n1", title: "The guest confirmed for Nov 12", source: "Claude Code", capture: "fact:chat", path: null, live: true, checkpoint: "cp_9" }],
        recap: { ...recap, went_in_total: 1 },
      }),
      "GET /api/brain/policies": policy(),
      "GET /api/brain/learned": [{ id: "l1", type: "fact", origin: "chat", area: "work", says: "Asks before adding facts about pricing", at }],
      "POST /api/brain/checkpoints/cp_9/undo": { ok: true },
    });
    renderAt(<CatchUpPage />, { path: "/brain/catch-up", route: "/brain/catch-up" });
    fireEvent.click(await screen.findByRole("tab", { name: "What changed" }));
    expect(await screen.findByText("The guest confirmed for Nov 12")).toBeInTheDocument();
    expect(screen.getByText(/1 change went in on its own/)).toBeInTheDocument();
    expect(await screen.findByText("Asks before adding facts about pricing")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await screen.findByRole("button", { name: "Undone" });
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/checkpoints/cp_9/undo")).toBe(true);
  });
});

describe("Card mode", () => {
  it("shows one card at a time: right arrow keeps, left arrow skips, then the done state", async () => {
    const calls = api({ "GET /api/brain/proposals": [safeA, safeB] });
    renderAt(<CardsPage />, { path: "/brain/cards", route: "/brain/cards" });
    expect(await screen.findByText("0 of 2 today")).toBeInTheDocument();
    expect(screen.getByText("“Sessions run 45 minutes”")).toBeInTheDocument();
    expect(screen.getByText("← skip · → keep · E edit")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    await screen.findByText("1 of 2 today");
    expect(screen.getByText("“Recordings go up the next day”")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    await screen.findByText("That's 2 for today.");
    expect(bodyOf(calls, "/api/brain/decisions")).toEqual([
      { decisions: [{ action: "approve", proposal_id: "prp_a" }] },
      { decisions: [{ action: "reject", proposal_id: "prp_b" }] },
    ]);
  });

  it("undoes the last card, bringing it back", async () => {
    const calls = api({ "GET /api/brain/proposals": [safeA] });
    renderAt(<CardsPage />, { path: "/brain/cards", route: "/brain/cards" });
    fireEvent.click(await screen.findByRole("button", { name: "Keep (right arrow)" }));
    await screen.findByText("That's 1 for today.");
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText("“Sessions run 45 minutes”")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/brain/checkpoints/cp_1/undo")).toBe(true);
  });

  it("says all caught up when nothing waits", async () => {
    api({ "GET /api/brain/proposals": [] });
    renderAt(<CardsPage />, { path: "/brain/cards", route: "/brain/cards" });
    expect(await screen.findByText("All caught up.")).toBeInTheDocument();
  });
});

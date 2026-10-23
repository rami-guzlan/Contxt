// Home: the quick start from real state (and put away, and opened again from Help), the day's
// Home from real counts, Tell saving a capture and Ask going to Ask, and the auto-governed Home
// with its change log, Undo and the cap's pause.

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { HomePage } from "./Home";

const now = new Date().toISOString();

const policy = (over: Record<string, unknown> = {}) => ({
  mode: "governed",
  auto_paused: false,
  preset: "careful",
  presets: ["personal", "careful", "regulated"],
  auto_daily_cap: 50,
  auto_applied_today: 0,
  standing: [],
  retrieval_policy: "standard",
  retrieval_policies: [],
  learned: [],
  areas: [],
  capture_types: [],
  capture_origins: [],
  ...over,
});

const note = (id: string, title: string) => ({
  id,
  title,
  body: null,
  revision: 1,
  version: 1,
  created_by: "act_owner",
  created_at: now,
  updated_at: now,
  edited_by: null,
  archived_at: null,
});

const proposal = (id: string, title: string) => ({ id, title, summary: "", reason: "From the weekly sync", note_summary: "", kind: "note.create" });

const request = { id: "pk_1", session_id: "s", at: now, request: "draft the note", app: "Cursor", got: [], opened: [], saved: [] };

const project = { id: "pj_1", title: "Harbor launch", summary: "", status: "active", active: true, current: "Waiting on the venue", next: "", blockers: "", updated: now, aliases: [], files: 0, updates: 0, topic: "" };

const catalog = {
  areas: [
    { key: "work", label: "Work", description: "", topics: [] },
    { key: "people", label: "People", description: "", topics: [] },
  ],
  entries: [
    { id: "e1", title: "a", area: "work", stale_reason: null },
    { id: "e2", title: "b", area: "people", stale_reason: "old" },
  ],
};

const checkpoint = (over: Record<string, unknown>) => ({
  id: "cp_1",
  at: now,
  by: "Claude Code",
  kind: "decisions",
  label: "Went in on its own: Venue holds 80 people",
  source: {},
  decisions: [{ action: "approved", kind: "note.create", title: "Venue holds 80 people" }],
  files: [],
  undoes: null,
  undone_by: null,
  undone_at: null,
  undoable: true,
  ...over,
});

function api(over: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/brain/policies": policy(),
    "GET /api/brain/apps": [{ client: "claude-code", label: "Claude Code", found: true, connected: true, last_request: null, setup: null }],
    "GET /api/notes": [],
    "GET /api/brain/checkpoints": [],
    "GET /api/brain/proposals": [],
    "GET /api/brain/requests": { requests: [], brain_tokens: 0, apps: [], engine: "" },
    "GET /api/brain/projects": [],
    "GET /api/brain/catalog": { areas: [], entries: [] },
    ...over,
  });
}

const dismissed = () => window.localStorage.setItem("gn.quickstart", JSON.stringify({ dismissed: true, done: {} }));

beforeEach(() => window.localStorage.clear());

describe("Quick start", () => {
  it("counts what is really done and opens the first step that is not", async () => {
    api();
    renderAt(<HomePage />);
    expect(await screen.findByText("1 of 5 done")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Capture one source/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Nothing captured yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Connect your AI/ }));
    expect(screen.getByText("Connected now: Claude Code.")).toBeInTheDocument();
  });

  it("marks a step done by hand, and finishes with the end card", async () => {
    api({
      "GET /api/notes": [note("ctx_1", "Kickoff")],
      "GET /api/brain/checkpoints": [checkpoint({ label: "Approved 1", decisions: [{ action: "approved" }] })],
      "GET /api/brain/requests": { requests: [request], brain_tokens: 0, apps: [], engine: "" },
    });
    window.localStorage.setItem("gn.receipt-opened", now);
    renderAt(<HomePage />);
    expect(await screen.findByText("ALL FIVE DONE")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Go to my Home" }));
    expect(await screen.findByRole("heading", { name: "Today" })).toBeInTheDocument();
  });

  it("says when it cannot check, with Try again", async () => {
    api({ "GET /api/brain/apps": { status: 500, body: { error: { code: "error", message: "The Brain is not reachable." } } } });
    renderAt(<HomePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The Brain is not reachable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("opens again from Help after it was put away", async () => {
    api();
    dismissed();
    renderAt(<HomePage />, { route: "/?quickstart=1" });
    expect(await screen.findByRole("region", { name: "Quick start" })).toBeInTheDocument();
  });
});

describe("The day's Home", () => {
  it("shows real counts, captures to distill and active projects", async () => {
    dismissed();
    api({
      "GET /api/brain/proposals": [proposal("p1", "One"), proposal("p2", "Two")],
      "GET /api/notes": [note("ctx_1", "Kickoff")],
      "GET /api/captures/status": { ctx_1: { item_id: "ctx_1", status: "awaiting_review", label: "Awaiting review" } },
      "GET /api/brain/requests": { requests: [request], brain_tokens: 0, apps: [], engine: "" },
      "GET /api/brain/projects": [project],
      "GET /api/brain/catalog": catalog,
    });
    renderAt(<HomePage />);
    expect(await screen.findByText(/2 things your AIs learned are waiting for you/)).toBeInTheDocument();
    expect(await screen.findByText("1 awaiting review")).toBeInTheDocument();
    expect(await screen.findByText("Harbor launch")).toBeInTheDocument();
    expect(screen.getByText(/Latest from Cursor/)).toBeInTheDocument();
    expect(await screen.findByText(/2 notes in 2 areas · 1 need a look/)).toBeInTheDocument();
  });

  it("is honest when nothing is there yet", async () => {
    dismissed();
    api();
    renderAt(<HomePage />);
    expect(await screen.findByText("You’re all caught up. Your Brain is in order.")).toBeInTheDocument();
    expect(await screen.findByText("No active projects yet")).toBeInTheDocument();
    expect(screen.getByText("Nothing captured yet")).toBeInTheDocument();
  });

  it("Tell saves the words as a capture and says where they went", async () => {
    dismissed();
    const calls = api({ "POST /api/notes": { status: 201, body: note("ctx_9", "Venue holds 80 people") } });
    renderAt(<HomePage />);
    await userEvent.type(await screen.findByRole("textbox", { name: "Tell your Brain" }), "Venue holds 80 people");
    await userEvent.click(screen.getByRole("button", { name: "Save to Capture" }));
    expect(await screen.findByText(/Saved to Capture as “Venue holds 80 people”/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/notes");
    expect(post?.body).toEqual({ title: "Venue holds 80 people", body: "Venue holds 80 people" });
  });

  it("Ask goes to Ask with the question", async () => {
    dismissed();
    api();
    renderAt(<HomePage />);
    await userEvent.click(await screen.findByRole("button", { name: "Ask it" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Ask your Brain" }), "Where is the venue?{Enter}");
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });
});

describe("The auto-governed Home", () => {
  it("lists what went in on its own and undoes one", async () => {
    dismissed();
    const calls = api({
      "GET /api/brain/policies": policy({ mode: "auto", auto_applied_today: 3 }),
      "GET /api/brain/checkpoints": [checkpoint({}), checkpoint({ id: "cp_0", label: "Approved 1", decisions: [{ action: "approved", title: "By hand" }] })],
      "POST /api/brain/checkpoints/cp_1/undo": { ok: true },
    });
    renderAt(<HomePage />);
    expect(await screen.findByText("Your Brain is keeping itself.")).toBeInTheDocument();
    expect(screen.getByText(/3 of 50 today/)).toBeInTheDocument();
    expect(await screen.findByText("Venue holds 80 people")).toBeInTheDocument();
    expect(screen.queryByText("By hand")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo: Venue holds 80 people" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/checkpoints/cp_1/undo")).toBe(true);
  });

  it("shows the pause when the daily cap is reached", async () => {
    dismissed();
    api({
      "GET /api/brain/policies": policy({ mode: "auto", auto_applied_today: 50 }),
      "GET /api/brain/proposals": [proposal("p1", "Always copy the venue on invites")],
    });
    renderAt(<HomePage />);
    expect(await screen.findByText("Auto-governance is paused.")).toBeInTheDocument();
    expect(screen.getByText(/Paused: 50 changes went in on their own today, the cap is 50/)).toBeInTheDocument();
    expect(await screen.findByText("“Always copy the venue on invites”")).toBeInTheDocument();
    expect(screen.getByText("Nothing has gone in on its own yet.")).toBeInTheDocument();
  });
});

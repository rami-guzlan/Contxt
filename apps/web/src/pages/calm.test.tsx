// The calm-governance pages: Catch up (a plan, one card at a time, keys and the finish), Moving
// in (read, sift, choose), the first run end to end, Activity, Outputs, See the difference and
// Settings.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SeeTheDifference } from "../components/Difference";
import { apps, goals, judgment, plan, quick, request, stamp } from "../test/fixtures";
import type { JudgmentCard } from "../api/types";
import { mockApi, renderAt, workspace } from "../test/render";
import { AiActivityPage } from "./Activity";
import { CatchUpPage } from "./CatchUp";
import { FirstRunPage } from "./FirstRun";
import { MoveInPage } from "./MoveIn";
import { OutputsPage } from "./Outputs";
import { SettingsPage } from "./Settings";

const decided = { results: [{ id: "p1", action: "reject", ok: true, message: "", data: {} }], checkpoint: { id: "cp-1", label: "Kept my note" } };
const claude = {
  id: "claude",
  label: "Claude Code",
  provider: "claude-code",
  one_click: true,
  installed: true,
  version: "2",
  signed_in: true,
  install: "",
  sign_in: "",
  actor_id: "act_claude",
  detail: "",
};

describe("catch up", () => {
  it("is a plan with a time, then one card at a time with a recommendation, then a finish", async () => {
    const calls = mockApi({
      "GET /api/brain/catch-up": plan(),
      "POST /api/brain/decisions": decided,
      "POST /api/brain/catch-up/snooze": {},
      "POST /api/brain/catch-up/seen": {},
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    expect(await screen.findByRole("heading", { level: 1, name: "About 3 minutes" })).toBeInTheDocument();
    expect(screen.getByText("decision")).toBeInTheDocument();
    expect(screen.getByText(/Handled for you: 1 thing went in on its own/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start" }));

    // a decision: what it is, what it is for, the two side by side, and what I recommend
    expect(await screen.findByText("Might disagree with your note")).toBeInTheDocument();
    expect(screen.getByText("For Q4 webinars")).toBeInTheDocument();
    expect(screen.getByText("Serves: what your Brain is for")).toBeInTheDocument();
    expect(screen.getByText(/I recommend: keep my note\./)).toBeInTheDocument();
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    await user.keyboard("{Enter}"); // the recommendation
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/brain/decisions")).toHaveLength(1));
    expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
      decisions: [{ action: "reject", proposal_id: "p1" }],
      source: { catch_up: judgment.key },
    });

    // a quick group: keep all, or untick one
    expect(await screen.findByText(`${quick.title}: ${quick.detail}`)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Numerals for numbers/ }));
    await user.click(screen.getByRole("button", { name: "Keep 1, not 1" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/brain/decisions")).toHaveLength(2));
    expect(calls.filter((c) => c.path === "/api/brain/decisions")[1]?.body).toMatchObject({
      decisions: [
        { action: "approve", proposal_id: "p2" },
        { action: "reject", proposal_id: "p3" },
      ],
    });

    // upkeep: later is a key away
    expect(await screen.findByText("Still true?")).toBeInTheDocument();
    await user.keyboard("l");
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/catch-up/snooze")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/catch-up/snooze")?.body).toEqual({ key: "recheck:pricing" });

    expect(await screen.findByRole("heading", { level: 1, name: /All caught up/ })).toBeInTheDocument();
    expect(screen.getByText(/Kept your note over/)).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/catch-up/seen")).toBe(true));
  });

  it("offers a safety rule as a must-hold for its area, set as one decision", async () => {
    const card = {
      key: "musthold:nut-rule",
      type: "musthold" as const,
      id: "nut-rule",
      title: "No peanuts at school",
      summary: "Ollie is allergic to peanuts.",
      area: "family",
      area_label: "Family",
      triggers: ["peanuts", "school"],
      recommend: { action: "make_must_hold", reason: "It reads like a rule that should never be missed." },
    };
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({ judgment: [], quick: [], upkeep: [card] }),
      "POST /api/brain/decisions": decided,
      "POST /api/brain/catch-up/seen": {},
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText("Must hold?")).toBeInTheDocument();
    expect(screen.getByText(/It would come in when a request mentions: peanuts, school/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Make it a must-hold" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/decisions")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
      decisions: [{ action: "update", entry_id: "nut-rule", fields: { load: "domain", applies_to: "family", triggers: "peanuts, school" } }],
      source: { catch_up: "musthold:nut-rule" },
    });
  });

  it("opens a baseline's choices only after the two are compared, and revising it takes a reason", async () => {
    const card: JudgmentCard = {
      ...judgment,
      key: "proposal:p9",
      proposal_id: "p9",
      type: "baseline",
      tag: "Changes a baseline",
      title: "Webinars run 45 minutes",
      body: "Webinars run 45 minutes, questions included.",
      why: "May disagree with “Webinar length”, a baseline: it is a rule.",
      recommend: { action: "keep_mine", reason: "AIs used your note in 12 chats this month, and nothing says it changed." },
      actions: ["revise", "keep_mine", "both_hold", "later"],
      baseline: {
        id: "webinar-length",
        title: "Webinar length",
        body: "Webinars run 30 minutes.",
        kind: "rule",
        load: "on-demand",
        why: "it is a rule",
        change: "disagree",
        tension: "",
        approved_by: "person:owner",
        approved_at: "2026-09-01",
        added: "2026-08-01",
        revised: "",
        verified: "2026-09-01",
        uses: 12,
        weighty: true,
        impact: { conversations: 12, recent: [{ request: "Draft the webinar invite", at: "2026-10-01T10:00:00Z", client: "Claude Code" }], domains: [] },
        previous_reason: "",
        min_words: 4,
      },
      check: { model: "done", verdict: { relation: "contradicts", proposed: "", existing: "", settle: "Say which length is current.", at: null } },
      held: null,
    };
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({ judgment: [card], quick: [], upkeep: [] }),
      "POST /api/brain/decisions": decided,
      "POST /api/brain/catch-up/seen": {},
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText("Changes a baseline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep the baseline" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Revise the baseline" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Compare the two" }));
    expect(screen.getByText(/It went into 12 conversations in the last 30 days/)).toBeInTheDocument();
    expect(screen.getByText(/Draft the webinar invite/)).toBeInTheDocument();
    expect(screen.getByText("Your AI read both: they disagree. Say which length is current.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revise the baseline" }));
    const why = screen.getByRole("textbox", { name: /Why does it change\?/ });
    await user.type(why, "Shorter");
    const submit = screen.getByRole("button", { name: "Revise it, with this reason" });
    expect(submit).toBeDisabled();
    await user.type(why, " webinars convert better");
    await user.click(submit);
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/decisions")).toBe(true));
    const body = calls.find((c) => c.path === "/api/brain/decisions")?.body as { source: Record<string, unknown> };
    expect(body).toMatchObject({
      decisions: [{ action: "approve", proposal_id: "p9", reason: "Shorter webinars convert better", replaces: ["webinar-length"] }],
      source: { catch_up: "proposal:p9" },
    });
    expect(typeof body.source.seconds).toBe("number");
  });

  it("asks once more about what went in on its own", async () => {
    const card = {
      key: "spot:n1",
      type: "spot" as const,
      id: "n1",
      title: "Webinar day",
      summary: "Webinars are on Tuesdays.",
      why: "It went in on its own on 2026-10-01.",
      uses: 3,
      last_used: null,
    };
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({ judgment: [], quick: [], upkeep: [card] }),
      "POST /api/brain/decisions": decided,
      "POST /api/brain/catch-up/seen": {},
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText("Still right?")).toBeInTheDocument();
    expect(screen.getByText(/It went in on its own on 2026-10-01\./)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Still right" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/decisions")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
      decisions: [{ action: "verify", entry_id: "n1" }],
      source: { catch_up: "spot:n1" },
    });
  });

  it("offers to retire a value a newer one replaced", async () => {
    const side = (id: string, title: string) => ({ id, title, summary: `${title}.`, uses: 0, added: null });
    const card = {
      key: "older:mrr-august|mrr-september",
      type: "older" as const,
      older: side("mrr-august", "MRR, August"),
      newer: side("mrr-september", "MRR, September"),
      older_as_of: "2026-08-31",
      newer_as_of: "2026-09-30",
    };
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({ judgment: [], quick: [], upkeep: [card] }),
      "POST /api/brain/decisions": decided,
      "POST /api/brain/catch-up/seen": {},
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText("A newer value")).toBeInTheDocument();
    expect(screen.getByText(/Older, as of/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retire the older one" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/decisions")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
      decisions: [{ action: "archive", entry_id: "mrr-august" }],
      source: { catch_up: "older:mrr-august|mrr-september" },
    });
  });

  it("lists a scheduled revision with a way to cancel it", async () => {
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({
        scheduled: [{ proposal_id: "p7", title: "Headlines", at: "2099-10-09T15:00:00Z", reason: "Twelve words fit the new layouts", baseline: "Headlines" }],
      }),
      "POST /api/brain/decisions": decided,
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    expect(await screen.findByText(/“Headlines” goes in/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel it" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/decisions")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
      decisions: [{ action: "unschedule", proposal_id: "p7" }],
    });
  });

  it("starts with what happened after time away", async () => {
    mockApi({ "GET /api/brain/catch-up": plan({ recap_first: true }) });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    expect(await screen.findByText("While you were away: 4 days")).toBeInTheDocument();
    expect(screen.getByText("Registrations open", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Teach it the answers" })).toHaveAttribute("href", "/brain/questions");
    await user.click(screen.getByRole("button", { name: "Catch up, about 3 minutes" }));
    expect(await screen.findByRole("button", { name: "Start" })).toBeInTheDocument();
  });

  it("offers the earlier workspace once", async () => {
    const legacy = {
      key: "legacy:workspace",
      title: "18 notes from your earlier workspace are not in your Brain yet",
      detail: "Notes come in as suggestions you keep or not.",
      counts: {} as never,
      seconds: 200,
      minutes: 4,
    };
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({ legacy, judgment: [], quick: [], upkeep: [] }),
      "POST /api/legacy/bring-into-brain": {
        projects_started: [],
        projects_matched: 2,
        projects_left: [],
        notes_proposed: 18,
        files_filed: 0,
        files_waiting: 3,
        waiting_files: ["deck.pdf"],
        next_steps: 2,
        todos_noted: 0,
        todo_note: null,
        refused: [],
        skipped: 0,
      },
      "POST /api/brain/catch-up/seen": {},
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText(legacy.title)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bring it in" }));
    expect(await screen.findByText(/18 suggestions to review, 3 files waiting/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/legacy/bring-into-brain")).toBe(true);
  });
});

const preview = {
  sources: [{ id: "s1", kind: "chatgpt", label: "ChatGPT memory", chars: 120, ideas: 3 }],
  ideas: [
    {
      id: "i1",
      source: "s1",
      source_kind: "chatgpt",
      text: "Planning the Q4 webinars for supervisors.",
      original: "Planning the Q4 webinars for supervisors.",
      group: "",
      kind: "fact",
      personal: false,
      topic: "projects/q4",
      topic_label: "Q4 webinars",
      match: null,
      why: "",
      status: "new",
      fits: true,
      serves: { goal: null, project: { id: "q4-webinars", title: "Q4 webinars" }, about_you: false },
    },
    {
      id: "i2",
      source: "s1",
      source_kind: "chatgpt",
      text: "Sam has a dog named Pepper.",
      original: "Has a dog named Pepper.",
      group: "",
      kind: "fact",
      personal: false,
      topic: "people/sam",
      topic_label: "Sam",
      match: null,
      why: "",
      status: "new",
      fits: false,
      serves: { goal: null, project: null, about_you: false },
      left_out: "none of your goals or projects covers it",
    },
    {
      id: "i3",
      source: "s1",
      source_kind: "chatgpt",
      text: "Never use exclamation marks.",
      original: "Never use exclamation marks.",
      group: "",
      kind: "rule",
      personal: true,
      topic: "brand/voice",
      topic_label: "Voice",
      match: { id: "voice", title: "Voice", score: 0.95 },
      why: "the Brain says much the same",
      status: "known",
      fits: true,
      serves: { goal: null, project: null, about_you: true },
    },
  ],
  stages: {
    sources: 1,
    chars: 120,
    ideas: 3,
    kinds: { identity: 0, rule: 0, state: 0, fact: 2 },
    new: 2,
    known: 1,
    waiting: 0,
    disagree: 0,
    private: 0,
    sifted: true,
    fits: 1,
    for_goals: 0,
    for_projects: { "Q4 webinars": 1 },
    about_you: 0,
    left_out: 1,
    to_keep: 1,
  },
  examples: { split: "i2", known: "i3", new: "i1", fits: "i1", left_out: "i2" },
};

describe("moving in", () => {
  it("reads what an AI knew, sifts it against the goals and projects, and keeps what you choose", async () => {
    const calls = mockApi({
      "POST /api/brain/move-in/preview": preview,
      "POST /api/brain/move-in": { stages: preview.stages, proposed: [{ idea: "i1", proposal_id: "p9", status: "pending" }], already: [], refused: [], secrets_left_out: 0 },
    });
    const user = userEvent.setup();
    renderAt(<MoveInPage />);
    expect(screen.getByText(/List everything you remember about me/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Paste it here"), "- Planning the Q4 webinars for supervisors.");
    await user.click(screen.getByRole("button", { name: "Read it" }));
    const pipeline = await screen.findByRole("list", { name: "How the Brain read it" });
    expect(within(pipeline).getByText("Fits your goals and projects")).toBeInTheDocument();
    expect(within(pipeline).getByText(/1 idea, 1 for Q4 webinars\. Left out 1: see why below/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Planning the Q4 webinars/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /dog named Pepper/ })).not.toBeChecked(); // left out, one tap away
    expect(screen.getByRole("checkbox", { name: /Never use exclamation marks/ })).toBeDisabled(); // already known
    await user.click(screen.getByRole("button", { name: "Keep 1 idea" }));
    expect(await screen.findByRole("heading", { name: /1 suggestion wait in Catch up/ })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/move-in")?.body).toMatchObject({ ids: ["i1"] });
  });
});

describe("the first run", () => {
  it("goes from the welcome to goals, connecting, and a rhythm", async () => {
    const soon = new Date(Date.now() + 60_000).toISOString();
    let arrived = false;
    const calls = mockApi({
      "GET /api/me": { actor_id: "act_owner", kind: "human", name: "Owner", actions: [], projects: null, workspace },
      "GET /api/onboarding": {
        steps: [],
        done: 0,
        total: 6,
        owner_name: "Owner",
        brain: { available: true, own_entries: 0, waiting: 0, projects: 0, files: 0, goals: false },
        local_model: true,
        completed_at: null,
        dismissed_at: null,
        tour_seen_at: null,
      },
      "GET /api/brain/goals": { ...goals, exists: false, answers: {}, purpose: "" },
      "PUT /api/actors/act_owner": { id: "act_owner", name: "Sam" },
      "GET /api/runners": [],
      "GET /api/speech": { installed: true, model: "small.en", present: true, ready: true, downloading: false, about_mb: 480, error: null },
      "GET /api/brain/projects": [],
      "PUT /api/brain/goals": { ...goals, status: "saved" },
      "POST /api/brain/projects": { id: "q4-webinars", title: "Q4 webinars" },
      "GET /api/brain/apps": apps,
      "POST /api/brain/apps/cursor/connect": { client: "cursor", connected: true, changed: true, backup: "mcp.json.bak" },
      "GET /api/brain/requests": () => ({
        requests: arrived ? [{ ...request, at: soon, request: "What do you know about me?" }] : [],
        brain_tokens: 6000,
        apps: ["Claude Code"],
        engine: "abc",
      }),
      "GET /api/brain/examples": [],
      "GET /api/brain/policies": { preset: "careful" },
      "PUT /api/brain/policies": { status: "updated", policy: {}, checkpoint: null },
      "POST /api/onboarding": {},
    });
    const user = userEvent.setup();
    renderAt(<FirstRunPage />, { path: "/welcome", route: "/welcome" });
    expect(screen.getByRole("heading", { name: "Tell it once. Every AI you use knows." })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    expect(screen.getByRole("list", { name: "The loop" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    expect(screen.getByText(/See what each AI got\./)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start my Brain" }));

    // goals: a name first, then one question at a time, then the playback
    expect(await screen.findByText(/sifted against what you say here/, { selector: ".lede" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("First, what should your AIs call you?"), "Sam");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.type(await screen.findByLabelText("What do you want this Brain to help you do?"), "Run marketing without dropping follow-ups.");
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await user.click(await screen.findByRole("button", { name: "Skip" }));
    await user.type(await screen.findByLabelText("What is in motion right now?"), "Q4 webinars");
    await user.click(screen.getByRole("button", { name: /See what I heard/ }));
    expect(await screen.findByRole("heading", { name: "Here is what I heard" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Q4 webinars" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Keep my goals" }));
    expect(await screen.findByText(/everything you bring in is sifted against this/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT" && c.path === "/api/brain/goals")?.body).toEqual({
      answers: { purpose: "Run marketing without dropping follow-ups.", in_motion: "Q4 webinars" },
    });
    expect(calls.find((c) => c.method === "POST" && c.path === "/api/brain/projects")?.body).toMatchObject({ name: "Q4 webinars" });
    await user.click(screen.getByRole("button", { name: "Continue" }));

    // move in can wait
    await user.click(await screen.findByRole("button", { name: "Skip this for now" }));

    // connect, with a yes before changing an app's settings, then the request arrives
    expect(await screen.findByRole("heading", { name: "Connect your AI, and prove it" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cursor" }));
    await user.click(screen.getByRole("button", { name: "Add it for me" }));
    await user.click(screen.getByRole("button", { name: "Yes, add it" }));
    expect(await screen.findByText(/Quit Cursor fully and open it again/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/apps/cursor/connect")?.body).toEqual({ confirm: true });
    arrived = true;
    expect(await screen.findByText(/Claude Code asked/, {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText("It got the startup context, 1 rule, 1 project and 1 note.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/ }));

    // see the difference, then a rhythm
    expect(await screen.findByRole("heading", { name: "See the difference" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await user.click(await screen.findByRole("radio", { name: /Personal/ }));
    await user.click(screen.getByRole("button", { name: "Done: open Home" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path === "/api/brain/policies")).toBe(true));
    expect(calls.find((c) => c.method === "PUT" && c.path === "/api/brain/policies")?.body).toEqual({ preset: "personal" });
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.path === "/api/onboarding")?.body).toEqual({ completed: true }));
  }, 20_000);
});

describe("activity", () => {
  it("shows what each AI asked, what it got and why, and lets you teach what was missing", async () => {
    const calls = mockApi({
      "GET /api/brain/weekly": [{ start: "2026-09-29", end: "2026-10-05", conversations: 4, packets: 9 }],
      "GET /api/brain/requests": { requests: [{ ...request, old_engine: true }], brain_tokens: 6400, apps: ["Claude Code", "Cursor"], engine: "new" },
      "POST /api/brain/proposals": { status: "pending", message: "", proposal_id: "p5" },
    });
    const user = userEvent.setup();
    renderAt(<AiActivityPage />, { path: "/activity", route: "/activity" });
    expect(await screen.findByText(/This week your AIs asked 9 times, in 4 chats/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "App" })).toBeInTheDocument();
    expect(screen.getByText(/runs an older version of the Brain's engine/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Write a LinkedIn post announcing the Q4 webinars/ }));
    expect(screen.getByRole("link", { name: "LinkedIn posting rules" })).toHaveAttribute("href", "/brain/entries/linkedin-rules");
    expect(screen.getByText("(score 0.61)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Something was missing/ }));
    await user.type(screen.getByLabelText("What should it have known?"), "The first webinar is October 22.");
    await user.click(screen.getByRole("button", { name: "Teach it" }));
    expect(await screen.findByText(/It waits in/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/proposals")?.body).toMatchObject({
      statement: "The first webinar is October 22.",
      evidence: "Missing when Claude Code was asked: “Write a LinkedIn post announcing the Q4 webinars”",
    });
  });
});

describe("outputs", () => {
  it("lists what your AI made, newest first, with downloads and what each was made from", async () => {
    mockApi({
      "GET /api/outputs": {
        root: "C:/home/outputs",
        folders: ["skill-runs", "skill-runs/2026-10-05-one-pager"],
        files: [
          { path: "skill-runs/2026-10-05-one-pager/one-pager.pdf", name: "one-pager.pdf", folder: "skill-runs/2026-10-05-one-pager", size: 20480, modified: stamp, kind: "pdf", from: "skill", working: false },
          { path: "notes.md", name: "notes.md", folder: "", size: 100, modified: "2026-10-01T10:00:00Z", kind: "document", from: null, working: false },
        ],
      },
      "GET /api/outputs/made-from": {
        path: "skill-runs/2026-10-05-one-pager/one-pager.pdf",
        how: "skill",
        skill_run: {
          task_id: "t1",
          skill: "one-pager",
          ask: "A one-pager for the webinar",
          project: null,
          attached: [],
          capture: null,
          status: "done",
          created_at: stamp,
          runs: [{ id: "run_1", at: stamp, status: "completed", by: "Claude Code" }],
        },
        given: [{ id: "run_1", pieces: [{ kind: "note", id: "voice", tokens: 40, why: "loaded by the skill", title: "Voice" }] }],
      },
    });
    const user = userEvent.setup();
    renderAt(<OutputsPage />);
    const pdf = await screen.findByRole("button", { name: "one-pager.pdf" });
    const row = pdf.closest("li") as HTMLElement;
    expect(within(row).getByText("From a skill run")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Download" })).toHaveAttribute(
      "href",
      "/api/outputs/file?path=skill-runs%2F2026-10-05-one-pager%2Fone-pager.pdf",
    );
    await user.click(pdf);
    expect(await within(row).findByRole("link", { name: "/one-pager" })).toHaveAttribute("href", "/skills/one-pager");
    expect(within(row).getByText(/A one-pager for the webinar/)).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Voice" })).toHaveAttribute("href", "/brain/entries/voice");
  });
});

describe("see the difference", () => {
  it("runs a request both ways on this computer and links each difference to the piece behind it", async () => {
    let polls = 0;
    const done = {
      id: "cmp_1",
      request: "Write a post",
      project: null,
      started_at: stamp,
      status: "done",
      step: "done",
      without: "Exciting news!",
      with_context: "57% of new supervisors got under 8 hours.",
      differences: [
        { what: "It opens with a sourced number", item: "linkedin-rules" },
        { what: "It ends with one question", item: "linkedin-post" },
      ],
      pieces: [
        { kind: "note", id: "linkedin-rules", title: "LinkedIn posting rules" },
        { kind: "skill", id: "linkedin-post", title: "/linkedin-post" },
      ],
      tokens: 640,
      kernel_tokens: 780,
      brain_tokens: 6200,
      share: 0.1,
      finished_at: stamp,
      error: null,
    };
    const calls = mockApi({
      "GET /api/runners": [claude],
      "GET /api/brain/examples": [],
      "GET /api/brain/projects": [],
      "POST /api/brain/difference": { ...done, status: "running", step: "without" },
      "GET /api/brain/difference/cmp_1": () => (++polls > 1 ? done : { ...done, status: "running", step: "with" }),
    });
    const user = userEvent.setup();
    renderAt(<SeeTheDifference suggestions={["Write a post"]} />);
    await user.click(await screen.findByRole("button", { name: "Write a post" }));
    await user.click(screen.getByRole("button", { name: "Run it both ways" }));
    expect(await screen.findByText("With your Brain", {}, { timeout: 6000 })).toBeInTheDocument();
    expect(screen.getByText("Exciting news!")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LinkedIn posting rules" })).toHaveAttribute("href", "/brain/entries/linkedin-rules");
    expect(screen.getByRole("link", { name: "/linkedin-post" })).toHaveAttribute("href", "/skills/linkedin-post");
    expect(screen.getByText(/It got 640 tokens, about a tenth of your Brain\./)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/difference")?.body).toEqual({ request: "Write a post" });
  }, 15_000);

  it("without Claude Code here, gives both prompts to paste", async () => {
    mockApi({
      "GET /api/runners": [],
      "GET /api/brain/examples": [],
      "GET /api/brain/projects": [],
      "GET /api/brain/preview": { request: "Write a post", text: "## Rules\n- Plain words", tokens: 300, project: null, procedure: null, notes: [], sections: [] },
    });
    const user = userEvent.setup();
    renderAt(<SeeTheDifference />);
    await user.type(await screen.findByLabelText("A request to try both ways"), "Write a post");
    await user.click(screen.getByRole("button", { name: "Show both prompts" }));
    expect(await screen.findByText("Without your Brain")).toBeInTheDocument();
    expect(screen.getByText("With your Brain (300 tokens of context)")).toBeInTheDocument();
  });
});

describe("settings", () => {
  it("sets the approval preset, and the table by kind and source behind Advanced", async () => {
    const policy = {
      review_days: {},
      default_owner: "person:sam",
      auto_apply_own_scope: true,
      auto_apply_scopes: [],
      max_proposals_per_session: 12,
      retention_days: 90,
      approver: "person:sam",
      areas: [],
      kinds: [],
      scopes: [],
      preset: "careful",
      presets: ["personal", "careful", "regulated"],
      capture: { file: { app: "apply", chat: "apply", folder: "apply" }, fact: { app: "apply", chat: "wait", folder: "wait" } },
      capture_types: ["file", "fact"],
      capture_origins: ["app", "chat", "folder"],
    };
    const calls = mockApi({
      "GET /api/brain/policies": policy,
      "PUT /api/brain/policies": { status: "updated", policy, checkpoint: { id: "cp" } },
      "GET /api/actors": [],
    });
    const user = userEvent.setup();
    renderAt(<SettingsPage />, { path: "/settings", route: "/settings?tab=approval" });
    await user.click(await screen.findByRole("radio", { name: /Regulated/ }));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ preset: "regulated" });
    await user.click(screen.getByRole("button", { name: /Advanced: by kind and source/ }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Facts from your ai's chats" }), "apply");
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "PUT")[1]?.body).toEqual({ capture: { fact: { chat: "apply" } } });
  });

  it("backs up now and downloads the matching model only when asked", async () => {
    const calls = mockApi({
      "GET /api/backups": [],
      "POST /api/backups": { name: "workspace-20261005T130000Z.zip", size: 2048, records: 120, files: 4, brain_files: 60, originals: 2 },
      "GET /api/legacy": { counts: {}, has_any: false },
    });
    const user = userEvent.setup();
    renderAt(<SettingsPage />, { path: "/settings", route: "/settings?tab=backups" });
    await user.click(await screen.findByRole("button", { name: "Back up now" }));
    expect(await screen.findByRole("link", { name: "Download it" })).toHaveAttribute("href", "/api/backups/workspace-20261005T130000Z.zip");
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/backups")).toBe(true);
  });

  it("downloads the model that matches by meaning on this computer, at the person's word", async () => {
    const calls = mockApi({
      "GET /api/brain/models": { matching: { enabled: true, model: "BAAI/bge-small-en-v1.5", present: false, downloading: false, error: null, about_mb: 70 } },
      "POST /api/brain/models/download": { matching: { enabled: true, present: false, downloading: true } },
      "GET /api/actors": [],
      "GET /api/runners": [],
    });
    const user = userEvent.setup();
    renderAt(<SettingsPage />, { path: "/settings", route: "/settings?tab=computer" });
    expect(await screen.findByText(/matches requests by words until its local model is here/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Download the model" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/models/download")).toBe(true));
  });

  it("shows the goals and what they steer, with earlier versions", async () => {
    mockApi({ "GET /api/brain/goals": goals });
    renderAt(<SettingsPage />, { path: "/settings", route: "/settings?tab=goals" });
    expect(await screen.findByText(/steer what gets pulled from everything you bring in/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Earlier versions" })).toHaveAttribute("href", "/brain/entries/you-goals");
    expect(screen.getByRole("button", { name: "Change my answers" })).toBeInTheDocument();
  });

  it("lists each AI app with its state, how to connect it, test it and remove it", async () => {
    mockApi({ "GET /api/brain/apps": apps });
    const user = userEvent.setup();
    renderAt(<SettingsPage />, { path: "/settings", route: "/settings" });
    const cards = await screen.findAllByRole("listitem");
    expect(within(cards[0] as HTMLElement).getByText(/asked/)).toBeInTheDocument();
    expect(within(cards[1] as HTMLElement).getByText("found on this computer, not connected")).toBeInTheDocument();
    await user.click(within(cards[0] as HTMLElement).getByRole("button", { name: "Setup and removal" }));
    expect(within(cards[0] as HTMLElement).getByText(/claude mcp remove contxt/)).toBeInTheDocument();
  });
});

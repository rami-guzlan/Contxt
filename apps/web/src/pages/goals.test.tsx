import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { GoalPage as GoalPageData, GoalView, Ladder } from "../api/types";
import { GoalsStrip } from "../components/goals/GoalsStrip";
import { mockApi, renderAt } from "../test/render";
import { GoalPage } from "./goals/GoalPage";
import { ProjectsPage } from "./Projects";
import { Alignment } from "./settings/Alignment";

const webinar: GoalView = {
  id: "goal-webinars",
  title: "Grow webinar attendance to 150 a session",
  level: "yours",
  kept_by: null,
  why: "Webinars are our best source of qualified conversations.",
  serves: [],
  measure: { kind: "enter", target: 150, unit: "a session" },
  measure_words: "You enter it at check-in, toward 150 a session",
  due: "2026-12-15",
  cadence: "weekly",
  lifecycle: "active",
  started: "2026-10-10",
  status: "on_track",
  words: "On track",
  call: "on_track",
  flag: "The measure says 64 against 150, which is behind its target.",
  stale: false,
  now: 71,
  target: 150,
  unit: "a session",
  trend: [60, 71],
  checked_at: "2026-10-10T09:00:00Z",
  checked_in_at: "2026-10-10T09:00:00Z",
  check_in_due: false,
  projects: [{ id: "q4", title: "Q4 webinar series", status: "active" }],
  shared_plan: true,
  suggestions: 1,
};

const tidy: GoalView = {
  ...webinar,
  id: "goal-nothing-waits",
  title: "Nothing waits in Catch up over a week",
  level: "agent",
  kept_by: "knowledge-agent",
  measure: { kind: "at_most", signal: "waiting", target: 0, unit: "items" },
  measure_words: "Items waiting for you longer than 7 days: at most 0 items",
  status: "off_track",
  words: "Off track",
  call: null,
  flag: "",
  now: 6,
  target: 0,
  unit: "items",
  projects: [],
  suggestions: undefined,
};

function ladder(extra: Partial<Ladder> = {}): Ladder {
  return {
    purpose: { id: "you-goals", exists: true, text: "Keep my work straight", signals: ["fewer corrections"] },
    yours: [webinar],
    agents: [tidy],
    has_goals: true,
    check_ins_due: 0,
    starters: [{ id: "goal-nothing-waits", title: tidy.title, on: true }],
    signals: [],
    ...extra,
  };
}

const project = {
  id: "q4",
  title: "Q4 webinar series",
  summary: "Three webinars.",
  status: "active",
  active: true,
  current: "",
  next: "",
  blockers: "",
  updated: null,
  aliases: [],
  files: 0,
  updates: 0,
  topic: "projects/q4",
  objective: "Three webinars that each bring 150 qualified attendees.",
  goals: ["goal-webinars"],
};

describe("Goals and Projects", () => {
  it("is simply Projects, with one quiet line, until you set a goal", async () => {
    mockApi({
      "GET /api/brain/projects": [{ ...project, goals: [] }],
      "GET /api/goals": ladder({ yours: [], agents: [], has_goals: false }),
      "GET /api/brain/goals": { exists: true, projects: [] },
    });
    renderAt(<ProjectsPage />);
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText(/Goals are optional/)).toBeInTheDocument();
    expect(screen.queryByText("Your goals")).not.toBeInTheDocument();
  });

  it("leads with your goals, each with its call, flag and check-in on the card", async () => {
    const calls = mockApi({
      "GET /api/brain/projects": [project],
      "GET /api/goals": ladder(),
      "GET /api/brain/goals": { exists: true, projects: [] },
      "POST /api/goals/goal-webinars/check-in": { ...webinar, now: 75 },
    });
    renderAt(<ProjectsPage />);
    expect(await screen.findByRole("heading", { name: "Goals and Projects" })).toBeInTheDocument();
    const card = screen.getAllByRole("link", { name: webinar.title })[0]!.closest("li") as HTMLElement;
    expect(screen.getByText("Serves:")).toBeInTheDocument();
    expect(within(card).getByText(/behind its target/)).toBeInTheDocument();
    expect(screen.getByText(/Objective: Three webinars/)).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Check in" }));
    const number = within(card).getByLabelText("The number now");
    await userEvent.clear(number);
    await userEvent.type(number, "75");
    await userEvent.type(within(card).getByLabelText("One line"), "Two promos booked");
    await userEvent.click(within(card).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.path.endsWith("/check-in"))?.body).toEqual({ call: "on_track", value: 75, line: "Two promos booked" }));
  });
});

const page: GoalPageData = {
  ...webinar,
  journal: [{ at: "2026-10-10T09:00:00Z", kind: "check_in", by: "person:owner", call: "on_track", value: 71, line: "Two promos booked" }],
  checks: [],
  plan: "# Plan\n\n## Wish and outcome\n\n150 a session.",
  context: "Goal: Grow webinar attendance (`goal-webinars`, yours)\nShared plan: get_note `goal-webinars` (Wish and outcome).",
  board: {
    columns: 2,
    template: "plan",
    version: 3,
    blocks: [
      { id: "b1", type: "note", title: "Wish and outcome", shared: true, collapsed: false, column: 0, text: "150 a session." },
      { id: "b2", type: "checklist", title: "Key results", shared: true, collapsed: false, column: 1, items: [{ text: "Pick the Q4 topics", done: true }] },
    ],
  },
  suggestions: [{ id: "s1", text: "Book 2 partner promos", source: "goal coach", at: "2026-10-10T09:00:00Z", status: "waiting" }],
  templates: [{ id: "plan", label: "Plan it" }],
};

describe("A goal's page", () => {
  it("shows your call beside the measure, the board, and what your AI gets", async () => {
    mockApi({ "GET /api/goals/goal-webinars": page, "GET /api/brain/projects": [project] });
    renderAt(<GoalPage />, { path: "/goals/:goalId", route: "/goals/goal-webinars" });
    expect(await screen.findByRole("heading", { name: webinar.title })).toBeInTheDocument();
    expect(screen.getByText(/behind its target/)).toBeInTheDocument();
    expect(screen.getByLabelText("Strategy board")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Your AIs can read this")).toHaveLength(2);
    expect(screen.getByText(/Private blocks never reach an AI/)).toBeInTheDocument();
    expect(screen.getByText(/Two promos booked/)).toBeInTheDocument();
  });

  it("saves a new private note, and a suggestion becomes a step", async () => {
    const calls = mockApi({
      "GET /api/goals/goal-webinars": page,
      "GET /api/brain/projects": [project],
      "PUT /api/goals/goal-webinars/board": page,
      "POST /api/goals/goal-webinars/suggestions/s1": page,
    });
    renderAt(<GoalPage />, { path: "/goals/:goalId", route: "/goals/goal-webinars" });
    await screen.findByLabelText("Strategy board");
    await userEvent.click(screen.getByRole("button", { name: "+ Block" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Note" }));
    await userEvent.click(screen.getByRole("button", { name: "Save the board" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const sent = calls.find((c) => c.method === "PUT")?.body as { layout: { blocks: { type: string; shared: boolean }[] }; expected_version: number };
    expect(sent.expected_version).toBe(3);
    expect(sent.layout.blocks.at(-1)).toMatchObject({ type: "note", shared: false });
    await userEvent.click(screen.getByRole("button", { name: "Make it a step" }));
    await waitFor(() => expect(calls.find((c) => c.path.endsWith("/suggestions/s1"))?.body).toEqual({ accept: true }));
  });
});

describe("Settings > Alignment", () => {
  it("lists agent goals with their measures, and offers the knowledge agent's goals", async () => {
    const calls = mockApi({
      "GET /api/goals": ladder({ agents: [], starters: [{ id: "goal-nothing-waits", title: tidy.title, on: false }] }),
      "GET /api/goals/settings": { weekly_review: false },
      "POST /api/goals/starters": ladder(),
    });
    renderAt(<Alignment purpose={<p>The purpose</p>} />, { path: "/settings", route: "/settings?tab=alignment" });
    expect(await screen.findByText("The purpose")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: webinar.title })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Turn them on" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/goals/starters")).toBe(true));
  });

  it("shows how the levels differ", async () => {
    mockApi({ "GET /api/goals": ladder(), "GET /api/goals/settings": { weekly_review: false } });
    renderAt(<Alignment purpose={<p>The purpose</p>} />, { path: "/settings", route: "/settings?tab=alignment&view=differ" });
    expect(await screen.findByText("Agent goals")).toBeInTheDocument();
    expect(screen.getByText(/A rule says how work must be done/)).toBeInTheDocument();
  });
});

describe("Home's goal strip", () => {
  it("stays away with nothing to show, and lists agent goals that need you", async () => {
    mockApi({ "GET /api/goals/home": { has_goals: false, purpose: "", check_ins: [], agent_goals: [tidy], review: null } });
    renderAt(<GoalsStrip />);
    expect(await screen.findByText("Agent goals that need you")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: tidy.title })).toBeInTheDocument();
  });
});

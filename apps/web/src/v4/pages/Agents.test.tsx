import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { AgentsPage } from "./Agents";

const provider = {
  id: "codex",
  label: "Codex",
  vendor: "OpenAI",
  model: "gpt-test-model",
  model_from: "~/.codex/config.toml",
  available: true,
  health: "Ready",
  data: "What the knowledge agent reads for a job is sent to OpenAI through Codex, on your own plan.",
  switches: "never on its own: when it cannot answer, the work stops and says so",
};

const agent = {
  model: "codex",
  suggestions: true,
  goals: [],
  actions: [
    { id: "tidy-repeats", label: "Find repeats", blurb: "Notes that say the same thing, merged or narrowed.", serves: null },
    { id: "check-drift", label: "Check drift", blurb: "Notes something newer may contradict.", serves: null },
    { id: "verify-sources", label: "Verify with sources", blurb: "Checked against the web.", serves: null },
  ],
  questions: [
    {
      key: "q1",
      action: "check-drift",
      verdict: "ask",
      ask: "Is the onboarding checklist still the current one?",
      why: "A newer capture lists other steps.",
      text: "",
      target: { type: "note", id: "n_onboarding", title: "Onboarding checklist" },
      at: "2026-10-20T10:00:00Z",
      status: "open",
    },
  ],
  runs: [
    {
      id: "arun_1",
      action: "tidy-repeats",
      label: "Find repeats",
      model: "codex",
      at: "2026-10-21T09:00:00Z",
      summary: "Two notes about invoices say the same",
      checked: 12,
      found: 12,
      proposed: 1,
      questions: 0,
      fine: 11,
      skipped: 0,
      proposals: ["prp_9"],
      notes: [],
    },
  ],
  models: [
    { id: "claude", label: "Claude Code", kind: "cli", available: false, detail: "Not signed in", brief: false },
    { id: "codex", label: "Codex", kind: "cli", available: true, detail: "Ready", brief: false },
  ],
  working: [],
  provider,
};

const runners = [{ id: "codex", label: "Codex", provider: "codex", one_click: true, installed: true, version: "1.0", signed_in: true, install: "", sign_in: "", actor_id: null, detail: "" }];
const instructions = [
  { app: "claude-code", supported: true, installed: false, path: "/home/someone/.claude/CLAUDE.md" },
  { app: "codex", supported: true, installed: false, path: "/home/someone/.codex/AGENTS.md" },
];

function base(over: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/brain/agent": agent,
    "GET /api/brain/agent/jobs": [],
    "GET /api/runners": runners,
    "GET /api/brain/models": { matching: { enabled: true, present: true, downloading: false } },
    "GET /api/connections/instructions": instructions,
    "GET /api/brain/proposals": [{ id: "prp_9" }],
    "GET /api/brain/agent/skills": [],
    ...over,
  });
}

afterEach(() => vi.restoreAllMocks());

describe("Agents, Knowledge agent", () => {
  it("shows the provider, model, where data goes, jobs and runs from the server", async () => {
    base();
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    expect(await screen.findByText(/Model: gpt-test-model \(read from ~\/\.codex\/config\.toml\)/)).toBeInTheDocument();
    expect(screen.getByText(/sent to OpenAI through Codex/)).toBeInTheDocument();
    expect(screen.getByText(/Never|never on its own/)).toBeInTheDocument();
    expect(screen.getByText(/Signed in · checked/)).toBeInTheDocument();
    expect(screen.getAllByText("Find repeats").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Two notes about invoices say the same/).length).toBeGreaterThan(0);
    expect(screen.getByText("Is the onboarding checklist still the current one?")).toBeInTheDocument();
    expect(screen.getByText(/Meaning index on CPU/)).toBeInTheDocument();
  });

  it("says plainly when there is no AI to run on and nothing has run", async () => {
    base({ "GET /api/brain/agent": { ...agent, provider: undefined, runs: [], questions: [] } });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    expect(await screen.findByText("No AI to run it on yet")).toBeInTheDocument();
    expect(screen.getByText(/No runs yet/)).toBeInTheDocument();
    expect(screen.getByText(/No open questions/)).toBeInTheDocument();
  });

  it("labels words-only search with its lower recall when the meaning model is missing", async () => {
    base({ "GET /api/brain/models": { matching: { enabled: true, present: false, downloading: false } } });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    expect(await screen.findByText(/Words-only search: the meaning model isn't on this computer/)).toBeInTheDocument();
  });

  it("shows a failure with Try again when the agent can't be read", async () => {
    base({ "GET /api/brain/agent": { status: 500, body: { error: { code: "error", message: "The server stopped." } } } });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    expect(await screen.findByText("The server stopped.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("runs a job by hand and keeps later jobs disabled", async () => {
    const calls = base({ "POST /api/brain/agent/actions/check-drift": { status: 201, body: { id: "job_1", kind: "action", action: "check-drift", status: "waiting" } } });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    await screen.findByText("Check drift");
    const card = screen.getByText("Check drift").closest("div")?.parentElement as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Run now" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/agent/actions/check-drift")).toBe(true));
    const later = screen.getByText("Verify with sources").closest("div")?.parentElement as HTMLElement;
    expect(within(later).getByRole("button", { name: "Later" })).toBeDisabled();
  });

  it("installs Ask the Brain first only after the person confirms, and shows the file", async () => {
    const calls = base({ "POST /api/connections/instructions/claude-code": { app: "claude-code", supported: true, installed: true, path: "/home/someone/.claude/CLAUDE.md" } });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    fireEvent.click(await screen.findByRole("switch", { name: "Ask the Brain first in Claude Code" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("/home/someone/.claude/CLAUDE.md")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path.startsWith("/api/connections/instructions"))).toBe(false);
    fireEvent.click(within(dialog).getByRole("button", { name: "Yes, add it" }));
    await waitFor(() => {
      const sent = calls.find((c) => c.method === "POST" && c.path === "/api/connections/instructions/claude-code");
      expect(sent?.body).toEqual({ confirmed: true });
    });
  });

  it("chooses the model it runs through", async () => {
    const calls = base({ "PUT /api/brain/agent/settings": agent });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents" });
    fireEvent.click(await screen.findByRole("tab", { name: "How it works" }));
    expect(screen.getByRole("radio", { name: /Claude Code/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Codex" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ model: "codex" }));
  });
});

describe("Agents, Alignment", () => {
  it("shows findings, what needs review and when it was last checked, with no score", async () => {
    base();
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents?tab=alignment" });
    expect(await screen.findByText("Brain upkeep")).toBeInTheDocument();
    expect(screen.getByText(/1 finding to decide across 2 checks · 1 need review in Catch up/)).toBeInTheDocument();
    expect(screen.getByText("Is the onboarding checklist still the current one?")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});

describe("Agents, profiles and skills", () => {
  it("lists agent profiles and makes a new one", async () => {
    const calls = base({
      "GET /api/agents": [
        { name: "support-writer", role: "Answers customer mail", responsibilities: [], goals: [], projects: [], skills: ["reply"], library: [], context: [], meetings_days: 0, boundaries: [], output: "outputs", output_shape: "", runner: "codex", review: true, scope: "", status: "active", prompt: "", path: "agents/support-writer.md" },
      ],
      "POST /api/agents": { status: 201, body: { name: "planner" } },
    });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents?tab=agents" });
    expect(await screen.findByText("support-writer")).toBeInTheDocument();
    expect(screen.getByText("Answers customer mail")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /New agent profile/ })[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "planner" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save the profile" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.path === "/api/agents")?.body).toEqual({ name: "planner", role: "", prompt: "" }));
  });

  it("shows an empty state for skills and the agent's skills with their release", async () => {
    base({
      "GET /api/skills": { skills: [], waiting: [] },
      "GET /api/brain/agent/skills": [
        { name: "tidy-repeats", description: "Merge notes that repeat.", when_to_use: "", triggers: [], text: "", own: false },
        { name: "pull-from-tools", description: "Pull from connected tools.", when_to_use: "", triggers: [], text: "", own: false },
      ],
    });
    renderAt(<AgentsPage />, { path: "/agents", route: "/agents?tab=skills" });
    expect(await screen.findByText("No skills of your own yet")).toBeInTheDocument();
    expect(await screen.findByText("Release 1 · run by hand")).toBeInTheDocument();
    expect(screen.getByText("Later · Release 2")).toBeInTheDocument();
  });
});

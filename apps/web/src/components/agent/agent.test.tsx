import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentOverview, AgentQuestion } from "../../api/types";
import { AgentPage } from "../../pages/brain/Agent";
import { Flashcards } from "../Flashcards";
import { mockApi, renderAt } from "../../test/render";
import { AgentProvider } from "./AgentContext";
import { AgentDock, AgentPanel, ModelPicker } from "./AgentPanel";
import { AgentStrip } from "./AgentStrip";

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
  window.localStorage.clear();
});

const question: AgentQuestion = {
  key: "freshen-up|retire|note|holiday-card|Retire this note?",
  action: "freshen-up",
  verdict: "retire",
  ask: "Retire this note?",
  why: "The holiday card went out.",
  text: "",
  target: { type: "note", id: "holiday-card", title: "Holiday card" },
  at: "2026-10-09T10:00:00Z",
  status: "open",
  run: "arun_1",
};

const overview: AgentOverview = {
  model: "claude",
  suggestions: true,
  actions: [
    { id: "tidy-repeats", label: "Find repeats", blurb: "Notes that say the same thing." },
    { id: "freshen-up", label: "Freshen up", blurb: "Stale notes." },
  ],
  questions: [question],
  runs: [
    {
      id: "arun_1",
      action: "freshen-up",
      label: "Freshen up",
      model: "claude",
      at: "2026-10-09T10:00:00Z",
      summary: "1 to retire.",
      checked: 1,
      found: 1,
      proposed: 0,
      questions: 1,
      fine: 0,
      skipped: 0,
      proposals: [],
      notes: [],
    },
  ],
  models: [
    { id: "claude", label: "Claude Code (your CLI)", kind: "cli", available: true, detail: "On this computer", brief: false },
    { id: "ollama:qwen3:1.7b", label: "qwen3:1.7b (local)", kind: "local", available: true, detail: "Through Ollama", brief: true },
  ],
  working: [],
};

const job = (id: string, extra: object) => ({
  id,
  kind: "action",
  action: "tidy-repeats",
  model: "claude",
  model_label: "Claude Code (your CLI)",
  message: "",
  status: "done",
  result: {},
  error: null,
  started_at: "2026-10-09T10:00:00Z",
  finished_at: "2026-10-09T10:00:30Z",
  ...extra,
});

describe("the knowledge agent", () => {
  it("shows its model, actions, questions and what it did, and runs an action", async () => {
    const calls = mockApi({
      "GET /api/brain/agent": overview,
      "GET /api/brain/agent/suggestions": [],
      "PUT /api/brain/agent/settings": { ...overview, model: "ollama:qwen3:1.7b" },
      "POST /api/brain/agent/actions/tidy-repeats": { status: 201, body: job("ajob_1", { status: "running" }) },
      "GET /api/brain/agent/jobs/ajob_1": job("ajob_1", {
        result: { id: "arun_2", summary: "One pair says the same thing.", proposed: 1, questions: 0, notes: [] },
      }),
    });
    const user = userEvent.setup();
    renderAt(<AgentPage />, { path: "/brain/agent", route: "/brain/agent" });
    expect(await screen.findByRole("radio", { name: /Claude Code \(your CLI\)/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: /qwen3:1\.7b/ }));
    expect(screen.getByText(/On this computer, through Ollama: free and private/)).toBeInTheDocument();
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ model: "ollama:qwen3:1.7b" }));
    expect(screen.getByText("Retire this note?")).toBeInTheDocument();
    expect(screen.getByText(/Last .*: 1 to retire\./)).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "Find repeats" });
    await user.click(within(card).getByRole("button", { name: "Run it" }));
    expect(await within(card).findByText("One pair says the same thing.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Catch up" })).toHaveAttribute("href", "/catch-up");
  });

  it("works through any AI CLI here, with any model it offers", async () => {
    const withClis: AgentOverview = {
      ...overview,
      model: "gemini:gemini-2.5-flash",
      models: [
        { id: "claude", label: "Claude Code", kind: "cli", available: true, detail: "On your own plan", brief: false },
        { id: "codex", label: "ChatGPT (Codex CLI)", kind: "cli", available: false, detail: "Not installed", brief: false },
        { id: "gemini", label: "Gemini CLI", kind: "cli", available: true, detail: "On your own plan", brief: false },
        { id: "ollama:qwen3:1.7b", label: "qwen3:1.7b (local)", kind: "local", available: true, detail: "Through Ollama", brief: true },
      ],
    };
    const calls = mockApi({
      "GET /api/brain/agent": withClis,
      "GET /api/brain/agent/suggestions": [],
      "PUT /api/brain/agent/settings": { ...withClis, model: "gemini:gemini-2.5-pro" },
    });
    const user = userEvent.setup();
    renderAt(<AgentPage />, { path: "/brain/agent", route: "/brain/agent" });
    expect(await screen.findByRole("radio", { name: /Gemini CLI/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Codex/ })).toBeDisabled();
    const name = screen.getByRole("textbox", { name: "Model for Gemini CLI" });
    expect(name).toHaveValue("gemini-2.5-flash");
    await user.clear(name);
    await user.type(name, "gemini-2.5-pro");
    await user.click(screen.getByRole("button", { name: "Use this model" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ model: "gemini:gemini-2.5-pro" }));
  });

  it("names the model the side panel works through, a CLI's own model too", async () => {
    mockApi({ "GET /api/brain/agent": { ...overview, model: "claude:claude-haiku-5-5" }, "GET /api/brain/agent/suggestions": [] });
    renderAt(<ModelPicker models={overview.models} value="claude:claude-haiku-5-5" />);
    expect(await screen.findByRole("combobox")).toHaveValue("claude:claude-haiku-5-5");
    expect(screen.getByRole("option", { name: "Claude Code (your CLI), claude-haiku-5-5" })).toBeInTheDocument();
  });

  it("answers a question in one tap", async () => {
    const calls = mockApi({
      "GET /api/brain/agent": overview,
      "GET /api/brain/agent/suggestions": [],
      "POST /api/brain/agent/questions/answer": { key: question.key, do: "retire", checkpoint: "cp-1" },
    });
    const user = userEvent.setup();
    renderAt(<AgentPage />, { path: "/brain/agent", route: "/brain/agent" });
    await user.click(await screen.findByRole("button", { name: "Retire it" }));
    expect(await screen.findByText(/Retired\./)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/agent/questions/answer")?.body).toEqual({ key: question.key, do: "retire" });
  });

  it("asks from the strip above the map and answers in the side panel, with actions and notes to keep", async () => {
    const calls = mockApi({
      "GET /api/brain/agent": overview,
      "GET /api/brain/agent/suggestions": [],
      "POST /api/brain/agent/chat": { status: 201, body: job("ajob_9", { kind: "chat", status: "running" }) },
      "GET /api/brain/agent/jobs/ajob_9": job("ajob_9", {
        kind: "chat",
        result: {
          reply: "Start with the **stale** notes.",
          run: ["freshen-up"],
          notes: [{ title: "Reviews on Fridays", text: "Client reviews happen on Fridays.", kind: "fact" }],
        },
      }),
      "POST /api/brain/agent/notes": { status: 201, body: { status: "pending", proposal_id: "p9", message: "" } },
    });
    const user = userEvent.setup();
    renderAt(
      <AgentProvider>
        <AgentStrip />
        <AgentPanel />
      </AgentProvider>,
    );
    await user.type(await screen.findByLabelText("Ask the knowledge agent"), "What should I tidy first?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    const panel = await screen.findByRole("complementary", { name: "Knowledge agent" });
    expect(within(panel).getByText("What should I tidy first?")).toBeInTheDocument();
    expect(await within(panel).findByText("stale")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/agent/chat")?.body).toEqual({ message: "What should I tidy first?", history: [] });
    expect(within(panel).getByRole("button", { name: "Run Freshen up" })).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Keep it" }));
    expect(await within(panel).findByText(/it waits in/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/agent/notes")?.body).toMatchObject({
      title: "Reviews on Fridays",
      said: "What should I tidy first?",
    });
  });

  it("brings up suggestions at the bottom right, and sets one aside", async () => {
    const calls = mockApi({
      "GET /api/brain/agent": overview,
      "GET /api/brain/agent/suggestions": [
        { key: "stale:abc", kind: "stale", title: "3 notes are past their review", detail: "The agent can sort them.", count: 3, action: "freshen-up", link: null },
      ],
      "POST /api/brain/agent/suggestions/dismiss": { status: 204 },
    });
    const user = userEvent.setup();
    renderAt(
      <AgentProvider>
        <AgentDock />
      </AgentProvider>,
    );
    const toast = await screen.findByRole("article", { name: "3 notes are past their review" });
    expect(within(toast).getByRole("button", { name: "Run it" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open the knowledge agent" })).toHaveTextContent("1");
    await user.click(within(toast).getByRole("button", { name: "Not now" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/brain/agent/suggestions/dismiss")?.body).toEqual({ key: "stale:abc" }));
    // set aside, it pops up no more; it stays on the button's count until the Brain changes
    expect(screen.queryByRole("article", { name: "3 notes are past their review" })).not.toBeInTheDocument();
  });
});

describe("Home's flashcards", () => {
  it("show what to keep an eye on one at a time, what the agent did, and what is coming", async () => {
    const calls = mockApi({
      "GET /api/brain/agent": overview,
      "GET /api/brain/agent/suggestions": [
        { key: "stale:abc", kind: "stale", title: "3 notes are past their review", detail: "The agent can sort them.", count: 3, action: "freshen-up", link: null },
        { key: "clashes:def", kind: "clashes", title: "1 suggestion may disagree", detail: "In Catch up.", count: 1, action: null, link: "/catch-up" },
      ],
      "POST /api/brain/agent/suggestions/dismiss": { status: 204 },
    });
    const user = userEvent.setup();
    renderAt(
      <AgentProvider>
        <Flashcards />
      </AgentProvider>,
    );
    const first = await screen.findByRole("article", { name: "3 notes are past their review" });
    expect(within(first).getByText("Stale context")).toBeInTheDocument();
    expect(within(first).getByText("3")).toBeInTheDocument();
    expect(screen.getByText("1 of 4")).toBeInTheDocument(); // two suggestions, the agent's last run, coming soon
    await user.click(screen.getByRole("button", { name: "Next card" }));
    expect(within(screen.getByRole("article", { name: "1 suggestion may disagree" })).getByRole("link", { name: "Open" })).toHaveAttribute("href", "/catch-up");
    await user.click(screen.getByRole("button", { name: "Next card" }));
    expect(screen.getByRole("article", { name: /Freshen up/ })).toHaveTextContent("1 to retire.");
    await user.click(screen.getByRole("button", { name: "See all 4" }));
    expect(screen.getByRole("article", { name: "Agents and workflows of your own" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("article", { name: "3 notes are past their review" })).getByRole("button", { name: "Got it" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/brain/agent/suggestions/dismiss")?.body).toEqual({ key: "stale:abc" }));
  });

  it("say so when nothing needs a look", async () => {
    mockApi({ "GET /api/brain/agent": { ...overview, runs: [] }, "GET /api/brain/agent/suggestions": [] });
    renderAt(
      <AgentProvider>
        <Flashcards />
      </AgentProvider>,
    );
    expect(await screen.findByRole("article", { name: "Nothing needs a look" })).toBeInTheDocument();
  });
});
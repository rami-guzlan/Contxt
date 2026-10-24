// Agent orchestrators in a project: the cards with their agents and the gate, Run with a
// steer, the editor (a new profile saved to Agents), the agent tasks apart from Your tasks,
// the activity timeline, Outputs grouped by run with the final pinned on top, and the auto
// sheet in Context. All from the API; each action calls its endpoint with the right body.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ProjectPage } from "./Project";

const ORC = "/api/projects/foc_q4/orchestrators";

const detail = {
  id: "foc_q4",
  title: "Q4 webinars",
  summary: "Run the Q4 series",
  aliases: [],
  status: "active",
  active: true,
  state: { current: "", next: "" },
  brief: "",
  route_key: "work/q4",
  objective: "",
  goals: [],
  updates: [],
  files: [],
  notes: [],
};

const clis = [
  { id: "claude", label: "Claude Code", models: [{ id: "opus", label: "Opus" }, { id: "sonnet", label: "Sonnet" }, { id: "haiku", label: "Haiku · cheaper" }], one_click: true },
  { id: "codex", label: "Codex CLI", models: [{ id: "gpt-5", label: "GPT-5" }], one_click: false },
];

const agents = [
  { id: "a1", profile: "ads-analyst", role: "Owns paid performance. Reads spend.", short: "paid performance", works_by: "files", cli: "claude", model: "sonnet", tools: [] },
  { id: "a2", profile: "publisher", role: "Owns publishing.", short: "publishing", works_by: "mcp", cli: "claude", model: "haiku", tools: ["mcp__buffer__list_posts"] },
];

const gate = {
  id: "gate_1",
  kind: "post",
  what: "Post the carousel to LinkedIn on Tuesday",
  tools: ["mcp__buffer__create_post"],
  agent_id: "a2",
  profile: "publisher",
  status: "pending",
  asked_at: "2026-10-22T09:05:00Z",
  approve_label: "Yes, post it",
};

const run = {
  id: "orun_7",
  orchestrator_id: "orc_1",
  status: "waiting",
  shown: "waiting",
  trigger: "gnomon",
  asked_by: "",
  steer: "focus on paid",
  task_id: "task_o",
  spec: { name: "Carousel pipeline", slug: "carousel-pipeline", goal: "Make and queue a carousel.", cli: "claude", model: "opus", sheet: "Carousel pipeline · sheet", agents },
  agents: {
    a1: { state: "reported", shown: "reported", task_id: "task_a1", act_task_id: null, task_status: "review", note: "", brief: "" },
    a2: { state: "reported", shown: "reported", task_id: "task_a2", act_task_id: null, task_status: "review", note: "", brief: "" },
  },
  trail: [
    { at: "2026-10-22T09:02:00Z", agent_id: "a1", profile: "ads-analyst", short: "paid performance", output_id: "art_41", title: "Spend snapshot", summary: "Spend 412 last week.", sources: ["Campaign export.csv"], act: false },
    { at: "2026-10-22T09:04:00Z", agent_id: "a2", profile: "publisher", short: "publishing", output_id: "art_42", title: "Buffer draft", summary: "Ready to queue.", sources: ["Buffer via MCP"], act: false },
  ],
  gates: [gate],
  final: { output_id: "art_43", title: "Carousel ready, waiting to post", summary: "Six slides, queued after your yes.", sources: ["Campaign export.csv", "Buffer via MCP"], at: "2026-10-22T09:06:00Z" },
  note: "",
  started_at: "2026-10-22T09:00:00Z",
  finished_at: null,
};

const orchestrator = {
  id: "orc_1",
  slug: "carousel-pipeline",
  name: "Carousel pipeline",
  goal: "Make and queue a carousel.",
  cli: "claude",
  model: "opus",
  trigger: "gnomon",
  sheet: "Carousel pipeline · sheet",
  agents,
  version: 2,
  latest_run: run,
};

const overview = {
  orchestrators: [orchestrator],
  agent_tasks: [
    { kind: "agent", title: "Owns paid performance. Reads spend.", profile: "ads-analyst", agent_id: "a1", orchestrator_id: "orc_1", orchestrator: "Carousel pipeline", run_id: "orun_7", works_by: "files", cli: "claude", model: "sonnet", state: "reported", task_id: "task_a1", note: "" },
    { kind: "orchestrator", title: "Collect the reports, fill Carousel pipeline · sheet, write the final output", profile: "", agent_id: "", orchestrator_id: "orc_1", orchestrator: "Carousel pipeline", run_id: "orun_7", works_by: "", cli: "claude", model: "opus", state: "waiting", task_id: "task_o", note: "" },
  ],
  clis,
  works_by: [],
};

const timeline = [
  { id: "e3", seq: 3, at: "2026-10-22T09:05:00Z", kind: "approval", who: "publisher", text: "Waiting for your yes", meta: gate.what, go: "", run_id: "orun_7", orchestrator_id: "orc_1" },
  { id: "e2", seq: 2, at: "2026-10-22T09:04:00Z", kind: "report", who: "publisher", text: "Reported back: Buffer draft", meta: "Ready to queue.", go: "outputs", run_id: "orun_7", orchestrator_id: "orc_1" },
  { id: "e1", seq: 1, at: "2026-10-22T09:00:00Z", kind: "plan", who: "Carousel pipeline", text: "Run started from Gnomon", meta: "Claude Code · Opus", go: "", run_id: "orun_7", orchestrator_id: "orc_1" },
];

const lanes = { lanes: { waiting_for_you: [], handed_off: [], working: [], blocked: [], open: [] }, done_this_week: [], count: 0 };

const tasksApi = {
  "GET /api/brain/projects/foc_q4": detail,
  "GET /api/skills": { skills: [], waiting: [] },
  "GET /api/agents": [{ name: "ads-analyst" }, { name: "publisher" }],
  "GET /api/work/projects/foc_q4/timeline": [],
  "GET /api/work/handoffs": lanes,
  [`GET ${ORC}`]: overview,
  [`GET ${ORC}/timeline`]: timeline,
};

const at = (tab: string) => ({ path: "/projects/:projectId", route: `/projects/foc_q4?tab=${tab}` });

describe("Project · Agent orchestrators", () => {
  it("shows the orchestrator with its agents, the gate, the agent tasks apart from Your tasks, and the activity", async () => {
    mockApi(tasksApi);
    renderAt(<ProjectPage />, at("tasks"));
    expect(await screen.findByText("Agent orchestrators")).toBeInTheDocument();
    expect(await screen.findByText("Make and queue a carousel.")).toBeInTheDocument();
    expect(screen.getAllByText("Waiting for you").length).toBeGreaterThan(0);
    expect(screen.getByText(/Files only · Claude Code · Sonnet/)).toBeInTheDocument();
    const card = screen.getByRole("group", { name: "Waiting for your yes" });
    expect(within(card).getByText(/Post the carousel to LinkedIn on Tuesday/)).toBeInTheDocument();
    expect(within(card).getByText(/mcp__buffer__create_post/)).toBeInTheDocument();
    expect(screen.getByText("Agent tasks")).toBeInTheDocument();
    expect(screen.getByText("Your tasks")).toBeInTheDocument();
    expect(screen.getByText("Owns paid performance. Reads spend.")).toBeInTheDocument();
    expect(await screen.findByText("Reported back: Buffer draft")).toBeInTheDocument();
    expect(screen.getByText("3 events")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Board/ })).toBeNull();
  });

  it("says yes to the gate with the owner's words", async () => {
    const calls = mockApi({ ...tasksApi, [`POST ${ORC}/runs/orun_7/gates/gate_1`]: { run, gate: { ...gate, status: "approved" } } });
    renderAt(<ProjectPage />, at("tasks"));
    await userEvent.click(await screen.findByRole("button", { name: "Yes, post it" }));
    const sent = calls.find((c) => c.method === "POST" && c.path === `${ORC}/runs/orun_7/gates/gate_1`);
    expect(sent?.body).toEqual({ decision: "approve", quote: "Yes, post it" });
  });

  it("runs an orchestrator with a steer", async () => {
    const idle = { ...orchestrator, latest_run: null };
    const calls = mockApi({ ...tasksApi, [`GET ${ORC}`]: { ...overview, orchestrators: [idle], agent_tasks: [] }, [`POST ${ORC}/orc_1/run`]: { status: 201, body: run } });
    renderAt(<ProjectPage />, at("tasks"));
    expect(await screen.findByText("No agent work yet. Run an orchestrator.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Steer the next run of Carousel pipeline"), "focus on paid");
    await userEvent.click(screen.getByRole("button", { name: "Run" }));
    const sent = calls.find((c) => c.method === "POST" && c.path === `${ORC}/orc_1/run`);
    expect(sent?.body).toEqual({ steer: "focus on paid" });
  });

  it("makes a new orchestrator with a new profile that is saved to Agents", async () => {
    const calls = mockApi({
      ...tasksApi,
      [`GET ${ORC}`]: { ...overview, orchestrators: [], agent_tasks: [] },
      [`GET ${ORC}/timeline`]: [],
      [`POST ${ORC}`]: { status: 201, body: { ...orchestrator, id: "orc_2", latest_run: null } },
    });
    renderAt(<ProjectPage />, at("tasks"));
    expect(await screen.findByText("No orchestrators here yet")).toBeInTheDocument();
    expect(screen.getByText(/Nothing yet\. Run an orchestrator/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New orchestrator" }));
    const editor = screen.getByRole("region", { name: "Orchestrator editor" });
    await userEvent.clear(within(editor).getByLabelText("Orchestrator name"));
    await userEvent.type(within(editor).getByLabelText("Orchestrator name"), "Promo check");
    await userEvent.type(within(editor).getByLabelText("Goal"), "See how the promo is doing.");
    await userEvent.type(within(editor).getByLabelText("New profile name"), "Voice editor");
    await userEvent.click(within(editor).getByRole("button", { name: "Create and add" }));
    expect(within(editor).getByText("NEW · SAVED TO AGENTS")).toBeInTheDocument();
    await userEvent.type(within(editor).getByLabelText("Role · the piece it owns"), "the copy.");
    await userEvent.click(within(editor).getByRole("button", { name: "Save" }));
    const sent = calls.find((c) => c.method === "POST" && c.path === ORC);
    expect(sent?.body).toMatchObject({
      name: "Promo check",
      goal: "See how the promo is doing.",
      cli: "claude",
      model: "opus",
      trigger: "gnomon",
      agents: [{ profile: "voice-editor", new_profile: true, role: "Owns the copy.", works_by: "files", cli: "claude", model: "sonnet", tools: [] }],
    });
  });

  it("shows a failure with Try again when the orchestrators can't be read", async () => {
    mockApi({ ...tasksApi, [`GET ${ORC}`]: { status: 500, body: { error: { code: "error", message: "The database is busy." } } } });
    renderAt(<ProjectPage />, at("tasks"));
    expect((await screen.findAllByText("The database is busy.")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Try again" }).length).toBeGreaterThan(0);
  });
});

describe("Project · Outputs and Context from orchestrators", () => {
  it("groups outputs by run with the final output pinned on top and its trail", async () => {
    mockApi({
      "GET /api/brain/projects/foc_q4": detail,
      [`GET ${ORC}`]: overview,
      [`GET ${ORC}/outputs`]: [run],
      "GET /api/outputs": { root: "", folders: [], files: [] },
      "GET /api/work/projects/foc_q4/timeline": [],
    });
    renderAt(<ProjectPage />, at("outputs"));
    expect(await screen.findByText("FINAL OUTPUT")).toBeInTheDocument();
    expect(screen.getByText("Carousel ready, waiting to post")).toBeInTheDocument();
    expect(screen.getByText("Six slides, queued after your yes.")).toBeInTheDocument();
    expect(screen.getByText("Steered: “focus on paid”")).toBeInTheDocument();
    expect(screen.getByText(/How it got here · 2 outputs/)).toBeInTheDocument();
    expect(screen.getByText("Spend snapshot")).toBeInTheDocument();
    expect(screen.getByText("Other outputs", { selector: "span" })).toBeInTheDocument();
  });

  it("shows each orchestrator's auto sheet with source and agent in Context", async () => {
    mockApi({
      "GET /api/brain/projects/foc_q4": detail,
      "GET /api/brain/proposals": [],
      "GET /api/work/live": { sheets: [], templates: [], waiting: [] },
      "GET /api/brain/requests": { requests: [], brain_tokens: 0, apps: [], engine: "" },
      [`GET ${ORC}/sheets`]: [
        {
          orchestrator_id: "orc_1",
          orchestrator: "Carousel pipeline",
          name: "Carousel pipeline · sheet",
          agents: 2,
          columns: ["What", "Value", "Source", "Agent", "As of"],
          cells: [{ what: "Spend, last 7 days", value: "412", source: "Campaign export.csv", agent: "ads-analyst", at: "2026-10-22T09:06:00Z", run_id: "orun_7" }],
        },
      ],
    });
    renderAt(<ProjectPage />, at("context"));
    const sheet = await screen.findByRole("table", { name: "Carousel pipeline · sheet" });
    expect(within(sheet).getByText("Spend, last 7 days")).toBeInTheDocument();
    expect(within(sheet).getByText("Campaign export.csv")).toBeInTheDocument();
    expect(within(sheet).getByText("Ads analyst")).toBeInTheDocument();
    expect(screen.getByText("Auto · kept by Carousel pipeline")).toBeInTheDocument();
  });
});

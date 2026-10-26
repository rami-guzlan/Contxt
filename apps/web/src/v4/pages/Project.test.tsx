// One project: Context (objective, progress, kept notes, packet, pending updates beside the
// approved value, telling it about the project), Tasks (Work with AI, the job timeline, the
// project's to-dos), Files with their source status, and Outputs as drafts with what they were
// made from. All from the API; each action calls its endpoint with the right body.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ProjectPage } from "./Project";

const detail = {
  id: "foc_spring",
  title: "Spring launch",
  summary: "Launch the spring line",
  aliases: ["the launch"],
  status: "active",
  active: true,
  state: { current: "Copy approved, assets in review.", next: "Book the photographer" },
  brief: "",
  route_key: "work/spring",
  objective: "A launch page live by May",
  goals: [],
  updates: [
    { seq: 2, at: "2026-10-21T10:00:00Z", summary: "Copy approved", changes: {}, evidence: "", actor: "owner" },
    { seq: 1, at: "2026-10-20T10:00:00Z", summary: "Kickoff held", changes: {}, evidence: "", actor: "claude-code" },
  ],
  files: [
    {
      path: "references/spring/brief.md",
      id: "ref_brief",
      title: "Spring brief",
      summary: "",
      version: 2,
      file_status: "current",
      dated: "2026-10-19",
      filename: "brief.docx",
      sections: 4,
    },
  ],
  notes: [
    { id: "n_rule", title: "No discounts", summary: "Never promise a discount in launch copy", kind: "rule", type: null, added: null },
    { id: "n_pref", title: "Tone", summary: "Warm, short sentences", kind: "preference", type: null, added: null },
  ],
};

const proposal = {
  id: "prp_9",
  kind: "project.progress",
  scope: "",
  route_key: "work/spring",
  title: "Registrations",
  note_summary: "",
  summary: "Registrations are at 388",
  body: "Registrations are at 388",
  current_body: "Registrations are at 214",
  created: "2026-10-22T09:00:00Z",
  proposer: "claude-code",
  reason: "",
  similar: "",
  conflicts: "",
  source: { id: "cap_3", version: "v2", locator: "row 389", speaker: "unknown", excerpt: "388 registered" },
  operation: "Project update",
  statement_status: "stated",
  effective: "",
  destination: "Projects › Spring launch",
  op_id: "op_1",
  target: { project_id: "foc_spring" },
};

const base = {
  "GET /api/brain/projects/foc_spring": detail,
  "GET /api/brain/proposals": [proposal],
  "GET /api/work/live": { sheets: [{ id: "spring-numbers", title: "Spring numbers", key: "Metric", columns: [{}, {}], partition_by: "", scope: "foc_spring", template: "", builtin: false, description: "" }], templates: [], waiting: [] },
  "GET /api/brain/requests": { requests: [], brain_tokens: 0, apps: [], engine: "" },
  "GET /api/brain/preview": {
    request: "A launch page live by May",
    mode: "project",
    tokens: 812,
    text: "PACKET TEXT FOR SPRING",
    project: { id: "foc_spring", title: "Spring launch" },
    procedure: null,
    candidates: [],
    notes: [{ id: "n_rule", title: "No discounts", kind: "rule", topic: "", score: 1, why: "must hold" }],
    sections: [],
    related: [],
  },
};

const lanes = (open: unknown[] = []) => ({ lanes: { waiting_for_you: [], handed_off: [], working: [], blocked: [], open }, done_this_week: [], count: open.length });

const at = (tab = "") => ({ path: "/projects/:projectId", route: `/projects/foc_spring${tab ? `?tab=${tab}` : ""}` });

describe("Project · Context", () => {
  it("shows the objective, latest progress and timeline, kept notes, the packet, and a pending update beside the approved value", async () => {
    mockApi(base);
    renderAt(<ProjectPage />, at());
    expect(await screen.findByRole("heading", { name: "Spring launch" })).toBeInTheDocument();
    expect(screen.getByText("A launch page live by May")).toBeInTheDocument();
    expect(screen.getByText(/Copy approved, assets in review\./)).toBeInTheDocument();
    expect(screen.getByText("Book the photographer")).toBeInTheDocument();
    expect(screen.getByText("Kickoff held")).toBeInTheDocument();
    expect(screen.getByText("Never promise a discount in launch copy")).toBeInTheDocument();
    expect(screen.getByText("Warm, short sentences")).toBeInTheDocument();
    expect(screen.getByText("the launch")).toBeInTheDocument();
    expect(await screen.findByText("812 tokens")).toBeInTheDocument();
    expect(await screen.findByText("Spring numbers")).toBeInTheDocument();
    // The approved value and the proposal stand side by side.
    expect(await screen.findByText(/CURRENT · APPROVED/)).toBeInTheDocument();
    expect(screen.getAllByText("Registrations are at 214").length).toBeGreaterThan(0);
    const card = screen.getByRole("article", { name: "Proposal prp_9" });
    expect(within(card).getByText("PROPOSED · NOT APPROVED YET")).toBeInTheDocument();
    expect(within(card).getByText("Registrations are at 388")).toBeInTheDocument();
    // Example data never shows.
    expect(screen.queryByText(/Floor Notes/)).not.toBeInTheDocument();
  });

  it("posts a progress update that replaces where it stands", async () => {
    const calls = mockApi({ ...base, "POST /api/brain/projects/foc_spring/updates": { status: 201, body: { status: "recorded" } } });
    renderAt(<ProjectPage />, at());
    await userEvent.click(await screen.findByRole("button", { name: "Post an update" }));
    await userEvent.type(screen.getByLabelText("Progress update"), "Photographer booked");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/brain/projects/foc_spring/updates");
    expect(post?.body).toEqual({ summary: "Photographer booked", state: { current: "Photographer booked" } });
  });

  it("changes the objective with a reason", async () => {
    const calls = mockApi({ ...base, "PUT /api/brain/projects/foc_spring/objective": detail });
    renderAt(<ProjectPage />, at());
    await userEvent.click(await screen.findByRole("button", { name: "Change" }));
    const dialog = screen.getByRole("dialog", { name: "Change the objective" });
    const box = within(dialog).getByLabelText("Objective");
    await userEvent.clear(box);
    await userEvent.type(box, "A launch page live by April");
    await userEvent.type(within(dialog).getByLabelText("Why it changes"), "Moved up a month");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/api/brain/projects/foc_spring/objective");
    expect(put?.body).toEqual({ objective: "A launch page live by April", reason: "Moved up a month" });
  });

  it("saves what you tell it as a capture in the project and starts Distill", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/notes": { status: 201, body: { id: "n_new", title: "About Spring launch" } },
      "PUT /api/workspace/n_new/projects": { id: "n_new", projects: ["foc_spring"] },
      "POST /api/brain/distill/requests": { status: 201, body: { id: "task_7" } },
    });
    renderAt(<ProjectPage />, at());
    await userEvent.type(await screen.findByLabelText("Tell it about this project"), "The venue moved to Hall B.");
    await userEvent.click(screen.getByRole("button", { name: "Sort it" }));
    expect(await screen.findByText(/Saved as a capture in this project/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST" && c.path === "/api/notes")?.body).toEqual({ title: "About Spring launch", body: "The venue moved to Hall B." });
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ projects: ["foc_spring"] });
    const distill = calls.find((c) => c.method === "POST" && c.path === "/api/brain/distill/requests");
    expect((distill?.body as { item_ids: string[] }).item_ids).toEqual(["n_new"]);
    expect((distill?.body as { start: boolean }).start).toBe(true);
  });

  it("shows a failure when the project can't be read", async () => {
    mockApi({ "GET /api/brain/projects/foc_spring": { status: 404, body: { error: { code: "not_found", message: "The Brain follows no project foc_spring." } } } });
    renderAt(<ProjectPage />, at());
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Not found")).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

const job = {
  task_id: "task_31",
  title: "Draft the launch email",
  status: "failed",
  runner: "claude",
  run_id: "run_1",
  model: "model-from-cli",
  tokens: { tokens_in: 1200, tokens_out: 300 },
  cost: 0.0123,
  started_at: "2026-10-22T09:00:00Z",
  finished_at: "2026-10-22T09:02:00Z",
  outputs: [],
  proposals: ["prp_12"],
  why: "The CLI is not signed in.",
  asked_by: "Owner",
};

const CLIS = [
  { id: "claude", label: "Claude Code", models: [{ id: "sonnet", label: "Sonnet" }, { id: "haiku", label: "Haiku · cheaper" }], one_click: true },
  { id: "codex", label: "Codex CLI", models: [{ id: "gpt-5-mini", label: "GPT-5 mini · cheaper" }], one_click: false },
];

const flow = () => ({
  id: "wf_1",
  name: "Carousel",
  description: "",
  project: "foc_spring",
  schedule: { kind: "manual" },
  when: "Run now only",
  ai: false,
  steps: [
    { kind: "prompt", text: "Make the carousel", runner: "claude", model: "sonnet", gate: false, budget: {} },
    { kind: "connector", ask: "Queue it in Buffer", tools: ["mcp__buffer__create_post"], writes: true, runner: "claude", model: "haiku", gate: true, budget: {} },
  ],
  runner: "claude",
  output: { kind: "outputs" },
  enabled: true,
  timezone: "UTC",
  next_due_at: null,
  revision: 1,
  version: 1,
  created_at: "",
  updated_at: "",
  archived_at: null,
  last_run: null,
  running: false,
  budget: {},
});

const run = (over: Record<string, unknown> = {}) => ({
  id: "wfr_1",
  workflow_id: "wf_1",
  workflow: "Carousel",
  status: "running",
  trigger: "now",
  due_at: null,
  started_at: "2026-10-26T09:00:00Z",
  finished_at: null,
  step: 0,
  steps: [
    { index: 0, kind: "prompt", title: "", status: "done", runner: "claude", model: "sonnet", result: { title: "Carousel v1" }, used: { tokens: 4900, cost: 0.02 } },
    { index: 1, kind: "connector", title: "", status: "waiting", runner: "claude", model: "haiku", gate: true },
  ],
  revision: 1,
  request: "",
  note: "",
  version: 1,
  waiting: null,
  ...over,
});

const tasksApi = {
  ...base,
  "GET /api/skills": { skills: [{ name: "launch-email", category: "", description: "", triggers: [], artifacts: [], makes_files: false, files: 0, last_run: null, used_by: [], use: "run" }], waiting: [] },
  "GET /api/agents": [{ name: "editor" }],
  "GET /api/work/projects/foc_spring/timeline": [job],
  "GET /api/workflows": [],
  "GET /api/work/handoffs": lanes([
    {
      id: "T-4",
      row: "t-4",
      task: "Send the brief to the printer",
      goal: null,
      project: "foc_spring",
      for: null,
      milestone: false,
      owner: "you",
      owner_label: "You",
      tool: null,
      status: "open",
      status_words: "Open",
      due: "2026-10-30",
      evidence: [],
      card: {},
      created: "",
      updated: "",
      days_open: 1,
      since_update: 1,
    },
  ]),
};

describe("Project · Tasks", () => {
  it("starts a Work with AI job with the prompt, skill and agent, and shows the timeline and the project's to-dos", async () => {
    const calls = mockApi({ ...tasksApi, "POST /api/work/projects/foc_spring/ask": { status: 201, body: { task: { id: "task_32" }, run: { id: "run_2" } } } });
    renderAt(<ProjectPage />, at("tasks"));
    expect(await screen.findByText("Draft the launch email")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/model-from-cli/)).toBeInTheDocument();
    expect(screen.getByText(/\$0\.0123/)).toBeInTheDocument();
    expect(screen.getByText("Why it stopped: The CLI is not signed in.")).toBeInTheDocument();
    expect(screen.getByText(/prp_12/)).toBeInTheDocument();
    expect(await screen.findByText("Send the brief to the printer")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/work/handoffs?project=foc_spring")).toBe(true);

    await userEvent.type(screen.getByLabelText("What should the AI do"), "Draft the follow-up email");
    await userEvent.click(await screen.findByRole("button", { name: "launch-email" }));
    await userEvent.click(await screen.findByRole("button", { name: "editor" }));
    await userEvent.click(screen.getByRole("button", { name: "Send to Claude Code" }));
    expect(await screen.findByText(/Started\. It shows in the timeline below\./)).toBeInTheDocument();
    const ask = calls.find((c) => c.method === "POST" && c.path === "/api/work/projects/foc_spring/ask");
    expect(ask?.body).toEqual({ prompt: "Draft the follow-up email", skill: "launch-email", agent: "editor", runner: "claude", model: null });
  });

  it("runs a job on another CLI and model, and says where the prompt and context go", async () => {
    const clis = [
      { id: "claude", label: "Claude Code", models: [{ id: "haiku", label: "Haiku · cheaper" }], one_click: true },
      { id: "codex", label: "Codex CLI", models: [{ id: "gpt-5-mini", label: "GPT-5 mini · cheaper" }], one_click: false },
    ];
    const calls = mockApi({
      ...tasksApi,
      "GET /api/projects/foc_spring/orchestrators": { orchestrators: [], agent_tasks: [], clis, works_by: [] },
      "POST /api/work/projects/foc_spring/ask": { status: 201, body: { task: { id: "task_33" }, run: { id: "run_3" } } },
    });
    renderAt(<ProjectPage />, at("tasks"));
    await userEvent.click(await screen.findByRole("button", { name: "Codex CLI" }));
    expect(screen.getByText(/Codex CLI sends this prompt and the project's context to OpenAI\. It has no tools here/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Model"), "gpt-5-mini");
    await userEvent.type(screen.getByLabelText("What should the AI do"), "Rewrite the launch copy");
    await userEvent.click(screen.getByRole("button", { name: "Send to Codex CLI" }));
    await screen.findByText(/Started\./);
    const ask = calls.find((c) => c.method === "POST" && c.path === "/api/work/projects/foc_spring/ask");
    expect(ask?.body).toMatchObject({ prompt: "Rewrite the launch copy", runner: "codex", model: "gpt-5-mini" });
  });

  it("saves a Work with AI prompt as step 1 of a workflow, adds a step on Codex, and saves it for the project", async () => {
    const calls = mockApi({
      ...tasksApi,
      "GET /api/projects/foc_spring/orchestrators": { orchestrators: [], agent_tasks: [], clis: CLIS, works_by: [] },
      "GET /api/workflows": [],
      "POST /api/workflows": { status: 201, body: flow() },
    });
    renderAt(<ProjectPage />, at("tasks"));
    await userEvent.type(await screen.findByLabelText("What should the AI do"), "Make the carousel");
    await userEvent.click(screen.getByRole("button", { name: "Save as workflow" }));
    expect(await screen.findByLabelText("Step 1 what it does")).toHaveValue("Make the carousel");
    await userEvent.type(screen.getByLabelText("Workflow name"), "Carousel");
    await userEvent.click(screen.getByRole("button", { name: "Add a step" }));
    const second = screen.getByRole("group", { name: "Step 2" });
    await userEvent.type(within(second).getByLabelText("Step 2 what it does"), "Rewrite the copy with my rules");
    await userEvent.click(within(second).getByRole("button", { name: "Codex CLI" }));
    await userEvent.selectOptions(within(second).getByLabelText("Step 2 model"), "gpt-5-mini");
    expect(within(second).getByText(/sends them to OpenAI\. It has no tools/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/workflows")).toBe(true));
    const saved = calls.find((c) => c.method === "POST" && c.path === "/api/workflows")?.body as { project: string; name: string; steps: Record<string, unknown>[] };
    expect(saved.project).toBe("foc_spring");
    expect(saved.name).toBe("Carousel");
    expect(saved.steps.map((s) => [s.kind, s.text, s.runner, s.model])).toEqual([
      ["prompt", "Make the carousel", "claude", null],
      ["prompt", "Rewrite the copy with my rules", "codex", "gpt-5-mini"],
    ]);
  });

  it("makes a step that sends outside wait for your yes, always", async () => {
    mockApi({ ...tasksApi, "GET /api/projects/foc_spring/orchestrators": { orchestrators: [], agent_tasks: [], clis: CLIS, works_by: [] }, "GET /api/workflows": [] });
    renderAt(<ProjectPage />, at("tasks"));
    await userEvent.click(await screen.findByRole("button", { name: "New workflow" }));
    await userEvent.selectOptions(screen.getByLabelText("Step 1 kind"), "connector");
    await userEvent.click(screen.getByLabelText("It sends or changes something outside"));
    const gate = screen.getByLabelText(/Wait for my yes before this step/);
    expect(gate).toBeChecked();
    expect(gate).toBeDisabled();
  });

  it("shows the latest run's steps with their AI and cost, says yes at a gate, and retries a failed step", async () => {
    const waiting = run({
      status: "waiting",
      step: 1,
      waiting: { step: 1, ask: "Step 2 acts outside Gnomon with mcp__buffer__create_post: what it sends cannot be undone. Say yes to let it run.", result: null, gate: true },
    });
    const calls = mockApi({
      ...tasksApi,
      "GET /api/projects/foc_spring/orchestrators": { orchestrators: [], agent_tasks: [], clis: CLIS, works_by: [] },
      "GET /api/workflows": [flow()],
      "GET /api/workflows/wf_1/runs": [waiting],
      "POST /api/workflows/runs/wfr_1/decide": run({ status: "running", step: 1 }),
    });
    renderAt(<ProjectPage />, at("tasks"));
    const latest = await screen.findByRole("generic", { name: "Latest run of Carousel" });
    expect(within(latest).getByText(/Claude Code · sonnet/)).toBeInTheDocument();
    expect(within(latest).getByText("4,900 tokens · $0.02")).toBeInTheDocument();
    expect(within(latest).getByText(/cannot be undone/)).toBeInTheDocument();
    await userEvent.click(within(latest).getByRole("button", { name: "Yes, go on" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/workflows/runs/wfr_1/decide")?.body).toEqual({ go: true }));
  });

  it("retries a failed step on the same AI", async () => {
    const failed = run({
      status: "failed",
      step: 1,
      note: "Step 2 failed.",
      steps: [
        { index: 0, kind: "prompt", title: "", status: "done", runner: "claude", model: "sonnet", result: { title: "Carousel v1" } },
        { index: 1, kind: "connector", title: "", status: "failed", runner: "claude", model: "haiku", note: "Its task failed." },
      ],
    });
    const calls = mockApi({
      ...tasksApi,
      "GET /api/projects/foc_spring/orchestrators": { orchestrators: [], agent_tasks: [], clis: CLIS, works_by: [] },
      "GET /api/workflows": [flow()],
      "GET /api/workflows/wf_1/runs": [failed],
      "POST /api/workflows/runs/wfr_1/retry": run({ status: "running", step: 1 }),
    });
    renderAt(<ProjectPage />, at("tasks"));
    await userEvent.click(await screen.findByRole("button", { name: "Retry step 2" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/workflows/runs/wfr_1/retry")).toBe(true));
  });

  it("adds a task to the project's Tasks sheet", async () => {
    const calls = mockApi({ ...tasksApi, "POST /api/work/handoffs": { task: { id: "T-5" } } });
    renderAt(<ProjectPage />, at("tasks"));
    await userEvent.type(await screen.findByLabelText("New task"), "Order the banners");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/work/handoffs");
    expect(post?.body).toEqual({ new_task: { title: "Order the banners", project: "foc_spring" } });
  });

  it("says so when there is no AI work and no task yet", async () => {
    mockApi({ ...tasksApi, "GET /api/work/projects/foc_spring/timeline": [], "GET /api/work/handoffs": lanes() });
    renderAt(<ProjectPage />, at("tasks"));
    expect(await screen.findByText("No AI work here yet")).toBeInTheDocument();
    expect(await screen.findByText(/No tasks yet\. Pull them from a meeting in Capture/)).toBeInTheDocument();
  });
});

describe("Project · Files and Outputs", () => {
  it("lists the project's sources with where each one stands", async () => {
    mockApi({
      ...base,
      "GET /api/notes": [{ id: "n_1", title: "Kickoff call", body: null, projects: ["foc_spring"], capture: "recording", created_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-20T10:00:00Z" }],
      "GET /api/captures/status": { n_1: { item_id: "n_1", status: "awaiting_review", label: "Waiting for review", stage: "review", detail: "2 pieces wait", can_retry: false, waiting: 2, kept: 0, skipped: 0, searchable: 0, task_id: null, proposal_ids: [] } },
    });
    renderAt(<ProjectPage />, at("files"));
    expect(await screen.findByText("Kickoff call")).toBeInTheDocument();
    expect(await screen.findByText("Waiting for review")).toBeInTheDocument();
    expect(screen.getByText("Spring brief")).toBeInTheDocument();
    expect(screen.getByText("Searchable · 4 sections")).toBeInTheDocument();
  });

  it("shows outputs as drafts, and what one was made from", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/work/projects/foc_spring/timeline": [],
      "GET /api/outputs": {
        root: "",
        folders: [],
        files: [
          { path: "spring/email.md", name: "email.md", folder: "spring", size: 10, modified: "2026-10-22T10:00:00Z", kind: "document", from: "skill", working: false, project: "foc_spring", title: "Launch email" },
          { path: "other/x.md", name: "x.md", folder: "other", size: 10, modified: "2026-10-22T10:00:00Z", kind: "document", from: null, working: false, project: "foc_other", title: "Not this project" },
        ],
      },
      "GET /api/outputs/made-from": {
        path: "spring/email.md",
        how: "skill",
        skill_run: { task_id: "task_31", skill: "launch-email", ask: "Draft it", project: "foc_spring", attached: [], capture: null, status: "succeeded", created_at: "", runs: [] },
        given: [{ id: "pk_5", pieces: [{ kind: "note", id: "n_rule", tokens: 20, why: "", title: "No discounts", version: 3 }] }],
      },
    });
    renderAt(<ProjectPage />, at("outputs"));
    expect(await screen.findByText("Launch email")).toBeInTheDocument();
    expect(screen.queryByText("Not this project")).not.toBeInTheDocument();
    expect(screen.getByText("Draft · not saved to Brain")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Made from" }));
    expect(await screen.findByText(/Skill launch-email, asked: “Draft it”/)).toBeInTheDocument();
    expect(screen.getByText("No discounts · version 3")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/outputs/made-from?path=spring%2Femail.md")).toBe(true);
  });

  it("says so when the project has no outputs", async () => {
    mockApi({ ...base, "GET /api/work/projects/foc_spring/timeline": [], "GET /api/outputs": { root: "", folders: [], files: [] } });
    renderAt(<ProjectPage />, at("outputs"));
    expect(await screen.findByText(/No outputs yet\./)).toBeInTheDocument();
  });
});

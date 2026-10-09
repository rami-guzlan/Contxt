// Workflows: each drawn as a strip of boxes and run now; built from a template or from nothing,
// with its schedule and steps; and a run that reaches a check waits for a yes, an edit, or a stop.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { NewWorkflowPage, WorkflowPage, WorkflowsPage } from "./Workflows";

afterEach(() => vi.restoreAllMocks());

const at = "2026-10-09T10:00:00Z";
const steps = [
  { kind: "skill", skill: "weekly-posts", ask: "Three posts.", docs: [], library: [], meetings: 0 },
  { kind: "check", ask: "Read them first." },
  { kind: "prompt", prompt_id: null, text: "One blurb from the posts.", skills: [], docs: [], library: [], meetings: 0 },
];
const workflow = {
  id: "wf_1",
  name: "Weekly posts",
  description: "Posts for the week, read before they are kept.",
  project: null,
  schedule: { kind: "weekly", days: ["mon"], time: "09:00" },
  when: "Every Monday at 09:00 (America/New_York)",
  ai: false,
  steps,
  runner: "claude",
  output: { kind: "outputs" },
  enabled: true,
  timezone: "America/New_York",
  next_due_at: "2026-10-12T13:00:00.000000Z",
  revision: 2,
  version: 2,
  created_at: at,
  updated_at: at,
  archived_at: null,
  last_run: { id: "wfr_1", status: "waiting", trigger: "schedule", started_at: at, finished_at: null, note: "", step: 1, steps: ["done", "waiting", "pending"] },
  running: true,
};
const waitingRun = {
  id: "wfr_1",
  workflow_id: "wf_1",
  workflow: "Weekly posts",
  status: "waiting",
  trigger: "schedule",
  due_at: null,
  started_at: at,
  finished_at: null,
  step: 1,
  steps: [
    { index: 0, kind: "skill", title: "", status: "done", task_id: "task_1", result: { artifact_id: "art_1", version: 1, title: "Poll posts", excerpt: "Post one." } },
    { index: 1, kind: "check", title: "", status: "waiting", ask: "Read them first." },
    { index: 2, kind: "prompt", title: "", status: "pending" },
  ],
  revision: 2,
  request: "",
  note: "",
  version: 3,
  waiting: { step: 1, ask: "Read them first.", result: { artifact_id: "art_1", version: 1, title: "Poll posts", excerpt: "Post one." } },
};
const templates = [
  {
    id: "weekly-upkeep",
    name: "Weekly Brain upkeep",
    description: "Every Monday the knowledge agent tidies the Brain.",
    schedule: { kind: "weekly", days: ["mon"], time: "08:00" },
    steps: [
      { kind: "upkeep", action: "tidy-repeats" },
      { kind: "upkeep", action: "freshen-up" },
    ],
    output: { kind: "outputs" },
  },
];
const agent = {
  model: "claude",
  suggestions: true,
  actions: [
    { id: "tidy-repeats", label: "Find repeats", blurb: "Notes that say the same thing." },
    { id: "freshen-up", label: "Freshen up", blurb: "Stale notes." },
  ],
  questions: [],
  runs: [],
  models: [],
  working: [],
};
const base = {
  "GET /api/brain/agent": agent,
  "GET /api/workflows/templates": templates,
  "GET /api/workflows/waiting": [],
  "GET /api/brain/projects": [],
  "GET /api/notes": [],
  "GET /api/brain/files": { references: [], assets: [], skills: [] },
  "GET /api/skills": { skills: [{ name: "weekly-posts", description: "Posts.", use: "run", category: "social", triggers: [], artifacts: [], makes_files: false, files: 1, last_run: null, used_by: [] }], waiting: [] },
  "GET /api/agents": [],
  "GET /api/prompts": [],
};

describe("Workflows", () => {
  it("draws each workflow as boxes, lists what waits for you, and runs one now", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/workflows": [{ ...workflow, running: false, last_run: { ...workflow.last_run, status: "done", steps: ["done", "done", "done"] } }],
      "GET /api/workflows/waiting": [waitingRun],
      "POST /api/workflows/wf_1/run": { status: 201, body: { ...waitingRun, status: "running", waiting: null } },
    });
    const user = userEvent.setup();
    renderAt(<WorkflowsPage />, { path: "/work/workflows", route: "/work/workflows" });
    const mine = await screen.findByRole("list", { name: "Your workflows" });
    const strip = within(mine).getByRole("list", { name: "Its steps" });
    expect(within(strip).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Every Monday at 09:00 (America/New_York)",
      "Skill/weekly-posts",
      "Your checkRead them first.",
      "PromptOne blurb from the posts.",
      "Outputs",
    ]);
    expect(within(screen.getByRole("list", { name: "Runs waiting for you" })).getByRole("link", { name: "Weekly posts" })).toHaveAttribute("href", "/work/workflows/wf_1?run=wfr_1");
    expect(screen.getByRole("link", { name: "Start from this" })).toHaveAttribute("href", "/work/workflows/new?template=weekly-upkeep");
    await user.click(within(mine).getByRole("button", { name: "Run now" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/workflows/wf_1/run")).toBe(true));
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("builds a new workflow from a template, with its schedule and steps", async () => {
    const calls = mockApi({ ...base, "POST /api/workflows": { status: 201, body: { ...workflow, id: "wf_2" } } });
    const user = userEvent.setup();
    renderAt(<NewWorkflowPage />, { path: "/work/workflows/new", route: "/work/workflows/new?template=weekly-upkeep" });
    expect(await screen.findByDisplayValue("Weekly Brain upkeep")).toBeInTheDocument();
    expect(screen.getByLabelText("How often")).toHaveValue("weekly");
    expect(screen.getByLabelText("At")).toHaveValue("08:00");
    await user.click(screen.getByRole("button", { name: /Your check/ }));
    await user.click(screen.getByRole("button", { name: "Save the workflow" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/workflows")?.body).toMatchObject({
        name: "Weekly Brain upkeep",
        schedule: { kind: "weekly", days: ["mon"], time: "08:00" },
        steps: [
          { kind: "upkeep", action: "tidy-repeats" },
          { kind: "upkeep", action: "freshen-up" },
          { kind: "check", ask: "Read what the step before made." },
        ],
        runner: "claude",
        output: { kind: "outputs" },
        enabled: true,
      }),
    );
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("names a connector step's tools, one per line", async () => {
    const calls = mockApi({ ...base, "POST /api/workflows": { status: 201, body: { ...workflow, id: "wf_3" } } });
    const user = userEvent.setup();
    renderAt(<NewWorkflowPage />, { path: "/work/workflows/new", route: "/work/workflows/new" });
    await user.type(await screen.findByLabelText("Its name"), "Deals");
    await user.click(screen.getByRole("button", { name: /Connector/ }));
    await user.type(screen.getByLabelText("What to find"), "This week's new deals.");
    await user.type(screen.getByLabelText(/The tools it may use/), "mcp__hubspot__search_crm_objects{Enter}mcp__hubspot__get_crm_objects");
    await user.click(screen.getByRole("button", { name: "Save the workflow" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
        name: "Deals",
        schedule: { kind: "manual" },
        steps: [{ kind: "connector", ask: "This week's new deals.", tools: ["mcp__hubspot__search_crm_objects", "mcp__hubspot__get_crm_objects"], writes: false }],
      }),
    );
  });

  it("waits at a check for a yes, an edit, or a stop", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/workflows/wf_1": workflow,
      "GET /api/workflows/wf_1/runs": [waitingRun],
      "GET /api/workflows/runs/wfr_1/steps/0": { title: "Poll posts", text: "Post one.\nPost two.", version: 1, artifact_id: "art_1" },
      "POST /api/workflows/runs/wfr_1/decide": { ...waitingRun, status: "running", step: 2, waiting: null },
    });
    const user = userEvent.setup();
    renderAt(<WorkflowPage />, { path: "/work/workflows/:id", route: "/work/workflows/wf_1?run=wfr_1" });
    const check = await screen.findByRole("region", { name: "Your check" });
    expect(within(check).getByRole("heading")).toHaveTextContent("Your check: Read them first.");
    expect(await within(check).findByText(/Post two\./)).toBeInTheDocument();
    await user.click(within(check).getByRole("button", { name: "Edit it first" }));
    const box = within(check).getByLabelText("Edit it before it goes on");
    await user.clear(box);
    await user.type(box, "Post one, shorter.");
    await user.click(within(check).getByRole("button", { name: "Go on with my edit" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/workflows/runs/wfr_1/decide")?.body).toEqual({ go: true, edit: "Post one, shorter.", note: "" }),
    );
  });
});

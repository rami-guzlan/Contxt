// One project: Context (objective, progress, kept notes, packet, pending updates beside the
// approved value, telling it about the project), Tasks (Work with AI, the job timeline, the
// project's to-dos), Files with their source status, and Outputs as drafts with what they were
// made from. All from the API; each action calls its endpoint with the right body.

import { screen, within } from "@testing-library/react";
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

const tasksApi = {
  ...base,
  "GET /api/skills": { skills: [{ name: "launch-email", category: "", description: "", triggers: [], artifacts: [], makes_files: false, files: 0, last_run: null, used_by: [], use: "run" }], waiting: [] },
  "GET /api/agents": [{ name: "editor" }],
  "GET /api/work/projects/foc_spring/timeline": [job],
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
    expect(ask?.body).toEqual({ prompt: "Draft the follow-up email", skill: "launch-email", agent: "editor" });
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

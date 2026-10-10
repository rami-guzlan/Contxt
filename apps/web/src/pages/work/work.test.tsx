// Work: the frame and its tabs, the overview of its parts, and each part as it lands.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { NewWorkAgentPage, WorkAgentPage, WorkAgentsPage } from "./Agents";
import { LibraryItemPage, LibraryPage } from "./Library";
import { WorkOverviewPage } from "./Overview";
import { WorkLayout } from "./WorkLayout";
import { WorkspaceDocPage, WorkspacePage } from "./Workspace";

afterEach(() => vi.restoreAllMocks());

// jsdom cannot run ProseMirror: the doc's editor is a plain text box here.
vi.mock("../../components/RichEditor", () => ({
  default: ({ markdown, label, onChange }: { markdown: string; label: string; onChange: (text: string) => void }) => (
    <textarea aria-label={label} defaultValue={markdown} onChange={(event) => onChange(event.target.value)} />
  ),
}));

const skills = {
  skills: [
    {
      name: "weekly-posts",
      description: "Three LinkedIn posts for the week.",
      category: "social",
      triggers: ["weekly posts"],
      use: "run",
      used_by: [],
      artifacts: ["post"],
      makes_files: false,
      files: 1,
      last_run: null,
    },
  ],
  waiting: [{ name: "one-pager", id: "p_1" }],
};

// What the overview reads besides the parts' own lists: the Brain's changes, its health and what
// waits in Catch up.
const governance = {
  "GET /api/brain/status": { available: true, principal: "person:ana" },
  "GET /api/brain/activity": [],
  "GET /api/brain/attention": { clashes: [], twins: [], flagged: [], recheck: [], usage: {}, days: 7 },
  "GET /api/brain/catch-up": { caught_up: true, seconds: 0 },
  "GET /api/work/attention": { stale_skills: [], broken_agents: [] },
  "GET /api/skills/suggestions": { suggestions: [], matched_by: "words" },
  "GET /api/brain/agent": { model: "claude", suggestions: true, actions: [], questions: [], runs: [], models: [], working: [] },
};

describe("Knowledge Work", () => {
  it("frames its parts as tabs, with what waits for a yes on Skills", async () => {
    mockApi({
      "GET /api/brain/status": { available: true },
      "GET /api/skills": skills,
      "GET /api/library": [],
      "GET /api/agents": [],
      "GET /api/workflows": [],
      "GET /api/workflows/waiting": [],
    });
    renderAt(<WorkLayout />, { path: "/work", route: "/work" });
    const tabs = await screen.findByRole("navigation", { name: "Knowledge Work sections" });
    expect(within(tabs).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual([
      "/work",
      "/work/workspace",
      "/work/library",
      "/work/prompts",
      "/work/skills",
      "/work/agents",
      "/work/workflows",
      "/work/outputs",
    ]);
    expect(within(tabs).getByRole("link", { name: /Skills/ })).toHaveTextContent("1");
    expect(screen.getByRole("heading", { level: 1, name: "Knowledge Work" })).toBeInTheDocument();
    expect(screen.getByText("Shape what your Brain knows and keep it current.")).toBeInTheDocument();
  });

  it("leads with what changed, what waits and how healthy the context is, then its parts", async () => {
    mockApi({
      ...governance,
      "GET /api/brain/activity": [
        { at: "2026-10-09T10:00:00Z", action: "auto-applied", by: "person:ana", proposer: "person:ana", note: "voice", title: "Our voice" },
        { at: "2026-10-09T09:00:00Z", action: "approved", by: "person:ana", proposer: "claude-code", note: "pricing", title: "Pricing" },
      ],
      "GET /api/brain/attention": {
        clashes: [],
        twins: [],
        flagged: [],
        recheck: [{ id: "pricing", title: "Pricing", why: "past its review date" }],
        usage: {},
        days: 7,
      },
      "GET /api/brain/catch-up": { caught_up: false, seconds: 120 },
      "GET /api/skills": skills,
      "GET /api/outputs": { root: "C:/home/outputs", folders: [], files: [] },
      "GET /api/skills/runs": [],
      "GET /api/library": [],
      "GET /api/agents": [],
      "GET /api/workspace/items": { items: [], projects: [] },
      "GET /api/prompts": [],
      "GET /api/workflows": [],
      "GET /api/workflows/waiting": [],
    });
    renderAt(<WorkOverviewPage />, { path: "/work", route: "/work" });
    const changed = await screen.findByRole("list", { name: "What changed" });
    expect(within(changed).getByRole("link", { name: "Our voice" })).toBeInTheDocument();
    expect(within(changed).getByText(/added by you/)).toBeInTheDocument();
    expect(within(changed).getByText(/suggested by your AI, kept by you/)).toBeInTheDocument();
    const waiting = await screen.findByRole("list", { name: "Waiting for you" });
    expect(within(waiting).getByRole("link", { name: "Catch up" })).toHaveAttribute("href", "/catch-up");
    expect(within(waiting).getByRole("link", { name: "/one-pager" })).toHaveAttribute("href", "/review");
    const health = await screen.findByRole("list", { name: "Context health" });
    expect(within(health).getByRole("link", { name: "1 note to recheck" })).toBeInTheDocument();
    const parts = screen.getByRole("list", { name: "The parts of Knowledge Work" });
    expect(within(parts).getAllByRole("heading").map((h) => h.textContent)).toEqual([
      "Workspace",
      "Library",
      "Prompts",
      "Skills",
      "Agents",
      "Workflows",
      "Outputs",
    ]);
    expect(within(parts).getByRole("link", { name: "Skills" })).toHaveAttribute("href", "/work/skills");
    expect(await within(parts).findByText("1 skill")).toBeInTheDocument();
    // Nothing made yet: the way in, one step at a time.
    const start = screen.getByRole("list", { name: "Start here" });
    expect(within(start).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual([
      "/work/library",
      "/work/skills?new=1",
      "/work/agents/new",
      "/work/workflows/new",
    ]);
  });

  it("shows the agents with each heartbeat, the flows, and what may be out of date", async () => {
    const flow = {
      id: "wf_1",
      name: "Case study every month",
      description: "",
      project: null,
      schedule: { kind: "monthly", day: 1, time: "09:00" },
      when: "Monthly on day 1 at 09:00 (America/New_York)",
      ai: false,
      steps: [{ kind: "agent", agent: "case-writer", ask: "This month's case study." }],
      runner: "claude",
      output: { kind: "outputs" },
      enabled: true,
      timezone: "America/New_York",
      next_due_at: "2026-11-01T13:00:00.000000Z",
      revision: 1,
      version: 1,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
      archived_at: null,
      last_run: null,
      running: false,
    };
    mockApi({
      ...governance,
      "GET /api/skills": { ...skills, waiting: [] },
      "GET /api/outputs": { root: "C:/home/outputs", folders: [], files: [] },
      "GET /api/skills/runs": [],
      "GET /api/library": [],
      "GET /api/agents": [{ ...writer, last_run: null }],
      "GET /api/workspace/items": { items: [], projects: [] },
      "GET /api/prompts": [],
      "GET /api/workflows": [flow],
      "GET /api/workflows/waiting": [],
      "GET /api/work/attention": { stale_skills: [{ name: "weekly-posts", last_edited: null, changed: [{ key: "brand/voice", title: "brand/voice", at: "2026-10-05T10:00:00Z" }] }], broken_agents: [{ name: "case-writer", broken: ["/gone-skill"] }] },
    });
    renderAt(<WorkOverviewPage />, { path: "/work", route: "/work" });
    const team = await screen.findByRole("list", { name: "Your agents" });
    expect(await within(team).findByRole("link", { name: "case-writer" })).toHaveAttribute("href", "/work/agents/case-writer");
    expect(within(team).getByText("Idle")).toBeInTheDocument();
    expect(within(team).getByText(/next/)).toBeInTheDocument();
    expect(within(team).getByRole("link", { name: "New agent" })).toHaveAttribute("href", "/work/agents/new");
    expect(screen.queryByRole("list", { name: "Start here" })).not.toBeInTheDocument();
    const flows = screen.getByRole("list", { name: "Your workflows" });
    expect(within(flows).getByRole("link", { name: "Case study every month" })).toHaveAttribute("href", "/work/workflows/wf_1");
    const health = await screen.findByRole("list", { name: "Context health" });
    expect(within(health).getByRole("link", { name: "/weekly-posts" })).toHaveAttribute("href", "/work/skills/weekly-posts");
    expect(within(health).getByText(/points to what is gone: \/gone-skill/)).toBeInTheDocument();
    expect(screen.getByText("Nothing waits for you.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Nothing changed in your Brain since/)).toBeInTheDocument();
  });
});

const guide = {
  path: "references/release-notes.md",
  title: "How we write release notes",
  kind: "guide",
  summary: "Lead with what changed for the customer.",
  entry_id: "card-release-notes",
  source_url: null,
  source_repo: null,
  source_paths: [],
  fetched_at: null,
  refresh: "never",
  updated: "2026-10-09T10:00:00Z",
  dated: "2026-10-09",
  version: 1,
  size: 120,
  original: null,
  project: null,
  project_title: null,
  used_by: { skills: ["weekly-posts"] },
};
const influence = {
  ...guide,
  path: "references/acme-site.md",
  title: "acme/site",
  kind: "influence",
  summary: "Our marketing site.",
  entry_id: "card-acme",
  source_repo: "https://github.com/acme/site",
  source_paths: ["src/Button.tsx"],
  fetched_at: "2026-10-01",
  refresh: "monthly",
  used_by: { skills: [] },
};

describe("the Library", () => {
  it("lists what good looks like by kind, with where each came from and what uses it", async () => {
    mockApi({ "GET /api/library": [guide, influence] });
    const user = userEvent.setup();
    renderAt(<LibraryPage />, { path: "/work/library", route: "/work/library" });
    const list = await screen.findByRole("list", { name: "Library" });
    expect(within(list).getByRole("link", { name: "How we write release notes" })).toHaveAttribute(
      "href",
      "/work/library/view?path=references%2Frelease-notes.md",
    );
    expect(within(list).getByText(/used by 1 skill or agent/)).toBeInTheDocument();
    expect(within(list).getByText(/from acme\/site/)).toHaveTextContent("every month");
    await user.click(screen.getByRole("button", { name: /Influences/ }));
    expect(within(screen.getByRole("list", { name: "Library" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("fetches a page and keeps it, as the kind chosen", async () => {
    const calls = mockApi({
      "GET /api/library": [],
      "POST /api/library/url": { status: "applied", message: "Filed.", path: "references/sourdough.md" },
    });
    const user = userEvent.setup();
    renderAt(<LibraryPage />, { path: "/work/library", route: "/work/library" });
    await user.click(await screen.findByRole("button", { name: "Add to the Library" }));
    await user.type(screen.getByLabelText("The page's address"), "https://example.org/sourdough");
    await user.selectOptions(screen.getByLabelText("Fetch it again"), "weekly");
    await user.click(screen.getByRole("button", { name: "Fetch and keep" }));
    expect(await screen.findByRole("link", { name: "Open it" })).toHaveAttribute("href", "/work/library/view?path=references%2Fsourdough.md");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ url: "https://example.org/sourdough", kind: "reference", refresh: "weekly" });
  });

  it("shows an item whole, and changes its kind and fetches it again", async () => {
    const calls = mockApi({
      "GET /api/library/item": { ...influence, text: "# acme/site\n\nPlain words, short pages.", checked_at: "2026-10-08T09:00:00Z" },
      "PUT /api/library/item": { ...influence, kind: "guide" },
      "POST /api/library/refresh": { status: "unchanged", message: "", path: influence.path, proposal_id: null },
    });
    const user = userEvent.setup();
    renderAt(<LibraryItemPage />, { path: "/work/library/view", route: "/work/library/view?path=references%2Facme-site.md" });
    expect(await screen.findByText("Plain words, short pages.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://github.com/acme/site" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Kind"), "guide");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ path: "references/acme-site.md", kind: "guide" });
    await user.click(screen.getByRole("button", { name: "Fetch it again now" }));
    expect(await screen.findByText("Nothing changed since it was fetched.")).toBeInTheDocument();
  });

  it("keeps assets beside documents, each saying where it came from and whose it is", async () => {
    const logo = {
      ...guide,
      path: "assets/brand/logo.png",
      title: "Logo",
      kind: "asset",
      file_kind: "asset",
      mime: "image/png",
      origin: "capture:document",
      origin_inferred: false,
      scope: "company",
      used_by: { skills: [] },
    };
    mockApi({ "GET /api/library": [{ ...guide, origin: "library", origin_inferred: false }, logo] });
    const user = userEvent.setup();
    renderAt(<LibraryPage />, { path: "/work/library", route: "/work/library" });
    const list = await screen.findByRole("list", { name: "Library" });
    expect(within(list).getAllByText("Yours")).toHaveLength(2);
    expect(within(list).getByText(/from capture: an uploaded document/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Assets/ }));
    const assets = within(screen.getByRole("list", { name: "Library" })).getAllByRole("listitem");
    expect(assets).toHaveLength(1);
    expect(within(assets[0] as HTMLElement).getByRole("link", { name: "Logo" })).toHaveAttribute(
      "href",
      "/work/library/view?path=assets%2Fbrand%2Flogo.png",
    );
  });

  it("shows an asset as itself and lets an older file say where it came from", async () => {
    const calls = mockApi({
      "GET /api/library/item": {
        ...guide,
        path: "assets/brand/logo.png",
        title: "Logo",
        kind: "asset",
        file_kind: "asset",
        mime: "image/png",
        origin: null,
        origin_inferred: false,
        scope: null,
        text: null,
        checked_at: null,
      },
      "PUT /api/library/item": { ...guide, origin: "capture:export" },
    });
    const user = userEvent.setup();
    renderAt(<LibraryItemPage />, { path: "/work/library/view", route: "/work/library/view?path=assets%2Fbrand%2Flogo.png" });
    expect(await screen.findByRole("img", { name: "Logo" })).toHaveAttribute("src", "/api/brain/files/content?path=assets%2Fbrand%2Flogo.png");
    expect(screen.getByLabelText("Kind")).toBeDisabled(); // an asset is an asset
    expect(screen.getByText("Not known")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Set where it came from"), "capture:export");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ path: "assets/brand/logo.png", origin: "capture:export" });
  });
});

const writer = {
  name: "case-writer",
  role: "Writes the studio's case studies from finished projects.",
  responsibilities: ["Draft one case study a month"],
  goals: [],
  projects: [],
  skills: ["weekly-posts"],
  library: ["references/release-notes.md"],
  context: ["brand/voice"],
  meetings_days: 14,
  boundaries: ["Never publish, send or post anything: leave drafts for the owner."],
  output: "outputs",
  output_shape: "A one-page case study.",
  runner: "claude",
  review: true,
  scope: "",
  status: "active",
  prompt: "You write case studies.",
  path: "agents/case-writer/AGENT.md",
  last_run: { task_id: "t1", status: "done", at: "2026-10-09T09:00:00Z" },
};
const writerFull = {
  agent: writer,
  resolved: {
    skills: [{ name: "weekly-posts", missing: false, description: "Three posts." }],
    library: [{ path: "references/release-notes.md", title: "How we write release notes", missing: false }],
    context: [{ key: "brand/voice", missing: false }],
    projects: [],
    broken: ["/gone-skill"],
  },
  prompt: "# You are working as case-writer\n\nWrites the studio's case studies.",
};
const pickers = {
  "GET /api/skills": skills,
  "GET /api/library": [guide],
  "GET /api/brain/projects": [],
  "GET /api/brain/catalog": { areas: [{ key: "brand", label: "Brand", description: "", topics: [{ key: "brand/voice", label: "Voice", description: "", entries: 2 }] }], entries: [] },
};

describe("Agents", () => {
  it("shows the team as faces, roles and what each points to", async () => {
    mockApi({ "GET /api/agents": [writer] });
    renderAt(<WorkAgentsPage />, { path: "/work/agents", route: "/work/agents" });
    const roster = await screen.findByRole("list", { name: "Agents" });
    expect(within(roster).getByRole("link", { name: "case-writer" })).toHaveAttribute("href", "/work/agents/case-writer");
    expect(within(roster).getByText("CW")).toBeInTheDocument();
    expect(within(roster).getByText("1 skill")).toBeInTheDocument();
    expect(within(roster).getByText("meetings, 14 days")).toBeInTheDocument();
    expect(within(roster).getByText(/last asked/)).toBeInTheDocument();
  });

  it("has the model write a new agent's prompt from the role, then saves the whole role", async () => {
    const calls = mockApi({
      ...pickers,
      "POST /api/agents/prompt": { id: "ajob_1", kind: "agent-prompt", status: "waiting", result: {}, error: null },
      "GET /api/brain/agent/jobs/ajob_1": {
        id: "ajob_1",
        kind: "agent-prompt",
        status: "done",
        result: { prompt: "You plan one case study a month.", questions: ["Which projects count as finished?"] },
        error: null,
      },
      "POST /api/agents": writerFull,
    });
    const user = userEvent.setup();
    renderAt(<NewWorkAgentPage />, { path: "/work/agents/new", route: "/work/agents/new" });
    await user.type(await screen.findByLabelText("What it does, in a line"), "Writes case studies");
    expect(screen.getByLabelText("Its name")).toHaveValue("case-studies");
    await user.clear(screen.getByLabelText("Its name"));
    await user.type(screen.getByLabelText("Its name"), "case-writer");
    await user.click(screen.getByRole("button", { name: "Write it with your AI" }));
    expect(await screen.findByDisplayValue("You plan one case study a month.")).toBeInTheDocument();
    expect(screen.getByText("Which projects count as finished?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save the agent" }));
    const saved = calls.find((c) => c.method === "POST" && c.path === "/api/agents");
    expect(saved?.body).toMatchObject({ name: "case-writer", role: "Writes case studies", prompt: "You plan one case study a month.", output: "outputs", review: true });
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("asks an agent for something and shows what it gets, naming what no longer resolves", async () => {
    const calls = mockApi({
      ...pickers,
      "GET /api/agents/case-writer": writerFull,
      "GET /api/agents/case-writer/runs": [],
      "POST /api/agents/case-writer/run": { id: "task_1", title: "Ask case-writer", status: "draft", template: "skill", project_id: null },
      "GET /api/runners": [],
    });
    const user = userEvent.setup();
    renderAt(<WorkAgentPage />, { path: "/work/agents/:name", route: "/work/agents/case-writer" });
    expect(await screen.findByRole("heading", { level: 1, name: "case-writer" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("/gone-skill");
    await user.type(screen.getByLabelText("What do you need from case-writer?"), "A case study of the podcast.");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ ask: "A case study of the podcast." });
    await user.click(screen.getByRole("tab", { name: "What it gets" }));
    expect(await screen.findByText(/# You are working as case-writer/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How we write release notes" })).toHaveAttribute("href", "/work/library/view?path=references%2Frelease-notes.md");
  });
});

// ---------------------------------------------------------------- Workspace

const at = "2026-10-09T10:00:00Z";
const q4 = { id: "q4-campaigns", title: "Q4 campaigns", missing: false };
const workspaceView = {
  items: [
    { id: "ctx_doc", title: "Q4 outline", kind: "doc", url: null, excerpt: "The points, in order", projects: [q4], updated_at: at, original: null },
    {
      id: "ctx_link",
      title: "Launch calendar",
      kind: "link",
      url: "https://calendar.example.com/launch",
      excerpt: "",
      projects: [q4],
      updated_at: at,
      original: null,
    },
    { id: "ctx_loose", title: "Ideas", kind: "doc", url: null, excerpt: "", projects: [], updated_at: at, original: null },
  ],
  projects: [{ id: "q4-campaigns", title: "Q4 campaigns", active: true }],
};
const doc = {
  id: "ctx_doc",
  title: "Q4 outline",
  body: "## The points\n\n1. Polls run on Tuesdays.",
  revision: 2,
  version: 3,
  created_by: "act_owner",
  created_at: at,
  updated_at: at,
  edited_by: "Owner",
  archived_at: null,
  capture: "note",
  projects: ["q4-campaigns"],
  url: null,
};
const brainProject = {
  id: "q4-campaigns",
  title: "Q4 campaigns",
  summary: "The fourth quarter",
  status: "active",
  active: true,
  current: "",
  next: "",
  blockers: "",
  updated: null,
  aliases: [],
  files: 0,
  updates: 0,
  topic: "projects/q4-campaigns",
};
const draftRun = {
  task_id: "task_1",
  skill: "weekly-posts",
  skills: ["weekly-posts"],
  kind: "run",
  agent: null,
  doc_action: null,
  ask: "A LinkedIn post from this outline.",
  status: "done",
  assignee_id: null,
  created_at: at,
  updated_at: at,
  makes_files: false,
  folder: null,
  files: [],
  capture: { id: "ctx_doc", title: "Q4 outline", revision: 2 },
  project: null,
  attached: [],
  result: { artifact_id: "art_1", title: "LinkedIn post", text: "Polls are back on Tuesdays.", version: 1, at },
  proposal: null,
};

describe("Workspace", () => {
  it("lists docs and links by project, and starts a doc from a template", async () => {
    const calls = mockApi({
      "GET /api/workspace/items": workspaceView,
      "POST /api/workspace/docs": { ...doc, id: "ctx_new", title: "Outline" },
    });
    const user = userEvent.setup();
    renderAt(<WorkspacePage />, { path: "/work/workspace", route: "/work/workspace" });
    const mine = await screen.findByRole("list", { name: "Q4 campaigns" });
    expect(within(mine).getByRole("link", { name: "Q4 outline" })).toHaveAttribute("href", "/work/workspace/ctx_doc");
    const calendar = within(mine).getByRole("link", { name: "Launch calendar" });
    expect(calendar).toHaveAttribute("href", "https://calendar.example.com/launch");
    expect(calendar).toHaveAttribute("target", "_blank");
    expect(within(screen.getByRole("list", { name: "No project" })).getByRole("link", { name: "Ideas" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Outline" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ template: "outline", projects: [] }));
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("shows one project's items and links what it adds to that project", async () => {
    const calls = mockApi({
      "GET /api/workspace/items": { ...workspaceView, items: workspaceView.items.slice(0, 2) },
      "POST /api/workspace/links": { ...doc, id: "ctx_sheet", title: "Budget", capture: "link", url: "https://sheet.example.com/budget" },
    });
    const user = userEvent.setup();
    renderAt(<WorkspacePage />, { path: "/work/workspace", route: "/work/workspace?project=q4-campaigns" });
    expect(await screen.findByRole("list", { name: "Workspace" })).toBeInTheDocument();
    expect(calls[0]?.path).toBe("/api/workspace/items?project=q4-campaigns");
    await user.click(screen.getByRole("button", { name: "Add a link" }));
    await user.type(screen.getByLabelText("The link"), "https://sheet.example.com/budget");
    await user.type(screen.getByLabelText("What it is (optional)"), "Budget");
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        url: "https://sheet.example.com/budget",
        title: "Budget",
        projects: ["q4-campaigns"],
      }),
    );
  });

  it("opens a doc with its projects and AI only when asked, and takes what a run made", async () => {
    const calls = mockApi({
      "GET /api/notes/ctx_doc": doc,
      "GET /api/brain/projects": [brainProject],
      "GET /api/skills": skills,
      "GET /api/agents": [writer],
      "GET /api/workspace/ctx_doc/runs": [draftRun],
      "GET /api/runners": [],
      "POST /api/workspace/ctx_doc/push-back": { id: "task_2", title: "Push back on Q4 outline", status: "ready", template: "skill", project_id: null },
      "POST /api/workspace/ctx_doc/use": { ...doc, body: "Polls are back on Tuesdays.", revision: 3 },
    });
    const user = userEvent.setup();
    renderAt(<WorkspaceDocPage />, { path: "/work/workspace/:docId", route: "/work/workspace/ctx_doc" });
    expect(await screen.findByRole("heading", { name: "With AI, when you ask" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Workspace" })).toHaveAttribute("href", "/work/workspace");
    expect(screen.getByRole("link", { name: "Word" })).toHaveAttribute("href", "/api/workspace/ctx_doc/export?format=docx");
    await user.click(screen.getByRole("button", { name: "Push back" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/workspace/ctx_doc/push-back")).toBe(true));
    const runs = await screen.findByRole("list", { name: "What AI made from it" });
    expect(within(runs).getByText("/weekly-posts")).toBeInTheDocument();
    await user.click(within(runs).getByRole("button", { name: "Use as the next version" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/workspace/ctx_doc/use")?.body).toEqual({ task_id: "task_1", how: "version" }));
    expect(await within(runs).findByText(/Every earlier version is kept/)).toBeInTheDocument();
  });

  it("offers only questions from a critic, never a version to take", async () => {
    mockApi({
      "GET /api/notes/ctx_doc": doc,
      "GET /api/brain/projects": [brainProject],
      "GET /api/skills": skills,
      "GET /api/agents": [],
      "GET /api/workspace/ctx_doc/runs": [{ ...draftRun, skill: "", skills: [], doc_action: "push-back", ask: "Push back on Q4 outline" }],
    });
    renderAt(<WorkspaceDocPage />, { path: "/work/workspace/:docId", route: "/work/workspace/ctx_doc" });
    const runs = await screen.findByRole("list", { name: "What AI made from it" });
    expect(within(runs).getByRole("button", { name: /Read/ })).toBeInTheDocument();
    expect(within(runs).queryByRole("button", { name: "Use as the next version" })).not.toBeInTheDocument();
    expect(within(runs).queryByRole("button", { name: "Keep as a new doc" })).not.toBeInTheDocument();
  });
});

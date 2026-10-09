// Work: the frame and its tabs, the overview of its parts, and each part as it lands.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { NewWorkAgentPage, WorkAgentPage, WorkAgentsPage } from "./Agents";
import { LibraryItemPage, LibraryPage } from "./Library";
import { WorkOverviewPage } from "./Overview";
import { WorkLayout } from "./WorkLayout";

afterEach(() => vi.restoreAllMocks());

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

describe("Work", () => {
  it("frames its parts as tabs, with what waits for a yes on Skills", async () => {
    mockApi({ "GET /api/brain/status": { available: true }, "GET /api/skills": skills, "GET /api/library": [], "GET /api/agents": [] });
    renderAt(<WorkLayout />, { path: "/work", route: "/work" });
    const tabs = await screen.findByRole("navigation", { name: "Work sections" });
    expect(within(tabs).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual(["/work", "/work/skills", "/work/agents", "/work/library", "/work/outputs"]);
    expect(within(tabs).getByRole("link", { name: /Skills/ })).toHaveTextContent("1");
    expect(screen.getByRole("heading", { level: 1, name: "Work" })).toBeInTheDocument();
  });

  it("overviews its parts, each with the question it answers, and what waits for you", async () => {
    mockApi({
      "GET /api/skills": skills,
      "GET /api/outputs": { root: "C:/home/outputs", folders: [], files: [] },
      "GET /api/skills/runs": [],
      "GET /api/library": [],
      "GET /api/agents": [],
    });
    renderAt(<WorkOverviewPage />, { path: "/work", route: "/work" });
    const parts = await screen.findByRole("list", { name: "The parts of Work" });
    expect(within(parts).getAllByRole("heading").map((h) => h.textContent)).toEqual([
      "Compose",
      "Workspace",
      "Skills",
      "Agents",
      "Workflows",
      "Library",
      "Outputs",
    ]);
    expect(within(parts).getByRole("link", { name: "Skills" })).toHaveAttribute("href", "/work/skills");
    expect(await within(parts).findByText("1 skill")).toBeInTheDocument();
    expect(screen.getByText(/waiting in/)).toHaveTextContent("/one-pager");
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

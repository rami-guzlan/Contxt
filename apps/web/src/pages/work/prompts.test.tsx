// Prompts: your own words kept in the Brain, found by their words, tags and project; a new one
// kept with its name, tags and picks; one prompt's page with its words to copy, its earlier
// versions and the files that came with it; and running it, which is secondary: the whole prompt
// a model gets with its size, the skills in the order picked, improving it only on a yes. The old
// Compose address opens a new prompt with what its link picked.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ComposeMoved } from "./Compose";
import { NewPromptPage, PromptPage, PromptsPage } from "./Prompts";

afterEach(() => vi.restoreAllMocks());

const at = "2026-10-09T10:00:00Z";
const card = (name: string, description: string) => ({
  name,
  category: "social",
  description,
  triggers: [],
  artifacts: ["post"],
  makes_files: false,
  files: 1,
  last_run: null,
  used_by: [],
  use: "run",
});
const skills = {
  skills: [card("weekly-posts", "Three LinkedIn posts for the week."), card("one-pager", "A one-page summary.")],
  waiting: [],
};
const assembly = {
  title: "Run /one-pager, /weekly-posts",
  prompt: "# Task: Run /one-pager, /weekly-posts\n\n## Instructions (prompt version 1)\nRun these skills for the request below.",
  tokens: 1234,
  exact: true,
  parts: [
    { label: "Instructions", tokens: 400 },
    { label: "The Brain's brief", tokens: 834 },
  ],
  brief: { available: true, entries: 4, note: null },
  short: "A one-pager, then posts from it.\n\nBefore you start, call get_task_context with this request.",
  short_tokens: 40,
  skills: ["one-pager", "weekly-posts"],
  agent: null,
  makes_files: false,
};
const saved = {
  id: "weekly-posts-prompt",
  path: "references/prompts/weekly-posts.md",
  title: "Weekly posts",
  body: "Three posts for next week.\n\n- One question each",
  picks: { skills: ["weekly-posts"], agent: null, docs: [], library: [], project: null },
  tags: ["social", "weekly"],
  project: "q4",
  project_title: "Q4 campaigns",
  origin: "chat",
  scope: "person:owner",
  revision: 2,
  version: 2,
  created_at: at,
  updated_at: at,
  archived_at: null,
  uses: 3,
  last_used: at,
  versions: [],
  attachments: [],
};
const other = {
  ...saved,
  id: "thank-you-prompt",
  path: "references/prompts/thank-you.md",
  title: "Thank-you note",
  body: "A thank-you note to the panel.",
  tags: ["events"],
  project: null,
  project_title: null,
  origin: "upload",
  uses: 0,
};
const base = {
  "GET /api/skills": skills,
  "GET /api/agents": [],
  "GET /api/notes": [],
  "GET /api/brain/files": { references: [], assets: [], skills: [] },
  "GET /api/brain/projects": [{ id: "q4", title: "Q4 campaigns", active: true }],
  "GET /api/prompts": [saved, other],
  "GET /api/skills/runs": [],
  "GET /api/runners": [],
  "POST /api/compose/assemble": assembly,
};

describe("Prompts", () => {
  it("lists your prompts, found by their words, tags and project", async () => {
    const calls = mockApi(base);
    const user = userEvent.setup();
    renderAt(<PromptsPage />, { path: "/work/prompts", route: "/work/prompts" });
    const list = await screen.findByRole("list", { name: "Prompts" });
    expect(within(list).getByRole("link", { name: "Weekly posts" }).getAttribute("href")).toBe("/work/prompts/weekly-posts-prompt");
    expect(within(list).getByText(/saved from a chat · for Q4 campaigns · ran 3 times/)).toBeInTheDocument();
    expect(within(list).getByText(/used often: worth a skill/)).toBeInTheDocument();
    expect(within(list).getByText(/saved here/)).toBeInTheDocument();
    await user.click(within(screen.getByRole("group", { name: "Tags" })).getByRole("button", { name: "events" }));
    expect(within(screen.getByRole("list", { name: "Prompts" })).queryByText("Weekly posts")).toBeNull();
    expect(within(screen.getByRole("list", { name: "Prompts" })).getByText("Thank-you note")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Find a prompt"), "panel");
    await waitFor(() => expect(calls.some((c) => c.path === "/api/prompts?q=panel")).toBe(true));
    await user.click(screen.getByRole("button", { name: "Set aside" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("archived=true"))).toBe(true));
  });

  it("keeps a new prompt with its name, tags and project, then opens it", async () => {
    const calls = mockApi({ ...base, "POST /api/prompts": { status: 201, body: { ...other, id: "new-prompt" } } });
    const user = userEvent.setup();
    renderAt(<NewPromptPage />, { path: "/work/prompts/new", route: "/work/prompts/new" });
    await user.type(await screen.findByLabelText("The prompt"), "A thank-you note to the panel.");
    expect(screen.getByText(/Leave it empty to call it “A thank-you note to the panel.”/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Tags"), "events, thanks, events");
    await waitFor(() => expect(screen.getByLabelText("For a project")).toHaveTextContent("Q4 campaigns"));
    await user.selectOptions(screen.getByLabelText("For a project"), "q4");
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/prompts")?.body).toEqual({
        title: "A thank-you note to the panel.",
        body: "A thank-you note to the panel.",
        tags: ["events", "thanks"],
        picks: { skills: [], agent: null, docs: [], library: [], project: "q4" },
      }),
    );
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("shows one prompt word for word, with its earlier versions and its files", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/prompts/weekly-posts-prompt": {
        ...saved,
        versions: [
          { revision: 2, title: "Weekly posts", body: saved.body, at },
          { revision: 1, title: "Weekly posts", body: "Three posts.", at },
        ],
        attachments: [{ path: "assets/calendar.csv", title: "Calendar", kind: "asset" }],
      },
      "PUT /api/prompts/weekly-posts-prompt": { ...saved, title: "Poll posts" },
      "DELETE /api/prompts/weekly-posts-prompt": { ...saved, archived_at: at },
      "POST /api/library/upload": { status: 201, body: { status: "applied", message: "Filed it.", path: "assets/brief.png" } },
    });
    const user = userEvent.setup();
    renderAt(<PromptPage />, { path: "/work/prompts/:promptId", route: "/work/prompts/weekly-posts-prompt" });
    expect(await screen.findByRole("heading", { name: "Weekly posts" })).toBeInTheDocument();
    expect(screen.getByText("The prompt, word for word")).toBeInTheDocument();
    expect(screen.getByText(/- One question each/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Used often: make it a skill" }).getAttribute("href")).toContain("/work/skills?new=1&ask=");
    expect(within(screen.getByRole("list", { name: "Earlier versions" })).getByText("Three posts.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Files that came with it" })).getByRole("link", { name: "Calendar" })).toBeInTheDocument();
    await user.upload(screen.getByLabelText("A file that goes with it"), new File(["png"], "brief.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Add it" }));
    await waitFor(() => {
      const form = calls.find((c) => c.path === "/api/library/upload")?.body as FormData;
      expect([form.get("kind"), form.get("attach_to"), form.get("project")]).toEqual(["asset", saved.path, "q4"]);
    });
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const name = screen.getByLabelText("Its name");
    await user.clear(name);
    await user.type(name, "Poll posts");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ title: "Poll posts", body: saved.body, tags: ["social", "weekly"], expected_version: 2 }),
    );
    await user.click(screen.getByRole("button", { name: "Set aside" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("runs a prompt with the skills in the order picked, and shows what a model gets", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/compose/run": { status: 201, body: { id: "task_1", title: "Run /one-pager", status: "draft", template: "skill", project_id: null } },
    });
    const user = userEvent.setup();
    renderAt(<NewPromptPage />, { path: "/work/prompts/new", route: "/work/prompts/new?run=1" });
    await user.type(await screen.findByLabelText("The prompt"), "A one-pager, then posts from it.");
    await user.click(screen.getByRole("button", { name: "Skills to follow" }));
    await user.click(await screen.findByRole("checkbox", { name: /\/one-pager/ }));
    await user.click(screen.getByRole("checkbox", { name: /\/weekly-posts/ }));
    expect(screen.getByRole("list", { name: "Skills to follow: chosen" })).toHaveTextContent(/one-pager.*weekly-posts/);
    const gets = screen.getByRole("region", { name: "What your AI gets" });
    expect(await within(gets).findByText("1,234 tokens", undefined, { timeout: 3000 })).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/api/compose/assemble").pop()?.body).toEqual({
        request: "A one-pager, then posts from it.",
        skills: ["one-pager", "weekly-posts"],
        agent: null,
        docs: [],
        library: [],
        project: null,
      }),
    );
    await user.click(within(gets).getByRole("tab", { name: "Short, for any AI" }));
    expect(within(gets).getByText(/call get_task_context with this request/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run here" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/compose/run")?.body).toMatchObject({
        request: "A one-pager, then posts from it.",
        skills: ["one-pager", "weekly-posts"],
      }),
    );
    expect(await screen.findByText(/It waits for a model/)).toBeInTheDocument();
  });

  it("counts a run from a saved prompt, and improves its words only when you say", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/prompts/weekly-posts-prompt": saved,
      "POST /api/compose/run": { status: 201, body: { id: "task_2", title: "Weekly posts", status: "draft", template: "skill", project_id: null } },
      "POST /api/compose/improve": { status: 201, body: { id: "ajob_1", kind: "prompt-improve", status: "waiting", result: {}, error: null } },
      "GET /api/brain/agent/jobs/ajob_1": {
        id: "ajob_1",
        kind: "prompt-improve",
        status: "done",
        result: { prompt: "Three LinkedIn posts for next week.", changes: ["Says where."], used: [], questions: ["Which day goes first?"] },
        error: null,
      },
      "PUT /api/prompts/weekly-posts-prompt": saved,
    });
    const user = userEvent.setup();
    renderAt(<PromptPage />, { path: "/work/prompts/:promptId", route: "/work/prompts/weekly-posts-prompt" });
    await user.click(await screen.findByRole("button", { name: "Run or preview" }));
    expect(await screen.findByRole("list", { name: "Skills to follow: chosen" })).toHaveTextContent("weekly-posts");
    await user.click(screen.getByRole("button", { name: "Run here" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/compose/run")?.body).toMatchObject({ prompt_id: "weekly-posts-prompt", project: "q4" }));
    await user.click(screen.getByRole("button", { name: "Improve" }));
    const improved = await screen.findByRole("region", { name: "Improved request" }, { timeout: 4000 });
    expect(within(improved).getByText("Which day goes first?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Keep these words as a new version" })).toBeNull(); // nothing changes until taken
    await user.click(within(improved).getByRole("button", { name: "Use it" }));
    await user.click(screen.getByRole("button", { name: "Keep these words as a new version" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ body: "Three LinkedIn posts for next week.", expected_version: 2 }),
    );
  });

  it("opens the old Compose links as a new prompt with what they picked", async () => {
    mockApi({ ...base, "GET /api/agents": [{ name: "case-writer", role: "Writes case studies", status: "active", projects: [] }] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/work/compose?agent=case-writer&ask=A%20case%20study"]}>
          <Routes>
            <Route path="/work/compose" element={<ComposeMoved />} />
            <Route path="/work/prompts/new" element={<NewPromptPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByLabelText("The prompt")).toHaveValue("A case study");
    await waitFor(() => expect(screen.getByLabelText("Work as an agent")).toHaveValue("case-writer"));
  });
});

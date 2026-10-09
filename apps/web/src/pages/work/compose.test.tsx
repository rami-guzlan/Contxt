// Compose: the request and its picks beside the whole prompt a model gets, with its size; run it
// here with the skills in the order picked; improve it and take the suggestion only on a yes;
// save it with its picks, load it again, and see how often it ran.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ComposePage } from "./Compose";

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
  id: "ctx_prompt",
  title: "Weekly posts",
  body: "Three posts for next week.",
  picks: { skills: ["weekly-posts"], agent: null, docs: [], library: [], project: null },
  revision: 2,
  version: 3,
  created_at: at,
  updated_at: at,
  archived_at: null,
  uses: 3,
  last_used: at,
  versions: [],
};
const base = {
  "GET /api/skills": skills,
  "GET /api/agents": [],
  "GET /api/notes": [],
  "GET /api/brain/files": { references: [], assets: [], skills: [] },
  "GET /api/brain/projects": [],
  "GET /api/prompts": [],
  "GET /api/skills/runs": [],
  "GET /api/runners": [],
  "POST /api/compose/assemble": assembly,
};

describe("Compose", () => {
  it("shows the whole prompt with its size, and runs the skills in the order picked", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/compose/run": { status: 201, body: { id: "task_1", title: "Run /one-pager", status: "draft", template: "skill", project_id: null } },
    });
    const user = userEvent.setup();
    renderAt(<ComposePage />, { path: "/work/compose", route: "/work/compose" });
    expect(await screen.findByText(/Write what you want, and the whole prompt/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("What do you want?"), "A one-pager, then posts from it.");
    await user.click(screen.getByRole("button", { name: "Skills to follow" }));
    await user.click(await screen.findByRole("checkbox", { name: /\/one-pager/ }));
    await user.click(screen.getByRole("checkbox", { name: /\/weekly-posts/ }));
    expect(screen.getByRole("list", { name: "Skills to follow: chosen" })).toHaveTextContent(/one-pager.*weekly-posts/);
    const gets = screen.getByRole("region", { name: "What your AI gets" });
    expect(await within(gets).findByText("1,234 tokens", undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(within(gets).getByText(/Run these skills for the request below/)).toBeInTheDocument();
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

  it("improves the request, and takes the suggestion only when you say", async () => {
    mockApi({
      ...base,
      "POST /api/compose/improve": { status: 201, body: { id: "ajob_1", kind: "prompt-improve", status: "waiting", result: {}, error: null } },
      "GET /api/brain/agent/jobs/ajob_1": {
        id: "ajob_1",
        kind: "prompt-improve",
        status: "done",
        result: {
          prompt: "Three LinkedIn posts for next week, following /weekly-posts.",
          changes: ["Says how many and for when."],
          used: ["/weekly-posts"],
          questions: ["Which day goes first?"],
        },
        error: null,
      },
    });
    const user = userEvent.setup();
    renderAt(<ComposePage />, { path: "/work/compose", route: "/work/compose" });
    const box = await screen.findByLabelText("What do you want?");
    await user.type(box, "posts pls");
    await user.click(screen.getByRole("button", { name: "Improve" }));
    const improved = await screen.findByRole("region", { name: "Improved request" }, { timeout: 4000 });
    expect(within(improved).getByText("Says how many and for when.")).toBeInTheDocument();
    expect(within(improved).getByText("Which day goes first?")).toBeInTheDocument();
    expect(box).toHaveValue("posts pls"); // nothing changes until taken
    await user.click(within(improved).getByRole("button", { name: "Use it" }));
    expect(box).toHaveValue("Three LinkedIn posts for next week, following /weekly-posts.");
  });

  it("saves a prompt with its picks, loads it again, and counts its runs", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/prompts": [saved],
      "POST /api/prompts": { status: 201, body: { ...saved, id: "ctx_new", title: "A thank-you note", uses: 0 } },
      "POST /api/compose/run": { status: 201, body: { id: "task_2", title: "Weekly posts", status: "draft", template: "skill", project_id: null } },
    });
    const user = userEvent.setup();
    renderAt(<ComposePage />, { path: "/work/compose", route: "/work/compose" });
    const list = await screen.findByRole("list", { name: "Saved prompts" });
    expect(within(list).getByText("Ran 3 times, last", { exact: false })).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "Used often: make it a skill" }).getAttribute("href")).toContain("/work/skills?new=1&ask=");
    await user.type(screen.getByLabelText("What do you want?"), "A thank-you note to the panel.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByLabelText("Its name")).toHaveValue("A thank-you note to the panel.");
    await user.click(screen.getByRole("button", { name: "Save it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/prompts")?.body).toEqual({
        title: "A thank-you note to the panel.",
        body: "A thank-you note to the panel.",
        picks: { skills: [], agent: null, docs: [], library: [], project: null },
      }),
    );
    await user.click(within(list).getByRole("button", { name: "Weekly posts" }));
    expect(screen.getByLabelText("What do you want?")).toHaveValue("Three posts for next week.");
    expect(screen.getByRole("list", { name: "Skills to follow: chosen" })).toHaveTextContent("weekly-posts");
    await user.click(screen.getByRole("button", { name: "Run here" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/compose/run")?.body).toMatchObject({ prompt_id: "ctx_prompt" }));
  });

  it("starts from a link with an agent and words already in", async () => {
    mockApi({
      ...base,
      "GET /api/agents": [{ name: "case-writer", role: "Writes case studies", status: "active", projects: [] }],
    });
    renderAt(<ComposePage />, { path: "/work/compose", route: "/work/compose?agent=case-writer&ask=A%20case%20study" });
    expect(await screen.findByLabelText("What do you want?")).toHaveValue("A case study");
    await waitFor(() => expect(screen.getByLabelText("Work as an agent")).toHaveValue("case-writer"));
  });
});

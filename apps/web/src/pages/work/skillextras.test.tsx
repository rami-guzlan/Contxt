// Skills, upgraded: skills worth writing down (written, or set aside), a skill brought in from a
// zip (and what was left out), and on a skill's page what uses it, what changed under it, and its
// copies in Claude Code with how far behind each is.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { SkillPage, SkillsPage } from "./Skills";

afterEach(() => vi.restoreAllMocks());

const card = {
  name: "weekly-posts",
  category: "social",
  description: "Draft the week's LinkedIn posts.",
  triggers: [],
  artifacts: ["post"],
  makes_files: false,
  files: 1,
  last_run: null,
  used_by: [],
  use: "run",
};
const skill = {
  name: "weekly-posts",
  category: "social",
  description: "Draft the week's LinkedIn posts.",
  when_to_use: "",
  path: "skills/social/weekly-posts",
  files: [{ path: "skills/social/weekly-posts/SKILL.md", kind: "skill", title: "SKILL.md", size: 300, mime: "text/markdown" }],
  triggers: [],
  artifacts: ["post"],
  depends_on: [],
  text: "# /weekly-posts\n\n1. Draft.",
  loads: ["rules/voice"],
};
const suggestion = {
  kind: "asks",
  key: "asks:abc",
  title: "Draft the weekly LinkedIn plan for the content team",
  count: 4,
  examples: ["Draft the weekly LinkedIn plan for the content team", "Weekly LinkedIn plan, draft it"],
  apps: ["Claude Code"],
  last: "2026-10-08T10:00:00Z",
  prompt_id: null,
  ask: 'Write a skill for what I keep asking for, like: "Draft the weekly LinkedIn plan"',
};
const base = {
  "GET /api/skills": { skills: [card], waiting: [] },
  "GET /api/skills/runs": [],
  "GET /api/brain/builtin-skills": { skills: [], missing: [] },
  "GET /api/skills/suggestions": { suggestions: [suggestion], matched_by: "meaning" },
};

describe("Skills, upgraded", () => {
  it("suggests a skill worth writing down, and writes it or sets it aside", async () => {
    const calls = mockApi({ ...base, "POST /api/skills/suggestions/dismiss": { status: 204 } });
    const user = userEvent.setup();
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills" });
    const list = await screen.findByRole("list", { name: "Skills worth writing down" });
    expect(within(list).getByText("Asked 4 times in Claude Code", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/alike by meaning/)).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Not now" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/skills/suggestions/dismiss")?.body).toEqual({ key: "asks:abc" }));
    await user.click(within(list).getByRole("button", { name: "Write it as a skill" }));
    expect(await screen.findByLabelText("What should it do?")).toHaveValue(suggestion.ask);
  });

  it("brings a skill in from a zip, and says what it left out", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/skills/import": { status: 201, body: { name: "brand-voice", replaced: false, files: 1, skipped: [".env: looks like a secret"] } },
    });
    const user = userEvent.setup();
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills" });
    await user.click(await screen.findByRole("button", { name: "Bring one in" }));
    const panel = screen.getByRole("region", { name: "Bring a skill in" });
    await user.upload(within(panel).getByLabelText("A skill as a zip"), new File(["PK"], "brand-voice.zip", { type: "application/zip" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/skills/import")).toBe(true));
    expect(calls.find((c) => c.path === "/api/skills/import")?.body).toBeInstanceOf(FormData);
    expect(await within(panel).findByRole("link", { name: "/brand-voice" })).toHaveAttribute("href", "/work/skills/brand-voice");
    expect(within(panel).getByText(".env: looks like a secret")).toBeInTheDocument();
  });

  it("says what uses a skill, what changed under it, and how far behind its copies are", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/brain/skills/weekly-posts": skill,
      "GET /api/skills/weekly-posts/runs": [],
      "GET /api/runners": [],
      "GET /api/notes": [],
      "GET /api/brain/projects": [],
      "GET /api/brain/files": { references: [], assets: [], skills: [] },
      "GET /api/skills/weekly-posts/about": {
        used_by: { skills: [], agents: ["content-strategist"], workflows: [{ id: "wf_1", name: "Weekly posts" }] },
        freshness: {
          last_edited: "2026-09-01T10:00:00Z",
          last_used: "2026-10-08T10:00:00Z",
          last_run_here: null,
          last_asked: "2026-10-08T10:00:00Z",
          changed: [{ key: "rules/voice", title: "rules/voice", at: "2026-09-20T09:00:00Z" }],
        },
        pushed: [{ place: "C:/Users/you/.claude/skills/weekly-posts", user: true, pushed_at: "2026-09-02T10:00:00Z", behind: 2 }],
      },
      "POST /api/skills/weekly-posts/push": { place: "C:/Users/you/.claude/skills/weekly-posts", behind: 0, pushed_at: "2026-10-09T10:00:00Z" },
    });
    const user = userEvent.setup();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts?tab=files" });
    expect(await screen.findByRole("link", { name: "content-strategist" })).toHaveAttribute("href", "/work/agents/content-strategist");
    expect(screen.getByRole("link", { name: "Weekly posts" })).toHaveAttribute("href", "/work/workflows/wf_1");
    expect(screen.getByText(/What it loads changed after its last edit: rules\/voice/)).toBeInTheDocument();
    const copies = screen.getByRole("list", { name: "Its copies" });
    expect(within(copies).getByText(/2 versions behind: update it/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Export as a zip/ })).toHaveAttribute("href", "/api/skills/weekly-posts/export");
    await user.click(screen.getByRole("button", { name: "Update the copy in Claude Code" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/skills/weekly-posts/push")?.body).toEqual({}));
  });
});

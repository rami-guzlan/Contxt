import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AiWork } from "../components/AiWork";
import { mockApi, renderAt } from "../test/render";
import { ReviewPage } from "./brain/Review";
import { SkillPage, SkillsPage } from "./work/Skills";

const claude = {
  id: "claude",
  label: "Claude Code",
  provider: "claude-code",
  one_click: true,
  installed: true,
  version: "2.1",
  signed_in: true,
  install: "",
  sign_in: "",
  actor_id: "act_claude",
  detail: "",
};

const posts = {
  name: "weekly-posts",
  category: "social",
  description: "Draft the week's LinkedIn posts from the content calendar. Use it on Mondays.",
  when_to_use: "Every Monday",
  path: "skills/social/weekly-posts",
  files: [{ path: "skills/social/weekly-posts/SKILL.md", kind: "skill", title: "SKILL.md", size: 300, mime: "text/markdown" }],
  triggers: ["draft this week's posts"],
  artifacts: ["post"],
  depends_on: [],
  text: "# /weekly-posts\n\nLoads: brand/voice\nFolder: vault/skills/social/weekly-posts (scripts and assets are resolved from here)\n\n# /weekly-posts\n\n1. Read the calendar.\n2. Draft one post per day.",
  loads: ["brand/voice"],
};

const cards = {
  skills: [
    {
      name: "weekly-posts",
      category: "social",
      description: posts.description,
      triggers: posts.triggers,
      artifacts: ["post"],
      makes_files: false,
      files: 1,
      last_run: { task_id: "task_1", status: "done", at: "2026-10-05T10:00:00Z" },
      used_by: [],
      use: "run",
    },
    {
      name: "one-pager",
      category: "sales",
      description: "A one-page PDF for a prospect.",
      triggers: [],
      artifacts: ["pdf", "docx"],
      makes_files: true,
      files: 3,
      last_run: null,
      used_by: [],
      use: "run",
    },
    {
      name: "shared-assets",
      category: "general",
      description: "Fonts and logos for the other skills.",
      triggers: [],
      artifacts: ["fonts", "logos"],
      makes_files: false,
      files: 6,
      last_run: null,
      used_by: ["one-pager"],
      use: "support",
    },
    {
      name: "end-session",
      category: "ops",
      description: "Close out a session.",
      triggers: [],
      artifacts: [],
      makes_files: false,
      files: 1,
      last_run: null,
      used_by: [],
      use: "chat",
    },
  ],
  waiting: [{ proposal_id: "skill-recap-1", name: "poll-recap", description: "Recap the polls.", task_id: "task_9" }],
};

const task = (id: string, template = "skill") => ({
  id,
  status: "ready",
  assignee_id: "act_claude",
  template,
  title: "Run /weekly-posts",
  instructions: "",
});

const doneRun = {
  task_id: "task_1",
  skill: "weekly-posts",
  kind: "run",
  ask: "Three posts on async reviews.",
  status: "done",
  assignee_id: "act_claude",
  attached: [] as string[],
  created_at: "2026-10-05T10:00:00Z",
  updated_at: "2026-10-05T10:02:00Z",
  makes_files: false,
  folder: null,
  files: [],
  capture: { id: "ctx_kick", title: "Kickoff call" },
  project: { id: "q4", title: "Q4 campaign" },
  result: { artifact_id: "art_1", title: "Async posts", text: "**Monday:** Reviews happen on Fridays.", version: 1, at: "2026-10-05T10:02:00Z" },
  proposal: null,
};

const side = {
  "GET /api/skills": cards,
  "GET /api/brain/skills/weekly-posts": posts,
  "GET /api/notes": [{ id: "ctx_kick", title: "Kickoff call", body: null }],
  "GET /api/brain/projects": [{ id: "q4", title: "Q4 campaign", active: true, status: "active" }],
  "GET /api/brain/files": {
    references: [{ path: "references/voice.md", kind: "reference", title: "Voice guide", size: 10, mime: "text/markdown" }],
    assets: [],
    skills: [],
  },
  "GET /api/runners": [claude],
};

describe("the Skills place", () => {
  it("shows each skill with what it makes and its last run, and what waits in Review", async () => {
    mockApi(side);
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills" });
    expect(await screen.findByRole("link", { name: "/weekly-posts" })).toHaveAttribute("href", "/work/skills/weekly-posts");
    expect(screen.getByText(/Writes a post · ran/)).toBeInTheDocument();
    expect(screen.getByText("Ask: “draft this week's posts”")).toBeInTheDocument();
    expect(screen.getByText("Makes PDF and DOCX files")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run /one-pager" })).toHaveAttribute("href", "/work/skills/one-pager");
    expect(screen.getByText(/Waiting in/)).toHaveTextContent("/poll-recap");
    // One that other skills build on is kept, not run.
    expect(screen.getByText("Used by other skills (1 skill), not run on its own")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Run /shared-assets" })).not.toBeInTheDocument();
    // The Brain's own housekeeping is called by name in a conversation.
    expect(screen.getByText("Use it in a chat: /end-session")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Run /end-session" })).not.toBeInTheDocument();
  });

  it("opens a skill other skills build on to its procedure, saying who uses it", async () => {
    mockApi({
      ...side,
      "GET /api/brain/skills/shared-assets": { ...posts, name: "shared-assets", triggers: [], text: "# /shared-assets\n\nThe fonts." },
    });
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/shared-assets" });
    expect(await screen.findByText("The fonts.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "/one-pager" })).toHaveAttribute("href", "/work/skills/one-pager");
    expect(screen.queryByRole("tab", { name: "Run" })).not.toBeInTheDocument();
  });

  it("keeps the Run tab for a skill others build on that also makes something", async () => {
    mockApi({
      ...side,
      "GET /api/skills": {
        ...cards,
        skills: cards.skills.map((s) => (s.name === "weekly-posts" ? { ...s, used_by: ["one-pager"] } : s)),
      },
      "GET /api/skills/weekly-posts/runs": [],
    });
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts" });
    expect(await screen.findByRole("region", { name: "Run it" })).toBeInTheDocument();
    expect(screen.getByText(/Other skills build on it/)).toBeInTheDocument();
  });

  it("sends running several skills to Compose", async () => {
    mockApi({ ...side, "GET /api/skills/runs": [] });
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills" });
    const panel = await screen.findByRole("region", { name: "Run skills" });
    expect(within(panel).getByRole("link", { name: "Open Compose" })).toHaveAttribute("href", "/work/compose");
  });

  it("starts a new skill from words brought from Compose", async () => {
    mockApi({ ...side, "GET /api/skills/runs": [] });
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills?new=1&ask=Make%20a%20skill%20from%20my%20weekly%20posts" });
    expect(await screen.findByLabelText("What should it do?")).toHaveValue("Make a skill from my weekly posts");
  });

  it("writes a new skill with your AI, started at once on this computer", async () => {
    const calls = mockApi({
      ...side,
      "POST /api/skills/drafts": { status: 201, body: task("task_new", "skill-draft") },
      "POST /api/runners/claude/runs": { status: 201, body: { id: "run_new", status: "running", events: [], task_title: "Write a new skill" } },
      "GET /api/runners/runs/run_new": { id: "run_new", status: "running", events: [], task_title: "Write a new skill" },
    });
    const user = userEvent.setup();
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills" });
    await user.click(await screen.findByRole("button", { name: "New skill" }));
    const panel = screen.getByRole("region", { name: "New skill" });
    await user.type(within(panel).getByLabelText("What should it do?"), "Recap a week of polls as one post.");
    await user.click(within(panel).getByRole("button", { name: "Write it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/skills/drafts")?.body).toEqual({ ask: "Recap a week of polls as one post." }),
    );
    await waitFor(() => expect(calls.find((c) => c.path === "/api/runners/claude/runs")?.body).toEqual({ task_id: "task_new" }));
    expect(await screen.findByLabelText("Run of Write a new skill")).toBeInTheDocument();
  });

  it("teaches a skill from something brought in", async () => {
    const calls = mockApi({
      ...side,
      "GET /api/notes/ctx_kick": { id: "ctx_kick", title: "Kickoff call", body: "Dana: polls on Tuesdays." },
      "POST /api/skills/drafts": { status: 201, body: { ...task("task_new", "skill-draft"), status: "draft", assignee_id: null } },
      "GET /api/runners": [],
    });
    const user = userEvent.setup();
    renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills?capture=ctx_kick" });
    expect(await screen.findByRole("link", { name: "Kickoff call" })).toHaveAttribute("href", "/capture/ctx_kick");
    await user.type(screen.getByLabelText("What should it do?"), "How we plan polls.");
    await user.click(screen.getByRole("button", { name: "Write it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/skills/drafts")?.body).toEqual({ ask: "How we plan polls.", capture_id: "ctx_kick" }),
    );
    // No AI app on this computer: it waits, with the prompt to paste elsewhere.
    expect(await screen.findByText("It waits for a model to write it.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
  });
});

describe("one skill", () => {
  it("runs with what you need and what to use, and shows the result to copy, save or file", async () => {
    const calls = mockApi({
      ...side,
      "GET /api/skills/weekly-posts/runs": [doneRun],
      "POST /api/skills/weekly-posts/runs": { status: 201, body: task("task_2") },
      "POST /api/runners/claude/runs": { status: 201, body: { id: "run_2", status: "running", events: [], task_title: "Run /weekly-posts" } },
      "GET /api/runners/runs/run_2": { id: "run_2", status: "running", events: [], task_title: "Run /weekly-posts" },
      "POST /api/notes": { status: 201, body: { id: "ctx_saved", title: "Async posts" } },
      "POST /api/brain/files": { status: 201, body: { status: "applied", message: "Filed.", project: "q4" } },
    });
    const user = userEvent.setup();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts" });
    const panel = await screen.findByRole("region", { name: "Run it" });
    expect(within(panel).getByLabelText("What do you need?")).toHaveAttribute("placeholder", "For example: draft this week's posts");
    await user.type(within(panel).getByLabelText("What do you need?"), "Three posts on polls.");
    await user.selectOptions(await within(panel).findByLabelText("Use something you brought in (optional)"), "ctx_kick");
    await user.selectOptions(within(panel).getByLabelText("For a project (optional)"), "q4");
    await user.selectOptions(within(panel).getByLabelText("Add a file"), "references/voice.md");
    await user.click(within(panel).getByRole("button", { name: "Run" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/skills/weekly-posts/runs")?.body).toEqual({
        ask: "Three posts on polls.",
        capture_id: "ctx_kick",
        project: "q4",
        files: ["references/voice.md"],
      }),
    );
    expect(await screen.findByLabelText("Run of Run /weekly-posts")).toBeInTheDocument();

    // What an earlier run made, with what to do with it.
    expect(await screen.findByText("Reviews happen on Fridays.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Three posts on async reviews.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep as a doc" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/notes")?.body).toEqual({
        title: "Async posts",
        body: "**Monday:** Reviews happen on Fridays.",
      }),
    );
    expect(await screen.findByRole("link", { name: "open the doc" })).toHaveAttribute("href", "/work/workspace/ctx_saved");
    await user.click(screen.getByRole("button", { name: "File in a project" }));
    expect(screen.getByLabelText("Project to file it in")).toHaveValue("q4"); // the project it ran for
    await user.click(screen.getByRole("button", { name: "File it" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/files")).toBe(true));
    const form = calls.find((c) => c.method === "POST" && c.path === "/api/brain/files")?.body as FormData;
    expect((form.get("file") as File).name).toBe("async-posts.md");
    expect(form.get("project")).toBe("q4");
    expect(await screen.findByText(/Filed in/)).toHaveTextContent("Filed in Q4 campaign.");
  });

  it("offers to run what has not started, and to try again what stopped", async () => {
    const calls = mockApi({
      ...side,
      "GET /api/skills/weekly-posts/runs": [
        { ...doneRun, task_id: "task_w", status: "ready", result: null, ask: "Waiting one." },
        { ...doneRun, task_id: "task_f", status: "failed", result: null, ask: "Stopped one.", attached: ["references/voice.md"] },
      ],
      "POST /api/runners/claude/runs": { status: 201, body: { id: "run_w", status: "running", events: [], task_title: "Run /weekly-posts" } },
      "GET /api/runners/runs/run_w": { id: "run_w", status: "running", events: [], task_title: "Run /weekly-posts" },
      "POST /api/skills/weekly-posts/runs": { status: 201, body: task("task_again") },
    });
    const user = userEvent.setup();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts" });
    expect(await screen.findByText("It hasn't started yet.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Run now with Claude Code" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/runners/claude/runs")?.body).toEqual({ task_id: "task_w" }));
    expect(screen.getByText("It stopped before it finished.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/skills/weekly-posts/runs")?.body).toEqual({
        ask: "Stopped one.",
        capture_id: "ctx_kick",
        project: "q4",
        files: ["references/voice.md"],
      }),
    );
  });

  it("lists the files a run made, to download, and where they are", async () => {
    mockApi({
      ...side,
      "GET /api/brain/skills/one-pager": { ...posts, name: "one-pager", artifacts: ["pdf"], triggers: [], text: "# /one-pager\n\nMake it." },
      "GET /api/skills/one-pager/runs": [
        {
          ...doneRun,
          result: null,
          capture: null,
          project: null,
          makes_files: true,
          folder: "C:/outputs/skill-runs/2026-10-06-one-pager",
          files: [{ name: "acme one-pager.pdf", size: 2048 }, { name: "preview.png", size: 900 }],
        },
      ],
    });
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/one-pager" });
    expect(await screen.findByText(/It makes files, so it works in a folder of its own/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "acme one-pager.pdf" })).toHaveAttribute(
      "href",
      "/api/skills/runs/task_1/files/acme%20one-pager.pdf",
    );
    expect(screen.getByText("C:/outputs/skill-runs/2026-10-06-one-pager")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "preview.png" })).toHaveAttribute("src", "/api/skills/runs/task_1/files/preview.png?download=false");
  });

  it("is edited by you at once, and Undo takes the edit back", async () => {
    const calls = mockApi({
      ...side,
      "PUT /api/skills/weekly-posts": { message: "approved", checkpoint: { id: "cp-7" } },
      "POST /api/brain/checkpoints/cp-7/undo": { undone: "cp-7", checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts?tab=procedure" });
    expect(await screen.findByText("Draft one post per day.")).toBeInTheDocument();
    expect(screen.getByText("“draft this week's posts”")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const steps = screen.getByLabelText("The steps");
    expect(steps).toHaveValue("# /weekly-posts\n\n1. Read the calendar.\n2. Draft one post per day.");
    await user.clear(steps);
    await user.type(steps, "1. Draft.");
    await user.type(screen.getByLabelText("Why (optional)"), "Shorter");
    await user.click(screen.getByRole("button", { name: "Save this version" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ body: "1. Draft.", reason: "Shorter" }),
    );
    await user.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/checkpoints/cp-7/undo")).toBe(true));
  });

  it("asks your AI for a better version, which waits in Review", async () => {
    const calls = mockApi({
      ...side,
      "GET /api/runners": [],
      "GET /api/skills/weekly-posts/runs": [
        { ...doneRun, task_id: "task_3", kind: "improve", ask: "Shorter hooks.", result: null, proposal: { id: "skill-weekly-1", status: "waiting" } },
        { ...doneRun, task_id: "task_2", kind: "improve", ask: "Longer hooks.", result: null, proposal: { id: "skill-weekly-0", status: "rejected" } },
      ],
      "POST /api/skills/weekly-posts/improve": { status: 201, body: { ...task("task_4", "skill-draft"), status: "draft", assignee_id: null } },
    });
    const user = userEvent.setup();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts?tab=improve" });
    expect(await screen.findByText("Shorter hooks.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See it in Review" })).toHaveAttribute("href", "/review");
    expect(screen.getByText("Its new version was turned down.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("What should change?"), "Add the UTM step.");
    await user.click(screen.getByRole("button", { name: "Improve it" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/skills/weekly-posts/improve")?.body).toEqual({ ask: "Add the UTM step." }));
    expect(await screen.findByText("It waits for a model to draft the new version.")).toBeInTheDocument();
  });

  it("teaches the skill from something it made", async () => {
    const calls = mockApi({
      ...side,
      "GET /api/runners": [],
      "GET /api/skills/weekly-posts/runs": [doneRun],
      "POST /api/skills/weekly-posts/improve": { status: 201, body: { ...task("task_5", "skill-draft"), status: "draft", assignee_id: null } },
    });
    const user = userEvent.setup();
    const first = renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts" });
    expect(await screen.findByRole("link", { name: "Teach the skill from this" })).toHaveAttribute(
      "href",
      "/work/skills/weekly-posts?tab=improve&example=art_1",
    );
    first.unmount();
    // Where that link leads: Improve, learning from the result.
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts?tab=improve&example=art_1" });
    const panel = await screen.findByRole("region", { name: "Improve it" });
    expect(await within(panel).findByText("Async posts")).toBeInTheDocument();
    expect(within(panel).getByLabelText("What should change?")).toHaveValue("Make what it makes come out like this example.");
    await user.click(within(panel).getByRole("button", { name: "Improve it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/skills/weekly-posts/improve")?.body).toEqual({
        ask: "Make what it makes come out like this example.",
        example: "art_1",
      }),
    );
  });

  it("keeps every version, compared with now, and brings one back to edit", async () => {
    mockApi({
      ...side,
      "GET /api/skills/weekly-posts/versions?text=true": [
        { ref: "current", at: "2026-10-06T10:00:00Z", current: true, message: "", text_changed: true, chars: 20, body: "1. Draft one post." },
        { ref: "abc123", at: "2026-09-01T10:00:00Z", message: "fixture", author: "Ana", text_changed: true, chars: 30, body: "1. Read the calendar first." },
      ],
    });
    const user = userEvent.setup();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/weekly-posts?tab=history" });
    await user.click(await screen.findByRole("button", { name: /fixture · Ana/ }));
    expect(screen.getByRole("region", { name: "Now" })).toHaveTextContent("1. Draft one post.");
    await user.click(screen.getByRole("button", { name: "Use this version again" }));
    expect(await screen.findByLabelText("The steps")).toHaveValue("1. Read the calendar first.");
  });
});

describe("Review of skills", () => {
  it("shows a new version of a skill beside the skill as it is now", async () => {
    mockApi({
      "GET /api/brain/review": {
        batches: [
          {
            key: "task:task_3",
            title: "Improve /weekly-posts",
            proposer: "model:Claude Code (act_claude)",
            created: "2026-10-06T10:00:00Z",
            proposal_ids: ["skill-weekly-1"],
            counts: { total: 1, new: 0, updates: 0, replaces: 0, conflicts: 0, close: 0, duplicates: 0, problems: 0, files: 0, new_topics: 0, look: 0, clear: 1 },
            topics: [],
            task_id: "task_3",
            task_status: "done",
            documents: [],
          },
        ],
        proposals: [
          {
            id: "skill-weekly-1",
            kind: "skill.update",
            scope: "company",
            body: "# /weekly-posts\n\n1. Draft short hooks.",
            target: { name: "weekly-posts", description: "Draft the week's posts." },
            analysis: {
              change: "skill",
              kind: "skill.update",
              skill: { name: "weekly-posts", category: "social", description: "Draft the week's posts." },
              skill_before: { description: "Draft the week's posts.", when_to_use: "", triggers: [], body: "# /weekly-posts\n\n1. Draft long hooks." },
            },
          },
        ],
      },
      "GET /api/brain/catalog": { areas: [], topics: [] },
      "GET /api/brain/projects": [],
      "GET /api/brain/distill/requests": [],
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    expect(await screen.findByText("Changes a skill")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /\/weekly-posts/ }));
    expect(await screen.findByRole("region", { name: "The skill now" })).toHaveTextContent("long hooks");
    expect(screen.getByRole("region", { name: "Proposed" })).toHaveTextContent("short hooks");
  });
});

describe("AI work", () => {
  it("says what runs now and links each run to the page its work belongs to", async () => {
    mockApi({
      "GET /api/runners/runs": [
        { id: "run_a", status: "running", task_title: "Run /weekly-posts", started_at: "2026-10-06T10:00:00Z", finished_at: null, link: "/work/skills/weekly-posts", made: [] },
        {
          id: "run_b",
          status: "succeeded",
          task_title: "Summarize “Kickoff”",
          started_at: "2026-10-06T09:00:00Z",
          finished_at: "2026-10-06T09:02:00Z",
          link: "/capture/ctx_kick",
          made: [{ name: "a.pdf", size: 1 }],
        },
      ],
      "GET /api/runners/runs/run_a": { id: "run_a", status: "running", events: [{ seq: 1, at: "", kind: "text", text: "Reading the calendar." }], task_title: "Run /weekly-posts" },
    });
    const user = userEvent.setup();
    renderAt(<AiWork />);
    await user.click(await screen.findByRole("button", { name: "AI working (1)" }));
    const tray = screen.getByRole("dialog", { name: "AI work" });
    const links = within(tray).getAllByRole("link", { name: "Open" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/work/skills/weekly-posts", "/capture/ctx_kick"]);
    expect(within(tray).getByText(/made 1 file/)).toBeInTheDocument();
    await user.click(within(tray).getByRole("button", { name: "Watch" }));
    expect(await within(tray).findByText("Reading the calendar.")).toBeInTheDocument();
  });

  it("stays out of the way until something has run here", async () => {
    mockApi({ "GET /api/runners/runs": [] });
    const { container } = renderAt(<AiWork />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});

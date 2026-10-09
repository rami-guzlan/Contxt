// The app's frame and its pages: the navigation with what waits, Home, Brain-backed projects,
// search, the earlier workspace in Settings, and the AI apps the app's own work runs on.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Layout } from "../components/Layout";
import { apps, goals, health, plan } from "../test/fixtures";
import { actors, mockApi, renderAt, workspace } from "../test/render";
import { ConnectionsPage } from "./Connections";
import { HomePage } from "./Home";
import { SearchPage } from "./Misc";
import { SettingsPage } from "./Settings";
import { Week } from "./brain/Week";
import { ProjectPage, ProjectsPage } from "./Projects";

const home = { workspace, counts: { brain_proposals: 3, ai_work: { ready: 1 } } };
const stamp = "2026-10-05T13:00:00.000000Z";
const project = {
  id: "q4-campaigns",
  title: "Q4 campaigns",
  summary: "The fourth-quarter campaign proposals",
  status: "active",
  active: true,
  current: "v3 sent to Jordan",
  next: "Wait for her notes",
  blockers: "",
  updated: stamp,
  aliases: ["campaign proposals"],
  files: 2,
  updates: 4,
  topic: "projects/q4-campaigns",
};
const detail = {
  id: "q4-campaigns",
  title: "Q4 campaigns",
  summary: "The fourth-quarter campaign proposals",
  aliases: ["campaign proposals"],
  status: "active",
  active: true,
  state: { status: "active", current: "v3 sent to Jordan", next: "Wait for her notes" },
  brief: "Proposals for LinkedIn video and events.",
  route_key: "projects/q4-campaigns",
  updates: [{ seq: 4, at: stamp, summary: "Sent v3 to Jordan", changes: { current: "v3 sent to Jordan" }, evidence: "", actor: "person:owner" }],
  files: [
    {
      path: "references/projects/q4-campaigns/campaign-proposal.md",
      id: "card-1",
      title: "Campaign proposal",
      summary: "The proposal",
      version: 3,
      file_status: "sent",
      dated: "2026-10-03",
      filename: "Campaign proposal v3.docx",
      sections: 5,
    },
  ],
  notes: [{ id: "decision-video", title: "Video stays", summary: "LinkedIn video keeps its budget.", kind: "fact", type: "decision", added: "2026-10-04" }],
};

describe("layout", () => {
  it("names the places for the person's questions, with Catch up while something needs them", async () => {
    mockApi({ "GET /api/home": home, "GET /api/brain/catch-up": plan(), "GET /api/brain/goals": goals });
    renderAt(
      <Layout>
        <p>content</p>
      </Layout>,
    );
    const main = screen.getByRole("navigation", { name: "Main" });
    expect(await within(main).findByRole("link", { name: /Catch up/ })).toHaveAttribute("href", "/catch-up");
    expect(within(main).getAllByRole("link").map((l) => l.textContent?.replace(/\d+ minutes?$/, ""))).toEqual([
      "Home",
      "Capture",
      "Projects",
      "Brain",
      "Work",
      "Activity",
      "Catch up",
    ]);
    expect(within(main).getByRole("link", { name: /Catch up/ })).toHaveTextContent("3 minutes");
    expect(screen.queryByLabelText(/waiting for you/)).not.toBeInTheDocument(); // calm: no red badge
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("note")).not.toBeInTheDocument(); // not a demo
  });

  it("lists Catch up only while something needs you, and says when a Brain is a demo", async () => {
    mockApi({
      "GET /api/home": home,
      "GET /api/brain/catch-up": plan({ caught_up: true, judgment: [], quick: [], upkeep: [] }),
      "GET /api/brain/goals": { ...goals, starter: "knowledge-company" },
    });
    renderAt(
      <Layout>
        <p>content</p>
      </Layout>,
    );
    expect(await screen.findByRole("note")).toHaveTextContent("Test workspace is made up");
    const main = screen.getByRole("navigation", { name: "Main" });
    expect(within(main).queryByRole("link", { name: /Catch up/ })).not.toBeInTheDocument();
  });

  it("adds things from one menu: talk, record, upload, write, or move in", async () => {
    mockApi({ "GET /api/home": home, "GET /api/brain/catch-up": plan() });
    const user = userEvent.setup();
    renderAt(
      <Layout>
        <p>content</p>
      </Layout>,
    );
    await user.click(screen.getByRole("button", { name: "Add" }));
    const menu = screen.getByRole("menu", { name: "Add" });
    expect(within(menu).getByRole("menuitem", { name: /Record a meeting/ })).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: /Upload a file/ })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Write" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Move in from another AI" })).toHaveAttribute("href", "/move-in");
  });
});

describe("home", () => {
  const cockpit = {
    "GET /api/home": home,
    "GET /api/brain/catch-up": plan(),
    "GET /api/brain/goals": goals,
    "GET /api/onboarding": {
      steps: [],
      done: 5,
      total: 6,
      owner_name: "Sam",
      brain: { available: true, own_entries: 30, waiting: 3, projects: 1, files: 0, goals: true },
      local_model: true,
      completed_at: stamp,
      dismissed_at: null,
      tour_seen_at: null,
    },
    "GET /api/brain/apps": apps,
    "GET /api/brain/projects": [project, { ...project, id: "old", title: "Old work", active: false }],
    "GET /api/notes": [],
    "GET /api/brain/weekly": [
      { start: "2026-09-22", end: "2026-09-28", conversations: 2, packets: 5 },
      { start: "2026-09-29", end: "2026-10-05", conversations: 4, packets: 9 },
    ],
    "GET /api/runners": [],
    "GET /api/brain/examples": [],
    "GET /api/brain/models": { matching: { enabled: true, present: false, downloading: false, about_mb: 70 } },
  };

  it("says in one line how you are doing, with the plan and the health behind it", async () => {
    mockApi(cockpit);
    renderAt(<HomePage />);
    expect(await screen.findByRole("heading", { level: 1, name: "Test workspace" })).toBeInTheDocument();
    expect(await screen.findByText("3 things for you, about 3 minutes.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Catch up, about 3 minutes/ })).toHaveAttribute("href", "/catch-up");
    expect(screen.getByLabelText("Brain health 82 of 100, good")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tidy up" })).toHaveAttribute("href", "/review");
    expect(screen.getByText("Run marketing without dropping follow-ups.")).toBeInTheDocument();
    // what is left to set up, until it is done
    const steps = await screen.findByRole("region", { name: "Next steps" });
    expect(within(steps).getByRole("link", { name: "Add its files" })).toHaveAttribute("href", "/projects/q4-campaigns");
    expect(within(steps).queryByRole("link", { name: "Connect an AI app" })).not.toBeInTheDocument();
    // nothing downloads on its own: matching by meaning waits for the person's word
    expect(within(steps).getByRole("link", { name: "Match by meaning" })).toHaveAttribute("href", "/settings?tab=computer");
    // three pictures and the apps, calm
    expect(await screen.findByLabelText("What your AIs asked")).toHaveTextContent("9");
    expect(screen.getByLabelText("What came in")).toHaveTextContent("Your AI's chats 3");
    expect(await screen.findByRole("link", { name: "Q4 campaigns" })).toHaveAttribute("href", "/projects/q4-campaigns");
    expect(screen.queryByRole("link", { name: "Old work" })).not.toBeInTheDocument();
    const appsLine = await screen.findByRole("region", { name: "Your AI apps" });
    expect(within(appsLine).getByText(/asked/)).toBeInTheDocument();
    expect(within(appsLine).getByRole("link", { name: "Connect" })).toHaveAttribute("href", "/settings?tab=apps");
    expect(screen.getByRole("link", { name: "Move in" })).toHaveAttribute("href", "/move-in");
  });

  it("is calm when nothing needs you, and warns when a change is not saved", async () => {
    mockApi({
      ...cockpit,
      "GET /api/brain/catch-up": plan({ caught_up: true, judgment: [], quick: [], upkeep: [], health: { ...health, unsaved: ["knowledge/x.md"] } }),
    });
    renderAt(<HomePage />);
    expect(await screen.findByText("All caught up.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "What went in" })).toHaveAttribute("href", "/catch-up");
    expect(screen.getByText(/live but not saved to your Brain's history/)).toBeInTheDocument();
  });

  it("opens the first run for a new Brain", async () => {
    mockApi({
      ...cockpit,
      "GET /api/brain/goals": { ...goals, exists: false, answers: {}, purpose: "" },
      "GET /api/onboarding": {
        steps: [],
        done: 0,
        total: 6,
        owner_name: "Owner",
        brain: { available: true, own_entries: 0, waiting: 0, projects: 0, files: 0, goals: false },
        local_model: true,
        completed_at: null,
        dismissed_at: null,
        tour_seen_at: null,
      },
    });
    renderAt(<HomePage />);
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("shows the week in the supply chain on the Brain's map", async () => {
    mockApi({
      "GET /api/brain/flow?days=7": {
        days: 7,
        since: "2026-09-28T00:00:00Z",
        came_in: 4,
        approved: 3,
        rejected: 1,
        decided: {},
        waiting: 3,
        oldest_waiting: "2026-10-01T10:00:00Z",
        delivery: { conversations: 12, work_runs: 3, entries: 20, empty: 2 },
        stock: { live: 140, due: 5, disputed: 1, unused_60_days: 30, standing_tokens: 1950 },
      },
      "GET /api/brain/gaps?days=30": [{ key: "k", kind: "nothing" }],
    });
    renderAt(<Week />);
    expect(await screen.findByText("Conversations served")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Found nothing/ })).toHaveAttribute("href", "/brain/questions");
    expect(screen.getByRole("link", { name: "5 notes due for a check" })).toHaveAttribute("href", "/brain/entries?view=due");
  });
});

describe("projects", () => {
  it("lists the Brain's projects and starts a new one", async () => {
    const calls = mockApi({
      "GET /api/brain/projects": [project],
      "POST /api/brain/projects": { ...project, id: "events", title: "Events" },
    });
    const user = userEvent.setup();
    renderAt(<ProjectsPage />);
    expect(await screen.findByRole("link", { name: "Q4 campaigns" })).toHaveAttribute("href", "/projects/q4-campaigns");
    expect(screen.getByText("v3 sent to Jordan")).toBeInTheDocument();
    expect(screen.getByText(/2 files · 4 updates/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New project" }));
    const form = screen.getByRole("form", { name: "New project" });
    await user.type(within(form).getByLabelText("Name"), "Events");
    await user.type(within(form).getByLabelText("What it is for"), "Conferences and webinars");
    await user.type(within(form).getByLabelText("Other names you will call it"), "events, the booth");
    await user.click(within(form).getByRole("button", { name: "Start it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        name: "Events",
        summary: "Conferences and webinars",
        aliases: ["events", "the booth"],
      }),
    );
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("shows a project in full, records progress and changes its names", async () => {
    const calls = mockApi({
      "GET /api/brain/projects/q4-campaigns": detail,
      "GET /api/brain/projects": [project],
      "GET /api/brain/proposals": [
        { id: "p1", kind: "note.create", scope: "person:owner", route_key: "projects/q4-campaigns" },
        { id: "p2", kind: "note.create", scope: "person:owner", route_key: "brand/voice" },
      ],
      "POST /api/brain/projects/q4-campaigns/updates": { id: "q4-campaigns", seq: 5 },
      "POST /api/brain/decisions": { results: [{ id: "q4-campaigns", ok: true, message: "Updated." }], checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<ProjectPage />, { path: "/projects/:projectId", route: "/projects/q4-campaigns" });
    expect(await screen.findByRole("heading", { level: 1, name: "Q4 campaigns" })).toBeInTheDocument();
    expect(screen.getByText("Wait for her notes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Campaign proposal" })).toBeInTheDocument();
    expect(screen.getByText(/version 3 · sent/)).toBeInTheDocument();
    expect(screen.getByText("Sent v3 to Jordan")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Video stays" })).toHaveAttribute("href", "/brain/entries/decision-video");
    expect(await screen.findByRole("link", { name: "1 suggestion for this project waits for you in Review" })).toHaveAttribute("href", "/review");

    await user.click(screen.getByRole("button", { name: "Record progress" }));
    const form = screen.getByRole("form", { name: "Record progress" });
    await user.type(within(form).getByLabelText("What happened"), "Jordan approved the video budget");
    await user.type(within(form).getByLabelText("Next (if it changed)"), "Book the shoot");
    await user.click(within(form).getByRole("button", { name: "Record it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/projects/q4-campaigns/updates")?.body).toEqual({
        summary: "Jordan approved the video budget",
        state: { next: "Book the shoot" },
      }),
    );

    await user.click(screen.getByRole("button", { name: "Change the names" }));
    const names = screen.getByLabelText("Other names, comma separated");
    await user.clear(names);
    await user.type(names, "campaign proposals, Jordan's proposals");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "update", entry_id: "q4-campaigns", fields: { aliases: "campaign proposals, Jordan's proposals" } }],
        label: "Names for Q4 campaigns",
      }),
    );
  });
});

describe("search", () => {
  it("finds the Brain's entries, its projects and your notes", async () => {
    mockApi({
      "GET /api/search": {
        query: "video",
        brain: [{ id: "decision-video", title: "Video stays", summary: "It keeps its budget.", scope: "company", kind: "fact", score: 1 }],
        projects: [project],
        notes: [{ id: "ctx_1", title: "Video ideas", body: null, revision: 1, version: 1, created_by: "act_owner", created_at: stamp, updated_at: stamp, edited_by: "Owner", archived_at: null }],
      },
    });
    renderAt(<SearchPage />, { path: "/search", route: "/search?q=video" });
    expect(await screen.findByRole("link", { name: "Video stays" })).toHaveAttribute("href", "/brain/entries/decision-video");
    expect(screen.getByRole("link", { name: "Q4 campaigns" })).toHaveAttribute("href", "/projects/q4-campaigns");
    expect(screen.getByRole("link", { name: "Video ideas" })).toHaveAttribute("href", "/capture/ctx_1");
  });
});

describe("the earlier workspace in settings", () => {
  it("copies it out as files, then brings its context into the Brain", async () => {
    const legacy = {
      counts: {
        goals: 1,
        todos_open: 19,
        todos_done: 0,
        meetings: 2,
        transcripts: 2,
        memories: 18,
        documents: 1,
        sheets: 2,
        canvases: 1,
        ai_work: 3,
        projects: 12,
        projects_without_brain: 3,
      },
      has_any: true,
      exported_at: null,
      export_dir: null,
      moved_at: null,
      moved: {},
    };
    const calls = mockApi({
      "GET /api/me": { actor_id: "act_owner", kind: "human", name: "Owner", actions: [], projects: null, workspace },
      "GET /api/health": { version: "0.2.0", schema_revision: "0012", brain: true },
      "GET /api/actors": actors,
      "GET /api/brain/distill/settings": { assignee_id: null },
      "GET /api/legacy": legacy,
      "POST /api/legacy/export": { dir: "C:/data/exports/workspace-export-2026-10-06", files: 40 },
      "POST /api/legacy/bring-into-brain": {
        projects_started: ["Website Work"],
        projects_matched: 11,
        projects_left: [],
        notes_proposed: 18,
        files_filed: 3,
        next_steps: 19,
        todos_noted: 26,
        todo_note: "ctx_9",
        refused: [],
        skipped: 0,
      },
    });
    const user = userEvent.setup();
    renderAt(<SettingsPage />, { path: "/settings", route: "/settings?tab=backups" });
    const card = (await screen.findByRole("heading", { name: "Your earlier workspace" })).closest("section") as HTMLElement;
    expect(within(card).getByText(/12 projects, 1 goal, 19 open to-dos, 18 project memories/)).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Copy it out as files" }));
    expect(await within(card).findByText(/Wrote 40 files/)).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Bring it into the Brain" }));
    expect(await within(card).findByRole("status")).toHaveTextContent(
      "Started 1 project (Website Work); matched 11 projects; 18 memories waiting in Catch up; 3 files filed; 19 to-dos made next steps.",
    );
    expect(within(card).getByRole("link", { name: "Open to-dos from the earlier workspace" })).toHaveAttribute("href", "/capture/ctx_9");
    expect(calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual(["/api/legacy/export", "/api/legacy/bring-into-brain"]);
    expect(screen.getByRole("button", { name: "Back up now" })).toBeInTheDocument();
  });
});

describe("running tasks from this computer", () => {
  it("shows each CLI's setup as steps: installed, signed in, ready", async () => {
    mockApi({
      "GET /api/actors": actors,
      "GET /api/providers": [],
      "GET /api/actors/act_claude/credentials": [],
      "GET /api/runners": [
        {
          id: "claude",
          label: "Claude Code",
          provider: "claude-code",
          one_click: true,
          installed: true,
          version: "2.1.272 (Claude Code)",
          signed_in: true,
          install: "npm install -g @anthropic-ai/claude-code",
          sign_in: "claude auth login",
          actor_id: "act_claude",
          detail: "Signed in and ready.",
        },
        {
          id: "codex",
          label: "ChatGPT (Codex CLI)",
          provider: "codex",
          one_click: false,
          installed: false,
          version: null,
          signed_in: null,
          install: "npm install -g @openai/codex",
          sign_in: "codex login",
          actor_id: null,
          detail: "ChatGPT (Codex CLI) is not installed on this computer.",
        },
      ],
    });
    renderAt(<ConnectionsPage />);
    const claudeCard = (await screen.findByRole("heading", { name: "Claude Code" })).closest("li") as HTMLElement;
    expect(within(claudeCard).getByText("Ready to run tasks")).toBeInTheDocument();
    expect(within(claudeCard).getByText(/2\.1\.272/)).toBeInTheDocument();
    const codexCard = screen.getByRole("heading", { name: "ChatGPT (Codex CLI)" }).closest("li") as HTMLElement;
    expect(within(codexCard).getByText("Not installed")).toBeInTheDocument();
    expect(within(codexCard).getByText("npm install -g @openai/codex")).toBeInTheDocument();
    expect(within(codexCard).getByText("codex login")).toBeInTheDocument();
  });
});

describe("connections", () => {
  it("shows the token once with the platform's setup and the worker prompt", async () => {
    mockApi({
      "GET /api/actors": actors,
      "GET /api/providers": [{ id: "claude-code", label: "Claude Code", transport: "http", schedule_hint: "Use /loop." }],
      "GET /api/actors/act_claude/credentials": [],
      "POST /api/connections": {
        actor: actors[1],
        credential: { id: "cred_1", token_hint: "wst_abcd" },
        token: "wst_secret_token",
        setup: { provider: "claude-code", label: "Claude Code", transport: "http", url: "http://127.0.0.1:8787/mcp", schedule_hint: "Use /loop.", file: ".mcp.json", config: '{"mcpServers": {}}' },
        worker_prompt: "Call get_due_tasks.",
      },
    });
    const user = userEvent.setup();
    renderAt(<ConnectionsPage />);
    await user.type(screen.getByLabelText("Name"), "Claude Code");
    await user.click(screen.getByRole("button", { name: "Connect a model" }));
    expect(await screen.findByText("wst_secret_token")).toBeInTheDocument();
    expect(screen.getByText(/shown once/)).toBeInTheDocument();
    expect(screen.getByText("Call get_due_tasks.")).toBeInTheDocument();
  });
});

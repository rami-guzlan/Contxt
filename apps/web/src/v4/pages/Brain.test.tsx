import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { BrainPage, NotePage, SheetPage } from "./Brain";

// Records shaped like the server's, with values no example in the design uses.
const catalog = {
  areas: [
    { key: "craft", label: "Craft rules", description: "How the work is done here.", topics: [] },
    { key: "people", label: "People we know", description: "", topics: [] },
  ],
  entries: [
    { id: "n_quill", title: "Quills are trimmed before noon", summary: "A house habit.", area: "craft", topic: "craft/habits", kind: "fact" },
    { id: "n_ivo", title: "Ivo prefers letters to calls", summary: "", area: "people", topic: "people/ivo", kind: "fact" },
  ],
};
const uses = (d7: number, d30: number, last: string | null = "2026-10-20T10:00:00Z") => ({ total: d30, d7, d30, last });
const inventory = [
  {
    type: "note",
    id: "n_quill",
    title: "Quills are trimmed before noon",
    summary: "",
    kind: "fact",
    area: "craft",
    area_label: "Craft rules",
    topic: "craft/habits",
    topic_label: "Habits",
    scope: "personal",
    partition: null,
    status: "live",
    live: true,
    tokens: 41,
    path: "craft/quills.md",
    owner: "Wren",
    owner_set: true,
    uses: uses(3, 9),
    checked: true,
    origin: { kind: "you", ref: "", label: "Written by you" },
  },
  {
    type: "note",
    id: "n_old",
    title: "The old ledger lives in the cellar",
    summary: "",
    kind: "fact",
    area: "craft",
    area_label: "Craft rules",
    topic: "craft/habits",
    topic_label: "Habits",
    scope: "personal",
    partition: null,
    status: "archived",
    live: false,
    tokens: 12,
    path: "craft/ledger.md",
    owner: "",
    owner_set: false,
    uses: uses(0, 0, null),
  },
];
const proposals = [{ id: "prp_a" }, { id: "prp_b" }];
const brainMap = { lines: ["area Craft rules (1 notes)", "rule Never mail the ledger", "sheet Project status: Status, Latest"], page: 1, pages: 1, levels: {} };
const taste = { lenses: { looks: [], feels: [], works: [] }, words: {}, count: 0 };

function knows(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/brain/catalog": catalog,
    "GET /api/brain/inventory": inventory,
    "GET /api/brain/projects": [],
    "GET /api/work/live": { sheets: [], templates: [], waiting: [] },
    "GET /api/brain/files": { references: [], assets: [], skills: [] },
    "GET /api/brain/proposals": proposals,
    "GET /api/brain/taste": taste,
    "GET /api/brain/map": brainMap,
    "GET /api/brain/goals": { purpose: "Keep the workshop's habits in one place." },
    "GET /api/brain/learned": [],
    "GET /api/brain/gaps": [],
    "GET /api/work/live/project-status": { status: 404, body: { error: { code: "not_found", message: "No sheet project-status." } } },
    ...extra,
  });
}

describe("Brain: What it knows", () => {
  it("shows the Brain's own areas, notes, purpose and must-holds", async () => {
    knows();
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain" });
    expect(await screen.findByText("Keep the workshop's habits in one place.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /Quills are trimmed before noon/ })).toHaveAttribute("href", "/brain/notes/n_quill");
    expect(screen.getAllByText("Craft rules").length).toBeGreaterThan(0);
    // The keyboard alternative to the map: one button per region.
    await user.click(screen.getByRole("button", { name: "Must-holds", pressed: false }));
    expect(await screen.findByText("Never mail the ledger")).toBeInTheDocument();
    // The derived sheet says honestly that it can't be shown here.
    expect(await screen.findByText(/this page can't show its rows yet/)).toBeInTheDocument();
  });

  it("says how many new things wait, and the line can be dismissed", async () => {
    knows();
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain" });
    expect(await screen.findByText(/Your AIs learned 2 new things since you last looked/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Catch up · 2" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/Your AIs learned/)).not.toBeInTheDocument();
  });

  it("shows an empty long-term memory honestly", async () => {
    knows({ "GET /api/brain/catalog": { areas: [], entries: [] }, "GET /api/brain/proposals": [] });
    renderAt(<BrainPage />, { path: "/brain", route: "/brain" });
    expect(await screen.findByText("Nothing in long-term memory yet")).toBeInTheDocument();
    expect(screen.queryByText(/Your AIs learned/)).not.toBeInTheDocument();
  });

  it("says what went wrong when the Brain can't be read, with a retry", async () => {
    knows({ "GET /api/brain/catalog": { status: 500, body: { error: { code: "boom", message: "The Brain could not be read." } } } });
    renderAt(<BrainPage />, { path: "/brain", route: "/brain" });
    expect(await screen.findByText("The Brain could not be read.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try again" }).length).toBeGreaterThan(0);
  });

  it("adds to the taste profile through the taste endpoint", async () => {
    const calls = knows({ "POST /api/brain/taste": { status: "pending", proposal_id: "prp_t", message: "It waits in Catch up." } });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain" });
    await user.click(await screen.findByRole("button", { name: "Customize" }));
    const dialog = screen.getByRole("dialog", { name: "Add to your taste" });
    await user.type(within(dialog).getByLabelText("In your words"), "Margins wide enough to breathe");
    await user.click(within(dialog).getByRole("button", { name: "Always" }));
    await user.click(within(dialog).getByRole("button", { name: "Add it" }));
    expect(await within(dialog).findByText("It waits in Catch up.")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/api/brain/taste");
    expect(sent?.body).toEqual({ text: "Margins wide enough to breathe", lens: "looks", kind: "principle", strength: "always" });
  });
});

describe("Brain: Notes", () => {
  it("lists the inventory by saved view, each note linking to its page", async () => {
    knows();
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=notes" });
    const row = await screen.findByRole("link", { name: /Quills are trimmed before noon/ });
    expect(row).toHaveAttribute("href", "/brain/notes/n_quill");
    expect(within(row).getByText("Wren")).toBeInTheDocument();
    expect(within(row).getByText("3/9")).toBeInTheDocument();
    expect(screen.queryByText("The old ledger lives in the cellar")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archived · 1" }));
    expect(await screen.findByText("The old ledger lives in the cellar")).toBeInTheDocument();
  });
});

describe("Brain: Questions", () => {
  const gaps = [
    { key: "flag:7", kind: "flagged", at: "2026-10-21T09:00:00Z", session_id: "s1", request: "Which kiln runs on Thursdays?", entry: null, close: [] },
    { key: "packet:9", kind: "nothing", at: "2026-10-20T09:00:00Z", session_id: "s2", request: "Who restocks the glaze?", entry: null, close: [] },
  ];

  it("shows what the AIs asked, including what they flagged, and dismisses one", async () => {
    const calls = knows({ "GET /api/brain/gaps": gaps, "POST /api/brain/gaps/dismiss": { status: 204 } });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=questions" });
    expect(await screen.findByText("“Which kiln runs on Thursdays?”")).toBeInTheDocument();
    expect(screen.getByText(/Your AI flagged it/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Questions · 2" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Not needed" })[0]!);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/gaps/dismiss")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/gaps/dismiss")?.body).toEqual({ key: "flag:7" });
  });

  it("answers a question as a proposal that waits for your yes", async () => {
    const calls = knows({ "GET /api/brain/gaps": gaps, "POST /api/brain/proposals": { status: "pending", message: "Waiting.", proposal_id: "prp_q" } });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=questions" });
    await user.click((await screen.findAllByRole("button", { name: "Answer it" }))[1]!);
    await user.type(screen.getByLabelText("Your answer"), "Odile, every Monday");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Answered: Odile, every Monday/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST" && c.path === "/api/brain/proposals")?.body).toEqual({
      title: "Who restocks the glaze?",
      statement: "Odile, every Monday",
    });
  });

  it("says so when there are no questions", async () => {
    knows();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=questions" });
    expect(await screen.findByText("No questions")).toBeInTheDocument();
  });
});

describe("Brain: Try a prompt", () => {
  it("shows the exact packet and how it was built, without saving anything", async () => {
    const calls = knows({
      "GET /api/brain/preview": {
        request: "When are quills trimmed?",
        mode: "lean",
        tokens: 212,
        text: "## Craft rules\n- Quills are trimmed before noon",
        project: null,
        procedure: null,
        candidates: ["n_quill", "n_ivo"],
        notes: [{ id: "n_quill", title: "Quills are trimmed before noon", kind: "fact", topic: "craft/habits", score: 0.81, why: "relevant to the request" }],
        sections: [],
        related: [],
        must_holds: [],
        log: [],
      },
    });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=try" });
    await user.type(await screen.findByLabelText("Your request"), "When are quills trimmed?");
    await user.click(screen.getByRole("button", { name: "Show what it sends" }));
    expect(await screen.findByText(/- Quills are trimmed before noon/)).toBeInTheDocument();
    expect(screen.getByText("2 considered → 1")).toBeInTheDocument();
    expect(screen.getAllByText(/212 tokens/).length).toBeGreaterThan(0);
    const asked = calls.find((c) => c.path.startsWith("/api/brain/preview"));
    expect(asked?.path).toBe("/api/brain/preview?request=When+are+quills+trimmed%3F");
    expect(calls.every((c) => c.method === "GET")).toBe(true);
  });
});

describe("Brain: Test bench", () => {
  it("leaves out an unchecked note without putting anything in its place", async () => {
    const sections = [
      { name: "notes", label: "Notes", tokens: 40, items: [
        { id: "n_quill", title: "Quills are trimmed before noon", why: "relevant to the request", tokens: 25, score: 0.81 },
        { id: "n_ivo", title: "Ivo trims on Fridays", why: "relevant to the request", tokens: 15, score: 0.62 },
      ] },
    ];
    const full = {
      request: "When are quills trimmed?", mode: "standard", tokens: 212, text: "## Notes\n- Quills are trimmed before noon",
      project: null, procedure: null, candidates: ["n_quill", "n_ivo"], notes: [], sections: [], related: [],
      must_holds: [], log: [], packet_sections: sections, packet_tokens: 212, brain_version: "v3", note_ids: ["n_quill", "n_ivo"],
    };
    const calls = knows({
      "GET /api/brain/preview": full,
      "POST /api/brain/preview": { ...full, text: "## Notes\n- Quills are trimmed before noon (custom)", packet_tokens: 197, note_ids: ["n_quill"] },
    });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=try" });
    await user.type(await screen.findByLabelText("Your request"), "When are quills trimmed?");
    await user.click(screen.getByRole("button", { name: "Show what it sends" }));
    expect(await screen.findByText(/Brain v3/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Ivo trims on Fridays/ }));
    expect(await screen.findByText("Custom packet")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/api/brain/preview");
    expect(sent?.body).toEqual({ request: "When are quills trimmed?", exclude: { sections: [], ids: ["n_ivo"] } });
    expect(await screen.findByText(/197 tokens/)).toBeInTheDocument();
  });

  it("estimates first, then runs three panels with the same model and shows what each used", async () => {
    const full = {
      request: "When are quills trimmed?", mode: "standard", tokens: 212, text: "## Notes", project: null, procedure: null,
      candidates: [], notes: [], sections: [], related: [], must_holds: [], log: [], packet_sections: [], packet_tokens: 212,
      brain_version: "v3", note_ids: [],
    };
    const panel = (mode: string, output: string) => ({
      mode, status: "done", output, packet: "", tokens_in: 300, tokens_out: 40, cost: 0.0012, ms: 2100, measured: true, error: null,
    });
    const run = {
      id: "bench_1", status: "done", runner: "claude", model: "claude-haiku-5-5", provider: "Anthropic", brain_version: "v3",
      panels: [panel("none", "No idea."), panel("full", "Before noon."), panel("custom", "Before noon, by Ivo.")],
    };
    const calls = knows({
      "GET /api/brain/preview": full,
      "POST /api/bench/estimate": { provider: "Anthropic", panels: [{ mode: "none", tokens_in: 10, cost: null }, { mode: "full", tokens_in: 300, cost: 0.001 }] },
      "POST /api/bench/runs": { ...run, status: "running" },
      "GET /api/bench/runs/bench_1": run,
    });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=try" });
    await user.type(await screen.findByLabelText("Your request"), "When are quills trimmed?");
    await user.click(screen.getByRole("button", { name: "Show what it sends" }));
    await user.type(await screen.findByLabelText(/Model/), "claude-haiku-5-5");
    await user.click(screen.getByRole("button", { name: "Estimate" }));
    expect(await screen.findByText(/Sends this request and its packet to Anthropic/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/bench/runs")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("Before noon, by Ivo.")).toBeInTheDocument();
    expect(screen.getByText("No idea.")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/api/bench/runs");
    expect(sent?.body).toMatchObject({ request: "When are quills trimmed?", runner: "claude", model: "claude-haiku-5-5" });
    expect(screen.getAllByText(/300 in · 40 out · \$0.0012 · 2.1 s/)).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Re-run" })).toBeInTheDocument();
  });

  it("saves the request as a test, runs its suite, and a person's score is sent", async () => {
    const full = {
      request: "When are quills trimmed?", mode: "standard", tokens: 212, text: "## Notes", project: null, procedure: null,
      candidates: [], notes: [], sections: [], related: [], must_holds: [], log: [], packet_sections: [], packet_tokens: 212,
      brain_version: "v3", note_ids: [],
    };
    const test = { id: "quills", suite: "quality", name: "Quills", request: "When are quills trimmed?", rubric: ["Says noon"] };
    const graded = {
      by: "model", overall: 4, reason: "Close.", criteria: [{ criterion: "Says noon", result: "met" }], thumbs: null, edits: null,
    };
    const result = {
      id: "bres_1", test: "quills", mode: "full", output: "Before noon.", error: null, grade_error: null, brain_version: "v3",
      score: graded, model_score: graded,
    };
    const calls = knows({
      "GET /api/brain/preview": full,
      "GET /api/bench/suites": { suites: [{ id: "quality", name: "quality", description: "", after_distill: false, tests: [test] }] },
      "GET /api/bench/summary": { by_mode: [], suites: [], sections: [], sections_note: "A signal, not proof.", scored: 0 },
      "POST /api/bench/suites/quality/tests": test,
      "POST /api/bench/suites/quality/run": { id: "bsuite_1", suite: "quality", status: "running", tests: 1 },
      "GET /api/bench/suite-runs/bsuite_1": { id: "bsuite_1", suite: "quality", status: "done", tests: 1, error: null, results: [result] },
      "POST /api/bench/results/bres_1/score": { ...result, score: { ...graded, by: "human", overall: 5 } },
    });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=try" });
    await user.type(await screen.findByLabelText("Your request"), "When are quills trimmed?");
    await user.click(screen.getByRole("button", { name: "Show what it sends" }));
    await user.type(await screen.findByLabelText("Test name"), "Quills");
    await user.type(screen.getByLabelText("Rubric"), "Says noon");
    await user.click(screen.getByRole("button", { name: "Save test" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/bench/suites/quality/tests")).toBe(true));
    const saved = calls.find((c) => c.method === "POST" && c.path === "/api/bench/suites/quality/tests");
    expect(saved?.body).toMatchObject({ name: "Quills", request: "When are quills trimmed?", rubric: ["Says noon"] });
    await user.click(await screen.findByRole("button", { name: "Run suite" }));
    expect(await screen.findByText(/Grader 4\/5, Close\./)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Edits needed"), "none");
    await user.click(screen.getByRole("button", { name: "Good" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/bench/results/bres_1/score")).toBe(true));
    const scored = calls.find((c) => c.path === "/api/bench/results/bres_1/score");
    expect(scored?.body).toEqual({ thumbs: "up", edits: "none", note: "" });
  });

  it("sets what counts as a drop and shows what each distill costs a suite that runs after it", async () => {
    const full = {
      request: "When are quills trimmed?", mode: "standard", tokens: 212, text: "## Notes", project: null, procedure: null,
      candidates: [], notes: [], sections: [], related: [], must_holds: [], log: [], packet_sections: [], packet_tokens: 212,
      brain_version: "v3", note_ids: [],
    };
    const test = { id: "quills", suite: "quality", name: "Quills", request: "When are quills trimmed?", rubric: ["Says noon"] };
    const calls = knows({
      "GET /api/brain/preview": full,
      "GET /api/bench/suites": { suites: [{ id: "quality", name: "quality", description: "", after_distill: true, tests: [test] }] },
      "GET /api/bench/summary": { by_mode: [], suites: [], sections: [], sections_note: "A signal, not proof.", scored: 0 },
      "GET /api/bench/settings": { fall: 1, met_to_missed: true, liked_floor: 2, daily_cap: 20 },
      "PUT /api/bench/settings": { fall: 2, met_to_missed: true, liked_floor: 2, daily_cap: 20 },
      "GET /api/bench/suites/quality/estimate": {
        tests: 1, tokens: 1800, cost: 0.0042, provider: "Anthropic", grader: "claude-haiku-5-5", daily_cap: 20,
      },
    });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=try" });
    await user.type(await screen.findByLabelText("Your request"), "When are quills trimmed?");
    await user.click(screen.getByRole("button", { name: "Show what it sends" }));
    expect(await screen.findByText(/Each distill: 1 tests, about 1,800 tokens to Anthropic \(about \$0.0042\)/)).toBeInTheDocument();
    await user.selectOptions(await screen.findByLabelText("Grade falls by"), "2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path === "/api/bench/settings")).toBe(true));
    expect(calls.find((c) => c.method === "PUT" && c.path === "/api/bench/settings")?.body).toEqual({ fall: 2 });
  });
});

describe("Brain: World", () => {
  it("draws regions, entries and relationships, and says why two are connected", async () => {
    knows({
      "GET /api/brain/world": {
        overview: { text: "Northwind is a small design studio.", state: "draft" },
        regions: [
          { id: "proj-site", label: "Website Redesign", kind: "project", status: "active" },
          { id: "area:rules", label: "Rules", kind: "area", status: "" },
        ],
        entries: [
          { id: "rules-style-002", title: "Headlines", region: "area:rules", level: "kept", kind: "rule" },
          { id: "rules-why", title: "Why sentence case", region: "area:rules", level: "confirmed", kind: "rule" },
        ],
        edges: [{ from: "rules-why", to: "rules-style-002", type: "explains", source: "relates" }],
        timeline: [{ what: "kept", id: "rules-why", title: "Why sentence case", recorded: "2026-10-25T10:00:00Z" }],
        lore: [],
        apps: [{ name: "Claude Code", seen: "2026-10-26T09:00:00Z", conversations: 3 }],
        edge_types: ["supersedes", "explains"],
      },
    });
    const user = userEvent.setup();
    const { container } = renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=world" });
    expect(await screen.findByText(/draft, not kept/)).toBeInTheDocument();
    expect(screen.getByText("Northwind is a small design studio.")).toBeInTheDocument();
    expect(screen.getByText(/Claude Code: 3 conversations/)).toBeInTheDocument();
    expect(screen.getByText(/kept: Why sentence case/)).toBeInTheDocument();
    const line = container.querySelector("line");
    expect(line).not.toBeNull();
    await user.click(line as Element);
    expect(await screen.findByText(/rules-why explains rules-style-002, from its relates/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Relationship type"), "supersedes");
    expect(container.querySelector("line")).toBeNull();
  });

  it("records the visit and shows what moved since the one before", async () => {
    const world = {
      overview: { text: "", state: "none" }, regions: [], entries: [], edges: [], lore: [], apps: [], edge_types: [],
      timeline: [], last_visit: "2026-10-20T09:00:00Z",
    };
    const calls = knows({ "GET /api/brain/world": world, "POST /api/brain/world/visit": { visited: "2026-10-26T10:00:00Z" } });
    const user = userEvent.setup();
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=world" });
    const button = await screen.findByRole("button", { name: "Since my last visit" });
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/world/visit")).toBe(true));
    await user.click(button);
    expect(await screen.findByText(/since your last visit \(2026-10-20\)/)).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.some((c) => c.method === "GET" && c.path.startsWith("/api/brain/world?") && c.path.includes("2026-10-20"))).toBe(true),
    );
  });
});

describe("Brain: Files", () => {
  it("lists documents and assets, each downloadable", async () => {
    knows({
      "GET /api/brain/files": {
        references: [{ path: "refs/kiln-guide.pdf", kind: "reference", title: "Kiln guide", size: 2048, mime: "application/pdf", updated: null, description: "", entry_id: null, original: null }],
        assets: [],
        skills: [],
      },
    });
    renderAt(<BrainPage />, { path: "/brain", route: "/brain?tab=files" });
    const card = await screen.findByRole("link", { name: /Kiln guide/ });
    expect(card).toHaveAttribute("href", "/api/brain/files/content?path=refs%2Fkiln-guide.pdf");
    expect(within(card).getByText(/2 KB/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ a note's page

const entry = {
  id: "n_quill",
  title: "Quills are trimmed before noon",
  text: "Quills are trimmed before noon, maybe earlier in winter.",
  scope: "personal",
  kind: "fact",
  status: "live",
  revision: "abc1234",
  summary: "",
  confidence: null,
  verified: null,
  stale: false,
  stale_reason: null,
  source: null,
  path: "craft/quills.md",
  said_by: "Wren",
};
const versions = [
  { ref: "current", at: "2026-10-21T10:00:00Z", title: entry.title, summary: "", status: "live", hash: "h2", chars: 56, text_changed: true, current: true, committed: false, changes: [] },
  { ref: "def5678", at: "2026-10-01T10:00:00Z", title: entry.title, summary: "", status: "live", hash: "h1", chars: 40, text_changed: true, committed: true, message: "Kept from a meeting", changes: [] },
];

function note(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/brain/entries/n_quill": entry,
    "GET /api/brain/entries/n_quill/details": { ...inventory[0], checked: false, load: "on-demand", origin: { kind: "capture", ref: "cap_9", label: "From the Tuesday meeting" } },
    "GET /api/brain/entries/n_quill/versions/current": {
      ...versions[0],
      body: entry.text,
      meta: { statement_status: "tentative", source_id: "context_item:cap_9", source_version: "3", source_excerpt: "we trim them before noon, maybe", source_speaker: "Wren" },
    },
    "GET /api/brain/entries/n_quill/versions": versions,
    "GET /api/brain/entries/n_quill/versions/def5678": { ...versions[1], body: "Quills are trimmed before noon." },
    "GET /api/brain/entries/n_quill/history": [{ at: "2026-10-21T10:00:00Z", action: "edit", by: "Owner" }],
    "POST /api/brain/decisions": { results: [{ id: "n_quill", action: "edit", ok: true, message: "Saved.", data: {} }], checkpoint: null },
    ...extra,
  });
}

describe("A note's page", () => {
  it("shows the current version, its statement status in words, and opens the original at the cited version", async () => {
    note();
    renderAt(<NotePage />, { path: "/brain/notes/:noteId", route: "/brain/notes/n_quill" });
    expect(await screen.findByRole("heading", { name: "Quills are trimmed before noon" })).toBeInTheDocument();
    expect(screen.getByText("Quills are trimmed before noon, maybe earlier in winter.")).toBeInTheDocument();
    expect((await screen.findAllByText("Tentative: it was said with a hedge")).length).toBeGreaterThan(0);
    const original = await screen.findByRole("link", { name: /Open original at version 3/ });
    expect(original).toHaveAttribute("href", "/capture/cap_9?version=3");
    expect(screen.getByRole("button", { name: /When relevant/, pressed: true })).toBeInTheDocument();
  });

  it("corrects the record itself with an edit decision", async () => {
    const calls = note();
    const user = userEvent.setup();
    renderAt(<NotePage />, { path: "/brain/notes/:noteId", route: "/brain/notes/n_quill" });
    await user.click(await screen.findByRole("button", { name: "Edit in your words" }));
    const dialog = screen.getByRole("dialog", { name: "Say it your way" });
    const box = within(dialog).getByLabelText("The note's text");
    await user.clear(box);
    await user.type(box, "Quills are trimmed before noon.");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.find((c) => c.method === "POST" && c.path === "/api/brain/decisions")?.body).toEqual({
      decisions: [{ action: "edit", entry_id: "n_quill", body: "Quills are trimmed before noon." }],
    });
  });

  it("changes when it's sent with an update decision", async () => {
    const calls = note();
    const user = userEvent.setup();
    renderAt(<NotePage />, { path: "/brain/notes/:noteId", route: "/brain/notes/n_quill" });
    await user.click(await screen.findByRole("button", { name: /Only when asked for/ }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "update", entry_id: "n_quill", fields: { load: "manual" } }],
      }),
    );
  });

  it("keeps earlier versions as they were, opens one and brings it back", async () => {
    const calls = note({ "POST /api/brain/decisions": { results: [{ id: "n_quill", action: "restore", ok: true, message: "Restored.", data: {} }], checkpoint: null } });
    const user = userEvent.setup();
    renderAt(<NotePage />, { path: "/brain/notes/:noteId", route: "/brain/notes/n_quill?view=versions" });
    expect(await screen.findByText("Kept from a meeting")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Open as it was" })[1]!);
    expect(await screen.findByText("Quills are trimmed before noon.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Bring back" }));
    await user.click(screen.getByRole("button", { name: "Bring it back" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "restore", entry_id: "n_quill", ref: "def5678" }],
      }),
    );
  });

  it("says when the note can't be found", async () => {
    mockApi({});
    renderAt(<NotePage />, { path: "/brain/notes/:noteId", route: "/brain/notes/n_none" });
    expect(await screen.findByText("Not found")).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ a sheet's page

const sheetView = {
  sheet: {
    id: "kilns",
    title: "Kiln bookings",
    key: "Kiln",
    columns: [
      { name: "Kiln", type: "text", friction: "free", age_days: null, source: "", sensitivity: "", options: [], ref: "", formula: "" },
      { name: "Booked by", type: "person", friction: "free", age_days: null, source: "", sensitivity: "", options: [], ref: "", formula: "" },
    ],
    partition_by: "",
    scope: "",
    template: "",
    builtin: false,
    description: "Who has which kiln this week.",
  },
  rows: [
    {
      id: "row_1",
      key: "North kiln",
      aliases: [],
      partition: "",
      created: "",
      updated: "",
      cells: { "Booked by": { value: "Odile", at: "2026-10-21T08:00:00Z", by: "Owner", said_by: "", as_of: "", source: "you", ai: false, stale: false } },
      computed: {},
      pending: [{ kind: "suggest", id: "ev_5", event: "ev_5", column: "Booked by", value: "Ivo", at: "2026-10-22T08:00:00Z", by: "Claude Code", source: "a chat" }],
    },
  ],
  summary: { rows: 1, columns: {} },
};

describe("A sheet's page", () => {
  it("shows the grid and a cell's history, and writes a new value", async () => {
    const calls = mockApi({
      "GET /api/work/live/kilns": sheetView,
      "GET /api/work/live/kilns/history": [
        { kind: "write", at: "2026-10-21T08:00:00Z", column: "Booked by", value: "Odile", by: "Owner", source: "you" },
        { kind: "write", at: "2026-10-14T08:00:00Z", column: "Booked by", value: "Wren", by: "Owner", source: "a meeting" },
      ],
      "POST /api/work/live/act": sheetView,
    });
    const user = userEvent.setup();
    renderAt(<SheetPage />, { path: "/brain/sheets/:sheetId", route: "/brain/sheets/kilns" });
    expect(await screen.findByRole("heading", { name: "Kiln bookings" })).toBeInTheDocument();
    await user.click(screen.getByRole("cell", { name: "North kiln, Booked by: Odile" }));
    expect(await screen.findByText("Wren")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/work/live/kilns/history?row=row_1&column=Booked+by")).toBe(true);
    expect(screen.getByText("SUGGESTED CHANGE")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Update Booked by"), "Ivo");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/work/live/act")?.body).toEqual({
        action: "write",
        fields: { sheet: "kilns", row: "row_1", values: { "Booked by": "Ivo" } },
      }),
    );
  });

  it("keeps an AI's suggested value with a decide action", async () => {
    const calls = mockApi({ "GET /api/work/live/kilns": sheetView, "GET /api/work/live/kilns/history": [], "POST /api/work/live/act": sheetView });
    const user = userEvent.setup();
    renderAt(<SheetPage />, { path: "/brain/sheets/:sheetId", route: "/brain/sheets/kilns" });
    await user.click(await screen.findByRole("cell", { name: "North kiln, Booked by: Odile" }));
    await user.click(screen.getByRole("button", { name: "Keep" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "decide", fields: { sheet: "kilns", row: "row_1", event: "ev_5", accept: true } }),
    );
  });

  it("says honestly when a derived sheet can only be read through the Brain", async () => {
    mockApi({ "GET /api/work/live/open-loops": { status: 404, body: { error: { code: "not_found", message: "No sheet." } } } });
    renderAt(<SheetPage />, { path: "/brain/sheets/:sheetId", route: "/brain/sheets/open-loops" });
    expect(await screen.findByText("Worked out by the Brain, not stored here")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Open loops this week" })).toBeInTheDocument();
  });
});

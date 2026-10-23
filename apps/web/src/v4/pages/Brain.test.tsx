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

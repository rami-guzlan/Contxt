import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ContextPreview } from "../../components/ContextPreview";
import { actors, mockApi, renderAt } from "../../test/render";
import { BrainLayout } from "./BrainLayout";
import { FilesPage, documentBody } from "./Files";
import { ActivityPage } from "./Activity";
import { EntryPage } from "./Entry";
import { GapsPage } from "./Gaps";
import { HistoryPage } from "./History";
import { InventoryPage } from "./Inventory";
import { SkillPage, SkillsPage } from "../work/Skills";
import { KnowsPage } from "./Knows";
import { PoliciesPage } from "./Policies";
import { ReviewPage, proposerName } from "./Review";

const entrySummary = {
  scope: "company",
  partition: null,
  added: "2026-01-02",
  verified: "2026-09-01",
  confidence: null,
  stale_reason: null,
  standing: false,
  file: null,
};

const catalog = {
  areas: [
    {
      key: "company",
      label: "Company",
      description: "Who we are",
      topics: [{ key: "company/about", label: "About", description: "the basics", entries: 1 }],
    },
    {
      key: "brand",
      label: "Brand",
      description: "How we sound",
      topics: [{ key: "brand/voice", label: "Voice", description: "tone and words", entries: 2 }],
    },
  ],
  entries: [
    {
      ...entrySummary,
      id: "facts-founding",
      title: "Founded in 2011",
      summary: "A small studio with big clients.",
      area: "company",
      topic: "company/about",
      kind: "fact",
      standing: true,
    },
    {
      ...entrySummary,
      id: "rules-voice",
      title: "Plain words",
      summary: "No hype, no jargon.",
      area: "brand",
      topic: "brand/voice",
      kind: "rule",
    },
    {
      ...entrySummary,
      id: "rules-old-tagline",
      title: "Old tagline",
      summary: "A retired slogan.",
      area: "brand",
      topic: "brand/voice",
      kind: "rule",
      stale_reason: "review was due 2026-06-01",
    },
  ],
};

const files = {
  references: [
    {
      path: "references/style-guide.md",
      kind: "reference",
      title: "Style guide",
      size: 2048,
      mime: "text/markdown",
      updated: "2026-09-01T10:00:00Z",
      description: "How we write and lay out pages.",
      entry_id: "rules-style-003",
      original: "Style guide.pdf",
    },
  ],
  assets: [
    {
      path: "assets/brand/logo.png",
      kind: "asset",
      title: "Logo",
      size: 5120,
      mime: "image/png",
      updated: null,
      description: "",
      entry_id: "logo-pointer",
      original: null,
    },
  ],
  skills: [
    {
      name: "brand-sheet",
      category: "design",
      description: "A one-page brand sheet for a client.",
      when_to_use: "",
      path: "skills/design/brand-sheet",
      files: [
        {
          path: "skills/design/brand-sheet/SKILL.md",
          kind: "skill",
          title: "SKILL.md",
          size: 400,
          mime: "text/markdown",
          updated: null,
          description: "",
          entry_id: null,
          original: null,
        },
        {
          path: "skills/design/brand-sheet/wordmark.png",
          kind: "skill",
          title: "wordmark.png",
          size: 900,
          mime: "image/png",
          updated: null,
          description: "",
          entry_id: null,
          original: null,
        },
      ],
    },
  ],
};

const proposal = {
  id: "launch-day",
  kind: "note.create",
  scope: "company",
  route_key: "rules/delivery",
  title: "Launch day",
  body: "Client sites launch on **Tuesdays**.",
  proposer: "model:Claude Code (act_claude)",
  created: "2026-09-28T12:00:00Z",
  reason: "rule proposed from the workspace",
  sources: ["context_item:ctx_1", "task:task_9", "run:run_3"],
  task_id: "task_9",
  target: { evidence: "Launch timing note" },
};

describe("the Brain's frame", () => {
  it("frames the Brain with what it knows, its notes, files and the questions it could not answer", async () => {
    mockApi({
      "GET /api/brain/status": { available: true, name: "Northwind Studio Brain" },
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/files": files,
      "GET /api/brain/gaps?days=30": [{ key: "k", kind: "nothing" }],
    });
    renderAt(<BrainLayout />, { path: "/brain", route: "/brain" });
    expect(await screen.findByRole("heading", { level: 1, name: "Brain" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Brain sections" });
    expect(within(nav).getByRole("link", { name: "What it knows" })).toHaveAttribute("href", "/brain");
    expect(within(nav).getByRole("link", { name: "Notes" })).toHaveAttribute("href", "/brain/entries");
    expect(within(nav).getByRole("link", { name: "Files" })).toHaveAttribute("href", "/brain/files");
    expect(within(nav).queryByRole("link", { name: "History" })).not.toBeInTheDocument(); // in Activity now
    expect(await within(nav).findByRole("link", { name: /Questions/ })).toHaveTextContent("1");
    expect(screen.getByText("Notes", { selector: "dt" }).nextElementSibling).toHaveTextContent("3");
  });

  it("explains how to connect a Brain when there is none", async () => {
    mockApi({ "GET /api/brain/status": { available: false, reason: "No Brain is configured." } });
    renderAt(<BrainLayout />, { path: "/brain", route: "/brain" });
    expect(await screen.findByText(/uv run contxt setup/)).toBeInTheDocument();
  });
});

const uses = (d7: number, d30: number, total: number, last: string | null = null) => ({ d7, d30, total, last });
const row = {
  type: "note" as const,
  kind: "rule",
  scope: "company",
  partition: null,
  status: "approved",
  live: true,
  load: "on-demand",
  tokens: 40,
  path: "knowledge/x.md",
  owner: "person:alex",
  owner_set: false,
  added: "2026-01-02",
  updated: "2026-01-02",
  revised: "2026-01-02",
  verified: "2026-09-01",
  checked: true,
  confidence: null,
  stale: null,
  review_days: 0,
  review_due: null,
  origin: { kind: "you", ref: "", label: "" },
  classification: "internal",
  supersedes: [],
  superseded_by: null,
  changes: 1,
  hash: "h",
};
const inventory = [
  {
    ...row,
    id: "facts-founding",
    title: "Founded in 2011",
    summary: "A small studio with big clients.",
    kind: "fact",
    area: "company",
    area_label: "Company",
    topic: "company/about",
    topic_label: "About",
    load: "standing",
    uses: uses(3, 9, 40, "2026-10-04"),
  },
  {
    ...row,
    id: "rules-voice",
    title: "Plain words",
    summary: "No hype, no jargon.",
    area: "brand",
    area_label: "Brand",
    topic: "brand/voice",
    topic_label: "Voice",
    owner: "person:sam",
    owner_set: true,
    origin: { kind: "conversation", ref: "sess-1", label: "proposed by person:alex" },
    checked: false,
    tokens: 900,
    uses: uses(0, 2, 2, "2026-09-20"),
  },
  {
    ...row,
    id: "rules-old-tagline",
    title: "Old tagline",
    summary: "A retired slogan.",
    area: "brand",
    area_label: "Brand",
    topic: "brand/voice",
    topic_label: "Voice",
    stale: "review was due 2026-06-01",
    uses: uses(0, 0, 0, null),
  },
  {
    ...row,
    id: "rules-first-tagline",
    title: "First tagline",
    summary: "Replaced long ago.",
    area: "brand",
    area_label: "Brand",
    topic: "brand/voice",
    topic_label: "Voice",
    status: "archived",
    live: false,
    superseded_by: "rules-old-tagline",
    uses: uses(0, 0, 5, "2026-03-01"),
  },
  {
    type: "skill" as const,
    id: "brand-sheet",
    title: "brand-sheet",
    summary: "A one-page brand sheet.",
    kind: "skill",
    area: "skills",
    area_label: "Skills",
    topic: "skills/design",
    topic_label: "Design",
    scope: "company",
    partition: null,
    status: "approved",
    live: true,
    tokens: 300,
    path: "skills/design/brand-sheet/SKILL.md",
    owner: "person:alex",
    owner_set: false,
    uses: uses(1, 1, 1, "2026-10-04"),
  },
];
const policies = {
  review_days: {},
  default_owner: "person:alex",
  auto_apply_own_scope: true,
  auto_apply_scopes: [],
  max_proposals_per_session: 12,
  retention_days: 90,
  approver: "person:alex",
  areas: ["company", "brand"],
  kinds: ["identity", "rule", "fact", "state", "focus"],
  scopes: ["company", "person:alex", "person:sam"],
};

describe("brain inventory", () => {
  const titles = () => screen.getAllByRole("row").slice(1).map((r) => within(r).queryAllByRole("link")[0]?.textContent);

  it("lists what the Brain holds with its owner, use and checks, and views find what needs a hand", async () => {
    mockApi({ "GET /api/brain/inventory": inventory, "GET /api/brain/policies": policies });
    const user = userEvent.setup();
    renderAt(<InventoryPage />, { path: "/brain/entries", route: "/brain/entries" });
    expect(await screen.findByRole("link", { name: "Founded in 2011" })).toHaveAttribute("href", "/brain/entries/facts-founding");
    expect(titles()).toEqual(["Old tagline", "Plain words", "Founded in 2011"]);
    const voice = screen.getByRole("link", { name: "Plain words" }).closest("tr")!;
    expect(voice).toHaveTextContent("Sam");
    expect(voice).toHaveTextContent("0 / 2");
    expect(voice).toHaveTextContent("not yet");
    expect(screen.getByRole("link", { name: "Founded in 2011" }).closest("tr")).toHaveTextContent("You");
    expect(screen.getByRole("button", { name: /^Due for a check/ })).toHaveTextContent("1");

    await user.click(screen.getByRole("button", { name: /^Due for a check/ }));
    expect(titles()).toEqual(["Old tagline"]);
    await user.click(screen.getByRole("button", { name: /^From AI, never checked/ }));
    expect(titles()).toEqual(["Plain words"]);
    await user.click(screen.getByRole("button", { name: /^Heaviest/ }));
    expect(titles()[0]).toBe("Plain words");
    await user.click(screen.getByRole("button", { name: /^Archived/ }));
    expect(titles()).toEqual(["First tagline"]);
    await user.click(screen.getByRole("button", { name: /^Skills and documents/ }));
    expect(titles()).toEqual(["brand-sheet"]);
  });

  it("filters, sorts, groups and shows the columns you pick", async () => {
    mockApi({ "GET /api/brain/inventory": inventory, "GET /api/brain/policies": policies });
    const user = userEvent.setup();
    renderAt(<InventoryPage />, { path: "/brain/entries", route: "/brain/entries?area=brand" });
    await screen.findByRole("link", { name: "Plain words" });
    expect(titles()).toEqual(["Old tagline", "Plain words"]);
    await user.type(screen.getByRole("searchbox", { name: "Filter by words" }), "hype");
    expect(titles()).toEqual(["Plain words"]);
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await user.click(screen.getByRole("button", { name: "Uses 7 / 30 days" }));
    await user.click(screen.getByRole("button", { name: /Uses 7 \/ 30 days/ }));
    expect(titles()[0]).toBe("Founded in 2011"); // most used first
    await user.selectOptions(screen.getByRole("combobox", { name: /Group by/ }), "owner");
    expect(screen.getByText(/^You/, { selector: "tr.group-row th" })).toBeInTheDocument();
    expect(screen.getByText(/^Sam/, { selector: "tr.group-row th" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Origin" })).not.toBeInTheDocument();
    await user.click(screen.getByText("Columns"));
    await user.click(screen.getByRole("checkbox", { name: "Origin" }));
    expect(screen.getByRole("button", { name: "Origin" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plain words" }).closest("tr")).toHaveTextContent("An AI conversation");
  });

  it("does not repeat a summary that only restates the title", async () => {
    const base = inventory[1]!;
    const items = [
      { ...base, id: "a", title: "Plain words, no hype.", summary: "Plain words, no hype." },
      { ...base, id: "b", title: "Headlines stay under nine words and...", summary: "Headlines stay under nine words and state one benefit." },
      { ...base, id: "c", title: "Launch day", summary: "Launch day is a Tuesday." },
    ];
    mockApi({ "GET /api/brain/inventory": items, "GET /api/brain/policies": policies });
    renderAt(<InventoryPage />, { path: "/brain/entries", route: "/brain/entries" });
    expect(await screen.findByText("Plain words, no hype.")).toBeInTheDocument();
    expect(screen.queryByText("Headlines stay under nine words and state one benefit.")).not.toBeInTheDocument();
    expect(screen.getByText("Launch day is a Tuesday.")).toBeInTheDocument();
  });

  it("checks the selected entries, or says they need an update, each batch one undo point", async () => {
    const calls = mockApi({
      "GET /api/brain/inventory": inventory,
      "GET /api/brain/policies": policies,
      "GET /api/actors": actors,
      "POST /api/brain/decisions": { results: [], checkpoint: { ...checkpoint, label: "Verified 2" } },
    });
    const user = userEvent.setup();
    renderAt(<InventoryPage />, { path: "/brain/entries", route: "/brain/entries?area=brand" });
    await user.click(await screen.findByRole("checkbox", { name: "Select every note shown" }));
    expect(screen.getByRole("form", { name: "Change the selected notes" })).toHaveTextContent("2 notes selected");
    await user.selectOptions(screen.getByRole("combobox", { name: "What to do" }), "verify");
    await user.click(screen.getByRole("button", { name: "Apply to 2 notes" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [
          { action: "verify", entry_id: "rules-old-tagline" },
          { action: "verify", entry_id: "rules-voice" },
        ],
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Verified 2. Undo point saved.");

    await user.click(screen.getByRole("checkbox", { name: "Select Plain words" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Old tagline" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "What to do" }), "mark");
    await user.type(screen.getByLabelText("Why"), "Say it for plant managers");
    await user.click(screen.getByRole("button", { name: "Apply to 2 notes" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/brain/decisions")).toHaveLength(2));
    expect(calls.filter((c) => c.path === "/api/brain/decisions").at(-1)?.body).toEqual({
      decisions: [
        { action: "mark", entry_id: "rules-old-tagline", state: "stale", reason: "Say it for plant managers" },
        { action: "mark", entry_id: "rules-voice", state: "stale", reason: "Say it for plant managers" },
      ],
    });
  });

  it("asks why before marking stale, and brings archived entries back", async () => {
    const calls = mockApi({
      "GET /api/brain/inventory": inventory,
      "GET /api/brain/policies": policies,
      "GET /api/actors": actors,
      "POST /api/brain/decisions": { results: [], checkpoint: { ...checkpoint, label: "Brought back 1" } },
    });
    const user = userEvent.setup();
    renderAt(<InventoryPage />, { path: "/brain/entries", route: "/brain/entries" });
    await user.click(await screen.findByRole("checkbox", { name: "Select Plain words" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "What to do" }), "mark");
    await user.click(screen.getByRole("button", { name: "Apply to 1 note" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Say why");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(screen.getByRole("button", { name: /^Archived/ }));
    await user.click(screen.getByRole("checkbox", { name: "Select First tagline" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "What to do" }), "unarchive");
    await user.click(screen.getByRole("button", { name: "Apply to 1 note" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "unarchive", entry_id: "rules-first-tagline", reason: "" }],
      }),
    );
  });
});

describe("brain entry", () => {
  const entry = {
    id: "rules-old-tagline",
    title: "Old tagline",
    text: "Use **Build better** in every headline.",
    scope: "company",
    kind: "rule",
    status: "approved",
    revision: "2025-01-01",
    summary: "A retired slogan.",
    confidence: null,
    verified: "2025-01-01",
    stale: true,
    stale_reason: "review was due 2026-06-01",
    source: "the 2025 brand book",
    path: "knowledge/brand/voice/old-tagline.md",
  };
  const history = [{ at: "2026-01-02T10:00:00Z", action: "approved", by: "person:alex", proposer: "model:Claude" }];

  it("shows the entry, why it is stale and its history, and the owner confirms it", async () => {
    const calls = mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/entries/rules-old-tagline": entry,
      "GET /api/brain/entries/rules-old-tagline/history": history,
      "POST /api/brain/entries/rules-old-tagline/verify": { ...entry, stale: false, stale_reason: null },
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: "/brain/entries/rules-old-tagline" });
    expect(await screen.findByRole("heading", { level: 1, name: "Old tagline" })).toBeInTheDocument();
    expect(screen.getByText(/review was due 2026-06-01/)).toBeInTheDocument();
    expect(screen.getByText("Build better").tagName).toBe("STRONG");
    expect(await screen.findByText(/Approved by Alex, proposed by Claude/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Brand" })).toHaveAttribute("href", "/brain/entries?area=brand");
    await user.click(screen.getByRole("button", { name: "Still true" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/verify"))).toBe(true));
  });

  it("quotes why someone marked an entry stale", async () => {
    mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/entries/rules-old-tagline": { ...entry, stale_reason: "marked stale" },
      "GET /api/brain/entries/rules-old-tagline/history": [
        { at: "2026-09-20T10:00:00Z", action: "marked", state: "stale", by: "person:alex", reason: "The tagline changed in May" },
      ],
    });
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: "/brain/entries/rules-old-tagline" });
    expect(await screen.findByText(/Marked stale: “The tagline changed in May”/)).toBeInTheDocument();
  });

  it("asks why before marking an entry disputed", async () => {
    const calls = mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/entries/rules-old-tagline": entry,
      "GET /api/brain/entries/rules-old-tagline/history": [],
      "POST /api/brain/entries/rules-old-tagline/mark": entry,
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: "/brain/entries/rules-old-tagline" });
    await user.click(await screen.findByRole("button", { name: "Mark disputed" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Say why");
    await user.type(screen.getByLabelText("Why"), "The client still uses it");
    await user.click(screen.getByRole("button", { name: "Mark disputed" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/mark"))?.body).toEqual({
        state: "disputed",
        reason: "The client still uses it",
      }),
    );
  });
});

describe("brain files", () => {
  it("groups every file by where it came from, each opening its Library page", async () => {
    mockApi({
      "GET /api/brain/files": {
        ...files,
        references: [{ ...files.references[0], origin: "capture:recording", scope: "company" }],
      },
      "GET /api/brain/catalog": catalog,
    });
    const user = userEvent.setup();
    renderAt(<FilesPage />, { path: "/brain/files", route: "/brain/files" });
    const capture = await screen.findByRole("region", { name: "Capture" });
    expect(within(capture).getByRole("link", { name: "Style guide" })).toHaveAttribute(
      "href",
      "/work/library/view?path=references%2Fstyle-guide.md",
    );
    expect(within(capture).getByText(/Capture: a recording/)).toBeInTheDocument();
    expect(within(capture).getByText("Yours")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Style guide" })).toHaveAttribute(
      "href",
      "/api/brain/files/content?path=references%2Fstyle-guide.md",
    );
    expect(screen.getByRole("link", { name: /original/i })).toHaveAttribute("href", expect.stringContaining("original=true"));
    // Filed before origins were kept: it waits under "Origin unknown" for one to be set.
    const unknown = screen.getByRole("region", { name: "Origin unknown" });
    expect(within(unknown).getByRole("link", { name: "Open Logo" })).toHaveAttribute(
      "href",
      "/work/library/view?path=assets%2Fbrand%2Flogo.png",
    );
    // a skill's own logos and fonts show with the skill that keeps them
    expect(screen.getByRole("heading", { name: "Kept with /brand-sheet" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "wordmark.png" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Documents" }));
    expect(screen.queryByRole("region", { name: "Origin unknown" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Kept with /brand-sheet" })).not.toBeInTheDocument();
  });

  it("gives skills their own place, by kind, each opening to its procedure", async () => {
    mockApi({
      "GET /api/skills": {
        skills: [
          {
            name: "brand-sheet",
            category: "design",
            description: "A one-page brand sheet for a client.",
            triggers: [],
            artifacts: ["pdf"],
            makes_files: true,
            files: 1,
            last_run: null,
            used_by: [],
            use: "run",
          },
        ],
        waiting: [],
      },
      "GET /api/brain/skills/brand-sheet": {
        ...files.skills[0],
        text: "# /brand-sheet\n\nFolder: skills/design/brand-sheet\n\n# /brand-sheet\n\nMake the sheet.",
        loads: ["brand/voice"],
      },
    });
    const { unmount } = renderAt(<SkillsPage />, { path: "/work/skills", route: "/work/skills" });
    expect(await screen.findByRole("button", { name: "New skill" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Design" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "/brand-sheet" })).toHaveAttribute("href", "/work/skills/brand-sheet");
    expect(screen.getByText("A one-page brand sheet for a client.")).toBeInTheDocument();
    expect(screen.getByText("Makes PDF files")).toBeInTheDocument();
    unmount();
    renderAt(<SkillPage />, { path: "/work/skills/:name", route: "/work/skills/brand-sheet?tab=procedure" });
    expect(await screen.findByRole("heading", { level: 1, name: "/brand-sheet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skills" })).toHaveAttribute("href", "/work/skills");
    expect(screen.getByText("Make the sheet.")).toBeInTheDocument();
    expect(screen.getByText("brand/voice")).toBeInTheDocument();
  });

  it("files a document into a project at once and takes it back with Undo", async () => {
    const calls = mockApi({
      "GET /api/brain/files": files,
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/projects": [campaign],
      "POST /api/brain/files": { status: 201, body: filed },
      "POST /api/brain/checkpoints/cp-1/undo": { undone: "cp-1", checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<FilesPage />, { path: "/brain/files", route: "/brain/files" });
    await user.click(await screen.findByRole("button", { name: "Add a file" }));
    const dialog = screen.getByRole("dialog", { name: "Add a file to the Brain" });
    await user.upload(
      within(dialog).getByLabelText("File"),
      new File(["%PDF"], "Q4 campaign proposal v2.pdf", { type: "application/pdf" }),
    );
    await user.selectOptions(within(dialog).getByLabelText("Project"), "q4-campaign");
    await user.selectOptions(within(dialog).getByLabelText("Which copy is this"), "sent");
    expect(within(dialog).queryByLabelText("Topic")).not.toBeInTheDocument(); // a project places it
    await user.click(within(dialog).getByRole("button", { name: "Add to the Brain" }));
    expect(await within(dialog).findByText(/Your AI can use it now/)).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST" && c.path === "/api/brain/files")?.body as FormData;
    expect(sent.get("project")).toBe("q4-campaign");
    expect(sent.get("status")).toBe("sent");
    expect(sent.get("topic")).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Undo" }));
    expect(await within(dialog).findByText(/Taken back out/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/checkpoints/cp-1/undo")).toBe(true);
  });

  it("starts a new project while filing, with the names you call it", async () => {
    const calls = mockApi({
      "GET /api/brain/files": files,
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/projects": [],
      "POST /api/brain/projects": { status: 201, body: campaign },
      "POST /api/brain/files": { status: 201, body: filed },
    });
    const user = userEvent.setup();
    renderAt(<FilesPage />, { path: "/brain/files", route: "/brain/files" });
    await user.click(await screen.findByRole("button", { name: "Add a file" }));
    const dialog = screen.getByRole("dialog", { name: "Add a file to the Brain" });
    await user.upload(within(dialog).getByLabelText("File"), new File(["# Plan"], "plan.md", { type: "text/markdown" }));
    await user.selectOptions(within(dialog).getByLabelText("Project"), "New project…");
    const add = within(dialog).getByRole("button", { name: "Add to the Brain" });
    expect(add).toBeDisabled(); // a new project needs its name and what it is for
    await user.type(within(dialog).getByLabelText("Project name"), "Q4 campaign proposals");
    await user.type(within(dialog).getByLabelText("What it is for"), "Proposals for the Q4 campaign");
    await user.type(within(dialog).getByLabelText("Other names you call it"), "the campaign proposals, Q4 campaign");
    await user.click(add);
    expect(await within(dialog).findByText(/Your AI can use it now/)).toBeInTheDocument();
    const made = calls.find((c) => c.method === "POST" && c.path === "/api/brain/projects")?.body;
    expect(made).toEqual({
      name: "Q4 campaign proposals",
      summary: "Proposals for the Q4 campaign",
      aliases: ["the campaign proposals", "Q4 campaign"],
    });
    const sent = calls.find((c) => c.method === "POST" && c.path === "/api/brain/files")?.body as FormData;
    expect(sent.get("project")).toBe("q4-campaign");
  });

  it("says when a file waits for review instead", async () => {
    mockApi({
      "GET /api/brain/files": files,
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/projects": [],
      "POST /api/brain/files": {
        status: 201,
        body: { ...filed, status: "pending", message: "Proposed reference pricing.pdf. It waits for review.", checkpoint_id: null },
      },
    });
    const user = userEvent.setup();
    renderAt(<FilesPage />, { path: "/brain/files", route: "/brain/files" });
    await user.click(await screen.findByRole("button", { name: "Add a file" }));
    const dialog = screen.getByRole("dialog", { name: "Add a file to the Brain" });
    await user.upload(within(dialog).getByLabelText("File"), new File(["%PDF"], "pricing.pdf", { type: "application/pdf" }));
    await user.selectOptions(within(dialog).getByLabelText("Topic"), "brand/voice");
    await user.click(within(dialog).getByRole("button", { name: "Add to the Brain" }));
    expect(await within(dialog).findByText(/waits for review/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Review it now" })).toHaveAttribute("href", "/review");
    expect(within(dialog).queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("groups documents by project and says which copy each is", async () => {
    mockApi({
      "GET /api/brain/files": {
        ...files,
        references: [
          ...files.references,
          {
            path: "references/projects/q4-campaign/q4-campaign-proposal.md",
            kind: "reference",
            title: "Q4 campaign proposal",
            size: 4200,
            mime: "text/markdown",
            updated: null,
            description: "Book 40 discovery calls before December.",
            entry_id: "q4-campaign-proposal",
            original: "Q4 campaign proposal v2.pdf",
            project: "q4-campaign",
            project_title: "Q4 campaign proposals",
            version: 2,
            file_status: "sent",
            dated: "2026-10-03",
            sections: 10,
            work: true,
            origin: "project",
            origin_inferred: true,
          },
        ],
      },
      "GET /api/brain/catalog": catalog,
    });
    renderAt(<FilesPage />, { path: "/brain/files", route: "/brain/files" });
    const group = await screen.findByRole("region", { name: "Q4 campaign proposals" });
    expect(within(group).getByText("version 2 · sent · 2026-10-03")).toBeInTheDocument();
    expect(within(group).getByText(/10 parts your AI can quote/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Origin unknown" })).toBeInTheDocument();
  });
});

describe("What your AI gets", () => {
  it("shows each piece of context and why, then the context itself", async () => {
    const calls = mockApi({
      "GET /api/brain/projects": [campaign],
      "GET /api/brain/preview": {
        request: "How much did I set aside for the podcast?",
        mode: "standard",
        tokens: 812,
        text: "## From your files\n\n> Budget: 4,500 dollars.",
        project: null,
        procedure: null,
        candidates: [],
        notes: [{ id: "paid-benchmarks", title: "Paid benchmarks", kind: "fact", topic: "marketing/paid", score: 0.6, why: "relevant to the request" }],
        sections: [
          {
            id: "references/projects/q4-campaign/q4-campaign-proposal.md#5",
            file: "references/projects/q4-campaign/q4-campaign-proposal.md",
            title: "Q4 campaign proposal",
            label: "Podcast sponsorship",
            score: 0.94,
            why: "about what the request asks",
          },
        ],
        related: [],
      },
    });
    const user = userEvent.setup();
    renderAt(<ContextPreview />);
    await user.type(screen.getByLabelText("What you would ask your AI"), "How much did I set aside for the podcast?");
    await user.click(screen.getByRole("button", { name: "Show what it gets" }));
    expect(await screen.findByRole("link", { name: "Q4 campaign proposal" })).toBeInTheDocument();
    expect(screen.getByText(/Podcast sponsorship/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Paid benchmarks" })).toHaveAttribute("href", "/brain/entries/paid-benchmarks");
    expect(screen.getByText("The context itself, about 812 tokens")).toBeInTheDocument();
    const asked = calls.find((c) => c.path.startsWith("/api/brain/preview"));
    expect(asked?.path).toBe("/api/brain/preview?request=How%20much%20did%20I%20set%20aside%20for%20the%20podcast%3F");
  });

  it("says plainly when nothing in the Brain fits", async () => {
    mockApi({
      "GET /api/brain/projects": [],
      "GET /api/brain/preview": {
        request: "What's the capital of Portugal?",
        mode: "lean",
        tokens: 90,
        text: "## Task",
        project: null,
        procedure: null,
        candidates: [],
        notes: [],
        sections: [],
        related: [],
      },
    });
    const user = userEvent.setup();
    renderAt(<ContextPreview />);
    await user.type(screen.getByLabelText("What you would ask your AI"), "What's the capital of Portugal?");
    await user.click(screen.getByRole("button", { name: "Show what it gets" }));
    expect(await screen.findByText(/Nothing in your Brain fits this request/)).toBeInTheDocument();
  });
});

const campaign = {
  id: "q4-campaign",
  title: "Q4 campaign proposals",
  summary: "Proposals for the Q4 campaign",
  status: "active",
  active: true,
  current: "",
  next: "",
  blockers: "",
  updated: null,
  aliases: ["the campaign proposals"],
  files: 0,
  updates: 0,
};

const filed = {
  status: "applied",
  message: "Filed Q4 campaign proposal in the project Q4 campaign proposals. Your AI can use it now: 10 section(s) it can quote.",
  proposal_id: "file-q4-campaign-proposal-abc123",
  entry_id: "q4-campaign-proposal",
  path: "references/projects/q4-campaign/q4-campaign-proposal.md",
  version: 2,
  replaced: null,
  sections: 10,
  project: "q4-campaign",
  checkpoint_id: "cp-1",
};

const noIssues = {
  replaces: [],
  conflicts: [],
  overlaps: [],
  duplicates: [],
  related: [],
  new_topic: false,
  suggested: [],
  base_changed: false,
  problems: [],
  placement: "chosen",
};

const scale = {
  id: "facts-scale",
  title: "Scale and reach",
  summary: "Company figures",
  route_key: "company/about",
  live: true,
  body: "Studio delivers 120+ projects a year.",
};

const figures = {
  id: "studio-figures",
  kind: "note.create",
  scope: "company",
  route_key: "company/about",
  title: "Studio figures",
  body: "Studio delivers 150+ projects a year.",
  proposer: "model:Claude Code (act_claude)",
  created: "2026-09-28T12:05:00Z",
  sources: ["context_item:ctx_1", "task:task_9", "brain:facts-scale"],
  task_id: "task_9",
  target: { evidence: "Deck, slide 4" },
  analysis: { ...noIssues, change: "new", route_key: "company/about", conflicts: [scale] },
};

const reviewBatch = {
  key: "task:task_9",
  title: "Distill the deck into the Brain",
  proposer: "Claude Code",
  created: "2026-09-28T12:00:00Z",
  proposal_ids: ["launch-day", "studio-figures"],
  counts: {
    total: 2,
    new: 2,
    updates: 0,
    replaces: 0,
    conflicts: 1,
    close: 0,
    duplicates: 0,
    problems: 0,
    files: 0,
    new_topics: 0,
    look: 1,
    clear: 1,
  },
  topics: [
    { route_key: "brand/voice", count: 1 },
    { route_key: "company/about", count: 1 },
  ],
  task_id: "task_9",
  task_status: "done",
  documents: [{ id: "ctx_1", title: "deck.pdf" }],
};

const review = {
  batches: [reviewBatch],
  proposals: [
    {
      ...proposal,
      route_key: "brand/voice",
      analysis: { ...noIssues, change: "new", route_key: "brand/voice", placement: "guessed", suggested: [{ topic: "company/about", score: 0.6 }] },
    },
    figures,
  ],
};

const checkpoint = {
  id: "cp_1",
  at: "2026-09-28T12:30:00Z",
  by: "Robin",
  kind: "decisions",
  label: "Approved 1",
  source: { title: "Distill the deck into the Brain", task_id: "task_9" },
  decisions: [{ action: "approved", proposal: "launch-day", note: "launch-day", title: "Launch day" }],
  files: [],
  undoes: null,
  undone_by: null,
  undone_at: null,
  blocked: [],
  undoable: true,
};

describe("brain review", () => {
  it("shows a batch, approves the ready proposals together, and offers an undo", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "POST /api/brain/decisions": { results: [{ id: "launch-day", action: "approve", ok: true, message: "", data: {} }], checkpoint },
      "POST /api/brain/checkpoints/cp_1/undo": { undone: "cp_1", checkpoint: { ...checkpoint, id: "cp_2", kind: "undo", label: "Undo: Approved 1" } },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    expect(within(batch).getByText("Read from deck.pdf", { exact: false })).toBeInTheDocument();
    expect(within(batch).getByRole("heading", { name: /Needs a look/ })).toBeInTheDocument();
    // the ready one is selected; the contradiction waits for a choice
    expect(within(batch).getByRole("checkbox", { name: "Select Launch day" })).toBeChecked();
    expect(within(batch).getByRole("checkbox", { name: "Select Studio figures" })).toBeDisabled();
    expect(within(batch).getByText(/Files under Brand \/ Voice \(placed by guess\)/)).toBeInTheDocument();
    expect(within(batch).getByText(/Approving adds 1 entry/)).toBeInTheDocument();

    await user.click(within(batch).getByRole("button", { name: "Approve 1" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "approve", proposal_id: "launch-day" }],
        source: { title: "Distill the deck into the Brain", task_id: "task_9" },
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Approved 1. Undo point saved.");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/checkpoints/cp_1/undo")).toBe(true));
    expect(await screen.findByRole("button", { name: "Redo" })).toBeInTheDocument();
  });

  it("compares a contradiction side by side and replaces the old entry when asked", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "POST /api/brain/decisions": { results: [], checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    await user.click(within(batch).getByRole("button", { name: /Studio figures/ }));
    expect(within(batch).getByText(/Contradicts “Scale and reach”/)).toBeInTheDocument();
    const before = within(batch).getByRole("region", { name: "In the Brain now" });
    expect(within(before).getByText("120+").tagName).toBe("DEL");
    expect(within(batch).getAllByText("Distill the deck into the Brain").length).toBeGreaterThan(0);
    await user.click(within(batch).getByRole("radio", { name: /Replace “Scale and reach” with this/ }));
    expect(within(batch).getByRole("checkbox", { name: "Select Studio figures" })).toBeChecked();
    await user.click(within(batch).getByRole("checkbox", { name: "Select Launch day" }));
    await user.click(within(batch).getByRole("button", { name: "Approve 1" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
        decisions: [{ action: "approve", proposal_id: "studio-figures", replaces: ["facts-scale"] }],
      }),
    );
  });

  it("moves a proposal to another topic and rejects with a reason", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "POST /api/brain/decisions": { results: [], checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    await user.click(within(batch).getByRole("button", { name: /Launch day/ }));
    expect(within(batch).getByText("Tuesdays").tagName).toBe("STRONG");
    await user.selectOptions(within(batch).getByLabelText("File it under"), "company/about");
    expect(within(batch).getByText(/Files under Company \/ About \(moved\)/)).toBeInTheDocument();
    await user.click(within(batch).getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
        decisions: [{ action: "approve", proposal_id: "launch-day", topic: "company/about" }],
      }),
    );
    await user.click(within(batch).getByRole("button", { name: "Reject 1…" }));
    await user.type(within(batch).getByLabelText("Why reject them"), "Not settled");
    await user.click(within(batch).getByRole("button", { name: "Reject 1" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/api/brain/decisions").at(-1)?.body).toMatchObject({
        decisions: [{ action: "reject", proposal_id: "launch-day", reason: "Not settled" }],
      }),
    );
  });

  it("says when nothing waits", async () => {
    mockApi({ "GET /api/brain/review": { batches: [], proposals: [] }, "GET /api/brain/catalog": catalog });
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    expect(await screen.findByText(/Nothing is waiting/)).toBeInTheDocument();
  });
});

describe("editing before approving", () => {
  it("approves a proposal in the person's own words", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "POST /api/brain/decisions": { results: [], checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    await user.click(within(batch).getByRole("button", { name: /Launch day/ }));
    await user.click(within(batch).getByRole("button", { name: "Edit before approving" }));
    const editor = within(batch).getByRole("group", { name: "Edit Launch day" });
    const text = within(editor).getByLabelText("Text");
    await user.clear(text);
    await user.type(text, "Client sites launch on Tuesdays, never before noon.");
    await user.click(within(editor).getByRole("tab", { name: "Preview" }));
    expect(within(editor).getByText("Client sites launch on Tuesdays, never before noon.")).toBeInTheDocument();
    await user.click(within(editor).getByRole("button", { name: "Keep these edits" }));
    expect(within(batch).getByText("Edited by you")).toBeInTheDocument();
    await user.click(within(batch).getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
        decisions: [{ action: "approve", proposal_id: "launch-day", body: "Client sites launch on Tuesdays, never before noon." }],
      }),
    );
  });

  it("keeps both of two clashing pieces, the older one edited so they stop overlapping", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "GET /api/runners": [],
      "POST /api/brain/decisions": { results: [], checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    await user.click(within(batch).getByRole("button", { name: /Studio figures/ }));
    await user.click(within(batch).getByRole("radio", { name: "Keep both" }));
    await user.click(within(batch).getByRole("button", { name: "Edit “Scale and reach” so both can stand" }));
    const editor = within(batch).getByRole("group", { name: "Edit Scale and reach" });
    const text = within(editor).getByLabelText("Text");
    await user.clear(text);
    await user.type(text, "Company-wide reach only; Studio's hours live in Studio figures.");
    await user.click(within(editor).getByRole("button", { name: "Keep this edit" }));
    expect(within(batch).getByText(/Your edit of “Scale and reach” is saved with this approval/)).toBeInTheDocument();
    await user.click(within(batch).getByRole("checkbox", { name: "Select Launch day" }));
    await user.click(within(batch).getByRole("button", { name: "Approve 1" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
        decisions: [
          { action: "approve", proposal_id: "studio-figures" },
          {
            action: "edit",
            entry_id: "facts-scale",
            body: "Company-wide reach only; Studio's hours live in Studio figures.",
          },
        ],
      }),
    );
  });
});

describe("changing an entry on its page", () => {
  const entry = {
    id: "rules-voice",
    title: "Plain words",
    text: "No hype, no jargon.",
    scope: "company",
    kind: "rule",
    status: "approved",
    revision: "2026-01-02",
    summary: "No hype, no jargon.",
    confidence: null,
    verified: "2026-09-01",
    stale: false,
    stale_reason: null,
    source: null,
    path: "knowledge/brand/voice/plain-words.md",
  };

  it("edits the text in place", async () => {
    const calls = mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/entries/rules-voice": entry,
      "GET /api/brain/entries/rules-voice/history": [],
      "POST /api/brain/decisions": { results: [{ id: "rules-voice", action: "edit", ok: true, message: "", data: {} }], checkpoint },
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: "/brain/entries/rules-voice" });
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const text = screen.getByLabelText("Text");
    await user.clear(text);
    await user.type(text, "No hype, no jargon, no exclamation marks.");
    await user.click(screen.getByRole("button", { name: "Save the note" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [
          { action: "edit", entry_id: "rules-voice", reason: "Edited on its page", body: "No hype, no jargon, no exclamation marks." },
        ],
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Undo point saved");
  });

  it("removes it from the Brain after asking, and undoes that right there", async () => {
    const calls = mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/entries/rules-voice": entry,
      "GET /api/brain/entries/rules-voice/history": [],
      "POST /api/brain/decisions": { results: [], checkpoint: { ...checkpoint, id: "cp_9", label: "Archived 1" } },
      "POST /api/brain/checkpoints/cp_9/undo": { undone: "cp_9", checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: "/brain/entries/rules-voice" });
    await user.click(await screen.findByRole("button", { name: "Remove from the Brain" }));
    await user.type(screen.getByLabelText("Why remove it"), "Merged into the style guide");
    await user.click(screen.getByRole("button", { name: "Remove it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "archive", entry_id: "rules-voice", reason: "Merged into the style guide" }],
      }),
    );
    expect(await screen.findByText(/is removed from the Brain/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/checkpoints/cp_9/undo")).toBe(true));
  });
});

describe("reconciling a clash", () => {
  const runner = {
    id: "claude",
    label: "Claude Code",
    provider: "claude-code",
    one_click: true,
    installed: true,
    version: "2.1",
    signed_in: true,
    install: "",
    sign_in: "",
    actor_id: null,
    detail: "",
  };
  const suggestion = {
    id: "update-facts-scale-1a2b",
    kind: "note.update",
    scope: "company",
    route_key: "company/about",
    title: "Scale and reach",
    body: "Studio delivers 120+ projects a year company-wide; product figures live in Studio figures.",
    proposer: "model:Claude Code (act_claude)",
    created: "2026-09-28T13:00:00Z",
    sources: ["task:task_rec", "run:run_9"],
    task_id: "task_rec",
    analysis: { ...noIssues, change: "update", route_key: "company/about", replaces: [scale] },
  };

  it("asks this computer's Claude Code to rewrite the other piece, and shows it working", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "GET /api/runners": [runner],
      "POST /api/brain/reconcile": { status: 201, body: { id: "task_rec", status: "draft", assignee_id: null } },
      "POST /api/runners/claude/runs": { status: 201, body: { id: "lrun_1" } },
      "GET /api/runners/runs/lrun_1": {
        id: "lrun_1",
        runner: "claude",
        task_id: "task_rec",
        task_title: "Reconcile “Scale and reach” with “Studio figures”",
        actor_id: "act_claude",
        started_by: "act_owner",
        status: "running",
        started_at: "2026-09-28T13:00:00Z",
        finished_at: null,
        exit_code: null,
        summary: "",
        events: [{ seq: 1, at: "2026-09-28T13:00:01Z", kind: "tool", name: "claim_task" }],
      },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    await user.click(within(batch).getByRole("button", { name: /Studio figures/ }));
    expect(within(batch).getByText(/A model rewrites “Scale and reach”/)).toBeInTheDocument();
    await user.click(await within(batch).findByRole("button", { name: "Reconcile with Claude Code" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/runners/claude/runs")?.body).toEqual({ task_id: "task_rec" }),
    );
    expect(calls.find((c) => c.path === "/api/brain/reconcile")?.body).toEqual({
      proposal_id: "studio-figures",
      entry_id: "facts-scale",
      current: "proposal",
    });
    expect(await within(batch).findByRole("log")).toHaveTextContent("claim_task");
  });

  it("shows the suggested rewrite beside the pair and approves both as one", async () => {
    const reconciled = {
      batches: [
        reviewBatch,
        {
          ...reviewBatch,
          key: "task:task_rec",
          title: "Reconcile “Scale and reach” with “Studio figures”",
          proposal_ids: [suggestion.id],
          task_id: "task_rec",
          documents: [],
          reconciles: { proposal_id: "studio-figures", entry_id: "facts-scale", current: "proposal" },
        },
      ],
      proposals: [
        review.proposals[0],
        {
          ...figures,
          reconciliations: [
            { task_id: "task_rec", status: "done", entry_id: "facts-scale", current: "proposal", suggestion_ids: [suggestion.id] },
          ],
        },
        suggestion,
      ],
    };
    const calls = mockApi({
      "GET /api/brain/review": reconciled,
      "GET /api/brain/catalog": catalog,
      "GET /api/runners": [runner],
      "POST /api/brain/decisions": { results: [], checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    // the rewrite waits beside its pair, not as a batch of its own
    expect(screen.queryByRole("region", { name: /^Reconcile/ })).not.toBeInTheDocument();
    await user.click(within(batch).getByRole("button", { name: /Studio figures/ }));
    expect(within(batch).getByText("Suggested change to “Scale and reach” so both can stand:")).toBeInTheDocument();
    await user.click(within(batch).getByRole("button", { name: "Approve both" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toMatchObject({
        decisions: [
          { action: "approve", proposal_id: "studio-figures" },
          { action: "approve", proposal_id: suggestion.id },
        ],
      }),
    );
  });

  it("asks a connected model when no CLI is set up here, with a prompt to paste", async () => {
    const calls = mockApi({
      "GET /api/brain/review": review,
      "GET /api/brain/catalog": catalog,
      "GET /api/runners": [],
      "GET /api/actors": actors,
      "POST /api/brain/reconcile": { status: 201, body: { id: "task_rec2", status: "ready", assignee_id: "act_claude" } },
    });
    const user = userEvent.setup();
    renderAt(<ReviewPage />, { path: "/review", route: "/review" });
    const batch = await screen.findByRole("region", { name: "Distill the deck into the Brain" });
    await user.click(within(batch).getByRole("button", { name: /Studio figures/ }));
    expect(within(batch).getByRole("link", { name: "Set up Claude Code on this computer" })).toHaveAttribute(
      "href",
      "/settings?tab=connections#runners",
    );
    await user.click(within(batch).getByRole("radio", { name: "“Scale and reach”, in the Brain" }));
    await user.click(within(batch).getByRole("button", { name: "Reconcile with a connected model" }));
    expect(within(batch).getByLabelText("Model that reconciles them")).toHaveValue("act_claude");
    await user.click(within(batch).getByRole("button", { name: "Ask it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/reconcile")?.body).toEqual({
        proposal_id: "studio-figures",
        entry_id: "facts-scale",
        current: "entry",
        assignee_id: "act_claude",
      }),
    );
    expect(await within(batch).findByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
  });
});

describe("brain history", () => {
  it("lists undo points and undoes one; a blocked one says what changed", async () => {
    const calls = mockApi({
      "GET /api/brain/checkpoints": [
        checkpoint,
        {
          ...checkpoint,
          id: "cp_0",
          label: "Rejected 2",
          undoable: false,
          blocked: [{ path: "knowledge/a.md", what: "the entry “Plain words”" }],
        },
        { ...checkpoint, id: "cp_old", label: "Archived 1", undone_by: "cp_9", undone_at: "2026-09-28T11:00:00Z", undoable: false },
      ],
      "POST /api/brain/checkpoints/cp_1/undo": { undone: "cp_1", checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<HistoryPage />, { path: "/brain/history", route: "/brain/history" });
    expect(await screen.findByText("Approved 1")).toBeInTheDocument();
    expect(screen.getAllByText(/from Distill the deck into the Brain/)).toHaveLength(3);
    expect(screen.getByText(/the entry “Plain words” changed since/)).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "Undo" });
    expect(buttons).toHaveLength(2); // the undone one has none
    expect(buttons[1]).toBeDisabled();
    await user.click(buttons[0]!);
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/checkpoints/cp_1/undo")).toBe(true));
  });
});

describe("brain helpers", () => {
  it("shows a filed document without the note the Brain adds when filing it", () => {
    const filed = [
      "# Checklist",
      "",
      "> Source: `checklist.pdf`, sha256 `abc`, filed 2026-09-28. Converted text; the original is",
      "> kept in the local library.",
      "",
      "# Checklist",
      "",
      "What every proposal covers.",
    ].join("\n");
    expect(documentBody(filed, "Checklist")).toBe("What every proposal covers.");
    expect(documentBody("# Other\n\nBody", "Checklist")).toBe("# Other\n\nBody");
  });

  it("names who proposed something the way a person would", () => {
    expect(proposerName("model:Claude Code (act_1)")).toBe("Claude Code (a model)");
    expect(proposerName("human:Owner (act_2)")).toBe("Owner");
    expect(proposerName("person:alex")).toBe("person:alex");
    expect(proposerName(undefined)).toBe("someone");
  });
});

describe("an entry's supply chain", () => {
  const entry = {
    id: "rules-voice",
    title: "Plain words",
    text: "No hype, no jargon.",
    scope: "company",
    kind: "rule",
    status: "approved",
    revision: "2026-01-02",
    summary: "No hype, no jargon.",
    confidence: null,
    verified: "2026-09-01",
    stale: false,
    stale_reason: null,
    source: "proposed by person:alex",
    path: "knowledge/brand/voice/plain-words.md",
  };
  const details = { ...inventory[1]!, review_days: 30, review_days_set: true, review_due: "2026-10-20" };
  const base = {
    "GET /api/brain/catalog": catalog,
    "GET /api/brain/entries/rules-voice": entry,
    "GET /api/brain/entries/rules-voice/details": details,
    "GET /api/brain/entries/rules-voice/history": [],
    "GET /api/brain/policies": policies,
    "GET /api/actors": actors,
  };
  const at = "/brain/entries/rules-voice";

  it("says who answers for it, where it came from and when it is next checked", async () => {
    mockApi(base);
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: at });
    expect(await screen.findByText("An AI conversation")).toBeInTheDocument();
    expect(screen.getByText("Sam")).toBeInTheDocument();
    expect(screen.getByText(/every 30 days/)).toBeInTheDocument();
    expect(screen.getByText("2 times in 30 days")).toBeInTheDocument();
  });

  it("changes its details as a decision", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/brain/decisions": { results: [{ id: "rules-voice", action: "update", ok: true, message: "", data: {} }], checkpoint },
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: at });
    await user.click(await screen.findByRole("button", { name: "Change details" }));
    await user.selectOptions(screen.getByLabelText("Owner"), "person:alex");
    await user.clear(screen.getByLabelText("Check every (days)"));
    await user.type(screen.getByLabelText("Check every (days)"), "90");
    await user.selectOptions(screen.getByLabelText("Sensitivity"), "confidential");
    await user.click(screen.getByRole("button", { name: "Save the details" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [
          {
            action: "update",
            entry_id: "rules-voice",
            fields: { owner: "person:alex", review_days: "90", classification: "confidential" },
          },
        ],
      }),
    );
  });

  it("lists its versions and puts an earlier one back", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/brain/entries/rules-voice/versions?text=true": [
        {
          ref: "aaa1111bbbb2",
          at: "2026-10-01T10:00:00Z",
          title: "Plain words",
          summary: "",
          status: "approved",
          hash: "h2",
          chars: 19,
          text_changed: true,
          current: true,
          committed: true,
          message: "Edited rules-voice",
          changes: [{ at: "2026-10-01T10:00:00Z", action: "edited", by: "person:alex", reason: "Shorter" }],
          body: "No hype, no jargon.",
        },
        {
          ref: "ccc3333dddd4",
          at: "2026-09-01T10:00:00Z",
          title: "Plain words",
          summary: "",
          status: "approved",
          hash: "h1",
          chars: 40,
          text_changed: true,
          committed: true,
          message: "Approved note.create rules-voice (company)",
          changes: [{ at: "2026-09-01T10:00:00Z", action: "approved", by: "person:alex", proposer: "model:Claude Code" }],
          body: "No hype, no jargon, no exclamation marks.",
        },
      ],
      "POST /api/brain/decisions": { results: [{ id: "rules-voice", action: "restore", ok: true, message: "", data: {} }], checkpoint: { ...checkpoint, label: "Restored 1" } },
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: `${at}?tab=versions` });
    expect(await screen.findByText(/Edited by You/)).toBeInTheDocument();
    expect(screen.getByText(/Approved by You, proposed by Claude Code/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Approved by You/ }));
    await user.type(screen.getByLabelText("Why put it back"), "Too short now");
    await user.click(screen.getByRole("button", { name: "Put this version back" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "restore", entry_id: "rules-voice", ref: "ccc3333dddd4", reason: "Too short now" }],
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Restored 1. Undo point saved.");
  });

  it("shows where it went, and why", async () => {
    mockApi({
      ...base,
      "GET /api/brain/entries/rules-voice/use": {
        id: "rules-voice",
        kind: "note",
        daily: [{ day: new Date().toISOString().slice(0, 10), conversations: 2, in_packets: 1, opened: 0, in_work: 1, tokens: 80 }],
        totals: { total: 2, d7: 2, d30: 2, last: "2026-10-05", tokens: 80, in_packets: 1, opened: 0, in_work: 1 },
        recent: [
          {
            session_id: "work:run_1",
            packet_id: "work",
            at: "2026-10-05T10:00:00Z",
            hash: "h2",
            reason: "in an AI work packet",
            tokens: 40,
            request: null,
            mode: null,
            via: "work",
            work: { run_id: "run_1", task_id: "task_1", title: "Draft the newsletter", project_id: null, actor: "Claude Code" },
          },
          {
            session_id: "sess-1",
            packet_id: "pkt-1",
            at: "2026-10-05T09:00:00Z",
            hash: "h2",
            reason: "score 0.71; words: hype, jargon",
            tokens: 40,
            request: "Write a post without hype",
            mode: "standard",
            via: "packet",
          },
        ],
      },
    });
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: `${at}?tab=use` });
    expect(await screen.findByText(/2 conversations and AI runs/)).toBeInTheDocument();
    expect(screen.getByText("Draft the newsletter")).toBeInTheDocument();
    expect(screen.getByText(/words: hype, jargon/)).toBeInTheDocument();
    expect(screen.getByText(/Write a post without hype/)).toBeInTheDocument();
  });

  it("brings an archived entry back", async () => {
    const calls = mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/entries/rules-first-tagline": { status: 404, body: { error: { code: "not_found", message: "No entry" } } },
      "GET /api/brain/entries/rules-first-tagline/details": inventory[3],
      "GET /api/brain/entries/rules-first-tagline/history": [],
      "GET /api/brain/entries/rules-first-tagline/versions?text=true": [],
      "POST /api/brain/decisions": { results: [{ id: "rules-first-tagline", action: "unarchive", ok: true, message: "", data: {} }], checkpoint: { ...checkpoint, label: "Brought back 1" } },
    });
    const user = userEvent.setup();
    renderAt(<EntryPage />, { path: "/brain/entries/:entryId", route: "/brain/entries/rules-first-tagline" });
    expect(await screen.findByRole("link", { name: "The entry that replaced it" })).toHaveAttribute("href", "/brain/entries/rules-old-tagline");
    await user.click(screen.getByRole("button", { name: "Bring it back" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [{ action: "unarchive", entry_id: "rules-first-tagline", reason: "Brought back on its page" }],
      }),
    );
  });
});

describe("brain activity, gaps and policies", () => {
  it("lists everything that happened and filters it", async () => {
    const calls = mockApi({
      "GET /api/brain/policies": policies,
      "GET /api/brain/activity": [
        { at: "2026-10-05T10:00:00Z", action: "updated", by: "person:alex", note: "rules-voice", title: "Plain words", fields: { owner: "person:sam" } },
        { at: "2026-10-04T10:00:00Z", action: "policy", by: "person:alex", changes: { review_days: { rule: 90 } }, reason: "Quarterly checks" },
        { at: "2026-10-03T10:00:00Z", action: "approved", by: "person:alex", kind: "skill.update", skill: "brand-sheet", path: "skills/brand/brand-sheet" },
        { at: "2026-10-02T10:00:00Z", action: "verified", by: "person:alex", note: "facts-founding", title: "Founded in 2011" },
      ],
    });
    const user = userEvent.setup();
    renderAt(<ActivityPage />, { path: "/brain/history", route: "/brain/history" });
    expect(await screen.findByText(/Changed its owner by You/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plain words" })).toHaveAttribute("href", "/brain/entries/rules-voice");
    expect(screen.getByText(/Changed the policy \(Review days\) by You/)).toBeInTheDocument();
    expect(screen.getByText(/“Quarterly checks”/)).toBeInTheDocument();
    // The chip says "Checked"; the sentence beside it goes on without a colon of its own.
    expect(screen.getByText(/^still true by You/)).toBeInTheDocument();
    // A procedure has no entry: the event names it by its skill.
    expect(screen.getByRole("link", { name: "/brand-sheet" })).toHaveAttribute("href", "/work/skills/brand-sheet");
    await user.selectOptions(screen.getByRole("combobox"), "restored");
    await waitFor(() => expect(calls.some((c) => c.path.includes("action=restored"))).toBe(true));
  });

  it("shows the gaps and what to do about each", async () => {
    const calls = mockApi({
      "GET /api/brain/gaps?days=30": [
        { key: "opened:sess-1:rules-voice", kind: "searched", at: "2026-10-05T10:00:00Z", session_id: "sess-1", request: "Avoid buzzwords in the post", entry: "rules-voice", entry_title: "Plain words", close: [] },
        { key: "packet:pkt-2", kind: "nothing", at: "2026-10-05T09:00:00Z", session_id: "sess-2", request: "Who runs our booth at Money20/20?", entry: null, close: [{ id: "facts-founding", title: "Founded in 2011" }] },
      ],
      "POST /api/brain/decisions": { results: [{ ok: true }], checkpoint: null },
      "POST /api/brain/gaps/dismiss": { status: 204 },
      "POST /api/brain/proposals": { status: "pending", message: "Waiting", proposal_id: "p1" },
    });
    const user = userEvent.setup();
    renderAt(<GapsPage />, { path: "/brain/gaps", route: "/brain/gaps" });
    expect(await screen.findByRole("heading", { name: "Found by searching (1)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plain words" })).toHaveAttribute("href", "/brain/entries/rules-voice");
    await user.click(screen.getByRole("button", { name: "Needs an update" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({
        decisions: [
          {
            action: "mark",
            entry_id: "rules-voice",
            state: "stale",
            reason: "Add the words people ask with to its title or summary: “Avoid buzzwords in the post”",
          },
        ],
      }),
    );
    expect(screen.getByRole("link", { name: "Founded in 2011" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Teach it" }));
    await user.type(screen.getByLabelText("Title"), "Booth staffing");
    await user.type(screen.getByLabelText("What it should say"), "Sam runs the booth.");
    await user.click(screen.getByRole("button", { name: "Propose it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/proposals")?.body).toEqual({
        title: "Booth staffing",
        statement: "Sam runs the booth.",
        kind: "fact",
        evidence: "Asked: Who runs our booth at Money20/20?",
      }),
    );
    expect(await screen.findByText(/waits in/)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Dismiss" })[1]!);
    await waitFor(() => expect(calls.find((c) => c.path === "/api/brain/gaps/dismiss")?.body).toEqual({ key: "packet:pkt-2" }));
  });

  it("saves only the policy settings that changed", async () => {
    const calls = mockApi({
      "GET /api/brain/policies": policies,
      "PUT /api/brain/policies": { status: "updated", policy: { ...policies, review_days: { rule: 90 }, retention_days: 60 }, checkpoint },
    });
    const user = userEvent.setup();
    renderAt(<PoliciesPage />, { path: "/settings", route: "/settings?tab=policies" });
    await user.type(await screen.findByLabelText("Check Rule every how many days"), "90");
    await user.clear(screen.getByLabelText(/Keep the detail of each handout/));
    await user.type(screen.getByLabelText(/Keep the detail of each handout/), "60");
    await user.click(screen.getByRole("button", { name: "Save the policy" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ review_days: { rule: 90 }, retention_days: 60 }),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("opens on what your AI knows, in the words it receives, with the map on top", async () => {
    const attention = { clashes: [], twins: [], flagged: [], recheck: [{ id: "rules-old-tagline", title: "Old tagline", why: "due" }], usage: { "rules-voice": 4 }, days: 7 };
    mockApi({
      "GET /api/brain/catalog": catalog,
      "GET /api/brain/attention": attention,
      "GET /api/brain/projects": [{ id: "spring", title: "Spring launch", summary: "", status: "active", active: true, current: "Filming", next: "Film the videos", blockers: "", updated: null, aliases: [], files: 2 }],
      "GET /api/brain/goals": { questions: [], answers: {}, exists: true, id: "you-goals", starter: null, updated: null, purpose: "Launch the spring line without dropping anything.", projects: [], text: "" },
      "GET /api/brain/inventory": [
        { ...row, id: "rules-voice", title: "Plain words", summary: "Write in plain words, short sentences.", kind: "rule", area: "brand", area_label: "Brand", topic: "brand/voice", topic_label: "Voice", uses: uses(4, 6, 10) },
        { ...row, id: "facts-team", title: "The team", summary: "Six people in one studio.", kind: "fact", area: "company", area_label: "Company", topic: "company/about", topic_label: "About", uses: uses(0, 0, 0) },
        { ...row, id: "you-goals", title: "Goals", summary: "", kind: "identity", load: "manual", uses: uses(0, 0, 0) },
      ],
    });
    const { unmount } = renderAt(<KnowsPage />, { path: "/brain", route: "/brain" });
    // The map on top: each area a tile, what it holds, how much your AI used it, what wants a look.
    const brand = await screen.findByRole("link", { name: "Brand: 2 notes, used 4 times this week, 1 to check" });
    expect(brand).toHaveAttribute("href", "/brain?area=brand");
    expect(brand).toHaveClass("heat-3", "flagged");
    // Then the sentences an AI receives, grouped the way a person thinks of them.
    expect(screen.getByText("Launch the spring line without dropping anything.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How you like work done" })).toBeInTheDocument();
    expect(screen.getByText("Write in plain words, short sentences.")).toBeInTheDocument();
    expect(screen.getByText(/used in 6 chats this month/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Company" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goals" })).not.toBeInTheDocument(); // the goals note is shown as goals
    expect(screen.getByRole("link", { name: "Spring launch" })).toHaveAttribute("href", "/projects/spring");
    unmount();
    renderAt(<KnowsPage />, { path: "/brain", route: "/brain?area=brand" });
    expect(await screen.findByRole("link", { name: "Voice" })).toHaveAttribute("href", "/brain/entries?area=brand&topic=brand%2Fvoice");
    expect(screen.getByRole("link", { name: "Plain words" })).toHaveAttribute("href", "/brain/entries/rules-voice");
    expect(screen.getByRole("link", { name: "Map" })).toHaveAttribute("href", "/brain");
  });
});

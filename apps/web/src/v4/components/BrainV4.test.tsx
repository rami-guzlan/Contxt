import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ReceiptView } from "./Receipt";
import { LevelChip, LoreShelf, MapCard, PullBudget, SectionAddresses, SessionSearch } from "./BrainV4";

afterEach(() => vi.restoreAllMocks());

const VIEW = {
  areas: [
    { id: "work", name: "Work", covers: "what you make", notes: 12 },
    { id: "home", name: "Home", covers: "", notes: 3 },
  ],
  projects: [{ id: "bakery", name: "Bakery site", aka: ["the site"], status: "active", address: "bakery" }],
  sheets: [{ id: "open-loops", name: "Open loops this week", columns: ["Owner", "Due"] }],
  must_holds: [{ id: "sign-off", name: "The owner signs off every invoice" }],
  lore: [{ id: "lore_two", name: "Two exports, one slide", address: "lore_two#story" }],
  levels: { canon: 1, confirmed: 2, kept: 9 },
  sealed: 1,
  text: "## Brain map · partial\nA partial list: absent here doesn't mean absent from the Brain.",
  cut: { areas: 1 },
  tokens: 120,
  limit: 250,
  caps: { areas: 8, projects: 6, sheets: 6, must_holds: 5, lore: 3 },
  fingerprint: "abc",
};

describe("the map card", () => {
  it("opens to the map from the server: tiers, +N more where cut, levels and the sealed line for the owner only", async () => {
    mockApi({ "GET /api/brain/map/view": VIEW });
    renderAt(<MapCard />);
    fireEvent.click(screen.getByRole("button", { name: /What your AIs see first/ }));
    expect(await screen.findByText("Work · 12")).toBeInTheDocument();
    expect(screen.queryByText("Home · 3")).not.toBeInTheDocument();
    expect(screen.getByText("+1 more")).toBeInTheDocument();
    expect(screen.getByText(/The map was cut to fit its 250 tokens/)).toBeInTheDocument();
    expect(screen.getByText("canon 1 · confirmed 2 · kept 9 · tentative 0 · exhaust 0")).toBeInTheDocument();
    expect(screen.getByText("ONLY YOU SEE THIS")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy section address lore_two#story" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "See everything" }));
    expect(screen.getByText("Home · 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show it as sent" }));
    expect(screen.getByText(/## Brain map · partial/)).toBeInTheDocument();
  });

  it("says when the map can't be read", async () => {
    mockApi({ "GET /api/brain/map/view": { status: 500, body: { error: { code: "internal", message: "Broken" } } } });
    renderAt(<MapCard />);
    fireEvent.click(screen.getByRole("button", { name: /What your AIs see first/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("levels and section addresses", () => {
  it("draws a level in words", () => {
    renderAt(<LevelChip level="kept" />);
    expect(screen.getByText("kept, not verified")).toBeInTheDocument();
  });

  it("lists a note's section addresses, each copyable", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText: write } });
    mockApi({
      "GET /api/brain/sections/webinar": {
        id: "webinar",
        kind: "note",
        name: "Webinar",
        sections: [{ address: "webinar#guest-bios", heading: "Guest bios", slug: "guest-bios", tokens: 20 }],
      },
    });
    renderAt(<SectionAddresses id="webinar" />);
    fireEvent.click(await screen.findByRole("button", { name: "Copy section address webinar#guest-bios" }));
    expect(write).toHaveBeenCalledWith("webinar#guest-bios");
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });
});

describe("the Lore shelf", () => {
  it("shows each lesson with its level, story and address, and what it warns about when opened", async () => {
    mockApi({
      "GET /api/brain/lore": [
        {
          id: "lore_two",
          title: "Two exports, one slide",
          story: "The slide quoted the older export.",
          pattern: "A number without its version.",
          words: ["registrations", "total"],
          level: "kept",
          level_label: "kept, not verified",
          address: "lore_two#story",
          sections: ["lore_two#story", "lore_two#pattern", "lore_two#words"],
          added: "2026-10-12",
          scope: "company",
        },
      ],
    });
    renderAt(<LoreShelf />);
    expect(await screen.findByText("Two exports, one slide")).toBeInTheDocument();
    expect(screen.getByText("kept, not verified")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Two exports, one slide/ }));
    expect(screen.getByText("A number without its version.")).toBeInTheDocument();
    expect(screen.getByText("registrations · total")).toBeInTheDocument();
  });

  it("says when there are no lessons yet", async () => {
    mockApi({ "GET /api/brain/lore": [] });
    renderAt(<LoreShelf />);
    expect(await screen.findByText("No lessons yet")).toBeInTheDocument();
  });
});

describe("session search", () => {
  it("searches past sessions' receipts and shows what each was given", async () => {
    const calls = mockApi({
      "GET /api/brain/sessions/search": [
        {
          session_id: "sess-1",
          date: "2026-10-23T09:40:00Z",
          last: "2026-10-23T09:41:00Z",
          app: "Claude Code",
          did: "Run of show for session 1",
          requests: ["Run of show for session 1"],
          given: ["Brain map · 236 tok", "Opened after the packet: run.docx#session-1 · 1,120 tok"],
          receipts: ["pkt-1"],
        },
      ],
    });
    renderAt(<SessionSearch />);
    fireEvent.change(screen.getByLabelText("Search past sessions"), { target: { value: "run of show" } });
    fireEvent.click(await screen.findByRole("button", { name: /Run of show for session 1/ }));
    expect(screen.getByText("Brain map · 236 tok")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/brain/sessions/search?q=run+of+show")).toBe(true);
    expect(screen.getByRole("button", { name: /Read that session's own record/ })).toBeDisabled();
  });

  it("says when no receipt mentions it", async () => {
    mockApi({ "GET /api/brain/sessions/search": [] });
    renderAt(<SessionSearch />);
    fireEvent.change(screen.getByLabelText("Search past sessions"), { target: { value: "lighthouse" } });
    expect(await screen.findByText(/No session's receipt mentions that/)).toBeInTheDocument();
  });
});

describe("the pull budget", () => {
  it("shows the budget and changes it through the policy", async () => {
    const policy = { pull_items: 2, pull_tokens: 1500 };
    const calls = mockApi({ "GET /api/brain/policies": policy, "PUT /api/brain/policies": { policy } });
    renderAt(<PullBudget />);
    expect(await screen.findByText(/open up to 2 more items, about 1,500 tokens/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ pull_items: 3 }));
  });
});

describe("the receipt", () => {
  it("lists what the AI opened after the packet, and pulls named only past the budget", async () => {
    mockApi({
      "GET /api/brain/receipts/pkt-1": {
        id: "pkt-1",
        session_id: "s",
        at: "",
        request: "Run of show",
        scope: [],
        partition: null,
        sent: [],
        opened: [{ id: "webinar#guest-bios", title: "webinar#guest-bios", address: "webinar#guest-bios", tokens: 120 }],
        refused: [{ address: "people#morgan", name: "People", status: "over_pull_budget", gone_at: null, says: "named only, over the pull budget" }],
        pull_budget: { items: 2, tokens: 1500, used_items: 1, used_tokens: 120 },
        did_not_fit: [],
        already_delivered: [],
        unknown: [],
        conflicts: [],
        older: [],
        tokens: { packet: 0, map: 0, opened: 120, total: 120, budget: null, counted: "estimated" },
        text: "",
        complete: false,
        note: "",
      },
    });
    renderAt(<ReceiptView id="pkt-1" defaultOpen />);
    expect(await screen.findByText("Opened by the AI after the packet")).toBeInTheDocument();
    expect(screen.getByText("webinar#guest-bios")).toBeInTheDocument();
    expect(screen.getByText("people#morgan · named only, over the pull budget")).toBeInTheDocument();
    expect(screen.getByText(/Pull budget: 1 of 2 used/)).toBeInTheDocument();
  });
});

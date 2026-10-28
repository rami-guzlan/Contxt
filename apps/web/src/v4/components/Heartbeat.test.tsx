// The heartbeat in the web app: the auto Home (bar, The world right now, Recent beats, no
// Goals), Settings' Heartbeat block, the Brain's auto banner and the auto strip, all from
// /api/heartbeat.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { HomePage } from "../pages/Home";
import { AutoBanner } from "./AutoBanner";
import { AutoStrip } from "./AutoStrip";
import { HeartbeatBar, RecentBeats, WorldRightNow } from "./Heartbeat";
import { HeartbeatSettings } from "./HeartbeatSettings";

const now = new Date().toISOString();

const connector = (over: Record<string, unknown> = {}) => ({
  id: "claude:mail",
  name: "mail",
  cli: "claude",
  cli_label: "Claude Code",
  how: "mcp",
  how_label: "MCP",
  cadence_minutes: null,
  feeds: ["state"],
  enabled: true,
  last_read_at: now,
  last_items: 2,
  status: "ok",
  status_line: "Read-only: 2 of 4 tools (2 that could change something are refused).",
  tools: ["list_messages", "get_thread"],
  found_in: "Claude Code settings",
  present: true,
  ...over,
});

const beat = (over: Record<string, unknown> = {}) => ({
  id: "beat_1",
  status: "done",
  trigger: "now",
  started_at: now,
  finished_at: now,
  connectors: [{ id: "claude:mail", name: "mail", read: true }],
  connectors_read: 1,
  items: 3,
  changes: 2,
  waits: 1,
  held: 0,
  tokens: 2400,
  tokens_known: true,
  tokens_unknown: 0,
  duration_ms: 900,
  errors: [],
  details: ["mail: Morgan approved hero option B → Website Redesign › latest progress"],
  nothing_new: false,
  ...over,
});

const status = (over: Record<string, unknown> = {}) => ({
  state: "ready",
  line: "Ready.",
  cadence: 15,
  cadences: [5, 15, 30, 60],
  quiet_hours: "night",
  quiet_options: [
    { id: "off", label: "Off" },
    { id: "night", label: "7pm to 7am" },
    { id: "nights_weekends", label: "Nights and weekends" },
  ],
  in_quiet_hours: false,
  paused: false,
  cli: "claude",
  cli_label: "Claude Code",
  signed_in: true,
  backoff: null,
  last_beat: beat(),
  next_beat_at: now,
  running: null,
  connectors: [connector(), connector({ id: "claude:computer-use", name: "computer-use", how: "computer", how_label: "Computer use", feeds: [], enabled: false, status: "off", status_line: "Reads through computer use." })],
  cost: { with_changes: 2400, nothing_new: 600, beats: 4, unknown: 0 },
  ...over,
});

const line = (over: Record<string, unknown> = {}) => ({
  id: "hbl_1",
  beat_id: "beat_1",
  region: "state",
  project: "pj_web",
  text: "Morgan approved hero option B",
  connector_id: "claude:mail",
  connector: "mail",
  how: "MCP",
  cli: "claude",
  cli_label: "Claude Code",
  at: now,
  written_at: now,
  wrote: "Wrote: Website Redesign › latest progress",
  reason: "Morgan approved it by email.",
  status: "applied",
  held: false,
  new_this_beat: true,
  proposal_id: "p1",
  checkpoint_id: "cp1",
  source_id: "connector:claude:mail:msg-1",
  can_undo: true,
  ...over,
});

const regions = [
  {
    id: "state",
    name: "State",
    headline: "The website hero is settled.",
    headline_at: now,
    updated_at: now,
    lines: [line(), line({ id: "hbl_2", source_id: "connector:claude:drive:pricing", text: "Pricing sheet v4 edited", status: "held", held: true, can_undo: false, reason: "", wrote: "Held back: must-hold: Never share pricing until it is final.", new_this_beat: false })],
    new_this_beat: 1,
    projects: [{ id: "pj_web", title: "Website Redesign", status: "Hero option B approved", at: now, from: ["mail"] }],
  },
  { id: "rules", name: "Rules", headline: "", headline_at: null, updated_at: null, lines: [], new_this_beat: 0, projects: [] },
];

function api(over: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/heartbeat/status": status(),
    "GET /api/heartbeat/regions": regions,
    "GET /api/heartbeat/beats": [beat(), beat({ id: "beat_0", items: 0, changes: 0, waits: 0, tokens: null, tokens_known: false, nothing_new: true, details: ["Read 1 connectors. Nothing new."] })],
    "GET /api/brain/policies": { mode: "auto", auto_daily_cap: 50, auto_applied_today: 2, capture_types: [], capture_origins: [], standing: [], learned: [] },
    ...over,
  });
}

beforeEach(() => window.localStorage.clear());

describe("The heartbeat bar", () => {
  it("shows the cadence, the last beat and the connectors from the server", async () => {
    api();
    renderAt(<HeartbeatBar />);
    expect(await screen.findByText("Heartbeat · every 15 min")).toBeInTheDocument();
    expect(screen.getByText(/read 1 connector, 3 items, 2 changes/)).toBeInTheDocument();
    expect(screen.getByLabelText("mail: on")).toBeInTheDocument();
    expect(screen.getByLabelText("computer-use: off")).toBeInTheDocument();
  });

  it("Beat now starts a beat and Pause pauses the heartbeat", async () => {
    const calls = api({ "POST /api/heartbeat/beat": { beat_id: "beat_2", status: "running" }, "PUT /api/heartbeat/settings": status({ paused: true }) });
    renderAt(<HeartbeatBar />);
    await userEvent.click(await screen.findByRole("button", { name: "Beat now" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/beat")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ paused: true });
  });

  it.each([
    [{ paused: true, state: "paused", line: "Paused. Nothing is read or changed until you resume." }, "Paused. Nothing is read or changed until you resume.", "Heartbeat · paused"],
    [{ state: "quiet", line: "Quiet hours (7pm to 7am). The next beat waits until they end." }, "Quiet hours (7pm to 7am). The next beat waits until they end.", null],
    [{ state: "unhealthy_sign_in", line: "Claude Code is not signed in, so the heartbeat waits." }, "Claude Code is not signed in, so the heartbeat waits.", null],
    [{ state: "provider_limit", line: "A provider limit was hit. The heartbeat tries again later." }, "A provider limit was hit. The heartbeat tries again later.", null],
  ])("says its state in words: %o", async (over, words, title) => {
    api({ "GET /api/heartbeat/status": status(over) });
    renderAt(<HeartbeatBar />);
    expect(await screen.findByText(words)).toBeInTheDocument();
    if (title) expect(screen.getByText(title)).toBeInTheDocument();
  });

  it("in quiet hours shows Beat now as off, with a way to beat once anyway", async () => {
    const calls = api({
      "GET /api/heartbeat/status": status({ state: "quiet", in_quiet_hours: true, line: "Quiet hours (7pm to 7am). The next beat waits until they end." }),
      "POST /api/heartbeat/beat": { beat_id: "beat_2", status: "running" },
    });
    renderAt(<HeartbeatBar />);
    expect(await screen.findByText("Quiet hours")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Beat now" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Beat once anyway" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/beat")).toBe(true);
  });

  it("lights the connector being read while a beat runs", async () => {
    api({ "GET /api/heartbeat/status": status({ running: { beat_id: "beat_2", reading: "claude:mail", read: [] } }) });
    renderAt(<HeartbeatBar />);
    expect(await screen.findByText("Reading mail through Claude Code…")).toBeInTheDocument();
    expect(screen.getByLabelText("mail: reading now")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Beating…" })).toBeDisabled();
  });

  it("shows a failure with Try again", async () => {
    api({ "GET /api/heartbeat/status": { status: 500, body: { error: { code: "x", message: "It broke" } } } });
    renderAt(<HeartbeatBar />);
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("The world right now", () => {
  it("shows a card per region with its latest lines, and every line with Undo when opened", async () => {
    const calls = api({ "POST /api/heartbeat/lines/hbl_1/undo": { ...line({ status: "undone" }), line: "Undone." } });
    renderAt(<WorldRightNow />);
    expect(await screen.findByText("The website hero is settled.")).toBeInTheDocument();
    expect(screen.getByText("+1 this beat")).toBeInTheDocument();
    expect(screen.getByText(/Website Redesign/)).toBeInTheDocument();
    expect(screen.getByText("Nothing from the heartbeat yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /State/ }));
    const every = screen.getByRole("region", { name: "State: every line" });
    expect(within(every).getByText("Wrote: Website Redesign › latest progress")).toBeInTheDocument();
    expect(within(every).getByText("Held back: must-hold: Never share pricing until it is final.")).toBeInTheDocument();
    expect(within(every).getByText("Why: Morgan approved it by email.")).toBeInTheDocument();
    await userEvent.click(within(every).getByRole("button", { name: "Undo: Wrote: Website Redesign › latest progress" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/lines/hbl_1/undo")).toBe(true);
  });

  it("shows an item that moved two homes once, with an Undo for each write", async () => {
    const task = line({ id: "hbl_3", wrote: "Wrote: Website Redesign › task: Send Morgan the files", reason: "It follows." });
    const two = [{ ...regions[0], lines: [line(), task], new_this_beat: 1 }];
    const calls = api({ "GET /api/heartbeat/regions": two, "POST /api/heartbeat/lines/hbl_3/undo": { ...task, status: "undone", line: "Undone." } });
    renderAt(<WorldRightNow />);
    expect(await screen.findAllByText("Morgan approved hero option B")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: /State/ }));
    const every = screen.getByRole("region", { name: "State: every line" });
    expect(within(every).getAllByText("Morgan approved hero option B")).toHaveLength(1);
    expect(within(every).getByText("Wrote: Website Redesign › latest progress")).toBeInTheDocument();
    await userEvent.click(within(every).getByRole("button", { name: "Undo: Wrote: Website Redesign › task: Send Morgan the files" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/lines/hbl_3/undo")).toBe(true);
  });

  it("is honest when the Brain has no regions", async () => {
    api({ "GET /api/heartbeat/regions": [] });
    renderAt(<WorldRightNow />);
    expect(await screen.findByText("No regions yet")).toBeInTheDocument();
  });
});

describe("Recent beats", () => {
  it("lists beats with their tokens, nothing-new beats muted, and the cost from real records", async () => {
    api();
    renderAt(<RecentBeats />);
    expect(await screen.findByText("1 connector · 3 items · 2 changes · 1 waits")).toBeInTheDocument();
    expect(screen.getByText("2,400 tok")).toBeInTheDocument();
    expect(screen.getByText("Nothing new · 1 connector")).toBeInTheDocument();
    expect(screen.getByText("tokens unknown")).toBeInTheDocument();
    expect(screen.getByText(/About 2,400 tokens a beat with changes, 600 with none/)).toBeInTheDocument();
    expect(screen.getByText(/Morgan approved hero option B/)).toBeInTheDocument(); // the first is open
  });

  it("says when there is no beat yet", async () => {
    api({ "GET /api/heartbeat/beats": [] });
    renderAt(<RecentBeats />);
    expect(await screen.findByText(/No beats yet/)).toBeInTheDocument();
  });
});

describe("The auto-governed Home", () => {
  it("shows the heartbeat and The world right now, and no Goals", async () => {
    window.localStorage.setItem("gn.quickstart", JSON.stringify({ dismissed: true, done: {} }));
    api({
      "GET /api/brain/apps": [],
      "GET /api/brain/checkpoints": [],
      "GET /api/brain/proposals": [],
      "GET /api/brain/projects": [],
      "GET /api/brain/catalog": { areas: [], entries: [] },
    });
    renderAt(<HomePage />);
    expect(await screen.findByText("Heartbeat · every 15 min")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "The world right now" })).toBeInTheDocument();
    expect(screen.getByText("Recent beats")).toBeInTheDocument();
    expect(screen.getByText("What Claude Code did, and why")).toBeInTheDocument();
    expect(screen.queryByText("Goals")).not.toBeInTheDocument();
  });
});

describe("Settings, Heartbeat", () => {
  it("changes the cadence and quiet hours, turns a connector off, and finds connectors", async () => {
    const calls = api({
      "PUT /api/heartbeat/settings": status(),
      "PUT /api/heartbeat/connectors/claude%3Amail": connector({ enabled: false, status: "off" }),
      "POST /api/heartbeat/connectors/rescan": { found: 2, added: [], line: "Found 2 connectors: 2 in Claude Code. Nothing new to add.", connectors: [] },
    });
    renderAt(<HeartbeatSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "30 min" }));
    expect(calls.find((c) => c.method === "PUT" && c.path === "/api/heartbeat/settings")?.body).toEqual({ cadence: 30 });
    await userEvent.click(screen.getByRole("button", { name: "Nights and weekends" }));
    expect(calls.filter((c) => c.path === "/api/heartbeat/settings").at(-1)?.body).toEqual({ quiet_hours: "nights_weekends" });
    expect(screen.getByText("Feeds State")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /mail: Last read ok. Turn off/ }));
    expect(calls.find((c) => c.path === "/api/heartbeat/connectors/claude%3Amail")?.body).toEqual({ enabled: false });
    // Found but off, in the compact list; computer use offers no setup yet.
    const off = screen.getByRole("group", { name: "Found, off" });
    expect(within(off).getByText(/Reads through computer use, not used yet/)).toBeInTheDocument();
    expect(within(off).queryByRole("button", { name: "Set up computer-use" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Find connectors in my CLIs" }));
    expect(await screen.findByText("Found 2 connectors: 2 in Claude Code. Nothing new to add.")).toBeInTheDocument();
    expect(screen.getByText(/About 2,400 tokens a beat with changes/)).toBeInTheDocument();
  });

  it("test-reads a connector and says whether it is ready for heartbeats, nothing kept", async () => {
    const calls = api({
      "POST /api/heartbeat/connectors/claude%3Amail/test": {
        id: "claude:mail",
        passed: true,
        steps: [
          { step: "found", ok: true, line: "Found in Claude Code." },
          { step: "signed in", ok: true, line: "Signed in." },
          { step: "read-only", ok: true, line: "2 tools only read; 0 refused." },
          { step: "test read", ok: true, items: 10, returned: 10, tokens: 69170, seconds: 44, cost: 0.05, per_day: 1.2 },
        ],
      },
    });
    renderAt(<HeartbeatSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Test read" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/connectors/claude%3Amail/test")).toBe(true);
    const shown = await screen.findByText(/Ready for heartbeats\./);
    expect(shown).toHaveTextContent("Ready for heartbeats.");
    expect(shown).toHaveTextContent("test read ✓ 10 items in 44 s, $0.050 a read, at most $1.20 a day");
  });

  it("shows how to sign a connector in again, and Check again looks again", async () => {
    const expired = connector({
      status: "unhealthy_sign_in",
      status_line: "Sign in again.",
      sign_in: { steps: "Open claude.ai, Settings, Connectors, and connect mail again. Then choose Check again here.", url: "https://claude.ai/settings/connectors" },
    });
    const calls = api({
      "GET /api/heartbeat/status": status({ connectors: [expired] }),
      "POST /api/heartbeat/connectors/rescan": { found: 1, added: [], line: "Found 1 connector.", connectors: [] },
    });
    renderAt(<HeartbeatSettings />);
    expect(await screen.findByText(/connect mail again/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "https://claude.ai/settings/connectors");
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/connectors/rescan")).toBe(true);
  });

  it("sets a new connector up from found to on, without a terminal", async () => {
    const fresh = connector({ id: "claude:drive", name: "Drive", enabled: false, status: "off", status_line: "", last_read_at: null, found_in: "your Claude account" });
    const calls = api({
      "GET /api/heartbeat/status": status({ connectors: [fresh] }),
      "POST /api/heartbeat/connectors/claude%3Adrive/test": {
        id: "claude:drive",
        passed: true,
        steps: [
          { step: "found", ok: true },
          { step: "signed in", ok: true },
          { step: "read-only", ok: true },
          { step: "test read", ok: true, items: 6, returned: 8, left_out: 2, tokens: 30000, seconds: 20, cost: 0.02, per_day: 0.5 },
        ],
      },
      "PUT /api/heartbeat/connectors/claude%3Adrive": fresh,
    });
    renderAt(<HeartbeatSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up Drive" }));
    const setup = await screen.findByRole("list", { name: "Set up Drive" });
    expect(within(setup).getByText("In your Claude account.")).toBeInTheDocument();
    await userEvent.click(within(setup).getByRole("button", { name: "Test read" }));
    expect(await within(setup).findByText(/Ready for heartbeats\..*6 items in 20 s, 2 left out/)).toBeInTheDocument();
    await userEvent.type(within(setup).getByLabelText("What Drive looks for"), "Client decisions");
    await userEvent.type(within(setup).getByLabelText("What Drive leaves out"), "newsletter");
    await userEvent.tab();
    const puts = () => calls.filter((c) => c.method === "PUT").map((c) => c.body);
    await waitFor(() => expect(puts()).toEqual([{ ask: "Client decisions" }, { skip: "newsletter" }]));
    await userEvent.click(within(setup).getByRole("button", { name: "Turn on Drive" }));
    await waitFor(() => expect(puts().at(-1)).toEqual({ enabled: true }));
  });

  it("will not turn on a connector whose check failed", async () => {
    const fresh = connector({ id: "claude:drive", name: "Drive", enabled: false, status: "off" });
    api({
      "GET /api/heartbeat/status": status({ connectors: [fresh] }),
      "POST /api/heartbeat/connectors/claude%3Adrive/test": { id: "claude:drive", passed: false, steps: [{ step: "found", ok: true }, { step: "signed in", ok: false, line: "Sign in again." }] },
    });
    renderAt(<HeartbeatSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up Drive" }));
    const setup = await screen.findByRole("list", { name: "Set up Drive" });
    await userEvent.click(within(setup).getByRole("button", { name: "Test read" }));
    expect(await within(setup).findByText(/Not ready\./)).toBeInTheDocument();
    expect(within(setup).getByRole("button", { name: "Turn on Drive" })).toBeDisabled();
  });

  it("sets how often each connector is read, and Scout reads every beat", async () => {
    const calls = api({ "PUT /api/heartbeat/connectors/claude%3Amail": connector({ cadence_minutes: 60 }) });
    renderAt(<HeartbeatSettings />);
    await userEvent.selectOptions(await screen.findByLabelText("How often mail is read"), "60");
    expect(calls.find((c) => c.path === "/api/heartbeat/connectors/claude%3Amail")?.body).toEqual({ cadence_minutes: 60 });
  });

  it("asks for a fix to a failed n8n read, and keeps it with your yes", async () => {
    const failed = connector({ id: "n8n:gmail", name: "Gmail through n8n", how: "n8n", how_label: "n8n", cli: "n8n", cli_label: "n8n", status: "error", status_line: "n8n: Credentials not found." });
    const calls = api({
      "GET /api/heartbeat/status": status({ connectors: [failed] }),
      "POST /api/heartbeat/n8n/n8n%3Agmail/fix": { ...failed, fix: "Sorted newest first." },
    });
    renderAt(<HeartbeatSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Suggest a fix" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/n8n/n8n%3Agmail/fix")).toBe(true);
  });

  it("shows a suggested fix with Keep and Skip", async () => {
    const waiting = connector({ id: "n8n:gmail", name: "Gmail through n8n", how: "n8n", how_label: "n8n", cli: "n8n", cli_label: "n8n", status: "error", fix: "Sorted newest first." });
    const calls = api({ "GET /api/heartbeat/status": status({ connectors: [waiting] }), "PUT /api/heartbeat/n8n/n8n%3Agmail/fix": { ...waiting, fix: null } });
    renderAt(<HeartbeatSettings />);
    expect(await screen.findByText(/Suggested fix: Sorted newest first./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ keep: true });
  });

  it("says so when no connector has been found", async () => {
    api({ "GET /api/heartbeat/status": status({ connectors: [], cost: { with_changes: null, nothing_new: null, beats: 0, unknown: 0 } }) });
    renderAt(<HeartbeatSettings />);
    expect(await screen.findByText(/No connectors yet/)).toBeInTheDocument();
    expect(screen.getByText(/No beats yet, so there is no cost to show/)).toBeInTheDocument();
  });
});

describe("The auto banner and the auto strip", () => {
  it("says how many regions the last beat updated", async () => {
    api();
    renderAt(<AutoBanner />);
    expect(await screen.findByText(/Auto-governed by Claude Code\. Heartbeat .*: 1 region updated\. Only must-holds wait here\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "The world right now →" })).toBeInTheDocument();
  });

  it("shows nothing when the Brain is governed", async () => {
    api({ "GET /api/brain/policies": { mode: "governed" } });
    const { container } = renderAt(<AutoBanner />);
    await new Promise((r) => setTimeout(r, 50));
    expect(container).toBeEmptyDOMElement();
  });

  it("keeps an area in the flow, links to its regions and hands it back", async () => {
    api();
    const govern = vi.fn();
    renderAt(<AutoStrip area="Project status" what="It keeps each project's status current." regions={["state"]} onGovern={govern} />);
    expect(await screen.findByText("Claude Code keeps Project status")).toBeInTheDocument();
    expect(screen.getByText(/Everything below stays yours to open, edit and undo/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /State: 1 line from the/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Govern this myself" }));
    expect(govern).toHaveBeenCalled();
  });
});

describe("Onboarding from the AI apps", () => {
  const memory = (cli: string, label: string) =>
    connector({ id: `memory:${cli}`, name: `${label} memory and chats`, cli, cli_label: label, how: "memory", how_label: "Memory and chats, every 1440 min", cadence_minutes: 1440, feeds: [], enabled: false, last_read_at: null, status: "off", status_line: "", tools: [] });

  it("has each AI app chosen read what it keeps on me, with memory pasted from another app", async () => {
    const calls = api({
      "GET /api/heartbeat/status": status({ connectors: [connector(), memory("claude", "Claude Code"), memory("codex", "Codex CLI")] }),
      "POST /api/heartbeat/onboard": { id: "beat_9", status: "running", reading: ["Claude Code memory and chats"] },
    });
    renderAt(<HeartbeatSettings />);
    const card = await screen.findByRole("region", { name: "Start with what your AI apps know" });
    expect(within(card).getByText(/what it remembers from Claude on the web, desktop and phone/)).toBeInTheDocument();
    expect(within(card).getByText(/what it remembers from ChatGPT/)).toBeInTheDocument();
    await userEvent.click(within(card).getAllByRole("checkbox")[1]!);
    await userEvent.click(within(card).getByText("Add memory from another AI app"));
    await userEvent.type(within(card).getByLabelText("What another AI app remembers about you"), "Prefers short answers");
    await userEvent.click(within(card).getByRole("button", { name: "Build my Brain from them" }));
    expect(calls.find((c) => c.path === "/api/heartbeat/onboard")?.body).toEqual({ clis: ["claude"], pasted: "Prefers short answers" });
    expect(await within(card).findByText(/Reading Claude Code memory and chats/)).toBeInTheDocument();
  });

  it("a memory read can be read daily and told what to look for", async () => {
    const calls = api({
      "GET /api/heartbeat/status": status({ own_cadences: [5, 15, 30, 60, 240, 1440], connectors: [memory("claude", "Claude Code")] }),
      "PUT /api/heartbeat/connectors/memory%3Aclaude": memory("claude", "Claude Code"),
    });
    renderAt(<HeartbeatSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Set up Claude Code memory and chats" }));
    const often = await screen.findByLabelText("How often Claude Code memory and chats is read");
    expect(within(often).getByRole("option", { name: "daily" })).toBeInTheDocument();
    const look = screen.getByLabelText("What Claude Code memory and chats looks for");
    await userEvent.type(look, "Deadlines");
    await userEvent.tab();
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ ask: "Deadlines" }));
  });
});

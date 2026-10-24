// The heartbeat in the web app: the auto Home (bar, The world right now, Recent beats, no
// Goals), Settings' Heartbeat block, the Brain's auto banner and the auto strip, all from
// /api/heartbeat.

import { screen, within } from "@testing-library/react";
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
    lines: [line(), line({ id: "hbl_2", text: "Pricing sheet v4 edited", status: "held", held: true, can_undo: false, reason: "", wrote: "Held back: must-hold: Never share pricing until it is final.", new_this_beat: false })],
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
    await userEvent.click(within(every).getByRole("button", { name: "Undo: Morgan approved hero option B" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/lines/hbl_1/undo")).toBe(true);
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
    await userEvent.click(screen.getByRole("button", { name: /mail: Reading. Turn off/ }));
    expect(calls.find((c) => c.path === "/api/heartbeat/connectors/claude%3Amail")?.body).toEqual({ enabled: false });
    expect(screen.getByRole("button", { name: /computer-use: Off/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Find connectors in my CLIs" }));
    expect(await screen.findByText("Found 2 connectors: 2 in Claude Code. Nothing new to add.")).toBeInTheDocument();
    expect(screen.getByText(/About 2,400 tokens a beat with changes/)).toBeInTheDocument();
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

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { SettingsPage } from "./Settings";

afterEach(() => vi.restoreAllMocks());

const at = (route: string) => renderAt(<SettingsPage />, { path: "/settings", route });

const runners = [
  { id: "claude", label: "Claude Code", provider: "claude", one_click: true, installed: true, version: "2.0", signed_in: true, install: "", sign_in: "", actor_id: null, detail: "" },
  { id: "codex", label: "Codex", provider: "codex", one_click: true, installed: true, version: "1.1", signed_in: false, install: "", sign_in: "", actor_id: null, detail: "" },
];

describe("Settings, Your AI apps", () => {
  it("shows each app, its last request and the CLIs from the server, and signs in", async () => {
    const calls = mockApi({
      "GET /api/brain/apps": [
        { client: "claude-code", label: "Claude Code", found: true, connected: true, last_request: { at: "2026-10-21T08:00:00Z", request: "draft the weekly note" }, setup: null },
        { client: "cursor", label: "Cursor", found: true, connected: false, last_request: null, setup: { client: "cursor", label: "Cursor", server: "contxt", file: "~/.cursor/mcp.json", config: '{"mcpServers":{}}', note: "" } },
      ],
      "GET /api/runners": runners,
      "GET /api/connections/instructions": [],
      "POST /api/runners/codex/sign-in": { opened: true, command: "codex login" },
    });
    at("/settings");
    expect(await screen.findByText("draft the weekly note")).toBeInTheDocument();
    expect(screen.getByText("Found · not connected yet")).toBeInTheDocument();
    expect(screen.getByText('{"mcpServers":{}}')).toBeInTheDocument();
    expect(await screen.findByText("Codex on this computer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/runners/codex/sign-in")).toBe(true));
  });

  it("connects an app only after the person says yes", async () => {
    const calls = mockApi({
      "GET /api/brain/apps": [{ client: "cursor", label: "Cursor", found: true, connected: false, last_request: null, setup: { client: "cursor", label: "Cursor", server: "contxt", file: "~/.cursor/mcp.json", config: "{}", note: "" } }],
      "GET /api/runners": [],
      "GET /api/connections/instructions": [],
      "POST /api/brain/apps/cursor/connect": { client: "cursor", connected: true, changed: true, backup: "~/.cursor/mcp.json.bak" },
    });
    at("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "Connect it for me" }));
    const dialog = await screen.findByRole("dialog");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    fireEvent.click(within(dialog).getByRole("button", { name: "Yes, connect it" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ confirm: true }));
  });

  it("shows a failure with Try again", async () => {
    mockApi({ "GET /api/brain/apps": { status: 500, body: { error: { code: "error", message: "Apps could not be read." } } }, "GET /api/runners": [], "GET /api/connections/instructions": [] });
    at("/settings");
    expect(await screen.findByText("Apps could not be read.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try again" }).length).toBeGreaterThan(0);
  });
});

const policy = {
  preset: "personal",
  presets: ["personal", "careful", "regulated"],
  auto_daily_cap: 50,
  auto_applied_today: 3,
  standing: [{ type: "fact", origin: "chat", area: "*", paused: false }],
  retrieval_policy: "standard",
  retrieval_policies: ["relaxed", "standard", "careful"],
  learned: [{ id: "lr_1", type: "fact", origin: "folder", area: "people", says: "Don't file staff phone numbers", at: "2026-10-19T12:00:00Z" }],
  areas: ["people", "work"],
  capture_types: ["fact", "rule"],
  capture_origins: ["app", "chat", "folder"],
  capture: { fact: { app: "apply", chat: "apply", folder: "wait" }, rule: { app: "apply", chat: "wait", folder: "wait" } },
};

describe("Settings, Approval and auto-governance", () => {
  it("switches between Governed and Auto, and pauses Auto", async () => {
    const auto = { ...policy, mode: "auto", auto_paused: false };
    const calls = mockApi({ "GET /api/brain/policies": auto, "PUT /api/brain/policies": { policy: auto } });
    at("/settings?tab=approval");
    expect(await screen.findByRole("radio", { name: /^Auto/ })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("button", { name: "Pause Auto" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ auto_paused: true }));
    fireEvent.click(screen.getByRole("radio", { name: /^Governed/ }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT").at(-1)?.body).toEqual({ mode: "governed" }));
  });

  it("shows the cap, standing permissions, presets, retrieval policy and learned rules, and changes them", async () => {
    const calls = mockApi({
      "GET /api/brain/policies": policy,
      "PUT /api/brain/policies": { policy },
      "DELETE /api/brain/learned/lr_1": {},
    });
    at("/settings?tab=approval");
    expect(await screen.findByText(/3 changes applied by itself today · pauses itself at 50 a day/)).toBeInTheDocument();
    expect(screen.getByText(/Fact · From an AI chat · any area/)).toBeInTheDocument();
    expect(screen.getByText("Don't file staff phone numbers")).toBeInTheDocument();
    expect(screen.getByText(/Sends less: a match has to be stronger/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /Everything your AI picks up waits/ }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ preset: "careful" }));

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "PUT").map((c) => c.body)).toContainEqual({ standing: [{ type: "fact", origin: "chat", area: "*", paused: true }] }),
    );

    fireEvent.click(screen.getByRole("radio", { name: "Relaxed" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT").map((c) => c.body)).toContainEqual({ retrieval_policy: "relaxed" }));

    fireEvent.click(screen.getByRole("button", { name: "Forget" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/brain/learned/lr_1")).toBe(true));
  });
});

describe("Settings, On this computer", () => {
  it("labels words-only search with its lower recall and downloads the model after a yes", async () => {
    const calls = mockApi({
      "GET /api/brain/models": { matching: { enabled: true, present: false, downloading: false, about_mb: 70 } },
      "GET /api/speech": { installed: true, model: "small", present: true, ready: true, downloading: false, about_mb: 480, error: null },
      "GET /api/brain/local-models": { enabled: true, machine: { ram_gb: 16, gpu: "", gpu_gb: 0, apple_silicon: false, system: "Linux" }, roles: [] },
      "GET /api/runners": runners,
      "POST /api/brain/models/download": { matching: { enabled: true, present: false, downloading: true } },
    });
    at("/settings?tab=computer");
    expect(await screen.findByText(/Search matches exact words only, with lower recall/)).toBeInTheDocument();
    expect(screen.getByText("Words-only search")).toBeInTheDocument();
    expect(screen.getByText(/Linux · 16 GB memory · no GPU found/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Download" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/About 70 MB/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Yes, download it" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/brain/models/download")).toBe(true));
  });
});

describe("Settings, Test the Brain", () => {
  it("lists the checks from the server and starts one", async () => {
    const calls = mockApi({
      "GET /api/test-the-brain": {
        source: "builtin",
        lab: null,
        error: null,
        running: null,
        status: { run_kinds: [{ id: "health", name: "Health check", covers: "Is your Brain well formed and current?", paid: false }], ready: [] },
        builtin: { name: "built-in", reads_brain: "brain", waits: [] },
      },
      "GET /api/test-the-brain/overview": { source: "builtin", pillars: [], last: null },
      "POST /api/test-the-brain/runs": { status: 202, body: { run: null, kind: "health", state: "running", message: "" } },
    });
    at("/settings?tab=test");
    expect(await screen.findByText("No pillars measured yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Run" }));
    expect(await screen.findByText("Health check")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "health" }));
  });
});

describe("Settings, Backups", () => {
  it("shows an empty state, then backs up now", async () => {
    const calls = mockApi({
      "GET /api/backups": [],
      "POST /api/backups": { status: 201, body: { name: "workspace-1.zip", size: 2048, records: 10, files: 2, brain_files: 5, originals: 0 } },
    });
    at("/settings?tab=backups");
    expect(await screen.findByText("No backups yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back up now" }));
    expect(await screen.findByText(/Backed up: workspace-1.zip, 2 KB/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/backups")).toBe(true);
  });

  it("lists backups with a download link", async () => {
    mockApi({ "GET /api/backups": [{ name: "workspace-20261020.zip", size: 3 * 1024 * 1024, at: "2026-10-20T07:00:00Z" }] });
    at("/settings?tab=backups");
    expect(await screen.findByText(/workspace-20261020.zip · 3.0 MB/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", "/api/backups/workspace-20261020.zip");
  });
});

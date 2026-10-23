// A capture's page: its text, the original to download, where it stands, its proposals on the
// Brain or as a list, and Exclude.

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { CaptureDetailPage } from "./CaptureDetail";

const capture = {
  id: "n1",
  title: "Planning call",
  body: "We agreed to ship on Friday.\n\nPat owns the release notes.",
  revision: 1,
  version: 2,
  created_by: "act_owner",
  created_at: "2026-10-22T10:00:00Z",
  updated_at: "2026-10-22T10:00:00Z",
  edited_by: null,
  archived_at: null,
  capture: "recording",
  original: { filename: "planning.webm", mime: "audio/webm", size: 3 * 1024 * 1024 },
  transcription: { state: "ready", progress: 1, duration: 600, error: null },
  projects: [],
};

const status = {
  item_id: "n1",
  status: "awaiting_review",
  label: "Awaiting review",
  stage: "review",
  detail: "",
  can_retry: false,
  waiting: 1,
  kept: 0,
  skipped: 0,
  searchable: 0,
  task_id: "task_1",
  proposal_ids: ["note-1"],
};

const proposal = {
  id: "note-1",
  kind: "note.create",
  scope: "work",
  route_key: "Releases/Schedule",
  title: "Ship on Friday",
  note_summary: "",
  summary: "Releases ship on Fridays.",
  body: "Releases ship on Fridays.",
  current_body: null,
  created: "2026-10-22T10:05:00Z",
  proposer: "act_claude",
  reason: "",
  similar: "",
  conflicts: "",
  source: { id: "context_item:n1", version: "v2", locator: "at 01:10", speaker: "Pat", excerpt: "We agreed to ship on Friday." },
  operation: "new note",
  statement_status: "stated",
  effective: "",
  destination: "Releases/Schedule",
  op_id: "",
  target: {},
};

function base(over: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/notes/n1": capture,
    "GET /api/captures/status": { n1: status },
    "GET /api/brain/proposals": [proposal],
    "GET /api/brain/distill/requests": [{ task_id: "task_1", left_out: [{ statement: "Small talk about lunch", why: "Not work context" }], proposals: [], items: ["n1"] }],
    "GET /api/brain/projects": [],
    ...over,
  });
}

afterEach(() => vi.restoreAllMocks());

describe("Capture detail", () => {
  it("shows the capture's own text, its original and where it stands", async () => {
    base();
    renderAt(<CaptureDetailPage />, { path: "/capture/:captureId", route: "/capture/n1" });
    expect(await screen.findByRole("heading", { name: "Planning call" })).toBeInTheDocument();
    expect(screen.getByText("We agreed to ship on Friday.")).toBeInTheDocument();
    expect(screen.getByText("Pat owns the release notes.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the original" })).toHaveAttribute("href", "/api/captures/n1/original?download=true");
    expect(await screen.findByText(/1 piece waits for you/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Transcript" })).toBeInTheDocument();
  });

  it("shows its proposals on the Brain, with what was left out, and as cards", async () => {
    base();
    renderAt(<CaptureDetailPage />, { path: "/capture/:captureId", route: "/capture/n1" });
    await userEvent.click(await screen.findByRole("tab", { name: /Distill into context/ }));
    expect(await screen.findByRole("img", { name: "Piece 1 lands in Long-term memory" })).toBeInTheDocument();
    expect(screen.getByText("Left out · Not work context")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "As a list" }));
    expect(await screen.findByRole("article", { name: "Proposal note-1" })).toBeInTheDocument();
  });

  it("excludes it with a reason", async () => {
    const calls = base({ "POST /api/captures/n1/exclude": { ...status, status: "excluded", stage: "captured" } });
    renderAt(<CaptureDetailPage />, { path: "/capture/:captureId", route: "/capture/n1" });
    await userEvent.type(await screen.findByLabelText("Why it stays out"), "personal");
    await userEvent.click(screen.getByRole("button", { name: "Exclude" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/captures/n1/exclude")).toBe(true));
    expect(calls.find((c) => c.path === "/api/captures/n1/exclude")?.body).toEqual({ reason: "personal" });
  });

  it("says so when the capture can't be found", async () => {
    base({ "GET /api/notes/n1": { status: 404, body: { error: { code: "not_found", message: "No note n1." } } } });
    renderAt(<CaptureDetailPage />, { path: "/capture/:captureId", route: "/capture/n1" });
    expect(await screen.findByText("Not found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows the transcription still running instead of text", async () => {
    base({ "GET /api/notes/n1": { ...capture, body: "", transcription: { state: "working", progress: 0.4, duration: null, error: null } } });
    renderAt(<CaptureDetailPage />, { path: "/capture/:captureId", route: "/capture/n1" });
    expect(await screen.findByText(/Turning it into text on this computer · 40%/)).toBeInTheDocument();
  });
});

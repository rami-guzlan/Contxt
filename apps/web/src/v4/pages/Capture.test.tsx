// Capture: the only intake (write or paste, upload, record a meeting), every source with its real
// status, a source's section with its lifecycle and proposals, the thread to the Brain, Scout.

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { CapturePage } from "./Capture";

const note = (id: string, title: string, capture = "document", extra = {}) => ({
  id,
  title,
  body: null,
  revision: 1,
  version: 1,
  created_by: "act_owner",
  created_at: "2026-10-22T10:00:00Z",
  updated_at: "2026-10-22T10:00:00Z",
  edited_by: null,
  archived_at: null,
  capture,
  original: capture === "document" ? { filename: `${title}.pdf`, mime: "application/pdf", size: 2048 } : null,
  transcription: null,
  projects: [],
  ...extra,
});

const status = (id: string, s: string, extra = {}) => ({
  item_id: id,
  status: s,
  label: s,
  stage: { captured: "captured", analysis_pending: "analysis", awaiting_review: "review", failed: "analysis", excluded: "captured", partial: "searchable" }[s] ?? "captured",
  detail: "",
  can_retry: false,
  waiting: 0,
  kept: 0,
  skipped: 0,
  searchable: 0,
  task_id: null,
  proposal_ids: [],
  ...extra,
});

const proposal = {
  id: "sheet-write-abc123",
  kind: "sheet.write",
  scope: "work",
  route_key: "Registrations/Session A",
  title: "Session A registrations",
  note_summary: "",
  summary: "Session A has 120 registrations.",
  body: "Session A has 120 registrations.",
  current_body: null,
  created: "2026-10-22T10:05:00Z",
  proposer: "act_claude",
  reason: "A count that moves.",
  similar: "",
  conflicts: "",
  source: { id: "context_item:n1", version: "v1", locator: "row 4", speaker: "unknown", excerpt: "Session A, 120 registered" },
  operation: "update a sheet value",
  statement_status: "stated",
  effective: "",
  destination: "Registrations › Session A › Registered",
  op_id: "op1",
  target: {},
};

const scout = {
  folders: [{ path: "/home/test/Work", project: null }],
  formats: { md: true, pdf: true, pptx: false },
  last_inspection: "2026-10-22T09:00:00Z",
  last_error: null,
  files_seen: 12,
  differences: [{ id: "scd_1", kind: "changed", path: "/home/test/Work/plan.md", size: 900, project: null, at: "2026-10-22T09:00:00Z", status: "waiting" }],
  later: ["Watching folders"],
};

function base(over: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/notes": [note("n1", "Registrations export"), note("n2", "Weekly sync", "recording")],
    "GET /api/captures/status": { n1: status("n1", "awaiting_review", { waiting: 1, proposal_ids: ["sheet-write-abc123"] }), n2: status("n2", "captured") },
    "GET /api/scout": scout,
    "GET /api/brain/projects": [],
    "GET /api/brain/proposals": [proposal],
    "GET /api/brain/distill/requests": [],
    ...over,
  });
}

afterEach(() => vi.restoreAllMocks());

describe("Capture", () => {
  it("lists the real sources with their real status, and Scout's folders and differences", async () => {
    base();
    renderAt(<CapturePage />);
    expect(await screen.findByText("Registrations export")).toBeInTheDocument();
    expect(screen.getByText("Weekly sync")).toBeInTheDocument();
    expect(await screen.findByText("Awaiting review")).toBeInTheDocument();
    expect(screen.getByText("Captured")).toBeInTheDocument();
    expect(screen.getByText("2 sources")).toBeInTheDocument();
    expect(await screen.findByText("/home/test/Work")).toBeInTheDocument();
    expect(screen.getByText("plan.md changed")).toBeInTheDocument();
    expect(screen.getAllByText("Later").length).toBeGreaterThanOrEqual(3);
  });

  it("says so when nothing has come in yet", async () => {
    base({ "GET /api/notes": [] });
    renderAt(<CapturePage />);
    expect(await screen.findByText(/Nothing here yet/)).toBeInTheDocument();
  });

  it("shows a failure with Try again", async () => {
    base({ "GET /api/notes": { status: 500, body: { error: { code: "error", message: "The server is down." } } } });
    renderAt(<CapturePage />);
    expect(await screen.findByText("The server is down.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try again" }).length).toBeGreaterThan(0);
  });

  it("saves pasted text to Capture", async () => {
    const calls = base({ "POST /api/notes": note("n3", "Pasted", "note") });
    renderAt(<CapturePage />);
    await userEvent.type(screen.getByLabelText("Write or paste"), "Invoices are due in 14 days.");
    await userEvent.click(screen.getByRole("button", { name: "Save to Capture" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/notes")).toBe(true));
    expect(calls.find((c) => c.path === "/api/notes" && c.method === "POST")?.body).toEqual({ body: "Invoices are due in 14 days." });
  });

  it("uploads a file as a capture", async () => {
    const calls = base({ "POST /api/captures": note("n4", "Brief") });
    renderAt(<CapturePage />);
    const input = screen.getByLabelText("Choose a file to upload");
    await userEvent.upload(input, new File(["hello"], "brief.txt", { type: "text/plain" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/captures")).toBe(true));
    expect(calls.find((c) => c.path === "/api/captures")?.body).toBeInstanceOf(FormData);
  });

  it("opens a source's section with its lifecycle and proposals, and keeps a piece", async () => {
    const calls = base({ "POST /api/brain/decisions": { results: [{ id: proposal.id, ok: true, message: "kept" }], checkpoint: { id: "cp_1" } } });
    renderAt(<CapturePage />);
    await userEvent.click(await screen.findByRole("button", { name: /Registrations export/ }));
    const section = await screen.findByRole("region", { name: "Registrations export" });
    expect(within(section).getByRole("list", { name: "Where this source is" })).toBeInTheDocument();
    expect(within(section).getByText(/1 piece waits for you/)).toBeInTheDocument();
    expect(await within(section).findByText("Pieces from this source · 1 waiting")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Keep" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/decisions")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/decisions")?.body).toEqual({ decisions: [{ action: "approve", proposal_id: proposal.id }] });
  });

  it("shows where a piece lands on the Brain", async () => {
    base();
    renderAt(<CapturePage />);
    await userEvent.click(await screen.findByRole("button", { name: /Registrations export/ }));
    await userEvent.click(await screen.findByRole("button", { name: "See it on your Brain" }));
    const dialog = await screen.findByRole("dialog", { name: "See it on your Brain" });
    expect(within(dialog).getByRole("img", { name: "Piece 1 lands in Context sheets" })).toBeInTheDocument();
    expect(within(dialog).getByText(/PIECE 1 OF 1/)).toBeInTheDocument();
    expect(within(dialog).getByText("True right now, but likely to change?")).toBeInTheDocument();
  });

  it("starts a distill request for a captured source", async () => {
    const calls = base({ "POST /api/brain/distill/requests": { id: "task_1" } });
    renderAt(<CapturePage />);
    await userEvent.click(await screen.findByRole("button", { name: /Weekly sync/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Distill" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/brain/distill/requests" && c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.path === "/api/brain/distill/requests" && c.method === "POST")?.body).toEqual({ item_ids: ["n2"], start: true });
  });

  it("retries a failed reading with the same model, and includes an excluded source", async () => {
    const calls = base({
      "GET /api/captures/status": {
        n1: status("n1", "failed", { can_retry: true, task_id: "task_9", detail: "The operating system denied access." }),
        n2: status("n2", "excluded", { detail: "personal" }),
      },
      "POST /api/captures/n1/read-again": { id: "task_10" },
      "POST /api/captures/n2/include": status("n2", "captured"),
    });
    renderAt(<CapturePage />);
    await userEvent.click(await screen.findByRole("button", { name: /Registrations export/ }));
    expect(await screen.findByText(/The operating system denied access/)).toBeInTheDocument();
    expect(screen.getByText("Failed at analysis")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I’ve allowed access" }));
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/captures/n1/read-again")).toBe(true));

    await userEvent.click(screen.getByRole("button", { name: /Weekly sync/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Include in Brain" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/captures/n2/include")).toBe(true));
  });

  it("scans, brings a difference in and dismisses another", async () => {
    const calls = base({
      "POST /api/scout/scan": { ...scout, found: [{ kind: "renamed", path: "/home/test/Work/b.md", from: "/home/test/Work/a.md", quiet: true }], unreadable: [] },
      "POST /api/scout/differences/scd_1/bring-in": { capture_id: "n9" },
      "PUT /api/scout": scout,
    });
    renderAt(<CapturePage />);
    await userEvent.click(await screen.findByRole("button", { name: "Scan now" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/scout/scan")).toBe(true));
    expect(await screen.findByText(/1 rename \(a\.md → b\.md\) recognised and not proposed/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bring in →" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/scout/differences/scd_1/bring-in")).toBe(true));
    expect(await screen.findByText("plan.md is in Capture now.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: ".pptx" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.path === "/api/scout")?.body).toEqual({ formats: { pptx: true } }));
  });
});

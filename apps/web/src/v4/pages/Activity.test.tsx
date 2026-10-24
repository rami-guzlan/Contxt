// Activity: the requests each app made with their receipts, the real cost numbers, undo points
// (undoing together when later changes depend on one) and the tasks being handed on.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ActivityPage } from "./Activity";

const now = new Date().toISOString();

function req(over: Record<string, unknown>) {
  return {
    id: "pk_1",
    session_id: "s_1",
    at: now,
    request: "draft the launch note",
    mode: "task",
    app: "Claude Code",
    client: "claude-code",
    tokens: 640,
    share: 0.1,
    project: null,
    skill: null,
    got: [{ kind: "note", id: "voice-rules", tokens: 300, why: "matches the request", title: "Voice rules", topic_label: "Writing" }],
    kernel: false,
    opened: [],
    nothing: false,
    saved: [],
    engine: null,
    old_engine: false,
    ...over,
  };
}

const requests = {
  requests: [req({}), req({ id: "pk_2", app: "Cursor", client: "cursor", request: "which port does it use", nothing: true, got: [], tokens: 0, share: null })],
  brain_tokens: 6400,
  apps: ["Claude Code", "Cursor"],
  engine: "e1",
};

const receipt = (id: string) => ({
  id,
  session_id: "s_1",
  at: now,
  request: "x",
  scope: [],
  partition: null,
  sent: [{ id: "voice-rules", title: "Voice rules" }],
  opened: [],
  did_not_fit: [],
  already_delivered: [],
  unknown: [],
  conflicts: [],
  older: [],
  tokens: { packet: 300, map: 0, opened: 0, total: 300, budget: null, counted: "estimated" },
  text: "",
  complete: false,
  note: "",
});

const base = {
  "GET /api/brain/weekly": [{ start: "2026-10-19", end: "2026-10-25", conversations: 5, packets: 12 }],
  "GET /api/brain/receipts/pk_1": receipt("pk_1"),
  "GET /api/brain/receipts/pk_2": receipt("pk_2"),
};

describe("Activity", () => {
  it("lists the real requests, opens each one's receipt, and filters by app", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/brain/requests": (call: { path: string }) =>
        call.path.includes("app=Cursor") ? { ...requests, requests: [requests.requests[1]] } : requests,
    });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity" });
    expect(await screen.findByRole("button", { name: /draft the launch note/ })).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument(); // asks this week, from the server
    expect(screen.getAllByText("Evidence receipt").length).toBe(1);
    expect(screen.getByText("640 tokens")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /which port does it use/ }));
    expect(await screen.findByText(/Nothing in your Brain matched/)).toBeInTheDocument();
    expect(await screen.findByText("pk_2")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Cursor" }));
    await screen.findByRole("button", { name: /which port does it use/ });
    expect(calls.some((c) => c.path.startsWith("/api/brain/requests") && c.path.includes("app=Cursor"))).toBe(true);
    expect(screen.queryByRole("button", { name: /draft the launch note/ })).not.toBeInTheDocument();
  });

  it("says when no app has asked yet", async () => {
    mockApi({ ...base, "GET /api/brain/requests": { requests: [], brain_tokens: 0, apps: [], engine: "e1" } });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity" });
    expect(await screen.findByText("No requests yet")).toBeInTheDocument();
  });

  it("shows a failure with Try again", async () => {
    mockApi({ ...base, "GET /api/brain/requests": { status: 500, body: { error: { code: "error", message: "The Brain did not answer." } } } });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity" });
    expect(await screen.findByText("The Brain did not answer.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows only the report's real numbers", async () => {
    const day = (d: string, brief: number, packets: number) => ({
      day: d,
      lines: {},
      total_usd: 0,
      total_tokens: brief,
      sources: {},
      packets,
      brief_tokens: brief,
      median_brief_by_type: {},
    });
    mockApi({
      ...base,
      "GET /api/brain/requests": requests,
      "GET /api/brain/report": {
        days: 7,
        per_day_usd: 0,
        spend: { days: [day("2026-10-21", 1000, 2), day("2026-10-22", 3000, 2)], model: "" },
        brief_tokens_by_type: {},
        eval_set: { cases: 0, labeled: 0, held_out: 0 },
        text: "",
      },
    });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity?tab=report" });
    expect(await screen.findByText("4,000")).toBeInTheDocument();
    expect(screen.getByText("1,000")).toBeInTheDocument();
    expect(screen.getByText("1 in 10")).toBeInTheDocument();
    expect(screen.getByText(/Not measured yet/)).toBeInTheDocument();
  });

  it("undoes a point, and offers to undo the later ones together when the server names them", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/brain/requests": requests,
      "GET /api/brain/activity": [],
      "GET /api/brain/checkpoints": [
        {
          id: "cp_2",
          at: now,
          by: "you",
          kind: "decisions",
          label: "Kept 2",
          source: {},
          decisions: [],
          files: [],
          undoes: null,
          undone_by: null,
          undone_at: null,
          blocked: [{ path: "vault/a.md", what: "Invoice terms" }],
          undoable: false,
        },
      ],
      "POST /api/brain/checkpoints/cp_2/undo": (call: { path: string }) =>
        call.path.includes("together=true")
          ? { undone: "cp_2", checkpoint: null }
          : {
              status: 409,
              body: {
                error: {
                  code: "conflict",
                  message: "Undoing “Kept 2” also undoes “Edited 1”, which changed the same entries after it.",
                  dependents: [{ id: "cp_3", label: "Edited 1", at: now }],
                  blocked: [],
                },
              },
            },
    });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity?tab=changes" });
    await userEvent.click(await screen.findByRole("tab", { name: "Undo points" }));
    await userEvent.click(await screen.findByRole("button", { name: "Undo Kept 2" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/also undoes “Edited 1”/)).toBeInTheDocument();
    expect(within(alert).getByText(/Edited 1 ·/)).toBeInTheDocument();
    await userEvent.click(within(alert).getByRole("button", { name: "Undo them together" }));
    expect(await screen.findByText(/Undid “Kept 2” and the changes after it/)).toBeInTheDocument();
    const undos = calls.filter((c) => c.method === "POST" && c.path.startsWith("/api/brain/checkpoints/cp_2/undo"));
    expect(undos.map((c) => c.path)).toEqual(["/api/brain/checkpoints/cp_2/undo", "/api/brain/checkpoints/cp_2/undo?together=true"]);
  });

  it("shows the tasks by lane and finishes one with evidence", async () => {
    const task = {
      id: "T1",
      row: "r1",
      task: "Write the launch note",
      goal: null,
      project: "Launch",
      for: null,
      milestone: false,
      owner: "you",
      owner_label: "You",
      tool: null,
      status: "working",
      status_words: "working",
      due: null,
      evidence: [],
      card: {},
      created: now,
      updated: now,
      days_open: 1,
      since_update: 0,
    };
    const calls = mockApi({
      ...base,
      "GET /api/brain/requests": requests,
      "GET /api/work/handoffs": {
        lanes: { waiting_for_you: [], handed_off: [], working: [task], blocked: [], open: [] },
        done_this_week: [],
        count: 1,
      },
      "GET /api/work/handoffs/T1": { ...task, log: [{ kind: "claim", at: now, by: "You" }], rendered: "" },
      "POST /api/work/handoffs": { task: { ...task, status: "done" }, card: "", task_status: "done" },
    });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity?tab=tasks" });
    const doing = await screen.findByRole("group", { name: "Doing" });
    expect(within(doing).getByText("Write the launch note")).toBeInTheDocument();
    expect(await screen.findByText(/Claim · You/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Finish" }));
    await userEvent.type(screen.getByLabelText("Evidence"), "out_9");
    await userEvent.click(screen.getByRole("button", { name: "Mark done" }));
    expect(await screen.findByText("Marked done.")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/work/handoffs");
    expect(post?.body).toEqual({ task: "T1", status: "done", evidence: ["out_9"] });
  });

  it("says when there are no tasks", async () => {
    mockApi({
      ...base,
      "GET /api/brain/requests": requests,
      "GET /api/work/handoffs": { lanes: { waiting_for_you: [], handed_off: [], working: [], blocked: [], open: [] }, done_this_week: [], count: 0 },
    });
    renderAt(<ActivityPage />, { path: "/activity", route: "/activity?tab=tasks" });
    expect(await screen.findByText("No tasks yet")).toBeInTheDocument();
  });
});

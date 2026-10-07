// Notes: your scratchpad, saved as you type, with versions; added to the Brain as a document,
// read by a model for what to remember, or a selection suggested in your own words. The rich
// editor is a plain text box here (jsdom cannot run ProseMirror).

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../test/render";
import { CapturePage } from "./Capture";
import { NotePage } from "./Notes";

vi.mock("../components/RichEditor", () => ({
  default: ({
    markdown,
    label,
    onChange,
    onSelection,
  }: {
    markdown: string;
    label: string;
    onChange: (text: string) => void;
    onSelection?: (text: string) => void;
  }) => (
    <div>
      <textarea aria-label={label} defaultValue={markdown} onChange={(event) => onChange(event.target.value)} />
      <button type="button" onClick={() => onSelection?.("Video keeps its budget.")}>
        select a sentence
      </button>
    </div>
  ),
}));

const stamp = "2026-10-05T13:00:00.000000Z";
const note = {
  id: "ctx_1",
  title: "Campaign ideas",
  body: "Video first.",
  revision: 2,
  version: 3,
  created_by: "act_owner",
  created_at: stamp,
  updated_at: stamp,
  edited_by: "Owner",
  archived_at: null,
};
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
  actor_id: "act_claude",
  detail: "",
};
const project = {
  id: "q4-campaigns",
  title: "Q4 campaigns",
  summary: "The fourth-quarter campaign proposals",
  status: "active",
  active: true,
  current: "",
  next: "",
  blockers: "",
  updated: null,
  aliases: [],
  files: 0,
  updates: 0,
  topic: "projects/q4-campaigns",
};
const base = {
  "GET /api/notes/ctx_1": note,
  "GET /api/brain/projects": [project],
  "GET /api/brain/distill/requests": [],
  "GET /api/runners": [runner],
};
const at = { path: "/capture/:noteId", route: "/capture/ctx_1" };

describe("notes", () => {
  it("lists what you brought in and makes a new note", async () => {
    const calls = mockApi({
      "GET /api/notes": [{ ...note, body: null }],
      "POST /api/notes": { ...note, id: "ctx_2", title: "Untitled note" },
    });
    const user = userEvent.setup();
    renderAt(<CapturePage />);
    expect(await screen.findByRole("link", { name: "Campaign ideas" })).toHaveAttribute("href", "/capture/ctx_1");
    await user.click(screen.getByRole("button", { name: "New note" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.path).toBe("/api/notes"));
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("saves as you type, and says when it changed elsewhere", async () => {
    let conflict = false;
    const calls = mockApi({
      ...base,
      "PUT /api/notes/ctx_1": () =>
        conflict ? { status: 409, body: { error: { code: "version_conflict", message: "changed" } } } : { ...note, body: "Video first, audio next.", version: 4 },
    });
    const user = userEvent.setup();
    renderAt(<NotePage />, at);
    const text = await screen.findByLabelText("Campaign ideas text");
    await user.type(text, " Audio next.");
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true), { timeout: 4000 });
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ expected_version: 3 });
    expect(await screen.findByText(/Saved/)).toBeInTheDocument();
    conflict = true;
    await user.type(text, "!");
    expect(await screen.findByText(/This note changed since you opened it/, undefined, { timeout: 4000 })).toBeInTheDocument();
  });

  it("adds the note to a project in the Brain, and takes it back out", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/notes/ctx_1/brain": {
        status: "applied",
        message: "Filed it.",
        proposal_id: null,
        entry_id: "card-1",
        path: "references/projects/q4-campaigns/campaign-ideas.md",
        version: 1,
        replaced: null,
        sections: 1,
        project: "q4-campaigns",
        checkpoint_id: "cp-1",
      },
      "POST /api/brain/checkpoints/cp-1/undo": { undone: "cp-1", checkpoint: null },
    });
    const user = userEvent.setup();
    renderAt(<NotePage />, at);
    const panel = await screen.findByRole("region", { name: "Add to the Brain" });
    await user.selectOptions(await within(panel).findByLabelText("Project"), "q4-campaigns");
    await user.selectOptions(within(panel).getByLabelText("Status"), "draft");
    await user.click(within(panel).getByRole("button", { name: "Add to the Brain" }));
    expect(await within(panel).findByText(/In your Brain now, version 1/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/notes/ctx_1/brain")?.body).toEqual({ project: "q4-campaigns", status: "draft" });
    await user.click(within(panel).getByRole("button", { name: "Undo" }));
    expect(await within(panel).findByText("Taken back out of the Brain.")).toBeInTheDocument();
  });

  it("asks a model to find what to remember, and runs it on this computer", async () => {
    let asked = false;
    const request = {
      task_id: "task_1",
      title: "Find what to remember in Campaign ideas",
      status: "draft",
      assignee_id: null,
      assignee_name: null,
      items: ["ctx_1"],
      created_at: stamp,
      updated_at: stamp,
      summary: "",
      proposals: [],
      waiting: true,
    };
    const calls = mockApi({
      ...base,
      "GET /api/brain/distill/requests": () => (asked ? [request] : []),
      "POST /api/notes/ctx_1/remember": () => {
        asked = true;
        return { id: "task_1", status: "draft", assignee_id: null };
      },
      "GET /api/tasks/task_1": { id: "task_1", status: "draft", assignee_id: null },
      "POST /api/runners/claude/runs": { id: "run_1", status: "running", events: [], task_title: request.title },
      "GET /api/runners/runs/run_1": { id: "run_1", status: "running", events: [], task_title: request.title },
    });
    const user = userEvent.setup();
    renderAt(<NotePage />, at);
    const panel = await screen.findByRole("region", { name: "Pull what matters" });
    expect(within(panel).getByText(/against your goals and active projects/)).toBeInTheDocument();
    await user.type(within(panel).getByLabelText("What to pull in (optional)"), "Only the decisions");
    await user.click(within(panel).getByRole("button", { name: "Pull what matters" }));
    expect(await within(panel).findByText("Waiting for a model to take it.")).toBeInTheDocument();
    await user.click(await within(panel).findByRole("button", { name: "Run now with Claude Code" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/runners/claude/runs")).toBe(true));
    expect(calls.find((c) => c.path === "/api/runners/claude/runs")?.body).toEqual({ task_id: "task_1" });
    expect(calls.find((c) => c.path === "/api/notes/ctx_1/remember")?.body).toMatchObject({ guidance: "Only the decisions" });
  });

  it("suggests the selected text to the Brain in your words", async () => {
    const calls = mockApi({
      ...base,
      "POST /api/brain/proposals": { status: "pending", message: "Waiting.", proposal_id: "p1" },
    });
    const user = userEvent.setup();
    renderAt(<NotePage />, at);
    await user.click(await screen.findByRole("button", { name: "select a sentence" }));
    const part = await screen.findByRole("region", { name: "Remember the selection" });
    await user.type(within(part).getByLabelText("Note title"), "Video budget");
    await user.click(within(part).getByRole("button", { name: "Suggest it" }));
    expect(await within(part).findByText(/waits in Review/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/brain/proposals")?.body).toMatchObject({
      title: "Video budget",
      statement: "Video keeps its budget.",
      origin: "doc:ctx_1@r2",
    });
  });

  it("puts an earlier version back", async () => {
    const calls = mockApi({
      ...base,
      "GET /api/notes/ctx_1/versions": [
        { revision: 2, title: "Campaign ideas", body: null, size: 12, by: "Owner", at: stamp, label: null, sealed: false, current: true },
        { revision: 1, title: "Ideas", body: null, size: 5, by: "Owner", at: stamp, label: "Sent to Jordan", sealed: true, current: false },
      ],
      "GET /api/notes/ctx_1/versions/1": { revision: 1, title: "Ideas", body: "Audio.", label: "Sent to Jordan" },
      "POST /api/notes/ctx_1/restore": { ...note, revision: 3, body: "Audio." },
    });
    const user = userEvent.setup();
    renderAt(<NotePage />, at);
    await user.click(await screen.findByRole("tab", { name: "Versions" }));
    await user.click(await screen.findByRole("button", { name: /Sent to Jordan/ }));
    await user.click(await screen.findByRole("button", { name: "Put this version back" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/notes/ctx_1/restore")?.body).toEqual({ revision: 1 }));
  });
});

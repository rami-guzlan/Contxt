import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../test/render";
import { RunNow } from "./RunNow";

const claude = {
  id: "claude",
  label: "Claude Code",
  provider: "claude-code",
  one_click: true,
  installed: true,
  version: "2.1.272 (Claude Code)",
  signed_in: true,
  install: "npm install -g @anthropic-ai/claude-code",
  sign_in: "claude auth login",
  actor_id: "act_claude",
  detail: "Signed in and ready.",
};
const codex = { ...claude, id: "codex", label: "ChatGPT (Codex CLI)", one_click: false, installed: false, signed_in: null };
const task = { id: "task_1", status: "ready", assignee_id: "act_claude" };

function run(status: string, events: object[]) {
  return {
    id: "lrun_1",
    runner: "claude",
    task_id: "task_1",
    task_title: "Distill 2 documents into the Brain",
    actor_id: "act_claude",
    started_by: "act_owner",
    status,
    started_at: "2026-09-28T13:00:00Z",
    finished_at: null,
    exit_code: null,
    summary: "",
    events,
  };
}

describe("run now", () => {
  it("starts the task with Claude Code and shows its work as it happens", async () => {
    let polls = 0;
    const calls = mockApi({
      "GET /api/runners": [claude, codex],
      "POST /api/runners/claude/runs": { status: 201, body: run("running", []) },
      "GET /api/runners/runs/lrun_1": () =>
        ++polls < 2
          ? run("running", [{ seq: 1, at: "", kind: "status", text: "Started the model; workspace tools connected." }])
          : run("succeeded", [
              { seq: 1, at: "", kind: "status", text: "Started the model; workspace tools connected." },
              { seq: 2, at: "", kind: "tool", name: "claim_task", text: "task_1" },
              { seq: 3, at: "", kind: "tool", name: "propose_brain_entry", text: "Launch day" },
              { seq: 4, at: "", kind: "result", ok: true, text: "Two proposals." },
              { seq: 5, at: "", kind: "done", ok: true, text: "Finished." },
            ]),
    });
    const user = userEvent.setup();
    renderAt(<RunNow task={task} />);
    await user.click(await screen.findByRole("button", { name: "Run now with Claude Code" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ task_id: "task_1" }));
    expect(await screen.findByText("propose_brain_entry", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("Two proposals.")).toBeInTheDocument();
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
  });

  it("helps a person sign in when the CLI is signed out", async () => {
    const calls = mockApi({
      "GET /api/runners": [{ ...claude, signed_in: false }, codex],
      "POST /api/runners/claude/sign-in": { opened: true, command: "claude auth login" },
      "GET /api/runners?refresh=true": [claude, codex],
    });
    const user = userEvent.setup();
    renderAt(<RunNow task={task} />);
    expect(await screen.findByText(/not signed in yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run now/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sign in to Claude Code" }));
    expect(await screen.findByText(/A terminal opened/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByRole("button", { name: "Run now with Claude Code" })).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/runners?refresh=true")).toBe(true);
  });

  it("copies the prompt that runs the task in any connected model", async () => {
    mockApi({
      "GET /api/runners": [codex],
      "GET /api/tasks/task_1/prompt": { prompt: "Call claim_task with task_id task_1." },
    });
    const user = userEvent.setup(); // provides the clipboard the page writes to
    renderAt(<RunNow task={task} />);
    expect(await screen.findByText(/set up Claude Code on this computer/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(await screen.findByRole("button", { name: "Prompt copied" })).toBeInTheDocument();
    await waitFor(async () => expect(await navigator.clipboard.readText()).toBe("Call claim_task with task_id task_1."));
  });

  it("waits for a ready task before it runs", async () => {
    mockApi({ "GET /api/runners": [claude, codex] });
    renderAt(<RunNow task={{ ...task, status: "draft" }} />);
    expect(await screen.findByRole("button", { name: "Run now with Claude Code" })).toBeDisabled();
    expect(screen.getByText("Mark the task ready to run it.")).toBeInTheDocument();
  });
});

// Capture: talk, record, upload, and what each brought-in thing says about its text.

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TalkButton, TalkProvider } from "../components/Talk";
import { ConnectionsPage } from "./Connections";
import { mockApi, renderAt } from "../test/render";
import { CapturePage } from "./Capture";
import { NotePage } from "./Notes";

vi.mock("../components/RichEditor", () => ({
  default: ({ markdown, label }: { markdown: string; label: string }) => <textarea aria-label={label} defaultValue={markdown} />,
}));

const stamp = "2026-10-05T13:00:00.000000Z";
const base = {
  revision: 1,
  version: 1,
  created_by: "act_owner",
  created_at: stamp,
  updated_at: stamp,
  edited_by: "Owner",
  archived_at: null,
  body: null,
};
const recording = {
  ...base,
  id: "ctx_rec",
  title: "Kickoff call",
  capture: "recording",
  original: { filename: "Kickoff call.m4a", mime: "audio/mp4", size: 2_000_000 },
  transcription: { state: "working", progress: 0.4, duration: null, error: null },
};
const talk = {
  ...base,
  id: "ctx_talk",
  title: "Send Dana the poll plan",
  capture: "talk",
  original: { filename: "talk.webm", mime: "audio/webm", size: 9000 },
  transcription: { state: "failed", progress: 0, duration: null, error: "Nothing was heard in it." },
};
const transcript = {
  ...base,
  id: "ctx_vtt",
  title: "Weekly sync",
  capture: "transcript",
  original: { filename: "Weekly sync.vtt", mime: "text/vtt", size: 900 },
  transcription: null,
};
const typed = { ...base, id: "ctx_note", title: "Ideas", capture: "note", original: null, transcription: null };
const ready = { installed: true, model: "small.en", present: true, ready: true, downloading: false, about_mb: 480, error: null };

describe("capture", () => {
  it("lists what was brought in, how far its text is, and filters by kind", async () => {
    const calls = mockApi({
      "GET /api/notes": [recording, talk, transcript, typed],
      "GET /api/speech": ready,
      "POST /api/captures/ctx_talk/retry": { ...talk, transcription: { ...talk.transcription, state: "pending" } },
    });
    const user = userEvent.setup();
    renderAt(<CapturePage />);
    expect(await screen.findByRole("link", { name: "Kickoff call" })).toHaveAttribute("href", "/capture/ctx_rec");
    expect(screen.getByText("Turning it into text, 40%")).toBeInTheDocument();
    expect(screen.getByText("Couldn't turn it into text")).toBeInTheDocument();
    expect(screen.getByText(/Transcript · Weekly sync\.vtt/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/captures/ctx_talk/retry")).toBe(true));
    await user.click(screen.getByRole("button", { name: "Recordings 1" }));
    expect(screen.queryByRole("link", { name: "Ideas" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kickoff call" })).toBeInTheDocument();
  });

  it("brings in a file and opens it", async () => {
    const calls = mockApi({ "GET /api/notes": [], "GET /api/speech": ready, "POST /api/captures": { status: 201, body: transcript } });
    const user = userEvent.setup();
    renderAt(<CapturePage />);
    await user.upload(await screen.findByLabelText("Files to bring in"), new File(["WEBVTT"], "Weekly sync.vtt", { type: "text/vtt" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/captures")).toBe(true));
    const form = calls.find((c) => c.path === "/api/captures")?.body as FormData;
    expect((form.get("file") as File).name).toBe("Weekly sync.vtt");
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("offers the speech model once, at the person's word", async () => {
    const calls = mockApi({
      "GET /api/notes": [],
      "GET /api/speech": { ...ready, present: false, ready: false },
      "POST /api/speech/download": { status: 202, body: { ...ready, present: false, ready: false, downloading: true } },
    });
    const user = userEvent.setup();
    renderAt(<CapturePage />);
    expect(await screen.findByText(/once its speech model is here \(about 480 MB, once\)/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Download it" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/speech/download")).toBe(true));
  });

  it("shows a recording's audio and waits for its text before its editor", async () => {
    mockApi({
      "GET /api/notes/ctx_rec": { ...recording, body: "", transcription: { ...recording.transcription, state: "pending", progress: 0 } },
      "GET /api/speech": { ...ready, present: false, ready: false },
      "GET /api/brain/projects": [],
      "GET /api/brain/distill/requests": [],
      "GET /api/runners": [],
    });
    renderAt(<NotePage />, { path: "/capture/:noteId", route: "/capture/ctx_rec" });
    expect(await screen.findByLabelText("The recording")).toHaveAttribute("src", "/api/captures/ctx_rec/original");
    expect(screen.getByRole("link", { name: "Download the original" })).toHaveAttribute("href", "/api/captures/ctx_rec/original?download=true");
    expect(await screen.findByText("Waiting for the speech model")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get the speech model" })).toHaveAttribute("href", "/settings?tab=connections");
    expect(screen.getByText("Its text appears here once it is turned into text.")).toBeInTheDocument();
    expect(screen.queryByLabelText(/text$/)).not.toBeInTheDocument();
  });
});

class FakeRecorder {
  static isTypeSupported = () => true;
  mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(["x".repeat(4000)], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

describe("talk", () => {
  beforeEach(() => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) },
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listens while Space is held and saves what was said to Capture", async () => {
    const calls = mockApi({ "POST /api/captures/talk": { status: 201, body: { ...talk, title: "Talk", transcription: { state: "pending", progress: 0, duration: null, error: null } } } });
    renderAt(
      <TalkProvider>
        <TalkButton />
      </TalkProvider>,
    );
    fireEvent.keyDown(window, { code: "Space", key: " " });
    expect(await screen.findByText(/Let go to send/)).toBeInTheDocument();
    await act(() => new Promise((done) => setTimeout(done, 650)));
    fireEvent.keyUp(window, { code: "Space", key: " " });
    await waitFor(() => expect(calls.some((c) => c.path === "/api/captures/talk")).toBe(true));
    expect(((calls[0]?.body as FormData).get("audio") as File).name).toBe("talk.webm");
    expect(await screen.findByRole("link", { name: "Open it" })).toHaveAttribute("href", "/capture/ctx_talk");
  });

  it("keeps listening after a tap until the next one, and leaves typing alone", async () => {
    const calls = mockApi({ "POST /api/captures/talk": { status: 201, body: talk } });
    renderAt(
      <TalkProvider>
        <TalkButton />
        <input aria-label="Somewhere to type" />
      </TalkProvider>,
    );
    fireEvent.keyDown(screen.getByLabelText("Somewhere to type"), { code: "Space", key: " " });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.keyDown(window, { code: "Space", key: " " });
    fireEvent.keyUp(window, { code: "Space", key: " " });
    expect(await screen.findByText(/Press again to send/)).toBeInTheDocument();
    await act(() => new Promise((done) => setTimeout(done, 600)));
    fireEvent.keyDown(window, { code: "Space", key: " " });
    await waitFor(() => expect(calls.some((c) => c.path === "/api/captures/talk")).toBe(true));
  });
});

const side = {
  "GET /api/brain/projects": [],
  "GET /api/brain/distill/requests": [],
  "GET /api/runners": [
    {
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
    },
  ],
  "GET /api/speech": ready,
};

describe("summaries", () => {
  it("shows what a capture says, how each point fits the Brain, and what it touches", async () => {
    mockApi({
      ...side,
      "GET /api/notes/ctx_vtt": {
        ...transcript,
        body: "**Dana** [00:01] We keep the videos.",
        digest: {
          state: "ready",
          summary: "Dana keeps the videos and drops the podcast.",
          points: [
            { text: "Three faculty videos in October.", fit: "new" },
            { text: "The podcast is dropped.", fit: "clashes", entry: "media-plan", why: "The plan funds it." },
          ],
          decisions: ["Drop the podcast."],
          actions: ["Sam updates the proposal."],
          questions: [],
          people: ["Dana", "Sam"],
          at: stamp,
          by: "Claude Code",
        },
      },
      "GET /api/captures/ctx_vtt/related": [{ id: "media-plan", title: "Q4 media plan", summary: "Where the money goes.", topic: "projects/q4", score: 0.8 }],
    });
    renderAt(<NotePage />, { path: "/capture/:noteId", route: "/capture/ctx_vtt" });
    const says = await screen.findByRole("region", { name: "What it says" });
    expect(within(says).getByText("Dana keeps the videos and drops the podcast.")).toBeInTheDocument();
    expect(within(says).getByText("Clashes")).toBeInTheDocument();
    expect(within(says).getByRole("link", { name: "the entry it clashes with" })).toHaveAttribute("href", "/brain/entries/media-plan");
    expect(within(says).getByText("Drop the podcast.")).toBeInTheDocument();
    expect(within(says).getByText("People: Dana, Sam")).toBeInTheDocument();
    const already = await screen.findByRole("region", { name: "In your Brain already" });
    expect(await within(already).findByRole("link", { name: "Q4 media plan" })).toHaveAttribute("href", "/brain/entries/media-plan");
  });

  it("asks for a summary with what to look for, and runs a waiting one here", async () => {
    let asked = false;
    const calls = mockApi({
      ...side,
      "GET /api/notes/ctx_vtt": () => ({ ...transcript, body: "Some text.", digest: asked ? { state: "waiting", task_id: "task_9" } : null }),
      "GET /api/captures/ctx_vtt/related": [],
      "POST /api/captures/ctx_vtt/summarize": () => {
        asked = true;
        return { status: 201, body: { id: "task_9", status: "draft", assignee_id: null } };
      },
      "GET /api/tasks/task_9": { id: "task_9", status: "draft", assignee_id: null, template: "digest" },
      "POST /api/runners/claude/runs": { id: "run_9", status: "running", events: [], task_title: "Summarize" },
      "GET /api/runners/runs/run_9": { id: "run_9", status: "running", events: [], task_title: "Summarize" },
    });
    const user = userEvent.setup();
    renderAt(<NotePage />, { path: "/capture/:noteId", route: "/capture/ctx_vtt" });
    const says = await screen.findByRole("region", { name: "What it says" });
    await user.type(within(says).getByLabelText("Anything to look for (optional)"), "who owns each action");
    await user.click(within(says).getByRole("button", { name: "Summarize" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/captures/ctx_vtt/summarize")?.body).toEqual({ guidance: "who owns each action" }));
    expect(await screen.findByText("Nothing in your Brain touches this yet: what you pull in from it will be new.")).toBeInTheDocument();
    expect(await within(says).findByText("Waiting for a model to summarize it.")).toBeInTheDocument();
    await user.click(await within(says).findByRole("button", { name: "Run now with Claude Code" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/runners/claude/runs")?.body).toEqual({ task_id: "task_9" }));
  });

  it("turns summaries as things arrive on and off", async () => {
    const calls = mockApi({
      "GET /api/actors": [],
      "GET /api/providers": [],
      "GET /api/runners": [],
      "GET /api/speech": ready,
      "GET /api/captures/settings": { summarize: true },
      "PUT /api/captures/settings": { summarize: false },
    });
    const user = userEvent.setup();
    renderAt(<ConnectionsPage embedded />);
    const toggle = await screen.findByRole("checkbox", { name: "Summarize what you bring in as it arrives" });
    expect(toggle).toBeChecked();
    await user.click(toggle);
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ summarize: false }));
  });
});

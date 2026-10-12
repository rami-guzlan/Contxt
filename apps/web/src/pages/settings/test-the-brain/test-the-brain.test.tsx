import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt, type Call } from "../../../test/render";
import { TestTheBrain } from "./TestTheBrain";
import { FlowMap, dotsFor } from "./FlowMap";

const WAITS = "Waits for the retrieval engine (build step 3b)";

const status = {
  run_kinds: [
    { id: "health", name: "Health check", covers: "Is your Brain well formed?", paid: false, last: { at: "2026-10-10T10:00:00Z", seconds: 2.5, usd: 0 }, suites: [] },
    { id: "difference", name: "See the difference", covers: "One request, twice.", paid: true, estimate: { calls: 3, seconds: 120 }, suites: [] },
  ],
  ready: [
    { suite: "Health check", setup: "this computer", state: "ready" },
    { suite: "The machine check", setup: "this computer", state: "waiting_step", note: WAITS },
    { suite: "Your labeled requests", setup: "this computer", state: "waiting_labels", note: "Label some of your requests in Activity first." },
  ],
  labels: { labeled: 12, total: 40, held_out: 4 },
  qualification: [],
  lock_holder: null,
  brain: "demo",
};

const builtinState = {
  source: "builtin",
  lab: null,
  error: null,
  status,
  running: null,
  builtin: {
    name: "Checks on your own Brain",
    reads_brain: "demo",
    waits: [status.ready[1]],
    computer: { system: "Windows 11", cpus: 8, python: "3.13", engine: false, matching: { enabled: true, present: false } },
  },
};

const labState = {
  ...builtinState,
  source: "lab",
  lab: { name: "Stub Lab", folder: "C:/labs/stub", contract: 1 },
  builtin: undefined,
};

const overview = {
  source: "builtin",
  pillars: [
    { id: "retrieval", name: "Retrieval", total: 2, measured: 2, met: 1, confident: 1, headline: { id: "r", name: "Needed-note recall, held out", value: 0.78, ci: [0.69, 0.86], bar: { op: ">=", value: 0.9 } }, trend: [0.7, 0.78] },
    { id: "briefs", name: "Briefs", total: 0, measured: 0, met: 0, confident: 0, headline: null, trend: [] },
    { id: "management", name: "Context management", total: 1, measured: 0, met: 0, confident: 0, headline: null, trend: [] },
    { id: "agent", name: "Knowledge agent", total: 0, measured: 0, met: 0, confident: 0, headline: null, trend: [] },
  ],
  effect: null,
  ready: status.ready,
  labels: status.labels,
  card: { days: 7, per_day_usd: 0.42, brief_tokens_by_type: { standard: 900 }, by_day: [{ day: "2026-10-09", total_usd: 0.4, lines: {} }] },
  last: { run: "r1", kind: "health", ended: "2026-10-10T10:00:00Z", valid: true },
  lock_holder: null,
};

const idle = { active: null, events: [], next: 0 };

function at(view: string, extra = "") {
  return { path: "/settings", route: `/settings?tab=test&view=${view}${extra}` };
}

afterEach(() => vi.useRealTimers());

describe("Test the Brain", () => {
  it("offers the seven views and says where the tests come from", async () => {
    mockApi({ "GET /api/test-the-brain": builtinState, "GET /api/test-the-brain/overview": overview });
    renderAt(<TestTheBrain />, at("overview"));
    expect(await screen.findByText("Checks on your own Brain")).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["Overview", "Run", "Gates", "Cases", "Watch it work", "This computer", "History"]);
    expect(screen.getByRole("button", { name: "Connect a Lab" })).toBeInTheDocument();
  });

  it("connects a Lab by its folder and disconnects it again", async () => {
    const calls = mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/overview": overview,
      "POST /api/test-the-brain/lab": labState,
    });
    renderAt(<TestTheBrain />, at("overview"));
    await userEvent.click(await screen.findByRole("button", { name: "Connect a Lab" }));
    await userEvent.type(screen.getByLabelText("The Lab's folder"), "C:/labs/stub");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/test-the-brain/lab")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ folder: "C:/labs/stub" });
  });

  it("says plainly what is wrong with a Lab, and what to do", async () => {
    mockApi({ "GET /api/test-the-brain": { ...labState, status: null, error: "There is no lab.contract.json in that folder." }, "GET /api/test-the-brain/overview": overview });
    renderAt(<TestTheBrain />, at("overview"));
    expect(await screen.findByText(/There is no lab.contract.json in that folder. Fix the Lab's folder, or disconnect it/)).toBeInTheDocument();
  });

  it("shows each pillar, what is ready and what waits, and the report card", async () => {
    mockApi({ "GET /api/test-the-brain": builtinState, "GET /api/test-the-brain/overview": overview });
    renderAt(<TestTheBrain />, at("overview"));
    expect(await screen.findByRole("heading", { name: "Retrieval" })).toBeInTheDocument();
    expect(screen.getByText(/of 2 bars met, 1 with confidence/)).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
    expect(screen.getByText(WAITS)).toBeInTheDocument();
    expect(screen.getByText("Label some of your requests in Activity first.")).toBeInTheDocument();
    expect(screen.getByText(/12 of 40 requests labeled, 4 held out/)).toBeInTheDocument();
    expect(screen.getByText(/About/)).toHaveTextContent("$0.42");
  });

  it("starts a free run at once and streams it while it goes", async () => {
    let started = false;
    const calls = mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/live": (call: Call) =>
        !started
          ? { active: null, events: [], next: 0 }
          : call.path.includes("after=0") || !call.path.includes("after")
          ? { active: { run: "r2", ticket: "r2", kind: "health", state: "running", message: "" }, events: [{ event: "start" }, { event: "suite_start", suite: "retrieval", total: 4 }, { event: "case_done", suite: "retrieval", done: 1, total: 4 }, { event: "failure", suite: "retrieval", case: "RT-1", message: "Missed the dates" }], next: 4 }
          : { active: { run: "r2", ticket: "r2", kind: "health", state: "running", message: "" }, events: [], next: 4 },
      "POST /api/test-the-brain/runs": () => {
        started = true;
        return { run: "r2", kind: "health", state: "running" };
      },
    });
    renderAt(<TestTheBrain />, at("run"));
    await userEvent.click(await screen.findByRole("button", { name: "Run Health check" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/test-the-brain/runs")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ kind: "health" });
    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.getByLabelText("retrieval: 1 of 4 cases")).toBeInTheDocument();
    expect(screen.getByText(/Missed the dates/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel this run" })).toBeInTheDocument();
  });

  it("asks twice before a paid run, and says what it will cost", async () => {
    const calls = mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/live": idle,
      "POST /api/test-the-brain/runs": { run: "r3", kind: "difference", state: "running" },
    });
    renderAt(<TestTheBrain />, at("run"));
    await userEvent.click(await screen.findByRole("button", { name: "Run See the difference" }));
    expect(await screen.findByText(/uses paid model calls: about 3 model calls on your plan, about 2 min/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Yes, run See the difference" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(1));
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ kind: "difference", confirm: true });
  });

  it("cancels a run that is going", async () => {
    const calls = mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/live": { active: { run: "r4", ticket: "r4", kind: "health", state: "running", message: "" }, events: [], next: 0 },
      "POST /api/test-the-brain/runs/r4/cancel": { run: "r4", state: "cancelled" },
    });
    renderAt(<TestTheBrain />, at("run"));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel this run" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/test-the-brain/runs/r4/cancel")).toBe(true));
  });

  it("disables every run button while the Lab holds its run lock", async () => {
    mockApi({
      "GET /api/test-the-brain": { ...labState, status: { ...status, lock_holder: "run-from-the-pane" } },
      "GET /api/test-the-brain/live": idle,
    });
    renderAt(<TestTheBrain />, at("run"));
    expect(await screen.findByText(/The Lab is busy: run run-from-the-pane is going/)).toBeInTheDocument();
    for (const button of screen.getAllByRole("button", { name: /^Run / })) expect(button).toBeDisabled();
  });

  it("shows every gate read only, with its verdict and where it came from", async () => {
    mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/gates": {
        run: "r1",
        gates: [
          { id: "retrieval.recall", name: "Needed-note recall, held out", bar: { op: ">=", value: 0.9 }, kind: "hard", source: "BL 5.9", pillar: "retrieval", value: 0.78, ci: [0.69, 0.86], n: 45, met: false, met_confident: false, run: "r1", trend: [0.7, 0.78] },
          { id: "retrieval.noise", name: "Noise share", bar: { op: "<=", value: 0.15 }, kind: "hard", source: "BL 5.9", pillar: "retrieval", value: 0.1, ci: [0.06, 0.14], n: 45, met: true, met_confident: true, run: "r1", trend: [0.1] },
          { id: "agent.precision", name: "Agent precision", bar: { op: ">=", value: 0.8 }, kind: "watch", source: "new", pillar: "agent", value: null, ci: null, n: null, met: null, met_confident: null, run: null, trend: [] },
        ],
      },
    });
    renderAt(<TestTheBrain />, at("gates"));
    expect(await screen.findByText("Not met")).toBeInTheDocument();
    expect(screen.getByText("Met with confidence")).toBeInTheDocument();
    expect(screen.getByText("Not measured yet")).toBeInTheDocument();
    expect(screen.getByText("at least 90%")).toBeInTheDocument();
    expect(screen.getByText(/Read only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /change|edit|save|approve/i })).toBeNull();
  });

  it("draws a retrieval case with its notes colored by label, and an outcome side by side", async () => {
    mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/runs": { runs: [{ run: "r1", kind: "fast", valid: true, config: {}, cost: {}, metrics: 1, failing: 1 }] },
      "GET /api/test-the-brain/runs/r1/cases": {
        total: 2,
        skipped: 0,
        kinds: ["outcome", "retrieval"],
        cases: [
          { id: "RT-1", suite: "retrieval", kind: "retrieval", title: "Invite for the open day", sensitive: false, pass: false, measures: {} },
          { id: "OC-1", suite: "outcomes", kind: "outcome", title: "Reply to a supplier", sensitive: false, pass: true, measures: {} },
        ],
      },
      "GET /api/test-the-brain/runs/r1/cases/RT-1": {
        id: "RT-1", suite: "retrieval", kind: "retrieval", title: "Invite for the open day", sensitive: true, pass: false, measures: {}, request: "Write an invite",
        view: { notes: [{ id: "n1", title: "House style", label: "needed_delivered", form: "body", scores: { keyword: 0.8 }, why: "Names the tone" }, { id: "n2", title: "Open day dates", label: "needed_missed", form: "none", why: "Below the cut" }], standards: [{ id: "S1", name: "Under budget", pass: false }] },
      },
      "GET /api/test-the-brain/runs/r1/cases/OC-1": {
        id: "OC-1", suite: "outcomes", kind: "outcome", title: "Reply to a supplier", sensitive: false, pass: true, measures: {}, request: "Reply",
        view: { with: { text: "Dear Sam, Tuesday as agreed." }, without: { text: "Dear supplier, soon please." }, key_points: [{ text: "Names the date", with: true, without: false }], violations: [{ rule: "No exclamation marks", arm: "without", text: "Please!" }] },
      },
    });
    renderAt(<TestTheBrain />, at("cases", "&run=r1"));
    await userEvent.click(await screen.findByRole("button", { name: /Invite for the open day/ }));
    expect(await screen.findByText("Needed, delivered")).toBeInTheDocument();
    expect(screen.getByText("Needed, missed")).toBeInTheDocument();
    expect(screen.getByText("Marked sensitive")).toBeInTheDocument();
    expect(screen.getByText("Under budget")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Reply to a supplier/ }));
    const withSide = await screen.findByLabelText("With your Brain");
    expect(within(withSide).getByText(/Tuesday as agreed/)).toBeInTheDocument();
    expect(screen.getByLabelText("Without your Brain")).toHaveTextContent("soon please");
    expect(screen.getByText("Please!")).toBeInTheDocument();
  });

  it("draws a typed request stage by stage and marks the stages that wait for build step 3b", async () => {
    const calls = mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/runs": { runs: [] },
      "POST /api/test-the-brain/watch": {
        test: true, client: "contxt-test", read_only: true, request: "Write a headline", ms: 12.5, tokens: 900, mode: "lean", notes: [{ id: "n1", title: "House style", outcome: "delivered", why: "relevant", label: "" }],
        stages: [
          { id: "read", name: "Read the request", state: "done", in: 1, out: 3, ms: null, note: "Read as writing", dropped: [], added: [] },
          { id: "gate", name: "Gate", state: "waiting", in: null, out: null, ms: null, note: WAITS, dropped: [], added: [] },
          { id: "search", name: "Wide search", state: "done", in: 40, out: 9, ms: null, note: "9 candidates", dropped: [], added: [] },
          { id: "fit", name: "Fit", state: "done", in: 9, out: 4, ms: 3, note: "900 tokens", dropped: [{ id: "n9", title: "Menu", why: "skipped, over budget" }], added: [] },
        ],
      },
    });
    renderAt(<TestTheBrain />, at("watch"));
    await userEvent.type(await screen.findByLabelText("Type a request"), "Write a headline");
    await userEvent.click(screen.getByRole("button", { name: "Watch it work" }));
    await screen.findByText("Wide search");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ request: "Write a headline" });
    expect(screen.getByText(WAITS)).toBeInTheDocument();
    expect(screen.getByLabelText("40 in, 9 out")).toBeInTheDocument();
    expect(screen.getByText(/Dropped or held back \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/counts as no request in usage or evals/)).toBeInTheDocument();
  });

  it("compares any two runs: what moved and what flipped", async () => {
    const run = (id: string, engine: string) => ({ run: id, kind: "fast", valid: true, config: { engine_ref: engine }, cost: { seconds: 3, usd_estimate: 0 }, metrics: 1, failing: 0, ended: "2026-10-10T10:00:00Z" });
    mockApi({
      "GET /api/test-the-brain": builtinState,
      "GET /api/test-the-brain/runs": { runs: [run("b-new", "bbb"), run("a-old", "aaa")] },
      "GET /api/test-the-brain/compare": {
        a: "a-old", b: "b-new", config: { a: {}, b: {} },
        metrics: [{ id: "retrieval.recall:heldout", gate: "g", from: 0.78, to: 0.93, delta: 0.15, met_from: false, met_to: true }],
        flipped: [{ id: "RT-1", title: "Invite for the open day", from: false, to: true }],
      },
    });
    renderAt(<TestTheBrain />, at("history"));
    expect(await screen.findByText("Engine changed: aaa to bbb")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Compare b-new"));
    await userEvent.click(screen.getByLabelText("Compare a-old"));
    expect(await screen.findByText("up 15%")).toBeInTheDocument();
    expect(screen.getByText(/now met/)).toBeInTheDocument();
    expect(screen.getByText("Now passes")).toBeInTheDocument();
  });

  it("says what the machine check waits for, and links to the local models", async () => {
    mockApi({ "GET /api/test-the-brain": builtinState });
    renderAt(<TestTheBrain />, at("computer"));
    expect(await screen.findByText(/Waits for the retrieval engine \(build step 3b\)\. It will list each step/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the local models settings" })).toHaveAttribute("href", "/settings?tab=computer");
  });

  it("fills the stages one after another, and all at once when motion is reduced", async () => {
    const stages = ["read", "gate", "fit"].map((id) => ({ id, name: id, state: "done", in: 4, out: 3, ms: 1, note: "", dropped: [], added: [] }));
    const media = (matches: boolean) =>
      vi.stubGlobal("matchMedia", (q: string) => ({ matches, media: q, addEventListener: () => undefined, removeEventListener: () => undefined }));
    media(true);
    const reduced = render(<FlowMap stages={stages} />);
    expect(reduced.container.querySelectorAll(".ttb-stage.is-in")).toHaveLength(3);
    reduced.unmount();
    media(false);
    const moving = render(<FlowMap stages={stages} />);
    expect(moving.container.querySelectorAll(".ttb-stage.is-in").length).toBeLessThan(3);
    await waitFor(() => expect(moving.container.querySelectorAll(".ttb-stage.is-in")).toHaveLength(3), { timeout: 3000 });
    expect(moving.container.querySelectorAll(".ttb-dot").length).toBeGreaterThan(0);
    vi.unstubAllGlobals();
  });

  it("carries a few dots for a count, never a crowd", () => {
    expect(dotsFor(0)).toBe(0);
    expect(dotsFor(1)).toBeGreaterThan(0);
    expect(dotsFor(1_000_000)).toBe(6);
  });
});
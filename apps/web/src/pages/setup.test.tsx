// First-time setup: the checklist follows what the server says is done, each step's form does
// its part (your name, what the Brain should know, a project...), finishing starts the tour, and
// Home shows how far it has come until it is finished or put aside.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TourProvider } from "../components/tour/Tour";
import { mockApi, renderAt, workspace } from "../test/render";
import { SetupCard, SetupPage } from "./Setup";

const status = (done: string[], extra: Record<string, unknown> = {}) => ({
  steps: ["you", "ai", "brain", "project", "file"].map((id) => ({ id, done: done.includes(id), count: null })),
  done: done.length,
  total: 5,
  owner_name: "Owner",
  brain: { available: true, own_entries: 0, waiting: 0, projects: 0, files: 0 },
  local_model: false,
  completed_at: null,
  dismissed_at: null,
  tour_seen_at: null,
  ...extra,
});

const me = { actor_id: "act_owner", kind: "human", name: "Owner", actions: [], projects: null, workspace };

describe("first-time setup", () => {
  it("opens on the first open step and saves your name, workspace and timezone", async () => {
    const calls = mockApi({
      "GET /api/onboarding": status(["ai"]),
      "GET /api/me": me,
      "PUT /api/actors/act_owner": { ...me, name: "Sam Lee" },
      "PATCH /api/workspace": workspace,
    });
    const user = userEvent.setup();
    renderAt(<SetupPage />);
    const steps = await screen.findByRole("list", { name: "Setup steps" });
    expect(within(steps).getByRole("button", { name: "Your AI, done" })).toBeInTheDocument();
    const step = screen.getByRole("region", { name: "Make it yours" });
    await user.type(within(step).getByLabelText("Your name"), "Sam Lee");
    await user.clear(within(step).getByLabelText("This workspace's name"));
    await user.type(within(step).getByLabelText("This workspace's name"), "Sam's work");
    await user.click(within(step).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.path === "/api/actors/act_owner")?.body).toEqual({ name: "Sam Lee" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ name: "Sam's work" });
    expect(await within(step).findByText("Saved.")).toBeInTheDocument();
  });

  it("proposes what the Brain should know, and says it waits for review", async () => {
    const calls = mockApi({
      "GET /api/onboarding": status(["you", "ai"]),
      "POST /api/brain/proposals": { status: "pending", message: "Waiting", proposal_id: "p1" },
    });
    const user = userEvent.setup();
    renderAt(<SetupPage />);
    const step = await screen.findByRole("region", { name: "Tell the Brain about you" });
    await user.type(within(step).getByLabelText("Who you are and what you do"), "I run marketing alone.");
    await user.type(within(step).getByLabelText("How you want work done"), "Plain writing.");
    await user.click(within(step).getByRole("button", { name: "Propose 2 entries to the Brain" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/brain/proposals")).toHaveLength(2));
    expect(calls.filter((c) => c.path === "/api/brain/proposals").map((c) => c.body)).toEqual([
      { title: "Who I am", statement: "I run marketing alone.", kind: "identity", evidence: "Said during first-time setup.", origin: "you:setup" },
      { title: "How I want work done", statement: "Plain writing.", kind: "rule", evidence: "Said during first-time setup.", origin: "you:setup" },
    ]);
    expect(await within(step).findByRole("link", { name: "Review them now" })).toHaveAttribute("href", "/review");
  });

  it("says how to connect a Brain when none is there", async () => {
    mockApi({ "GET /api/onboarding": status(["you", "ai"], { brain: { available: false, own_entries: 0, waiting: 0, projects: 0, files: 0 } }) });
    renderAt(<SetupPage />);
    const step = await screen.findByRole("region", { name: "Tell the Brain about you" });
    expect(within(step).getByText("uv run contxt setup")).toBeInTheDocument();
  });

  it("starts a project from its step, and finishing starts the tour", async () => {
    const calls = mockApi({
      "GET /api/onboarding": status(["you", "ai", "brain"]),
      "GET /api/brain/projects": [],
      "POST /api/brain/projects": { id: "q4", title: "Q4 proposals", aliases: [] },
      "POST /api/onboarding": {},
      "GET /api/notes": [],
    });
    const user = userEvent.setup();
    renderAt(
      <TourProvider steps={[{ id: "x", chapter: "basics", title: "Tour begins", body: <p>Hi.</p> }]} patience={100}>
        <SetupPage />
      </TourProvider>,
    );
    const step = await screen.findByRole("region", { name: "Start a project" });
    await user.type(within(step).getByLabelText("Name"), "Q4 proposals");
    await user.type(within(step).getByLabelText("What it is for"), "Campaign proposals for Jordan");
    await user.type(within(step).getByLabelText("Other names you will call it"), "campaign proposals, Jordan's proposals");
    await user.click(within(step).getByRole("button", { name: "Start it" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/brain/projects" && c.method === "POST")?.body).toEqual({
        name: "Q4 proposals",
        summary: "Campaign proposals for Jordan",
        aliases: ["campaign proposals", "Jordan's proposals"],
      }),
    );
    await user.click(screen.getByRole("button", { name: /Finish and take the tour/ }));
    const finish = await screen.findByRole("region", { name: "Finish" });
    await user.click(within(finish).getByRole("button", { name: "Finish and take the tour" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/onboarding" && c.method === "POST")?.body).toEqual({ completed: true, dismissed: false }));
    expect(await screen.findByRole("dialog", { name: "Tour begins" })).toBeInTheDocument();
  });
});

describe("the setup card on Home", () => {
  it("shows how far setup has come, and can be put aside", async () => {
    const calls = mockApi({ "GET /api/onboarding": status(["you", "ai"]), "POST /api/onboarding": {} });
    const user = userEvent.setup();
    renderAt(<SetupCard />);
    const card = await screen.findByRole("region", { name: "Get set up" });
    expect(within(card).getByText("2 of 5 done. Next: the brain.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Continue setup" })).toHaveAttribute("href", "/settings?tab=start");
    await user.click(within(card).getByRole("button", { name: "Not now" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ dismissed: true }));
  });

  it("is gone once setup is finished", async () => {
    mockApi({ "GET /api/onboarding": status(["you"], { completed_at: "2026-10-05T12:00:00Z" }) });
    const { container } = renderAt(<SetupCard />);
    await waitFor(() => expect(container.querySelector(".setup-card")).toBeNull());
  });
});

// Goals and projects: the Brain's projects from the API, the to-dos across them, a nudge for a
// quiet project, and New project, which creates one in the Brain and opens it.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { ProjectsPage } from "./Projects";

const today = new Date().toISOString();
const old = new Date(Date.now() - 12 * 86_400_000).toISOString();

const project = (over: Record<string, unknown> = {}) => ({
  id: "foc_spring",
  title: "Spring launch",
  summary: "Launch the spring line",
  status: "active",
  active: true,
  current: "Copy approved, assets in review.",
  next: "Book the photographer",
  blockers: "",
  updated: today,
  aliases: [],
  files: 2,
  updates: 3,
  topic: "work/spring",
  objective: "A launch page live by May",
  ...over,
});

const task = (over: Record<string, unknown> = {}) => ({
  id: "T-4",
  row: "t-4",
  task: "Send the brief to the printer",
  goal: null,
  project: "foc_spring",
  for: null,
  milestone: false,
  owner: "you",
  owner_label: "You",
  tool: null,
  status: "open",
  status_words: "Open",
  due: null,
  evidence: [],
  card: {},
  created: today,
  updated: today,
  days_open: 1,
  since_update: 1,
  ...over,
});

const lanes = (open: unknown[] = []) => ({
  lanes: { waiting_for_you: [], handed_off: [], working: [], blocked: [], open },
  done_this_week: [],
  count: open.length,
});

describe("Projects", () => {
  it("shows each project from the API with where it stands, and the open to-dos across them", async () => {
    mockApi({
      "GET /api/brain/projects": [project()],
      "GET /api/work/handoffs": lanes([task()]),
    });
    renderAt(<ProjectsPage />, { path: "/projects", route: "/projects" });
    const card = await screen.findByRole("button", { name: /Spring launch/ });
    expect(within(card).getByText("Copy approved, assets in review.")).toBeInTheDocument();
    expect(within(card).getByText("Active")).toBeInTheDocument();
    expect(within(card).getByText("Active today")).toBeInTheDocument();
    expect(await within(card).findByText("2 files · 3 updates · 1 to-do open")).toBeInTheDocument();
    expect(screen.getByText("Send the brief to the printer")).toBeInTheDocument();
    expect(screen.getByText("1 open")).toBeInTheDocument();
    expect(screen.getAllByText("LATER", { exact: false }).length).toBeGreaterThan(0);
  });

  it("opens a project from its card", async () => {
    mockApi({ "GET /api/brain/projects": [project()], "GET /api/work/handoffs": lanes() });
    renderAt(<ProjectsPage />, { path: "/projects", route: "/projects" });
    await userEvent.click(await screen.findByRole("button", { name: /Spring launch/ }));
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("says what to do when there are no projects and no to-dos", async () => {
    mockApi({ "GET /api/brain/projects": [], "GET /api/work/handoffs": lanes() });
    renderAt(<ProjectsPage />, { path: "/projects", route: "/projects" });
    expect(await screen.findByText("No projects yet. Start one here.")).toBeInTheDocument();
    expect(await screen.findByText("No open to-dos")).toBeInTheDocument();
  });

  it("shows a failure with Try again", async () => {
    mockApi({
      "GET /api/brain/projects": { status: 500, body: { error: { code: "internal", message: "The Brain could not be read." } } },
      "GET /api/work/handoffs": lanes(),
    });
    renderAt(<ProjectsPage />, { path: "/projects", route: "/projects" });
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("The Brain could not be read.")).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("creates a project in the Brain with its name, objective and other names", async () => {
    const calls = mockApi({
      "GET /api/brain/projects": [],
      "GET /api/work/handoffs": lanes(),
      "POST /api/brain/projects": { status: 201, body: project({ id: "foc_new", title: "Autumn" }) },
    });
    renderAt(<ProjectsPage />, { path: "/projects", route: "/projects" });
    await userEvent.click(await screen.findByRole("button", { name: "New project" }));
    const dialog = screen.getByRole("dialog", { name: "New project" });
    const create = within(dialog).getByRole("button", { name: "Create" });
    expect(create).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Project name"), "Autumn");
    await userEvent.type(within(dialog).getByLabelText("Objective"), "A catalog out by September");
    await userEvent.type(within(dialog).getByLabelText("Other names"), "fall, the catalog");
    await userEvent.click(create);
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
    const made = calls.find((c) => c.method === "POST" && c.path === "/api/brain/projects");
    expect(made?.body).toEqual({
      name: "Autumn",
      summary: "A catalog out by September",
      objective: "A catalog out by September",
      aliases: ["fall", "the catalog"],
    });
  });

  it("asks where a quiet project is, and records the answer as progress", async () => {
    const calls = mockApi({
      "GET /api/brain/projects": [project({ updated: old })],
      "GET /api/work/handoffs": lanes(),
      "POST /api/brain/projects/foc_spring/updates": { status: 201, body: { status: "recorded" } },
    });
    renderAt(<ProjectsPage />, { path: "/projects", route: "/projects" });
    expect(await screen.findByText("Spring launch hasn't moved in 12 days. Where is it?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Paused" }));
    const update = calls.find((c) => c.method === "POST" && c.path === "/api/brain/projects/foc_spring/updates");
    expect(update?.body).toEqual({ summary: "Paused for now.", state: { status: "paused" } });
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { SheetView, TaskItem } from "../api/types";
import { TasksTab } from "../components/tasks/Tasks";
import { mockApi, renderAt } from "../test/render";
import { LiveSection, SheetPage } from "./work/Live";
import { OutputsPage } from "./work/Outputs";

const cell = (value: string | number, extra = {}) => ({ value, at: "2026-10-10T09:00:00Z", by: "person:owner", said_by: "owner", as_of: "", source: "app", ai: false, stale: false, ...extra });

const accounts: SheetView = {
  sheet: {
    id: "accounts",
    title: "Accounts",
    key: "Account",
    partition_by: "",
    scope: "person:owner",
    template: "accounts",
    builtin: false,
    description: "",
    columns: [
      { name: "Account", type: "text", friction: "free", age_days: null, source: "", sensitivity: "", options: [], ref: "", formula: "" },
      { name: "Health", type: "status", friction: "free", age_days: 30, source: "", sensitivity: "", options: ["green", "amber", "red"], ref: "", formula: "" },
      { name: "Renewal date", type: "date", friction: "free", age_days: null, source: "", sensitivity: "", options: [], ref: "", formula: "" },
      {
        name: "Days until renewal",
        type: "text",
        friction: "free",
        age_days: null,
        source: "",
        sensitivity: "",
        options: [],
        ref: "",
        formula: "[Renewal date] - TODAY()",
        formula_words: "Renewal date minus today",
      },
    ],
  },
  rows: [
    {
      id: "northwind",
      key: "Northwind",
      aliases: ["NW"],
      partition: "",
      created: "2026-10-01T09:00:00Z",
      updated: "2026-10-10T09:00:00Z",
      cells: { Account: cell("Northwind"), Health: cell("green", { ai: true }), "Renewal date": cell("2026-11-02") },
      computed: { "Days until renewal": 23 },
      pending: [],
    },
  ],
  summary: { rows: 1, columns: { Health: { filled: 1, by_status: { green: 1 } } } },
};

describe("Live context", () => {
  it("lists the sheets, starts one from a template, and keeps or turns down what waits", async () => {
    const calls = mockApi({
      "GET /api/work/live": {
        sheets: [accounts.sheet],
        templates: [
          { id: "accounts", title: "Accounts", builtin: false, columns: [] },
          { id: "repos", title: "Repos or services", builtin: false, columns: [] },
        ],
        waiting: [{ sheet: "accounts", sheet_title: "Accounts", row: "Northwind", column: "Contract owner", value: "Dana", event: "e1", at: "", source: "chat" }],
      },
      "POST /api/work/live/act": accounts,
    });
    renderAt(<LiveSection />);
    expect(await screen.findByRole("link", { name: "Accounts" })).toHaveAttribute("href", "/work/live/accounts");
    await userEvent.selectOptions(screen.getByLabelText("Template"), "repos");
    await userEvent.click(screen.getByRole("button", { name: "New sheet" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST").map((c) => c.body)).toEqual([
      { action: "create_sheet", fields: { template: "repos" } },
      { action: "decide", fields: { sheet: "accounts", row: "Northwind", event: "e1", accept: true } },
    ]));
  });

  it("moves a card on the board, which writes the cell", async () => {
    const calls = mockApi({ "GET /api/work/live/accounts": accounts, "POST /api/work/live/act": accounts });
    renderAt(<SheetPage />, { path: "/work/live/:sheetId", route: "/work/live/accounts?view=board" });
    const card = await screen.findByRole("article", { name: "Northwind" });
    expect(within(screen.getByRole("region", { name: /board by Health/ })).getByRole("region", { name: "green" })).toContainElement(card);
    await userEvent.selectOptions(within(card).getByLabelText("Move to"), "red");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "write", fields: { sheet: "accounts", row: "Northwind", values: { Health: "red" } } }),
    );
    expect(screen.getByLabelText("Summary")).toHaveTextContent("Health: 1 green");
  });

  it("opens a row with its marks and history, and keeps an AI value as it is", async () => {
    const calls = mockApi({
      "GET /api/work/live/accounts": accounts,
      "GET /api/work/live/accounts/history": [{ kind: "cell", id: "e2", at: "2026-10-10T09:00:00Z", column: "Health", value: "green", by: "person:owner", ai: true }],
      "POST /api/work/live/act": accounts,
    });
    renderAt(<SheetPage />, { path: "/work/live/:sheetId", route: "/work/live/accounts?view=board" });
    await userEvent.click(await screen.findByRole("button", { name: "Northwind" }));
    const drawer = screen.getByRole("complementary", { name: "Northwind" });
    expect(within(drawer).getByText("computed")).toBeInTheDocument();
    expect(await within(drawer).findByText(/an AI/)).toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "Keep as it is" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "touch", fields: { sheet: "accounts", row: "Northwind", column: "Health" } }));
  });

  it("shows the sheet as a grid with its columns", async () => {
    mockApi({ "GET /api/work/live/accounts": accounts });
    renderAt(<SheetPage />, { path: "/work/live/:sheetId", route: "/work/live/accounts" });
    const grid = await screen.findByRole("region", { name: "Accounts grid" });
    expect(await within(grid).findByText("Northwind")).toBeInTheDocument();
    expect(within(grid).getByText("Days until renewal")).toBeInTheDocument();
  });

  it("places dated rows on the calendar and shows the grid", async () => {
    mockApi({ "GET /api/work/live/accounts": accounts });
    renderAt(<SheetPage />, { path: "/work/live/:sheetId", route: "/work/live/accounts?view=calendar" });
    expect(await screen.findByRole("list", { name: "Dated rows" })).toHaveTextContent("Northwind: 2026-11-02");
  });
});

const task = (extra: Partial<TaskItem>): TaskItem => ({
  id: "T-1",
  row: "t-1",
  task: "Update the pricing skill",
  goal: null,
  project: null,
  for: null,
  milestone: false,
  owner: "Claude Code",
  owner_label: "Claude Code",
  tool: null,
  status: "handed_off",
  status_words: "Handed off",
  due: null,
  evidence: [],
  card: { done_when: "Uses the corrected figure", next_step: "Update the figure", at: "2026-10-10T09:00:00Z" },
  created: "2026-10-09T09:00:00Z",
  updated: "2026-10-09T09:00:00Z",
  days_open: 1,
  since_update: 1,
  unclaimed: true,
  ...extra,
});

describe("Tasks and handoffs", () => {
  it("shows the lanes, a task's card, and hands it on with the composer", async () => {
    const calls = mockApi({
      "GET /api/work/handoffs": {
        lanes: { waiting_for_you: [], handed_off: [task({})], working: [], blocked: [], open: [] },
        done_this_week: [],
        count: 1,
      },
      "GET /api/work/handoffs/T-1": { ...task({}), log: [], rendered: "Task T-1: Update the pricing skill\nNext step: Update the figure" },
      "POST /api/work/handoffs": { task: task({ owner: "agent:knowledge-agent" }), card: "", task_status: "handed_off" },
      "POST /api/work/handoffs/T-1/take-back": { task: task({ status: "waiting_for_you" }) },
    });
    renderAt(<TasksTab />);
    const lane = await screen.findByRole("region", { name: "Handed off" });
    expect(within(lane).getByText(/not claimed for a day/)).toBeInTheDocument();
    await userEvent.click(within(lane).getByRole("button", { name: "T-1 Update the pricing skill" }));
    const drawer = await screen.findByRole("complementary", { name: "Task T-1" });
    expect(await within(drawer).findByText(/Next step: Update the figure/)).toBeInTheDocument();
    await userEvent.click(within(drawer).getByLabelText("Knowledge agent"));
    await userEvent.click(within(drawer).getByRole("button", { name: "Hand off to Knowledge agent" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/work/handoffs")?.body).toMatchObject({
        task: "T-1",
        to: "Knowledge agent",
        done_when: "Uses the corrected figure",
        next_step: "Update the figure",
      }),
    );
    await userEvent.click(within(lane).getByRole("button", { name: "Take back" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/work/handoffs/T-1/take-back")).toBe(true));
  });

  it("draws who did what on the timeline", async () => {
    mockApi({
      "GET /api/work/handoffs": { lanes: { waiting_for_you: [], handed_off: [], working: [], blocked: [], open: [] }, done_this_week: [], count: 0 },
      "GET /api/work/handoffs/timeline": {
        since: "2026-10-03T00:00:00Z",
        owners: ["you", "Claude Code"],
        events: [
          { at: "2026-10-09T09:00:00Z", task: "T-1", title: "x", owner: "you", kind: "open" },
          { at: "2026-10-09T10:00:00Z", task: "T-1", title: "x", owner: "Claude Code", kind: "handoff", from: "you", to: "Claude Code" },
        ],
      },
    });
    renderAt(<TasksTab />);
    await userEvent.click(await screen.findByRole("tab", { name: "Timeline" }));
    expect(await screen.findByRole("button", { name: "→ Claude Code T-1" })).toBeInTheDocument();
  });
});

describe("Outputs", () => {
  it("groups by project, then by what each is for, and filters", async () => {
    const file = (path: string, extra = {}) => ({ path, name: path, folder: "", size: 10, modified: "2026-10-10T09:00:00Z", kind: "document", from: null, working: false, ...extra });
    mockApi({
      "GET /api/outputs": {
        root: "/out",
        folders: [],
        files: [
          file("renewal.md", { project: "q4", for: "accounts/Northwind", maker: "Accounts agent" }),
          file("plan.md", { project: "q4", for: null, maker: "you" }),
          file("loose.md", { project: null, for: null, maker: "you" }),
        ],
      },
      "GET /api/brain/projects": [{ id: "q4", title: "Q4 webinars", summary: "", status: "active", active: true, current: "", next: "", blockers: "", updated: null, aliases: [], files: 0, updates: 0, topic: "" }],
    });
    renderAt(<OutputsPage />);
    const q4 = await screen.findByRole("region", { name: "Q4 webinars" });
    expect(within(q4).getByText("Northwind")).toBeInTheDocument();
    expect(within(q4).getByText("renewal.md")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "No project" })).toHaveTextContent("loose.md");
    await userEvent.selectOptions(screen.getByLabelText("Project"), "none");
    expect(screen.queryByText("renewal.md")).not.toBeInTheDocument();
  });
});

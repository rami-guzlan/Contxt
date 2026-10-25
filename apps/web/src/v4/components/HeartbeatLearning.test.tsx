// Heartbeat learning on screen: Today shows what waits for the distill, what a filter dropped,
// Forget this, Bring back and Distill now; Settings sets the goal, the filters and the schedule.

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { HeartbeatToday } from "./HeartbeatToday";
import { LearningSettings } from "./LearningSettings";

const learning = (over: Record<string, unknown> = {}) => ({ goal: "", filters: [], buffer_days: 30, learn: "nightly", distill_at: "19:00", live: { connectors: [], sheets: [] }, ...over });
const entry = (over: Record<string, unknown> = {}) => ({
  id: "stg_1",
  connector_id: "claude:mail",
  connector: "mail",
  item_id: "msg-1",
  field: "text",
  title: "Morgan approved hero option B",
  url: "",
  old_value: null,
  new_value: "Approved.",
  changed_at: null,
  seen_at: new Date().toISOString(),
  score: 0.6,
  filter: "",
  unclear: false,
  status: "staged",
  outcome: null,
  ...over,
});

describe("Heartbeat, Today", () => {
  it("lists what waits for the distill by source, forgets one, brings a dropped one back and distills now", async () => {
    const calls = mockApi({
      "GET /api/heartbeat/learning": learning(),
      "GET /api/heartbeat/staged": (call: { path: string }) =>
        call.path.includes("dropped") ? [entry({ id: "stg_2", title: "Weekly newsletter", status: "dropped", filter: "your filter: newsletter" })] : [entry()],
      "GET /api/heartbeat/still-waiting": { count: 2, days: 14, items: [] },
      "POST /api/heartbeat/staged/stg_1/forget": entry({ status: "forgotten" }),
      "POST /api/heartbeat/staged/stg_2/bring-back": entry({ id: "stg_2", status: "staged" }),
      "POST /api/heartbeat/distill": { beat_id: "beat_d", status: "running" },
    });
    renderAt(<HeartbeatToday />);
    expect(await screen.findByText("Morgan approved hero option B")).toBeInTheDocument();
    expect(screen.getByText(/The distill learns from it at 19:00/)).toBeInTheDocument();
    expect(screen.getByText(/2 from the distill have waited in Catch up for over 14 days/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Forget: Morgan approved hero option B" }));
    await userEvent.click(screen.getByText(/Dropped by your filters · 1/));
    expect(screen.getByText(/your filter: newsletter/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bring back: Weekly newsletter" }));
    await userEvent.click(screen.getByRole("button", { name: "Distill now" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/heartbeat/distill")).toBe(true));
    expect(calls.some((c) => c.path === "/api/heartbeat/staged/stg_1/forget")).toBe(true);
    expect(calls.some((c) => c.path === "/api/heartbeat/staged/stg_2/bring-back")).toBe(true);
  });

  it("shows nothing when each beat judges what it reads", async () => {
    const calls = mockApi({ "GET /api/heartbeat/learning": learning({ learn: "per_beat" }), "GET /api/heartbeat/staged": [], "GET /api/heartbeat/still-waiting": { count: 0, days: 14, items: [] } });
    renderAt(<HeartbeatToday />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByRole("region", { name: "Today" })).not.toBeInTheDocument();
  });
});

describe("Settings, how it learns", () => {
  it("saves the goal, adds a filter and changes the schedule", async () => {
    const calls = mockApi({ "GET /api/heartbeat/learning": learning(), "PUT /api/heartbeat/learning": learning() });
    renderAt(<LearningSettings />);
    await userEvent.type(await screen.findByLabelText(/Your goal/), "Run the Q4 webinars");
    await userEvent.click(screen.getByRole("button", { name: "Save goal" }));
    await userEvent.type(screen.getByLabelText("New filter"), "newsletter");
    await userEvent.click(screen.getByRole("button", { name: "Add filter" }));
    await userEvent.selectOptions(screen.getByLabelText(/Learn/), "per_beat");
    const bodies = calls.filter((c) => c.method === "PUT").map((c) => c.body);
    expect(bodies).toEqual([{ goal: "Run the Q4 webinars" }, { filters: [{ pattern: "newsletter" }] }, { learn: "per_beat" }]);
  });
});

describe("Settings, apply during the day", () => {
  it("marks a connector and a sheet live", async () => {
    const calls = mockApi({
      "GET /api/heartbeat/learning": learning(),
      "PUT /api/heartbeat/learning": learning(),
      "GET /api/heartbeat/status": { connectors: [{ id: "claude:mail", name: "Gmail", how: "mcp" }] },
      "GET /api/work/live": { sheets: [{ id: "guests", title: "Guests and partners" }], templates: [], waiting: [] },
    });
    renderAt(<LearningSettings />);
    await userEvent.click(await screen.findByLabelText("Gmail"));
    await userEvent.click(screen.getByLabelText("Guests and partners"));
    const bodies = calls.filter((c) => c.method === "PUT").map((c) => c.body);
    expect(bodies[0]).toEqual({ live: { connectors: ["claude:mail"], sheets: [] } });
    expect(bodies[1]).toEqual({ live: { connectors: [], sheets: ["guests"] } });
  });
});

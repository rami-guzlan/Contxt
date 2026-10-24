// An auto-governed area's strip: "Govern this myself" makes it wait for the owner, and "Hand it
// back" returns it to the governing AI. Governed Brains show no strip.

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { AutoArea } from "./AutoArea";

const policy = (over: Record<string, unknown> = {}) => ({ mode: "auto", auto_paused: false, auto_notice: null, self_governed: [], ...over });
const status = { paused: false, quiet: false, cadence_minutes: 15, next_beat_at: null, last_beat: null, connectors: [], state: "ok", line: "" };

describe("An auto strip", () => {
  it("governs the area on request, then hands it back", async () => {
    const calls = mockApi({
      "GET /api/brain/policies": policy(),
      "GET /api/heartbeat/status": status,
      "GET /api/heartbeat/regions": [],
      "PUT /api/brain/policies": { policy: policy({ self_governed: ["sheet:guests"] }) },
    });
    renderAt(<AutoArea govKey="sheet:guests" area="this sheet" what="It writes the current values." />);
    fireEvent.click(await screen.findByRole("button", { name: /Govern this myself/ }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ self_governed: ["sheet:guests"] }));
  });

  it("says the owner governs it, and hands it back", async () => {
    const calls = mockApi({
      "GET /api/brain/policies": policy({ self_governed: ["sheet:guests", "area:people"] }),
      "PUT /api/brain/policies": { policy: policy() },
    });
    renderAt(<AutoArea govKey="sheet:guests" area="this sheet" what="It writes the current values." />);
    expect(await screen.findByText(/You govern this sheet yourself/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hand it back" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ self_governed: ["area:people"] }));
  });

  it("shows nothing when the Brain is Governed", async () => {
    const calls = mockApi({ "GET /api/brain/policies": policy({ mode: "governed" }) });
    renderAt(<AutoArea govKey="area:*" area="Catch up" what="x" />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: /Govern this myself/ })).not.toBeInTheDocument();
  });
});

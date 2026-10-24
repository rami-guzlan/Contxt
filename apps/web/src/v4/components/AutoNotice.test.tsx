// The one-time notice of the switch to Auto: keep it, or go back to Governed.

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { AutoNotice } from "./AutoNotice";

const policy = (notice: unknown) => ({ mode: "auto", auto_paused: false, auto_notice: notice, self_governed: [] });

describe("The switch to Auto", () => {
  it("says the Brain is auto-governed and goes back to Governed on request", async () => {
    const calls = mockApi({
      "GET /api/brain/policies": policy({ at: "2026-10-23T09:00:00Z", was: "governed" }),
      "PUT /api/brain/policies": { policy: policy(null) },
    });
    renderAt(<AutoNotice />);
    expect(await screen.findByText("Your Brain is auto-governed now.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go back to Governed" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ mode: "governed", auto_notice: null }));
  });

  it("shows nothing once dismissed", async () => {
    const calls = mockApi({ "GET /api/brain/policies": policy(null) });
    renderAt(<AutoNotice />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

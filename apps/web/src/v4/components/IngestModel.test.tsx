// The model that reads what comes in: Haiku by default, changeable in Settings.

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { IngestModel } from "./IngestModel";

describe("Reading what comes in", () => {
  it("shows Haiku and saves another choice", async () => {
    const calls = mockApi({
      "GET /api/brain/distill/settings": { assignee_id: null, triage: null, model: "haiku" },
      "PUT /api/brain/distill/settings": { assignee_id: null, triage: null, model: "sonnet" },
    });
    renderAt(<IngestModel />);
    const select = await screen.findByLabelText(/Reading what comes in/);
    await waitFor(() => expect(select).toHaveValue("haiku"));
    await userEvent.selectOptions(select, "sonnet");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ assignee_id: null, model: "sonnet" });
  });
});

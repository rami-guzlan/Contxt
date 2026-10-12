// The updating loop in the app (brain-logic plan 9): "That's wrong" on a request finds the note
// behind it, and Catch up asks "Still true?" with a one-tap answer, beside the loop's other asks.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { plan, request } from "../test/fixtures";
import { mockApi, renderAt } from "../test/render";
import { AiActivityPage } from "./Activity";
import { CatchUpPage } from "./CatchUp";

describe("the updating loop", () => {
  it("says what was wrong on a request and names the note most likely behind it", async () => {
    const calls = mockApi({
      "GET /api/brain/weekly": [],
      "GET /api/brain/requests": { requests: [request], brain_tokens: 6400, apps: ["Claude Code"], engine: "new" },
      "GET /api/brain/requests/pkt-1": { ...request, text: "## Task\n\nWrite a post" },
      "POST /api/loop/corrections": { card: { id: "linkedin-rules", title: "LinkedIn posting rules" }, suspects: [] },
    });
    const user = userEvent.setup();
    renderAt(<AiActivityPage />, { path: "/activity", route: "/activity" });
    await user.click(await screen.findByRole("button", { name: /Write a LinkedIn post announcing the Q4 webinars/ }));
    await user.click(screen.getByRole("button", { name: "That's wrong" }));
    await user.type(screen.getByLabelText("What was wrong?"), "Posts go out on Thursdays now");
    await user.click(screen.getByRole("button", { name: "Find the note behind it" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Most likely behind it: LinkedIn posting rules");
    expect(calls.find((c) => c.path === "/api/loop/corrections")?.body).toEqual({
      text: "Posts go out on Thursdays now",
      packet_id: "pkt-1",
      session_id: "sess-1",
    });
  });

  it("asks still true in Catch up and answers in one tap", async () => {
    const calls = mockApi({
      "GET /api/brain/catch-up": plan({
        caught_up: false,
        loop: [
          {
            key: "correction:3",
            type: "still_true",
            correction: 3,
            note: "linkedin-rules",
            title: "LinkedIn posting rules",
            text: "Posts go out on Thursdays now",
            ask: 'You corrected an AI ("Posts go out on Thursdays now"). Is "LinkedIn posting rules" still true?',
          },
          { key: "lesson:tidy-repeats:marketing:declined", type: "lesson", text: "In marketing, you declined it 3 times.", ask: "Keep this as a note, so the agent stops asking?" },
          { key: "review:2026-Q4", type: "quarterly_review", ask: "Run the alignment check?" },
        ],
      }),
      "POST /api/loop/corrections/3": { id: 3, status: "still_true" },
      "POST /api/loop/lessons": { proposal_id: "p9", status: "pending" },
    });
    const user = userEvent.setup();
    renderAt(<CatchUpPage />, { path: "/catch-up", route: "/catch-up" });
    const loop = await screen.findByRole("region", { name: "The updating loop" });
    expect(within(loop).getByText("Still true?")).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.tagName === "LI" && el.textContent === "3 things to keep true")).toBeInTheDocument();
    await user.click(within(loop).getByRole("button", { name: "Still true" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/loop/corrections/3")?.body).toEqual({ status: "still_true" }));
    await user.click(within(loop).getByRole("button", { name: "Keep as a note" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/api/loop/lessons")?.body).toEqual({ key: "lesson:tidy-repeats:marketing:declined" }));
    expect(within(loop).getByRole("button", { name: "Run the alignment check" })).toBeInTheDocument();
  });
});

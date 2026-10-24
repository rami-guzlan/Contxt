// Ask: a question goes to the chosen AI with only the Brain's tools; the answer comes back with
// the notes it cites, its receipts and who answered. A refusal shows the server's words and
// where to fix it.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { AskPage } from "./Ask";

const provider = {
  id: "claude",
  label: "Claude Code",
  vendor: "Anthropic",
  model: "model-from-test",
  model_from: "read from the CLI's own config",
  available: true,
  health: "ok",
  data: "Packets go to Anthropic through the Claude Code CLI on this computer.",
  switches: "Stops and tells you. Never switches provider on its own.",
};

const answer = {
  question: "When are invoices due?",
  answer: "Invoices are due in 14 days [invoice-days].",
  session_id: "s_1",
  receipts: ["pk_77"],
  cited: ["invoice-days"],
  asked_brain: true,
  provider,
};

const receipt = {
  id: "pk_77",
  session_id: "s_1",
  at: "2026-10-22T10:00:00Z",
  request: "When are invoices due?",
  scope: [],
  partition: null,
  sent: [{ id: "invoice-days", title: "Invoice terms" }],
  opened: [],
  did_not_fit: [],
  already_delivered: [],
  unknown: [],
  conflicts: [],
  older: [],
  tokens: { packet: 120, map: 0, opened: 0, total: 120, budget: null, counted: "estimated" },
  text: "packet text",
  complete: false,
  note: "",
};

beforeEach(() => window.sessionStorage.clear());

describe("Ask", () => {
  it("sends the question and shows the answer, its cited notes, its receipt and who answered", async () => {
    const calls = mockApi({
      "GET /api/brain/catch-up": { status: 404, body: { error: { code: "not_found", message: "none" } } },
      "POST /api/brain/agent/ask": answer,
      "GET /api/brain/receipts/pk_77": receipt,
    });
    renderAt(<AskPage />, { path: "/ask", route: "/ask" });
    expect(screen.getByText("What should your Brain know?")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your question"), "When are invoices due?{Enter}");

    expect(await screen.findByText(/Invoices are due in 14 days/)).toBeInTheDocument();
    const ask = calls.find((c) => c.method === "POST" && c.path === "/api/brain/agent/ask");
    expect(ask?.body).toEqual({ question: "When are invoices due?" });

    const links = screen.getAllByRole("link", { name: /invoice-days/ });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link).toHaveAttribute("href", "/brain/notes/invoice-days");
    expect(screen.getByText("Evidence receipt")).toBeInTheDocument();
    expect(await screen.findByText(/1 sent · 0 opened/)).toBeInTheDocument();

    const who = screen.getByRole("group", { name: "Who answered" });
    expect(within(who).getByText(/Claude Code, Anthropic, model-from-test/)).toBeInTheDocument();
    expect(within(who).getByText(provider.data)).toBeInTheDocument();

    // The conversation is kept for this viewer only.
    expect(window.sessionStorage.getItem("contxt.v4.ask.thread")).toContain("invoice-days");
  });

  it("says so when the AI answered without asking the Brain", async () => {
    mockApi({
      "GET /api/brain/catch-up": { status: 404, body: { error: { code: "not_found", message: "none" } } },
      "POST /api/brain/agent/ask": { ...answer, answer: "I am not sure.", receipts: [], cited: [], asked_brain: false },
    });
    renderAt(<AskPage />, { path: "/ask", route: "/ask" });
    await userEvent.type(screen.getByLabelText("Your question"), "Anything?{Enter}");
    expect(await screen.findByText(/answered without asking the Brain/)).toBeInTheDocument();
    expect(screen.queryByText("Evidence receipt")).not.toBeInTheDocument();
  });

  it("shows the server's refusal and how to fix it in Agents", async () => {
    mockApi({
      "GET /api/brain/catch-up": { status: 404, body: { error: { code: "not_found", message: "none" } } },
      "POST /api/brain/agent/ask": {
        status: 409,
        body: { error: { code: "conflict", message: "Ask runs through Claude Code in this release, and your chosen AI is Codex." } },
      },
    });
    renderAt(<AskPage />, { path: "/ask", route: "/ask" });
    await userEvent.type(screen.getByLabelText("Your question"), "Hello{Enter}");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/your chosen AI is Codex/)).toBeInTheDocument();
    expect(within(alert).getByRole("link", { name: "Open Agents" })).toHaveAttribute("href", "/agents");
    expect(within(alert).getByRole("button", { name: "Ask again" })).toBeInTheDocument();
  });

  it("sends the question from ?q= on arrival", async () => {
    const calls = mockApi({
      "GET /api/brain/catch-up": { status: 404, body: { error: { code: "not_found", message: "none" } } },
      "POST /api/brain/agent/ask": answer,
      "GET /api/brain/receipts/pk_77": receipt,
    });
    renderAt(<AskPage />, { path: "/ask", route: "/ask?q=When%20are%20invoices%20due%3F" });
    expect(await screen.findByText(/Invoices are due in 14 days/)).toBeInTheDocument();
    const asks = calls.filter((c) => c.method === "POST" && c.path === "/api/brain/agent/ask");
    expect(asks).toHaveLength(1);
    expect(asks[0]?.body).toEqual({ question: "When are invoices due?" });
  });

  it("shows the weekly check-in when Catch up has something waiting", async () => {
    mockApi({
      "GET /api/brain/catch-up": {
        caught_up: false,
        minutes: 4,
        counts: { judgment: 2, quick: 0, quick_items: 1, upkeep: 0, offers: 0, legacy: 0, handled: 0, snoozed: 0 },
      },
    });
    renderAt(<AskPage />, { path: "/ask", route: "/ask" });
    expect(await screen.findByText("Weekly check-in")).toBeInTheDocument();
    expect(screen.getByText(/3 things wait for you, about 4 minutes/)).toBeInTheDocument();
  });
});

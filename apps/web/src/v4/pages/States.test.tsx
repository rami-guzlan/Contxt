import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { StatesPage } from "./States";

afterEach(() => vi.restoreAllMocks());

const LABELS = [
  "EMPTY · CAPTURE",
  "EMPTY · CATCH UP",
  "LOADING · BRAIN",
  "STALE · SCOUT",
  "STALE · NOTE",
  "PERMISSION DENIED · FILE",
  "PERMISSION DENIED · SCOPE",
  "PARTIAL FAILURE · APPLY",
  "PARTIAL COVERAGE · SOURCE",
  "RETRY · ANALYSIS",
  "SIGN-IN EXPIRED · AI",
  "RECOVERY · AFTER RESTART",
  "WORDS-ONLY · SEARCH",
];

describe("States page", () => {
  it("shows every state as a reference, with where you meet it and how to reproduce it", () => {
    renderAt(<StatesPage />, { path: "/states", route: "/states" });
    expect(screen.getByRole("heading", { name: "When things aren’t ready" })).toBeInTheDocument();
    expect(screen.getByText(/A reference of states, not your Brain/)).toBeInTheDocument();
    for (const label of LABELS) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getAllByText("Where you'll meet it")).toHaveLength(LABELS.length);
    expect(screen.getAllByText("Make it happen for real")).toHaveLength(LABELS.length);
  });

  it("draws the examples with the shared parts", () => {
    renderAt(<StatesPage />, { path: "/states", route: "/states" });
    expect(screen.getAllByText("Nothing captured yet").length).toBe(2); // the title and the Empty example
    expect(screen.getByText(/Loading notes and sources…/)).toBeInTheDocument();
    expect(screen.getAllByRole("alert").length).toBeGreaterThanOrEqual(4);
    expect(screen.getAllByText("Partly searchable").length).toBe(2);
    expect(screen.getByText("Words-only search")).toBeInTheDocument();
  });

  it("reads nothing from the server: it holds none of the person's data", () => {
    const calls = mockApi({});
    renderAt(<StatesPage />, { path: "/states", route: "/states" });
    expect(calls).toHaveLength(0);
  });

  it("takes you to the real place each state appears", () => {
    renderAt(<StatesPage />, { path: "/states", route: "/states" });
    fireEvent.click(screen.getAllByRole("button", { name: "Open Capture" })[0] as HTMLElement);
    expect(screen.getByText("navigated away")).toBeInTheDocument();
  });
});

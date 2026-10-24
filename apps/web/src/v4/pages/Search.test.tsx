// Search: pages of the app, then what /api/search finds, grouped and linked; nothing found,
// and a search that fails.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { SearchPage } from "./Search";

const results = {
  query: "harbor",
  brain: [{ id: "harbor-venue", title: "Harbor venue rules", summary: "", scope: "", kind: "fact", score: 1 }],
  projects: [{ id: "pj_1", title: "Harbor launch", summary: "", status: "active", active: true }],
  notes: [{ id: "ctx_1", title: "Harbor kickoff call", body: null }],
};

describe("Search", () => {
  it("groups what the Brain finds and opens a result", async () => {
    const calls = mockApi({ "GET /api/search": results });
    renderAt(<SearchPage />, { path: "/search", route: "/search" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search notes, projects, pages" }), "harbor");
    const projects = await screen.findByRole("group", { name: "Projects" });
    expect(within(projects).getByText("Harbor launch")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Brain" })).getByText("Harbor venue rules")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Captures" })).getByText("Harbor kickoff call")).toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith("/api/search?q=harbor"))).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /Harbor launch/ }));
    expect(await screen.findByText("navigated away")).toBeInTheDocument();
  });

  it("lists the app's pages before anything is typed, and filters them", async () => {
    mockApi({});
    renderAt(<SearchPage />, { path: "/search", route: "/search" });
    expect(within(screen.getByRole("group", { name: "Pages" })).getByText("Capture")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "S");
    expect(within(screen.getByRole("group", { name: "Pages" })).getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("Type one more letter to search your Brain.")).toBeInTheDocument();
  });

  it("says when nothing matches", async () => {
    mockApi({ "GET /api/search": { query: "zzz", brain: [], projects: [], notes: [] } });
    renderAt(<SearchPage />, { path: "/search", route: "/search?q=zzz" });
    expect(await screen.findByText(/Nothing in your Brain or your captures matches “zzz”/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ask your Brain: “zzz”/ })).toBeInTheDocument();
  });

  it("says when the search fails, with Try again", async () => {
    mockApi({ "GET /api/search": { status: 500, body: { error: { code: "error", message: "Search is not reachable." } } } });
    renderAt(<SearchPage />, { path: "/search", route: "/search?q=harbor" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Search is not reachable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

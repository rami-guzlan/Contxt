// Work: the frame and its tabs, the overview of its parts, and each part as it lands.

import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { WorkOverviewPage } from "./Overview";
import { WorkLayout } from "./WorkLayout";

afterEach(() => vi.restoreAllMocks());

const skills = {
  skills: [
    {
      name: "weekly-posts",
      description: "Three LinkedIn posts for the week.",
      category: "social",
      triggers: ["weekly posts"],
      use: "run",
      used_by: [],
      artifacts: ["post"],
      makes_files: false,
      files: 1,
      last_run: null,
    },
  ],
  waiting: [{ name: "one-pager", id: "p_1" }],
};

describe("Work", () => {
  it("frames its parts as tabs, with what waits for a yes on Skills", async () => {
    mockApi({ "GET /api/brain/status": { available: true }, "GET /api/skills": skills });
    renderAt(<WorkLayout />, { path: "/work", route: "/work" });
    const tabs = await screen.findByRole("navigation", { name: "Work sections" });
    expect(within(tabs).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual(["/work", "/work/skills", "/work/outputs"]);
    expect(within(tabs).getByRole("link", { name: /Skills/ })).toHaveTextContent("1");
    expect(screen.getByRole("heading", { level: 1, name: "Work" })).toBeInTheDocument();
  });

  it("overviews its parts, each with the question it answers, and what waits for you", async () => {
    mockApi({
      "GET /api/skills": skills,
      "GET /api/outputs": { root: "C:/home/outputs", folders: [], files: [] },
      "GET /api/skills/runs": [],
    });
    renderAt(<WorkOverviewPage />, { path: "/work", route: "/work" });
    const parts = await screen.findByRole("list", { name: "The parts of Work" });
    expect(within(parts).getAllByRole("heading").map((h) => h.textContent)).toEqual([
      "Compose",
      "Workspace",
      "Skills",
      "Agents",
      "Workflows",
      "Library",
      "Outputs",
    ]);
    expect(within(parts).getByRole("link", { name: "Skills" })).toHaveAttribute("href", "/work/skills");
    expect(await within(parts).findByText("1 skill")).toBeInTheDocument();
    expect(screen.getByText(/waiting in/)).toHaveTextContent("/one-pager");
  });
});

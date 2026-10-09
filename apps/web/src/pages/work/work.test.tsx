// Work: the frame and its tabs, the overview of its parts, and each part as it lands.

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { LibraryItemPage, LibraryPage } from "./Library";
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
    mockApi({ "GET /api/brain/status": { available: true }, "GET /api/skills": skills, "GET /api/library": [] });
    renderAt(<WorkLayout />, { path: "/work", route: "/work" });
    const tabs = await screen.findByRole("navigation", { name: "Work sections" });
    expect(within(tabs).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual(["/work", "/work/skills", "/work/library", "/work/outputs"]);
    expect(within(tabs).getByRole("link", { name: /Skills/ })).toHaveTextContent("1");
    expect(screen.getByRole("heading", { level: 1, name: "Work" })).toBeInTheDocument();
  });

  it("overviews its parts, each with the question it answers, and what waits for you", async () => {
    mockApi({
      "GET /api/skills": skills,
      "GET /api/outputs": { root: "C:/home/outputs", folders: [], files: [] },
      "GET /api/skills/runs": [],
      "GET /api/library": [],
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

const guide = {
  path: "references/release-notes.md",
  title: "How we write release notes",
  kind: "guide",
  summary: "Lead with what changed for the customer.",
  entry_id: "card-release-notes",
  source_url: null,
  source_repo: null,
  source_paths: [],
  fetched_at: null,
  refresh: "never",
  updated: "2026-10-09T10:00:00Z",
  dated: "2026-10-09",
  version: 1,
  size: 120,
  original: null,
  project: null,
  project_title: null,
  used_by: { skills: ["weekly-posts"] },
};
const influence = {
  ...guide,
  path: "references/acme-site.md",
  title: "acme/site",
  kind: "influence",
  summary: "Our marketing site.",
  entry_id: "card-acme",
  source_repo: "https://github.com/acme/site",
  source_paths: ["src/Button.tsx"],
  fetched_at: "2026-10-01",
  refresh: "monthly",
  used_by: { skills: [] },
};

describe("the Library", () => {
  it("lists what good looks like by kind, with where each came from and what uses it", async () => {
    mockApi({ "GET /api/library": [guide, influence] });
    const user = userEvent.setup();
    renderAt(<LibraryPage />, { path: "/work/library", route: "/work/library" });
    const list = await screen.findByRole("list", { name: "Library" });
    expect(within(list).getByRole("link", { name: "How we write release notes" })).toHaveAttribute(
      "href",
      "/work/library/view?path=references%2Frelease-notes.md",
    );
    expect(within(list).getByText(/used by 1 skill or agent/)).toBeInTheDocument();
    expect(within(list).getByText(/from acme\/site/)).toHaveTextContent("every month");
    await user.click(screen.getByRole("button", { name: /Influences/ }));
    expect(within(screen.getByRole("list", { name: "Library" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("fetches a page and keeps it, as the kind chosen", async () => {
    const calls = mockApi({
      "GET /api/library": [],
      "POST /api/library/url": { status: "applied", message: "Filed.", path: "references/sourdough.md" },
    });
    const user = userEvent.setup();
    renderAt(<LibraryPage />, { path: "/work/library", route: "/work/library" });
    await user.click(await screen.findByRole("button", { name: "Add to the Library" }));
    await user.type(screen.getByLabelText("The page's address"), "https://example.org/sourdough");
    await user.selectOptions(screen.getByLabelText("Fetch it again"), "weekly");
    await user.click(screen.getByRole("button", { name: "Fetch and keep" }));
    expect(await screen.findByRole("link", { name: "Open it" })).toHaveAttribute("href", "/work/library/view?path=references%2Fsourdough.md");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ url: "https://example.org/sourdough", kind: "reference", refresh: "weekly" });
  });

  it("shows an item whole, and changes its kind and fetches it again", async () => {
    const calls = mockApi({
      "GET /api/library/item": { ...influence, text: "# acme/site\n\nPlain words, short pages.", checked_at: "2026-10-08T09:00:00Z" },
      "PUT /api/library/item": { ...influence, kind: "guide" },
      "POST /api/library/refresh": { status: "unchanged", message: "", path: influence.path, proposal_id: null },
    });
    const user = userEvent.setup();
    renderAt(<LibraryItemPage />, { path: "/work/library/view", route: "/work/library/view?path=references%2Facme-site.md" });
    expect(await screen.findByText("Plain words, short pages.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://github.com/acme/site" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Kind"), "guide");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ path: "references/acme-site.md", kind: "guide" });
    await user.click(screen.getByRole("button", { name: "Fetch it again now" }));
    expect(await screen.findByText("Nothing changed since it was fetched.")).toBeInTheDocument();
  });
});

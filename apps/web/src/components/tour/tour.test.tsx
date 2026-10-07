// The guided tour: steps across pages with Back, Next and the arrow keys; a step says what is
// missing when its part is not on the page; closing midway can be resumed; finishing is kept.
// The help menu starts it whole or from a chapter, and shows how far the setup has come.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mockApi } from "../../test/render";
import { HelpMenu } from "./HelpMenu";
import type { TourStep } from "./steps";
import { placeCard, TourProvider, useTour } from "./Tour";

const steps: TourStep[] = [
  { id: "a", chapter: "basics", route: "/", title: "First stop", body: <p>Hello there.</p> },
  { id: "b", chapter: "basics", route: "/", target: "box", title: "The box", body: <p>A box.</p> },
  { id: "c", chapter: "home", route: "/other", target: "other-box", title: "Another page", body: <p>Over here.</p> },
  {
    id: "d",
    chapter: "projects",
    route: ({ projectId }) => (projectId ? `/projects/${projectId}` : null),
    fallback: "/",
    target: "project-part",
    missing: "Start a project first.",
    title: "A project",
    body: <p>Projects.</p>,
  },
];

/** A part the tour can highlight; the test DOM has no layout, so it says its own size. */
function Part({ name }: { name: string }) {
  return (
    <div
      data-tour={name}
      ref={(element) => {
        if (element) element.getBoundingClientRect = () => ({ x: 40, y: 80, top: 80, left: 40, width: 200, height: 60, right: 240, bottom: 140, toJSON: () => ({}) });
      }}
    >
      {name}
    </div>
  );
}

function Starter() {
  const tour = useTour();
  return (
    <div>
      <button type="button" onClick={() => tour.start()}>
        start
      </button>
      <button type="button" onClick={() => tour.start("projects")}>
        projects chapter
      </button>
      <button type="button" onClick={tour.resume}>
        resume
      </button>
      <span data-testid="saved">{tour.saved === null ? "none" : tour.saved}</span>
    </div>
  );
}

function renderTour(extra?: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <TourProvider steps={steps} patience={300}>
          <Starter />
          {extra}
          <Routes>
            <Route path="/" element={<Part name="box" />} />
            <Route path="/other" element={<Part name="other-box" />} />
          </Routes>
        </TourProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.scrollBy = vi.fn();
});

describe("the guided tour", () => {
  it("walks through steps across pages with Back, Next and the arrow keys", async () => {
    mockApi({ "GET /api/brain/projects": [], "GET /api/notes": [] });
    const user = userEvent.setup();
    const { container } = renderTour();
    await user.click(screen.getByRole("button", { name: "start" }));
    const first = await screen.findByRole("dialog", { name: "First stop" });
    expect(within(first).getByText("1 of 4")).toBeInTheDocument();
    expect(document.querySelector(".tour-spot")).toBeNull(); // a step without a part sits in the middle
    await user.click(within(first).getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("dialog", { name: "The box" })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector(".tour-spot")).not.toBeNull());
    await user.keyboard("{ArrowRight}");
    expect(await screen.findByRole("dialog", { name: "Another page" })).toBeInTheDocument();
    expect(container.querySelector('[data-tour="other-box"]')).not.toBeNull(); // it went to the page
    await user.keyboard("{ArrowLeft}");
    expect(await screen.findByRole("dialog", { name: "The box" })).toBeInTheDocument();
  });

  it("says what is missing when there is nothing to show yet", async () => {
    mockApi({ "GET /api/brain/projects": [], "GET /api/notes": [] });
    const user = userEvent.setup();
    renderTour();
    await user.click(screen.getByRole("button", { name: "projects chapter" }));
    const card = await screen.findByRole("dialog", { name: "A project" });
    expect(within(card).getByText("Start a project first.")).toBeInTheDocument();
    expect(document.querySelector(".tour-spot")).toBeNull();
  });

  it("can be resumed where it was closed, and a finished tour is kept", async () => {
    const calls = mockApi({ "GET /api/brain/projects": [], "GET /api/notes": [], "POST /api/onboarding": {} });
    const user = userEvent.setup();
    renderTour();
    await user.click(screen.getByRole("button", { name: "start" }));
    await user.click(within(await screen.findByRole("dialog", { name: "First stop" })).getByRole("button", { name: "Next" }));
    await screen.findByRole("dialog", { name: "The box" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("saved")).toHaveTextContent("1");
    await user.click(screen.getByRole("button", { name: "resume" }));
    await screen.findByRole("dialog", { name: "The box" });
    await user.keyboard("{ArrowRight}");
    await screen.findByRole("dialog", { name: "Another page" });
    await user.keyboard("{ArrowRight}");
    const last = await screen.findByRole("dialog", { name: "A project" });
    await act(async () => {
      await user.click(within(last).getByRole("button", { name: "Finish" }));
    });
    await waitFor(() => expect(calls.find((c) => c.path === "/api/onboarding")?.body).toEqual({ tour_seen: true }));
    expect(screen.getByTestId("saved")).toHaveTextContent("none");
  });

  it("is started from the help menu, beside the first run and the tips", async () => {
    mockApi({
      "GET /api/brain/projects": [],
      "GET /api/notes": [],
      "GET /api/onboarding": { steps: [], done: 6, total: 7, completed_at: null, dismissed_at: null, tour_seen_at: null },
    });
    const user = userEvent.setup();
    renderTour(<HelpMenu />);
    await user.click(screen.getByRole("button", { name: "Help and guided tour" }));
    const menu = screen.getByRole("menu", { name: "Help" });
    expect(within(menu).getByRole("menuitem", { name: /Take the short tour/ })).toBeInTheDocument();
    expect(await within(menu).findByRole("menuitem", { name: /The first run not finished yet/ })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Show the tips again" })).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: /Take the short tour/ }));
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

describe("the tour's own steps", () => {
  // Every part a step points at must be on a page, or the step can only say it is missing.
  const sources = import.meta.glob(["../../**/*.tsx", "!../../**/*.test.tsx"], { query: "?raw", import: "default", eager: true });
  const marked = new Set<string>();
  for (const text of Object.values(sources) as string[]) {
    for (const found of text.matchAll(/(?:data-tour|tour)=(?:"([a-z-]+)"|\{[^}]*"([a-z-]+)")/g)) marked.add(found[1] ?? found[2] ?? "");
  }

  it("point only at parts the app marks", async () => {
    const { STEPS, CHAPTERS } = await import("./steps");
    const missing = STEPS.filter((s) => s.target && !marked.has(s.target)).map((s) => `${s.id}: ${s.target}`);
    expect(missing).toEqual([]);
    const chapters = new Set<string>(CHAPTERS.map((c) => c.id));
    expect(STEPS.filter((s) => !chapters.has(s.chapter)).map((s) => s.id)).toEqual([]);
    expect(CHAPTERS.every((c) => STEPS.some((s) => s.chapter === c.id))).toBe(true);
  });
});

describe("where the card goes", () => {
  const view = { width: 1000, height: 800 };
  const card = { width: 380, height: 200 };
  it("sits below, above or beside what it points at, and in the middle without it", () => {
    expect(placeCard({ top: 100, left: 50, width: 200, height: 40 }, card, view)).toMatchObject({ side: "bottom", top: 152 });
    expect(placeCard({ top: 600, left: 50, width: 200, height: 40 }, card, view)).toMatchObject({ side: "top", top: 388 });
    expect(placeCard({ top: 0, left: 10, width: 150, height: 800 }, card, view)).toMatchObject({ side: "right", left: 172 });
    expect(placeCard(null, card, view)).toMatchObject({ side: "center", top: 300, left: 310 });
    expect(placeCard({ top: 100, left: 900, width: 80, height: 40 }, card, view).left).toBe(608); // kept on screen
  });
});

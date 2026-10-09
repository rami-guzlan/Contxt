// The short tour, from the Help menu: one step per place a person meets first. The first run
// teaches by doing and each page has a one-line tip on the first visit, so this is the
// reminder, not the lesson. A step highlights the element marked data-tour="<target>" on its
// route; a step without a target, or whose target is not on the page, shows in the middle.

import type { ReactNode } from "react";

export interface TourPlace {
  /** A project, a capture and a skill, for the steps shown on one. */
  projectId?: string;
  noteId?: string;
  skillName?: string;
}

export interface TourStep {
  id: string;
  chapter: string;
  title: string;
  body: ReactNode;
  /** Where the step is shown; a function picks a project, capture or skill page when there is one. */
  route?: string | ((place: TourPlace) => string | null);
  /** Where to go when `route` finds nothing to show (no project yet, say). */
  fallback?: string;
  /** Said instead of the highlight when the target is not there. */
  missing?: string;
  target?: string;
}

export const CHAPTERS = [{ id: "basics", label: "The places" }] as const;

export const STEPS: TourStep[] = [
  {
    id: "home",
    chapter: "basics",
    route: "/",
    title: "Home: how you're doing",
    body: (
      <p>
        One line says whether anything needs you. When it says catch up, it is usually a few minutes: a plan, never a pile, and every change
        can be undone.
      </p>
    ),
  },
  {
    id: "capture",
    chapter: "basics",
    route: "/capture",
    target: "capture-list",
    missing: "What you bring in lands here: talk with Space, record a meeting, drop a file.",
    title: "Capture: what you bring in",
    body: (
      <p>
        Talk, recordings, transcripts, files and notes wait here, private to you. The Brain summarizes each one and pulls out what serves your
        goals and projects; you keep what you want.
      </p>
    ),
  },
  {
    id: "brain",
    chapter: "basics",
    route: "/brain",
    target: "brain-tabs",
    title: "Brain: what your AI knows",
    body: <p>What every AI you connect can know, in the words it receives. Each request gets only the few notes it needs.</p>,
  },
  {
    id: "work",
    chapter: "basics",
    route: "/work",
    target: "work-tabs",
    title: "Work: putting your Brain to use",
    body: (
      <p>
        Ask with your skills and references at hand, write and plan by project, and hand work to agents and workflows. Skills, the procedures
        your AI follows to make things, live here too.
      </p>
    ),
  },
  {
    id: "activity",
    chapter: "basics",
    route: "/activity",
    title: "Activity: what each AI got",
    body: <p>Every request from every AI you connect: what it was handed, why, and what it saved. Changes and their undo points are here too.</p>,
  },
];

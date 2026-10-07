// The guided tour: a spotlight on one part of a page at a time, a card that says what it is for
// and how it fits the rest, and Back and Next. It moves between pages as it goes. It starts
// from the help button (top right), from one of its chapters, or at the end of the setup.
// Close it midway and the help button offers to resume where you were.

import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router";

import { get } from "../../api/client";
import { keys, useMarkOnboarding } from "../../api/hooks";
import type { BrainProject, Note, SkillCards } from "../../api/types";
import { CHAPTERS, STEPS, type TourPlace, type TourStep } from "./steps";

interface TourApi {
  /** Start at the beginning, or at a chapter's (or step's) first step. */
  start: (from?: string) => void;
  /** Go back to where the tour was closed. */
  resume: () => void;
  /** The step it was closed at, if it was closed midway. */
  saved: number | null;
  total: number;
  active: boolean;
}

const TourContext = createContext<TourApi>({ start: () => undefined, resume: () => undefined, saved: null, total: 0, active: false });
export const useTour = () => useContext(TourContext);

const SAVED = "workspace.tour.step"; // this browser's place in the tour: a convenience only

function readSaved(): number | null {
  try {
    const value = window.localStorage.getItem(SAVED);
    return value === null ? null : Number(value);
  } catch {
    return null;
  }
}

function writeSaved(index: number | null) {
  try {
    if (index === null) window.localStorage.removeItem(SAVED);
    else window.localStorage.setItem(SAVED, String(index));
  } catch {
    // private windows may refuse; the tour still works, it just will not resume
  }
}

export function TourProvider({
  children,
  steps = STEPS,
  patience = 4000,
}: {
  children: ReactNode;
  steps?: TourStep[];
  /** How long a step looks for what it highlights before saying it is not there, in ms. */
  patience?: number;
}) {
  const client = useQueryClient();
  const mark = useMarkOnboarding();
  const [index, setIndex] = useState<number | null>(null);
  const [saved, setSaved] = useState<number | null>(() => readSaved());
  const [place, setPlace] = useState<TourPlace>({});

  const open = useCallback(
    async (at: number) => {
      // a project, a capture (a recording, for the story the tour tells) and a skill to show
      // their pages, when there are any
      const [projects, notes, skills] = await Promise.all([
        client
          .fetchQuery({ queryKey: [...keys.brain, "projects"], queryFn: () => get<BrainProject[]>("/api/brain/projects") })
          .catch(() => [] as BrainProject[]),
        get<Note[]>("/api/notes").catch(() => [] as Note[]),
        get<SkillCards>("/api/skills").catch(() => ({ skills: [], waiting: [] }) as SkillCards),
      ]);
      const spoken = notes.find((n) => n.capture === "recording" || n.capture === "transcript" || n.capture === "talk");
      const runnable = skills.skills.filter((s) => s.use === "run");
      setPlace({
        projectId: (projects.find((p) => p.active) ?? projects[0])?.id,
        noteId: (spoken ?? notes[0])?.id,
        skillName: (runnable.find((s) => s.last_run) ?? runnable[0])?.name,
      });
      setIndex(Math.max(0, Math.min(at, steps.length - 1)));
    },
    [client, steps.length],
  );

  const start = useCallback(
    (from?: string) => {
      const at = from ? steps.findIndex((s) => s.chapter === from || s.id === from) : 0;
      void open(at < 0 ? 0 : at);
    },
    [open, steps],
  );

  const close = useCallback(
    (finished: boolean) => {
      if (finished) {
        writeSaved(null);
        setSaved(null);
        mark.mutate({ tour_seen: true });
      } else if (index !== null) {
        writeSaved(index);
        setSaved(index);
      }
      setIndex(null);
    },
    [index, mark],
  );

  const api = useMemo<TourApi>(
    () => ({ start, resume: () => void open(saved ?? 0), saved, total: steps.length, active: index !== null }),
    [start, open, saved, steps.length, index],
  );
  const step = index !== null ? steps[index] : undefined;
  return (
    <TourContext.Provider value={api}>
      {children}
      {step && index !== null ? (
        <TourCard
          key={step.id}
          step={step}
          index={index}
          total={steps.length}
          place={place}
          patience={patience}
          onBack={() => setIndex(Math.max(0, index - 1))}
          onNext={() => (index + 1 >= steps.length ? close(true) : setIndex(index + 1))}
          onClose={() => close(false)}
        />
      ) : null}
    </TourContext.Provider>
  );
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const GAP = 12;
const PAD = 8;

/** Where the card goes: below the highlight, else above, else beside it, kept on screen. */
export function placeCard(spot: Box | null, card: { width: number; height: number }, view: { width: number; height: number }) {
  const clampX = (x: number) => Math.max(GAP, Math.min(x, view.width - card.width - GAP));
  const clampY = (y: number) => Math.max(GAP, Math.min(y, view.height - card.height - GAP));
  if (!spot) return { top: clampY((view.height - card.height) / 2), left: clampX((view.width - card.width) / 2), side: "center" };
  const below = spot.top + spot.height + GAP;
  if (below + card.height <= view.height - GAP) return { top: below, left: clampX(spot.left), side: "bottom" };
  const above = spot.top - GAP - card.height;
  if (above >= GAP) return { top: above, left: clampX(spot.left), side: "top" };
  const right = spot.left + spot.width + GAP;
  if (right + card.width <= view.width - GAP) return { top: clampY(spot.top), left: right, side: "right" };
  const left = spot.left - GAP - card.width;
  if (left >= GAP) return { top: clampY(spot.top), left, side: "left" };
  return { top: clampY(view.height - card.height - GAP), left: clampX((view.width - card.width) / 2), side: "over" };
}

function TourCard({
  step,
  index,
  total,
  place,
  patience,
  onBack,
  onNext,
  onClose,
}: {
  step: TourStep;
  index: number;
  total: number;
  place: TourPlace;
  patience: number;
  onBack: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const titleId = useId();
  const bodyId = useId();
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const [spot, setSpot] = useState<Box | null>(null);
  const [looked, setLooked] = useState(false);
  const [size, setSize] = useState({ width: 380, height: 260 });
  const [view, setView] = useState({ width: window.innerWidth, height: window.innerHeight });

  const resolved = typeof step.route === "function" ? step.route(place) : step.route;
  const where = resolved ?? step.fallback;
  const unplaced = typeof step.route === "function" && !resolved; // nothing made yet to show
  const chapter = CHAPTERS.find((c) => c.id === step.chapter)?.label ?? "";

  // go to the step's page, once per step (the page the person is on is read, not watched)
  const here = useRef(location.pathname + location.search);
  here.current = location.pathname + location.search;
  useEffect(() => {
    if (where && here.current !== where) navigate(where);
  }, [where, navigate]);

  // find what it highlights, waiting for the page (and its lazy parts) to load
  useEffect(() => {
    setSpot(null);
    setLooked(false);
    if (!step.target || unplaced) {
      setLooked(true);
      return;
    }
    let stopped = false;
    let tries = 0;
    const look = () => {
      if (stopped) return;
      const element = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
      const box = element?.getBoundingClientRect();
      if (element && box && box.width > 0 && box.height > 0) {
        bringIntoView(box);
        window.requestAnimationFrame(() => {
          if (stopped) return;
          setSpot(padded(element.getBoundingClientRect()));
          setLooked(true);
        });
        return;
      }
      if (++tries * 100 > patience) setLooked(true); // not on this page: say so instead
      else window.setTimeout(look, 100);
    };
    look();
    return () => {
      stopped = true;
    };
  }, [step.target, unplaced, location.pathname, location.search, patience]);

  // follow the highlighted part as the page scrolls, resizes or settles
  useEffect(() => {
    const measure = () => {
      setView({ width: window.innerWidth, height: window.innerHeight });
      const element = step.target ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`) : null;
      if (element && looked && !unplaced) setSpot(padded(element.getBoundingClientRect()));
    };
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    const timer = window.setInterval(measure, 500);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      window.clearInterval(timer);
    };
  }, [step.target, looked, unplaced]);

  // the card's own size, to place it
  useLayoutEffect(() => {
    const box = card.current?.getBoundingClientRect();
    if (box && (Math.abs(box.width - size.width) > 1 || Math.abs(box.height - size.height) > 1)) {
      setSize({ width: box.width, height: box.height });
    }
  });

  // keys: next, back, close
  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        onNext();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        onBack();
      }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [onBack, onNext, onClose]);

  useEffect(() => {
    if (looked) next.current?.focus({ preventScroll: true });
  }, [looked]);

  const missing = looked && !!step.target && !spot;
  const at = placeCard(spot, size, view);
  return createPortal(
    <div className="tour" data-testid="tour">
      <div
        className={spot ? "tour-shield" : "tour-shield dim"}
        aria-hidden="true"
        onWheel={(event) => window.scrollBy({ top: event.deltaY, left: event.deltaX })}
      />
      {spot ? <div className="tour-spot" aria-hidden="true" style={spot} /> : null}
      <div
        ref={card}
        className={`tour-card side-${at.side}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        style={{ top: at.top, left: at.left, visibility: looked ? "visible" : "hidden" }}
      >
        <p className="tour-chapter">
          {chapter}
          <span>
            {index + 1} of {total}
          </span>
        </p>
        <h2 id={titleId}>{step.title}</h2>
        <div id={bodyId} className="tour-body">
          {missing && step.missing ? <p className="tour-missing">{step.missing}</p> : null}
          {step.body}
        </div>
        <div className="tour-progress" aria-hidden="true">
          <span style={{ width: `${((index + 1) / total) * 100}%` }} />
        </div>
        <div className="tour-actions">
          <button type="button" className="link" onClick={onClose}>
            Close the tour
          </button>
          <span className="tour-nav">
            <button type="button" onClick={onBack} disabled={index === 0}>
              Back
            </button>
            <button ref={next} type="button" className="primary" onClick={onNext}>
              {index + 1 === total ? "Finish" : "Next"}
            </button>
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}

const TOP = 72; // the sticky top bar, which would hide what scrolls under it

/** Scroll so the part is in view below the top bar: centered when it fits, its top shown when
 * it is taller than the window. Fixed parts (the sidebar) stay where they are. */
function bringIntoView(box: DOMRect) {
  const room = window.innerHeight - TOP - GAP;
  if (box.top >= TOP && box.bottom <= window.innerHeight - GAP) return;
  const shift = box.height <= room ? box.top - TOP - (room - box.height) / 2 : box.top - TOP - GAP;
  window.scrollBy({ top: shift });
}

function padded(box: DOMRect): Box {
  return { top: box.top - PAD, left: box.left - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2 };
}

// The help button at the top right: the short tour of the places, back to where it was closed,
// the first run again, and the first-visit tips again.

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import { useOnboarding } from "../../api/hooks";
import { resetTips } from "../Tips";
import { useTour } from "./Tour";

export function HelpMenu() {
  const tour = useTour();
  const navigate = useNavigate();
  const { data: setup } = useOnboarding();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    box.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  function choose(action: () => void) {
    setOpen(false);
    action();
  }

  // up and down move through the menu; Escape closes it and returns to the button
  function keys(event: KeyboardEvent<HTMLDivElement>) {
    const items = [...(box.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = (at + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }
  }

  const unfinished = setup && !setup.completed_at;
  return (
    <div className="help-menu" ref={box} data-tour="help" onKeyDown={keys}>
      <button
        ref={button}
        type="button"
        className="help-button"
        aria-label="Help and guided tour"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Help and guided tour"
        onClick={() => setOpen(!open)}
      >
        ?{unfinished ? <span className="help-dot" aria-hidden="true" /> : null}
      </button>
      {open ? (
        <div className="help-popover" role="menu" aria-label="Help">
          <button type="button" role="menuitem" className="help-item lead" onClick={() => choose(() => tour.start())}>
            Take the short tour <span className="muted small">The places, in about a minute</span>
          </button>
          {tour.saved !== null && tour.saved > 0 ? (
            <button type="button" role="menuitem" className="help-item" onClick={() => choose(tour.resume)}>
              Resume the tour <span className="muted small">at step {tour.saved + 1} of {tour.total}</span>
            </button>
          ) : null}
          <hr />
          <button type="button" role="menuitem" className="help-item" onClick={() => choose(() => navigate("/welcome"))}>
            The first run{" "}
            {setup ? <span className="muted small">{setup.completed_at ? "finished: go through it again" : "not finished yet"}</span> : null}
          </button>
          <button type="button" role="menuitem" className="help-item" onClick={() => choose(resetTips)}>
            Show the tips again
          </button>
        </div>
      ) : null}
    </div>
  );
}

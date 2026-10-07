// "AI work" at the top of every page: what your AI is doing on this computer right now, live,
// and what it finished lately, each with the page its work belongs to (the skill it ran, the
// capture it summarized, Review where what it proposed waits).

import { Bot } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { useRecentRuns } from "../api/hooks";
import type { LocalRun } from "../api/types";
import { when } from "../lib/format";
import { RunConsole } from "./RunNow";
import { Pill } from "./ui";

const ACTIVE = ["starting", "running"];
const SHOWN = 8;

export function AiWork() {
  const { data: runs } = useRecentRuns();
  const [open, setOpen] = useState(false);
  const [watching, setWatching] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const active = (runs ?? []).filter((r) => ACTIVE.includes(r.status));
  if (!runs?.length) return null; // nothing has run here yet: nothing to show
  return (
    <div
      className="ai-work"
      data-tour="ai-work"
      ref={box}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          button.current?.focus();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className={active.length ? "ai-work-button busy" : "ai-work-button"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen(!open)}
      >
        <Bot className="button-icon" aria-hidden="true" />
        {active.length ? `AI working (${active.length})` : "AI work"}
      </button>
      {open ? (
        <div className="ai-work-popover" role="dialog" aria-label="AI work">
          <p className="help-heading">{active.length ? "Working now" : "Lately"}</p>
          <ol className="ai-work-list">
            {runs.slice(0, SHOWN).map((run) => (
              <li key={run.id} className="ai-work-item">
                <Item run={run} watching={watching === run.id} onWatch={() => setWatching(watching === run.id ? null : run.id)} />
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}

function Item({ run, watching, onWatch }: { run: LocalRun; watching: boolean; onWatch: () => void }) {
  const going = ACTIVE.includes(run.status);
  return (
    <>
      <div className="ai-work-row">
        <Pill status={run.status} />
        <span className="ai-work-title">{run.task_title}</span>
      </div>
      <div className="ai-work-row muted small">
        <span>{going ? `started ${when(run.started_at)}` : `finished ${when(run.finished_at ?? run.started_at)}`}</span>
        {run.made?.length ? <span>· made {run.made.length} file{run.made.length === 1 ? "" : "s"}</span> : null}
        {run.link ? (
          <Link to={run.link} className="small">
            Open
          </Link>
        ) : null}
        <button type="button" className="link small" aria-expanded={watching} onClick={onWatch}>
          {watching ? "Hide" : going ? "Watch" : "Steps"}
        </button>
      </div>
      {watching ? <RunConsole runId={run.id} /> : null}
    </>
  );
}

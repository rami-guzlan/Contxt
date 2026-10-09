// Home's flashcards: what to keep an eye on, one card at a time. Stale context, repeats, drift,
// gaps, quiet projects and the knowledge agent's questions come from its suggestions (made by
// code as the Brain changes); its last actions say what it did; a last card says what is coming
// (agents and workflows of your own). Each card has the one thing to do about it.

import { ArrowLeft, ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAgent, useAgentSuggestions, useDismissAgentSuggestion } from "../api/hooks";
import type { AgentRun, AgentSuggestion } from "../api/types";
import { when } from "../lib/format";
import { useAgentPanel } from "./agent/AgentContext";

const LABELS: Record<string, string> = {
  stale: "Stale context",
  repeats: "Repeats",
  drift: "Drift",
  clashes: "Disagreements",
  "went-in": "Went in on its own",
  gaps: "Gaps",
  projects: "Projects",
  unused: "Unused notes",
  skills: "Skills",
  questions: "The agent asks",
};

interface Card {
  key: string;
  label: string;
  count?: number;
  title: string;
  detail: string;
  tone: "attention" | "calm" | "info" | "soon";
  run?: string;
  to?: string;
  doLabel?: string;
  dismiss?: string;
}

function fromSuggestion(s: AgentSuggestion): Card {
  return {
    key: s.key,
    label: LABELS[s.kind] ?? "To look at",
    count: s.count,
    title: s.title,
    detail: s.detail,
    tone: "attention",
    run: s.action ?? undefined,
    to: s.action ? undefined : (s.link ?? undefined),
    doLabel: s.action ? "Let the agent check" : "Open",
    dismiss: s.key,
  };
}

function fromRun(run: AgentRun): Card {
  return {
    key: `run:${run.id}`,
    label: "The agent did",
    title: `${run.label}, ${when(run.at)}`,
    detail: run.summary,
    tone: "info",
    to: run.proposed ? "/catch-up" : "/brain/agent",
    doLabel: run.proposed ? "See its suggestions" : "See what it did",
  };
}

export function Flashcards() {
  const { data: suggestions } = useAgentSuggestions();
  const { data: agent } = useAgent();
  const panel = useAgentPanel();
  const dismiss = useDismissAgentSuggestion();
  const [at, setAt] = useState(0);
  const [all, setAll] = useState(false);
  const cards: Card[] = (suggestions ?? []).map(fromSuggestion);
  if (!cards.length) {
    cards.push({
      key: "calm",
      label: "All fresh",
      title: "Nothing needs a look",
      detail: "No stale notes, repeats, gaps or quiet projects right now. The agent keeps watching as your Brain changes.",
      tone: "calm",
    });
  }
  for (const run of (agent?.runs ?? []).slice(0, 2)) cards.push(fromRun(run));
  cards.push({
    key: "soon",
    label: "Coming soon",
    title: "Agents and workflows of your own",
    detail: "Define agents and the workflows they run on a schedule; what each one does will show here, one card at a time.",
    tone: "soon",
  });
  const index = Math.min(at, cards.length - 1);
  const shown = all ? cards : cards.slice(index, index + 1);
  const go = (step: number) => setAt((index + step + cards.length) % cards.length);
  return (
    <section
      className="flashcards"
      aria-label="Keep an eye on"
      tabIndex={0}
      onKeyDown={(event) => {
        if (all) return;
        if (event.key === "ArrowRight") go(1);
        if (event.key === "ArrowLeft") go(-1);
      }}
    >
      <div className="flashcards-head">
        <h2>Keep an eye on</h2>
        <button type="button" className="link small" onClick={() => setAll(!all)}>
          {all ? "One at a time" : `See all ${cards.length}`}
        </button>
      </div>
      <div className={all ? "flashcard-grid" : "flashcard-one"}>
        {shown.map((card) => (
          <article key={card.key} className={`flashcard ${card.tone}`} aria-label={card.title}>
            <p className="flashcard-label">{card.label}</p>
            {card.count !== undefined ? <p className="flashcard-count">{card.count}</p> : null}
            <p className="flashcard-title">{card.title}</p>
            <p className="muted small">{card.detail}</p>
            <div className="row small">
              {card.run ? (
                <button type="button" className="primary" onClick={() => panel.openPanel({ action: card.run })}>
                  {card.doLabel}
                </button>
              ) : card.to ? (
                <Link className="button primary" to={card.to}>
                  {card.doLabel}
                </Link>
              ) : null}
              {card.dismiss ? (
                <button type="button" className="link" disabled={dismiss.isPending} onClick={() => dismiss.mutate({ key: card.dismiss ?? "" })}>
                  Got it
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
      {!all && cards.length > 1 ? (
        <div className="flashcard-nav">
          <button type="button" className="link" aria-label="Previous card" onClick={() => go(-1)}>
            <ArrowLeft className="button-icon" aria-hidden="true" />
          </button>
          <span className="muted small" aria-live="polite">
            {index + 1} of {cards.length}
          </span>
          <button type="button" className="link" aria-label="Next card" onClick={() => go(1)}>
            <ArrowRight className="button-icon" aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </section>
  );
}

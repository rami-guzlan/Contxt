// The knowledge agent at a glance, above the Brain's map: ask it something, or run one of its
// actions, and the side panel opens with the answer. More on the Knowledge agent tab.

import { Bot } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAgent, useAgentSuggestions } from "../../api/hooks";
import { useAgentPanel } from "./AgentContext";

export function AgentStrip() {
  const panel = useAgentPanel();
  const { data: agent } = useAgent();
  const { data: suggestions } = useAgentSuggestions();
  const [text, setText] = useState("");
  const waiting = agent?.questions.length ?? 0;
  const hinted = new Set((suggestions ?? []).map((s) => s.action).filter(Boolean));
  return (
    <section className="agent-strip" aria-label="Knowledge agent">
      <div className="agent-strip-head">
        <h2>
          <Bot className="title-icon" aria-hidden="true" /> Knowledge agent
        </h2>
        <Link className="small" to="/brain/agent">
          {waiting ? `${waiting} question${waiting === 1 ? "" : "s"} for you` : "More"}
        </Link>
      </div>
      <form
        className="agent-strip-ask"
        onSubmit={(event) => {
          event.preventDefault();
          if (!text.trim()) return;
          panel.openPanel({ message: text.trim() });
          setText("");
        }}
      >
        <input
          aria-label="Ask the knowledge agent"
          placeholder="Ask about your Brain: what is out of date, what repeats, what is missing for a goal…"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" className="primary" disabled={!text.trim()}>
          Ask
        </button>
      </form>
      <div className="chips" role="group" aria-label="Actions">
        {(agent?.actions ?? []).map((a) => (
          <button
            key={a.id}
            type="button"
            className={hinted.has(a.id) ? "chip-button active" : "chip-button"}
            title={a.blurb}
            onClick={() => panel.openPanel({ action: a.id })}
          >
            {a.label}
          </button>
        ))}
      </div>
    </section>
  );
}

// The knowledge agent everywhere: a slide-over panel on the right (a quarter of the screen) with
// its conversation and its actions, and at the bottom right its suggestions as the Brain
// changes, with the button that opens the panel. Every change it suggests waits for the owner.

import { Bot, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import {
  useAgent,
  useAgentChat,
  useAgentJob,
  useAgentSettings,
  useAgentSuggestions,
  useDismissAgentSuggestion,
  useKeepAgentNote,
  useRunAgentAction,
} from "../../api/hooks";
import type { AgentAction, AgentJob, AgentModel } from "../../api/types";
import { Markdown } from "../Markdown";
import { ErrorNote } from "../ui";
import { useAgentPanel } from "./AgentContext";
import { AgentQuestionCard } from "./AgentQuestions";

interface Turn {
  id: string;
  role: "user" | "agent" | "action";
  text?: string;
  job?: string;
  action?: string;
  /** The agent's answer, kept once it came: the actions it offered and the notes it suggested. */
  offered?: { run: string[]; notes: { title: string; text: string; kind: string }[] };
}

const THREAD = "contxt.agent.thread";
const KEEP_TURNS = 60;

function loadThread(): Turn[] {
  try {
    const raw = window.sessionStorage.getItem(THREAD);
    const found = raw ? (JSON.parse(raw) as Turn[]) : [];
    return Array.isArray(found) ? found.slice(-KEEP_TURNS) : [];
  } catch {
    return [];
  }
}

function saveThread(turns: Turn[]): void {
  try {
    window.sessionStorage.setItem(THREAD, JSON.stringify(turns.slice(-KEEP_TURNS)));
  } catch {
    // a private window keeps the conversation only while the page is open
  }
}

let counter = 0;
const turnId = () => `t${Date.now()}-${(counter += 1)}`;

/** Choose the model the agent works through, from the ones that can answer here. */
export function ModelPicker({ models, value, compact = false }: { models: AgentModel[]; value: string; compact?: boolean }) {
  const settings = useAgentSettings();
  const usable = models.filter((m) => m.available || m.id === value);
  return (
    <label className={compact ? "inline-select model-pick compact" : "inline-select model-pick"}>
      <span className="muted small">Model</span>
      <select value={value} disabled={settings.isPending} onChange={(event) => settings.mutate({ model: event.target.value })}>
        {usable.map((m) => (
          <option key={m.id} value={m.id} disabled={!m.available}>
            {m.label}
          </option>
        ))}
      </select>
      <ErrorNote error={settings.error} />
    </label>
  );
}

export function AgentPanel() {
  const panel = useAgentPanel();
  const { data: agent } = useAgent();
  const chat = useAgentChat();
  const run = useRunAgentAction();
  const [turns, setTurns] = useState<Turn[]>(loadThread);
  const [text, setText] = useState("");
  const thread = useRef<HTMLDivElement>(null);
  const actions = agent?.actions ?? [];

  useEffect(() => saveThread(turns), [turns]);
  useEffect(() => {
    const box = thread.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [turns.length, panel.open]);
  useEffect(() => {
    if (!panel.open) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") panel.closePanel();
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [panel]);

  function history() {
    return turns
      .filter((t) => (t.role === "user" || t.role === "agent") && t.text)
      .slice(-12)
      .map((t) => ({ role: t.role as "user" | "agent", text: t.text ?? "" }));
  }

  function send(message: string) {
    const said = message.trim();
    if (!said) return;
    const past = history();
    const mine: Turn = { id: turnId(), role: "user", text: said };
    setTurns((current) => [...current, mine]);
    setText("");
    chat.mutate(
      { message: said, history: past },
      { onSuccess: (job) => setTurns((current) => [...current, { id: turnId(), role: "agent", job: job.id }]) },
    );
  }

  function start(action: string) {
    run.mutate(
      { action },
      { onSuccess: (job) => setTurns((current) => [...current, { id: turnId(), role: "action", job: job.id, action }]) },
    );
  }

  // A message or an action handed over by whatever opened the panel.
  const { open, takeSeed } = panel;
  useEffect(() => {
    if (!open) return;
    const seed = takeSeed();
    if (seed?.message) send(seed.message);
    else if (seed?.action) start(seed.action);
  }, [open, takeSeed]);

  if (!panel.open) return null;
  return (
    <aside className="agent-panel" aria-label="Knowledge agent">
      <header className="agent-panel-head">
        <h2>
          <Bot className="title-icon" aria-hidden="true" /> Knowledge agent
        </h2>
        <button type="button" className="link" aria-label="Close the knowledge agent" onClick={panel.closePanel}>
          <X className="button-icon" aria-hidden="true" />
        </button>
      </header>
      {agent ? <ModelPicker models={agent.models} value={agent.model} compact /> : null}
      <div className="agent-quick chips" role="group" aria-label="Actions">
        {actions.map((a) => (
          <button key={a.id} type="button" className="chip-button" title={a.blurb} disabled={run.isPending} onClick={() => start(a.id)}>
            {a.label}
          </button>
        ))}
      </div>
      <ErrorNote error={run.error ?? chat.error} />
      <div className="agent-thread" ref={thread}>
        {turns.length ? (
          turns.map((turn) =>
            turn.role === "user" ? (
              <p key={turn.id} className="agent-turn mine">
                {turn.text}
              </p>
            ) : turn.role === "agent" ? (
              <AgentReply
                key={turn.id}
                turn={turn}
                onDone={(text, offered) => setTurns((current) => current.map((t) => (t.id === turn.id ? { ...t, text, offered } : t)))}
                onRun={start}
                actions={actions}
                said={turns[turns.indexOf(turn) - 1]?.text ?? ""}
              />
            ) : (
              <ActionTurn key={turn.id} jobId={turn.job ?? null} action={actions.find((a) => a.id === turn.action)} />
            ),
          )
        ) : (
          <div className="agent-empty muted small">
            <p>Ask about your Brain, or run an action above. It reads a map of everything in your Brain, made by code a moment ago, so it never guesses at what is there.</p>
            <p>Every change it suggests waits for your yes.</p>
          </div>
        )}
      </div>
      <form
        className="agent-composer"
        onSubmit={(event) => {
          event.preventDefault();
          send(text);
        }}
      >
        <textarea
          aria-label="Message the knowledge agent"
          rows={2}
          value={text}
          placeholder="For example: what is out of date?"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send(text);
            }
          }}
        />
        <button type="submit" className="primary" disabled={!text.trim() || chat.isPending}>
          Send
        </button>
      </form>
      {turns.length ? (
        <button type="button" className="link small agent-clear" onClick={() => setTurns([])}>
          Start a new conversation
        </button>
      ) : null}
    </aside>
  );
}

function Working({ job }: { job: AgentJob | undefined }) {
  return (
    <p className="muted small" role="status">
      {job?.status === "waiting" ? "Waiting its turn…" : `Thinking with ${job?.model_label ?? "your model"}…`}
    </p>
  );
}

function AgentReply({
  turn,
  onDone,
  onRun,
  actions,
  said,
}: {
  turn: Turn;
  onDone: (text: string, offered: NonNullable<Turn["offered"]>) => void;
  onRun: (action: string) => void;
  actions: AgentAction[];
  said: string;
}) {
  const answered = turn.text !== undefined;
  const { data: job, error } = useAgentJob(answered ? null : (turn.job ?? null));
  useEffect(() => {
    if (!answered && job?.status === "done") {
      onDone(job.result.reply ?? "", { run: job.result.run ?? [], notes: job.result.notes ?? [] });
    }
  }, [job, answered, onDone]);
  if (error) return <ErrorNote error={error} />;
  if (job?.status === "failed") return <p className="warning small">{job.error}</p>;
  if (!answered) return <Working job={job} />;
  const offered = turn.offered ?? { run: [], notes: [] };
  return (
    <div className="agent-turn theirs">
      <Markdown text={turn.text || "(no answer)"} />
      {offered.run.length ? (
        <div className="row small">
          {offered.run.map((id) => (
            <button key={id} type="button" onClick={() => onRun(id)}>
              Run {actions.find((a) => a.id === id)?.label ?? id}
            </button>
          ))}
        </div>
      ) : null}
      {offered.notes.map((note) => (
        <SuggestedNote key={note.title} note={note} said={said} />
      ))}
    </div>
  );
}

function SuggestedNote({ note, said }: { note: { title: string; text: string; kind: string }; said: string }) {
  const keep = useKeepAgentNote();
  return (
    <div className="agent-note">
      <p className="small">
        <strong>{note.title}</strong> <span className="muted">({note.kind})</span>
      </p>
      <p className="small">{note.text}</p>
      {keep.isSuccess ? (
        <p className="small" role="status">
          Suggested: it waits in <Link to="/catch-up">Catch up</Link>.
        </p>
      ) : (
        <button type="button" className="small" disabled={keep.isPending} onClick={() => keep.mutate({ ...note, said })}>
          Keep it
        </button>
      )}
      <ErrorNote error={keep.error} />
    </div>
  );
}

/** An action at work, then what came of it: its summary, the suggestions it made, and its
 * questions, answered right here. */
export function ActionTurn({ jobId, action }: { jobId: string | null; action?: AgentAction }) {
  const { data: job, error } = useAgentJob(jobId);
  const { data: agent } = useAgent();
  if (error) return <ErrorNote error={error} />;
  const label = action?.label ?? job?.action ?? "The action";
  if (!job || job.status === "waiting" || job.status === "running") {
    return (
      <div className="agent-turn action">
        <p className="small">
          <strong>{label}</strong>
        </p>
        <Working job={job} />
      </div>
    );
  }
  if (job.status === "failed") {
    return (
      <div className="agent-turn action">
        <p className="small">
          <strong>{label}</strong>
        </p>
        <p className="warning small">{job.error}</p>
      </div>
    );
  }
  const result = job.result;
  const questions = (agent?.questions ?? []).filter((q) => q.run === result.id);
  return (
    <div className="agent-turn action">
      <p className="small">
        <strong>{label}</strong> <span className="muted">· {job.model_label}</span>
      </p>
      <p className="small">{result.summary}</p>
      {result.proposed ? (
        <p className="small">
          {result.proposed === 1 ? "1 suggestion waits" : `${result.proposed} suggestions wait`} in <Link to="/catch-up">Catch up</Link>.
        </p>
      ) : null}
      {questions.map((q) => (
        <AgentQuestionCard key={q.key} question={q} compact />
      ))}
      {result.notes?.length ? <p className="muted small">{result.notes.join(" ")}</p> : null}
    </div>
  );
}

/** Bottom right: the agent's suggestions as the Brain changes, and the button that opens the
 * panel. Set one aside and it stays away for a few days, or until what it counts changes. */
export function AgentDock() {
  const panel = useAgentPanel();
  const { data: suggestions } = useAgentSuggestions();
  const dismiss = useDismissAgentSuggestion();
  const [hidden, setHidden] = useState(false);
  if (panel.open) return null;
  const shown = hidden ? [] : (suggestions ?? []).slice(0, 2);
  const count = suggestions?.length ?? 0;
  return (
    <div className="agent-dock">
      {shown.map((s) => (
        <article key={s.key} className="agent-toast" aria-label={s.title}>
          <p className="agent-toast-title">{s.title}</p>
          <p className="muted small">{s.detail}</p>
          <div className="row small">
            {s.action ? (
              <button type="button" className="primary" onClick={() => panel.openPanel({ action: s.action ?? undefined })}>
                Run it
              </button>
            ) : s.link ? (
              <Link className="button primary" to={s.link}>
                Open
              </Link>
            ) : null}
            <button type="button" className="link" disabled={dismiss.isPending} onClick={() => dismiss.mutate({ key: s.key })}>
              Not now
            </button>
          </div>
        </article>
      ))}
      <div className="row agent-dock-row">
        {shown.length ? (
          <button type="button" className="link small" onClick={() => setHidden(true)}>
            Hide suggestions
          </button>
        ) : null}
        <button type="button" className="agent-open" onClick={() => panel.openPanel()} aria-label="Open the knowledge agent">
          <Bot className="button-icon" aria-hidden="true" />
          Agent
          {count ? <span className="calm-count">{count}</span> : null}
        </button>
      </div>
    </div>
  );
}

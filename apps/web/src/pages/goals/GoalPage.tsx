// A goal's page (goals plan 6.2 and 6.3): it leads with your strategy and your check-in, and AI
// work sits beside it in a rail. You set the status; a computed measure shows beside your call,
// never over it. AI suggests and you choose. Each board block has one switch, "Your AIs can
// read this": shared blocks go to the goal's plan file, private ones never leave the app.

import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import {
  useAnswerStep,
  useBrainProjects,
  useChangeGoal,
  useGoal,
  useGoalDecision,
  useLinkProject,
  useSaveBoard,
} from "../../api/hooks";
import type { GoalBlock, GoalBoard, GoalPage as Goal } from "../../api/types";
import { useAgentPanel } from "../../components/agent/AgentContext";
import { CheckIn, GoalStatus, Progress, Trend } from "../../components/goals/GoalParts";
import { CopyBlock, ErrorNote, Loading, Section } from "../../components/ui";
import { when } from "../../lib/format";

const BLOCKS: { type: GoalBlock["type"]; label: string }[] = [
  { type: "note", label: "Note" },
  { type: "checklist", label: "Checklist" },
  { type: "doc", label: "Doc" },
  { type: "projects", label: "Projects" },
  { type: "links", label: "Links and files" },
  { type: "decisions", label: "Decisions" },
];

export function GoalPage() {
  const { goalId = "" } = useParams();
  const { data: goal, isLoading, error } = useGoal(goalId);
  const [checking, setChecking] = useState(false);
  const { openPanel } = useAgentPanel();
  if (isLoading) return <Loading />;
  if (!goal) return <ErrorNote error={error} />;
  const ask = () =>
    openPanel({
      message: `About my goal "${goal.title}" (\`${goal.id}\`): suggest how to break it into projects, a plan for what gets in the way, a measure code could compute, and what the Brain already holds on it.`,
    });
  return (
    <div className="page goal-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/projects">Goals and Projects</Link>
      </nav>
      <header className="page-head">
        <div className="row wrap">
          <h1>{goal.title}</h1>
          {goal.lifecycle === "active" && goal.level === "yours" ? (
            <button type="button" className="primary" onClick={() => setChecking(!checking)} aria-expanded={checking}>
              Check in
            </button>
          ) : null}
          <button type="button" onClick={ask}>
            Ask AI
          </button>
        </div>
        {goal.why ? <p className="lede">Why: “{goal.why}”</p> : null}
        <p className="row wrap">
          <GoalStatus goal={goal} />
          {goal.call && goal.checked_in_at ? <span className="muted small">{when(goal.checked_in_at)}</span> : null}
          <Progress goal={goal} />
          <span className="muted small">{goal.due ? `by ${goal.due}` : "ongoing"}</span>
          <Trend values={goal.trend} />
          <span className="muted small">Owner: {goal.level === "yours" ? "You" : goal.kept_by}</span>
        </p>
        {goal.flag ? <p className="small flag">{goal.flag}</p> : null}
        <Lifecycle goal={goal} />
      </header>
      {checking || goal.check_in_due ? (
        <Section title="Check in">
          <CheckIn goal={goal} onDone={() => setChecking(false)} />
        </Section>
      ) : null}
      <div className="goal-layout">
        <Board goal={goal} />
        <Rail goal={goal} />
      </div>
    </div>
  );
}

function Lifecycle({ goal }: { goal: Goal }) {
  const change = useChangeGoal(goal.id);
  const [asking, setAsking] = useState<string | null>(null);
  const set = (status: string) => change.mutate({ status }, { onSuccess: () => setAsking(null) });
  if (goal.lifecycle !== "active") {
    return (
      <p className="small">
        This goal is {goal.lifecycle}.{" "}
        <button type="button" className="link small" onClick={() => set("active")} disabled={change.isPending}>
          Make it active again
        </button>
      </p>
    );
  }
  return (
    <div className="row small">
      <button type="button" className="link small" onClick={() => set("paused")} disabled={change.isPending}>
        Pause
      </button>
      {goal.due ? (
        <button type="button" className="link small" onClick={() => setAsking("met")}>
          Met it
        </button>
      ) : (
        <button type="button" className="link small" onClick={() => setAsking("met")}>
          Call it met
        </button>
      )}
      <button type="button" className="link small" onClick={() => setAsking("dropped")}>
        Drop it
      </button>
      {asking ? (
        <span role="alertdialog" aria-label="Confirm">
          {asking === "met" ? "Mark this goal met?" : "Drop this goal? Its projects stay as they are."}{" "}
          <button type="button" className="link small" onClick={() => set(asking)}>
            Yes
          </button>{" "}
          <button type="button" className="link small" onClick={() => setAsking(null)}>
            No
          </button>
        </span>
      ) : null}
      <ErrorNote error={change.error} />
    </div>
  );
}

// ---------------------------------------------------------------- the strategy board

function newBlock(type: GoalBlock["type"]): GoalBlock {
  const title = BLOCKS.find((b) => b.type === type)?.label ?? "Block";
  // New notes start private, so scratch thinking stays yours.
  return { id: Math.random().toString(36).slice(2, 12), type, title, shared: type !== "note", collapsed: false, column: 0, items: [], links: [], text: "" };
}

function Board({ goal }: { goal: Goal }) {
  const save = useSaveBoard(goal.id);
  const [board, setBoard] = useState<GoalBoard>(goal.board);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    setBoard(goal.board);
    setDirty(false);
  }, [goal.board]);
  const change = (next: GoalBoard) => {
    setBoard(next);
    setDirty(true);
  };
  const setBlock = (id: string, patch: Partial<GoalBlock>) => change({ ...board, blocks: board.blocks.map((b) => (b.id === id ? { ...b, ...patch } : b)) });
  const move = (id: string, by: number) => {
    const blocks = [...board.blocks];
    const at = blocks.findIndex((b) => b.id === id);
    const to = at + by;
    if (at < 0 || to < 0 || to >= blocks.length) return;
    const [moved] = blocks.splice(at, 1);
    if (moved) blocks.splice(to, 0, moved);
    change({ ...board, blocks });
  };
  const columns = board.columns === 2 ? [0, 1] : [0];
  return (
    <section className="goal-board" aria-label="Strategy board">
      <header className="row wrap">
        <h2>Strategy board</h2>
        <AddBlock onAdd={(type) => change({ ...board, blocks: [...board.blocks, newBlock(type)] })} />
        <span className="small">
          Columns:{" "}
          {[1, 2].map((n) => (
            <button key={n} type="button" className={`link small${board.columns === n ? " current" : ""}`} aria-pressed={board.columns === n} onClick={() => change({ ...board, columns: n as 1 | 2 })}>
              {n}
            </button>
          ))}
        </span>
        <button type="button" className="primary" disabled={!dirty || save.isPending} onClick={() => save.mutate(board)}>
          {save.isPending ? "Saving..." : dirty ? "Save the board" : "Saved"}
        </button>
      </header>
      {!board.blocks.length ? <p className="muted small">An empty board. Add a note, a checklist or your projects.</p> : null}
      <div className={`board-columns cols-${board.columns}`}>
        {columns.map((column) => (
          <div key={column} className="board-column">
            {board.blocks
              .filter((b) => (board.columns === 2 ? b.column === column : true))
              .map((block) => (
                <BlockCard
                  key={block.id}
                  goal={goal}
                  block={block}
                  twoColumns={board.columns === 2}
                  onChange={(patch) => setBlock(block.id, patch)}
                  onMove={(by) => move(block.id, by)}
                  onRemove={() => change({ ...board, blocks: board.blocks.filter((b) => b.id !== block.id) })}
                />
              ))}
          </div>
        ))}
      </div>
      <ErrorNote error={save.error} />
    </section>
  );
}

function AddBlock({ onAdd }: { onAdd: (type: GoalBlock["type"]) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="add-block">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        + Block
      </button>
      {open ? (
        <span className="row small" role="menu">
          {BLOCKS.map((b) => (
            <button key={b.type} type="button" role="menuitem" className="link small" onClick={() => (onAdd(b.type), setOpen(false))}>
              {b.label}
            </button>
          ))}
        </span>
      ) : null}
    </span>
  );
}

function BlockCard({
  goal,
  block,
  twoColumns,
  onChange,
  onMove,
  onRemove,
}: {
  goal: Goal;
  block: GoalBlock;
  twoColumns: boolean;
  onChange: (patch: Partial<GoalBlock>) => void;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  return (
    <article className="card board-block" aria-label={block.title}>
      <header className="row wrap">
        <input className="block-title" maxLength={120} value={block.title} onChange={(event) => onChange({ title: event.target.value })} aria-label="Block title" />
        <label className="small">
          <input type="checkbox" checked={block.shared} onChange={(event) => onChange({ shared: event.target.checked })} /> Your AIs can read this
        </label>
        <span className="row small">
          <button type="button" className="link small" aria-label="Move up" onClick={() => onMove(-1)}>
            ↑
          </button>
          <button type="button" className="link small" aria-label="Move down" onClick={() => onMove(1)}>
            ↓
          </button>
          {twoColumns ? (
            <button type="button" className="link small" onClick={() => onChange({ column: block.column === 1 ? 0 : 1 })}>
              Other column
            </button>
          ) : null}
          <button type="button" className="link small" aria-expanded={!block.collapsed} onClick={() => onChange({ collapsed: !block.collapsed })}>
            {block.collapsed ? "Open" : "Fold"}
          </button>
          <button type="button" className="link small" onClick={onRemove}>
            Remove
          </button>
        </span>
      </header>
      {block.collapsed ? null : <BlockBody goal={goal} block={block} onChange={onChange} />}
    </article>
  );
}

function BlockBody({ goal, block, onChange }: { goal: Goal; block: GoalBlock; onChange: (patch: Partial<GoalBlock>) => void }) {
  if (block.type === "note") {
    return <textarea rows={4} maxLength={8000} value={block.text ?? ""} onChange={(event) => onChange({ text: event.target.value })} aria-label={`${block.title} text`} />;
  }
  if (block.type === "checklist") return <Checklist block={block} onChange={onChange} />;
  if (block.type === "doc") {
    return (
      <div className="stack small">
        <input placeholder="The doc's title" maxLength={200} value={block.doc_title ?? ""} onChange={(event) => onChange({ doc_title: event.target.value })} aria-label="Doc title" />
        <input placeholder="Its id in Workspace (optional)" maxLength={60} value={block.doc_id ?? ""} onChange={(event) => onChange({ doc_id: event.target.value })} aria-label="Doc id" />
        {block.doc_id ? <Link to={`/work/workspace/${encodeURIComponent(block.doc_id)}`}>Open it in Workspace</Link> : null}
      </div>
    );
  }
  if (block.type === "projects") return <ProjectsBlock goal={goal} />;
  if (block.type === "links") return <Links block={block} onChange={onChange} />;
  return <Decisions goal={goal} />;
}

function Checklist({ block, onChange }: { block: GoalBlock; onChange: (patch: Partial<GoalBlock>) => void }) {
  const items = block.items ?? [];
  const [text, setText] = useState("");
  return (
    <div className="stack">
      <ul className="checklist">
        {items.map((item, i) => (
          <li key={i} className="row">
            <label>
              <input
                type="checkbox"
                checked={item.done}
                onChange={(event) => onChange({ items: items.map((it, j) => (j === i ? { ...it, done: event.target.checked } : it)) })}
              />{" "}
              {item.text}
            </label>
            <button type="button" className="link small" aria-label={`Remove ${item.text}`} onClick={() => onChange({ items: items.filter((_, j) => j !== i) })}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <form
        className="row"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          if (!text.trim()) return;
          onChange({ items: [...items, { text: text.trim(), done: false }] });
          setText("");
        }}
      >
        <input placeholder="Add an item" maxLength={300} value={text} onChange={(event) => setText(event.target.value)} aria-label="New item" />
        <button type="submit" className="link small">
          Add
        </button>
      </form>
    </div>
  );
}

function Links({ block, onChange }: { block: GoalBlock; onChange: (patch: Partial<GoalBlock>) => void }) {
  const links = block.links ?? [];
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  return (
    <div className="stack small">
      <ul>
        {links.map((link, i) => (
          <li key={i}>
            {link.url ? (
              <a href={link.url} target="_blank" rel="noreferrer">
                {link.title || link.url}
              </a>
            ) : (
              link.title
            )}{" "}
            <button type="button" className="link small" onClick={() => onChange({ links: links.filter((_, j) => j !== i) })}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="row">
        <input placeholder="Title" maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} aria-label="Link title" />
        <input placeholder="https://" maxLength={1000} value={url} onChange={(event) => setUrl(event.target.value)} aria-label="Link address" />
        <button
          type="button"
          className="link small"
          onClick={() => {
            if (!title.trim() && !url.trim()) return;
            onChange({ links: [...links, { title: title.trim(), url: url.trim() }] });
            setTitle("");
            setUrl("");
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}

function ProjectsBlock({ goal }: { goal: Goal }) {
  const { data: projects } = useBrainProjects();
  const link = useLinkProject(goal.id);
  const [pick, setPick] = useState("");
  const linked = new Set(goal.projects.map((p) => p.id));
  return (
    <div className="stack small">
      <ul>
        {goal.projects.map((p) => (
          <li key={p.id}>
            <Link to={`/projects/${encodeURIComponent(p.id)}`}>{p.title}</Link> <span className="muted">{p.status}</span>{" "}
            <button type="button" className="link small" onClick={() => link.mutate({ project: p.id, linked: false })}>
              Unlink
            </button>
          </li>
        ))}
      </ul>
      <div className="row">
        <select value={pick} onChange={(event) => setPick(event.target.value)} aria-label="A project to link">
          <option value="">Link a project...</option>
          {(projects ?? [])
            .filter((p) => !linked.has(p.id))
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
        </select>
        <button type="button" className="link small" disabled={!pick || link.isPending} onClick={() => link.mutate({ project: pick, linked: true }, { onSuccess: () => setPick("") })}>
          Link
        </button>
      </div>
      <ErrorNote error={link.error} />
    </div>
  );
}

function Decisions({ goal }: { goal: Goal }) {
  const decide = useGoalDecision(goal.id);
  const [text, setText] = useState("");
  const decided = goal.journal.filter((e) => e.kind === "decision");
  return (
    <div className="stack small">
      <ul>
        {decided.map((e, i) => (
          <li key={i}>
            <span className="muted">{e.at.slice(0, 10)}</span> {e.text}
          </li>
        ))}
      </ul>
      <form
        className="row"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          decide.mutate(text.trim(), { onSuccess: () => setText("") });
        }}
      >
        <input placeholder="What you decided" maxLength={1000} value={text} onChange={(event) => setText(event.target.value)} aria-label="A decision" />
        <button type="submit" className="link small" disabled={!text.trim() || decide.isPending}>
          Record
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- the rail

function Rail({ goal }: { goal: Goal }) {
  const answer = useAnswerStep(goal.id);
  const [feed, setFeed] = useState<"all" | "mine" | "ai">("all");
  const entries = goal.journal.filter((e) => (feed === "all" ? true : feed === "mine" ? e.kind === "check_in" || e.kind === "decision" : e.kind === "progress"));
  return (
    <aside className="goal-rail" aria-label="Beside the goal">
      <Section title="Projects">
        {goal.projects.length ? (
          <ul className="small">
            {goal.projects.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${encodeURIComponent(p.id)}`}>{p.title}</Link> <span className="muted">{p.status}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">No projects yet. Link one on the board.</p>
        )}
      </Section>
      <Section title="AI on this">
        <p className="muted small">The tasks your AIs work for this goal show here once tasks and handoffs arrive.</p>
      </Section>
      <Section title="Suggested">
        {goal.suggestions.length ? (
          <ul className="small stack">
            {goal.suggestions.map((s) => (
              <li key={s.id}>
                “{s.text}” <span className="muted">({s.source})</span>
                <div className="row">
                  <button type="button" className="link small" disabled={answer.isPending} onClick={() => answer.mutate({ step: s.id, accept: true })}>
                    Make it a step
                  </button>
                  <button type="button" className="link small" disabled={answer.isPending} onClick={() => answer.mutate({ step: s.id, accept: false })}>
                    No
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">Nothing waits. The coach and the knowledge agent suggest next steps here.</p>
        )}
        <ErrorNote error={answer.error} />
      </Section>
      <Section title="Updates">
        <div className="row small" role="group" aria-label="Show">
          {(["all", "mine", "ai"] as const).map((f) => (
            <button key={f} type="button" className={`link small${feed === f ? " current" : ""}`} aria-pressed={feed === f} onClick={() => setFeed(f)}>
              {f === "all" ? "All" : f === "mine" ? "Only mine" : "Only AI"}
            </button>
          ))}
        </div>
        {entries.length ? (
          <ul className="small updates">
            {entries.slice(0, 20).map((e, i) => (
              <li key={i}>
                <span className="muted">{when(e.at)}</span>{" "}
                {e.kind === "check_in"
                  ? `You: ${e.value ?? ""}${e.value !== null && e.value !== undefined ? ", " : ""}${(e.call ?? "").replace("_", " ")}${e.line ? `. “${e.line}”` : ""}`
                  : e.kind === "decision"
                    ? `Decided: ${e.text}`
                    : `${e.by}: ${e.text}`}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">No updates yet.</p>
        )}
      </Section>
      <Section title="What your AI gets for this goal">
        <p className="muted small">The goal, its why and pointers to the blocks you shared. Private blocks never reach an AI.</p>
        <CopyBlock text={goal.context} prose />
        {goal.plan ? (
          <details>
            <summary className="small">The shared plan</summary>
            <CopyBlock text={goal.plan} prose />
          </details>
        ) : null}
      </Section>
    </aside>
  );
}

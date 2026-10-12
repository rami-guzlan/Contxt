// Goals and Projects: the work the Brain follows across every conversation and, once you set
// one, the goals it serves (goals plan 6.1). Each project has its objective (the output it is
// chasing, at the top of every brief in it), where it stands, your own Workspace for it, its
// progress as a timeline, its files, the notes filed with it, and the names your AI knows it by;
// and you can see exactly what your AI gets for it. Goals are optional: without one this is
// simply Projects, with one quiet line about them.

import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import {
  useAiRequests,
  useBrainDecisions,
  useBrainProject,
  useBrainProjects,
  useBrainProposals,
  useCreateBrainProject,
  useGoals,
  useLadder,
  useProjectObjective,
  useUpdateProject,
} from "../api/hooks";
import type { BrainProject, BrainProjectDetail } from "../api/types";
import { ContextPreview } from "../components/ContextPreview";
import { GoalCard, SetGoal, goalUrl } from "../components/goals/GoalParts";
import { ProjectTasks } from "../components/tasks/Tasks";
import { Markdown } from "../components/Markdown";
import { Empty, ErrorNote, Field, Loading, Section } from "../components/ui";
import { ProjectWorkspace } from "../components/work/WorkspaceParts";
import { label, plural, when } from "../lib/format";
import { workspaceFor } from "../lib/links";
import { AddFileDialog } from "./brain/AddFile";
import { day, entryUrl, fileViewUrl } from "./brain/shared";

const projectUrl = (id: string) => `/projects/${encodeURIComponent(id)}`;
const QUIET_DAYS = 14; // this long without a move, a project is asked whether it is still active

/** Days since a project last moved, or null when it never did. */
export function quietDays(updated: string | null | undefined, now = Date.now()): number | null {
  if (!updated) return null;
  return Math.floor((now - new Date(updated).getTime()) / 86_400_000);
}

/** Text cut at a word to fit a card; the project's page has it whole. */
function clip(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit - 1);
  return `${cut.slice(0, cut.lastIndexOf(" ") > 0 ? cut.lastIndexOf(" ") : cut.length).replace(/[,;:.]$/, "")}…`;
}
// What a progress update can change in where a project stands, in the order people read it.
const STATE: { key: string; name: string }[] = [
  { key: "status", name: "Status" },
  { key: "current", name: "Now" },
  { key: "next", name: "Next" },
  { key: "blockers", name: "Blocked on" },
  { key: "decisions", name: "Decided" },
  { key: "completed", name: "Done" },
];

export function ProjectsPage() {
  const { data: projects, isLoading, error } = useBrainProjects();
  const { data: ladder } = useLadder();
  const [params] = useSearchParams();
  // "Set it as a goal" from Catch up opens the panel with the words it came with.
  const start = params.get("set") ?? "";
  const [adding, setAdding] = useState(false);
  const [setting, setSetting] = useState(!!start);
  const [goalFilter, setGoalFilter] = useState("");
  if (isLoading) return <Loading />;
  if (!projects) return <ErrorNote error={error} />;
  const hasGoals = !!ladder?.has_goals;
  const goals = (ladder?.yours ?? []).filter((g) => !["dropped", "retired"].includes(g.lifecycle));
  const titles = new Map(goals.map((g) => [g.id, g.title]));
  const shown = goalFilter ? projects.filter((p) => (goalFilter === "none" ? !p.goals?.length : p.goals?.includes(goalFilter))) : projects;
  const active = shown.filter((p) => p.active);
  const rest = shown.filter((p) => !p.active);
  return (
    <div className="page">
      <h1>{hasGoals ? "Goals and Projects" : "Projects"}</h1>
      <p className="lede">
        {hasGoals ? "What you want to achieve, and the work toward it. Your Brain's purpose is in " : "The work your AI follows. "}
        {hasGoals ? (
          <>
            <Link to="/settings?tab=alignment">Settings &gt; Alignment</Link>.
          </>
        ) : (
          "Mention a project by any of its names in any chat, and your AI gets its objective, where it stands, its latest progress and its current files."
        )}
      </p>
      {!hasGoals ? (
        <p className="muted small">
          Goals are optional. Add one when you want to plan toward something bigger than a single project.{" "}
          <button type="button" className="link small" onClick={() => setSetting(true)}>
            Set a goal
          </button>
        </p>
      ) : null}
      <div className="row" data-tour="projects-new">
        {hasGoals ? (
          <button type="button" onClick={() => setSetting(true)}>
            + Goal
          </button>
        ) : null}
        <button type="button" className="primary" onClick={() => setAdding(!adding)}>
          {hasGoals ? "+ Project" : "New project"}
        </button>
      </div>
      {setting ? <SetGoal start={start} onClose={() => setSetting(false)} /> : null}
      {adding ? <NewProject goals={goals.map((g) => ({ id: g.id, title: g.title }))} onDone={() => setAdding(false)} /> : null}
      {hasGoals ? (
        <Section title="Your goals">
          <ul className="goal-cards">
            {goals.map((g) => (
              <GoalCard key={g.id} goal={g} />
            ))}
          </ul>
          <button type="button" className="link small" onClick={() => setSetting(true)}>
            + Set a goal
          </button>
        </Section>
      ) : null}
      <Section
        title={hasGoals ? "Projects" : "Active"}
        tour="projects-list"
        actions={
          hasGoals ? (
            <label className="small">
              Goal{" "}
              <select value={goalFilter} onChange={(event) => setGoalFilter(event.target.value)}>
                <option value="">All</option>
                {goals.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
                <option value="none">No goal</option>
              </select>
            </label>
          ) : null
        }
      >
        {active.length ? (
          <ul className="project-cards">
            {active.map((p) => (
              <ProjectCard key={p.id} project={p} goals={hasGoals ? titles : undefined} />
            ))}
          </ul>
        ) : (
          <Empty why="No active projects. Start one here, or tell your AI in a chat: “I'm starting the Q4 campaign proposals.”" />
        )}
      </Section>
      {rest.length ? (
        <Section title="Paused or finished">
          <ul className="project-cards">
            {rest.map((p) => (
              <ProjectCard key={p.id} project={p} goals={hasGoals ? titles : undefined} />
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

function ProjectCard({ project, goals: titles }: { project: BrainProject; goals?: Map<string, string> }) {
  const { data: goals } = useGoals();
  const fromGoals = (goals?.projects ?? []).some((name) => name.toLowerCase() === project.title.toLowerCase());
  const quiet = quietDays(project.updated);
  const serves = (project.goals ?? []).filter((id) => titles?.has(id));
  return (
    <li className="card project-card">
      <header>
        <h3>
          <Link to={projectUrl(project.id)}>{project.title}</Link>
        </h3>
        {project.status && project.status !== "active" ? <span className="chip">{label(project.status)}</span> : null}
        {fromGoals ? <span className="chip small">From your goals</span> : null}
      </header>
      {titles ? (
        <p className="small">
          {serves.length ? (
            <>
              Serves:{" "}
              {serves.map((id, i) => (
                <span key={id}>
                  {i ? ", " : ""}
                  <Link to={goalUrl(id)}>{titles.get(id)}</Link>
                </span>
              ))}
            </>
          ) : (
            <span className="muted">(no goal)</span>
          )}
        </p>
      ) : null}
      {project.objective ? <p className="small">Objective: {clip(project.objective, 200)}</p> : null}
      {project.summary ? <p className="muted">{project.summary}</p> : null}
      {project.current && project.current !== project.summary ? (
        <p className="small">
          <strong>Latest:</strong> {clip(project.current, 200)}
        </p>
      ) : null}
      {project.next ? (
        <p className="small">
          <strong>Next:</strong> {clip(project.next, 200)}
        </p>
      ) : null}
      <p className="muted small">
        {plural(project.files, "file")} · {plural(project.updates, "update")}
        {project.updated ? ` · moved ${when(project.updated)}` : ""}
      </p>
      {project.active && quiet !== null && quiet >= QUIET_DAYS ? <StillActive project={project} days={quiet} /> : null}
    </li>
  );
}

/** Nothing moved in two weeks: still active, paused, or done? One tap. */
function StillActive({ project, days }: { project: BrainProject; days: number }) {
  const update = useUpdateProject(project.id);
  const set = (status: string, summary: string) => update.mutate({ summary, state: { status } });
  if (update.isSuccess) return <p className="small muted">Noted.</p>;
  return (
    <div className="nudge small">
      <span>Nothing moved in {plural(days, "day")}. Still active?</span>
      <div className="row">
        <button type="button" className="link small" disabled={update.isPending} onClick={() => set("active", "Still active")}>
          Yes
        </button>
        <button type="button" className="link small" disabled={update.isPending} onClick={() => set("paused", "Paused for now")}>
          Paused
        </button>
        <button type="button" className="link small" disabled={update.isPending} onClick={() => set("done", "Done")}>
          Done
        </button>
      </div>
      <ErrorNote error={update.error} />
    </div>
  );
}

/** A new project: its name, the output it is chasing (its objective, which opens every brief in
 * it), what it is for in a line, the goals it serves (asked only when you have goals), and the
 * other names you will call it. */
function NewProject({ onDone, goals = [] }: { onDone: () => void; goals?: { id: string; title: string }[] }) {
  const create = useCreateBrainProject();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [summary, setSummary] = useState("");
  const [aliases, setAliases] = useState("");
  const [serves, setServes] = useState<string[]>([]);
  const words = objective.trim() ? objective.trim().split(/\s+/).length : 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      {
        name: name.trim(),
        summary: summary.trim(),
        ...(objective.trim() ? { objective: objective.trim() } : {}),
        ...(serves.length ? { goals: serves } : {}),
        aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean),
      },
      {
        onSuccess: (made) => {
          onDone();
          navigate(projectUrl(made.id));
        },
      },
    );
  }

  return (
    <form className="card stack" onSubmit={submit} aria-label="New project">
      <Field label="Name">
        <input required maxLength={80} value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field label="What output are we chasing?" hint={`Its objective, a sentence or two: every brief in the project opens with it. ${words ? `${words} of 60 words.` : ""}`}>
        <textarea rows={2} maxLength={1000} value={objective} onChange={(event) => setObjective(event.target.value)} />
      </Field>
      <Field label="What it is for" hint="One line.">
        <input required maxLength={300} value={summary} onChange={(event) => setSummary(event.target.value)} />
      </Field>
      {goals.length ? (
        <fieldset className="stack small">
          <legend>The goals it serves</legend>
          {goals.map((g) => (
            <label key={g.id}>
              <input
                type="checkbox"
                checked={serves.includes(g.id)}
                onChange={(event) => setServes(event.target.checked ? [...serves, g.id] : serves.filter((id) => id !== g.id))}
              />{" "}
              {g.title}
            </label>
          ))}
        </fieldset>
      ) : null}
      <Field label="Other names you will call it" hint="Comma separated, like: campaign proposals, Jordan's proposals">
        <input value={aliases} onChange={(event) => setAliases(event.target.value)} />
      </Field>
      <div className="row">
        <button type="submit" className="primary" disabled={create.isPending || !name.trim() || !summary.trim() || words > 60}>
          Start it
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
      <ErrorNote error={create.error} />
    </form>
  );
}

// ---------------------------------------------------------------- one project

/** The project's objective: the output it is chasing, the first line of every brief in it.
 * Changing it reaches every brief, so it takes a reason and makes an undo point. */
function Objective({ project }: { project: BrainProjectDetail }) {
  const change = useProjectObjective(project.id);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(project.objective ?? "");
  const [reason, setReason] = useState("");
  if (!editing) {
    return (
      <p>
        <strong>Objective:</strong> {project.objective || <span className="muted">not set yet; its briefs use what it is for meanwhile</span>}{" "}
        <button type="button" className="link small" onClick={() => setEditing(true)}>
          {project.objective ? "Edit" : "Set it"}
        </button>
      </p>
    );
  }
  return (
    <form
      className="stack"
      aria-label="Objective"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        change.mutate({ objective: text.trim(), reason: reason.trim() }, { onSuccess: () => setEditing(false) });
      }}
    >
      <Field label="What output are we chasing?" hint="A sentence or two, about 60 words at most. It reaches every brief in the project.">
        <textarea rows={2} maxLength={1000} value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      <Field label="Why it changes">
        <input required maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
      </Field>
      <div className="row">
        <button type="submit" className="primary" disabled={change.isPending || !reason.trim()}>
          Save
        </button>
        <button type="button" onClick={() => setEditing(false)}>
          Cancel
        </button>
      </div>
      <ErrorNote error={change.error} />
    </form>
  );
}

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const { data: project, isLoading, error } = useBrainProject(projectId);
  const { data: ladder } = useLadder();
  const [adding, setAdding] = useState(false);
  if (isLoading) return <Loading />;
  if (!project) return <ErrorNote error={error} />;
  return (
    <div className="page project-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/projects">{ladder?.has_goals ? "Goals and Projects" : "Projects"}</Link>
      </nav>
      <header className="page-head">
        <h1>{project.title}</h1>
        {ladder?.has_goals && project.goals?.length ? (
          <p className="small">
            Serves:{" "}
            {project.goals.map((id, i) => (
              <span key={id}>
                {i ? ", " : ""}
                <Link to={goalUrl(id)}>{ladder.yours.find((g) => g.id === id)?.title ?? id}</Link>
              </span>
            ))}
          </p>
        ) : null}
        <Objective project={project} />
        {project.summary ? <p className="lede">{project.summary}</p> : null}
        <ProjectTasks project={project.id} />
      </header>
      <div className="grid-2">
        <Section title="Where it stands" tour="project-state">
          <Standing project={project} />
          <RecordProgress project={project} />
        </Section>
        <Section
          title="Workspace"
          tour="project-workspace"
          actions={
            <Link className="small" to={workspaceFor(project.id)}>
              Open in Work
            </Link>
          }
        >
          <ProjectWorkspace project={project} />
        </Section>
      </div>
      <Section
        title="Files"
        tour="project-files"
        actions={
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            Add a file
          </button>
        }
      >
        <p className="muted small">What the Brain holds for it. Every AI you connect can read these.</p>
        <Files project={project} />
      </Section>
      {adding ? <AddFileDialog project={project.id} onClose={() => setAdding(false)} /> : null}
      <Section title="Progress">
        <Timeline project={project} />
      </Section>
      <div className="grid-2">
        <Section title="Your AI on this project">
          <AiOnProject id={project.id} />
        </Section>
        <Section title="What your AI gets" tour="project-preview">
          <p className="muted small">Ask something about this project the way you would ask your AI, and see what it gets, and why.</p>
          <ContextPreview project={project.id} example={`Where do we stand on ${project.title}?`} />
        </Section>
      </div>
      <Section title="Kept with it">
        <Waiting project={project} />
        {project.notes.length ? (
          <ul className="list">
            {project.notes.map((n) => (
              <li key={n.id}>
                <Link to={entryUrl(n.id)}>{n.title}</Link>
                {n.summary ? <span className="muted"> · {n.summary}</span> : null}
                {n.added ? <span className="muted small"> · {day(n.added)}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <Empty why="No decisions, facts or preferences filed with it yet. Your AI saves them here as you work." />
        )}
      </Section>
      <Section title="The names your AI knows it by">
        <Names project={project} />
      </Section>
      {project.brief && project.brief !== project.summary ? (
        <Section title="Brief">
          <Markdown text={project.brief} />
        </Section>
      ) : null}
    </div>
  );
}

/** The recent requests that brought this project: which app, when, and what was asked. */
function AiOnProject({ id }: { id: string }) {
  const { data } = useAiRequests({ limit: 100 });
  const mine = (data?.requests ?? []).filter((r) => r.project?.id === id || r.got.some((p) => p.kind === "focus" && p.id === id)).slice(0, 6);
  if (!mine.length) {
    return <p className="muted small">No AI has asked about it yet. Mention it in any chat and its state comes along.</p>;
  }
  return (
    <ul className="list compact-list">
      {mine.map((r) => (
        <li key={r.id}>
          <strong>{r.app}</strong> <span className="muted small">{when(r.at)}</span> · “{r.request}”
        </li>
      ))}
      <li>
        <Link className="small" to="/activity">
          Everything in Activity
        </Link>
      </li>
    </ul>
  );
}

/** Suggestions filed under this project that wait for the person's yes. */
function Waiting({ project }: { project: BrainProjectDetail }) {
  const { data: proposals } = useBrainProposals();
  const waiting = (proposals ?? []).filter((p) => p.route_key === project.route_key).length;
  if (!waiting) return null;
  return (
    <p>
      <Link to="/review">
        {plural(waiting, "suggestion")} for this project {waiting === 1 ? "waits" : "wait"} for you in Review
      </Link>
    </p>
  );
}

function Standing({ project }: { project: BrainProjectDetail }) {
  const rows = STATE.filter((s) => (project.state[s.key] ?? "").trim());
  if (!rows.length) return <p className="muted">Nothing recorded yet. Record where it stands below, or let your AI do it as you work.</p>;
  return (
    <dl className="state">
      {rows.map((s) => (
        <div key={s.key}>
          <dt>{s.name}</dt>
          <dd>{project.state[s.key]}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Progress in a line, and what changed in where it stands; added to the journal, never rewritten. */
function RecordProgress({ project }: { project: BrainProjectDetail }) {
  const update = useUpdateProject(project.id);
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState("");
  const [state, setState] = useState<Record<string, string>>({});

  function submit(event: FormEvent) {
    event.preventDefault();
    const changed = Object.fromEntries(Object.entries(state).filter(([, v]) => v.trim()));
    update.mutate(
      { summary: summary.trim(), state: changed },
      {
        onSuccess: () => {
          setOpen(false);
          setSummary("");
          setState({});
        },
      },
    );
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}>
        Record progress
      </button>
    );
  }
  return (
    <form className="stack" onSubmit={submit} aria-label="Record progress">
      <Field label="What happened" hint="One line, like: Sent v3 to Jordan.">
        <input required maxLength={300} value={summary} onChange={(event) => setSummary(event.target.value)} />
      </Field>
      {STATE.filter((s) => ["current", "next", "blockers", "decisions"].includes(s.key)).map((s) => (
        <Field key={s.key} label={`${s.name} (if it changed)`}>
          <input
            maxLength={1000}
            placeholder={project.state[s.key] || ""}
            value={state[s.key] ?? ""}
            onChange={(event) => setState({ ...state, [s.key]: event.target.value })}
          />
        </Field>
      ))}
      <div className="row">
        <button type="submit" className="primary" disabled={update.isPending || !summary.trim()}>
          Record it
        </button>
        <button type="button" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      <ErrorNote error={update.error} />
    </form>
  );
}

function Files({ project }: { project: BrainProjectDetail }) {
  if (!project.files.length) {
    return <Empty why="No files yet. Add the drafts and documents of this work: your AI quotes the part a request is about." />;
  }
  return (
    <ul className="file-list">
      {project.files.map((f) => (
        <li key={f.path} className="file-row">
          <div className="file-main">
            <Link className="file-title" to={fileViewUrl(f.path)}>
              {f.title}
            </Link>
            <p className="file-meta">
              {[
                f.version ? `version ${f.version}` : "",
                f.file_status ?? "",
                f.dated ? day(f.dated) : "",
                f.sections ? plural(f.sections, "part") : "",
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Timeline({ project }: { project: BrainProjectDetail }) {
  if (!project.updates.length) return <Empty why="No progress recorded yet." />;
  return (
    <ol className="history">
      {project.updates.map((u) => (
        <li key={u.seq}>
          <span>
            <strong>{u.summary}</strong>
            {Object.entries(u.changes ?? {}).map(([key, value]) => (
              <span key={key} className="muted small">
                {" "}
                · {STATE.find((s) => s.key === key)?.name ?? label(key)}: {String(value)}
              </span>
            ))}
          </span>
          <time dateTime={u.at}>{when(u.at)}</time>
        </li>
      ))}
    </ol>
  );
}

/** The other names a project goes by: a request using any of them brings the project. */
function Names({ project }: { project: BrainProjectDetail }) {
  const decide = useBrainDecisions();
  const [editing, setEditing] = useState(false);
  const [names, setNames] = useState(project.aliases.join(", "));

  function submit(event: FormEvent) {
    event.preventDefault();
    decide.mutate(
      { decisions: [{ action: "update", entry_id: project.id, fields: { aliases: names } }], label: `Names for ${project.title}` },
      { onSuccess: () => setEditing(false) },
    );
  }

  return (
    <div className="stack">
      <p>
        <strong>{project.title}</strong>
        {project.aliases.length ? <span className="muted">, also {project.aliases.map((a) => `“${a}”`).join(", ")}</span> : null}
      </p>
      {editing ? (
        <form className="row wrap" onSubmit={submit} aria-label="The names your AI knows it by">
          <input aria-label="Other names, comma separated" value={names} onChange={(event) => setNames(event.target.value)} />
          <button type="submit" className="primary" disabled={decide.isPending}>
            Save
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <p>
          <button type="button" className="link" onClick={() => setEditing(true)}>
            Change the names
          </button>
        </p>
      )}
      <ErrorNote error={decide.error} />
      {decide.data?.results.filter((r) => !r.ok).map((r) => (
        <p key={r.id} className="error" role="alert">
          {r.message}
        </p>
      ))}
    </div>
  );
}

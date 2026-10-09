// Work, Agents: digital roles written like a job description. Each points to the skills,
// Library documents, Brain topics, projects and recent meetings it needs (never copies), says
// what it never does and where its work goes; its operating prompt can be written by your AI
// from the form, for you to read, edit and save. Ask it for something here (a run like a skill
// run), or have any connected AI take it on (MCP get_agent, or Claude Code as a subagent).

import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import {
  useAddAgentToClaudeCode,
  useArchiveWorkAgent,
  useAskWorkAgent,
  useBrainCatalog,
  useBrainProjects,
  useLibrary,
  useSaveWorkAgent,
  useSkills,
  useWorkAgent,
  useWorkAgentRuns,
  useWorkAgents,
  useWorkAgentVersions,
  useWorkJob,
  useWriteAgentPrompt,
} from "../../api/hooks";
import type { AgentOutput, Task, WorkAgent, WorkAgentForm, WorkAgentFull } from "../../api/types";
import { RunCard } from "../../components/SkillWork";
import { Working } from "../../components/RunNow";
import { CopyBlock, Empty, ErrorNote, Field, Loading, Pill, Section, Tabs } from "../../components/ui";
import { linesOf, PickMany, textOf } from "../../components/work/PickMany";
import { plural, when } from "../../lib/format";
import { agentUrl, skillUrl } from "../../lib/links";
import { libraryItemUrl } from "./Library";

/** "content-strategist" as CS: the face of an agent on its card. */
export function initials(name: string): string {
  return (
    name
      .split("-")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "A"
  );
}

const OUTPUT_WORDS: Record<AgentOutput, string> = {
  outputs: "Outputs: what it makes lands in your outputs folder",
  workspace: "Workspace: drafts come back for you to edit",
  proposals: "The Brain: what should last comes as proposals",
};
const RUNNERS = [
  { value: "claude", label: "Claude Code on this computer" },
  { value: "codex", label: "Codex on this computer" },
  { value: "any", label: "Any AI you connect (it picks up the job)" },
];

// ---------------------------------------------------------------- the roster

export function WorkAgentsPage() {
  const [params, setParams] = useSearchParams();
  const archived = params.get("archived") === "1";
  const { data: agents, isLoading, error } = useWorkAgents(archived);
  if (isLoading) return <Loading />;
  if (!agents) return <ErrorNote error={error} />;
  return (
    <div className="work-tab agents">
      <div className="work-intro">
        <p>
          Your team of digital coworkers. Each agent is a role written like a job description: what it does, what it points to (skills,
          references, topics, projects, recent meetings) and what it never does. It always reads the current version of what it points to.
        </p>
        <Link className="button primary" to="/work/agents/new">
          <Plus className="button-icon" aria-hidden="true" />
          New agent
        </Link>
      </div>
      {agents.length ? (
        <ul className="agent-roster" aria-label="Agents">
          {agents.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </ul>
      ) : (
        <Empty
          why={
            archived
              ? "No archived agents."
              : "No agents yet. Write one like a job description: a line on what it does, the skills and references it uses, and what it never does."
          }
        >
          {!archived ? (
            <Link className="button primary" to="/work/agents/new">
              Write your first agent
            </Link>
          ) : null}
        </Empty>
      )}
      <p className="small">
        <button type="button" className="link" onClick={() => setParams(archived ? {} : { archived: "1" })}>
          {archived ? "Show active agents" : "Show archived agents"}
        </button>
      </p>
    </div>
  );
}

export function AgentCard({ agent }: { agent: WorkAgent }) {
  const pointers = [
    agent.skills.length ? plural(agent.skills.length, "skill") : "",
    agent.library.length ? plural(agent.library.length, "document") : "",
    agent.projects.length ? plural(agent.projects.length, "project") : "",
    agent.meetings_days ? `meetings, ${agent.meetings_days} days` : "",
  ].filter(Boolean);
  return (
    <li className={agent.status === "archived" ? "agent-card archived" : "agent-card"}>
      <span className="agent-face" aria-hidden="true">
        {initials(agent.name)}
      </span>
      <div className="agent-card-main">
        <Link to={agentUrl(agent.name)} className="agent-card-name">
          {agent.name}
        </Link>
        <p className="small">{agent.role}</p>
        {pointers.length ? (
          <ul className="chips" aria-label="Points to">
            {pointers.map((p) => (
              <li key={p} className="chip">
                {p}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="muted small">
          {agent.last_run ? (
            <>
              <Pill status={agent.last_run.status} /> last asked {when(agent.last_run.at)}
            </>
          ) : (
            "Not asked yet"
          )}
        </p>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- writing one

interface Draft {
  name: string;
  role: string;
  responsibilities: string;
  goals: string;
  boundaries: string;
  projects: string[];
  skills: string[];
  library: string[];
  context: string;
  meetings_days: number;
  output: AgentOutput;
  output_shape: string;
  runner: string;
  review: boolean;
  prompt: string;
}

function draftOf(agent?: WorkAgent): Draft {
  return {
    name: agent?.name ?? "",
    role: agent?.role ?? "",
    responsibilities: textOf(agent?.responsibilities ?? []),
    goals: textOf(agent?.goals ?? []),
    boundaries: textOf(agent?.boundaries ?? []),
    projects: agent?.projects ?? [],
    skills: agent?.skills ?? [],
    library: agent?.library ?? [],
    context: (agent?.context ?? []).join(", "),
    meetings_days: agent?.meetings_days ?? 0,
    output: agent?.output ?? "outputs",
    output_shape: agent?.output_shape ?? "",
    runner: agent?.runner ?? "claude",
    review: agent?.review ?? true,
    prompt: agent?.prompt ?? "",
  };
}

function formOf(draft: Draft): WorkAgentForm {
  return {
    name: draft.name.trim().toLowerCase(),
    role: draft.role.trim(),
    responsibilities: linesOf(draft.responsibilities),
    goals: linesOf(draft.goals),
    boundaries: linesOf(draft.boundaries),
    projects: draft.projects,
    skills: draft.skills,
    library: draft.library,
    context: draft.context
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean),
    meetings_days: Number(draft.meetings_days) || 0,
    output: draft.output,
    output_shape: draft.output_shape.trim(),
    runner: draft.runner,
    review: draft.review,
    prompt: draft.prompt,
  };
}

/** A slug from the role, for a new agent's name: "Writes the weekly plan" as "weekly-plan-writer"
 * is the person's to choose; this only suggests one from the first words. */
function suggestName(role: string): string {
  return role
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .split(/\s+/)
    .filter((w) => w && !["the", "a", "an", "and", "of", "for", "from", "to", "our", "my", "writes", "makes"].includes(w))
    .slice(0, 3)
    .join("-");
}

export function AgentEditor({ agent, onSaved }: { agent?: WorkAgent; onSaved: (saved: WorkAgentFull) => void }) {
  const isNew = !agent;
  const [draft, setDraft] = useState<Draft>(() => draftOf(agent));
  const [nameTouched, setNameTouched] = useState(!isNew);
  const save = useSaveWorkAgent();
  const write = useWriteAgentPrompt();
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job } = useWorkJob(jobId);
  const { data: skills } = useSkills();
  const { data: library } = useLibrary();
  const { data: projects } = useBrainProjects();
  const { data: catalog } = useBrainCatalog();
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  useEffect(() => {
    if (job?.status === "done" && job.result.prompt) setDraft((d) => ({ ...d, prompt: job.result.prompt ?? d.prompt }));
  }, [job?.status, job?.result.prompt]);
  const topics = (catalog?.areas ?? []).flatMap((a) => [a.key, ...a.topics.map((t) => t.key)]);
  const writing = write.isPending || (!!job && ["waiting", "running"].includes(job.status));
  return (
    <form
      className="stack agent-editor"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({ form: formOf(draft), isNew }, { onSuccess: onSaved });
      }}
    >
      <Section title="The role">
        <div className="stack">
          <Field label="What it does, in a line" hint="Like the first line of a job description.">
            <input
              required
              value={draft.role}
              placeholder="Writes the weekly LinkedIn plan from the content calendar"
              onChange={(event) => {
                set("role", event.target.value);
                if (!nameTouched) set("name", suggestName(event.target.value));
              }}
            />
          </Field>
          {isNew ? (
            <Field label="Its name" hint="Lowercase words joined by hyphens. Any AI asks for it by this name.">
              <input
                required
                value={draft.name}
                pattern="[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?"
                onChange={(event) => {
                  setNameTouched(true);
                  set("name", event.target.value.toLowerCase());
                }}
              />
            </Field>
          ) : null}
          <Field label="What it is responsible for" hint="One per line.">
            <textarea rows={3} value={draft.responsibilities} onChange={(event) => set("responsibilities", event.target.value)} />
          </Field>
          <Field label="The goals its work serves" hint="One per line, in your words.">
            <textarea rows={2} value={draft.goals} onChange={(event) => set("goals", event.target.value)} />
          </Field>
        </div>
      </Section>
      <Section title="What it points to">
        <div className="stack">
          <PickMany
            label="Skills it follows"
            empty="None: the Brain picks what fits each task"
            options={(skills?.skills ?? []).map((s) => ({ value: s.name, label: `/${s.name}`, hint: s.description.split(/(?<=[.!?])\s/)[0] }))}
            value={draft.skills}
            onChange={(v) => set("skills", v)}
          />
          <PickMany
            label="Library documents it reads whole"
            empty="None"
            options={(library ?? []).map((d) => ({ value: d.path, label: d.title, hint: d.kind }))}
            value={draft.library}
            onChange={(v) => set("library", v)}
          />
          <PickMany
            label="Projects it works on"
            empty="None"
            options={(projects ?? []).map((p) => ({ value: p.id, label: p.title, hint: p.active ? "" : "paused or finished" }))}
            value={draft.projects}
            onChange={(v) => set("projects", v)}
          />
          <Field label="Its context in the Brain" hint="Areas or topics, comma separated, such as brand/voice. Each task's brief brings what fits from there.">
            <input list="agent-topics" value={draft.context} onChange={(event) => set("context", event.target.value)} />
          </Field>
          <datalist id="agent-topics">
            {topics.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
          <Field label="Recent meetings it reads" hint="Recordings and transcripts from this many days back, for its projects. 0 for none.">
            <input type="number" min={0} max={90} value={draft.meetings_days} onChange={(event) => set("meetings_days", Number(event.target.value))} />
          </Field>
        </div>
      </Section>
      <Section title="Boundaries and output">
        <div className="stack">
          <Field label="What it never does" hint="One per line. Left empty: never publish, send or post; never change the Brain directly.">
            <textarea rows={3} value={draft.boundaries} onChange={(event) => set("boundaries", event.target.value)} />
          </Field>
          <div className="skill-inputs">
            <Field label="Where its work goes">
              <select value={draft.output} onChange={(event) => set("output", event.target.value as AgentOutput)}>
                {(Object.keys(OUTPUT_WORDS) as AgentOutput[]).map((o) => (
                  <option key={o} value={o}>
                    {OUTPUT_WORDS[o]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="How it runs">
              <select value={draft.runner} onChange={(event) => set("runner", event.target.value)}>
                {RUNNERS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="The shape of its work (optional)" hint="Such as: a one-page plan in Markdown, three posts under 200 words.">
            <input value={draft.output_shape} onChange={(event) => set("output_shape", event.target.value)} />
          </Field>
          <label className="check">
            <input type="checkbox" checked={draft.review} onChange={(event) => set("review", event.target.checked)} /> What it makes waits for my look
          </label>
        </div>
      </Section>
      <Section
        title="Its operating prompt"
        actions={
          <button
            type="button"
            disabled={!draft.role.trim() || writing}
            onClick={() => {
              const { prompt: _ignored, ...form } = formOf(draft);
              write.mutate(form, { onSuccess: (made) => setJobId(made.id) });
            }}
          >
            {writing ? "Your AI is writing it…" : draft.prompt ? "Write it again with your AI" : "Write it with your AI"}
          </button>
        }
      >
        <p className="muted small">
          How it does the work, step by step, as you would tell a new colleague. Your AI can write it from the role above; you read it,
          change it and save it. What it points to, its boundaries and where its work goes are added around it on every run.
        </p>
        <textarea className="mono" rows={12} value={draft.prompt} aria-label="Its operating prompt" onChange={(event) => set("prompt", event.target.value)} />
        {job?.status === "done" && job.result.questions?.length ? (
          <div className="notice small">
            <p>To make it sharper, the role could say:</p>
            <ul className="list">
              {job.result.questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {job?.status === "failed" ? <p className="error">{job.error}</p> : null}
        <ErrorNote error={write.error} />
      </Section>
      <div className="row">
        <button type="submit" className="primary" disabled={save.isPending || !draft.role.trim() || !draft.name.trim()}>
          {save.isPending ? "Saving…" : isNew ? "Save the agent" : "Save changes"}
        </button>
        <span className="muted small">Saved in your Brain, with an undo point and every version kept.</span>
      </div>
      <ErrorNote error={save.error} />
    </form>
  );
}

export function NewWorkAgentPage() {
  const navigate = useNavigate();
  return (
    <div className="agent-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/work/agents">Agents</Link>
      </nav>
      <header className="entry-head">
        <h1>New agent</h1>
        <p className="lede">A job description, not a prompt: say what it does and what it needs, and your AI can write the rest.</p>
      </header>
      <AgentEditor onSaved={(saved) => navigate(agentUrl(saved.agent.name))} />
    </div>
  );
}

// ---------------------------------------------------------------- one agent

const TABS = [
  { id: "ask", label: "Ask it" },
  { id: "role", label: "Role" },
  { id: "prompt", label: "What it gets" },
  { id: "elsewhere", label: "Use it elsewhere" },
  { id: "history", label: "History" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export function WorkAgentPage() {
  const { name = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data, isLoading, error } = useWorkAgent(name);
  const asked = params.get("tab");
  const tab: Tab = TABS.some((t) => t.id === asked) ? (asked as Tab) : "ask";
  const show = (next: Tab) => setParams(next === "ask" ? {} : { tab: next }, { replace: true });
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  const { agent, resolved } = data;
  return (
    <div className="agent-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/work/agents">Agents</Link>
      </nav>
      <header className="entry-head agent-head">
        <span className="agent-face large" aria-hidden="true">
          {initials(agent.name)}
        </span>
        <div>
          <h1>{agent.name}</h1>
          <p className="lede">{agent.role}</p>
          {agent.status === "archived" ? <p className="notice small">Archived. Save it again from Role to bring it back.</p> : null}
        </div>
      </header>
      {resolved.broken.length ? (
        <p className="notice small" role="note">
          Some of what it points to no longer resolves: {resolved.broken.join(", ")}. Fix them in Role.
        </p>
      ) : null}
      <Tabs tabs={TABS} active={tab} onChange={show} />
      {tab === "ask" ? <AskIt agent={agent} /> : null}
      {tab === "role" ? <AgentEditor agent={agent} onSaved={() => show("ask")} /> : null}
      {tab === "prompt" ? <WhatItGets data={data} /> : null}
      {tab === "elsewhere" ? <Elsewhere agent={agent} /> : null}
      {tab === "history" ? <AgentHistory name={agent.name} /> : null}
    </div>
  );
}

function AskIt({ agent }: { agent: WorkAgent }) {
  const ask = useAskWorkAgent();
  const { data: runs } = useWorkAgentRuns(agent.name);
  const { data: projects } = useBrainProjects();
  const [text, setText] = useState("");
  const [project, setProject] = useState(agent.projects[0] ?? "");
  const [task, setTask] = useState<Task | null>(null);
  return (
    <div className="stack">
      <section className="skill-panel" aria-label="Ask it">
        <Field label={`What do you need from ${agent.name}?`}>
          <textarea rows={3} value={text} onChange={(event) => setText(event.target.value)} />
        </Field>
        <Field label="For a project (optional)">
          <select value={project} onChange={(event) => setProject(event.target.value)}>
            <option value="">No project</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </Field>
        <div className="row">
          <button
            type="button"
            className="primary"
            disabled={!text.trim() || ask.isPending || agent.status === "archived"}
            onClick={() =>
              ask.mutate(
                { name: agent.name, ask: text.trim(), project: project || undefined },
                {
                  onSuccess: (made) => {
                    setTask(made);
                    setText("");
                  },
                },
              )
            }
          >
            {ask.isPending ? "Asking…" : "Ask"}
          </button>
        </div>
        <ErrorNote error={ask.error} />
        {task ? <Working key={task.id} task={task} waiting="It waits for a model: run it here, or paste the prompt into a connected AI." /> : null}
      </section>
      <Section title="What it made">
        {runs?.length ? (
          <ol className="skill-runs">
            {runs.map((run) => (
              <li key={run.task_id} className="skill-run">
                <RunCard run={run} showSkills />
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted small">Nothing yet. Ask it for something above.</p>
        )}
      </Section>
    </div>
  );
}

function WhatItGets({ data }: { data: WorkAgentFull }) {
  const { resolved } = data;
  return (
    <div className="entry-layout">
      <div className="stack">
        <p className="muted small">
          The role as a model gets it now, with every pointer resolved to its current version. On a run, the Brain's brief for the task
          and the task itself follow it.
        </p>
        <CopyBlock text={data.prompt} label="What it gets" />
      </div>
      <aside className="entry-side">
        <Section title="Points to">
          <ul className="list">
            {resolved.skills.map((s) => (
              <li key={s.name} className={s.missing ? "missing" : undefined}>
                {s.missing ? `/${s.name} (not found)` : <Link to={skillUrl(s.name)}>/{s.name}</Link>}
              </li>
            ))}
            {resolved.library.map((d) => (
              <li key={d.path} className={d.missing ? "missing" : undefined}>
                {d.missing ? `${d.path} (not found)` : <Link to={libraryItemUrl(d.path)}>{d.title}</Link>}
              </li>
            ))}
            {resolved.projects.map((p) => (
              <li key={p.id} className={p.missing ? "missing" : undefined}>
                {p.missing ? `${p.id} (not found)` : <Link to={`/projects/${encodeURIComponent(p.id)}`}>{p.title}</Link>}
              </li>
            ))}
            {resolved.context.map((c) => (
              <li key={c.key} className={c.missing ? "missing" : undefined}>
                {c.key}
                {c.missing ? " (not found)" : ""}
              </li>
            ))}
          </ul>
        </Section>
      </aside>
    </div>
  );
}

function Elsewhere({ agent }: { agent: WorkAgent }) {
  const add = useAddAgentToClaudeCode();
  const archive = useArchiveWorkAgent();
  const navigate = useNavigate();
  return (
    <div className="stack">
      <Section title="In any AI you connect">
        <p>
          Say “work as {agent.name}” in Claude, Codex, Cursor or any AI connected to your Brain. It calls <code>get_agent</code> and gets the
          current role, with what it points to as each is now.
        </p>
      </Section>
      <Section title="In Claude Code, as a subagent">
        <p>
          Adds <code>~/.claude/agents/{agent.name}.md</code> on this computer. The file holds no copy of the role: it tells Claude Code to fetch
          it from your Brain, so it always works from the current version.
        </p>
        <button type="button" disabled={add.isPending} onClick={() => add.mutate(agent.name)}>
          {add.isPending ? "Adding…" : "Add to Claude Code"}
        </button>
        {add.data ? (
          <p className="notice small" role="status">
            {add.data.replaced ? "Updated" : "Added"} {add.data.path}.
          </p>
        ) : null}
        <ErrorNote error={add.error} />
      </Section>
      {agent.status !== "archived" ? (
        <Section title="Archive it">
          <p className="muted small">It leaves your team; its file and every version stay in the Brain, and the undo point can bring it back.</p>
          <button type="button" disabled={archive.isPending} onClick={() => archive.mutate(agent.name, { onSuccess: () => navigate("/work/agents") })}>
            Archive {agent.name}
          </button>
          <ErrorNote error={archive.error} />
        </Section>
      ) : null}
    </div>
  );
}

function AgentHistory({ name }: { name: string }) {
  const { data: versions, isLoading, error } = useWorkAgentVersions(name);
  if (isLoading) return <Loading />;
  if (!versions) return <ErrorNote error={error} />;
  return (
    <Section title="Every saved version">
      <ol className="list">
        {versions.map((v) => (
          <li key={v.ref}>
            <strong>{v.current ? "Now" : v.ref}</strong> <span className="muted small">{when(v.at)}</span>
            {v.message ? <span className="small"> · {v.message}</span> : null}
          </li>
        ))}
      </ol>
    </Section>
  );
}

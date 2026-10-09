// Beside a Workspace doc: the projects it is linked to (a link, never a copy; it stays yours),
// and AI only when you ask: draft from it with a skill or an agent ("I outline, you write"), push
// back on it (questions, nothing written for you), or continue it. What a run made shows here;
// take it as the doc's next version, add it at the end, keep it as a new doc, or leave it.

import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { docExportUrl, useBrainProjects, useDocAction, useDocRuns, useLinkDocProjects, useSkills, useUseDocResult, useWorkAgents } from "../../api/hooks";
import type { Note, SkillRun, Task } from "../../api/types";
import { when } from "../../lib/format";
import { docUrl } from "../../lib/links";
import { Markdown } from "../Markdown";
import { Working } from "../RunNow";
import { ErrorNote, Field, Pill } from "../ui";
import { PickMany } from "./PickMany";

const GOING = ["draft", "ready", "claimed", "in_progress"];

export function DocProjects({ note }: { note: Note }) {
  const { data: projects } = useBrainProjects();
  const link = useLinkDocProjects();
  return (
    <section className="side-part" aria-label="Projects">
      <h3>Projects</h3>
      <PickMany
        label="Linked to"
        empty="No project"
        options={(projects ?? []).map((p) => ({ value: p.id, label: p.title, hint: p.active ? "" : "paused or finished" }))}
        value={note.projects ?? []}
        onChange={(next) => link.mutate({ id: note.id, projects: next })}
        max={10}
        hint="Shows on each project's page. A link, never a copy: it stays yours until you share it."
      />
      <ErrorNote error={link.error} />
    </section>
  );
}

export function DocWithAi({ note, beforeAsk }: { note: Note; beforeAsk: () => Promise<boolean> }) {
  const action = useDocAction();
  const { data: skills } = useSkills();
  const { data: agents } = useWorkAgents();
  const [by, setBy] = useState("");
  const [ask, setAsk] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const runnable = (skills?.skills ?? []).filter((s) => s.use === "run");
  const go = (input: Parameters<typeof action.mutate>[0]) =>
    void beforeAsk().then(() => action.mutate(input, { onSuccess: (made) => setTask(made) }));
  const [kind, name] = by.split(":");
  return (
    <section className="side-part" aria-label="With AI">
      <h3>With AI, when you ask</h3>
      <p className="muted small">Nothing here runs on its own. Each run reads this doc as it is when you ask.</p>
      <Field label="Draft from this with">
        <select value={by} onChange={(event) => setBy(event.target.value)}>
          <option value="">Choose a skill or an agent</option>
          {(agents ?? []).length ? (
            <optgroup label="Agents">
              {(agents ?? []).map((a) => (
                <option key={a.name} value={`agent:${a.name}`}>
                  {a.name}
                </option>
              ))}
            </optgroup>
          ) : null}
          {runnable.length ? (
            <optgroup label="Skills">
              {runnable.map((s) => (
                <option key={s.name} value={`skill:${s.name}`}>
                  /{s.name}
                </option>
              ))}
            </optgroup>
          ) : null}
        </select>
      </Field>
      <Field label="What you want (optional)">
        <input value={ask} placeholder="For example: a LinkedIn post from this outline" onChange={(event) => setAsk(event.target.value)} />
      </Field>
      <div className="row">
        <button
          type="button"
          className="primary"
          disabled={!by || action.isPending}
          onClick={() => go({ id: note.id, action: "draft", skill: kind === "skill" ? name : undefined, agent: kind === "agent" ? name : undefined, ask })}
        >
          Draft from this
        </button>
        <button type="button" disabled={action.isPending} onClick={() => go({ id: note.id, action: "push-back" })} title="Questions and challenges; nothing written for you">
          Push back
        </button>
        <button type="button" disabled={action.isPending} onClick={() => go({ id: note.id, action: "continue" })}>
          Continue
        </button>
      </div>
      <ErrorNote error={action.error} />
      {task ? <Working key={task.id} task={task} waiting="It waits for a model: run it here, or paste the prompt into a connected AI." /> : null}
      <DocRuns note={note} />
      <p className="small">
        <Link to={`/work/compose?doc=${encodeURIComponent(note.id)}`}>Open in Compose</Link>: more skills, documents and the whole prompt.
      </p>
      <p className="small">
        Take it with you:{" "}
        <a href={docExportUrl(note.id, "md")} download>
          Markdown
        </a>{" "}
        ·{" "}
        <a href={docExportUrl(note.id, "docx")} download>
          Word
        </a>
      </p>
    </section>
  );
}

function DocRuns({ note }: { note: Note }) {
  const { data: runs } = useDocRuns(note.id);
  if (!runs?.length) return null;
  return (
    <ol className="doc-runs" aria-label="What AI made from it">
      {runs.slice(0, 6).map((run) => (
        <li key={run.task_id}>
          <DocRun note={note} run={run} />
        </li>
      ))}
    </ol>
  );
}

function DocRun({ note, run }: { note: Note; run: SkillRun }) {
  const use = useUseDocResult();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const who = run.agent ?? (run.skill ? `/${run.skill}` : run.ask);
  const critic = run.doc_action === "push-back";
  const adds = run.doc_action === "continue";
  return (
    <article className="doc-run">
      <header className="row small">
        <Pill status={run.status} />
        <span>{who}</span>
        <span className="muted">{when(run.created_at)}</span>
      </header>
      {run.result ? (
        <>
          <button type="button" className="link small" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Read"} “{run.result.title}”
          </button>
          {open ? (
            <div className="document small">
              <Markdown text={run.result.text} />
            </div>
          ) : null}
          {!critic ? (
            <div className="row small">
              {adds ? (
                <button type="button" disabled={use.isPending} onClick={() => use.mutate({ id: note.id, taskId: run.task_id, how: "append" })}>
                  Add it at the end
                </button>
              ) : (
                <button type="button" disabled={use.isPending} onClick={() => use.mutate({ id: note.id, taskId: run.task_id, how: "version" })}>
                  Use as the next version
                </button>
              )}
              <button
                type="button"
                disabled={use.isPending}
                onClick={() =>
                  use.mutate(
                    { id: note.id, taskId: run.task_id, how: "new" },
                    { onSuccess: (made) => navigate(docUrl(made.id)) },
                  )
                }
              >
                Keep as a new doc
              </button>
            </div>
          ) : null}
          {use.isSuccess ? <p className="muted small">Done. Every earlier version is kept under Versions.</p> : null}
          <ErrorNote error={use.error} />
        </>
      ) : GOING.includes(run.status) ? (
        <p className="muted small">Your AI is working on it.</p>
      ) : (
        <p className="muted small">It finished without a result.</p>
      )}
    </article>
  );
}

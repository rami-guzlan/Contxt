// Working with a skill: run it for what you need and see what it made (text to copy, save or
// file in a project; files to download), ask your AI to improve it or write a new one (both
// wait in Review), edit it yourself, and look back at its versions. Several skills at once
// (followed in order, or the Brain picks) run from a prompt in Knowledge Work.

import { useState } from "react";
import { Link } from "react-router";

import { post } from "../api/client";
import {
  keys,
  skillFileUrl,
  useBrainFiles,
  useBrainProjects,
  useCreateNote,
  useDraftSkill,
  useEditSkill,
  useFileInBrain,
  useImproveSkill,
  useInvalidate,
  useLatestSkillRuns,
  useNotes,
  useRecentRuns,
  useRunSkill,
  useSkillRuns,
  useSkillVersions,
} from "../api/hooks";
import type { BrainCheckpoint, SkillRun, SkillVersion, Task } from "../api/types";
import { bytes, when } from "../lib/format";
import { Compare } from "./Diff";
import { Markdown } from "./Markdown";
import { RunButtons, RunConsole, RunnerNote, Working } from "./RunNow";
import { ErrorNote, Field, Loading, Pill } from "./ui";

const WAITING = ["draft", "ready"];
const WORKING = ["claimed", "in_progress"];
const STOPPED = ["failed", "blocked", "cancelled"];

const FORMATS = /^(pdf|docx|pptx|xlsx|png|jpe?g|svg|gif|html|csv|zip|mp4)$/i;
// What is made as a file on this computer (as the server decides it, services/skills.py).
const FILE_KINDS = /^(pdf|docx|pptx|xlsx|image|png|jpe?g|svg|gif|html|csv|zip|video|mp4)$/i;

function listed(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}` : (items[0] ?? "");
}

/** What a skill makes, said the way a person would: "Makes PDF and DOCX files", "Writes a
 * post", "Makes image files and writes a post". */
export function makesLine(artifacts: string[], makesFiles: boolean): string {
  const kinds = artifacts.map((a) => a.trim()).filter(Boolean);
  const files = makesFiles ? kinds.filter((kind) => FILE_KINDS.test(kind)) : [];
  const texts = kinds.filter((kind) => !files.includes(kind));
  const writes = texts.length > 1 ? `writes: ${texts.join(", ")}` : texts[0] ? `writes ${/^[aeiou]/i.test(texts[0]) ? "an" : "a"} ${texts[0]}` : "";
  if (!files.length) return writes ? writes[0]?.toUpperCase() + writes.slice(1) : "";
  const made = `Makes ${listed(files.map((kind) => (FORMATS.test(kind) ? kind.toUpperCase() : kind)))} files`;
  return writes ? `${made} and ${writes}` : made;
}

// ---------------------------------------------------------------- run it

/** Say what you need, optionally with something you brought in, a project and files, and run. */
export function RunSkill({ name, triggers, makesFiles }: { name: string; triggers: string[]; makesFiles: boolean }) {
  const run = useRunSkill();
  const [ask, setAsk] = useState("");
  const [capture, setCapture] = useState("");
  const [project, setProject] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [task, setTask] = useState<Task | null>(null);
  const example = triggers[0] ? `For example: ${triggers[0]}` : "What should it make?";
  async function go() {
    setTask(null);
    const made = await run.mutateAsync({
      name,
      ask: ask.trim(),
      capture_id: capture || undefined,
      project: project || undefined,
      files: files.length ? files : undefined,
    });
    setTask(made);
    setAsk("");
  }
  return (
    <section className="skill-panel" aria-label="Run it" data-tour="skill-run">
      <Field label="What do you need?">
        <textarea rows={3} value={ask} placeholder={example} onChange={(event) => setAsk(event.target.value)} />
      </Field>
      <div className="skill-inputs">
        <CapturePicker value={capture} onChange={setCapture} />
        <ProjectPicker value={project} onChange={setProject} label="For a project (optional)" />
        <FilePicker value={files} onChange={setFiles} />
      </div>
      {makesFiles ? (
        <p className="muted small">
          It makes files, so it works in a folder of its own under your outputs folder, with file and Python tools and no web. You
          download what it makes here.
        </p>
      ) : null}
      <div className="row">
        <button type="button" className="primary" disabled={!ask.trim() || run.isPending} onClick={() => void go().catch(() => undefined)}>
          {run.isPending ? "Asking…" : "Run"}
        </button>
        <Link className="small" to={`/work/prompts/new?skill=${encodeURIComponent(name)}${ask.trim() ? `&ask=${encodeURIComponent(ask.trim())}` : ""}`}>
          More picks, and the whole prompt
        </Link>
      </div>
      <ErrorNote error={run.error} />
      {task ? <Working key={task.id} task={task} waiting="It waits for a model: run it here, or paste the prompt into a connected AI." /> : null}
    </section>
  );
}

/** The latest runs from here and from every skill, each with what came of it. */
export function LatestRuns({ limit = 5 }: { limit?: number }) {
  const { data: runs } = useLatestSkillRuns(limit);
  if (!runs?.length) return null;
  return (
    <section className="latest-runs" aria-label="Latest runs">
      <h2>Latest runs</h2>
      <ol className="skill-runs">
        {runs.map((run) => (
          <li key={run.task_id} className="skill-run">
            <RunCard run={run} showSkills />
          </li>
        ))}
      </ol>
    </section>
  );
}

function CapturePicker({
  value,
  onChange,
  label: text = "Use something you brought in (optional)",
}: {
  value: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  const { data: notes } = useNotes();
  const usable = (notes ?? []).filter((n) => !n.transcription || n.transcription.state === "ready").slice(0, 40);
  if (!usable.length) return null;
  return (
    <Field label={text}>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Nothing</option>
        {usable.map((note) => (
          <option key={note.id} value={note.id}>
            {note.title}
          </option>
        ))}
      </select>
    </Field>
  );
}

function ProjectPicker({ value, onChange, label: text }: { value: string; onChange: (id: string) => void; label: string }) {
  const { data: projects } = useBrainProjects();
  const active = (projects ?? []).filter((p) => p.active);
  if (!active.length) return null;
  return (
    <Field label={text}>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">None</option>
        {active.map((project) => (
          <option key={project.id} value={project.id}>
            {project.title}
          </option>
        ))}
      </select>
    </Field>
  );
}

function FilePicker({ value, onChange }: { value: string[]; onChange: (paths: string[]) => void }) {
  const { data: files } = useBrainFiles();
  const documents = files?.references ?? [];
  if (!documents.length) return null;
  const left = documents.filter((d) => !value.includes(d.path));
  return (
    <Field label="Files from your Brain (optional)">
      <div className="stack-tight">
        {value.length ? (
          <ul className="chips">
            {value.map((path) => (
              <li key={path} className="chip">
                {documents.find((d) => d.path === path)?.title ?? path}{" "}
                <button type="button" className="link" aria-label={`Leave out ${path}`} onClick={() => onChange(value.filter((p) => p !== path))}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {value.length < 5 ? (
          <select
            aria-label="Add a file"
            value=""
            onChange={(event) => event.target.value && onChange([...value, event.target.value])}
          >
            <option value="">Add a file…</option>
            {left.map((document) => (
              <option key={document.path} value={document.path}>
                {document.title}
              </option>
            ))}
          </select>
        ) : null}
      </div>
    </Field>
  );
}

// ---------------------------------------------------------------- what came of it

/** The skill's runs and drafts, newest first, each with what came of it. */
export function SkillRuns({ name, kind }: { name: string; kind: SkillRun["kind"] }) {
  const { data: runs, isLoading, error } = useSkillRuns(name);
  if (isLoading) return <Loading />;
  if (!runs) return <ErrorNote error={error} />;
  const mine = runs.filter((r) => r.kind === kind);
  if (!mine.length)
    return (
      <p className="muted small">
        {kind === "run" ? "No runs yet: what it makes shows here." : "No improvements asked for yet."}
      </p>
    );
  return (
    <ol className="skill-runs">
      {mine.map((run) => (
        <li key={run.task_id} className="skill-run">
          <RunCard run={run} />
        </li>
      ))}
    </ol>
  );
}

export function RunCard({ run, showSkills = false }: { run: SkillRun; showSkills?: boolean }) {
  // A run started on this computer a moment ago may not have claimed its task yet.
  const { data: live } = useRecentRuns();
  const starting = !!live?.some((r) => r.task_id === run.task_id && ["starting", "running"].includes(r.status));
  const waiting = WAITING.includes(run.status) && !starting;
  const working = WORKING.includes(run.status) || (WAITING.includes(run.status) && starting);
  const going = waiting || working;
  const followed = run.skills ?? (run.skill ? [run.skill] : []);
  return (
    <article aria-label={`Asked ${when(run.created_at)}`}>
      <header className="skill-run-head">
        <Pill status={run.status} />
        <span className="muted small">{when(run.created_at)}</span>
        {run.agent ? (
          <Link className="small" to={`/work/agents/${encodeURIComponent(run.agent)}`}>
            Asked {run.agent}
          </Link>
        ) : null}
        {(showSkills || followed.length > 1) && !(run.agent && !followed.length) ? (
          <span className="small">
            {followed.length
              ? followed.map((name, i) => (
                  <span key={name}>
                    {i ? " then " : ""}
                    <Link to={`/work/skills/${encodeURIComponent(name)}`}>/{name}</Link>
                  </span>
                ))
              : "The skill that fit"}
          </span>
        ) : null}
        {run.capture ? (
          <Link className="small" to={`/capture/${encodeURIComponent(run.capture.id)}`}>
            {run.capture.title}
          </Link>
        ) : null}
        {run.project ? (
          <Link className="small" to={`/projects/${encodeURIComponent(run.project.id)}`}>
            {run.project.title}
          </Link>
        ) : null}
      </header>
      <blockquote className="skill-ask">{run.ask}</blockquote>
      {waiting && !run.result ? <NotStarted run={run} /> : null}
      {working && !run.result ? (
        <p className="muted small" role="status">
          Your AI is working on it.
        </p>
      ) : null}
      {STOPPED.includes(run.status) && !run.result && !run.proposal ? <Again run={run} /> : null}
      {run.result ? <Result result={run.result} project={run.project?.id} skill={run.skill} /> : null}
      {run.files.length ? <MadeFiles run={run} /> : null}
      {run.kind === "improve" && run.proposal?.status === "waiting" ? (
        <p className="small">
          It proposed a new version. <Link to="/review">See it in Review</Link>: nothing changes until you approve it.
        </p>
      ) : null}
      {run.kind === "improve" && run.proposal?.status === "approved" ? (
        <p className="small">
          Its new version was approved and is in use. <Link to={`/work/skills/${encodeURIComponent(run.skill)}?tab=history`}>See its history</Link>.
        </p>
      ) : null}
      {run.kind === "improve" && run.proposal?.status === "rejected" ? (
        <p className="muted small">Its new version was turned down.</p>
      ) : null}
      {!going && run.kind === "run" && !run.result && !run.files.length ? (
        <p className="muted small">It finished without saving a result.</p>
      ) : null}
    </article>
  );
}

/** Asked for but not started: run it here now, or paste its prompt into a connected AI. */
function NotStarted({ run }: { run: SkillRun }) {
  const [runId, setRunId] = useState<string | null>(null);
  if (runId) return <RunConsole runId={runId} />;
  return (
    <div className="stack">
      <p className="muted small" role="status">
        It hasn't started yet.
      </p>
      <RunButtons task={{ id: run.task_id, status: run.status, assignee_id: run.assignee_id }} onStarted={setRunId} />
      <RunnerNote />
    </div>
  );
}

/** It stopped before it finished (the app closed, a time limit): ask again with the same inputs. */
function Again({ run }: { run: SkillRun }) {
  const rerun = useRunSkill();
  const improve = useImproveSkill();
  const [task, setTask] = useState<Task | null>(null);
  const busy = rerun.isPending || improve.isPending;
  if (task) return <Working key={task.id} task={task} waiting="It waits for a model: run it here, or paste the prompt into a connected AI." />;
  function retry() {
    const done = { onSuccess: (made: Task) => setTask(made) };
    if (run.kind === "improve") improve.mutate({ name: run.skill, ask: run.ask }, done);
    else
      rerun.mutate(
        {
          name: run.skill,
          ask: run.ask,
          capture_id: run.capture?.id,
          project: run.project?.id,
          files: run.attached.length ? run.attached : undefined,
        },
        done,
      );
  }
  return (
    <div className="row small">
      <span className="muted">It stopped before it finished.</span>
      <button type="button" disabled={busy} onClick={retry}>
        Try again
      </button>
      <ErrorNote error={rerun.error ?? improve.error} />
    </div>
  );
}

function Result({ result, project, skill }: { result: NonNullable<SkillRun["result"]>; project?: string; skill: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(result.text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="skill-result">
      <div className="document compact">
        <Markdown text={result.text} />
      </div>
      <div className="row small">
        <button type="button" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy"}
        </button>
        <SaveAsNote title={result.title} text={result.text} />
        <FileInProject
          title={result.title}
          initial={project}
          file={() => new File([result.text], `${slug(result.title) || "result"}.md`, { type: "text/markdown" })}
        />
        {skill ? (
          <Link className="button" to={`/work/skills/${encodeURIComponent(skill)}?tab=improve&example=${encodeURIComponent(result.artifact_id)}`}>
            Teach the skill from this
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function SaveAsNote({ title, text }: { title: string; text: string }) {
  const create = useCreateNote();
  if (create.data)
    return (
      <span className="small">
        Kept: <Link to={`/work/workspace/${encodeURIComponent(create.data.id)}`}>open the doc</Link>
      </span>
    );
  return (
    <>
      <button type="button" disabled={create.isPending} onClick={() => create.mutate({ title, body: text })} title="A doc in your Workspace, to keep working on">
        Keep as a doc
      </button>
      <ErrorNote error={create.error} />
    </>
  );
}

/** Files what was made in one of the Brain's projects, as a document it keeps. */
function FileInProject({ title, file, initial }: { title: string; file: () => File | Promise<File>; initial?: string }) {
  const { data: projects } = useBrainProjects();
  const filing = useFileInBrain();
  const [open, setOpen] = useState(false);
  const [project, setProject] = useState(initial ?? "");
  const [error, setError] = useState<unknown>(null);
  const active = (projects ?? []).filter((p) => p.active);
  if (!active.length) return null;
  const chosen = active.find((p) => p.id === project);
  if (filing.data && chosen)
    return (
      <span className="small">
        Filed in <Link to={`/projects/${encodeURIComponent(chosen.id)}`}>{chosen.title}</Link>
        {filing.data.status === "pending" ? ", waiting in Review" : ""}.
      </span>
    );
  if (!open)
    return (
      <button type="button" onClick={() => setOpen(true)}>
        File in a project
      </button>
    );
  async function go() {
    setError(null);
    try {
      filing.mutate({ file: await file(), title, project });
    } catch (caught) {
      setError(caught);
    }
  }
  return (
    <span className="row small">
      <select aria-label="Project to file it in" value={project} onChange={(event) => setProject(event.target.value)}>
        <option value="">Choose a project</option>
        {active.map((p) => (
          <option key={p.id} value={p.id}>
            {p.title}
          </option>
        ))}
      </select>
      <button type="button" className="primary" disabled={!project || filing.isPending} onClick={() => void go()}>
        File it
      </button>
      <ErrorNote error={filing.error ?? error} />
    </span>
  );
}

/** Pictures a run made, shown in place (the server shows nothing else in place). */
const PICTURE = /\.(png|jpe?g|gif|webp)$/i;

function MadeFiles({ run }: { run: SkillRun }) {
  const [copied, setCopied] = useState(false);
  const pictures = run.files.filter((file) => PICTURE.test(file.name)).slice(0, 6);
  return (
    <div className="made-files">
      <h4>What it made</h4>
      {pictures.length ? (
        <div className="made-previews">
          {pictures.map((file) => (
            <a key={file.name} href={skillFileUrl(run.task_id, file.name)} download title={`Download ${file.name}`}>
              <img src={skillFileUrl(run.task_id, file.name, false)} alt={file.name} loading="lazy" />
            </a>
          ))}
        </div>
      ) : null}
      <ul className="list">
        {run.files.map((file) => (
          <li key={file.name} className="file-line">
            <a href={skillFileUrl(run.task_id, file.name)} download>
              {file.name}
            </a>
            <span className="muted"> · {bytes(file.size)} </span>
            <FileInProject
              title={file.name}
              initial={run.project?.id}
              file={async () => {
                const response = await fetch(skillFileUrl(run.task_id, file.name), { credentials: "same-origin" });
                if (!response.ok) throw new Error(`Could not read ${file.name}.`);
                return new File([await response.blob()], file.name.split("/").pop() ?? file.name);
              }}
            />
          </li>
        ))}
      </ul>
      {run.folder ? (
        <p className="muted small">
          In <code>{run.folder}</code>{" "}
          <button
            type="button"
            className="link"
            onClick={() => void navigator.clipboard?.writeText(run.folder ?? "").then(() => setCopied(true), () => undefined)}
          >
            {copied ? "Copied" : "Copy the folder's path"}
          </button>
        </p>
      ) : null}
    </div>
  );
}

function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

// ---------------------------------------------------------------- make it better

/** Say what should change, optionally with an example to learn from (something it made that
 * you liked, or a copy you edited); your AI drafts the new version and it waits in Review. */
export function ImproveSkill({ name, example, onClearExample }: { name: string; example?: string | null; onClearExample?: () => void }) {
  const improve = useImproveSkill();
  const { data: runs } = useSkillRuns(name);
  const shown = example ? runs?.find((r) => r.result?.artifact_id === example)?.result : null;
  const [ask, setAsk] = useState(example ? "Make what it makes come out like this example." : "");
  const [capture, setCapture] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  return (
    <section className="skill-panel" aria-label="Improve it">
      {example ? (
        <p className="small">
          Learning from what it made: <strong>{shown?.title ?? "a result"}</strong>
          {shown ? ` (${when(shown.at)})` : ""}.{" "}
          {onClearExample ? (
            <button type="button" className="link" onClick={onClearExample}>
              Leave it out
            </button>
          ) : null}
        </p>
      ) : null}
      <Field label="What should change?" hint="Your AI writes the new version; it waits in Review, beside the version it replaces.">
        <textarea
          rows={3}
          value={ask}
          placeholder="For example: make the hook shorter, and add the UTM step"
          onChange={(event) => setAsk(event.target.value)}
        />
      </Field>
      <div className="skill-inputs">
        <CapturePicker value={capture} onChange={setCapture} label="An example you brought in or wrote (optional)" />
      </div>
      <div className="row">
        <button
          type="button"
          className="primary"
          disabled={!ask.trim() || improve.isPending}
          onClick={() =>
            improve.mutate(
              { name, ask: ask.trim(), capture_id: capture || undefined, example: example || undefined },
              {
                onSuccess: (made) => {
                  setTask(made);
                  setAsk("");
                },
              },
            )
          }
        >
          Improve it
        </button>
      </div>
      <ErrorNote error={improve.error} />
      {task ? <Working key={task.id} task={task} waiting="It waits for a model to draft the new version." /> : null}
    </section>
  );
}

/** Describe a skill (or teach one from something you brought in); your AI drafts it for Review. */
export function NewSkill({
  capture,
  initial = "",
  onClose,
}: {
  capture?: { id: string; title: string } | null;
  /** Words to start from: a saved prompt made into a skill, say. */
  initial?: string;
  onClose?: () => void;
}) {
  const draft = useDraftSkill();
  const [ask, setAsk] = useState(initial);
  const [task, setTask] = useState<Task | null>(null);
  return (
    <section className="skill-panel new-skill" aria-label="New skill">
      <h2>New skill</h2>
      <p className="muted small">
        Say what it should make and how. Your AI writes it from your Brain's rules and voice, in the shape of your other skills; it
        waits in Review until you approve it.
      </p>
      {capture ? (
        <p className="small">
          Teaching from <Link to={`/capture/${encodeURIComponent(capture.id)}`}>{capture.title}</Link>.
        </p>
      ) : null}
      <Field label="What should it do?">
        <textarea
          rows={3}
          value={ask}
          placeholder="For example: turn a podcast transcript into three LinkedIn posts with a hook, a takeaway and a question"
          onChange={(event) => setAsk(event.target.value)}
        />
      </Field>
      <div className="row">
        <button
          type="button"
          className="primary"
          disabled={!ask.trim() || draft.isPending}
          onClick={() =>
            draft.mutate(
              { ask: ask.trim(), capture_id: capture?.id },
              {
                onSuccess: (made) => {
                  setTask(made);
                  setAsk("");
                },
              },
            )
          }
        >
          Write it
        </button>
        {onClose ? (
          <button type="button" onClick={onClose}>
            Close
          </button>
        ) : null}
      </div>
      <ErrorNote error={draft.error} />
      {task ? (
        <>
          <Working key={task.id} task={task} waiting="It waits for a model to write it." />
          <p className="small">
            When it's written, it waits in <Link to="/review">Review</Link>.
          </p>
        </>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------- edit it yourself

interface SkillText {
  name: string;
  description: string;
  when_to_use: string;
  triggers: string[];
  body: string;
}

/** Your own new version of a skill: it applies at once, and Undo takes it back. `saved` is the
 * skill's words to ask for it as they are now, when the editor opens with others added. */
export function SkillEditor({
  skill,
  saved: savedTriggers,
  onDone,
}: {
  skill: SkillText;
  saved?: string[];
  onDone: (checkpoint: BrainCheckpoint | null) => void;
}) {
  const edit = useEditSkill();
  const [description, setDescription] = useState(skill.description);
  const [whenToUse, setWhenToUse] = useState(skill.when_to_use);
  const [triggers, setTriggers] = useState(skill.triggers.join("\n"));
  const [body, setBody] = useState(skill.body);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState(false);
  function save() {
    edit.mutate(
      {
        name: skill.name,
        body,
        description: description.trim() !== skill.description ? description.trim() : undefined,
        when_to_use: whenToUse.trim() !== skill.when_to_use ? whenToUse.trim() : undefined,
        triggers: triggers.trim() !== (savedTriggers ?? skill.triggers).join("\n")
          ? triggers.split("\n").map((t) => t.trim()).filter(Boolean)
          : undefined,
        reason: reason.trim() || undefined,
      },
      { onSuccess: (done) => onDone(done.checkpoint) },
    );
  }
  return (
    <section className="skill-panel" aria-label="Edit the skill">
      <Field label="What it does" hint="Your AI reads this to decide when to use it.">
        <textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
      </Field>
      <Field label="When to use it">
        <input value={whenToUse} onChange={(event) => setWhenToUse(event.target.value)} />
      </Field>
      <Field label="What you say to ask for it" hint="One phrase per line.">
        <textarea rows={3} value={triggers} onChange={(event) => setTriggers(event.target.value)} />
      </Field>
      <div className="editor-tabs" role="tablist" aria-label="Write or preview">
        <button type="button" role="tab" aria-selected={!preview} className={preview ? "tab" : "tab active"} onClick={() => setPreview(false)}>
          Write
        </button>
        <button type="button" role="tab" aria-selected={preview} className={preview ? "tab active" : "tab"} onClick={() => setPreview(true)}>
          Preview
        </button>
      </div>
      {preview ? (
        <div className="document compact">
          <Markdown text={body} />
        </div>
      ) : (
        <textarea
          aria-label="The steps"
          className="code-input"
          rows={Math.min(30, Math.max(10, body.split("\n").length + 2))}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      )}
      <Field label="Why (optional)">
        <input value={reason} placeholder="What you changed, for its history" onChange={(event) => setReason(event.target.value)} />
      </Field>
      <div className="row">
        <button type="button" className="primary" disabled={!body.trim() || edit.isPending} onClick={save}>
          Save this version
        </button>
        <button type="button" onClick={() => onDone(null)}>
          Cancel
        </button>
      </div>
      <ErrorNote error={edit.error} />
    </section>
  );
}

/** "Saved" with the undo point a change made. */
export function Saved({ checkpoint, onUndone }: { checkpoint: BrainCheckpoint; onUndone: () => void }) {
  const invalidate = useInvalidate();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function undo() {
    setBusy(true);
    setError(null);
    try {
      await post(`/api/brain/checkpoints/${encodeURIComponent(checkpoint.id)}/undo`);
      await invalidate(keys.skills, keys.brain, keys.events);
      onUndone();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  return (
    <p className="notice small" role="status">
      Saved: every AI you connect uses this version now.{" "}
      <button type="button" className="link" disabled={busy} onClick={() => void undo()}>
        Undo
      </button>
      <ErrorNote error={error} />
    </p>
  );
}

// ---------------------------------------------------------------- its versions

/** Every version of the skill, newest first; pick one to see how it differs from now. */
export function SkillHistory({ name, onRestore }: { name: string; onRestore: (version: SkillVersion) => void }) {
  const { data: versions, isLoading, error } = useSkillVersions(name, true);
  const [chosen, setChosen] = useState<string | null>(null);
  if (isLoading) return <Loading />;
  if (!versions) return <ErrorNote error={error} />;
  const current = versions.find((v) => v.current) ?? versions[0];
  const picked = versions.find((v) => v.ref === chosen);
  if (versions.length < 2)
    return <p className="muted small">This is its first version. Each change you or your AI make is kept here.</p>;
  return (
    <div className="stack">
      <ol className="version-list">
        {versions.map((version) => (
          <li key={version.ref} className={version.ref === chosen ? "version active" : "version"}>
            <button
              type="button"
              className="version-pick"
              aria-pressed={version.ref === chosen}
              disabled={version.ref === current?.ref}
              onClick={() => setChosen(version.ref === chosen ? null : version.ref)}
            >
              <span>{when(version.at)}</span>
              <span className="muted small">
                {version.current ? "Now" : version.message || "A change"}
                {version.author ? ` · ${version.author}` : ""}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {picked && current && picked.ref !== current.ref ? (
        <>
          <Compare
            before={{ label: `Version of ${when(picked.at)}`, title: `/${name}`, body: picked.body ?? "" }}
            after={{ label: "Now", title: `/${name}`, body: current.body ?? "" }}
          />
          <div className="row">
            <button type="button" onClick={() => onRestore(picked)}>
              Use this version again
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}


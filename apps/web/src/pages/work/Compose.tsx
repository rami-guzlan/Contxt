// Knowledge Work, running a prompt: the panel a prompt's page opens when you want to run it or
// see what a model gets. Pick what goes with the words (skills in order, an agent, your notes,
// documents to read whole, a project), and the whole prompt sits beside them, exactly as a model
// gets it, with its size. Then improve the words, run it here, or copy it for any AI. Running is
// secondary: Prompts keeps your words; this is one thing you can do with them. The old Compose
// address sends its links (?skill=, ?agent=, ?doc=, ?project=, ?ask=) to a new prompt with this
// panel open.

import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation } from "react-router";

import {
  useAssembled,
  useBrainFiles,
  useBrainProjects,
  useComposeRun,
  useImprovePrompt,
  useNotes,
  useSkills,
  useWorkAgents,
  useWorkJob,
} from "../../api/hooks";
import type { ComposePicks, ComposeSpec, SavedPrompt, Task } from "../../api/types";
import { CAPTURE_NAMES } from "../../components/CaptureParts";
import { Compare } from "../../components/Diff";
import { Working } from "../../components/RunNow";
import { CopyBlock, ErrorNote, Field, Loading, Tabs } from "../../components/ui";
import { PickMany } from "../../components/work/PickMany";
import { SKILLS } from "../../lib/links";

const SETTLE_MS = 500; // a pause this long in typing or picking refreshes the whole prompt
export const NO_PICKS: ComposePicks = { skills: [], agent: null, docs: [], library: [], project: null };
const WORKING = ["waiting", "running"];

/** Picks from a link: ?skill=, ?agent=, ?doc= and ?project=. */
export function picksFromLink(params: URLSearchParams): ComposePicks {
  const skill = params.get("skill");
  const doc = params.get("doc");
  return {
    ...NO_PICKS,
    skills: skill ? [skill] : [],
    agent: params.get("agent"),
    docs: doc ? [doc] : [],
    project: params.get("project"),
  };
}

/** Does a link ask to run something (a skill, an agent, a doc), not only to write a prompt? */
export function linkRuns(params: URLSearchParams): boolean {
  return params.get("run") === "1" || ["skill", "agent", "doc"].some((key) => params.get(key));
}

/** The old Compose address: its links open a new prompt with the run panel open. */
export function ComposeMoved() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("run", "1");
  return <Navigate to={`/work/prompts/new?${params.toString()}`} replace />;
}

/** The value once it has stopped changing for `ms`. */
export function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/** New skill, written by your AI from a request you keep making. */
export function skillFromPrompt(spec: ComposeSpec): string {
  const ask = [
    `Make a skill from a request I keep making: "${spec.request.trim()}"`,
    spec.skills.length ? `It follows ${spec.skills.map((s) => `/${s}`).join(", ")}.` : "",
    spec.library.length ? `It reads ${spec.library.join(", ")}.` : "",
  ]
    .filter(Boolean)
    .join(" ");
  return `${SKILLS}?new=1&ask=${encodeURIComponent(ask)}`;
}

/** Run the words here, improve them, or see the whole prompt a model gets; `prompt` is the
 * saved prompt they came from, so a run counts as its use. Without `withProject`, the page
 * around it picks the project. */
export function ComposePanel({
  request,
  onRequest,
  picks,
  onPicks,
  prompt = null,
  withProject = true,
}: {
  request: string;
  onRequest: (text: string) => void;
  picks: ComposePicks;
  onPicks: (picks: ComposePicks) => void;
  prompt?: SavedPrompt | null;
  withProject?: boolean;
}) {
  const [task, setTask] = useState<Task | null>(null);
  const run = useComposeRun();
  const improving = useImproving();
  const spec = useMemo<ComposeSpec>(() => ({ request, ...picks }), [request, picks]);
  const empty = !request.trim();
  return (
    <div className="compose-layout">
      <section className="compose-ask" aria-label="What goes with it">
        <Pickers picks={picks} onChange={onPicks} withProject={withProject} />
        <div className="row compose-actions">
          <button
            type="button"
            className="primary"
            disabled={empty || run.isPending}
            onClick={() => run.mutate({ ...spec, prompt_id: prompt?.id }, { onSuccess: (made) => setTask(made) })}
          >
            {run.isPending ? "Asking…" : "Run here"}
          </button>
          <button
            type="button"
            disabled={empty || improving.working}
            title="Your AI rewrites the words with what you picked, and says what it changed"
            onClick={() => improving.start(spec)}
          >
            {improving.working ? "Improving…" : "Improve"}
          </button>
          {empty ? null : (
            <Link
              className="button"
              to={`/work/workflows/new?name=${encodeURIComponent(prompt?.title ?? request.trim().split("\n")[0]?.slice(0, 80) ?? "")}`}
              state={{
                step: prompt
                  ? { kind: "prompt", prompt_id: prompt.id, text: "", docs: [], library: [], meetings: 0 }
                  : { kind: "prompt", prompt_id: null, text: request, skills: picks.skills, agent: picks.agent, docs: picks.docs, library: picks.library, meetings: 0 },
              }}
            >
              Schedule it
            </Link>
          )}
        </div>
        <ErrorNote error={run.error ?? improving.error} />
        {task ? <Working key={task.id} task={task} waiting="It waits for a model: run it here, or copy the prompt into a connected AI." /> : null}
        <Improved improving={improving} onTake={onRequest} />
      </section>
      <section className="compose-prompt" aria-label="What your AI gets">
        <h2>What your AI gets</h2>
        <Assembled spec={spec} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- what goes with it

function Pickers({ picks, onChange, withProject }: { picks: ComposePicks; onChange: (picks: ComposePicks) => void; withProject: boolean }) {
  const { data: skills } = useSkills();
  const { data: agents } = useWorkAgents();
  const { data: notes } = useNotes();
  const { data: files } = useBrainFiles();
  const set = (changes: Partial<ComposePicks>) => onChange({ ...picks, ...changes });
  const runnable = (skills?.skills ?? []).filter((s) => s.use === "run");
  const readable = (notes ?? []).filter((n) => !n.transcription || n.transcription.state === "ready");
  return (
    <div className="compose-pickers">
      <PickMany
        label="Skills to follow"
        empty="None: your Brain picks the one that fits"
        options={runnable.map((s) => ({ value: s.name, label: `/${s.name}`, hint: s.description.split(/(?<=[.!?])\s/)[0] }))}
        value={picks.skills}
        onChange={(next) => set({ skills: next })}
        max={6}
        ordered
        hint={picks.skills.length > 1 ? "Followed in this order, each building on the last." : "Up to six, in the order you pick them."}
      />
      <Field label="Work as an agent" hint="Its role, and what it points to, come along.">
        <select value={picks.agent ?? ""} onChange={(event) => set({ agent: event.target.value || null })}>
          <option value="">No agent</option>
          {(agents ?? [])
            .filter((a) => a.status !== "archived")
            .map((a) => (
              <option key={a.name} value={a.name}>
                {a.name}: {a.role}
              </option>
            ))}
        </select>
      </Field>
      <PickMany
        label="Your notes and docs"
        empty="None"
        options={readable.map((n) => ({ value: n.id, label: n.title, hint: CAPTURE_NAMES[n.capture ?? "note"] }))}
        value={picks.docs}
        onChange={(next) => set({ docs: next })}
        max={5}
        hint="Pinned to the run as they are now. Private to you until you run it."
      />
      <PickMany
        label="Documents to read whole"
        empty="None"
        options={(files?.references ?? []).filter((f) => f.library !== "prompt").map((f) => ({ value: f.path, label: f.title, hint: f.project_title ?? f.path }))}
        value={picks.library}
        onChange={(next) => set({ library: next })}
        max={5}
        hint="From your Library and the Brain's files: read whole, as they are when it runs."
      />
      {withProject ? <ProjectPicker value={picks.project} onChange={(project) => set({ project })} /> : null}
    </div>
  );
}

/** The project something is for, from the Brain's active projects. */
export function ProjectPicker({ value, onChange }: { value: string | null; onChange: (project: string | null) => void }) {
  const { data: projects } = useBrainProjects();
  return (
    <Field label="For a project">
      <select value={value ?? ""} onChange={(event) => onChange(event.target.value || null)}>
        <option value="">None</option>
        {(projects ?? [])
          .filter((p) => p.active || p.id === value)
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
      </select>
    </Field>
  );
}

// ---------------------------------------------------------------- the whole prompt

function Assembled({ spec }: { spec: ComposeSpec }) {
  const settled = useSettled(spec, SETTLE_MS);
  const { data, error, isFetching } = useAssembled(settled.request.trim() ? settled : null);
  const [view, setView] = useState<"whole" | "short">("whole");
  if (!spec.request.trim()) {
    return <p className="muted">Write the prompt, and the whole prompt your AI gets appears here: its instructions, your notes, and the Brain's brief.</p>;
  }
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <div className="stack">
      <p className="compose-size" role="status">
        <strong>{data.tokens.toLocaleString()} tokens</strong>
        {data.exact ? "" : " (estimated)"}
        {isFetching || settled !== spec ? <span className="muted small"> · updating</span> : null}
      </p>
      <ul className="compose-parts" aria-label="Its parts">
        {data.parts.map((part) => (
          <li key={part.label}>
            {part.label} <span className="muted">{part.tokens.toLocaleString()}</span>
          </li>
        ))}
      </ul>
      {data.brief.available ? null : (
        <p className="notice small">{data.brief.note || "The Brain is not connected, so the run gets no brief."}</p>
      )}
      {data.makes_files ? (
        <p className="muted small">A skill you picked makes files, so the run works in a folder of its own under your outputs folder.</p>
      ) : null}
      <Tabs
        tabs={[
          { id: "whole", label: "The whole prompt" },
          { id: "short", label: "Short, for any AI" },
        ]}
        active={view}
        onChange={setView}
      />
      {view === "whole" ? (
        <CopyBlock text={data.prompt} label={data.title} />
      ) : (
        <>
          <p className="muted small">
            For an AI connected to your Brain: it fetches the brief, the agent, the skills and the documents itself ({data.short_tokens.toLocaleString()}{" "}
            tokens to paste).
          </p>
          <CopyBlock text={data.short} label="Short, for any AI" />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- improving it

/** Improving the words: the model's job, the words as they were when asked, and what it
 * suggests. Nothing changes until the owner takes it. */
function useImproving() {
  const improve = useImprovePrompt();
  const [jobId, setJobId] = useState<string | null>(null);
  const [asked, setAsked] = useState("");
  const { data: job } = useWorkJob(jobId);
  return {
    start(spec: ComposeSpec) {
      setAsked(spec.request);
      improve.mutate(spec, { onSuccess: (made) => setJobId(made.id) });
    },
    clear: () => setJobId(null),
    working: improve.isPending || (!!jobId && !!job && WORKING.includes(job.status)),
    error: improve.error,
    job: jobId ? job : undefined,
    asked,
  };
}

function Improved({ improving, onTake }: { improving: ReturnType<typeof useImproving>; onTake: (text: string) => void }) {
  const { job, asked } = improving;
  if (job?.status === "failed") return <p className="error">{job.error}</p>;
  const result = job?.status === "done" ? job.result : null;
  if (!result?.prompt) return null;
  const suggested = result.prompt;
  return (
    <section className="compose-improved" aria-label="Improved request">
      <p className="muted small">Your AI's rewrite, with what you picked. Nothing changes until you take it.</p>
      <Compare before={{ label: "Yours", title: "Your words", body: asked }} after={{ label: "Suggested", title: "Improved", body: suggested }} />
      {result.changes?.length ? (
        <ul className="small" aria-label="What changed">
          {result.changes.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {result.used?.length ? <p className="muted small">It leaned on {result.used.join(", ")}.</p> : null}
      {result.questions?.length ? (
        <div className="notice small">
          <p>Still unclear:</p>
          <ul>
            {result.questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="row">
        <button
          type="button"
          className="primary"
          onClick={() => {
            onTake(suggested);
            improving.clear();
          }}
        >
          Use it
        </button>
        <button type="button" onClick={improving.clear}>
          Keep mine
        </button>
      </div>
    </section>
  );
}

// Work, Compose: one place to ask, built so you see and reuse what goes to the model. Write what
// you want, pick what goes with it (skills in order, an agent, your notes, documents to read
// whole, a project), and the whole prompt sits beside it, exactly as a model gets it, with its
// size. Then improve it, run it here, copy it for any AI, save it, or make it a skill: show it
// once here, write it down as a skill, hand it off to an agent.

import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import {
  useArchivePrompt,
  useAssembled,
  useBrainFiles,
  useBrainProjects,
  useComposeRun,
  useImprovePrompt,
  useNotes,
  useSavedPrompts,
  useSavePrompt,
  useSkills,
  useWorkAgents,
  useWorkJob,
} from "../../api/hooks";
import type { ComposePicks, ComposeSpec, SavedPrompt, Task } from "../../api/types";
import { CAPTURE_NAMES } from "../../components/CaptureParts";
import { Compare } from "../../components/Diff";
import { Working } from "../../components/RunNow";
import { LatestRuns } from "../../components/SkillWork";
import { CopyBlock, Empty, ErrorNote, Field, Loading, Section, Tabs } from "../../components/ui";
import { PickMany } from "../../components/work/PickMany";
import { plural, when } from "../../lib/format";
import { SKILLS } from "../../lib/links";
import { ScopeChip } from "../../components/work/Scope";

const SETTLE_MS = 500; // a pause this long in typing or picking refreshes the whole prompt
const NONE: ComposePicks = { skills: [], agent: null, docs: [], library: [], project: null };
const WORKING = ["waiting", "running"];

/** Picks from a link into Compose: ?skill=, ?agent=, ?doc=, ?project= and ?ask=. */
function fromLink(params: URLSearchParams): ComposePicks {
  const skill = params.get("skill");
  const doc = params.get("doc");
  return {
    ...NONE,
    skills: skill ? [skill] : [],
    agent: params.get("agent"),
    docs: doc ? [doc] : [],
    project: params.get("project"),
  };
}

/** The value once it has stopped changing for `ms`. */
function useSettled<T>(value: T, ms: number): T {
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

export function ComposePage() {
  const [params] = useSearchParams();
  const [request, setRequest] = useState(params.get("ask") ?? "");
  const [picks, setPicks] = useState<ComposePicks>(() => fromLink(params));
  const [loaded, setLoaded] = useState<SavedPrompt | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [saving, setSaving] = useState(false);
  const run = useComposeRun();
  const improving = useImproving();
  const spec = useMemo<ComposeSpec>(() => ({ request, ...picks }), [request, picks]);
  const empty = !request.trim();
  return (
    <div className="work-tab compose">
      <div className="work-intro">
        <p>
          One place to ask. Write what you want, pick what goes with it, and see the whole prompt your AI gets beside it, with its size. Then
          improve it, run it here, copy it for any AI, or save it to use again.
        </p>
      </div>
      <div className="compose-layout">
        <section className="compose-ask" aria-label="Your request">
          <Field label="What do you want?" hint={loaded ? `From your saved prompt “${loaded.title}”.` : undefined}>
            <textarea
              rows={6}
              value={request}
              placeholder="For example: three LinkedIn posts for next week from my launch outline, in our voice"
              onChange={(event) => setRequest(event.target.value)}
            />
          </Field>
          <Pickers picks={picks} onChange={setPicks} />
          <div className="row compose-actions">
            <button
              type="button"
              className="primary"
              disabled={empty || run.isPending}
              onClick={() => run.mutate({ ...spec, prompt_id: loaded?.id }, { onSuccess: (made) => setTask(made) })}
            >
              {run.isPending ? "Asking…" : "Run here"}
            </button>
            <button
              type="button"
              disabled={empty || improving.working}
              title="Your AI rewrites the request with what you picked, and says what it changed"
              onClick={() => improving.start(spec)}
            >
              {improving.working ? "Improving…" : "Improve"}
            </button>
            <button type="button" disabled={empty} aria-expanded={saving} onClick={() => setSaving(!saving)}>
              Save
            </button>
            {empty ? null : (
              <>
                <Link className="button" to={skillFromPrompt(spec)}>
                  Make it a skill
                </Link>
                <Link
                  className="button"
                  to={`/work/workflows/new?name=${encodeURIComponent(loaded?.title ?? request.trim().split("\n")[0]?.slice(0, 80) ?? "")}`}
                  state={{
                    step: loaded
                      ? { kind: "prompt", prompt_id: loaded.id, text: "", docs: [], library: [], meetings: 0 }
                      : { kind: "prompt", prompt_id: null, text: request, skills: picks.skills, agent: picks.agent, docs: picks.docs, library: picks.library, meetings: 0 },
                  }}
                >
                  Schedule it
                </Link>
              </>
            )}
          </div>
          <ErrorNote error={run.error ?? improving.error} />
          {saving && !empty ? (
            <SaveForm
              spec={spec}
              loaded={loaded}
              onDone={(saved) => {
                if (saved) setLoaded(saved);
                setSaving(false);
              }}
            />
          ) : null}
          {task ? <Working key={task.id} task={task} waiting="It waits for a model: run it here, or copy the prompt into a connected AI." /> : null}
          <Improved improving={improving} onTake={setRequest} />
        </section>
        <section className="compose-prompt" aria-label="What your AI gets">
          <h2>What your AI gets</h2>
          <Assembled spec={spec} />
        </section>
      </div>
      <LatestRuns />
      <SavedPrompts
        onLoad={(saved) => {
          setLoaded(saved);
          setRequest(saved.body);
          setPicks(saved.picks);
          setTask(null);
          setSaving(false);
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------- what goes with it

function Pickers({ picks, onChange }: { picks: ComposePicks; onChange: (picks: ComposePicks) => void }) {
  const { data: skills } = useSkills();
  const { data: agents } = useWorkAgents();
  const { data: notes } = useNotes();
  const { data: files } = useBrainFiles();
  const { data: projects } = useBrainProjects();
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
        options={(files?.references ?? []).map((f) => ({ value: f.path, label: f.title, hint: f.project_title ?? f.path }))}
        value={picks.library}
        onChange={(next) => set({ library: next })}
        max={5}
        hint="From your Library and the Brain's files: read whole, as they are when it runs."
      />
      <Field label="For a project">
        <select value={picks.project ?? ""} onChange={(event) => set({ project: event.target.value || null })}>
          <option value="">None</option>
          {(projects ?? [])
            .filter((p) => p.active || p.id === picks.project)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
        </select>
      </Field>
    </div>
  );
}

// ---------------------------------------------------------------- the whole prompt

function Assembled({ spec }: { spec: ComposeSpec }) {
  const settled = useSettled(spec, SETTLE_MS);
  const { data, error, isFetching } = useAssembled(settled.request.trim() ? settled : null);
  const [view, setView] = useState<"whole" | "short">("whole");
  if (!spec.request.trim()) {
    return <p className="muted">Write what you want, and the whole prompt your AI gets appears here: its instructions, your notes, and the Brain's brief.</p>;
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

/** Improving the request: the model's job, the request as it was when asked, and what it
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
      <Compare before={{ label: "Yours", title: "Your request", body: asked }} after={{ label: "Suggested", title: "Improved", body: suggested }} />
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

// ---------------------------------------------------------------- saving it

function SaveForm({ spec, loaded, onDone }: { spec: ComposeSpec; loaded: SavedPrompt | null; onDone: (saved: SavedPrompt | null) => void }) {
  const save = useSavePrompt();
  const { request, ...picks } = spec;
  const [title, setTitle] = useState(loaded?.title ?? request.trim().split("\n")[0]?.slice(0, 80) ?? "");
  return (
    <form
      className="inline-form"
      aria-label="Save the prompt"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({ title: title.trim(), body: request, picks }, { onSuccess: onDone });
      }}
    >
      <Field label="Its name">
        <input required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
      </Field>
      {loaded ? (
        <button
          type="button"
          className="primary"
          disabled={!title.trim() || save.isPending}
          onClick={() => save.mutate({ id: loaded.id, title: title.trim(), body: request, picks, expected_version: loaded.version }, { onSuccess: onDone })}
        >
          Save changes
        </button>
      ) : null}
      <button type="submit" className={loaded ? undefined : "primary"} disabled={!title.trim() || save.isPending}>
        {loaded ? "Save as new" : "Save it"}
      </button>
      <button type="button" onClick={() => onDone(null)}>
        Cancel
      </button>
      <ErrorNote error={save.error} />
    </form>
  );
}

// ---------------------------------------------------------------- saved prompts

function SavedPrompts({ onLoad }: { onLoad: (saved: SavedPrompt) => void }) {
  const [q, setQ] = useState("");
  const settled = useSettled(q, 250);
  const { data, isLoading, error } = useSavedPrompts(settled);
  const archive = useArchivePrompt();
  return (
    <Section title="Saved prompts">
      <input type="search" aria-label="Find a saved prompt" placeholder="Find a saved prompt" value={q} onChange={(event) => setQ(event.target.value)} />
      {isLoading ? (
        <Loading />
      ) : !data ? (
        <ErrorNote error={error} />
      ) : data.length ? (
        <ul className="workspace-list" aria-label="Saved prompts">
          {data.map((saved) => (
            <li key={saved.id} className="workspace-row">
              <span className="kind-chip kind-guide">{saved.uses ? `${saved.uses} runs` : "Saved"}</span>
              <div className="workspace-row-main">
                <button type="button" className="link workspace-row-title" onClick={() => onLoad(saved)}>
                  {saved.title}
                </button>
                <ScopeChip />
                <p className="muted small">{saved.body.length > 160 ? `${saved.body.slice(0, 159)}…` : saved.body}</p>
                <p className="muted small">
                  {saved.uses ? `Ran ${plural(saved.uses, "time")}, last ${when(saved.last_used)}` : `Saved ${when(saved.updated_at)}`}
                  {" · "}
                  <button type="button" className="link" onClick={() => archive.mutate({ id: saved.id })}>
                    Set aside
                  </button>
                  {saved.uses >= 3 ? (
                    <>
                      {" · "}
                      <Link to={skillFromPrompt({ request: saved.body, ...saved.picks })}>Used often: make it a skill</Link>
                    </>
                  ) : null}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <Empty why={settled ? "No saved prompt matches." : "Nothing saved yet. Save a prompt you will ask again; it keeps its picks and every version."} />
      )}
      <ErrorNote error={archive.error} />
    </Section>
  );
}

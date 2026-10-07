// First-time setup: five steps from an empty Brain to one your AI uses, each done when its
// thing exists (so it never disagrees with the Brain): your name, your AI, what the Brain should
// know about you, a first project, and its files. It ends at the guided tour. Home shows how far
// it has come until it is finished or put aside.

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router";

import { patch } from "../api/client";
import {
  keys,
  useBrainProjects,
  useCreateBrainProject,
  useInvalidate,
  useMarkOnboarding,
  useMe,
  useOnboarding,
  useProposeEntry,
  useRenameActor,
} from "../api/hooks";
import type { Onboarding, SetupStep } from "../api/types";
import { useTour } from "../components/tour/Tour";
import { ErrorNote, Field, Loading } from "../components/ui";
import { plural } from "../lib/format";
import { AddFileDialog } from "./brain/AddFile";
import { ConnectBrain } from "../components/ConnectBrain";
import { Runners } from "./Connections";

const STEPS: { id: SetupStep; title: string; short: string }[] = [
  { id: "you", title: "Make it yours", short: "Your name" },
  { id: "ai", title: "Bring in your AI", short: "Your AI" },
  { id: "brain", title: "Tell the Brain about you", short: "The Brain" },
  { id: "project", title: "Start a project", short: "A project" },
  { id: "file", title: "Add its files", short: "Its files" },
];
type Place = SetupStep | "finish";

/** Home's prompt: how far the setup has come, until it is finished or put aside. */
export function SetupCard() {
  const { data: setup } = useOnboarding();
  const mark = useMarkOnboarding();
  if (!setup || setup.completed_at || setup.dismissed_at) return null;
  const next = STEPS.find((s) => !setup.steps.find((x) => x.id === s.id)?.done);
  return (
    <section className="setup-card" aria-label="Get set up">
      <div>
        <h2>{setup.done ? "Finish setting up" : "Welcome. Let's get you set up"}</h2>
        <p className="muted">
          {setup.done
            ? `${setup.done} of ${setup.total} done.${next ? ` Next: ${next.short.toLowerCase()}.` : ""}`
            : "Five short steps: your name, your AI, what the Brain should know about you, a project and its files. About ten minutes."}
        </p>
        <div className="setup-meter" aria-hidden="true">
          <span style={{ width: `${(setup.done / setup.total) * 100}%` }} />
        </div>
      </div>
      <div className="row">
        <Link className="button primary" to="/settings?tab=start">
          {setup.done ? "Continue setup" : "Start setup"}
        </Link>
        <button type="button" className="link" onClick={() => mark.mutate({ dismissed: true })}>
          Not now
        </button>
      </div>
    </section>
  );
}

export function SetupPage() {
  const { data: setup, isLoading, error } = useOnboarding();
  const [place, setPlace] = useState<Place | null>(null);
  const done = new Set((setup?.steps ?? []).filter((s) => s.done).map((s) => s.id));
  const first = STEPS.find((s) => !done.has(s.id))?.id ?? "finish";
  // open on the first open step, then stay put: finishing a step shows it done, and Next moves on
  useEffect(() => {
    if (setup && place === null) setPlace(first);
  }, [setup, place, first]);
  if (isLoading) return <Loading />;
  if (!setup) return <ErrorNote error={error} />;
  const at: Place = place ?? first;
  const index = at === "finish" ? STEPS.length : STEPS.findIndex((s) => s.id === at);
  const go = (to: Place) => setPlace(to);
  const forward = () => go(STEPS[index + 1]?.id ?? "finish");
  return (
    <div className="setup">
      <div className="setup-head">
        <div>
          <h2>First-time setup</h2>
          <p className="muted">
            {setup.completed_at
              ? "Finished. Come back any time to add what is missing."
              : `${setup.done} of ${setup.total} done. Each step is done once its thing exists, so do them here or anywhere in the app.`}
          </p>
        </div>
        <div className="setup-meter" aria-hidden="true">
          <span style={{ width: `${(setup.done / setup.total) * 100}%` }} />
        </div>
      </div>
      <div className="setup-body">
        <ol className="setup-steps" aria-label="Setup steps">
          {STEPS.map((step, i) => (
            <li key={step.id}>
              <button
                type="button"
                className={["setup-step", at === step.id ? "current" : "", done.has(step.id) ? "done" : ""].join(" ").trim()}
                aria-current={at === step.id ? "step" : undefined}
                onClick={() => go(step.id)}
              >
                <span className="setup-mark" aria-hidden="true">
                  {done.has(step.id) ? "✓" : i + 1}
                </span>
                <span>
                  {step.short}
                  {done.has(step.id) ? <span className="sr-only">, done</span> : null}
                </span>
              </button>
            </li>
          ))}
          <li>
            <button
              type="button"
              className={at === "finish" ? "setup-step current" : "setup-step"}
              aria-current={at === "finish" ? "step" : undefined}
              onClick={() => go("finish")}
            >
              <span className="setup-mark" aria-hidden="true">
                ★
              </span>
              <span>Finish and take the tour</span>
            </button>
          </li>
        </ol>
        <div className="setup-panel">
          {at === "you" ? <You setup={setup} onNext={forward} /> : null}
          {at === "ai" ? <Ai setup={setup} onNext={forward} /> : null}
          {at === "brain" ? <Brain setup={setup} onNext={forward} /> : null}
          {at === "project" ? <FirstProject setup={setup} onNext={forward} /> : null}
          {at === "file" ? <FirstFiles setup={setup} onNext={forward} /> : null}
          {at === "finish" ? <Finish setup={setup} /> : null}
          {at !== "finish" && index > 0 ? (
            <button type="button" className="link small" onClick={() => go(STEPS[index - 1]?.id ?? "you")}>
              ← Back to {STEPS[index - 1]?.short.toLowerCase()}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** A step's frame: what it is and why it matters, its form, and how to move on. */
function Step({
  title,
  why,
  done,
  children,
  onNext,
  skip = "Skip for now",
}: {
  title: string;
  why: ReactNode;
  done: boolean;
  children: ReactNode;
  onNext: () => void;
  skip?: string;
}) {
  return (
    <section className="setup-step-panel" aria-label={title}>
      <h3>
        {title} {done ? <span className="chip chip-approved">Done</span> : null}
      </h3>
      <div className="setup-why">{why}</div>
      {children}
      <div className="row setup-next">
        <button type="button" className={done ? "primary" : ""} onClick={onNext}>
          {done ? "Next" : skip}
        </button>
      </div>
    </section>
  );
}

function stepDone(setup: Onboarding, id: SetupStep) {
  return !!setup.steps.find((s) => s.id === id)?.done;
}

// ---------------------------------------------------------------- 1. you

function You({ setup, onNext }: { setup: Onboarding; onNext: () => void }) {
  const { data: me } = useMe();
  const rename = useRenameActor();
  const mark = useMarkOnboarding();
  const invalidate = useInvalidate();
  const here = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [name, setName] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [zone, setZone] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!me) return;
    setName((n) => n || (me.name === "Owner" ? "" : me.name));
    setWorkspace((w) => w || me.workspace.name);
    setZone((z) => z || me.workspace.timezone || here);
  }, [me, here]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!me) return;
    setError(null);
    try {
      if (name.trim() && name.trim() !== me.name) await rename.mutateAsync({ id: me.actor_id, name: name.trim() });
      if (workspace.trim() !== me.workspace.name || zone !== me.workspace.timezone) {
        await patch("/api/workspace", { name: workspace.trim() || undefined, timezone: zone || undefined });
      }
      if (!name.trim()) await mark.mutateAsync({ step: "you" });
      await invalidate(keys.me, keys.home, keys.onboarding);
      setSaved(true);
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <Step
      title="Make it yours"
      done={stepDone(setup, "you")}
      onNext={onNext}
      why={
        <p>
          Your AI addresses you by this name, and the Brain records you as the person who approves what it learns. The
          timezone dates what comes in.
        </p>
      }
    >
      <form className="stack" onSubmit={(e) => void save(e)} aria-label="About you">
        <Field label="Your name">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sam Lee" maxLength={80} autoComplete="name" />
        </Field>
        <Field label="This workspace's name">
          <input value={workspace} onChange={(e) => setWorkspace(e.target.value)} placeholder="Sam's workspace" />
        </Field>
        <Field label="Timezone" hint={zone !== here ? `This computer is on ${here}.` : "From this computer."}>
          <span className="row">
            <input value={zone} onChange={(e) => setZone(e.target.value)} placeholder="America/New_York" />
            {zone !== here ? (
              <button type="button" onClick={() => setZone(here)}>
                Use {here}
              </button>
            ) : null}
          </span>
        </Field>
        <div className="row">
          <button type="submit" className="primary" disabled={rename.isPending}>
            Save
          </button>
          {saved ? <span className="muted small">Saved.</span> : null}
        </div>
        <ErrorNote error={error} />
      </form>
    </Step>
  );
}

// ---------------------------------------------------------------- 2. ai

function Ai({ setup, onNext }: { setup: Onboarding; onNext: () => void }) {
  return (
    <Step
      title="Bring in your AI"
      done={stepDone(setup, "ai")}
      onNext={onNext}
      why={
        <>
          <p>
            Connect the AI apps you use to your Brain: one command or one settings block each, and from then on they read the Brain
            in every chat. The app also hands a model a few jobs of its own, like finding what to remember in a note:{" "}
            <strong>run now</strong> with Claude Code on this computer (one click, and you watch it work), or connect any model to
            check in for them.
          </p>
          <p className="muted small">
            Every model gets its own revocable token and only ever sees its own queue. What it suggests waits for your review.
          </p>
        </>
      }
    >
      <ConnectBrain />
      {setup.local_model ? <p className="notice">Claude Code on this computer is ready to run tasks.</p> : null}
      <Runners />
      <p>
        <Link to="/settings?tab=connections">Connect another model (Claude, ChatGPT, Codex, Gemini or a local one)</Link>
      </p>
    </Step>
  );
}

// ---------------------------------------------------------------- 3. the brain

const PROMPTS = [
  {
    key: "identity",
    title: "Who I am",
    kind: "identity",
    label: "Who you are and what you do",
    placeholder: "I lead marketing at a 40-person software company, and run it mostly on my own.",
  },
  {
    key: "audience",
    title: "Who we serve",
    kind: "fact",
    label: "Who you serve",
    placeholder: "Our customers are operations leaders at mid-size manufacturers.",
  },
  {
    key: "rules",
    title: "How I want work done",
    kind: "rule",
    label: "How you want work done",
    placeholder: "Plain, direct writing. No hype. Never publish anything without my approval.",
  },
  {
    key: "now",
    title: "What matters now",
    kind: "state",
    label: "What matters right now",
    placeholder: "This quarter: relaunch the website and grow the pipeline.",
  },
] as const;

function Brain({ setup, onNext }: { setup: Onboarding; onNext: () => void }) {
  const propose = useProposeEntry();
  const [text, setText] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const filled = PROMPTS.filter((p) => text[p.key]?.trim());

  async function teach(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      for (const prompt of filled) {
        await propose.mutateAsync({
          title: prompt.title,
          statement: (text[prompt.key] ?? "").trim(),
          kind: prompt.kind,
          evidence: "Said during first-time setup.",
          origin: "you:setup",
        });
      }
      setSent(filled.length);
      setText({});
    } catch (caught) {
      setError(caught);
    }
  }

  if (!setup.brain.available) {
    return (
      <Step
        title="Tell the Brain about you"
        done={false}
        onNext={onNext}
        why={
          <p>
            The Brain is what every model knows before it helps you. None is connected yet: run{" "}
            <code>uv run contxt setup</code> in the Contxt folder, restart the app, then come back to this step.
          </p>
        }
      >
        {null}
      </Step>
    );
  }
  return (
    <Step
      title="Tell the Brain about you"
      done={stepDone(setup, "brain")}
      onNext={onNext}
      why={
        <>
          <p>
            The Brain is what every model knows before it helps you: who you are, facts about your work, the rules you want
            followed, and what matters now. Each answer below becomes a <strong>proposal</strong>: it waits in Brain, Review for
            your approval, and only then do models receive it.
          </p>
          <p className="muted small">
            Write a sentence or two for each you want; leave the rest. Add more any time, from documents you upload or from any
            doc you write.
          </p>
        </>
      }
    >
      <form className="stack" onSubmit={(e) => void teach(e)} aria-label="Teach the Brain">
        {PROMPTS.map((prompt) => (
          <Field key={prompt.key} label={prompt.label}>
            <textarea
              rows={2}
              value={text[prompt.key] ?? ""}
              placeholder={prompt.placeholder}
              onChange={(e) => setText({ ...text, [prompt.key]: e.target.value })}
            />
          </Field>
        ))}
        <div className="row">
          <button type="submit" className="primary" disabled={!filled.length || propose.isPending}>
            Propose {filled.length ? plural(filled.length, "entry", "entries") : "them"} to the Brain
          </button>
        </div>
        <ErrorNote error={error} />
      </form>
      {sent || setup.brain.waiting ? (
        <p className="notice">
          {sent ? `${plural(sent, "proposal")} sent. ` : ""}
          {plural(setup.brain.waiting, "proposal")} {setup.brain.waiting === 1 ? "waits" : "wait"} for your review.{" "}
          <Link to="/review">Review them now</Link>: nothing reaches your models until you approve it.
        </p>
      ) : null}
      {setup.brain.own_entries ? <p className="muted small">The Brain already holds {plural(setup.brain.own_entries, "entry", "entries")} of yours.</p> : null}
    </Step>
  );
}

// ---------------------------------------------------------------- 4 and 5. a project, its files

function FirstProject({ setup, onNext }: { setup: Onboarding; onNext: () => void }) {
  const { data: projects } = useBrainProjects();
  const create = useCreateBrainProject();
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [aliases, setAliases] = useState("");

  function add(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { name: name.trim(), summary: summary.trim(), aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean) },
      {
        onSuccess: () => {
          setName("");
          setSummary("");
          setAliases("");
        },
      },
    );
  }

  return (
    <Step
      title="Start a project"
      done={stepDone(setup, "project")}
      onNext={onNext}
      why={
        <p>
          A project is work your AI follows across every chat: what it is for, where it stands, its files. Mention it by any of
          its names and your AI brings all of that with it.
        </p>
      }
    >
      {projects?.length ? (
        <p className="muted">
          Your Brain follows {plural(projects.length, "project")}: {projects.map((p) => p.title).join(", ")}.{" "}
          <Link to="/projects">See them</Link>
        </p>
      ) : null}
      <form className="stack" onSubmit={add} aria-label="New project">
        <Field label="Name">
          <input required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Q4 campaign proposals" />
        </Field>
        <Field label="What it is for" hint="One line.">
          <input required maxLength={300} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Field>
        <Field label="Other names you will call it" hint="Comma separated.">
          <input value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="campaign proposals, Jordan's proposals" />
        </Field>
        <div className="row">
          <button type="submit" className="primary" disabled={create.isPending || !name.trim() || !summary.trim()}>
            Start it
          </button>
        </div>
        <ErrorNote error={create.error} />
      </form>
    </Step>
  );
}

function FirstFiles({ setup, onNext }: { setup: Onboarding; onNext: () => void }) {
  const { data: projects } = useBrainProjects();
  const [adding, setAdding] = useState(false);
  const project = projects?.find((p) => p.active) ?? projects?.[0];
  return (
    <Step
      title="Add its files"
      done={stepDone(setup, "file")}
      onNext={onNext}
      why={
        <p>
          Drafts, briefs, proposals: add them to the project and your AI quotes the part a request is about, with which version it
          is. A file named like one already there becomes its new version.
        </p>
      }
    >
      {project ? (
        <p>
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            Add a file to {project.title}
          </button>
        </p>
      ) : (
        <p className="muted">Start a project first.</p>
      )}
      {adding && project ? <AddFileDialog project={project.id} onClose={() => setAdding(false)} /> : null}
    </Step>
  );
}

// ---------------------------------------------------------------- finish

function Finish({ setup }: { setup: Onboarding }) {
  const mark = useMarkOnboarding();
  const tour = useTour();
  const missing = STEPS.filter((s) => !stepDone(setup, s.id));
  return (
    <section className="setup-step-panel" aria-label="Finish">
      <h3>{missing.length ? "Almost there" : "You are set up"}</h3>
      {missing.length ? (
        <p>
          Still open: {missing.map((s) => s.short.toLowerCase()).join(", ")}. Finish now anyway and come back from the{" "}
          <strong>?</strong> at the top right whenever you like.
        </p>
      ) : (
        <p>Everything is in place. The guided tour shows how it all fits together: Home, Capture, Projects, the Brain, Skills and Review.</p>
      )}
      <div className="row">
        <button
          type="button"
          className="primary"
          onClick={() => mark.mutate({ completed: true, dismissed: false }, { onSuccess: () => tour.start() })}
        >
          Finish and take the tour
        </button>
        <button type="button" onClick={() => mark.mutate({ completed: true, dismissed: false })} disabled={!!setup.completed_at}>
          {setup.completed_at ? "Finished" : "Finish without the tour"}
        </button>
      </div>
    </section>
  );
}

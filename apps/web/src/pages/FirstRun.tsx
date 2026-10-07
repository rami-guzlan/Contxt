// The first run, full screen, about ten minutes: a welcome (the line, the loop, the three
// promises), your goals (the interview), moving in what your AIs know, connecting an AI app and
// watching its first request arrive, one before and after, and your rhythm (what waits for you).
// It teaches by doing; every step can be skipped, and Settings brings it back.

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import {
  keys,
  useAiApps,
  useAiRequests,
  useBrainPolicies,
  useConnectApp,
  useGoals,
  useMarkOnboarding,
  useMe,
  useOnboarding,
  useRenameActor,
  useSetBrainPolicies,
} from "../api/hooks";
import type { AiApp, AiRequest, Goals, Onboarding, Preset } from "../api/types";
import { SeeTheDifference } from "../components/Difference";
import { GoalsInterview } from "../components/GoalsInterview";
import { CopyBlock, ErrorNote, Loading } from "../components/ui";
import { plural, when } from "../lib/format";
import { MoveIn } from "./MoveIn";

type Step = "welcome" | "goals" | "move-in" | "connect" | "difference" | "rhythm";

export const STEPS: { id: Step; label: string }[] = [
  { id: "welcome", label: "Welcome" },
  { id: "goals", label: "Your goals" },
  { id: "move-in", label: "Move in" },
  { id: "connect", label: "Connect" },
  { id: "difference", label: "See the difference" },
  { id: "rhythm", label: "Your rhythm" },
];

export const LINE = "Tell it once. Every AI you use knows.";
export const PROMISES: [string, string][] = [
  ["The same you in every AI", "Who you are, your goals, how you like work done, your projects: told once, used everywhere. Switch tools without starting over."],
  [
    "Only what matters, only what you approved",
    "What you bring in is sifted against your goals and projects. Your own words go straight in; what an AI picks up about how to behave waits for your yes. Every change has an undo.",
  ],
  ["See what each AI got", "For every request: what it was given, why, and what it saved."],
];

export function FirstRunPage() {
  const navigate = useNavigate();
  const mark = useMarkOnboarding();
  const client = useQueryClient();
  // Home opens the first run for a new Brain: say at once that it is finished or put aside, so
  // Home does not read the old state while the new one is fetched and send the person back.
  const finish = (body: { completed?: boolean; dismissed?: boolean }) => {
    const now = new Date().toISOString();
    client.setQueryData<Onboarding>(keys.onboarding, (old) =>
      old ? { ...old, ...(body.completed ? { completed_at: now } : {}), ...(body.dismissed ? { dismissed_at: now } : {}) } : old,
    );
    mark.mutate(body, { onSettled: () => navigate("/") });
  };
  const [step, setStep] = useState<Step>(() => {
    const wanted = new URLSearchParams(window.location.search).get("step");
    return (STEPS.find((s) => s.id === wanted)?.id as Step) ?? "welcome";
  });
  const index = STEPS.findIndex((s) => s.id === step);
  const next = () => setStep(STEPS[Math.min(index + 1, STEPS.length - 1)]?.id ?? "rhythm");
  const leave = () => finish({ dismissed: true });
  return (
    <div className="first-run">
      <header className="first-run-head">
        <ol className="first-run-steps" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s.id} className={i < index ? "done" : i === index ? "now" : undefined} aria-current={i === index ? "step" : undefined}>
              {i < index ? <Check className="button-icon" aria-hidden="true" /> : null}
              {s.label}
            </li>
          ))}
        </ol>
        <button type="button" className="link" onClick={leave}>
          <X className="button-icon" aria-hidden="true" />
          Finish later
        </button>
      </header>
      <main className="first-run-body">
        {step === "welcome" ? <Welcome onStart={next} /> : null}
        {step === "goals" ? <GoalsStep onDone={next} /> : null}
        {step === "move-in" ? (
          <section>
            <h1>Move in what your AIs already know</h1>
            <p className="lede">Optional, and worth it: ChatGPT, Claude and Cursor already remember things about you. Watch the Brain sift them against your goals.</p>
            <MoveIn onDone={next} />
          </section>
        ) : null}
        {step === "connect" ? <Connect onDone={next} /> : null}
        {step === "difference" ? (
          <section>
            <h1>See the difference</h1>
            <p className="lede">The same request, answered without your Brain and with it.</p>
            <DifferenceStep />
            <button type="button" className="primary" onClick={next}>
              Next <ArrowRight className="button-icon" aria-hidden="true" />
            </button>
          </section>
        ) : null}
        {step === "rhythm" ? <Rhythm onDone={() => finish({ completed: true })} /> : null}
      </main>
    </div>
  );
}

function Welcome({ onStart }: { onStart: () => void }) {
  const [frame, setFrame] = useState(0);
  return (
    <section className="welcome-frames">
      {frame === 0 ? (
        <>
          <h1 className="the-line">{LINE}</h1>
          <p className="lede">
            Your Brain is plain files on your computer. Claude, Cursor, Codex and any app that speaks MCP read the part each request needs, and it
            changes only the way you allow.
          </p>
        </>
      ) : null}
      {frame === 1 ? (
        <>
          <h1>How it works</h1>
          <ol className="loop" aria-label="The loop">
            <li>You bring things in: talk, meetings, files, notes.</li>
            <li>The Brain summarizes each one and pulls out what serves your goals and your projects.</li>
            <li>Facts and progress go in at once; anything that changes how your AIs behave waits for your yes.</li>
            <li>Every AI you connect gets the part each request needs.</li>
            <li>You can see what each one got.</li>
          </ol>
        </>
      ) : null}
      {frame === 2 ? (
        <>
          <h1>Three promises</h1>
          <ul className="promises">
            {PROMISES.map(([title, text]) => (
              <li key={title}>
                <strong>{title}.</strong> {text}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <div className="row">
        {frame < 2 ? (
          <>
            <button type="button" className="primary" onClick={() => setFrame(frame + 1)}>
              Next <ArrowRight className="button-icon" aria-hidden="true" />
            </button>
            <button type="button" className="link" onClick={onStart}>
              Skip the welcome
            </button>
          </>
        ) : (
          <>
            <button type="button" className="primary big" onClick={onStart} autoFocus>
              Start my Brain
            </button>
            <a className="link" href="#finished" onClick={(event) => { event.preventDefault(); setFrame(3); }}>
              See a finished one first
            </a>
          </>
        )}
      </div>
      {frame === 3 ? (
        <div className="finished-one">
          <p>
            A demo Brain shows what a finished one looks like, with made-up people and numbers. In a terminal, in the Contxt folder:
          </p>
          <CopyBlock label="Open a demo Brain" text="uv run contxt demo knowledge-company" />
          <p className="muted small">Then come back here and start your own.</p>
          <button type="button" className="primary" onClick={onStart}>
            Start my Brain
          </button>
        </div>
      ) : null}
    </section>
  );
}

function GoalsStep({ onDone }: { onDone: () => void }) {
  const { data: me } = useMe();
  const { data: setup } = useOnboarding();
  const rename = useRenameActor();
  const [name, setName] = useState("");
  const unnamed = !!setup && (setup.owner_name || "Owner") === "Owner";
  return (
    <section>
      <h1>What is your Brain for?</h1>
      {unnamed && me ? (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) rename.mutate({ id: me.actor_id, name: name.trim() });
          }}
        >
          <label className="field-label" htmlFor="owner-name">
            First, what should your AIs call you?
          </label>
          <input id="owner-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" />
          <button type="submit" disabled={!name.trim() || rename.isPending}>
            {rename.isSuccess ? "Saved" : "Save"}
          </button>
          <ErrorNote error={rename.error} />
        </form>
      ) : null}
      <GoalsInterview onDone={(_goals: Goals) => onDone()} />
    </section>
  );
}

/** Connect an AI app, then watch its first request arrive: the moment that teaches it all. */
function Connect({ onDone }: { onDone: () => void }) {
  const since = useRef(new Date().toISOString());
  const { data: apps, isLoading } = useAiApps(true);
  const { data: requests } = useAiRequests({ limit: 5 }, true);
  const arrived = useMemo(() => (requests?.requests ?? []).find((r) => r.at >= since.current.slice(0, 19)), [requests]);
  const found = (apps ?? []).filter((a) => a.found && a.setup);
  const [pick, setPick] = useState<string | null>(null);
  const app = found.find((a) => a.client === pick) ?? found[0];
  const [waited, setWaited] = useState(0);
  useEffect(() => {
    if (arrived) return;
    const timer = window.setInterval(() => setWaited((w) => w + 5), 5000);
    return () => window.clearInterval(timer);
  }, [arrived]);
  if (isLoading) return <Loading />;
  return (
    <section>
      <h1>Connect your AI, and prove it</h1>
      {arrived ? (
        <Arrived request={arrived} onDone={onDone} />
      ) : (
        <>
          {found.length > 1 ? (
            <div className="chips" role="group" aria-label="Your AI apps">
              {found.map((a) => (
                <button key={a.client} type="button" className={a === app ? "chip-button active" : "chip-button"} aria-pressed={a === app} onClick={() => setPick(a.client)}>
                  {a.label}
                  {a.connected ? " (connected)" : ""}
                </button>
              ))}
            </div>
          ) : null}
          {app ? <AppSetup app={app} /> : <p className="muted">No AI app found on this computer. Claude Code, Claude Desktop, Cursor and Codex each take one step: see Settings, Your AI apps.</p>}
          <div className="handshake" role="status" aria-live="polite">
            <p>
              <strong>Now ask it:</strong> “What do you know about me and how I like work done?”
            </p>
            <p className="muted">This page lights up when the request arrives.</p>
            {waited >= 120 ? (
              <div className="warning small">
                <p>Nothing yet. The usual causes:</p>
                <ul>
                  <li>The app was not restarted after connecting: quit it fully and open it again.</li>
                  <li>An older setup points somewhere else: connect it again from here.</li>
                  <li>It runs in another folder or profile: start a new chat in the app you connected.</li>
                </ul>
              </div>
            ) : null}
          </div>
          <p className="muted small">
            Claude Code on this computer can also run the app's own AI work. Set it up later in Settings, On this computer.
          </p>
          <button type="button" className="link" onClick={onDone}>
            Skip for now
          </button>
        </>
      )}
    </section>
  );
}

function AppSetup({ app }: { app: AiApp }) {
  const connect = useConnectApp();
  const [asking, setAsking] = useState(false);
  const setup = app.setup;
  if (!setup) return null;
  return (
    <div className="app-setup">
      <h2>{app.label}</h2>
      {setup.command ? <CopyBlock label="Run this once in a terminal" text={setup.command} /> : null}
      {setup.config ? <CopyBlock label={`Add this to ${setup.file ?? "its settings file"}`} text={setup.config} /> : null}
      <p className="muted small">{setup.note}</p>
      {app.connected ? (
        <p className="small">
          <Check className="button-icon" aria-hidden="true" /> {app.label} is set up. Restart it if it was open.
        </p>
      ) : asking ? (
        <div className="confirm" role="alertdialog" aria-label={`Add it to ${app.label}`}>
          <p>This changes {app.label}'s own settings. A backup copy is made first. Go ahead?</p>
          <div className="row">
            <button type="button" className="primary" disabled={connect.isPending} onClick={() => connect.mutate(app.client, { onSuccess: () => setAsking(false) })}>
              Yes, add it
            </button>
            <button type="button" className="link" onClick={() => setAsking(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => setAsking(true)}>
          Add it for me
        </button>
      )}
      {connect.data ? (
        <p className="small" role="status">
          {connect.data.changed ? `Added. Quit ${app.label} fully and open it again.` : `${app.label} already had it.`}
          {connect.data.backup ? ` The old settings are kept beside them.` : ""}
        </p>
      ) : null}
      <ErrorNote error={connect.error} />
    </div>
  );
}

export function describeGot(request: AiRequest): string {
  const notes = request.got.filter((p) => p.kind === "note" && p.note_kind !== "focus");
  const rules = notes.filter((p) => p.note_kind === "rule").length;
  const projects = request.project ? 1 : request.got.filter((p) => p.kind === "focus").length;
  const parts = [
    request.kernel ? "the startup context" : "",
    rules ? plural(rules, "rule") : "",
    projects ? plural(projects, "project") : "",
    notes.length - rules ? plural(notes.length - rules, "note") : "",
  ].filter(Boolean);
  return parts.length ? parts.join(", ").replace(/, ([^,]*)$/, " and $1") : "nothing yet: your Brain is new";
}

function Arrived({ request, onDone }: { request: AiRequest; onDone: () => void }) {
  return (
    <div className="arrived" role="status">
      <h2>
        <Check className="title-icon" aria-hidden="true" /> {request.app} asked {when(request.at)}
      </h2>
      <p className="lede">It got {describeGot(request)}.</p>
      <p className="muted">
        “{request.request}”. Every request from every AI you connect shows like this in <Link to="/activity">Activity</Link>.
      </p>
      <button type="button" className="primary" onClick={onDone}>
        Next <ArrowRight className="button-icon" aria-hidden="true" />
      </button>
    </div>
  );
}

function DifferenceStep() {
  const { data: goals } = useGoals();
  const suggestions = ["What do you know about me and my goals?", ...(goals?.projects ?? []).slice(0, 1).map((p) => `Draft a short update on ${p}`)];
  return <SeeTheDifference suggestions={suggestions} />;
}

export const PRESETS: { id: Preset; title: string; waits: string }[] = [
  {
    id: "personal",
    title: "Personal",
    waits: "Facts, decisions and progress your AI notes go in at once. Rules, preferences and changes to your notes wait for your yes.",
  },
  {
    id: "careful",
    title: "Careful",
    waits: "Files go in at once. Everything else your AIs pick up waits for your yes.",
  },
  {
    id: "regulated",
    title: "Regulated",
    waits: "Nothing a chat or a folder brings goes in without your approval, files and your own preferences included.",
  },
];

function Rhythm({ onDone }: { onDone: () => void }) {
  const { data: policies } = useBrainPolicies();
  const set = useSetBrainPolicies();
  const [preset, setPreset] = useState<Preset | null>(null);
  const current = preset ?? policies?.preset ?? "careful";
  return (
    <section>
      <h1>Your rhythm</h1>
      <p className="lede">What should wait for you? Each change can be undone, whichever you pick.</p>
      <fieldset className="presets">
        <legend className="sr-only">What waits for you</legend>
        {PRESETS.map((p) => (
          <label key={p.id} className={`preset${current === p.id ? " active" : ""}`}>
            <input type="radio" name="preset" value={p.id} checked={current === p.id} onChange={() => setPreset(p.id)} />
            <strong>{p.title}</strong>
            <span className="muted small">{p.waits}</span>
          </label>
        ))}
      </fieldset>
      <p>Catch up when Home says so: usually a few minutes a week.</p>
      <ErrorNote error={set.error} />
      <button
        type="button"
        className="primary big"
        disabled={set.isPending}
        onClick={() => {
          if (preset && preset !== policies?.preset) set.mutate({ preset } as never, { onSuccess: onDone });
          else onDone();
        }}
      >
        Done: open Home
      </button>
    </section>
  );
}

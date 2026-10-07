import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { del, get, post } from "../api/client";
import {
  keys,
  useActors,
  useCaptureSettings,
  useCheckRunners,
  useConnect,
  useDownloadSpeech,
  useInvalidate,
  useProviders,
  useRunners,
  useSetCaptureSettings,
  useSpeech,
} from "../api/hooks";
import type { Actor, Connection, Credential, RunnerStatus } from "../api/types";
import { ConnectBrain } from "../components/ConnectBrain";
import { SignIn } from "../components/RunNow";
import { CopyBlock, Empty, ErrorNote, Field, Section } from "../components/ui";
import { when } from "../lib/format";

/** Whether what is brought in gets its summary and key points as it arrives. */
function Summaries() {
  const { data: settings } = useCaptureSettings();
  const change = useSetCaptureSettings();
  if (!settings) return null;
  return (
    <Section title="Summaries">
      <label className="check">
        <input
          type="checkbox"
          checked={settings.summarize}
          disabled={change.isPending}
          onChange={(event) => change.mutate({ summarize: event.target.checked })}
        />{" "}
        Summarize what you bring in as it arrives
      </label>
      <p className="muted small">
        Claude Code on this computer writes each recording's, transcript's and document's summary and key points, and marks how each fits
        your Brain. Off: summarize one when you choose.
      </p>
      <ErrorNote error={change.error} />
    </Section>
  );
}

/** Talk and recordings become text on this computer: the model, once, at the person's word. */
function SpeechToText() {
  const { data: speech } = useSpeech();
  const download = useDownloadSpeech();
  if (!speech) return null;
  return (
    <Section title="Speech to text on this computer">
      {speech.ready ? (
        <p>Ready: talk and recordings turn into text here with {speech.model}. No audio leaves this computer.</p>
      ) : !speech.installed ? (
        <p>Speech to text isn't installed with this app: talk and recordings are kept, but not turned into text.</p>
      ) : (
        <>
          <p>
            Talk and recordings turn into text on this computer with a local model ({speech.model}, about {speech.about_mb} MB, downloaded
            once). No audio leaves this computer.
          </p>
          <button type="button" className="primary" disabled={speech.downloading || download.isPending} onClick={() => download.mutate()}>
            {speech.downloading ? "Downloading the speech model…" : "Download the speech model"}
          </button>
        </>
      )}
      {speech.error ? <p className="error">{speech.error}</p> : null}
      <ErrorNote error={download.error} />
    </Section>
  );
}

export function ConnectionsPage({ embedded = false }: { embedded?: boolean }) {
  const { data: actors } = useActors();
  const models = (actors ?? []).filter((a) => a.kind === "model");
  const [created, setCreated] = useState<Connection | null>(null);
  return (
    <div className={embedded ? "" : "page"}>
      {embedded ? null : <h1>Connections</h1>}
      <p className="lede">
        Connect each AI app you use to your Brain once: from then on it reads what matters in every chat and saves what it learns
        for your review. Below that, the models that take on the work the app itself starts, like finding what to remember in a
        note. Each of those gets its own revocable token and only ever sees its own queue.
      </p>
      <h2 className="section-title">Your Brain in every chat</h2>
      <ConnectBrain />
      <Runners />
      <SpeechToText />
      <Summaries />
      <h2 className="section-title">Connect a model for scheduled checks</h2>
      <ConnectForm onCreated={setCreated} />
      {created ? <NewConnection connection={created} onDone={() => setCreated(null)} /> : null}
      <Section title="Connected models">
        {models.length ? (
          <ul className="items">
            {models.map((actor) => (
              <ModelRow key={actor.id} actor={actor} />
            ))}
          </ul>
        ) : (
          <Empty why="No models connected yet." />
        )}
      </Section>
    </div>
  );
}

// The CLIs on this computer: each one's setup as three steps, and whether it is ready.
export function Runners() {
  const { data: runners } = useRunners();
  const check = useCheckRunners();
  return (
    <div id="runners">
      <Section
        title="Run the app's AI work on this computer"
        actions={
          <button type="button" onClick={() => void check()}>
            Check again
          </button>
        }
      >
        <p className="muted">
          Two ways, and you can use both. <strong>Run now</strong>: the app starts a CLI on this computer for one job (finding
          what to remember in a note, say) and shows its work as it goes. <strong>On a schedule</strong>: a model you connect
          below checks in with its worker prompt and takes whatever is waiting. Either way, what it suggests waits for you in
          Review.
        </p>
        <ul className="runner-cards">
          {(runners ?? []).map((runner) => (
            <RunnerCard key={runner.id} runner={runner} />
          ))}
        </ul>
      </Section>
    </div>
  );
}

function RunnerCard({ runner }: { runner: RunnerStatus }) {
  const ready = runner.installed && runner.signed_in !== false;
  const state = ready ? (runner.one_click ? "Ready to run tasks" : "Ready") : runner.installed ? "Sign-in needed" : "Not installed";
  return (
    <li className="runner-card">
      <header>
        <h3>{runner.label}</h3>
        <span className={ready ? "chip chip-standing" : "chip chip-stale"}>{state}</span>
      </header>
      <ol className="steps">
        <li className={runner.installed ? "step done" : "step"}>
          <strong>Install</strong>
          {runner.installed ? (
            <span className="muted"> {runner.version ?? "installed"}</span>
          ) : (
            <CopyBlock label="In a terminal on this computer" text={runner.install} />
          )}
        </li>
        <li className={runner.signed_in ? "step done" : "step"}>
          <strong>Sign in</strong>
          {runner.signed_in ? (
            <span className="muted"> signed in</span>
          ) : runner.installed ? (
            <SignIn runner={runner} />
          ) : (
            <span className="muted">
              {" "}
              then <code>{runner.sign_in}</code>
            </span>
          )}
        </li>
        <li className="step">
          <strong>Run</strong>
          <span className="muted">
            {" "}
            {runner.one_click
              ? `"Find what to remember" and reconciling a clash show "Run now with ${runner.label}".`
              : `Connect it below as ${runner.label}, then paste a job's prompt into it (Copy prompt) or schedule its worker prompt.`}
          </span>
        </li>
      </ol>
    </li>
  );
}

function ConnectForm({ onCreated }: { onCreated: (connection: Connection) => void }) {
  const { data: providers } = useProviders();
  const connect = useConnect();
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("claude-code");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const connection = await connect.mutateAsync({ name, provider });
    setName("");
    onCreated(connection);
  }
  return (
    <form className="inline-form" onSubmit={(event) => void submit(event).catch(() => undefined)}>
      <Field label="Name">
        <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Claude Code" />
      </Field>
      <Field label="Platform">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {(providers ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </Field>
      <button type="submit" className="primary" disabled={!name.trim() || connect.isPending}>
        Connect a model
      </button>
      <ErrorNote error={connect.error} />
    </form>
  );
}

function NewConnection({ connection, onDone }: { connection: Connection; onDone: () => void }) {
  return (
    <Section title={`Set up ${connection.actor.name}`} actions={<button onClick={onDone}>Done</button>}>
      <p className="warning">This token is shown once. Put it in the client's settings now; you can issue a new one later.</p>
      <CopyBlock label="Token" text={connection.token} />
      <CopyBlock label={`MCP settings (${connection.setup.file ?? "client settings"})`} text={connection.setup.config} />
      {connection.setup.command ? <CopyBlock label="Or run" text={connection.setup.command} /> : null}
      <p className="muted">{connection.setup.schedule_hint}</p>
      <CopyBlock label="Worker prompt for its scheduled check" text={connection.worker_prompt} />
    </Section>
  );
}

function ModelRow({ actor }: { actor: Actor }) {
  const invalidate = useInvalidate();
  const [error, setError] = useState<unknown>(null);
  const { data: credentials } = useQuery({
    queryKey: [...keys.actors, actor.id, "credentials"],
    queryFn: () => get<Credential[]>(`/api/actors/${actor.id}/credentials`),
  });
  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      await invalidate(keys.actors);
    } catch (caught) {
      setError(caught);
    }
  }
  return (
    <li className="item">
      <div>
        <strong>{actor.name}</strong>
        <span className="muted">
          {" "}
          · {actor.provider} · {actor.last_seen_at ? `last checked in ${when(actor.last_seen_at)}` : "has not checked in yet"}
        </span>
      </div>
      <ul className="list small">
        {(credentials ?? []).map((credential) => (
          <li key={credential.id}>
            Token {credential.token_hint}… <span className="muted">· {credential.revoked_at ? "revoked" : `used ${when(credential.last_used_at) || "never"}`}</span>
            {!credential.revoked_at ? (
              <button type="button" className="link" onClick={() => void run(() => del(`/api/credentials/${credential.id}`))}>
                Revoke
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <div className="row small">
        <button type="button" onClick={() => void run(() => post(`/api/actors/${actor.id}/disable`))}>
          Disconnect
        </button>
      </div>
      <ErrorNote error={error} />
    </li>
  );
}

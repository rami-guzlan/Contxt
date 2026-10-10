// Settings: your AI apps (connected or not, their last request, one step to connect, how to
// test and remove), your goals (the interview, earlier versions, what they steer), approval
// (the presets, with the table by kind and source behind Advanced), this computer (the local
// models, the app's own AI work), backups (back up now, download, restore), and about (the
// workspace, the version, the license in plain words, the first run again).

import { useQuery } from "@tanstack/react-query";
import { Check, Download } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { get, patch } from "../api/client";
import {
  backupUrl,
  keys,
  useAiApps,
  useBackups,
  useBrainPolicies,
  useConnectApp,
  useDownloadModels,
  useGoals,
  useInvalidate,
  useMakeBackup,
  useMe,
  useModels,
  useSetBrainPolicies,
} from "../api/hooks";
import type { AiApp, CaptureOrigin, CaptureType, Preset } from "../api/types";
import { GoalsInterview } from "../components/GoalsInterview";
import { Markdown } from "../components/Markdown";
import { resetTips } from "../components/Tips";
import { CopyBlock, ErrorNote, Field, KeyValues, Loading, Section, Tabs } from "../components/ui";
import { bytes, plural, when } from "../lib/format";
import { PoliciesPage } from "./brain/Policies";
import { entryUrl } from "./brain/shared";
import { ConnectionsPage } from "./Connections";
import { PRESETS } from "./FirstRun";
import { AiWork, EarlierWorkspace } from "./Misc";
import { LocalModels } from "./settings/LocalModels";
import { RedactCloud } from "./settings/Privacy";

const TABS = [
  { id: "apps", label: "Your AI apps" },
  { id: "goals", label: "Your goals" },
  { id: "approval", label: "Approval" },
  { id: "computer", label: "On this computer" },
  { id: "backups", label: "Backups" },
  { id: "about", label: "About" },
] as const;
type Tab = (typeof TABS)[number]["id"];

// Addresses from before: each old tab lands where its content went.
const MOVED: Record<string, Tab> = { connections: "apps", policies: "approval", workspace: "about" };

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab") ?? "";
  if (asked === "start") return <Navigate to="/welcome" replace />;
  const tab: Tab = (TABS.find((t) => t.id === asked)?.id as Tab | undefined) ?? MOVED[asked] ?? "apps";
  return (
    <div className="page settings">
      <h1>Settings</h1>
      <Tabs tour="settings-tabs" tabs={TABS} active={tab} onChange={(next) => setParams(next === "apps" ? {} : { tab: next }, { replace: true })} />
      {tab === "apps" ? <YourApps /> : null}
      {tab === "goals" ? <YourGoals /> : null}
      {tab === "approval" ? <Approval /> : null}
      {tab === "computer" ? <ThisComputer /> : null}
      {tab === "backups" ? <Backups /> : null}
      {tab === "about" ? <About /> : null}
    </div>
  );
}

// ---------------------------------------------------------------- your AI apps

const REMOVE: Record<string, string> = {
  "claude-code": "Run claude mcp remove contxt in a terminal.",
  "claude-desktop": "Delete the contxt entry from its settings file, then restart Claude Desktop.",
  cursor: "Delete the contxt entry from ~/.cursor/mcp.json, then reload Cursor.",
  codex: "Delete the [mcp_servers.contxt] block from ~/.codex/config.toml.",
};

function YourApps() {
  const { data: apps, isLoading, error } = useAiApps();
  if (isLoading) return <Loading />;
  if (!apps) return <ErrorNote error={error} />;
  return (
    <>
      <p className="lede">
        Connect each AI app once. From then on every chat in it reads the part of your Brain a request needs, and you see what each one got in{" "}
        <Link to="/activity">Activity</Link>. No account, no token: it reads your Brain on this computer.
      </p>
      <ul className="app-cards">
        {apps.map((app) => (
          <AppCard key={`${app.client}:${app.label}`} app={app} />
        ))}
      </ul>
      <p className="muted small">
        Any other app that speaks MCP works too: <code>uv run contxt connect</code> prints its setup.
      </p>
    </>
  );
}

function AppCard({ app }: { app: AiApp }) {
  const connect = useConnectApp();
  const [asking, setAsking] = useState(false);
  const [open, setOpen] = useState(!app.connected && app.found);
  const state = app.last_request ? `asked ${when(app.last_request.at)}` : app.connected ? "connected, no request yet" : app.found ? "found on this computer, not connected" : "not found on this computer";
  return (
    <li className="app-card">
      <div className="row">
        <strong>{app.label}</strong>
        <span className="muted small">{state}</span>
        {app.setup ? (
          <button type="button" className="link small" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide setup" : app.connected ? "Setup and removal" : "Connect"}
          </button>
        ) : null}
      </div>
      {app.last_request ? <p className="small muted">Last: “{app.last_request.request}”</p> : null}
      {open && app.setup ? (
        <div className="app-setup">
          {app.setup.command ? <CopyBlock label="Run this once in a terminal" text={app.setup.command} /> : null}
          {app.setup.config ? <CopyBlock label={`Add this to ${app.setup.file ?? "its settings file"}`} text={app.setup.config} /> : null}
          <p className="muted small">{app.setup.note}</p>
          {!app.connected && app.found ? (
            asking ? (
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
            )
          ) : null}
          {connect.data ? <p className="small">{connect.data.changed ? `Added. Quit ${app.label} fully and open it again.` : `${app.label} already had it.`}</p> : null}
          <ErrorNote error={connect.error} />
          <p className="small">
            <strong>Test it:</strong> ask it “what do you know about me?” The request shows in <Link to="/activity">Activity</Link> within seconds.
          </p>
          {REMOVE[app.client] ? (
            <p className="small muted">
              <strong>Remove it:</strong> {REMOVE[app.client]}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

// ---------------------------------------------------------------- your goals

function YourGoals() {
  const { data: goals, isLoading, error } = useGoals();
  const [editing, setEditing] = useState(false);
  if (isLoading) return <Loading />;
  if (!goals) return <ErrorNote error={error} />;
  if (editing || !goals.exists) {
    return (
      <Section title="What is your Brain for?">
        <GoalsInterview onDone={() => setEditing(false)} />
      </Section>
    );
  }
  return (
    <>
      <p className="lede">
        Your goals steer what gets pulled from everything you bring in: each meeting, file and note is sifted against them and your active
        projects. They do not change what each request gets.
      </p>
      <div className="goals-text">
        <Markdown text={goals.text} />
      </div>
      <p className="muted small">{goals.updated ? `Last changed ${goals.updated}. ` : ""}Private to you, versioned like every note.</p>
      <div className="row">
        <button type="button" className="primary" onClick={() => setEditing(true)}>
          Change my answers
        </button>
        <Link className="button" to={entryUrl(goals.id)}>
          Earlier versions
        </Link>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- approval

const TYPE_WORDS: Record<CaptureType, string> = {
  file: "Files",
  fact: "Facts",
  decision: "Decisions",
  progress: "Progress",
  preference: "Preferences",
  rule: "Rules",
  convention: "Who you are",
  change: "Changes to your notes",
};
const ORIGIN_WORDS: Record<CaptureOrigin, string> = { app: "From you", chat: "From your AI's chats", folder: "From your folders" };

function Approval() {
  const { data: policies, isLoading, error } = useBrainPolicies();
  const set = useSetBrainPolicies();
  const [advanced, setAdvanced] = useState(false);
  if (isLoading) return <Loading />;
  if (!policies) return <ErrorNote error={error} />;
  const current = policies.preset ?? "careful";
  const choose = (preset: Preset) => set.mutate({ preset } as never);
  const flip = (type: CaptureType, origin: CaptureOrigin, value: "apply" | "wait") => set.mutate({ capture: { [type]: { [origin]: value } } } as never);
  return (
    <>
      <p className="lede">What goes straight in, and what waits for your yes. Whatever you pick, every change can be undone.</p>
      <fieldset className="presets">
        <legend className="sr-only">Your preset</legend>
        {PRESETS.map((p) => (
          <label key={p.id} className={`preset${current === p.id ? " active" : ""}`}>
            <input type="radio" name="preset" value={p.id} checked={current === p.id} disabled={set.isPending} onChange={() => choose(p.id)} />
            <strong>{p.title}</strong>
            <span className="muted small">{p.waits}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="stack-tight">
        <legend className="sr-only">Changes to your baselines</legend>
        <label className="check">
          <input
            type="checkbox"
            checked={!!policies.revision_delay}
            disabled={set.isPending}
            onChange={(event) => set.mutate({ revision_delay: event.target.checked } as never)}
          />{" "}
          Give me a day before a rule or a must-hold changes
          <span className="muted small"> You decide now; it goes in 24 hours later, and you can cancel it in Catch up until then.</span>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={policies.model_checks !== false}
            disabled={set.isPending}
            onChange={(event) => set.mutate({ model_checks: event.target.checked } as never)}
          />{" "}
          Let my AI double-check disagreements
          <span className="muted small">
            {" "}
            With Claude Code connected, it reads a suggestion beside the notes it may disagree with, up to 60 pairs a day. Without it, words and
            figures are checked alone.
          </span>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={policies.cross_check !== false}
            disabled={set.isPending}
            onChange={(event) => set.mutate({ cross_check: event.target.checked } as never)}
          />{" "}
          Cross-check my beliefs each week
          <span className="muted small">
            {" "}
            Your most used notes and oldest baselines are read against the rest of your Brain; at most one belief to look at a week.
          </span>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={!!policies.challenger}
            disabled={set.isPending}
            onChange={(event) => set.mutate({ challenger: event.target.checked } as never)}
          />{" "}
          Let a challenger argue against my beliefs
          <span className="muted small">
            {" "}
            Once a week, Claude Code looks for current evidence on the web against a few of your beliefs, each only as a claim to test. It uses some
            of your quota and changes nothing: it raises challenges for you to settle.
          </span>
        </label>
        <RedactCloud />
      </fieldset>
      {set.isSuccess ? (
        <p className="small" role="status">
          <Check className="button-icon" aria-hidden="true" /> Saved, with an undo point.
        </p>
      ) : null}
      <ErrorNote error={set.error} />
      <button type="button" className="link" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
        {advanced ? "Hide the details" : "Advanced: by kind and source"}
      </button>
      {advanced && policies.capture ? (
        <>
          <table className="table capture-table">
            <caption className="sr-only">What goes straight in, by kind and source</caption>
            <thead>
              <tr>
                <th scope="col">Kind</th>
                {(policies.capture_origins ?? (["app", "chat", "folder"] as CaptureOrigin[])).map((origin) => (
                  <th key={origin} scope="col">
                    {ORIGIN_WORDS[origin]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(policies.capture_types ?? (Object.keys(policies.capture) as CaptureType[])).map((type) => (
                <tr key={type}>
                  <th scope="row">{TYPE_WORDS[type] ?? type}</th>
                  {(policies.capture_origins ?? (["app", "chat", "folder"] as CaptureOrigin[])).map((origin) => {
                    const value = policies.capture?.[type]?.[origin] ?? "wait";
                    return (
                      <td key={origin}>
                        <select
                          aria-label={`${TYPE_WORDS[type] ?? type} ${ORIGIN_WORDS[origin].toLowerCase()}`}
                          value={value}
                          disabled={set.isPending}
                          onChange={(event) => flip(type, origin, event.target.value as "apply" | "wait")}
                        >
                          <option value="apply">Straight in</option>
                          <option value="wait">Waits for you</option>
                        </select>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Whatever this says, something that would replace or disagree with a note, nearly repeats one, or holds private detail waits for you.
          </p>
          <PoliciesPage />
        </>
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------- this computer

function MatchingModel() {
  const { data } = useModels();
  const download = useDownloadModels();
  const m = data?.matching;
  if (!m || !m.enabled) return null;
  return (
    <Section title="Matching by meaning">
      {m.present ? (
        <p>Ready: your Brain matches requests to notes by meaning, with {m.model} on this computer.</p>
      ) : (
        <>
          <p>
            Your Brain matches requests by words until its local model is here (about {m.about_mb ?? 70} MB, downloaded once). Then it matches by
            meaning, as it does in every chat. Nothing you write leaves this computer.
          </p>
          <button type="button" className="primary" disabled={m.downloading || download.isPending} onClick={() => download.mutate()}>
            {m.downloading || download.isPending ? "Downloading…" : "Download the model"}
          </button>
        </>
      )}
      {m.error ? <p className="error">{m.error}</p> : null}
      <ErrorNote error={download.error} />
    </Section>
  );
}

function ThisComputer() {
  return (
    <>
      <MatchingModel />
      <LocalModels />
      <AiWork />
      <ConnectionsPage embedded computer />
    </>
  );
}

// ---------------------------------------------------------------- backups

function Backups() {
  const { data: backups } = useBackups();
  const make = useMakeBackup();
  return (
    <>
      <Section title="Back up now">
        <p>One archive with everything: the app's records and files, and your Brain with its original documents.</p>
        <button type="button" className="primary" disabled={make.isPending} onClick={() => make.mutate()}>
          {make.isPending ? "Backing up…" : "Back up now"}
        </button>
        {make.data ? (
          <p className="small" role="status">
            Saved {make.data.name}: {plural(make.data.records, "record")}, {plural(make.data.files, "file")}, {plural(make.data.brain_files, "Brain file")}.{" "}
            <a href={backupUrl(make.data.name)} download>
              Download it
            </a>
          </p>
        ) : null}
        <ErrorNote error={make.error} />
        {backups?.length ? (
          <ul className="list compact-list">
            {backups.map((b) => (
              <li key={b.name}>
                <a href={backupUrl(b.name)} download>
                  <Download className="button-icon" aria-hidden="true" /> {b.name}
                </a>{" "}
                <span className="muted small">
                  {bytes(b.size)} · {when(b.at)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </Section>
      <Section title="From a terminal">
        <CopyBlock label="Back up" text="uv run contxt backup --with-brain" />
        <CopyBlock label="Restore into an empty folder" text="uv run contxt restore <the backup's file> --brain-dir <a new folder>" />
        <p className="muted small">Restoring never writes over a workspace that has data, and checks every file against its fingerprint.</p>
      </Section>
      <EarlierWorkspace />
    </>
  );
}

// ---------------------------------------------------------------- about

function About() {
  const { data: me } = useMe();
  const invalidate = useInvalidate();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => get<{ version: string; schema_revision: string; brain: boolean }>("/api/health"),
  });
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [tips, setTips] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await patch("/api/workspace", { name: name || undefined, timezone: timezone || undefined });
      setSaved(true);
      await invalidate(keys.me, keys.home);
    } catch (caught) {
      setError(caught);
    }
  }
  return (
    <>
      <Section title="This workspace">
        <form className="inline-form" onSubmit={save}>
          <Field label="Name">
            <input placeholder={me?.workspace.name} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Time zone" hint="Such as America/New_York.">
            <input placeholder={me?.workspace.timezone} value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </Field>
          <button type="submit" className="primary">
            Save
          </button>
          {saved ? <span className="muted">Saved.</span> : null}
          <ErrorNote error={error} />
        </form>
      </Section>
      <Section title="Getting started">
        <div className="row">
          <Link className="button" to="/welcome">
            Show the first run again
          </Link>
          <button
            type="button"
            onClick={() => {
              resetTips();
              setTips(true);
            }}
          >
            {tips ? "Tips will show again" : "Show the tips again"}
          </button>
        </div>
      </Section>
      <Section title="About Contxt">
        <KeyValues
          rows={[
            ["Version", health?.version],
            ["Database revision", health?.schema_revision],
            ["Brain connected", health ? (health.brain ? "yes" : "no") : ""],
            ["Signed in as", me ? `${me.name} (${me.kind})` : ""],
          ]}
        />
        <p className="small">
          Source-available under the PolyForm Shield license: free to use, change and share, for anything except a product that competes with
          Contxt.
        </p>
      </Section>
    </>
  );
}

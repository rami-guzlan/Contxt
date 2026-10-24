// Agent orchestrators in a project (v4 orcVals, AGENTS.md 8b): the cards with Run and a steer,
// the editor (goal, CLI, model, how it starts, agents with a profile, a role and how each
// works), the gate card with the owner's yes, the agent tasks, the activity timeline, Outputs
// grouped by orchestrator and run with the FINAL OUTPUT pinned on top, and the auto sheets.
// Everything comes from /api/projects/{id}/orchestrators; nothing here is example data.

import { useState } from "react";

import { useWorkAgents } from "../../api/hooks";
import { css, cx } from "../css";
import {
  type AgentSpecIn,
  type AgentTask,
  type CliChoice,
  type Gate,
  type Orchestrator,
  type OrchestratorIn,
  type OrchestratorRun,
  type TimelineEvent,
  type WorksBy,
  isLive,
  useDecideGate,
  useOrchestratorOutputs,
  useOrchestrators,
  useOrchestratorSheets,
  useOrchestratorTimeline,
  useRunOrchestrator,
  useSaveOrchestrator,
} from "../hooks/orchestrators";
import { Btn, Empty, Failure, Later, Loading, S, when } from "../ui";

export type Go = "outputs" | "sheet" | "cards";

const ERR = "font:400 13px Geist;color:oklch(0.55 0.17 28)";
const CARD = "padding:18px 20px;border-radius:20px;background:var(--surface);box-shadow:var(--shadow);display:flex;flex-direction:column;gap:12px";
const LABEL = "font:500 11.5px Geist;color:var(--muted);width:72px";
const INPUT = "border:1px solid var(--line2);border-radius:12px;padding:9px 12px;outline:none;resize:vertical;background:var(--bg);color:var(--ink);font:400 14px/1.5 Geist";
const TAG = "font:500 10.5px 'Geist Mono';letter-spacing:.05em;padding:2px 7px;border-radius:6px;background:var(--soft);color:var(--ink2)";

const RUN_WORDS: Record<string, [string, string]> = {
  running: ["Running…", "oklch(0.74 0.12 80 / .25)"],
  waiting: ["Waiting for you", "oklch(0.74 0.12 35 / .24)"],
  done: ["Done", "oklch(0.62 0.14 150 / .2)"],
  stopped: ["Stopped · run again", "var(--soft)"],
};
const AGENT_WORDS: Record<string, [string, string]> = {
  queued: ["Queued", "var(--soft)"],
  working: ["Working…", "oklch(0.74 0.12 80 / .25)"],
  waiting: ["Needs you", "oklch(0.74 0.12 35 / .24)"],
  reported: ["Reported", "oklch(0.62 0.14 150 / .2)"],
  stopped: ["Stopped", "var(--soft)"],
  idle: ["Ready", "var(--soft)"],
};
const HOW: Record<WorksBy, [string, string]> = {
  computer: ["Computer use", "Takes over this computer's screen and uses apps you're already signed in to."],
  mcp: ["CLI + MCP bridge", "Uses the MCP tools already connected in its CLI."],
  files: ["Files only", "Reads the packet and files Gnomon hands it. No other tools."],
};
const KIND: Record<string, [string, number]> = {
  plan: ["Plan", 265],
  spawn: ["Spawned", 210],
  agent: ["Agent", 250],
  report: ["Report", 150],
  sheet: ["Sheet", 300],
  proposal: ["Proposal", 35],
  final: ["Final", 120],
  approval: ["Needs you", 25],
  stopped: ["Stopped", 80],
};
const FILTERS: [string, string[] | null][] = [
  ["All", null],
  ["Agents", ["spawn", "agent", "report"]],
  ["Outputs", ["report", "final"]],
  ["Sheet", ["sheet"]],
  ["Proposals", ["proposal"]],
  ["Approvals", ["approval"]],
];

export const human = (name: string) => {
  const words = name.replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
};
const initials = (name: string) =>
  human(name)
    .split(" ")
    .map((w) => w[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
const hue = (name: string) => [...name].reduce((n, c) => (n * 31 + c.charCodeAt(0)) % 360, 7);
const face = (name: string, size = 30) =>
  `width:${size}px;height:${size}px;border-radius:10px;flex:none;display:flex;align-items:center;justify-content:center;font:500 11px Geist;background:oklch(0.74 0.1 ${hue(name)} / .22);color:var(--ink)`;
const pill = ([, bg]: [string, string]) => `padding:3px 10px;border-radius:99px;font:500 11.5px Geist;white-space:nowrap;color:var(--ink);background:${bg}`;
const chip = (on: boolean) =>
  `padding:5px 11px;border-radius:99px;font:${on ? 500 : 400} 12px Geist;cursor:pointer;` +
  (on ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:transparent;color:var(--ink);border:1px solid var(--line2)");

const runWords = (k: string): [string, string] => RUN_WORDS[k] ?? ["Done", "oklch(0.62 0.14 150 / .2)"];
const agentWords = (k: string): [string, string] => AGENT_WORDS[k] ?? ["Queued", "var(--soft)"];

function Pill({ words }: { words: [string, string] }) {
  return <span style={css(pill(words))}>{words[0]}</span>;
}

function Problem({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <span role="alert" style={css(ERR)}>
      {error instanceof Error ? error.message : String(error)}
    </span>
  );
}

function cliLabel(clis: CliChoice[], cli: string) {
  return clis.find((c) => c.id === cli)?.label ?? cli;
}
function modelLabel(clis: CliChoice[], cli: string, model: string) {
  return clis.find((c) => c.id === cli)?.models.find((m) => m.id === model)?.label ?? model;
}

// ------------------------------------------------------------------ the cards and the editor

export function OrchestratorsPanel({ projectId, onGo }: { projectId: string; onGo: (go: Go, orchestrator?: string) => void }) {
  const overview = useOrchestrators(projectId);
  const [open, setOpen] = useState<string | null>(null); // an orchestrator's id, or "new"
  const clis = overview.data?.clis ?? [];
  const list = overview.data?.orchestrators ?? [];
  const editing = open === "new" ? null : list.find((o) => o.id === open) ?? null;

  return (
    <div style={css("display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:3px;max-width:700px")}>
          <span style={css("font:500 15px Geist")}>Agent orchestrators</span>
          <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>
            Give an orchestrator a goal. It spawns agents, each with a profile and a role that owns one piece of the work. They do the work through your CLIs and report back; the orchestrator fills its own Context sheet and puts what they made in Outputs.
          </span>
        </div>
        <Btn kind="primarySm" onClick={() => setOpen(open === "new" ? null : "new")}>
          New orchestrator
        </Btn>
      </div>
      {overview.isLoading ? (
        <Loading what="Loading orchestrators" />
      ) : overview.error ? (
        <Failure error={overview.error} retry={() => void overview.refetch()} />
      ) : list.length === 0 && open !== "new" ? (
        <Empty title="No orchestrators here yet">Make one with a goal and the agents it spawns. It runs on your CLIs, on this computer.</Empty>
      ) : (
        <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,420px),1fr));gap:14px")}>
          {list.map((o) => (
            <OrchestratorCard key={o.id} o={o} clis={clis} projectId={projectId} selected={open === o.id} onOpen={() => setOpen(open === o.id ? null : o.id)} onGo={onGo} />
          ))}
        </div>
      )}
      {open && overview.data ? <Editor key={open} projectId={projectId} o={editing} clis={clis} onClose={() => setOpen(null)} onSaved={(id) => setOpen(id)} /> : null}
    </div>
  );
}

function OrchestratorCard({
  o,
  clis,
  projectId,
  selected,
  onOpen,
  onGo,
}: {
  o: Orchestrator;
  clis: CliChoice[];
  projectId: string;
  selected: boolean;
  onOpen: () => void;
  onGo: (go: Go, orchestrator?: string) => void;
}) {
  const run = useRunOrchestrator(projectId);
  const [steer, setSteer] = useState("");
  const r = o.latest_run;
  const busy = r?.shown === "running" || r?.shown === "waiting" || run.isPending;
  const start = () => {
    if (busy) return;
    run.mutate({ id: o.id, steer: steer.trim() }, { onSuccess: () => setSteer("") });
  };
  const status = r ? runWords(r.shown) : (["Ready", "var(--soft)"] as [string, string]);
  return (
    <div style={cx(CARD, selected ? "outline:2px solid var(--ink)" : "")}>
      <div style={css("display:flex;align-items:flex-start;gap:10px")}>
        <div style={css("display:flex;flex-direction:column;gap:3px;flex:1;min-width:0")}>
          <span style={css("font:400 20px/1.3 Newsreader")}>{o.name}</span>
          <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{o.goal || "No goal yet. Edit it to give it one."}</span>
        </div>
        <Pill words={status} />
      </div>
      <div style={css("display:flex;flex-direction:column;gap:6px")}>
        {o.agents.length === 0 ? <span style={css(S.small)}>No agents yet. Edit it to add the agents it spawns.</span> : null}
        {o.agents.map((a) => {
          const state = r ? r.agents[a.id]?.shown ?? "queued" : "idle";
          return (
            <div key={a.id} style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
              <span aria-hidden style={css(face(a.profile))}>
                {initials(a.profile)}
              </span>
              <div style={css("display:flex;flex-direction:column;gap:1px;flex:1;min-width:160px")}>
                <span style={css("font:500 13px Geist")}>
                  {human(a.profile)} · <span style={css("font-weight:400;color:var(--ink2)")}>owns {a.short}</span>
                </span>
                <span style={css("font:400 11.5px Geist;color:var(--muted)")}>
                  {HOW[a.works_by][0]} · {cliLabel(clis, a.cli)} · {modelLabel(clis, a.cli, a.model)}
                </span>
              </div>
              <Pill words={agentWords(state)} />
            </div>
          );
        })}
      </div>
      {r?.shown === "stopped" && r.note ? <span style={css("font:400 13px/1.5 Geist;color:oklch(0.5 0.15 28)")}>Why it stopped: {r.note}</span> : null}
      {r
        ? Object.entries(r.agents)
            .filter(([, s]) => s.shown === "waiting" && s.note)
            .map(([id, s]) => (
              <span key={id} style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>
                {human(r.spec.agents.find((a) => a.id === id)?.profile ?? id)} needs you: {s.note}
              </span>
            ))
        : null}
      <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding-top:4px;border-top:1px solid var(--line)")}>
        <input
          aria-label={`Steer the next run of ${o.name}`}
          value={steer}
          onChange={(e) => setSteer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") start();
          }}
          placeholder="Steer this run (optional)"
          style={css("flex:1;min-width:180px;border:1px solid var(--line2);border-radius:99px;padding:8px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 13.5px Geist;margin-top:10px")}
        />
        <button type="button" onClick={onOpen} style={css("padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink);cursor:pointer;margin-top:10px")}>
          {selected ? "Close" : "Edit"}
        </button>
        <button
          type="button"
          onClick={start}
          disabled={busy || !o.agents.length || !o.goal.trim()}
          style={css("padding:7px 14px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 12.5px Geist;cursor:pointer;margin-top:10px")}
        >
          {run.isPending ? "Starting…" : r?.shown === "running" ? "Running…" : "Run"}
        </button>
      </div>
      <Problem error={run.error} />
      {r ? r.gates.filter((g) => g.status === "pending").map((g) => <GateCard key={g.id} projectId={projectId} run={r} gate={g} />) : null}
      <div style={css("display:flex;gap:14px;flex-wrap:wrap")}>
        <button type="button" onClick={() => onGo("sheet")} style={css("border:0;background:transparent;padding:0;font:500 12.5px Geist;color:var(--ink2);cursor:pointer")}>
          Sheet: {o.sheet} →
        </button>
        <button type="button" onClick={() => onGo("outputs", o.id)} style={css("border:0;background:transparent;padding:0;font:500 12.5px Geist;color:var(--ink2);cursor:pointer")}>
          Outputs →
        </button>
      </div>
    </div>
  );
}

function GateCard({ projectId, run, gate }: { projectId: string; run: OrchestratorRun; gate: Gate }) {
  const decide = useDecideGate(projectId);
  const who = gate.profile ? `${human(gate.profile)} asks: ` : "";
  return (
    <div role="group" aria-label="Waiting for your yes" style={css("display:flex;flex-direction:column;gap:8px;padding:10px 12px;border-radius:12px;border:1.5px dashed oklch(0.68 0.14 35)")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:400 13px/1.45 Geist;flex:1;min-width:200px")}>
          {who}
          {gate.what}. It waits for your yes: the orchestrator recommends, it doesn't act on its own.
        </span>
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => decide.mutate({ run: run.id, gate: gate.id, approve: true, quote: gate.approve_label })}
          style={css("padding:7px 14px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 12.5px Geist;cursor:pointer")}
        >
          {gate.approve_label}
        </button>
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => decide.mutate({ run: run.id, gate: gate.id, approve: false, quote: "Not now" })}
          style={css("padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink);cursor:pointer")}
        >
          Not now
        </button>
      </div>
      {gate.tools.length ? <span style={css(S.small)}>Only after your yes, it may use: {gate.tools.join(", ")}</span> : null}
      <Problem error={decide.error} />
    </div>
  );
}

type Draft = Omit<OrchestratorIn, "agents"> & { agents: (AgentSpecIn & { key: string })[] };

let seq = 0;
const key = () => `k${++seq}`;

function draftOf(o: Orchestrator | null, clis: CliChoice[]): Draft {
  if (!o) {
    const cli = clis[0];
    return { name: "New orchestrator", goal: "", cli: cli?.id ?? "claude", model: cli?.models[0]?.id ?? "", trigger: "gnomon", agents: [] };
  }
  return {
    name: o.name,
    goal: o.goal,
    cli: o.cli,
    model: o.model,
    trigger: o.trigger,
    expected_version: o.version,
    agents: o.agents.map((a) => ({ key: key(), id: a.id, profile: a.profile, role: a.role, works_by: a.works_by, cli: a.cli, model: a.model, tools: a.tools })),
  };
}

function Editor({
  projectId,
  o,
  clis,
  onClose,
  onSaved,
}: {
  projectId: string;
  o: Orchestrator | null;
  clis: CliChoice[];
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const save = useSaveOrchestrator(projectId);
  const run = useRunOrchestrator(projectId);
  const agents = useWorkAgents();
  const [d, setD] = useState<Draft>(() => draftOf(o, clis));
  const [steer, setSteer] = useState("");
  const [newProfile, setNewProfile] = useState("");
  const known = (agents.data ?? []).map((a) => a.name);
  const profiles = [...new Set([...known, ...d.agents.map((a) => a.profile)])];
  const models = (cli: string) => clis.find((c) => c.id === cli)?.models ?? [];
  const slug = d.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "orchestrator";
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }));
  const setAgent = (i: number, patch: Partial<AgentSpecIn>) => setD((x) => ({ ...x, agents: x.agents.map((a, n) => (n === i ? { ...a, ...patch } : a)) }));
  const add = (profile: string, isNew = false) =>
    setD((x) => ({
      ...x,
      agents: [...x.agents, { key: key(), profile, new_profile: isNew, role: "Owns ", works_by: "files", cli: clis[0]?.id ?? "claude", model: clis[0]?.models[1]?.id ?? clis[0]?.models[0]?.id ?? "", tools: [] }],
    }));

  function body(): OrchestratorIn {
    return { ...d, agents: d.agents.map(({ key: _key, ...a }) => a) };
  }
  function saveIt(then?: (saved: Orchestrator) => void) {
    save.mutate(
      { id: o?.id, spec: body() },
      {
        onSuccess: (saved) => {
          if (then) then(saved);
          else onSaved(saved.id);
        },
      },
    );
  }
  function runIt() {
    saveIt((saved) => {
      onSaved(saved.id);
      run.mutate({ id: saved.id, steer: steer.trim() });
    });
  }

  return (
    <div role="region" aria-label="Orchestrator editor" style={css("background:var(--surface);box-shadow:var(--shadow);border-radius:22px;padding:20px 22px;display:flex;flex-direction:column;gap:16px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <input
          aria-label="Orchestrator name"
          value={d.name}
          onChange={(e) => set({ name: e.target.value })}
          style={css("flex:1;min-width:220px;border:0;border-bottom:1px dashed var(--line2);outline:none;background:transparent;color:var(--ink);font:400 24px/1.3 Newsreader;padding:2px 0")}
        />
        <Btn kind="primarySm" onClick={() => saveIt()} disabled={save.isPending || !d.name.trim()}>
          {save.isPending ? "Saving…" : "Save"}
        </Btn>
        <Btn onClick={onClose}>Done</Btn>
      </div>
      <label style={css("display:flex;flex-direction:column;gap:6px")}>
        <span style={css("font:500 11.5px Geist;color:var(--muted)")}>Goal</span>
        <textarea value={d.goal} onChange={(e) => set({ goal: e.target.value })} rows={2} style={css(INPUT + ";font-size:15px")} />
      </label>
      <div role="group" aria-label="Runs on" style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
        <span style={css(LABEL)}>Runs on</span>
        {clis.map((c) => (
          <button key={c.id} type="button" aria-pressed={d.cli === c.id} onClick={() => set({ cli: c.id, model: c.models[0]?.id ?? "" })} style={css(chip(d.cli === c.id))}>
            {c.label}
          </button>
        ))}
        <span style={css(S.small)}>
          Local model
          <Later />
        </span>
      </div>
      <div role="group" aria-label="Model" style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
        <span style={css(LABEL)}>Model</span>
        {models(d.cli).map((m) => (
          <button key={m.id} type="button" aria-pressed={d.model === m.id} onClick={() => set({ model: m.id })} style={css(chip(d.model === m.id))}>
            {m.label}
          </button>
        ))}
      </div>
      {clis.find((c) => c.id === d.cli)?.one_click === false ? (
        <span style={css(S.small)}>{cliLabel(clis, d.cli)} runs from a copied prompt for now: a run on it waits for you to start it.</span>
      ) : null}
      <div role="group" aria-label="Starts" style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
        <span style={css(LABEL)}>Starts</span>
        {(
          [
            ["gnomon", "From Gnomon"],
            ["ai", "From your AI"],
          ] as const
        ).map(([id, l]) => (
          <button key={id} type="button" aria-pressed={d.trigger === id} onClick={() => set({ trigger: id })} style={css(chip(d.trigger === id))}>
            {l}
          </button>
        ))}
        <span style={css(S.small)}>
          On a schedule
          <Later />
        </span>
      </div>
      {d.trigger === "ai" ? (
        <div style={css("padding:10px 14px;border-radius:12px;background:var(--code);font:400 12.5px/1.6 'Geist Mono';color:#d8d5cd")}>
          you, in your AI › “run {slug}, and focus on paid”
          <br />→ orchestrators_run("{slug}", project="{projectId}", steer="focus on paid") · same run, same timeline
        </div>
      ) : null}
      <div style={css("display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:14px;background:var(--soft);flex-wrap:wrap")}>
        <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.05em;color:var(--ink2)")}>AUTO SHEET</span>
        <span style={css("font:400 13.5px/1.45 Geist;flex:1;min-width:220px")}>
          {o?.sheet ?? `${d.name} · sheet`} · made for this orchestrator in Project › Context. Columns: What · Value · Source · Agent · As of. Every cell keeps its source and the agent that found it.
        </span>
      </div>
      <div style={css("display:flex;flex-direction:column;gap:10px")}>
        <span style={css("font:500 14px Geist")}>Agents it spawns</span>
        {d.agents.map((a, i) => (
          <div key={a.key} role="group" aria-label={`Agent ${human(a.profile)}`} style={css("padding:14px 16px;border-radius:16px;border:1px solid var(--line);display:flex;flex-direction:column;gap:10px")}>
            <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
              <span aria-hidden style={css(face(a.profile, 32))}>
                {initials(a.profile)}
              </span>
              <span style={css("font:500 14px Geist;flex:1;min-width:160px")}>{human(a.profile)}</span>
              {a.new_profile && !known.includes(a.profile) ? <span style={css(TAG)}>NEW · SAVED TO AGENTS</span> : null}
              <button
                type="button"
                aria-label={`Remove ${human(a.profile)}`}
                onClick={() => setD((x) => ({ ...x, agents: x.agents.filter((_, n) => n !== i) }))}
                style={css("border:0;background:transparent;color:var(--faint);font:400 15px Geist;padding:0 4px;cursor:pointer")}
              >
                ×
              </button>
            </div>
            <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
              <span style={css(LABEL)}>Profile</span>
              {profiles.map((p) => (
                <button key={p} type="button" aria-pressed={a.profile === p} onClick={() => setAgent(i, { profile: p, new_profile: !known.includes(p) })} style={css(chip(a.profile === p))}>
                  {human(p)}
                </button>
              ))}
            </div>
            <label style={css("display:flex;flex-direction:column;gap:4px")}>
              <span style={css("font:500 11.5px Geist;color:var(--muted)")}>Role · the piece it owns</span>
              <textarea value={a.role} onChange={(e) => setAgent(i, { role: e.target.value })} rows={2} style={css(INPUT)} />
            </label>
            <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
              <span style={css(LABEL)}>Works by</span>
              {(Object.keys(HOW) as WorksBy[]).map((h) => (
                <button key={h} type="button" aria-pressed={a.works_by === h} onClick={() => setAgent(i, { works_by: h })} style={css(chip(a.works_by === h))}>
                  {HOW[h][0]}
                </button>
              ))}
            </div>
            <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
              <span style={css(LABEL)}>CLI</span>
              {clis.map((c) => (
                <button key={c.id} type="button" aria-pressed={a.cli === c.id} onClick={() => setAgent(i, { cli: c.id, model: c.models[0]?.id ?? "" })} style={css(chip(a.cli === c.id))}>
                  {c.label}
                </button>
              ))}
            </div>
            <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
              <span style={css(LABEL)}>Model</span>
              {models(a.cli).map((m) => (
                <button key={m.id} type="button" aria-pressed={a.model === m.id} onClick={() => setAgent(i, { model: m.id })} style={css(chip(a.model === m.id))}>
                  {m.label}
                </button>
              ))}
            </div>
            {a.works_by === "mcp" ? (
              <label style={css("display:flex;flex-direction:column;gap:4px")}>
                <span style={css("font:500 11.5px Geist;color:var(--muted)")}>Connected tools it may use, by full name, comma-separated</span>
                <input
                  value={a.tools.join(", ")}
                  onChange={(e) =>
                    setAgent(i, {
                      tools: e.target.value
                        .split(",")
                        .map((t) => t.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="mcp__buffer__list_posts, mcp__buffer__create_post"
                  style={css(INPUT)}
                />
                <span style={css(S.small)}>Tools that post, send or spend are kept back: the agent gets them only for an action you said yes to.</span>
              </label>
            ) : null}
            <span style={css("font:400 12.5px/1.45 Geist;color:var(--ink2)")}>{HOW[a.works_by][1]}</span>
          </div>
        ))}
        <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:12px 14px;border-radius:14px;border:1.5px dashed var(--line2)")}>
          <span style={css("font:500 13px Geist")}>Spawn an agent</span>
          {agents.isLoading ? <span style={css(S.small)}>Loading profiles…</span> : null}
          {agents.error ? <span style={css(S.small)}>Profiles couldn't be read.</span> : null}
          {known.slice(0, 4).map((p) => (
            <Btn key={p} onClick={() => add(p)}>
              + {human(p)}
            </Btn>
          ))}
          <input
            aria-label="New profile name"
            value={newProfile}
            onChange={(e) => setNewProfile(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newProfile.trim()) {
                e.preventDefault();
                add(newProfile.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""), true);
                setNewProfile("");
              }
            }}
            placeholder="Or name a new profile"
            style={css("flex:1;min-width:160px;border:1px solid var(--line2);border-radius:99px;padding:7px 12px;outline:none;background:var(--bg);color:var(--ink);font:400 13px Geist")}
          />
          <Btn
            kind="primarySm"
            disabled={!newProfile.trim()}
            onClick={() => {
              add(newProfile.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""), true);
              setNewProfile("");
            }}
          >
            Create and add
          </Btn>
        </div>
        {d.agents.some((a) => a.new_profile && !known.includes(a.profile)) ? <span style={css(S.small)}>New profiles are saved to Agents when you save.</span> : null}
      </div>
      <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
        <input
          aria-label="Steer this run from the start"
          value={steer}
          onChange={(e) => setSteer(e.target.value)}
          placeholder="Steer this run from the start (optional)"
          style={css("flex:1;min-width:220px;border:1px solid var(--line2);border-radius:99px;padding:9px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 14px Geist")}
        />
        <Btn kind="primary" onClick={runIt} disabled={save.isPending || run.isPending || !d.agents.length || !d.goal.trim()}>
          {run.isPending ? "Starting…" : "Save and run"}
        </Btn>
      </div>
      {!d.agents.length ? <span style={css(S.small)}>Spawn at least one agent first.</span> : null}
      <Problem error={save.error} />
      <Problem error={run.error} />
      {save.isSuccess && !save.isPending ? <span role="status" style={css(S.small)}>Saved.</span> : null}
      <span style={css("font:400 12px/1.5 Geist;color:var(--muted)")}>
        Each agent runs through its CLI on this computer, with the tools already connected there. Computer use takes over the screen while it works. Anything customer-facing, or that spends money, waits for your yes.
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ agent tasks and activity

export function AgentTasks({ projectId }: { projectId: string }) {
  const overview = useOrchestrators(projectId);
  const clis = overview.data?.clis ?? [];
  const rows = overview.data?.agent_tasks ?? [];
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:500 15px Geist")}>Agent tasks</span>
        <span style={css("font:400 12.5px Geist;color:var(--muted)")}>What each agent owns in the latest run</span>
      </div>
      <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:4px 20px")}>
        {overview.isLoading ? <Loading what="Loading agent tasks" /> : null}
        {overview.error ? <Failure error={overview.error} retry={() => void overview.refetch()} /> : null}
        {rows.map((t) => (
          <AgentTaskRow key={`${t.run_id}-${t.kind}-${t.agent_id}`} t={t} clis={clis} />
        ))}
        {overview.data && rows.length === 0 ? <div style={css("padding:16px 0;font:400 14px Geist;color:var(--muted)")}>No agent work yet. Run an orchestrator.</div> : null}
      </div>
    </div>
  );
}

function AgentTaskRow({ t, clis }: { t: AgentTask; clis: CliChoice[] }) {
  const words = t.kind === "orchestrator" ? runWords(t.state) : agentWords(t.state);
  const meta =
    t.kind === "orchestrator"
      ? ["Orchestrator", cliLabel(clis, t.cli), modelLabel(clis, t.cli, t.model), t.run_id]
      : [human(t.profile), t.orchestrator, t.run_id, HOW[t.works_by as WorksBy]?.[0] ?? ""];
  return (
    <div style={css("display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
      {t.kind === "orchestrator" ? (
        <span aria-hidden style={css("width:30px;height:30px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font:500 10px Geist;background:var(--ink);color:var(--bg)")}>
          OR
        </span>
      ) : (
        <span aria-hidden style={css(face(t.profile))}>
          {initials(t.profile)}
        </span>
      )}
      <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:400 14.5px/1.4 Geist")}>{t.title}</span>
        <span style={css("font:400 12px Geist;color:var(--muted)")}>
          {meta.filter(Boolean).join(" · ")}
          {t.task_id ? ` · ${t.task_id}` : ""}
        </span>
        {t.note ? <span style={css("font:400 12px Geist;color:var(--ink2)")}>{t.note}</span> : null}
      </div>
      <Pill words={words} />
    </div>
  );
}

export function OrchestratorActivity({ projectId, onGo }: { projectId: string; onGo: (go: Go) => void }) {
  const overview = useOrchestrators(projectId);
  const timeline = useOrchestratorTimeline(projectId, isLive(overview.data));
  const [filter, setFilter] = useState("All");
  const all = timeline.data ?? [];
  const kinds = FILTERS.find(([l]) => l === filter)?.[1] ?? null;
  const shown = all.filter((e) => !kinds || kinds.includes(e.kind));
  return (
    <div style={css("position:sticky;top:24px;background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px 20px;display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px")}>
        <span style={css("font:500 15px Geist")}>Orchestrator activity</span>
        <span style={css("font:400 12px Geist;color:var(--muted)")}>{all.length ? `${all.length} events` : ""}</span>
      </div>
      <div role="group" aria-label="Show" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
        {FILTERS.map(([l]) => (
          <button key={l} type="button" aria-pressed={filter === l} onClick={() => setFilter(l)} style={css(chip(filter === l))}>
            {l}
          </button>
        ))}
        <span style={css(S.small)}>
          Lore
          <Later />
        </span>
      </div>
      <div style={css("display:flex;flex-direction:column;max-height:680px;overflow:auto")}>
        {timeline.isLoading ? <Loading what="Loading activity" /> : null}
        {timeline.error ? <Failure error={timeline.error} retry={() => void timeline.refetch()} /> : null}
        {shown.map((e) => (
          <ActivityRow key={e.id} e={e} onGo={onGo} />
        ))}
        {timeline.data && shown.length === 0 ? (
          <span style={css("font:400 13px/1.5 Geist;color:var(--muted);padding:10px 0")}>
            Nothing yet. Run an orchestrator and every step shows here: the plan, each agent it spawned, what they reported, the sheet it filled, proposals and approvals.
          </span>
        ) : null}
      </div>
    </div>
  );
}

function ActivityRow({ e, onGo }: { e: TimelineEvent; onGo: (go: Go) => void }) {
  const [label, h] = KIND[e.kind] ?? ["Event", 80];
  const go = e.go === "outputs" ? "See in Outputs →" : e.go === "sheet" ? "See the sheet →" : e.go === "cards" ? "Open in Catch up →" : "";
  return (
    <div style={css("display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line)")}>
      <div style={css("padding-top:5px")}>
        <span aria-hidden style={css(`width:8px;height:8px;border-radius:50%;display:block;background:oklch(0.66 0.12 ${h})`)} />
      </div>
      <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:3px")}>
        <div style={css("display:flex;gap:8px;align-items:baseline;flex-wrap:wrap")}>
          <span style={css(`font:500 11px Geist;padding:2px 8px;border-radius:6px;color:var(--ink);background:oklch(0.74 0.1 ${h} / .2)`)}>{label}</span>
          <span style={css("font:400 11.5px Geist;color:var(--muted)")}>{e.who ? human(e.who) : ""}</span>
          <span style={css("font:400 11.5px Geist;color:var(--muted);margin-left:auto")}>{when(e.at)}</span>
        </div>
        <span style={css("font:400 13.5px/1.45 Geist")}>{e.text}</span>
        {e.meta ? <span style={css("font:400 11.5px/1.45 'Geist Mono';color:var(--muted);word-break:break-word")}>{e.meta}</span> : null}
        {go ? (
          <button type="button" onClick={() => onGo(e.go as Go)} style={css("align-self:flex-start;border:0;background:transparent;padding:0;font:500 12.5px Geist;color:var(--ink2);cursor:pointer")}>
            {go}
          </button>
        ) : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Outputs, grouped by run

export function OrchestratorOutputs({
  projectId,
  tab,
  onTab,
  onSheet,
}: {
  projectId: string;
  tab: string;
  onTab: (tab: string) => void;
  onSheet: () => void;
}) {
  const overview = useOrchestrators(projectId);
  const runs = useOrchestratorOutputs(projectId);
  const clis = overview.data?.clis ?? [];
  const list = overview.data?.orchestrators ?? [];
  const shown = tab === "other" ? [] : (runs.data ?? []).filter((r) => tab === "all" || r.orchestrator_id === tab);
  return (
    <div style={css("display:flex;flex-direction:column;gap:20px")}>
      <div role="group" aria-label="Show outputs from" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
        {[["all", "All runs"] as const, ...list.map((o) => [o.id, o.name] as const), ["other", "Other outputs"] as const].map(([id, l]) => (
          <button key={id} type="button" aria-pressed={tab === id} onClick={() => onTab(id)} style={css(chip(tab === id))}>
            {l}
          </button>
        ))}
      </div>
      {runs.isLoading ? <Loading what="Loading runs" /> : null}
      {runs.error ? <Failure error={runs.error} retry={() => void runs.refetch()} /> : null}
      {shown.map((r, i) => (
        <RunGroup key={r.id} r={r} clis={clis} first={i === 0} onSheet={onSheet} />
      ))}
    </div>
  );
}

function RunGroup({ r, clis, first, onSheet }: { r: OrchestratorRun; clis: CliChoice[]; first: boolean; onSheet: () => void }) {
  const [open, setOpen] = useState<boolean>(first);
  const status = runWords(r.shown);
  const trailOpen = open || !r.final;
  const meta = [r.id, `started ${when(r.started_at)}`, `${r.spec.agents.length} agents`, cliLabel(clis, r.spec.cli), modelLabel(clis, r.spec.cli, r.spec.model)];
  return (
    <section aria-label={`${r.spec.name}, run ${r.id}`} style={css("display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;align-items:baseline;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:500 15px Geist")}>{r.spec.name}</span>
        <span style={css("font:400 12.5px Geist;color:var(--muted)")}>{meta.join(" · ")}</span>
        <Pill words={status} />
      </div>
      {r.steer ? <span style={css("font:400 13px Geist;color:var(--ink2)")}>Steered: “{r.steer}”</span> : null}
      {r.final ? (
        <div style={css("padding:20px 22px;border-radius:20px;background:var(--surface);box-shadow:var(--shadow2);border:2px solid var(--ink);display:flex;flex-direction:column;gap:10px")}>
          <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
            <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;padding:3px 8px;border-radius:6px;background:var(--ink);color:var(--bg)")}>FINAL OUTPUT</span>
            <span style={css("font:400 12px 'Geist Mono';color:var(--muted)")}>{r.final.output_id}</span>
            <span style={css("font:400 12px Geist;color:var(--muted);margin-left:auto")}>{when(r.final.at)}</span>
          </div>
          <span style={css("font:400 24px/1.25 Newsreader")}>{r.final.title}</span>
          <div style={css("display:flex;flex-direction:column;gap:3px")}>
            <span style={css("font:500 11.5px Geist;color:var(--muted)")}>The orchestrator's summary</span>
            <span style={css("font:400 15px/1.55 Geist")}>{r.final.summary}</span>
          </div>
          <div style={css("display:flex;flex-direction:column;gap:4px")}>
            <span style={css("font:500 11.5px Geist;color:var(--muted)")}>Sources</span>
            <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
              {r.final.sources.length === 0 ? <span style={css(S.small)}>None named.</span> : null}
              {r.final.sources.map((s) => (
                <span key={s} style={css("padding:3px 9px;border-radius:6px;background:var(--soft);font:400 12px Geist;color:var(--ink2)")}>
                  {s}
                </span>
              ))}
            </div>
          </div>
          <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
            <Btn onClick={() => setOpen(!open)}>{open ? "Hide the trail" : `Show the trail · ${r.trail.length}`}</Btn>
            <Btn onClick={onSheet}>Open its sheet</Btn>
          </div>
        </div>
      ) : (
        <div style={css("padding:16px 18px;border-radius:16px;border:1.5px dashed var(--line2);font:400 14px/1.5 Geist;color:var(--ink2)")}>
          {r.shown === "stopped"
            ? `This run stopped before it finished${r.note ? `: ${r.note}` : "."} Its agents' outputs are below.`
            : `The final output lands here when the orchestrator has every report. ${r.trail.filter((t) => !t.act).length} of ${r.spec.agents.length} agents have reported.`}
        </div>
      )}
      {trailOpen && r.trail.length ? (
        <div style={css("display:flex;flex-direction:column;padding-left:6px")}>
          <span style={css("font:500 11.5px Geist;color:var(--muted);padding-bottom:6px")}>
            How it got here · {r.trail.length} {r.trail.length === 1 ? "output" : "outputs"}
          </span>
          {r.trail.map((x) => (
            <div key={`${x.output_id}-${x.at}`} style={css("display:flex;gap:14px;align-items:stretch")}>
              <div style={css("display:flex;flex-direction:column;align-items:center;flex:none;width:12px")}>
                <span aria-hidden style={css(`width:10px;height:10px;border-radius:50%;flex:none;margin-top:4px;background:oklch(0.66 0.1 ${hue(x.profile)})`)} />
                <span style={css("flex:1;width:2px;background:var(--line2)")} />
              </div>
              <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:4px;padding:0 0 16px")}>
                <div style={css("display:flex;gap:8px;align-items:baseline;flex-wrap:wrap")}>
                  <span style={css("font:400 11.5px 'Geist Mono';color:var(--muted)")}>{when(x.at)}</span>
                  <span style={css("font:500 12.5px Geist")}>{human(x.profile)}</span>
                  <span style={css("font:400 12px Geist;color:var(--muted)")}>{x.act ? "did the approved action" : `owns ${x.short}`}</span>
                  <span style={css("font:400 11.5px 'Geist Mono';color:var(--muted);margin-left:auto")}>{x.output_id}</span>
                </div>
                <span style={css("font:400 15px/1.4 Geist")}>{x.title}</span>
                <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>{x.summary}</span>
                <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
                  {x.sources.map((s) => (
                    <span key={s} style={css("padding:2px 8px;border-radius:6px;background:var(--soft);font:400 11.5px Geist;color:var(--ink2)")}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div style={css("height:1px;background:var(--line);margin-top:6px")} />
    </section>
  );
}

// ------------------------------------------------------------------ the auto sheets (Context)

export function OrchestratorSheets({ projectId }: { projectId: string }) {
  const sheets = useOrchestratorSheets(projectId);
  if (sheets.isLoading) return <Loading what="Loading orchestrator sheets" />;
  if (sheets.error) return <Failure error={sheets.error} retry={() => void sheets.refetch()} />;
  const list = sheets.data ?? [];
  if (list.length === 0) return null;
  const grid = "display:grid;grid-template-columns:minmax(150px,1.2fr) minmax(130px,1fr) minmax(200px,1.6fr) minmax(120px,.9fr) 110px";
  return (
    <div style={css("display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:500 15px Geist")}>Orchestrator sheets</span>
        <span style={css("font:400 12.5px Geist;color:var(--muted);flex:1")}>Made automatically, one per orchestrator. Each cell keeps its source and the agent that found it.</span>
      </div>
      {list.map((s) => (
        <div key={s.orchestrator_id} id={`sheet-${s.orchestrator_id}`} style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);overflow:hidden")}>
          <div style={css("display:flex;align-items:center;gap:10px;padding:14px 20px;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
            <span style={css("font:500 15px Geist")}>{s.name}</span>
            <span style={css("padding:2px 8px;border-radius:99px;font:500 11px Geist;background:oklch(0.74 0.1 265 / .2);color:var(--ink)")}>Auto · kept by {s.orchestrator}</span>
            <span style={css("font:400 12.5px Geist;color:var(--muted);margin-left:auto")}>
              {s.cells.length} {s.cells.length === 1 ? "cell" : "cells"} · {s.agents} agents
            </span>
          </div>
          <div style={css("overflow-x:auto")}>
            <div role="table" aria-label={s.name} style={css("min-width:720px")}>
              <div role="row" style={css(grid + ";background:var(--soft)")}>
                {s.columns.map((c) => (
                  <span key={c} role="columnheader" style={css("padding:9px 14px;font:500 12px Geist;color:var(--muted)")}>
                    {c}
                  </span>
                ))}
              </div>
              {s.cells.map((c) => (
                <div key={c.what} role="row" style={css(grid + ";border-top:1px solid var(--line)")}>
                  <span role="cell" style={css("padding:10px 14px;font:500 13.5px/1.4 Geist")}>
                    {c.what}
                  </span>
                  <span role="cell" style={css("padding:10px 14px;font:400 13.5px/1.4 Geist")}>
                    {c.value}
                  </span>
                  <span role="cell" style={css("padding:10px 14px;font:400 12.5px/1.4 Geist;color:var(--ink2)")}>
                    {c.source}
                  </span>
                  <span role="cell" style={css("padding:10px 14px;font:400 12.5px/1.4 Geist;color:var(--ink2)")}>
                    {human(c.agent)}
                  </span>
                  <span role="cell" style={css("padding:10px 14px;font:400 12px 'Geist Mono';color:var(--muted)")}>
                    {when(c.at)}
                  </span>
                </div>
              ))}
              {s.cells.length === 0 ? (
                <div style={css("padding:14px 20px;font:400 13px Geist;color:var(--muted);border-top:1px solid var(--line)")}>Empty until the first run. The orchestrator fills it as agents report.</div>
              ) : null}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

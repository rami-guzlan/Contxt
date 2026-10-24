// Agents (v4 slices 11, 12, 13): the knowledge agent (Use it, How it works), agent profiles,
// skills and alignment. Release 1: every job runs by hand, schedules are a later phase, the
// alignment score is dropped (findings, what needs review, when it was last checked).

import { type ReactNode, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";

import {
  useAgentChat,
  useAgentJob,
  useAgentSettings,
  useAgentSkills,
  useAnswerAgentQuestion,
  useCheckRunners,
  useKeepAgentNote,
  useModels,
  useRunSkill,
  useRunners,
  useSkills,
  useWorkAgents,
} from "../../api/hooks";
import type { AgentAction, AgentChatResult, AgentJob, AgentQuestion, AgentRun, AgentSkill, RunnerStatus, SkillCard, WorkAgent } from "../../api/types";
import { useInstruction, useInstructions, useProposals, type InstructionStatus } from "../api";
import { css } from "../css";
import { AGENT_SKILL_RELEASE, isLater, useAgentJobs, useAgentPage, useAskProfile, useCreateProfile, useRunnerSignIn, useStartAction, type AgentPage } from "../hooks/agents";
import { Btn, Empty, Failure, Later, Loaded, Loading, Modal, S, Status, plural, when } from "../ui";

const TS = (on: boolean) =>
  `padding:7px 14px;border-radius:99px;border:0;white-space:nowrap;font:${on ? 500 : 400} 13px Geist;background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink2)"}`;
const SEG = (on: boolean) =>
  `padding:7px 14px;border-radius:99px;border:0;font:${on ? 500 : 400} 13px Geist;background:${on ? "var(--surface)" : "transparent"};color:var(--ink);${on ? "box-shadow:0 1px 2px rgba(30,25,15,.08)" : ""}`;
const OPT = (on: boolean, off = false) =>
  `padding:6px 13px;border-radius:99px;font:500 12.5px Geist;border:1px solid ${on ? "var(--ink)" : "var(--line2)"};background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : off ? "var(--muted)" : "var(--ink)"}`;
const SURFACE = "background:var(--surface);border-radius:20px;box-shadow:var(--shadow)";
const TAG = "padding:3px 9px;border-radius:99px;background:var(--soft);color:var(--ink2);font:500 12px Geist;white-space:nowrap";
const SW = (on: boolean) =>
  `position:relative;width:38px;height:22px;border-radius:99px;border:0;flex:none;padding:0;background:${on ? "oklch(0.62 0.14 150)" : "var(--gray)"}`;
const KNOB = (on: boolean) => `position:absolute;top:3px;left:${on ? 19 : 3}px;width:16px;height:16px;border-radius:50%;background:#fff;transition:left .15s`;

type Tab = "agentk" | "agents" | "skills" | "alignment";
const TABS: [Tab, string][] = [
  ["agentk", "Knowledge agent"],
  ["agents", "Agent profiles"],
  ["skills", "Skills"],
  ["alignment", "Alignment"],
];

/** The tabs of a page, in the design's own pill style. */
export function TabRow<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} style={css("display:flex;gap:6px;flex-wrap:wrap")}>
      {options.map(([id, text]) => (
        <button key={id} role="tab" aria-selected={value === id} onClick={() => onChange(id)} style={css(TS(value === id))}>
          {text}
        </button>
      ))}
    </div>
  );
}

export function AgentsPage() {
  const [params, setParams] = useSearchParams();
  const found = params.get("tab") as Tab | null;
  const tab: Tab = TABS.some(([id]) => id === found) ? (found as Tab) : "agentk";
  return (
    <div className="gn-page">
      <div style={css("max-width:1120px;margin:0 auto;padding:56px 64px 28px;display:flex;flex-direction:column;gap:22px;box-sizing:border-box")}>
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <h1 style={css(S.h1)}>Agents</h1>
          <span style={css("font:400 17px Geist;color:var(--ink2)")}>
            Run your knowledge agent, build the agents and skills you work with, and keep your Brain aligned.
          </span>
        </div>
        <TabRow value={tab} options={TABS} onChange={(id) => setParams(id === "agentk" ? {} : { tab: id })} label="Agents" />
      </div>
      <div style={css("max-width:1120px;margin:0 auto;padding:0 64px 96px;display:flex;flex-direction:column;gap:28px;box-sizing:border-box")}>
        {tab === "agentk" ? <KnowledgeAgent /> : null}
        {tab === "agents" ? <Profiles /> : null}
        {tab === "skills" ? <Skills /> : null}
        {tab === "alignment" ? <Alignment /> : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ jobs run by hand

/** When a job finishes, the agent's runs, questions and Catch up are read again. */
function useFinishedRefresh(jobs: AgentJob[] | undefined) {
  const client = useQueryClient();
  const running = useRef<string>("");
  useEffect(() => {
    const now = (jobs ?? [])
      .filter((j) => j.status === "waiting" || j.status === "running")
      .map((j) => j.id)
      .join(",");
    if (running.current && now !== running.current) {
      void client.invalidateQueries({ queryKey: ["brain", "agent"], exact: true });
      void client.invalidateQueries({ queryKey: ["brain", "proposals"] });
    }
    running.current = now;
  }, [jobs, client]);
}

function latestJob(jobs: AgentJob[] | undefined, action: string): AgentJob | undefined {
  return (jobs ?? []).find((j) => j.kind === "action" && j.action === action);
}

function lastRun(runs: AgentRun[], action: string): AgentRun | undefined {
  return runs.find((r) => r.action === action);
}

function runLine(run: AgentRun): string {
  const parts = [run.summary || `Checked ${run.checked}`];
  if (run.proposed) parts.push(plural(run.proposed, "suggestion") + " in Catch up");
  if (run.questions) parts.push(plural(run.questions, "question"));
  return parts.join(" · ");
}

/** One job's button and its last result: running, failed (with a retry on the same
 * provider) or done. */
function JobRun({ action, runs, label = "Run now", compact = false }: { action: AgentAction; runs: AgentRun[]; label?: string; compact?: boolean }) {
  const jobs = useAgentJobs();
  const start = useStartAction();
  const job = latestJob(jobs.data, action.id);
  const busy = start.isPending || job?.status === "waiting" || job?.status === "running";
  const last = lastRun(runs, action.id);
  const later = isLater(action.id);
  let res = last ? `Last run ${when(last.at)} · ${runLine(last)}` : "Not run yet";
  let tone = "var(--muted)";
  if (busy) res = job ? `Working through ${job.model_label}…` : "Starting…";
  else if (job?.status === "failed") {
    res = `Stopped: ${job.error ?? "it could not finish"}. Nothing was sent anywhere else.`;
    tone = "oklch(0.55 0.17 28)";
  } else if (job?.status === "done" && last) {
    res = `Just now · ${runLine(last)}`;
    tone = "oklch(0.5 0.12 150)";
  }
  const retry = job?.status === "failed" && !busy;
  return (
    <>
      <span role="status" style={css(`font:400 12.5px/1.45 Geist;color:${tone}`)}>
        {later ? "Later: this job is part of a later release." : res}
      </span>
      {start.error ? <Failure error={start.error} /> : null}
      <button
        type="button"
        disabled={busy || later}
        onClick={() => start.mutate(action.id)}
        style={css(
          `align-self:flex-start;padding:${compact ? "6px 12px" : "7px 14px"};border-radius:99px;border:0;font:500 12.5px Geist;${busy || later ? "background:var(--soft);color:var(--ink2)" : "background:var(--ink);color:var(--bg)"}`,
        )}
      >
        {later ? "Later" : busy ? "Running…" : retry ? `Retry with ${job?.model_label ?? "the same AI"}` : label}
      </button>
    </>
  );
}

// ------------------------------------------------------------------ the knowledge agent

function KnowledgeAgent() {
  const q = useAgentPage();
  const jobs = useAgentJobs();
  useFinishedRefresh(jobs.data);
  const [view, setView] = useState<"use" | "edit">("use");
  return (
    <Loaded q={q}>
      {(agent) => {
        const label = agent.provider?.label ?? agent.models.find((m) => m.id === agent.model)?.label ?? agent.model;
        const working = agent.working.length > 0;
        return (
          <div style={css("display:flex;flex-direction:column;gap:22px")}>
            <div style={css("display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap")}>
              <div style={css("display:flex;align-items:center;gap:14px")}>
                <span aria-hidden style={css("width:42px;height:42px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center;flex:none")}>
                  <span style={css("width:2px;height:18px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
                </span>
                <div style={css("display:flex;flex-direction:column;gap:2px")}>
                  <span style={css("font:500 18px Geist")}>Your knowledge agent</span>
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>
                    {working ? `Working through ${label}…` : `Idle · runs through ${label}`} · suggests only · runs when you start it · schedules are a later phase
                  </span>
                </div>
              </div>
              <div role="tablist" aria-label="Knowledge agent" style={css("display:flex;gap:4px;padding:4px;border-radius:99px;background:var(--soft)")}>
                {(
                  [
                    ["use", "Use it"],
                    ["edit", "How it works"],
                  ] as const
                ).map(([id, l]) => (
                  <button key={id} role="tab" aria-selected={view === id} onClick={() => setView(id)} style={css(SEG(view === id))}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
            <ProviderView agent={agent} />
            <AskBrainFirst />
            {view === "use" ? <UseIt agent={agent} /> : <HowItWorks agent={agent} />}
          </div>
        );
      }}
    </Loaded>
  );
}

function ProviderView({ agent }: { agent: AgentPage }) {
  const p = agent.provider;
  const runners = useRunners();
  const check = useCheckRunners();
  const client = useQueryClient();
  const signIn = useRunnerSignIn();
  const models = useModels();
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<unknown>(null);
  const [checkedAt, setCheckedAt] = useState<number>(() => Date.now());
  const cli = (p?.id ?? agent.model).split(":")[0];
  const runner: RunnerStatus | undefined = (runners.data ?? []).find((r) => r.id === cli);
  const again = async () => {
    setChecking(true);
    setCheckError(null);
    try {
      await check();
      await client.invalidateQueries({ queryKey: ["brain", "agent"], exact: true });
      setCheckedAt(Date.now());
    } catch (error) {
      setCheckError(error);
    } finally {
      setChecking(false);
    }
  };
  if (!p) {
    return (
      <Empty title="No AI to run it on yet">
        The knowledge agent runs through an AI CLI on this computer (Claude Code, Codex or Gemini CLI). Install and sign in to one in Settings, Your AI apps, then choose it under How it works.
      </Empty>
    );
  }
  const signedIn = runner ? runner.signed_in : null;
  const ok = p.available && signedIn !== false;
  const at = when(new Date(checkedAt).toISOString());
  const health = checking
    ? "Checking…"
    : !p.available
      ? "Can't answer now"
      : signedIn === false
        ? "Signed out"
        : signedIn === true
          ? `Signed in · checked ${at}`
          : `Ready · checked ${at}`;
  const matching = models.data?.matching;
  const search = models.isLoading
    ? "Checking the meaning model…"
    : matching?.present
      ? "Meaning index on CPU. Words-only search is the fallback; its lower recall is reported separately."
      : "Words-only search: the meaning model isn't on this computer, so paraphrases can be missed. Its lower recall is reported separately. Get the model in Settings, On this computer.";
  const rows: [string, ReactNode][] = [
    ["Provider and model", `${p.label}, your choice. Model: ${p.model ?? "the CLI's own default"} (${p.model_from === "named here" ? "named here" : `read from ${p.model_from}`}).`],
    ["Can do", "Distill proposals, answers with receipts, and tidy-ups you start. Reads only the passages Contxt sends."],
    ["Where data goes", `${p.data} Your Brain, indexes and sources stay here.`],
    ["If it fails", `Stops and tells you, with a retry. It switches ${p.switches}.`],
    ["Local models and GPU", "Optional. Nothing in this release needs one."],
    ["Search", search],
  ];
  return (
    <div style={css(`${SURFACE};padding:4px 22px`)}>
      <div style={css("display:flex;align-items:center;gap:10px;padding:14px 0 10px;flex-wrap:wrap")}>
        <span style={css("font:500 15px Geist;flex:1;min-width:200px")}>Runs on the CLI AI you chose</span>
        <span
          role="status"
          style={css(
            `font:500 12px Geist;padding:3px 10px;border-radius:99px;color:var(--ink);background:${checking ? "oklch(0.74 0.12 80 / .25)" : ok ? "oklch(0.62 0.14 150 / .2)" : "oklch(0.64 0.17 28 / .2)"}`,
          )}
        >
          {health}
        </span>
        {signedIn === false && runner ? (
          <Btn kind="ghostSm" style="padding:6px 13px;font:500 12.5px Geist" disabled={signIn.isPending} onClick={() => signIn.mutate(runner.id)}>
            {signIn.isPending ? "Opening…" : `Sign in to ${runner.label}`}
          </Btn>
        ) : null}
        <Btn kind="ghostSm" style="padding:6px 13px;font:500 12.5px Geist" disabled={checking} onClick={() => void again()}>
          {checking ? "Checking…" : "Check again"}
        </Btn>
      </div>
      {!p.available ? <span style={css("display:block;font:400 13px/1.5 Geist;color:var(--ink2);padding-bottom:10px")}>{p.health}</span> : null}
      {signIn.data && !signIn.data.opened ? (
        <span style={css("display:block;font:400 13px/1.5 Geist;color:var(--ink2);padding-bottom:10px")}>
          Couldn't open a terminal. Run <code>{signIn.data.command}</code> in one, then press Check again.
        </span>
      ) : null}
      {signIn.error ? <Failure error={signIn.error} /> : null}
      {checkError ? <Failure error={checkError} /> : null}
      {rows.map(([k, v]) => (
        <div key={k} style={css("display:grid;grid-template-columns:minmax(120px,180px) minmax(0,1fr);gap:16px;padding:12px 0;border-top:1px solid var(--line)")}>
          <span style={css("font:500 13px Geist")}>{k}</span>
          <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>{v}</span>
        </div>
      ))}
    </div>
  );
}

const APP_LABEL: Record<string, string> = { "claude-code": "Claude Code", codex: "Codex", gemini: "Gemini CLI" };

/** Ask the Brain first: one global instruction in each connected assistant's own file. It
 * writes only after the person's yes, and shows where it was written. */
export function AskBrainFirst() {
  const q = useInstructions();
  const act = useInstruction();
  const [confirm, setConfirm] = useState<InstructionStatus | null>(null);
  return (
    <div style={css("padding:18px 20px;border-radius:18px;border:1px solid var(--line);display:flex;flex-direction:column;gap:10px")}>
      <span style={css("font:500 15px Geist")}>Ask the Brain first</span>
      <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>
        Adds one global instruction to each connected assistant: check your Brain before answering about your work. It's an instruction, not a lock. Assistants can still answer without it, and
        Contxt can't see or control those answers.
      </span>
      <Loaded
        q={q}
        empty={(list) =>
          list.some((x) => x.supported) ? null : <Empty title="No assistant here keeps an instructions file">Claude Code, Codex and Gemini CLI do. Install one, then come back.</Empty>
        }
      >
        {(list) => {
          const on = list.filter((x) => x.installed);
          return (
            <>
              {list
                .filter((x) => x.supported)
                .map((x) => (
                  <div key={x.app} style={css("display:flex;align-items:center;gap:12px;padding:8px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                    <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:2px")}>
                      <span style={css("font:500 14px Geist")}>{APP_LABEL[x.app] ?? x.app}</span>
                      <span style={css("font:400 12px 'Geist Mono';color:var(--muted);word-break:break-all")}>{x.path}</span>
                    </div>
                    <span style={css("font:400 12.5px Geist;color:var(--ink2)")}>{x.installed ? "On" : "Off"}</span>
                    <button
                      role="switch"
                      aria-checked={x.installed}
                      aria-label={`Ask the Brain first in ${APP_LABEL[x.app] ?? x.app}`}
                      disabled={act.isPending}
                      onClick={() => (x.installed ? act.mutate({ app: x.app, install: false }) : setConfirm(x))}
                      style={css(SW(x.installed))}
                    >
                      <span style={css(KNOB(x.installed))} />
                    </button>
                  </div>
                ))}
              <span style={css("font:400 12.5px 'Geist Mono';color:var(--ink);padding:10px 12px;border-radius:12px;background:var(--soft);word-break:break-all")}>
                {on.length ? `On · added to ${on.map((x) => x.path).join(" and ")}` : "Off · no global instruction is installed"}
              </span>
            </>
          );
        }}
      </Loaded>
      {act.error && !confirm ? <Failure error={act.error} /> : null}
      {confirm ? (
        <Modal title={`Add the instruction to ${APP_LABEL[confirm.app] ?? confirm.app}?`} eyebrow="ASK THE BRAIN FIRST" onClose={() => setConfirm(null)}>
          <span style={css("font:400 14px/1.55 Geist;color:var(--ink2)")}>
            This writes one marked block at the end of the file this assistant reads in every project. The rest of the file stays as it is, and you can remove the block here at any time.
          </span>
          <span style={css("font:400 12.5px 'Geist Mono';padding:10px 12px;border-radius:12px;background:var(--soft);word-break:break-all")}>{confirm.path}</span>
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" disabled={act.isPending} onClick={() => act.mutate({ app: confirm.app, install: true }, { onSuccess: () => setConfirm(null) })}>
              {act.isPending ? "Adding…" : "Yes, add it"}
            </Btn>
            <Btn kind="ghostSm" onClick={() => setConfirm(null)}>
              Cancel
            </Btn>
          </div>
          {act.error ? <Failure error={act.error} /> : null}
        </Modal>
      ) : null}
    </div>
  );
}

function UseIt({ agent }: { agent: AgentPage }) {
  const navigate = useNavigate();
  const proposals = useProposals();
  return (
    <div style={css("display:flex;flex-direction:column;gap:22px")}>
      <AskAgent />
      <Questions questions={agent.questions} waiting={proposals.data?.length} onCatchUp={() => navigate("/brain/catch-up")} />
      <div style={css("display:flex;flex-direction:column;gap:10px")}>
        <span style={css("font:500 15px Geist")}>What it can do for you</span>
        {agent.actions.length === 0 ? (
          <Empty title="No jobs listed">The server lists no upkeep jobs for this Brain.</Empty>
        ) : (
          <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px")}>
            {agent.actions.map((a) => (
              <div key={a.id} style={css(`${SURFACE};border-radius:18px;padding:16px;display:flex;flex-direction:column;gap:8px`)}>
                <div style={css("display:flex;justify-content:space-between;gap:8px;align-items:baseline")}>
                  <span style={css("font:500 15px Geist")}>{a.label}</span>
                  <span style={css("font:400 11.5px Geist;color:var(--muted);white-space:nowrap")}>By hand</span>
                </div>
                <span style={css("font:400 13px/1.45 Geist;color:var(--ink2);flex:1")}>{a.blurb}</span>
                {a.serves ? <span style={css("font:400 12px Geist;color:var(--muted)")}>Serves your goal: {a.serves.title}</span> : null}
                <JobRun action={a} runs={agent.runs} />
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={css("display:flex;flex-direction:column;gap:10px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap")}>
          <div style={css("display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:500 15px Geist")}>
              Scheduled runs
              <Later />
            </span>
            <span style={css("font:400 13px Geist;color:var(--muted)")}>Your own runs, on your schedule: a skill, or a job in your own words.</span>
          </div>
          <Btn kind="primarySm" disabled title="Schedules are a later phase">
            New scheduled run
          </Btn>
        </div>
        <div style={css(`${SURFACE};border-radius:18px;padding:18px`)}>
          <span style={css("font:400 14px Geist;color:var(--muted)")}>Schedules are a later phase. Run any job by hand above; it runs once, when you press Run now.</span>
        </div>
      </div>
      <RecentRuns runs={agent.runs} />
    </div>
  );
}

function AskAgent() {
  const [text, setText] = useState("");
  const [history, setHistory] = useState<{ role: "user" | "agent"; text: string }[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const chat = useAgentChat();
  const job = useAgentJob(jobId);
  const keep = useKeepAgentNote();
  const [kept, setKept] = useState<Record<string, string>>({});
  const done = job.data?.status === "done" || job.data?.status === "failed";
  const busy = chat.isPending || (Boolean(jobId) && !done);
  useEffect(() => {
    if (job.data?.status === "done" && job.data.result.reply) {
      const reply = job.data.result.reply;
      setHistory((h) => (h[h.length - 1]?.text === reply ? h : [...h, { role: "agent", text: reply }]));
    }
  }, [job.data]);
  const send = (message: string) => {
    const m = message.trim();
    if (!m || busy) return;
    chat.mutate(
      { message: m, history },
      {
        onSuccess: (started) => {
          setHistory((h) => [...h, { role: "user", text: m }]);
          setJobId(started.id);
          setText("");
        },
      },
    );
  };
  const lastAsked = history.filter((h) => h.role === "user").slice(-1)[0]?.text ?? "";
  const found = job.data?.status === "done" ? ((job.data.result.notes ?? []) as unknown[]) : [];
  const notes = found.filter((n): n is AgentChatResult["notes"][number] => typeof n === "object" && n !== null && "text" in n);
  return (
    <div style={css(`${SURFACE};padding:16px 18px;display:flex;flex-direction:column;gap:10px`)}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
        style={css("display:flex;gap:8px")}
      >
        <input
          aria-label="Ask your knowledge agent"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask it to tidy, find or fill something in your Brain"
          style={css("flex:1;min-width:0;border:1px solid var(--line2);border-radius:14px;padding:11px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 15px Geist")}
        />
        <Btn kind="primary" type="submit" disabled={busy || !text.trim()}>
          {busy ? "Asking…" : "Ask"}
        </Btn>
      </form>
      <div style={css(S.wrap)}>
        {["What's gone stale?", "Where are my gaps?", "What repeats?"].map((l) => (
          <button key={l} type="button" disabled={busy} onClick={() => send(l)} style={css("padding:6px 12px;border-radius:99px;background:var(--soft);border:0;font:400 12.5px Geist;color:var(--ink)")}>
            {l}
          </button>
        ))}
      </div>
      {history.length ? (
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          {history.map((t, i) => (
            <div key={i} style={css(`font:400 14px/1.55 Geist;white-space:pre-wrap;${t.role === "user" ? "color:var(--ink2)" : "color:var(--ink)"}`)}>
              <span style={css(S.eyebrow)}>{t.role === "user" ? "YOU" : "KNOWLEDGE AGENT"}</span>
              <br />
              {t.text}
            </div>
          ))}
        </div>
      ) : null}
      {busy && jobId ? <Loading what={`Working through ${job.data?.model_label ?? "your AI"}`} /> : null}
      {job.data?.status === "failed" ? (
        <Failure error={new Error(`${job.data.error ?? "It could not answer."} Nothing was sent to another provider.`)} retry={lastAsked ? () => send(lastAsked) : undefined} />
      ) : null}
      {chat.error ? <Failure error={chat.error} /> : null}
      {notes.map((n) => (
        <div key={n.title + n.text} style={css("display:flex;gap:10px;align-items:center;padding:10px 12px;border-radius:12px;background:var(--soft);flex-wrap:wrap")}>
          <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:500 13.5px Geist")}>{n.title || "A note it suggests"}</span>
            <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{n.text}</span>
          </div>
          {kept[n.text] ? (
            <span style={css(S.small)}>{kept[n.text]}</span>
          ) : (
            <Btn
              kind="ghostSm"
              disabled={keep.isPending}
              onClick={() => keep.mutate({ title: n.title, text: n.text, kind: n.kind }, { onSuccess: (r) => setKept((k) => ({ ...k, [n.text]: r.message || "Waiting in Catch up" })) })}
            >
              Keep · waits in Catch up
            </Btn>
          )}
        </div>
      ))}
      {keep.error ? <Failure error={keep.error} /> : null}
    </div>
  );
}

function Questions({ questions, waiting, onCatchUp }: { questions: AgentQuestion[]; waiting: number | undefined; onCatchUp: () => void }) {
  const answer = useAnswerAgentQuestion();
  const [open, setOpen] = useState<string | null>(null);
  const [words, setWords] = useState("");
  const first = questions[0];
  return (
    <div style={css("display:flex;flex-direction:column;gap:8px")}>
      <div style={css("display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:16px;background:var(--soft);flex-wrap:wrap")}>
        <span aria-hidden style={css(`width:8px;height:8px;border-radius:50%;flex:none;background:${first ? "oklch(0.72 0.15 60)" : "var(--muted)"}`)} />
        <span style={css("font:400 14px Geist;flex:1;min-width:220px")}>
          {first ? `It has ${plural(questions.length, "question")} for you.` : "No open questions from your knowledge agent right now."}
        </span>
        <button type="button" onClick={onCatchUp} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2);padding:0")}>
          Catch up · {waiting === undefined ? "…" : waiting}
        </button>
      </div>
      {questions.map((qn) => (
        <div key={qn.key} style={css("display:flex;flex-direction:column;gap:6px;padding:12px 0;border-top:1px solid var(--line)")}>
          <span style={css("font:400 15px Geist")}>{qn.ask}</span>
          <span style={css(S.small)}>
            {qn.target.title} · {qn.why || "No reason given"} · {when(qn.at)}
          </span>
          <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
            {qn.target.type === "note" ? (
              <Btn kind="ghostSm" disabled={answer.isPending} onClick={() => answer.mutate({ key: qn.key, do: "verify" })}>
                Still true
              </Btn>
            ) : null}
            <Btn kind="ghostSm" disabled={answer.isPending} onClick={() => setOpen(open === qn.key ? null : qn.key)}>
              Answer
            </Btn>
            <Btn kind="link" disabled={answer.isPending} onClick={() => answer.mutate({ key: qn.key, do: "dismiss" })}>
              Set aside
            </Btn>
          </div>
          {open === qn.key ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!words.trim()) return;
                answer.mutate(
                  { key: qn.key, do: "answer", text: words.trim() },
                  {
                    onSuccess: () => {
                      setOpen(null);
                      setWords("");
                    },
                  },
                );
              }}
              style={css("display:flex;gap:8px")}
            >
              <input aria-label="Your answer" value={words} onChange={(e) => setWords(e.target.value)} placeholder="Say it in a sentence. It waits in Catch up." style={css(`${S.input};flex:1;min-width:0`)} />
              <Btn kind="primarySm" type="submit" disabled={answer.isPending || !words.trim()}>
                Send
              </Btn>
            </form>
          ) : null}
        </div>
      ))}
      {answer.error ? <Failure error={answer.error} /> : null}
    </div>
  );
}

function RecentRuns({ runs }: { runs: AgentRun[] }) {
  return (
    <div style={css("display:flex;flex-direction:column;gap:8px")}>
      <span style={css("font:500 15px Geist")}>Recent runs</span>
      <div style={css(`${SURFACE};border-radius:18px;padding:2px 18px`)}>
        {runs.length === 0 ? (
          <div style={css("padding:18px 0;font:400 14px Geist;color:var(--muted)")}>No runs yet. Start a job above; its result shows here.</div>
        ) : (
          runs.slice(0, 8).map((r, i) => (
            <div key={r.id} style={css(`display:flex;gap:14px;padding:11px 0;${i ? "border-top:1px solid var(--line);" : ""}flex-wrap:wrap`)}>
              <span style={css("font:400 13px Geist;color:var(--muted);width:130px")}>{when(r.at)}</span>
              <span style={css("font:400 14px Geist;flex:1;min-width:200px")}>
                {r.label}: {runLine(r)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function HowItWorks({ agent }: { agent: AgentPage }) {
  const settings = useAgentSettings();
  const navigate = useNavigate();
  const label = agent.provider?.label ?? agent.model;
  const steps: [string, string][] = [
    ["It looks over your Brain", `When you start a job. It runs through ${label} on your computer.`],
    ["It spots what's off", "Notes that repeat, went stale or disagree. Questions nobody answered."],
    ["You decide in Catch up", "It suggests fixes. Nothing changes until you say yes."],
  ];
  const cardS = `${SURFACE};border-radius:18px;padding:16px 18px;display:flex;flex-direction:column;gap:10px`;
  return (
    <div style={css("display:flex;flex-direction:column;gap:16px")}>
      <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>Change how it works. Settings hold thresholds and choices, never its prompts.</span>
      <div style={css("display:flex;flex-direction:column;gap:16px;padding:22px;border-radius:20px;background:var(--soft)")}>
        <span style={css("font:500 15px Geist")}>How it works, in plain words</span>
        <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:16px")}>
          {steps.map(([t, d], i) => (
            <div key={t} style={css("display:flex;flex-direction:column;gap:6px")}>
              <span style={css("width:30px;height:30px;border-radius:10px;display:flex;align-items:center;justify-content:center;font:500 13px Geist;background:var(--surface)")}>{i + 1}</span>
              <span style={css("font:500 14px Geist")}>{t}</span>
              <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>{d}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:14px")}>
        <div style={css(cardS)}>
          <span style={css("font:500 14px Geist")}>Runs through</span>
          <div role="radiogroup" aria-label="Runs through" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
            {agent.models.length === 0 ? <span style={css(S.small)}>No AI CLI or local model is on this computer.</span> : null}
            {agent.models.map((m) => {
              const on = m.id === agent.model || agent.model.split(":")[0] === m.id;
              return (
                <button
                  key={m.id}
                  role="radio"
                  aria-checked={on}
                  disabled={!m.available || settings.isPending}
                  title={m.detail}
                  onClick={() => settings.mutate({ model: m.id })}
                  style={css(OPT(on, !m.available))}
                >
                  {m.label}
                  {m.available ? "" : " · can't answer"}
                </button>
              );
            })}
          </div>
          <span style={css(S.small)}>Contxt starts it on this computer. What it reads goes to that CLI's provider; a local model keeps it here. It never switches on its own.</span>
          {settings.error ? <Failure error={settings.error} /> : null}
        </div>
        <div style={css(cardS)}>
          <span style={css("font:500 14px Geist")}>How far it can go</span>
          <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>
            Suggests only. Every change it finds waits for your yes in Catch up. What may go straight in, with undo, is set in Settings, Approval.
          </span>
          <Btn kind="ghostSm" style="align-self:flex-start" onClick={() => navigate("/settings?tab=approval")}>
            Approval settings
          </Btn>
        </div>
        <div style={css(cardS)}>
          <div style={css("display:flex;align-items:center;gap:12px")}>
            <span style={css("font:500 14px Geist;flex:1")}>Its suggestions on Home</span>
            <button
              role="switch"
              aria-checked={agent.suggestions}
              aria-label="Show its suggestions"
              disabled={settings.isPending}
              onClick={() => settings.mutate({ suggestions: !agent.suggestions })}
              style={css(SW(agent.suggestions))}
            >
              <span style={css(KNOB(agent.suggestions))} />
            </button>
          </div>
          <span style={css(S.small)}>Made by code from your Brain as it is, without a model. {agent.suggestions ? "Shown." : "Hidden."}</span>
        </div>
        <div style={css(cardS)}>
          <span style={css("font:500 14px Geist")}>
            What it can read and change
            <Later />
          </span>
          <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>In this release it reads only the passages Contxt gathers for each job and changes nothing itself.</span>
        </div>
      </div>
      <div style={css(`${SURFACE};border-radius:18px;padding:6px 18px`)}>
        <div style={css("padding:12px 0 8px;font:500 14px Geist")}>Jobs and when they run</div>
        {agent.actions.map((a) => (
          <div key={a.id} style={css("display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
            <div style={css("width:220px;display:flex;flex-direction:column;gap:2px")}>
              <span style={css("font:400 14px Geist")}>{a.label}</span>
              <span style={css("font:400 12px/1.4 Geist;color:var(--muted)")}>{a.blurb}</span>
            </div>
            <div style={css("display:flex;gap:4px;flex-wrap:wrap;flex:1")}>
              <span style={css(OPT(true))}>By hand</span>
              <span style={css(OPT(false, true))}>
                On a schedule
                <Later />
              </span>
            </div>
            <div style={css("display:flex;flex-direction:column;gap:4px;align-items:flex-end;max-width:320px")}>
              <JobRun action={a} runs={agent.runs} compact />
            </div>
          </div>
        ))}
      </div>
      <AgentSkillList actions={agent.actions} />
    </div>
  );
}

/** The procedures the knowledge agent follows, each with the release it belongs to. */
function AgentSkillList({ actions, title = "The skills it follows" }: { actions: AgentAction[]; title?: string }) {
  const q = useAgentSkills();
  return (
    <div style={css("display:flex;flex-direction:column")}>
      <span style={css("font:500 15px Geist;margin-bottom:14px")}>{title}</span>
      <Loaded q={q} empty={(list) => (list.length ? null : <Empty title="No skills listed">The Brain lists no knowledge agent skills.</Empty>)}>
        {(list: AgentSkill[]) =>
          list.map((s) => {
            const action = actions.find((a) => a.id === s.name);
            return (
              <div key={s.name} style={css("display:flex;align-items:center;padding:14px 0;border-top:1px solid var(--line);gap:16px;flex-wrap:wrap")}>
                <div style={css("width:260px;display:flex;flex-direction:column;gap:2px")}>
                  <span style={css("font:400 15px Geist")}>/{s.name}</span>
                  <span style={css(S.small)}>{s.own ? "Your Brain's own version" : "Comes with every Brain"}</span>
                </div>
                <span style={css("font:400 14px/1.45 Geist;color:var(--ink2);flex:1;min-width:200px")}>{s.description || s.when_to_use}</span>
                <span style={css(TAG)}>{AGENT_SKILL_RELEASE[s.name] ?? "Release not listed"}</span>
                {action && !isLater(s.name) ? <RunByHand action={action} /> : null}
              </div>
            );
          })
        }
      </Loaded>
    </div>
  );
}

function RunByHand({ action }: { action: AgentAction }) {
  const jobs = useAgentJobs();
  const start = useStartAction();
  const job = latestJob(jobs.data, action.id);
  const busy = start.isPending || job?.status === "waiting" || job?.status === "running";
  return (
    <button type="button" aria-label={`Run ${action.label}`} disabled={busy} onClick={() => start.mutate(action.id)} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink)")}>
      {busy ? "Running…" : job?.status === "failed" ? "Failed · retry" : "Run"}
    </button>
  );
}

// ------------------------------------------------------------------ agent profiles

function initials(name: string): string {
  return name
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function Profiles() {
  const q = useWorkAgents();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<WorkAgent | null>(null);
  return (
    <div style={css("display:flex;flex-direction:column;gap:26px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap")}>
        <span style={css("font:400 15px/1.55 Geist;color:var(--ink2);max-width:680px")}>
          Bring your own way of working. A profile gives any AI your taste, your sources and the context it needs. Skills do the steps. Profiles decide how the work should feel.
        </span>
        <Btn kind="primarySm" onClick={() => setCreating(true)}>
          New agent profile
        </Btn>
      </div>
      <div style={css("display:flex;align-items:center;gap:12px;padding:16px 18px;border-radius:18px;border:1px solid var(--line);flex-wrap:wrap")}>
        <span aria-hidden style={css("width:10px;height:10px;border-radius:50%;flex:none;background:oklch(0.68 0.14 25)")} />
        <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:220px")}>
          <span style={css("font:500 15px Geist")}>Your taste lives in your Brain</span>
          <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>Every agent can start from it. Giving a profile its own taste, tagged sources and a packet comes later.</span>
        </div>
        <button type="button" onClick={() => navigate("/brain")} style={css("padding:7px 14px;border-radius:99px;background:var(--soft);border:0;font:500 12.5px Geist;color:var(--ink)")}>
          Open Taste →
        </button>
      </div>
      <div style={css("display:flex;flex-direction:column;gap:12px")}>
        <span style={css("font:500 15px Geist")}>Agent profiles</span>
        <Loaded q={q}>
          {(list) => (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px")}>
              {list.map((a) => (
                <button
                  key={a.name}
                  type="button"
                  onClick={() => setOpen(a)}
                  style={css(`${SURFACE};border:0;padding:20px;display:flex;flex-direction:column;gap:10px;text-align:left;color:var(--ink);min-height:190px`)}
                >
                  <span aria-hidden style={css("width:46px;height:46px;border-radius:15px;display:flex;align-items:center;justify-content:center;font:500 14px Geist;background:var(--soft);color:var(--ink2)")}>
                    {initials(a.name)}
                  </span>
                  <span style={css("font:400 21px/1.25 Newsreader")}>{a.name}</span>
                  <span style={css("font:400 13.5px/1.45 Geist;color:var(--ink2)")}>{a.role || "No role written yet"}</span>
                  <span style={css("font:400 12px Geist;color:var(--muted);margin-top:auto")}>
                    {plural(a.skills.length, "skill")} · {plural(a.context.length + a.library.length, "piece")} of context · runs through {a.runner}
                    {a.last_run ? ` · last run ${when(a.last_run.at)}` : ""}
                  </span>
                </button>
              ))}
              <button
                type="button"
                onClick={() => setCreating(true)}
                style={css("min-height:190px;border-radius:20px;border:1.5px dashed var(--line2);background:transparent;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;color:var(--ink2)")}
              >
                <span style={css("font:400 28px Newsreader")}>+</span>
                <span style={css("font:500 14px Geist")}>New agent profile</span>
                <span style={css("font:400 12px Geist;color:var(--muted)")}>{list.length ? "Your taste, sources and context" : "You have none yet. Start one here."}</span>
              </button>
            </div>
          )}
        </Loaded>
      </div>
      {creating ? <NewProfile onClose={() => setCreating(false)} /> : null}
      {open ? <ProfileView agent={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

function NewProfile({ onClose }: { onClose: () => void }) {
  const create = useCreateProfile();
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [prompt, setPrompt] = useState("");
  return (
    <Modal title="New agent profile" eyebrow="AGENT PROFILES" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          create.mutate({ name: name.trim(), role: role.trim(), prompt: prompt.trim() }, { onSuccess: onClose });
        }}
        style={css("display:flex;flex-direction:column;gap:12px")}
      >
        <label style={css(S.col)}>
          <span style={css("font:500 13px Geist")}>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} style={css(S.input)} />
        </label>
        <label style={css(S.col)}>
          <span style={css("font:500 13px Geist")}>Its role, like a job description</span>
          <input value={role} onChange={(e) => setRole(e.target.value)} style={css(S.input)} />
        </label>
        <label style={css(S.col)}>
          <span style={css("font:500 13px Geist")}>Its instructions, in your words</span>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5} style={css(`${S.input};resize:vertical;font:400 14px/1.55 Geist`)} />
        </label>
        <span style={css(S.small)}>Saved in your Brain with an undo point. Its own taste, tagged sources and packet come in a later release.</span>
        {create.error ? <Failure error={create.error} /> : null}
        <div style={css("display:flex;gap:8px")}>
          <Btn kind="primarySm" type="submit" disabled={create.isPending || !name.trim()}>
            {create.isPending ? "Saving…" : "Save the profile"}
          </Btn>
          <Btn kind="ghostSm" onClick={onClose}>
            Cancel
          </Btn>
        </div>
      </form>
    </Modal>
  );
}

function ProfileView({ agent, onClose }: { agent: WorkAgent; onClose: () => void }) {
  const ask = useAskProfile();
  const [text, setText] = useState("");
  const rows: [string, string[]][] = [
    ["Responsibilities", agent.responsibilities],
    ["Skills", agent.skills],
    ["Projects", agent.projects],
    ["Context", [...agent.context, ...agent.library]],
    ["Boundaries", agent.boundaries],
  ];
  return (
    <Modal title={agent.name} eyebrow="AGENT PROFILE" onClose={onClose} width={620}>
      <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>{agent.role || "No role written yet."}</span>
      {rows.map(([k, v]) => (
        <div key={k} style={css("display:grid;grid-template-columns:140px 1fr;gap:12px;font:400 14px Geist")}>
          <span style={css("color:var(--muted)")}>{k}</span>
          <span>{v.length ? v.join(", ") : "None"}</span>
        </div>
      ))}
      <div style={css("display:grid;grid-template-columns:140px 1fr;gap:12px;font:400 14px Geist")}>
        <span style={css("color:var(--muted)")}>Runs through</span>
        <span>{agent.runner}</span>
        <span style={css("color:var(--muted)")}>Kept at</span>
        <span style={css("font:400 12.5px 'Geist Mono';word-break:break-all")}>{agent.path}</span>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) ask.mutate({ name: agent.name, ask: text.trim() });
        }}
        style={css("display:flex;gap:8px")}
      >
        <input aria-label={`Ask ${agent.name}`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask it for something" style={css(`${S.input};flex:1;min-width:0`)} />
        <Btn kind="primarySm" type="submit" disabled={ask.isPending || !text.trim()}>
          {ask.isPending ? "Asking…" : "Ask"}
        </Btn>
      </form>
      {ask.data ? <Status kind="captured">Asked. It runs on this computer's CLI; follow it in Activity.</Status> : null}
      {ask.error ? <Failure error={ask.error} /> : null}
    </Modal>
  );
}

// ------------------------------------------------------------------ skills

function Skills() {
  const q = useSkills();
  const agent = useAgentPage();
  const [running, setRunning] = useState<SkillCard | null>(null);
  return (
    <div style={css("display:flex;flex-direction:column;gap:36px")}>
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap")}>
          <span style={css("font:400 15px Geist;color:var(--ink2)")}>Procedures your AI follows by itself. Run one here, or just ask for it in any AI.</span>
          <Btn kind="primary" disabled title="Not available here yet">
            New skill
          </Btn>
        </div>
        <span style={css("font:400 13px Geist;color:var(--muted)")}>Writing a new skill here isn't available yet. In any connected AI, say “save this as a skill”.</span>
      </div>
      <Loaded
        q={q}
        empty={(d) => (d.skills.length ? null : <Empty title="No skills of your own yet">Ask any connected AI to save a way of working as a skill. It waits in Catch up until you keep it.</Empty>)}
      >
        {(d) => (
          <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px")}>
            {d.skills.map((s) => (
              <div key={s.name} style={css(`${SURFACE};padding:22px;display:flex;flex-direction:column;gap:10px;min-height:180px`)}>
                <span style={css("font:500 11px 'Geist Mono';letter-spacing:.04em;color:var(--muted)")}>
                  {[s.category, s.last_run ? `last run ${when(s.last_run.at)}` : "not run yet"].filter(Boolean).join(" · ").toUpperCase()}
                </span>
                <span style={css("font:400 24px/1.25 Newsreader")}>{s.name}</span>
                <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{s.description}</span>
                {s.use === "run" ? (
                  <Btn kind="primarySm" style="margin-top:auto;align-self:flex-start;padding:7px 14px" onClick={() => setRunning(s)}>
                    Run
                  </Btn>
                ) : (
                  <span style={css("margin-top:auto;font:400 12px Geist;color:var(--muted)")}>
                    {s.use === "support" ? "Files other skills use, kept rather than run" : "Called by name in a conversation"}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </Loaded>
      {agent.data ? (
        <AgentSkillList actions={agent.data.actions} title="Comes with every Brain" />
      ) : agent.isLoading ? (
        <Loading />
      ) : agent.error ? (
        <Failure error={agent.error} retry={() => void agent.refetch()} />
      ) : null}
      {running ? <RunSkill skill={running} onClose={() => setRunning(null)} /> : null}
    </div>
  );
}

function RunSkill({ skill, onClose }: { skill: SkillCard; onClose: () => void }) {
  const run = useRunSkill();
  const [ask, setAsk] = useState("");
  return (
    <Modal title={`Run ${skill.name}`} eyebrow="SKILL" onClose={onClose}>
      <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{skill.description}</span>
      {run.data ? (
        <>
          <Status kind="captured">Started. It runs on this computer's CLI; follow it in Activity.</Status>
          <Btn kind="ghostSm" onClick={onClose}>
            Close
          </Btn>
        </>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (ask.trim()) run.mutate({ name: skill.name, ask: ask.trim() });
          }}
          style={css("display:flex;flex-direction:column;gap:10px")}
        >
          <label style={css(S.col)}>
            <span style={css("font:500 13px Geist")}>What should it do?</span>
            <textarea value={ask} onChange={(e) => setAsk(e.target.value)} rows={3} style={css(`${S.input};resize:vertical`)} />
          </label>
          {run.error ? <Failure error={run.error} /> : null}
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" type="submit" disabled={run.isPending || !ask.trim()}>
              {run.isPending ? "Starting…" : "Run"}
            </Btn>
            <Btn kind="ghostSm" onClick={onClose}>
              Cancel
            </Btn>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ------------------------------------------------------------------ alignment

const CHECKS: [string, string][] = [
  ["check-drift", "Drift"],
  ["tidy-repeats", "Repeats"],
  ["freshen-up", "Stale"],
  ["check-alignment", "Off-goal"],
  ["fill-gaps", "Gaps"],
];

function Alignment() {
  const q = useAgentPage();
  const proposals = useProposals();
  const jobs = useAgentJobs();
  useFinishedRefresh(jobs.data);
  const start = useStartAction();
  const answer = useAnswerAgentQuestion();
  const navigate = useNavigate();
  const [runAll, setRunAll] = useState<string | null>(null);
  return (
    <Loaded q={q}>
      {(agent) => {
        const waitingIds = new Set((proposals.data ?? []).map((p) => p.id));
        const checks = CHECKS.flatMap(([id, name]) => {
          const action = agent.actions.find((a) => a.id === id);
          return action ? [{ id, name, action }] : [];
        });
        const findings = (id: string) => agent.questions.filter((x) => x.action === id);
        const review = (id: string) => {
          const ids = new Set(agent.runs.filter((r) => r.action === id).flatMap((r) => r.proposals));
          return [...ids].filter((p) => waitingIds.has(p)).length;
        };
        const open = checks.reduce((n, c) => n + findings(c.id).length, 0);
        const needs = proposals.data ? checks.reduce((n, c) => n + review(c.id), 0) : null;
        const lastAt = agent.runs.find((r) => checks.some((c) => c.id === r.action))?.at;
        const any = (jobs.data ?? []).some((j) => j.kind === "action" && (j.status === "waiting" || j.status === "running"));
        const label = agent.provider?.label ?? agent.model;
        if (checks.length === 0) return <Empty title="No checks listed">The server lists none of the alignment checks for this Brain.</Empty>;
        return (
          <div style={css("display:flex;flex-direction:column;gap:40px")}>
            <div style={css("display:flex;align-items:center;gap:26px;flex-wrap:wrap")}>
              <div style={css("width:112px;height:112px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;background:var(--gray)")}>
                <div style={css("width:92px;height:92px;border-radius:50%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center")}>
                  <span style={css("font:400 28px Newsreader")}>{open}</span>
                  <span style={css("font:400 10px Geist;color:var(--muted)")}>to decide</span>
                </div>
              </div>
              <div style={css("flex:1;min-width:260px;display:flex;flex-direction:column;gap:6px")}>
                <span style={css("font:400 30px Newsreader")}>Brain upkeep</span>
                <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>
                  {plural(open, "finding")} to decide across {plural(checks.length, "check")} · {needs === null ? "counting what needs review…" : `${needs} need review in Catch up`} ·{" "}
                  {lastAt ? `last checked ${when(lastAt)}` : "not checked yet"}. There is no score: each finding says why.
                </span>
              </div>
              <Btn
                kind="primarySm"
                disabled={any || start.isPending}
                onClick={() => {
                  setRunAll(null);
                  void (async () => {
                    try {
                      for (const c of checks) await start.mutateAsync(c.id);
                      setRunAll(`Started ${plural(checks.length, "check")}. They run one after another through ${label}.`);
                    } catch {
                      // the error shows below
                    }
                  })();
                }}
              >
                {any ? "Running…" : "Run every check"}
              </Btn>
            </div>
            {runAll ? (
              <span role="status" style={css(S.muted)}>
                {runAll}
              </span>
            ) : null}
            {start.error ? <Failure error={start.error} /> : null}
            <div style={css("display:flex;flex-direction:column;gap:14px")}>
              <div style={css("display:flex;flex-direction:column;gap:3px")}>
                <span style={css("font:500 15px Geist")}>Checks</span>
                <span style={css(S.muted)}>Your knowledge agent runs these through {label} when you start them. Fixes go to Catch up for your yes.</span>
              </div>
              <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:14px")}>
                {checks.map((c) => {
                  const f = findings(c.id);
                  const last = lastRun(agent.runs, c.id);
                  const r = proposals.data ? review(c.id) : 0;
                  return (
                    <div key={c.id} style={css(`${SURFACE};padding:20px;display:flex;flex-direction:column;gap:10px`)}>
                      <div style={css("display:flex;align-items:center;gap:10px")}>
                        <span style={css(TAG)}>{c.name}</span>
                        <span style={css("margin-left:auto;font:400 12px Geist;color:var(--muted)")}>{last ? `Last checked ${when(last.at)}` : "Not checked yet"}</span>
                      </div>
                      <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{c.action.blurb}</span>
                      {f.map((x) => (
                        <div key={x.key} style={css("display:flex;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--line)")}>
                          <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:2px")}>
                            <span style={css("font:400 14px/1.4 Geist")}>{x.ask}</span>
                            <span style={css(S.small)}>
                              {x.target.title}
                              {x.why ? ` · ${x.why}` : ""}
                            </span>
                          </div>
                          <button type="button" disabled={answer.isPending} onClick={() => answer.mutate({ key: x.key, do: "dismiss" })} style={css("border:0;background:transparent;font:400 12px Geist;color:var(--muted)")}>
                            Ignore
                          </button>
                          {x.target.type === "note" ? (
                            <button
                              type="button"
                              disabled={answer.isPending}
                              onClick={() => answer.mutate({ key: x.key, do: "verify" })}
                              style={css("padding:5px 12px;border-radius:99px;background:var(--soft);border:0;font:500 12px Geist;color:var(--ink)")}
                            >
                              Still true
                            </button>
                          ) : null}
                        </div>
                      ))}
                      {last && f.length === 0 ? <span style={css("font:400 13px Geist;color:oklch(0.5 0.1 150)")}>No findings open from the last check.</span> : null}
                      {r ? (
                        <button type="button" onClick={() => navigate("/brain/catch-up")} style={css("align-self:flex-start;border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink)")}>
                          {plural(r, "suggestion")} need review in Catch up →
                        </button>
                      ) : null}
                      <JobRun action={c.action} runs={agent.runs} label={last ? "Check again" : "Check now"} compact />
                    </div>
                  );
                })}
              </div>
              {answer.error ? <Failure error={answer.error} /> : null}
            </div>
            <div style={css("display:flex;flex-direction:column;gap:12px")}>
              <span style={css("font:400 30px Newsreader")}>
                Pull in from your other tools
                <Later />
              </span>
              <span style={css("font:400 15px/1.55 Geist;color:var(--ink2);max-width:680px")}>
                Contxt's CLI bridges to the tools you already use. It pulls only what's relevant, and drops it in Capture, private until you distill it. This comes in a later release.
              </span>
            </div>
          </div>
        );
      }}
    </Loaded>
  );
}

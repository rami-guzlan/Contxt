// One project (v4 isProject, Release 1): Context, Tasks, Files and Outputs, all reading the same
// project record and task IDs. A pending update shows beside the approved value, never over it.
// Outputs are drafts that keep the record versions they read and never change records. Tasks
// hold Work with AI, the agent orchestrators, the agent tasks and the person's own tasks, with
// the orchestrators' activity beside them; Outputs groups what runs made by orchestrator and run.

import { type ReactNode, type RefObject, useCallback, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import type { BrainProjectDetail, OutputFile, TaskItem } from "../../api/types";
import { type Proposal, useAsk, useProposals, useSourceStatus, useWorkAsk, useWorkTimeline, type WorkJob } from "../api";
import { DistillThread } from "../components/DistillThread";
import { ProposalCard } from "../components/ProposalCard";
import { AgentTasks, type Go, OrchestratorActivity, OrchestratorOutputs, OrchestratorSheets, OrchestratorsPanel } from "../components/Orchestrators";
import { ReceiptView } from "../components/Receipt";
import { css, cx } from "../css";
import {
  flatTasks,
  useAddTask,
  useAiRequests,
  useBrainPreview,
  useBrainProject,
  useHandOff,
  useLive,
  useLiveAct,
  useMadeFrom,
  useNotes,
  useOutputs,
  useProjectTasks,
  useSetObjective,
  useSkills,
  useTellProject,
  useUpdateProject,
  useWorkAgents,
} from "../hooks/projects";
import { Btn, Chip, Empty, Failure, Loading, Modal, S, Status, when } from "../ui";
import { useOrchestrators } from "../hooks/orchestrators";
import type { WorkflowStep } from "../hooks/workflows";
import { ProjectWorkflows } from "../components/ProjectWorkflows";
import { ProjectStatus } from "./Projects";
import { AutoArea } from "../components/AutoArea";

type Tab = "context" | "tasks" | "files" | "outputs";

const TABS: [Tab, string, string][] = [
  ["context", "Context", "What your AI knows and sends"],
  ["tasks", "Tasks", "What needs doing"],
  ["files", "Files", "Sources for this project"],
  ["outputs", "Outputs", "What AI work produced"],
];

const tabStyle = (on: boolean) =>
  "padding:10px 18px;border-radius:12px;border:0;display:flex;flex-direction:column;align-items:flex-start;gap:1px;text-align:left;cursor:pointer;background:" +
  (on ? "var(--surface)" : "transparent") +
  ";box-shadow:" +
  (on ? "var(--shadow)" : "none") +
  ";color:var(--ink)";

const SECTION = "max-width:1120px;margin:0 auto;padding:28px 64px 96px;display:flex;flex-direction:column;gap:16px;box-sizing:border-box";
const LIST = "background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:4px 22px";
const ERR = "font:400 13px Geist;color:oklch(0.55 0.17 28)";

function Problem({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <span role="alert" style={css(ERR)}>
      {error instanceof Error ? error.message : String(error)}
    </span>
  );
}

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.some(([id]) => id === params.get("tab")) ? params.get("tab") : "context") as Tab;
  const project = useBrainProject(projectId);

  if (project.isLoading) {
    return (
      <div style={css(SECTION)}>
        <Loading what="Loading the project" />
      </div>
    );
  }
  if (project.error || !project.data) {
    return (
      <div style={css(SECTION)}>
        <button type="button" onClick={() => navigate("/projects")} style={css(S.link)}>
          ← Projects
        </button>
        <Failure error={project.error ?? new Error("This project could not be read.")} retry={() => void project.refetch()} />
      </div>
    );
  }
  const p = project.data;
  // Where the orchestrators' links go: Outputs (one orchestrator's runs), its sheet in
  // Context, or Catch up for a proposal.
  const go = (to: Go, orchestrator?: string) => {
    if (to === "cards") navigate("/brain/catch-up");
    else if (to === "sheet") setParams({});
    else setParams(orchestrator ? { tab: "outputs", runs: orchestrator } : { tab: "outputs" });
  };

  return (
    <div className="gn-page">
      <div style={css("max-width:1120px;margin:0 auto;padding:48px 64px 0;display:flex;flex-direction:column;gap:20px;box-sizing:border-box")}>
        <button type="button" onClick={() => navigate("/projects")} style={css(S.link)}>
          ← Projects
        </button>
        <div style={css("display:flex;flex-direction:column;gap:10px;max-width:760px")}>
          <div style={css("display:flex")}>
            <ProjectStatus status={p.status} />
          </div>
          <h1 style={css(S.h1)}>{p.title}</h1>
          <span style={css("font:400 17px/1.55 Geist;color:var(--ink2);text-wrap:pretty")}>{p.summary}</span>
        </div>
        <div role="tablist" aria-label="Project views" style={css("display:flex;gap:4px;padding:4px;border-radius:16px;background:var(--soft);align-self:flex-start;flex-wrap:wrap")}>
          {TABS.map(([id, label, desc]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setParams(id === "context" ? {} : { tab: id })} style={css(tabStyle(tab === id))}>
              <span style={css("font:500 14px Geist")}>{label}</span>
              <span style={css("font:400 12px Geist;opacity:.72")}>{desc}</span>
            </button>
          ))}
        </div>
      </div>
      {tab === "context" ? <ContextView p={p} /> : null}
      {tab === "tasks" ? <TasksView p={p} onGo={go} /> : null}
      {tab === "files" ? <FilesView p={p} /> : null}
      {tab === "outputs" ? <OutputsView p={p} runs={params.get("runs") ?? "all"} onRuns={(runs) => setParams({ tab: "outputs", runs })} onSheet={() => go("sheet")} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ Context

/** Proposals waiting for this project, wherever they came from. */
function forProject(list: Proposal[] | undefined, p: BrainProjectDetail): Proposal[] {
  return (list ?? []).filter((x) => {
    const target = x.target ?? {};
    if (target.project_id === p.id || target.project === p.id || target.focus === p.id) return true;
    const dest = `${x.destination ?? ""}`.toLowerCase();
    return Boolean(dest) && (dest.includes(p.id.toLowerCase()) || dest.includes(p.title.toLowerCase()));
  });
}

function ContextView({ p }: { p: BrainProjectDetail }) {
  const proposals = useProposals();
  const pending = forProject(proposals.data, p);
  const [thread, setThread] = useState<Proposal[] | null>(null);
  const closeThread = useCallback(() => setThread(null), []);
  const tell = useRef<HTMLTextAreaElement>(null);

  return (
    <div style={css("max-width:1120px;margin:0 auto;padding:28px 64px 96px;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:56px;box-sizing:border-box")}>
      <div style={css("grid-column:1 / -1")}>
        <AutoArea govKey={`packet:${p.id}`} area={`the ${p.title} packet`} what="It keeps this project's packet and live status current from each beat; open, edit and undo as usual." regions={[]} />
      </div>
      <div style={css("grid-column:1 / -1")}>
        <OrchestratorSheets projectId={p.id} />
      </div>
      {proposals.error ? (
        <div style={css("grid-column:1 / -1")}>
          <Failure error={proposals.error} retry={() => void proposals.refetch()} />
        </div>
      ) : null}
      {pending.map((x) => (
        <div key={x.id} style={css("grid-column:1 / -1;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px;margin-bottom:-24px;align-items:start")}>
          <div style={css("padding:16px 18px;border-radius:18px;background:oklch(0.62 0.14 150 / .12);display:flex;flex-direction:column;gap:4px")}>
            <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em")}>{(x.title || x.operation || "Record").toUpperCase()} · CURRENT · APPROVED</span>
            <span style={css("font:400 20px/1.35 Newsreader")}>{x.current_body?.trim() || "Nothing approved here yet."}</span>
            <span style={css("font:400 12.5px Geist;color:var(--ink2)")}>
              {x.current_body ? "The approved value stays until you decide." : "Keeping the proposal adds it; nothing is sent from it before then."}
            </span>
          </div>
          <ProposalCard p={x} onBrain={() => setThread([x])} />
        </div>
      ))}

      <div style={css("display:flex;flex-direction:column;gap:32px")}>
        <Progress p={p} />
        <Objective p={p} />
        <LiveSheets p={p} />
        {p.files.length > 0 ? (
          <div style={css("display:flex;flex-direction:column;gap:10px")}>
            <span style={css("font:500 15px Geist")}>Files</span>
            <div style={css("display:flex;gap:10px;flex-wrap:wrap")}>
              {p.files.map((f) => (
                <span key={f.path} style={css("padding:10px 14px;border-radius:12px;background:var(--soft);font:400 14px Geist")}>
                  {f.title || f.filename || f.path}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        <Asked p={p} />
      </div>

      <div style={css("display:flex;flex-direction:column;gap:18px")}>
        <TellAgent p={p} box={tell} />
        <Kept p={p} waiting={pending.length} onAdd={() => tell.current?.focus()} />
        <Packet p={p} />
        <div style={css("margin-top:12px;padding:18px;border-radius:18px;background:var(--soft);display:flex;flex-direction:column;gap:10px")}>
          <span style={css("font:500 14px Geist")}>Also known as</span>
          <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
            {p.aliases.length === 0 ? <span style={css(S.small)}>No other names yet.</span> : null}
            {p.aliases.map((k) => (
              <span key={k} style={css("padding:4px 10px;border-radius:99px;background:var(--surface);font:400 13px Geist")}>
                {k}
              </span>
            ))}
            <button
              type="button"
              disabled
              title="Adding a name here is not available yet"
              style={css("padding:4px 10px;border-radius:99px;border:1px dashed var(--line2);background:transparent;font:400 13px Geist;color:var(--muted)")}
            >
              + add
            </button>
          </div>
          <span style={css(S.small)}>When you say any of these, your AI knows you mean this project. Adding one here is not available yet.</span>
        </div>
      </div>

      {thread ? <DistillThread proposals={thread} sourceTitle={p.title} onClose={closeThread} /> : null}
    </div>
  );
}

function Progress({ p }: { p: BrainProjectDetail }) {
  const update = useUpdateProject(p.id);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [all, setAll] = useState(false);
  const latest = p.updates[0];
  const current = p.state.current || latest?.summary || "";
  const next = p.state.next || "";
  const shown = all ? p.updates : p.updates.slice(0, 5);

  function save() {
    const line = text.trim();
    if (!line) return;
    update.mutate(
      { summary: line.slice(0, 300), state: { current: line } },
      {
        onSuccess: () => {
          setText("");
          setOpen(false);
        },
      },
    );
  }

  return (
    <>
      <div style={css("background:var(--surface);border-radius:22px;padding:28px;display:flex;flex-direction:column;gap:18px;box-shadow:var(--shadow)")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap")}>
          <div style={css("display:flex;align-items:center;gap:8px")}>
            <span style={css("width:8px;height:8px;border-radius:50%;background:oklch(0.7 0.14 150)")} />
            <span style={css("font:500 13px Geist;color:var(--ink)")}>Latest progress update</span>
            <span style={css("font:400 13px Geist;color:var(--muted)")}>· what your AI reads first</span>
          </div>
          <span style={css("font:400 12px Geist;color:var(--faint)")}>{latest ? `${when(latest.at)} · ${latest.actor || "unknown"}` : "No updates yet"}</span>
        </div>
        <span style={css("font:400 23px/1.45 Newsreader;text-wrap:pretty")}>
          {current || "Where it stands isn't recorded yet."}
          {next ? (
            <>
              {" "}
              Next up: <span style={css("background:oklch(0.74 0.12 320 / .22);padding:0 4px;border-radius:4px")}>{next}</span>
            </>
          ) : null}
        </span>
        {p.state.blockers ? <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>Blocked by: {p.state.blockers}</span> : null}
        {open ? (
          <div style={css("display:flex;flex-direction:column;gap:10px")}>
            <textarea
              aria-label="Progress update"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              placeholder="What changed? One line."
              style={css("border:1px solid var(--line2);border-radius:14px;padding:12px 14px;outline:none;resize:none;background:var(--bg);color:var(--ink);font:400 15px/1.5 Geist")}
            />
            <div style={css("display:flex;gap:8px")}>
              <Btn kind="primarySm" onClick={save} disabled={!text.trim() || update.isPending}>
                {update.isPending ? "Saving…" : "Save"}
              </Btn>
              <Btn kind="ghostSm" onClick={() => setOpen(false)}>
                Cancel
              </Btn>
            </div>
            <Problem error={update.error} />
          </div>
        ) : (
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" onClick={() => setOpen(true)}>
              Post an update
            </Btn>
            <span style={css("font:400 12px/1.4 Geist;color:var(--muted);align-self:center")}>Replaces this line, and adds it to the timeline.</span>
          </div>
        )}
      </div>

      <div style={css("display:flex;flex-direction:column")}>
        <div style={css("display:flex;flex-direction:column;gap:2px;margin-bottom:16px")}>
          <span style={css("font:500 15px Geist")}>Progress</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>Every update, newest first. Your AI sees the last five.</span>
        </div>
        {p.updates.length === 0 ? <span style={css(S.muted)}>No progress recorded yet. Post the first update above.</span> : null}
        {shown.map((u, i) => (
          <div key={u.seq} style={css("display:flex;gap:16px")}>
            <div style={css("display:flex;flex-direction:column;align-items:center")}>
              <span style={css(`width:10px;height:10px;border-radius:50%;flex:none;margin-top:5px;background:${i === 0 ? "oklch(0.7 0.14 150)" : "var(--line2)"}`)} />
              {i < shown.length - 1 ? <span style={css("width:2px;flex:1;background:var(--line2)")} /> : null}
            </div>
            <div style={css("padding-bottom:20px;display:flex;flex-direction:column;gap:4px")}>
              <span style={css("font:400 15px Geist")}>{u.summary}</span>
              <div style={css("display:flex;gap:8px;align-items:center")}>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>{when(u.at)}</span>
                <span style={css("padding:1px 8px;border-radius:99px;background:var(--soft);font:500 11px Geist;color:var(--ink2)")}>{u.actor || "unknown"}</span>
              </div>
            </div>
          </div>
        ))}
        {p.updates.length > 5 ? (
          <button
            type="button"
            onClick={() => setAll(!all)}
            style={css("align-self:flex-start;display:flex;align-items:center;gap:6px;padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 13px Geist;color:var(--ink)")}
          >
            {all ? "Show the last five" : `Show all ${p.updates.length}`} <span style={css("font:400 11px Geist")}>{all ? "▴" : "▾"}</span>
          </button>
        ) : null}
      </div>
    </>
  );
}

function Objective({ p }: { p: BrainProjectDetail }) {
  const set = useSetObjective(p.id);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(p.objective ?? "");
  const [reason, setReason] = useState("");
  // A stable close keeps the dialog from taking focus back on every keystroke.
  const close = useCallback(() => setOpen(false), []);
  return (
    <div style={css("display:flex;align-items:flex-start;gap:14px;padding:18px 20px;border-radius:18px;border:1px solid var(--line)")}>
      <div style={css("flex:1;display:flex;flex-direction:column;gap:4px")}>
        <span style={css("font:500 11px 'Geist Mono';color:var(--muted);letter-spacing:.04em")}>OBJECTIVE · OPENS EVERY BRIEF</span>
        <span style={css("font:400 16px/1.5 Geist")}>{p.objective || "No objective yet. Say the output this project is chasing."}</span>
      </div>
      <button type="button" onClick={() => setOpen(true)} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2)")}>
        Change
      </button>
      {open ? (
        <Modal title="Change the objective" eyebrow="OPENS EVERY BRIEF" onClose={close}>
          <textarea aria-label="Objective" value={text} onChange={(e) => setText(e.target.value)} rows={3} style={css(S.input + ";resize:none;line-height:1.5")} />
          <input aria-label="Why it changes" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why it changes, in a few words" style={css(S.input)} />
          <span style={css(S.small)}>The old objective stays in its history, with an undo point.</span>
          <Problem error={set.error} />
          <div style={css("display:flex;gap:8px;justify-content:flex-end")}>
            <Btn kind="ghost" onClick={close}>
              Cancel
            </Btn>
            <Btn
              kind="primary"
              disabled={!text.trim() || !reason.trim() || set.isPending}
              onClick={() => set.mutate({ objective: text.trim(), reason: reason.trim() }, { onSuccess: close })}
            >
              {set.isPending ? "Saving…" : "Save"}
            </Btn>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function LiveSheets({ p }: { p: BrainProjectDetail }) {
  const navigate = useNavigate();
  const live = useLive();
  const act = useLiveAct();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const scoped = (live.data?.sheets ?? []).filter((s) => [p.id, `project:${p.id}`, p.title].includes(s.scope));
  return (
    <div style={css("display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:3px")}>
          <div style={css("display:flex;align-items:center;gap:8px")}>
            <span style={css("font:400 26px Newsreader")}>Live context sheets</span>
            <span style={css("padding:3px 9px;border-radius:99px;background:oklch(0.74 0.12 150 / .18);color:oklch(0.45 0.1 150);font:500 11px Geist")}>Always changing</span>
          </div>
          <span style={css("font:400 13px/1.5 Geist;color:var(--muted);max-width:520px")}>
            What's true right now, for your AIs. Meetings and captures keep these current, and every cell keeps its history. Not stored in the long-term Brain.
          </span>
        </div>
        <Btn kind="soft" onClick={() => setAdding(true)}>
          + New live sheet
        </Btn>
      </div>
      {adding ? (
        <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
          <input aria-label="Sheet name" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Name the sheet" style={css(S.input + ";flex:1;min-width:0;font-size:14px")} />
          <Btn
            kind="primarySm"
            disabled={!title.trim() || act.isPending}
            onClick={() =>
              act.mutate(
                { action: "create_sheet", fields: { title: title.trim(), scope: p.id } },
                {
                  onSuccess: () => {
                    setTitle("");
                    setAdding(false);
                  },
                },
              )
            }
          >
            Create
          </Btn>
          <Btn kind="ghostSm" onClick={() => setAdding(false)}>
            Cancel
          </Btn>
        </div>
      ) : null}
      <Problem error={act.error} />
      {live.isLoading ? (
        <Loading what="Loading sheets" />
      ) : live.error ? (
        <Failure error={live.error} retry={() => void live.refetch()} />
      ) : scoped.length === 0 ? (
        <span style={css(S.muted)}>No live sheets for this project yet.</span>
      ) : (
        <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px")}>
          {scoped.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => navigate(`/brain/sheets/${encodeURIComponent(s.id)}`)}
              style={css("padding:18px;border-radius:18px;border:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;gap:8px;text-align:left;color:var(--ink)")}
            >
              <span style={css("font:500 15px Geist")}>{s.title}</span>
              {s.description ? <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{s.description}</span> : null}
              <span style={css("font:400 12px Geist;color:var(--faint)")}>
                {s.columns.length} {s.columns.length === 1 ? "column" : "columns"} · keyed by {s.key || "row"}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Asked({ p }: { p: BrainProjectDetail }) {
  const requests = useAiRequests({ limit: 50 });
  const [open, setOpen] = useState(false);
  const [receipt, setReceipt] = useState<string | null>(null);
  const mine = (requests.data?.requests ?? []).filter((r) => r.project?.id === p.id);
  return (
    <div style={css("display:flex;flex-direction:column")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={css("display:flex;align-items:center;gap:10px;padding:12px 0;border:0;border-top:1px solid var(--line);background:transparent;text-align:left;color:var(--ink2);width:100%;font:400 14px Geist")}
      >
        <span style={css("flex:1")}>What your AIs asked about it · {requests.data ? mine.length : "…"}</span>
        <span style={css("font:400 12px Geist")}>{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        requests.isLoading ? (
          <Loading />
        ) : requests.error ? (
          <Failure error={requests.error} retry={() => void requests.refetch()} />
        ) : mine.length === 0 ? (
          <span style={css(S.muted + ";padding:8px 0")}>No AI has asked about this project in the last 50 requests.</span>
        ) : (
          mine.map((q) => (
            <div key={q.id} style={css("display:flex;flex-direction:column")}>
              <button
                type="button"
                onClick={() => setReceipt(receipt === q.id ? null : q.id)}
                style={css("display:flex;align-items:center;gap:14px;padding:11px 0;border:0;border-top:1px solid var(--line);background:transparent;text-align:left;color:var(--ink);width:100%")}
              >
                <span style={css("font:500 12px Geist;width:110px;color:var(--ink2)")}>{q.app}</span>
                <span style={css("font:400 14px Geist;flex:1")}>“{q.request}”</span>
                <span style={css("font:400 12px Geist;color:var(--muted)")}>{when(q.at)}</span>
              </button>
              {receipt === q.id ? <ReceiptView id={q.id} defaultOpen /> : null}
            </div>
          ))
        )
      ) : null}
    </div>
  );
}

function TellAgent({ p, box }: { p: BrainProjectDetail; box: RefObject<HTMLTextAreaElement | null> }) {
  const [mode, setMode] = useState<"capture" | "ask">("capture");
  const [text, setText] = useState("");
  const tellIt = useTellProject({ id: p.id, title: p.title });
  const ask = useAsk();
  const proposals = useProposals();
  const [thread, setThread] = useState(false);
  const closeThread = useCallback(() => setThread(false), []);
  const cap = mode === "capture";
  const busy = tellIt.isPending || ask.isPending;
  const made = tellIt.data;
  const fromIt = made
    ? (proposals.data ?? []).filter((x) => x.task_id === made.task.id || x.sources?.includes(made.note.id) || x.source?.id === made.note.id)
    : [];

  function send() {
    const words = text.trim();
    if (!words || busy) return;
    if (cap) tellIt.mutate(words, { onSuccess: () => setText("") });
    else ask.mutate(`About the project ${p.title}: ${words}`);
  }

  const seg = (on: boolean) =>
    `flex:1;padding:5px 0;border-radius:99px;border:0;font:${on ? 500 : 400} 12.5px Geist;background:${on ? "var(--surface)" : "transparent"};color:var(--ink);${on ? "box-shadow:0 1px 2px rgba(30,25,15,.08)" : ""}`;

  return (
    <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:22px;display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;align-items:center;gap:12px")}>
        <span style={css("width:32px;height:32px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center;flex:none")}>
          <span style={css("width:2px;height:14px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
        </span>
        <div style={css("flex:1;display:flex;flex-direction:column;gap:1px")}>
          <span style={css("font:500 15px Geist")}>Tell it about this project</span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>Working on {p.title}</span>
        </div>
        <div role="tablist" aria-label="Tell or ask" style={css("display:flex;gap:2px;padding:3px;border-radius:99px;background:var(--soft);width:180px")}>
          {(
            [
              ["capture", "Capture"],
              ["ask", "Ask"],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={mode === id} onClick={() => setMode(id)} style={css(seg(mode === id))}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>
        {cap
          ? "Type everything at once. It's saved as a capture in this project, and Distill proposes where each piece goes. Nothing is kept until you keep it."
          : "Ask anything about this project. The answer shows exactly what your AI was handed."}
      </span>
      <div style={css("border:1px solid var(--line2);border-radius:16px;padding:12px 12px 10px 14px;display:flex;flex-direction:column;gap:8px;background:var(--bg)")}>
        <textarea
          ref={box}
          aria-label={cap ? "Tell it about this project" : "Ask about this project"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
          }}
          rows={3}
          placeholder={cap ? "What happened, what was decided, what changed…" : "Where does this stand? What's still open?"}
          style={css("border:0;outline:none;resize:none;background:transparent;color:var(--ink);font:400 15px/1.5 Geist;padding:0")}
        />
        <div style={css("display:flex;align-items:center;gap:8px")}>
          <span style={css("flex:1")} />
          <Btn kind="primarySm" onClick={send} disabled={!text.trim() || busy}>
            {busy ? (cap ? "Saving…" : "Asking…") : cap ? "Sort it" : "Ask"}
          </Btn>
        </div>
      </div>
      <Problem error={cap ? tellIt.error : ask.error} />
      {cap && made ? (
        <div role="status" style={css("display:flex;flex-direction:column;gap:8px;padding:12px 14px;border-radius:14px;background:var(--soft)")}>
          <span style={css("font:400 13.5px/1.5 Geist")}>
            Saved as a capture in this project. Distill is reading it ({made.task.id}). Its proposals wait for you; nothing is searchable until you keep it.
          </span>
          <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
            <Btn kind="ghostSm" onClick={() => setThread(true)} disabled={fromIt.length === 0}>
              See it on your Brain
            </Btn>
            <span style={css(S.small)}>{fromIt.length ? `${fromIt.length} proposed` : "Proposals show here when Distill finishes."}</span>
          </div>
        </div>
      ) : null}
      {!cap && ask.data ? (
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <span style={css("font:400 15px/1.55 Geist;white-space:pre-line")}>{ask.data.answer}</span>
          <span style={css(S.small)}>
            {ask.data.provider.label}
            {ask.data.provider.model ? ` · ${ask.data.provider.model}` : ""}
          </span>
          {ask.data.receipts.map((id) => (
            <ReceiptView key={id} id={id} />
          ))}
        </div>
      ) : null}
      {thread && made ? <DistillThread proposals={fromIt} sourceTitle={`About ${p.title}`} onClose={closeThread} /> : null}
    </div>
  );
}

const GROUPS: [string, (kind: string) => boolean][] = [
  ["Rules", (k) => ["rule", "correction", "must-hold"].includes(k)],
  ["Preferences", (k) => k === "preference"],
  ["Facts and decisions", (k) => !["rule", "correction", "must-hold", "preference", "reference"].includes(k)],
];

function Kept({ p, waiting, onAdd }: { p: BrainProjectDetail; waiting: number; onAdd: () => void }) {
  const navigate = useNavigate();
  const [refs, setRefs] = useState(false);
  const kindOf = (n: BrainProjectDetail["notes"][number]) => String(n.type || n.kind || "").toLowerCase();
  const references = p.notes.filter((n) => kindOf(n) === "reference");
  return (
    <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:20px;display:flex;flex-direction:column;gap:16px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px")}>
        <div style={css("display:flex;flex-direction:column;gap:2px")}>
          <span style={css("font:500 15px Geist")}>Kept with this project</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>Only true here. Sent with every request about it.</span>
        </div>
        <button type="button" onClick={() => navigate("/brain/catch-up")} style={css("border:0;background:transparent;font:400 12px Geist;color:var(--muted);text-align:right")}>
          {waiting ? `${waiting} waiting in Catch up` : "Nothing waiting"}
        </button>
      </div>
      {GROUPS.map(([label, test]) => {
        const items = p.notes.filter((n) => test(kindOf(n)));
        return (
          <div key={label} style={css("display:flex;flex-direction:column;gap:6px")}>
            <span style={css("font:500 12px Geist;color:var(--muted)")}>{label}</span>
            {items.length === 0 ? <span style={css("font:400 13px Geist;color:var(--faint)")}>None yet.</span> : null}
            {items.map((k) => (
              <div key={k.id} style={css("display:flex;gap:10px;align-items:flex-start")}>
                <span style={css("width:7px;height:7px;border-radius:50%;flex:none;margin-top:7px;background:var(--ink2)")} />
                <span style={css("font:400 14px/1.45 Geist;flex:1")}>{k.summary || k.title}</span>
              </div>
            ))}
          </div>
        );
      })}
      <button type="button" onClick={onAdd} style={css("align-self:flex-start;border:0;background:transparent;padding:2px 0;font:400 13px Geist;color:var(--muted)")}>
        + Add (tell it above; it waits for your review)
      </button>
      <div style={css("display:flex;flex-direction:column;border-top:1px solid var(--line);padding-top:4px")}>
        <button
          type="button"
          aria-expanded={refs}
          onClick={() => setRefs(!refs)}
          style={css("display:flex;align-items:center;gap:8px;padding:10px 0;border:0;background:transparent;text-align:left;color:var(--ink);width:100%")}
        >
          <span style={css("font:500 12px Geist;color:var(--muted);flex:1")}>From captures</span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>{references.length} {references.length === 1 ? "reference" : "references"}</span>
          <span style={css("font:400 11px Geist;color:var(--muted)")}>{refs ? "▾" : "▸"}</span>
        </button>
        {refs ? (
          <div style={css("display:flex;flex-direction:column;gap:6px")}>
            {references.length === 0 ? (
              <span style={css("font:400 13px Geist;color:var(--muted);padding:4px 0 8px")}>Nothing yet. Distill a meeting or upload into this project.</span>
            ) : null}
            {references.map((r) => (
              <div key={r.id} style={css("padding:10px 12px;border-radius:12px;background:var(--soft);display:flex;flex-direction:column;gap:1px")}>
                <span style={css("font:400 14px Geist")}>{r.title}</span>
                <span style={css("font:500 10px 'Geist Mono';color:var(--muted);letter-spacing:.03em")}>{r.added ? `ADDED ${when(r.added).toUpperCase()}` : "REFERENCE"}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Packet({ p }: { p: BrainProjectDetail }) {
  const request = p.objective || p.title;
  const preview = useBrainPreview(request, p.id);
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const kind = "padding:1px 7px;border-radius:6px;background:var(--soft);font:500 10.5px 'Geist Mono';color:var(--ink2);flex:none";

  function copy(text: string) {
    navigator.clipboard?.writeText(text).then(
      () => setCopied("Copied."),
      () => setCopied("Couldn't copy. Select the text and copy it yourself."),
    );
  }

  return (
    <div style={css("position:relative;background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:20px;display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:500 15px Geist")}>Project packet</span>
        <span style={css("font:400 13px/1.45 Geist;color:var(--muted)")}>
          Exactly what goes with a request about this project. Shown for: “{request}”.
        </span>
      </div>
      {preview.isLoading ? (
        <Loading what="Building the packet" />
      ) : preview.error ? (
        <Failure error={preview.error} retry={() => void preview.refetch()} />
      ) : preview.data ? (
        <>
          <div style={css("display:flex;justify-content:space-between;font:400 12px Geist;color:var(--muted)")}>
            <span>
              {preview.data.notes.length} {preview.data.notes.length === 1 ? "note" : "notes"} · {preview.data.sections.length}{" "}
              {preview.data.sections.length === 1 ? "file section" : "file sections"}
            </span>
            <span>{preview.data.tokens.toLocaleString()} tokens</span>
          </div>
          {preview.data.notes.length > 0 ? (
            <PacketGroup label="Notes by meaning">
              {preview.data.notes.map((n) => (
                <PacketRow key={n.id} kind={n.kind || "note"} kindStyle={kind} title={n.title} why={n.why} />
              ))}
            </PacketGroup>
          ) : null}
          {preview.data.sections.length > 0 ? (
            <PacketGroup label="File pointers">
              {preview.data.sections.map((s) => (
                <PacketRow key={s.id} kind="file" kindStyle={kind} title={`${s.title}${s.label ? ` · ${s.label}` : ""}`} why={s.why} />
              ))}
            </PacketGroup>
          ) : null}
          {preview.data.notes.length + preview.data.sections.length === 0 ? <span style={css(S.muted)}>Nothing from the Brain matches yet; only the project brief goes.</span> : null}
        </>
      ) : null}
      <button
        type="button"
        disabled
        title="Pinning notes to the packet is not available yet"
        style={css("padding:10px;border-radius:12px;border:1.5px dashed var(--line2);background:transparent;font:500 13px Geist;color:var(--muted)")}
      >
        + Add notes, categories or files · not available yet
      </button>
      {preview.data ? (
        <button type="button" aria-expanded={show} onClick={() => setShow(!show)} style={css("align-self:flex-start;border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink2)")}>
          {show ? "Hide what's sent" : "See exactly what's sent"}
        </button>
      ) : null}
      {show && preview.data ? (
        <pre style={css("margin:0;padding:14px;border-radius:12px;background:var(--code);color:#d8d5cd;font:400 11px/1.6 'Geist Mono';white-space:pre-wrap;max-height:260px;overflow:auto")}>
          {preview.data.text}
        </pre>
      ) : null}
      <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
        <Btn kind="primarySm" disabled title="Saving a packet of your own picks is not available yet">
          Save packet
        </Btn>
        <Btn kind="ghostSm" disabled={!preview.data} onClick={() => preview.data && copy(preview.data.text)}>
          Copy
        </Btn>
        {copied ? <span role="status" style={css(S.small)}>{copied}</span> : null}
      </div>
      <span style={css("font:400 12px/1.5 Geist;color:var(--muted)")}>
        Files go as pointers by default, so the AI opens them only when it needs to. Must-hold rules are always added on top.
      </span>
    </div>
  );
}

function PacketGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={css("display:flex;flex-direction:column")}>
      <span style={css("font:500 12px Geist;color:var(--muted);padding-bottom:4px")}>{label}</span>
      {children}
    </div>
  );
}

function PacketRow({ kind, kindStyle, title, why }: { kind: string; kindStyle: string; title: string; why: string }) {
  return (
    <div title={why} style={css("display:flex;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--line)")}>
      <span style={css(kindStyle)}>{kind}</span>
      <span style={css("font:400 13px/1.35 Geist;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap")}>{title}</span>
    </div>
  );
}

// ------------------------------------------------------------------ Tasks

const JOB_WORDS: Record<string, [string, string]> = {
  queued: ["analysis_pending", "Queued"],
  ready: ["analysis_pending", "Ready to run"],
  starting: ["analysis_pending", "Starting"],
  running: ["indexing", "Running"],
  in_progress: ["indexing", "Running"],
  claimed: ["indexing", "Running"],
  succeeded: ["searchable", "Done · in Outputs"],
  completed: ["searchable", "Done · in Outputs"],
  awaiting_review: ["review", "Waiting for your review"],
  failed: ["failed", "Failed"],
  cancelled: ["excluded", "Stopped"],
  canceled: ["excluded", "Stopped"],
};

function TasksView({ p, onGo }: { p: BrainProjectDetail; onGo: (to: Go, orchestrator?: string) => void }) {
  const overview = useOrchestrators(p.id);
  const [draft, setDraft] = useState<WorkflowStep | null>(null);
  return (
    <div style={css(SECTION + ";gap:28px")}>
      <WorkWithAI p={p} onSaveAsWorkflow={setDraft} />
      <Timeline p={p} />
      <ProjectWorkflows project={p.id} clis={overview.data?.clis ?? []} draft={draft} onDraftUsed={() => setDraft(null)} />
      <OrchestratorsPanel projectId={p.id} onGo={onGo} />
      <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:24px;align-items:start")}>
        <div style={css("display:flex;flex-direction:column;gap:22px")}>
          <AgentTasks projectId={p.id} />
          <ProjectTodos p={p} />
        </div>
        <OrchestratorActivity projectId={p.id} onGo={onGo} />
      </div>
    </div>
  );
}

// Where each CLI sends the prompt and the project's context.
const PROVIDER: Record<string, string> = { claude: "Anthropic", codex: "OpenAI", gemini: "Google" };

function WorkWithAI({ p, onSaveAsWorkflow }: { p: BrainProjectDetail; onSaveAsWorkflow: (step: WorkflowStep) => void }) {
  const skills = useSkills();
  const agents = useWorkAgents();
  const ask = useWorkAsk();
  const overview = useOrchestrators(p.id);
  const [prompt, setPrompt] = useState("");
  const [skill, setSkill] = useState<string | null>(null);
  const [agent, setAgent] = useState<string | null>(null);
  const [runner, setRunner] = useState("claude");
  const [model, setModel] = useState<string | null>(null);
  const runnable = (skills.data?.skills ?? []).filter((s) => s.use === "run");
  const profiles = agents.data ?? [];
  const clis = overview.data?.clis ?? [];
  const cli = clis.find((c) => c.id === runner);
  const label = cli?.label ?? "Claude Code";

  function send() {
    const words = prompt.trim();
    if (!words || ask.isPending) return;
    ask.mutate(
      { project: p.id, prompt: words, skill: skill ?? undefined, agent: agent ?? undefined, runner, model: model ?? undefined },
      { onSuccess: () => setPrompt("") },
    );
  }

  // This prompt, with its skill or agent, CLI and model, as step 1 of a new workflow.
  function saveAsWorkflow() {
    const words = prompt.trim();
    if (!words) return;
    const how = { runner: runner as WorkflowStep["runner"], model, gate: false, budget: {} };
    if (skill) onSaveAsWorkflow({ kind: "skill", skill, ask: words, ...how });
    else if (agent) onSaveAsWorkflow({ kind: "agent", agent, ask: words, ...how });
    else onSaveAsWorkflow({ kind: "prompt", text: words, ...how });
  }

  return (
    <div style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:16px 18px;display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={css("width:26px;height:26px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center;flex:none")}>
          <span style={css("width:2px;height:12px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
        </span>
        <span style={css("font:500 14px Geist")}>Work with AI</span>
        <span style={css("font:400 13px Geist;color:var(--muted)")}>Runs on your computer, with this project's packet. Results land in Outputs as drafts.</span>
      </div>
      <textarea
        aria-label="What should the AI do"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
        }}
        rows={2}
        placeholder={`Ask ${label} to do something here.`}
        style={css("border:0;outline:none;resize:none;background:transparent;color:var(--ink);font:400 16px/1.5 Geist;padding:2px")}
      />
      <div style={css("display:flex;align-items:center;gap:6px;flex-wrap:wrap")}>
        <span style={css("font:400 12px Geist;color:var(--muted);margin-right:2px")}>Skill</span>
        {skills.isLoading ? <span style={css(S.small)}>Loading…</span> : null}
        {skills.error ? <span style={css(S.small)}>Skills couldn't be read.</span> : null}
        {skills.data && runnable.length === 0 ? <span style={css(S.small)}>None yet</span> : null}
        {runnable.map((s) => (
          <Chip key={s.name} on={skill === s.name} onClick={() => setSkill(skill === s.name ? null : s.name)}>
            {s.name}
          </Chip>
        ))}
        <span style={css("font:400 12px Geist;color:var(--muted);margin:0 2px 0 8px")}>Agent</span>
        {agents.isLoading ? <span style={css(S.small)}>Loading…</span> : null}
        {agents.error ? <span style={css(S.small)}>Agents couldn't be read.</span> : null}
        {agents.data && profiles.length === 0 ? <span style={css(S.small)}>None yet</span> : null}
        {profiles.map((a) => (
          <Chip key={a.name} on={agent === a.name} onClick={() => setAgent(agent === a.name ? null : a.name)}>
            {a.name}
          </Chip>
        ))}
      </div>
      <div style={css("display:flex;align-items:center;gap:6px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:10px")}>
        <span style={css("font:400 12px Geist;color:var(--muted);margin-right:2px")}>Runs in</span>
        {(clis.length ? clis : [{ id: "claude", label: "Claude Code", models: [], one_click: true }]).map((c) => (
          <Chip
            key={c.id}
            on={runner === c.id}
            onClick={() => {
              setRunner(c.id);
              setModel(null);
            }}
          >
            {c.label}
          </Chip>
        ))}
        {cli?.models.length ? (
          <select
            aria-label="Model"
            value={model ?? ""}
            onChange={(e) => setModel(e.target.value || null)}
            style={css("border:1px solid var(--line2);border-radius:99px;background:transparent;color:var(--ink);font:400 12.5px Geist;padding:4px 10px")}
          >
            <option value="">Its usual model</option>
            {cli.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        ) : null}
        <div style={css("margin-left:auto;display:flex;align-items:center;gap:6px")}>
          <Btn disabled={!prompt.trim()} onClick={saveAsWorkflow}>
            Save as workflow
          </Btn>
          <button
            type="button"
            title="Send"
            aria-label={`Send to ${label}`}
            onClick={send}
            disabled={!prompt.trim() || ask.isPending}
            style={css("width:34px;height:34px;border-radius:50%;background:var(--ink);color:var(--bg);border:0;font:500 15px Geist")}
          >
            ↑
          </button>
        </div>
      </div>
      {ask.isPending ? <span role="status" style={css(S.small)}>Starting the job…</span> : null}
      {ask.isSuccess ? <span role="status" style={css(S.small)}>Started. It shows in the timeline below.</span> : null}
      <Problem error={ask.error} />
      <span style={css(S.small)}>
        {label} sends this prompt and the project's context to {PROVIDER[runner] ?? "its provider"}.
        {cli && !cli.one_click ? " It has no tools here: it answers once, and the answer is saved to Outputs." : ""}
      </span>
    </div>
  );
}

function Timeline({ p }: { p: BrainProjectDetail }) {
  const timeline = useWorkTimeline(p.id);
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px")}>
      <div style={css("display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:500 15px Geist")}>AI work here</span>
        <span style={css(S.muted)}>Each job, newest first: what ran, what it made and proposed, and what it cost.</span>
      </div>
      {timeline.isLoading ? (
        <Loading what="Loading AI work" />
      ) : timeline.error ? (
        <Failure error={timeline.error} retry={() => void timeline.refetch()} />
      ) : (timeline.data ?? []).length === 0 ? (
        <Empty title="No AI work here yet">Ask above; each job shows here with its status, model and cost.</Empty>
      ) : (
        <div style={css(LIST)}>
          {(timeline.data ?? []).map((j) => (
            <JobRow key={j.task_id} j={j} />
          ))}
        </div>
      )}
    </div>
  );
}

function JobRow({ j }: { j: WorkJob }) {
  const [kind, words] = JOB_WORDS[j.status] ?? ["captured", j.status];
  const tokens = Object.entries(j.tokens ?? {})
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => `${v.toLocaleString()} ${k.replace("tokens_", "").replace("_", " ")}`);
  const meta = [j.task_id, j.model ? j.model : "model not reported", when(j.started_at)];
  if (j.asked_by) meta.push(`asked by ${j.asked_by}`);
  return (
    <div style={css("display:flex;flex-direction:column;gap:6px;padding:14px 0;border-bottom:1px solid var(--line)")}>
      <div style={css("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
        <span style={css("font:400 15px Geist;flex:1;min-width:200px")}>{j.title}</span>
        <Status kind={kind}>{words}</Status>
      </div>
      <span style={css(S.small)}>{meta.join(" · ")}</span>
      <span style={css(S.small)}>
        {tokens.length ? tokens.join(" · ") : "Tokens not reported"} · {j.cost === null || j.cost === undefined ? "cost not reported" : `$${j.cost.toFixed(4)}`}
      </span>
      {j.outputs.length ? <span style={css("font:400 13px Geist;color:var(--ink2)")}>Made: {j.outputs.map((o) => o.title).join(", ")} (drafts in Outputs)</span> : null}
      {j.proposals.length ? (
        <span style={css("font:400 13px Geist;color:var(--ink2)")}>
          Proposed {j.proposals.length} {j.proposals.length === 1 ? "change" : "changes"}, waiting in Catch up: {j.proposals.join(", ")}
        </span>
      ) : null}
      {j.why ? <span style={css("font:400 13px/1.5 Geist;color:oklch(0.5 0.15 28)")}>Why it stopped: {j.why}</span> : null}
    </div>
  );
}

function ProjectTodos({ p }: { p: BrainProjectDetail }) {
  const tasks = useProjectTasks(p.id);
  const add = useAddTask(p.id);
  const [text, setText] = useState("");
  const list = flatTasks(tasks.data);
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:500 15px Geist")}>Your tasks</span>
        <span style={css("font:400 12.5px Geist;color:var(--muted)")}>For people. Tasks stay tasks, not memory.</span>
      </div>
      {tasks.isLoading ? (
        <Loading what="Loading tasks" />
      ) : tasks.error ? (
        <Failure error={tasks.error} retry={() => void tasks.refetch()} />
      ) : (
        <div style={css(LIST)}>
          {list.map((t) => (
            <TaskRow key={t.id} t={t} />
          ))}
          {list.length === 0 ? <div style={css("padding:18px 0;font:400 14px Geist;color:var(--muted)")}>No tasks yet. Pull them from a meeting in Capture, or add one here.</div> : null}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const title = text.trim();
              if (!title) return;
              add.mutate(title, { onSuccess: () => setText("") });
            }}
            style={css("display:flex;gap:8px;padding:14px 0;flex-wrap:wrap")}
          >
            <input
              aria-label="New task"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Add a task"
              style={css("flex:1;min-width:0;border:1px solid var(--line2);border-radius:12px;padding:9px 12px;outline:none;background:var(--bg);color:var(--ink);font:400 14px Geist")}
            />
            <button type="submit" disabled={!text.trim() || add.isPending} style={css(S.soft + ";padding:8px 16px")}>
              Add
            </button>
            {add.error ? (
              <span role="alert" style={css(ERR + ";flex-basis:100%")}>
                {(add.error as Error).message}
              </span>
            ) : null}
          </form>
        </div>
      )}
    </div>
  );
}

function TaskRow({ t }: { t: TaskItem }) {
  const handOff = useHandOff();
  const done = t.status === "done";
  const from = t.evidence[0] || (t.owner === "you" ? "you" : t.owner_label || "unknown");
  return (
    <div style={css("display:flex;flex-direction:column;gap:4px;padding:14px 0;border-bottom:1px solid var(--line)")}>
      <div style={css("display:flex;align-items:center;gap:14px")}>
        <button
          type="button"
          role="checkbox"
          aria-checked={done}
          aria-label={t.task}
          disabled={done || handOff.isPending}
          onClick={() => handOff.mutate({ task: t.id, status: "done" })}
          style={css(
            "width:22px;height:22px;flex:none;border-radius:50%;padding:0;display:flex;align-items:center;justify-content:center;font:500 11px Geist;" +
              (done ? "background:var(--ink);color:var(--bg);border:0" : "border:1.5px solid var(--line2);background:transparent;color:transparent"),
          )}
        >
          ✓
        </button>
        <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:2px")}>
          <span style={css("font:400 15px Geist;" + (done ? "color:var(--muted);text-decoration:line-through" : "color:var(--ink)"))}>{t.task}</span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>
            {t.id} · {t.owner_label || t.owner || "Unassigned"} · {t.due || "no date"} · {t.status_words || t.status} · from {from}
          </span>
        </div>
      </div>
      {handOff.error ? (
        <span role="alert" style={css(ERR + ";padding-left:36px")}>
          {(handOff.error as Error).message}
        </span>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ Files

function FilesView({ p }: { p: BrainProjectDetail }) {
  const navigate = useNavigate();
  const notes = useNotes();
  const linked = (notes.data ?? []).filter((n) => n.projects?.includes(p.id));
  const status = useSourceStatus(linked.map((n) => n.id));
  return (
    <div style={css(SECTION)}>
      <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>Sources linked to this project, with where each one is. Saved isn't the same as searchable.</span>
      {notes.isLoading ? <Loading what="Loading sources" /> : null}
      {notes.error ? <Failure error={notes.error} retry={() => void notes.refetch()} /> : null}
      {status.error ? <Failure error={status.error} retry={() => void status.refetch()} /> : null}
      {!notes.isLoading && linked.length === 0 && p.files.length === 0 ? (
        <Empty title="No sources in this project yet">Capture a meeting, a document or a note into it, and it shows here with where it stands.</Empty>
      ) : (
        <div style={css(LIST)}>
          {linked.map((n) => {
            const s = status.data?.[n.id];
            return (
              <button
                key={n.id}
                type="button"
                onClick={() => navigate(`/capture/${encodeURIComponent(n.id)}`)}
                className="gn-hover"
                style={css("display:flex;align-items:center;gap:16px;padding:15px 0;border:0;border-bottom:1px solid var(--line);background:transparent;width:100%;text-align:left;color:var(--ink);flex-wrap:wrap")}
              >
                <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:3px")}>
                  <span style={css("font:400 16px Geist")}>{n.title || "Untitled capture"}</span>
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>
                    {(n.capture || "note").toString()} · {when(n.updated_at || n.created_at)}
                    {s?.detail ? ` · ${s.detail}` : ""}
                  </span>
                </div>
                {s ? <Status kind={s.status}>{s.label}</Status> : <Status kind="captured">{status.isLoading ? "Checking…" : "Status unknown"}</Status>}
              </button>
            );
          })}
          {p.files.map((f) => {
            const searchable = f.sections > 0;
            const meta = ["Filed in the Brain", f.version ? `v${f.version}` : "", f.file_status || "", f.dated || ""].filter(Boolean).join(" · ");
            return (
              <div key={f.path} style={css("display:flex;align-items:center;gap:16px;padding:15px 0;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
                <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:3px")}>
                  <span style={css("font:400 16px Geist")}>{f.title || f.filename || f.path}</span>
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>{meta}</span>
                </div>
                <Status kind={searchable ? "searchable" : "captured"}>{searchable ? `Searchable · ${f.sections} sections` : "Kept whole as a reference"}</Status>
              </div>
            );
          })}
        </div>
      )}
      <Btn kind="ghostSm" style="align-self:flex-start" onClick={() => navigate(`/capture?project=${encodeURIComponent(p.id)}`)}>
        Capture into this project
      </Btn>
    </div>
  );
}

// ------------------------------------------------------------------ Outputs

function OutputsView({ p, runs, onRuns, onSheet }: { p: BrainProjectDetail; runs: string; onRuns: (runs: string) => void; onSheet: () => void }) {
  const outputs = useOutputs();
  const timeline = useWorkTimeline(p.id);
  const files = (outputs.data?.files ?? []).filter((f) => f.project === p.id);
  const fromFiles = new Set(files.map((f) => f.title || f.name));
  const drafts = (timeline.data ?? []).flatMap((j) => j.outputs.map((o) => ({ ...o, job: j }))).filter((o) => !fromFiles.has(o.title));
  const loading = outputs.isLoading || timeline.isLoading;
  return (
    <div style={css(SECTION)}>
      <span style={css("font:400 15px/1.5 Geist;color:var(--ink2);max-width:680px")}>
        What AI work produced here, grouped by orchestrator and run. Final outputs sit on top, with the trail that led to them. Outputs never change records; to keep something, capture it and review the proposal.
      </span>
      <OrchestratorOutputs projectId={p.id} tab={runs} onTab={onRuns} onSheet={onSheet} />
      {runs === "all" || runs === "other" ? <span style={css("font:500 15px Geist")}>Other outputs</span> : null}
      {outputs.error ? <Failure error={outputs.error} retry={() => void outputs.refetch()} /> : null}
      {timeline.error ? <Failure error={timeline.error} retry={() => void timeline.refetch()} /> : null}
      {runs !== "all" && runs !== "other" ? null : loading ? (
        <Loading what="Loading outputs" />
      ) : (
        <div style={css(LIST)}>
          {files.map((f) => (
            <OutputRow key={f.path} f={f} />
          ))}
          {drafts.map((o) => (
            <div key={o.id} style={css("display:flex;align-items:center;gap:16px;padding:15px 0;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
              <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:3px")}>
                <span style={css("font:400 16px Geist")}>{o.title}</span>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>
                  {o.id} · from job {o.job.task_id}
                  {o.job.model ? ` · ${o.job.model}` : ""} · {when(o.job.finished_at || o.job.started_at)} · keeps the record versions it read
                </span>
              </div>
              <span style={css("padding:3px 10px;border-radius:99px;font:500 12px Geist;background:var(--soft);color:var(--ink2)")}>Draft · not saved to Brain</span>
            </div>
          ))}
          {files.length + drafts.length === 0 ? <div style={css("padding:18px 0;font:400 14px Geist;color:var(--muted)")}>No outputs yet. Ask your AI to draft something for this project in Tasks.</div> : null}
        </div>
      )}
    </div>
  );
}

function OutputRow({ f }: { f: OutputFile }) {
  const [open, setOpen] = useState(false);
  const made = useMadeFrom(open ? f.path : null);
  const by = f.maker || (f.from === "skill" ? "a skill run" : f.from === "chat" ? "a conversation" : "AI");
  return (
    <div style={css("display:flex;flex-direction:column;gap:8px;padding:15px 0;border-bottom:1px solid var(--line)")}>
      <div style={css("display:flex;align-items:center;gap:16px;flex-wrap:wrap")}>
        <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:3px")}>
          <span style={css("font:400 16px Geist")}>{f.title || f.name}</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>
            {f.path} · {by} · {when(f.modified)}
            {f.working ? " · still being written" : ""} · keeps the record versions it read
          </span>
        </div>
        <span style={css("padding:3px 10px;border-radius:99px;font:500 12px Geist;background:var(--soft);color:var(--ink2)")}>Draft · not saved to Brain</span>
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2)")}>
          {open ? "Hide what it was made from" : "Made from"}
        </button>
      </div>
      {open ? (
        made.isLoading ? (
          <Loading />
        ) : made.error ? (
          <Failure error={made.error} retry={() => void made.refetch()} />
        ) : made.data ? (
          <div style={cx("padding:12px 14px;border-radius:14px;background:var(--soft);display:flex;flex-direction:column;gap:6px")}>
            <span style={css("font:400 13.5px/1.5 Geist")}>
              {made.data.how === "skill" && made.data.skill_run
                ? `Skill ${made.data.skill_run.skill}, asked: “${made.data.skill_run.ask}” (${made.data.skill_run.task_id}, ${made.data.skill_run.status})`
                : made.data.how === "export" && made.data.export
                  ? `Exported from ${made.data.export.title}, version ${made.data.export.version}`
                  : made.data.how === "chat" && made.data.chat
                    ? `A conversation in ${made.data.chat.app}: ${made.data.chat.title}`
                    : "Not known: nothing recorded how this file was made."}
            </span>
            {(made.data.given ?? []).map((g) => (
              <div key={g.id} style={css("display:flex;flex-direction:column;gap:2px")}>
                <span style={css("font:500 12px Geist;color:var(--muted)")}>What the run read ({g.id})</span>
                {g.pieces.length === 0 ? <span style={css(S.small)}>Nothing from the Brain.</span> : null}
                {g.pieces.map((piece, i) => (
                  <span key={i} style={css("font:400 13px Geist")}>
                    {pieceText(piece)}
                  </span>
                ))}
              </div>
            ))}
          </div>
        ) : null
      ) : null}
    </div>
  );
}

function pieceText(piece: unknown): string {
  const x = (piece ?? {}) as Record<string, unknown>;
  const title = String(x.title ?? x.id ?? "A piece");
  const version = x.version ?? x.revision;
  return version !== undefined && version !== null ? `${title} · version ${String(version)}` : title;
}

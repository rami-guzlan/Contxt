// A project's workflows on its Tasks tab (Release 1 plan, section 11): saved chains where each
// step is its own AI (Claude Code with the app's tools; Codex and Gemini CLI answer once), each
// with Run and Edit, and the latest run's steps: the CLI and model, what it made, what it used,
// and the owner's yes at a gate, Stop, and Retry on the same CLI when a step failed.

import { useState } from "react";

import { css } from "../css";
import type { CliChoice } from "../hooks/orchestrators";
import { type Workflow, type WorkflowBudget, type WorkflowRun, type WorkflowStep, useProjectWorkflows, useSaveWorkflow, useWorkflowAct, useWorkflowRuns } from "../hooks/workflows";
import { Btn, Chip, Failure, Loading, Modal, S, Status } from "../ui";

export const MAX_STEPS = 10;
const PROVIDER: Record<string, string> = { claude: "Anthropic", codex: "OpenAI", gemini: "Google" };
const KINDS: [NonNullable<WorkflowStep["kind"]>, string][] = [
  ["prompt", "A prompt"],
  ["skill", "A skill"],
  ["agent", "An agent"],
  ["connector", "Your connected tools"],
  ["check", "Wait for your yes"],
];
const RUN_WORDS: Record<string, [string, string]> = {
  running: ["indexing", "Running"],
  waiting: ["review", "Waiting for you"],
  done: ["searchable", "Done"],
  failed: ["failed", "Failed"],
  stopped: ["excluded", "Stopped"],
};
const STEP_WORDS: Record<string, string> = { pending: "Not started", running: "Running", waiting: "Waiting for your yes", done: "Done", failed: "Failed" };

const money = (n: number | null | undefined) => (n == null ? "" : `$${n < 0.01 ? n.toFixed(4) : n.toFixed(2)}`);

function cliOf(clis: CliChoice[], id: string | undefined) {
  return clis.find((c) => c.id === (id || "claude"));
}

function chain(w: Workflow, clis: CliChoice[]) {
  return w.steps.map((s) => (s.kind === "check" ? "Your yes" : [cliOf(clis, s.runner)?.label ?? "Claude Code", s.model].filter(Boolean).join(" · "))).join(" → ");
}

export function ProjectWorkflows({ project, clis, draft, onDraftUsed }: { project: string; clis: CliChoice[]; draft: WorkflowStep | null; onDraftUsed: () => void }) {
  const flows = useProjectWorkflows(project);
  const [editing, setEditing] = useState<Workflow | "new" | null>(null);
  const opening = draft ? "new" : editing;
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px")}>
      <div style={css("display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:220px")}>
          <span style={css("font:500 15px Geist")}>Workflows</span>
          <span style={css(S.muted)}>Steps that hand their work to each other through Outputs, each on its own AI. Anything that sends outside waits for your yes.</span>
        </div>
        <Btn onClick={() => setEditing("new")}>New workflow</Btn>
      </div>
      {flows.isLoading ? <Loading what="Loading workflows" /> : null}
      {flows.error ? <Failure error={flows.error} retry={() => void flows.refetch()} /> : null}
      {flows.data && flows.data.length === 0 ? <span style={css(S.small)}>None yet. Make one here, or save a Work with AI prompt as step 1.</span> : null}
      {(flows.data ?? []).map((w) => (
        <FlowRow key={w.id} w={w} clis={clis} onEdit={() => setEditing(w)} />
      ))}
      {opening ? (
        <Builder
          project={project}
          clis={clis}
          start={opening === "new" ? null : opening}
          first={draft}
          onClose={() => {
            setEditing(null);
            onDraftUsed();
          }}
        />
      ) : null}
    </div>
  );
}

function FlowRow({ w, clis, onEdit }: { w: Workflow; clis: CliChoice[]; onEdit: () => void }) {
  const act = useWorkflowAct();
  const runs = useWorkflowRuns(w.id, w.running);
  const latest = runs.data?.[0];
  const [status, label] = latest ? (RUN_WORDS[latest.status] ?? ["nothing", latest.status]) : ["nothing", "Not run yet"];
  return (
    <div style={css("background:var(--surface);border-radius:18px;box-shadow:var(--shadow);padding:14px 16px;display:flex;flex-direction:column;gap:10px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:200px")}>
          <span style={css("font:500 14px Geist")}>{w.name}</span>
          <span style={css(S.small)}>{chain(w, clis)}</span>
        </div>
        <Status kind={status}>{label}</Status>
        <Btn onClick={onEdit}>Edit</Btn>
        <Btn kind="primarySm" disabled={w.running || act.isPending} onClick={() => act.mutate({ act: "run", id: w.id })}>
          {w.running ? "Running…" : "Run"}
        </Btn>
      </div>
      {act.error ? <Failure error={act.error} /> : null}
      {latest ? <RunSteps run={latest} w={w} clis={clis} /> : null}
    </div>
  );
}

function RunSteps({ run, w, clis }: { run: WorkflowRun; w: Workflow; clis: CliChoice[] }) {
  const act = useWorkflowAct();
  const failed = run.status === "failed" && run.steps[run.step]?.status === "failed";
  const spent = run.steps.reduce((sum, s) => sum + (s.used?.cost ?? 0), 0);
  return (
    <div aria-label={`Latest run of ${w.name}`} style={css("display:flex;flex-direction:column;border-top:1px solid var(--line)")}>
      {run.steps.map((s) => {
        const cli = cliOf(clis, s.runner);
        return (
          <div key={s.index} style={css("display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
            <span style={css("font:500 12px 'Geist Mono';color:var(--muted);width:18px")}>{s.index + 1}</span>
            <span style={css("flex:1;min-width:160px;font:400 13.5px/1.45 Geist")}>
              {s.title || w.steps[s.index]?.text || w.steps[s.index]?.ask || s.kind}
              <span style={css(S.small)}>
                {" · "}
                {s.kind === "check" ? "your check" : [cli?.label ?? "Claude Code", s.model].filter(Boolean).join(" · ")}
                {s.tries && s.tries > 1 ? ` · try ${s.tries}` : ""}
              </span>
              {s.result?.title ? <span style={css(S.small)}> · made “{s.result.title}”</span> : null}
              {s.note && s.status === "failed" ? <span style={css(S.small)}> · {s.note}</span> : null}
            </span>
            {s.used ? (
              <span style={css(S.small)}>
                {s.used.tokens.toLocaleString()} tokens{s.used.cost != null ? ` · ${money(s.used.cost)}` : ""}
              </span>
            ) : null}
            <span style={css(S.small)}>{STEP_WORDS[s.status] ?? s.status}</span>
          </div>
        );
      })}
      {run.note ? <span style={css(S.small + ";padding-top:8px")}>{run.note}</span> : null}
      {spent ? <span style={css(S.small + ";padding-top:4px")}>This run so far: {money(spent)}</span> : null}
      {run.waiting ? (
        <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding-top:10px")}>
          <span style={css("flex:1;min-width:200px;font:400 13.5px/1.45 Geist")}>{run.waiting.ask}</span>
          <Btn disabled={act.isPending} onClick={() => act.mutate({ act: "no", id: run.id })}>
            Stop here
          </Btn>
          <Btn kind="primarySm" disabled={act.isPending} onClick={() => act.mutate({ act: "yes", id: run.id })}>
            Yes, go on
          </Btn>
        </div>
      ) : null}
      {failed ? (
        <div style={css("display:flex;gap:8px;align-items:center;padding-top:10px")}>
          <span style={css("flex:1;font:400 13px Geist;color:var(--ink2)")}>Retry runs step {run.step + 1} again on the same AI; what the steps before made stays.</span>
          <Btn kind="primarySm" disabled={act.isPending} onClick={() => act.mutate({ act: "retry", id: run.id })}>
            Retry step {run.step + 1}
          </Btn>
        </div>
      ) : null}
      {run.status === "running" ? (
        <Btn kind="link" disabled={act.isPending} onClick={() => act.mutate({ act: "stop", id: run.id })}>
          Stop this run
        </Btn>
      ) : null}
      {act.error ? <Failure error={act.error} /> : null}
    </div>
  );
}

const blank = (): WorkflowStep => ({ kind: "prompt", text: "", runner: "claude", model: null, gate: false, budget: {} });

function Builder({ project, clis, start, first, onClose }: { project: string; clis: CliChoice[]; start: Workflow | null; first: WorkflowStep | null; onClose: () => void }) {
  const save = useSaveWorkflow();
  const [name, setName] = useState(start?.name ?? "");
  const [steps, setSteps] = useState<WorkflowStep[]>(start?.steps.map((s) => ({ ...s })) ?? [first ?? blank()]);
  const [budget, setBudget] = useState<WorkflowBudget>(start?.budget ?? {});
  const change = (i: number, patch: Partial<WorkflowStep>) => setSteps((all) => all.map((s, n) => (n === i ? { ...s, ...patch } : s)));

  function submit() {
    save.mutate({ id: start?.id, draft: { name: name.trim(), project, steps, budget } }, { onSuccess: onClose });
  }

  return (
    <Modal title={start ? `Edit ${start.name}` : "New workflow"} eyebrow="WORKFLOW" onClose={onClose} width={720}>
      <div style={css("display:flex;flex-direction:column;gap:14px")}>
        <input aria-label="Workflow name" placeholder="Name it" value={name} onChange={(e) => setName(e.target.value)} style={css(S.input)} />
        {steps.map((s, i) => (
          <StepEditor key={i} i={i} s={s} clis={clis} onChange={(patch) => change(i, patch)} onRemove={steps.length > 1 ? () => setSteps((all) => all.filter((_, n) => n !== i)) : undefined} />
        ))}
        <div style={css("display:flex;gap:10px;align-items:center;flex-wrap:wrap")}>
          <Btn disabled={steps.length >= MAX_STEPS} onClick={() => setSteps((all) => [...all, blank()])}>
            Add a step
          </Btn>
          <span style={css(S.small)}>{steps.length >= MAX_STEPS ? `A workflow has at most ${MAX_STEPS} steps.` : `${steps.length} of at most ${MAX_STEPS} steps`}</span>
          <label style={css("margin-left:auto;display:flex;gap:6px;align-items:center;font:400 12.5px Geist")}>
            Whole run at most $
            <input
              aria-label="Run budget in dollars"
              inputMode="decimal"
              value={budget.cost ?? ""}
              onChange={(e) => setBudget(e.target.value ? { ...budget, cost: Number(e.target.value) } : { ...budget, cost: undefined })}
              style={css(S.input + ";width:80px;padding:6px 8px;font-size:13px")}
            />
          </label>
        </div>
        {save.error ? <Failure error={save.error} /> : null}
        <div style={css("display:flex;justify-content:flex-end;gap:8px")}>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn kind="primarySm" disabled={!name.trim() || save.isPending} onClick={submit}>
            {save.isPending ? "Saving…" : "Save workflow"}
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

function StepEditor({ i, s, clis, onChange, onRemove }: { i: number; s: WorkflowStep; clis: CliChoice[]; onChange: (patch: Partial<WorkflowStep>) => void; onRemove?: () => void }) {
  const cli = cliOf(clis, s.runner);
  const ai = s.kind !== "check";
  const forced = s.kind === "connector" && !!s.writes;
  const label = cli?.label ?? "Claude Code";
  const field = s.kind === "prompt" ? "text" : "ask";
  return (
    <fieldset aria-label={`Step ${i + 1}`} style={css("border:1px solid var(--line2);border-radius:16px;padding:12px 14px;display:flex;flex-direction:column;gap:10px;margin:0")}>
      <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
        <span style={css("font:500 12px 'Geist Mono';color:var(--muted)")}>STEP {i + 1}</span>
        <select aria-label={`Step ${i + 1} kind`} value={s.kind} onChange={(e) => onChange({ kind: e.target.value as WorkflowStep["kind"], runner: e.target.value === "connector" ? "claude" : s.runner })} style={css(S.input + ";padding:6px 10px;font-size:13px")}>
          {KINDS.map(([id, words]) => (
            <option key={id} value={id}>
              {words}
            </option>
          ))}
        </select>
        {onRemove ? (
          <Btn kind="link" onClick={onRemove}>
            Remove
          </Btn>
        ) : null}
      </div>
      {s.kind === "skill" ? <input aria-label={`Step ${i + 1} skill`} placeholder="The skill it follows" value={s.skill ?? ""} onChange={(e) => onChange({ skill: e.target.value })} style={css(S.input)} /> : null}
      {s.kind === "agent" ? <input aria-label={`Step ${i + 1} agent`} placeholder="The agent profile" value={s.agent ?? ""} onChange={(e) => onChange({ agent: e.target.value })} style={css(S.input)} /> : null}
      <textarea
        aria-label={`Step ${i + 1} ${s.kind === "check" ? "what to look at" : "what it does"}`}
        rows={2}
        placeholder={s.kind === "check" ? "What should you look at before it goes on?" : "What should this step do with what the step before made?"}
        value={(s[field] as string | undefined) ?? ""}
        onChange={(e) => onChange({ [field]: e.target.value })}
        style={css(S.input + ";resize:vertical")}
      />
      {s.kind === "connector" ? (
        <div style={css("display:flex;gap:10px;align-items:center;flex-wrap:wrap")}>
          <input aria-label={`Step ${i + 1} tools`} placeholder="mcp__buffer__create_post, …" value={(s.tools ?? []).join(", ")} onChange={(e) => onChange({ tools: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })} style={css(S.input + ";flex:1;min-width:220px")} />
          <label style={css("display:flex;gap:6px;align-items:center;font:400 13px Geist")}>
            <input type="checkbox" checked={!!s.writes} onChange={(e) => onChange({ writes: e.target.checked, gate: e.target.checked || s.gate })} />
            It sends or changes something outside
          </label>
        </div>
      ) : null}
      {ai ? (
        <div style={css("display:flex;gap:6px;align-items:center;flex-wrap:wrap")}>
          <span style={css(S.small)}>Runs on</span>
          {clis
            .filter((c) => s.kind !== "connector" || c.id === "claude")
            .map((c) => (
              <Chip key={c.id} on={(s.runner || "claude") === c.id} onClick={() => onChange({ runner: c.id as WorkflowStep["runner"], model: null })}>
                {c.label}
              </Chip>
            ))}
          {cli?.models.length ? (
            <select aria-label={`Step ${i + 1} model`} value={s.model ?? ""} onChange={(e) => onChange({ model: e.target.value || null })} style={css(S.input + ";padding:5px 10px;font-size:12.5px")}>
              <option value="">Its usual model</option>
              {cli.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          ) : null}
          <label style={css("margin-left:auto;display:flex;gap:6px;align-items:center;font:400 12.5px Geist")}>
            At most
            <input
              aria-label={`Step ${i + 1} token budget`}
              inputMode="numeric"
              placeholder="tokens"
              value={s.budget?.tokens ?? ""}
              onChange={(e) => onChange({ budget: { ...s.budget, tokens: e.target.value ? Number(e.target.value) : undefined } })}
              style={css(S.input + ";width:90px;padding:5px 8px;font-size:12.5px")}
            />
            tokens
          </label>
        </div>
      ) : null}
      {ai ? (
        <label style={css("display:flex;gap:6px;align-items:center;font:400 13px Geist")}>
          <input type="checkbox" checked={forced || !!s.gate} disabled={forced} onChange={(e) => onChange({ gate: e.target.checked })} />
          Wait for my yes before this step{forced ? " (always, since what it sends cannot be undone)" : ""}
        </label>
      ) : null}
      {ai ? (
        <span style={css(S.small)}>
          {label} gets this step's prompt, the project's context and what the step before made, and sends them to {PROVIDER[s.runner || "claude"] ?? "its provider"}.
          {cli && !cli.one_click ? " It has no tools: it answers once, and the answer is saved to Outputs." : ""}
        </span>
      ) : null}
    </fieldset>
  );
}

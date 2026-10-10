// Knowledge Work's overview leads with governance, then the work: what changed in your Brain
// since you last looked and who changed it (you, an AI, a workflow); what waits for you; how
// healthy the context is (notes to recheck, possible duplicates, skills that may be out of date,
// agents whose pointers broke); then each workflow as a strip of boxes and arrows with your team
// of agents and their heartbeats; and last, small, the recent runs.

import { useState } from "react";
import { Link, useNavigate } from "react-router";

import {
  useBrainActivity,
  useBrainAttention,
  useCatchUp,
  useBrainStatus,
  useLibrary,
  useOutputs,
  useSavedPrompts,
  useSkills,
  useWaitingRuns,
  useWorkAgents,
  useWorkAttention,
  useWorkflows,
  useWorkspace,
} from "../../api/hooks";
import type { BrainEvent, WorkAgent, Workflow, WorkflowRun } from "../../api/types";
import { LatestRuns } from "../../components/SkillWork";
import { Section } from "../../components/ui";
import { FlowCard, workflowUrl } from "../../components/work/Flows";
import { SuggestedSkills } from "../../components/work/SkillExtras";
import { minutes } from "../../lib/catchup";
import { plural, when } from "../../lib/format";
import { OUTPUTS, SKILLS, skillUrl } from "../../lib/links";
import { entryUrl } from "../brain/shared";
import { AgentCard, type Heartbeat } from "./Agents";

const SEEN_KEY = "contxt.knowledge-work.seen";
const WEEK = 7 * 24 * 60 * 60 * 1000;

interface Part {
  title: string;
  question: string;
  text: string;
  to?: string;
  count?: string;
}

/** An agent's heartbeat from the workflows it is a step of: working, waiting for you, paused or
 * idle, and when it runs next. */
export function heartbeat(agent: WorkAgent, workflows: Workflow[], waiting: WorkflowRun[]): Heartbeat {
  const flows = workflows.filter((w) => w.steps.some((s) => s.kind === "agent" && s.agent === agent.name));
  const next = flows
    .filter((w) => w.enabled && w.next_due_at)
    .map((w) => w.next_due_at as string)
    .sort()[0];
  if (agent.status === "archived") return { status: "paused", next: null };
  if (waiting.some((run) => flows.some((f) => f.id === run.workflow_id))) return { status: "waiting", next };
  const busy = ["claimed", "in_progress"].includes(agent.last_run?.status ?? "") || flows.some((f) => f.running);
  return { status: busy ? "working" : "idle", next };
}

/** When you last looked at the overview, kept in this browser; a week ago the first time. */
function readSeen(): string {
  try {
    const saved = window.localStorage.getItem(SEEN_KEY);
    if (saved) return saved;
  } catch {
    // storage blocked: fall back to a week
  }
  return new Date(Date.now() - WEEK).toISOString();
}

function saveSeen(at: string) {
  try {
    window.localStorage.setItem(SEEN_KEY, at);
  } catch {
    // storage blocked: the overview still works, it just forgets
  }
}

export function WorkOverviewPage() {
  const { data: skills } = useSkills();
  const { data: outputs } = useOutputs();
  const { data: library } = useLibrary();
  const { data: agents } = useWorkAgents();
  const { data: workspace } = useWorkspace();
  const { data: prompts } = useSavedPrompts();
  const { data: workflows } = useWorkflows();
  const { data: checks } = useWaitingRuns();
  const navigate = useNavigate();
  const team = (agents ?? []).filter((a) => a.status !== "archived");
  const flows = workflows ?? [];
  const fresh = agents && workflows && prompts && !team.length && !flows.length && !prompts.length;
  const parts: Part[] = [
    {
      title: "Workspace",
      question: "Where you think",
      text: "Your own docs, plans and links, by project, private until you add them to the Brain; and soon the live context your AIs keep current.",
      to: "/work/workspace",
      count: workspace ? plural(workspace.items.length, "item") : undefined,
    },
    {
      title: "Library",
      question: "What is kept whole",
      text: "Guides to follow, references to read whole, influences whose taste to borrow and assets, each with where it came from, kept current.",
      to: "/work/library",
      count: library ? plural(library.filter((item) => item.kind !== "prompt").length, "item") : undefined,
    },
    {
      title: "Prompts",
      question: "Your own words, for later",
      text: "Your prompts kept word for word with their files, to find and reuse; any AI connected to your Brain finds one by its name.",
      to: "/work/prompts",
      count: prompts ? plural(prompts.length, "prompt") : undefined,
    },
    {
      title: "Skills",
      question: "Procedures the Brain routes",
      text: "What your AI follows for a kind of task, with its files; the Brain hands the right one to any AI you connect.",
      to: SKILLS,
      count: skills ? plural(skills.skills.length, "skill") : undefined,
    },
    {
      title: "Agents",
      question: "Roles and their context",
      text: "Roles written like a job description, pointing to the skills, references and context they need.",
      to: "/work/agents",
      count: agents ? plural(agents.length, "agent") : undefined,
    },
    {
      title: "Workflows",
      question: "Context work on a schedule",
      text: "Upkeep, refreshes and checks that keep the Brain current, waiting for your yes before anything that matters.",
      to: "/work/workflows",
      count: workflows ? plural(workflows.length, "workflow") : undefined,
    },
    {
      title: "Outputs",
      question: "What was made",
      text: "Every file your AI made, with what it was made from.",
      to: OUTPUTS,
      count: outputs ? plural(outputs.files.length, "file") : undefined,
    },
  ];
  return (
    <div className="work-tab work-overview">
      {fresh ? <StartHere /> : null}
      <Changes />
      <div className="grid-2 overview-top">
        <Waiting checks={checks ?? []} reviewing={skills?.waiting ?? []} />
        <Health />
      </div>
      <SuggestedSkills onWrite={(ask) => navigate(`${SKILLS}?new=1&ask=${encodeURIComponent(ask)}`)} />
      <div className="grid-2">
        <Section
          title="Flows"
          actions={
            <Link className="small" to="/work/workflows/new">
              New workflow
            </Link>
          }
        >
          {flows.length ? (
            <ul className="flow-list" aria-label="Your workflows">
              {flows.map((workflow) => (
                <li key={workflow.id}>
                  <FlowCard workflow={workflow} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">
              No workflows yet: keep the Brain current on a schedule, with a check before anything matters.{" "}
              <Link to="/work/workflows">Start from a template</Link>.
            </p>
          )}
        </Section>
        <Section
          title="Agents"
          actions={
            <Link className="small" to="/work/agents">
              Every agent
            </Link>
          }
        >
          <ul className="agent-roster compact" aria-label="Your agents">
            {team.slice(0, 6).map((agent) => (
              <AgentCard key={agent.name} agent={agent} heartbeat={heartbeat(agent, flows, checks ?? [])} />
            ))}
            <li className="agent-card agent-new">
              <Link to="/work/agents/new" className="agent-card-name">
                New agent
              </Link>
              <p className="muted small">A job description, not a prompt: say what it does and what it needs.</p>
            </li>
          </ul>
        </Section>
      </div>
      <LatestRuns limit={5} />
      <Section title="What each part is for">
        <ul className="work-parts" aria-label="The parts of Knowledge Work">
          {parts.map((part) => (
            <li key={part.title} className="work-part">
              <p className="work-part-question">{part.question}</p>
              <h2>{part.to ? <Link to={part.to}>{part.title}</Link> : part.title}</h2>
              <p>{part.text}</p>
              {part.count ? <p className="muted small">{part.count}</p> : null}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

const ACTION_WORDS: Record<string, string> = {
  "auto-applied": "added",
  approved: "kept",
  updated: "changed",
  archived: "archived",
  unarchived: "brought back",
  verified: "confirmed",
  marked: "marked",
  restored: "restored",
  reverted: "undone",
};

/** Who it was, in the person's words: you, a workflow, another person, or an AI. */
function who(handle: string | undefined, owner: string | undefined): string {
  const name = String(handle || "");
  if (!name) return "";
  if (owner && name === owner) return "you";
  if (name.startsWith("workflow")) return "a workflow";
  if (name.startsWith("person:")) return name.slice("person:".length);
  return "your AI";
}

/** What happened and who did it: "added by you", "suggested by your AI, kept by you". */
function described(event: BrainEvent, owner: string | undefined): string {
  const word = ACTION_WORDS[event.action] ?? event.action;
  const maker = who(event.proposer || event.by, owner);
  const decider = who(event.by, owner);
  if (event.action === "approved" && maker && decider && maker !== decider) return `suggested by ${maker}, kept by ${decider}`;
  return maker ? `${word} by ${maker}` : word;
}

/** What changed in the Brain since you last looked at this overview, newest first. */
function Changes() {
  const [since, setSince] = useState(readSeen);
  const { data: status } = useBrainStatus();
  const { data: events } = useBrainActivity({ since });
  const owner = typeof status?.principal === "string" ? status.principal : undefined;
  const changed = (events ?? []).filter((e) => e.action !== "rejected");
  return (
    <Section
      title="What changed since you last looked"
      actions={
        changed.length ? (
          <button
            type="button"
            className="link small"
            onClick={() => {
              const now = new Date().toISOString();
              saveSeen(now);
              setSince(now);
            }}
          >
            Mark as seen
          </button>
        ) : undefined
      }
    >
      {changed.length ? (
        <ul className="list" aria-label="What changed">
          {changed.slice(0, 8).map((event, i) => (
            <li key={`${event.at}-${i}`}>
              {event.note ? <Link to={entryUrl(event.note)}>{event.title ?? event.note}</Link> : (event.title ?? "A change")}
              <span className="muted small">
                {" · "}
                {described(event, owner)} · {when(event.at)}
              </span>
            </li>
          ))}
          {changed.length > 8 ? (
            <li>
              <Link className="small" to="/activity?tab=changes">
                {plural(changed.length - 8, "more change")} in Activity
              </Link>
            </li>
          ) : null}
        </ul>
      ) : (
        <p className="muted small">Nothing changed in your Brain since {when(since)}.</p>
      )}
    </Section>
  );
}

/** Workflow checks, suggestions in Catch up and new skills: everything that waits for a yes. */
function Waiting({ checks, reviewing }: { checks: WorkflowRun[]; reviewing: { name: string }[] }) {
  const { data: plan } = useCatchUp();
  const suggestions = plan && !plan.caught_up ? plan : null;
  return (
    <Section title="Waiting for you">
      {checks.length || reviewing.length || suggestions ? (
        <ul className="list" aria-label="Waiting for you">
          {suggestions ? (
            <li>
              <Link to="/catch-up">Catch up</Link>
              <span className="muted small"> · what your AIs suggested, {minutes(suggestions.seconds)}</span>
            </li>
          ) : null}
          {checks.map((run) => (
            <li key={run.id}>
              <Link to={workflowUrl(run.workflow_id, run.id)}>{run.workflow}</Link>
              <span className="muted small">
                {" · "}
                {run.waiting ? run.waiting.ask : "a step waits for a person"} · {when(run.started_at)}
              </span>
            </li>
          ))}
          {reviewing.map((w) => (
            <li key={w.name}>
              <Link to="/review">/{w.name}</Link>
              <span className="muted small"> · a new skill waits in Review</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">Nothing waits for you. Suggestions, checks in your workflows and new skills to approve show here.</p>
      )}
    </Section>
  );
}

/** How healthy the context is: notes to recheck or flagged, possible duplicates, clashes,
 * skills that may be out of date, agents that point to what is gone. */
function Health() {
  const { data: attention } = useBrainAttention();
  const { data: work } = useWorkAttention();
  const stale = work?.stale_skills ?? [];
  const broken = work?.broken_agents ?? [];
  const recheck = attention?.recheck ?? [];
  const flagged = attention?.flagged ?? [];
  const twins = attention?.twins ?? [];
  const clashes = attention?.clashes ?? [];
  const nothing = !stale.length && !broken.length && !recheck.length && !flagged.length && !twins.length && !clashes.length;
  return (
    <Section title="Context health">
      {nothing ? (
        <p className="muted small">Healthy: nothing to recheck, no duplicates, no clashes, and every skill and agent points to what is there.</p>
      ) : (
        <ul className="list" aria-label="Context health">
          {recheck.length ? (
            <li>
              <Link to="/catch-up">{plural(recheck.length, "note")} to recheck</Link>
              <span className="muted small"> · {recheck.slice(0, 3).map((n) => n.title).join(", ")}</span>
            </li>
          ) : null}
          {flagged.length ? (
            <li>
              <Link to="/brain/entries">{plural(flagged.length, "note")} flagged</Link>
              <span className="muted small"> · {flagged.slice(0, 3).map((n) => n.title).join(", ")}</span>
            </li>
          ) : null}
          {clashes.length ? (
            <li>
              <Link to="/catch-up">{plural(clashes.length, "suggestion")} clash with what the Brain holds</Link>
            </li>
          ) : null}
          {twins.length ? (
            <li>
              <Link to="/brain/agent">{plural(twins.length, "pair")} of notes may say the same thing</Link>
            </li>
          ) : null}
          {stale.map((skill) => (
            <li key={skill.name}>
              <Link to={skillUrl(skill.name)}>/{skill.name}</Link>
              <span className="muted small">
                {" · "}may be out of date: {skill.changed.map((c) => c.title).join(", ")} changed since its last edit
              </span>
            </li>
          ))}
          {broken.map((agent) => (
            <li key={agent.name}>
              <Link to={`/work/agents/${encodeURIComponent(agent.name)}`}>{agent.name}</Link>
              <span className="muted small"> · points to what is gone: {agent.broken.join(", ")}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** The way in for an empty Knowledge Work. */
function StartHere() {
  const steps = [
    { title: "Keep a guide or a reference whole", text: "Add it to the Library, from a page, a repository or a file, with how often to refresh it.", to: "/work/library" },
    { title: "Write a procedure down as a skill", text: "What you ask again and again, as a procedure the Brain hands to any AI.", to: `${SKILLS}?new=1` },
    { title: "Give a role its context", text: "An agent: a job description that points to the skills and references it needs.", to: "/work/agents/new" },
    { title: "Keep it current on a schedule", text: "A workflow for upkeep, refreshes and checks, with your yes before anything matters.", to: "/work/workflows/new" },
  ];
  return (
    <Section title="Start here">
      <ol className="start-here" aria-label="Start here">
        {steps.map((step) => (
          <li key={step.title}>
            <Link to={step.to}>{step.title}</Link>
            <span className="muted small"> {step.text}</span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

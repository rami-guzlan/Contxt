// Work's overview, Paperclip-light and drawn like his sketches: your team of agents, each with
// its heartbeat; what waits for you; each workflow as a strip of boxes and arrows; what is worth
// a look (skills to write down, skills gone stale, agents whose pointers broke); and the recent
// runs. New to it, the way in is the ladder from doing to delegating: show it once (Compose),
// write it down (a skill), give it a role (an agent), give it a schedule (a workflow).

import { Link, useNavigate } from "react-router";

import {
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
import type { WorkAgent, Workflow, WorkflowRun } from "../../api/types";
import { LatestRuns } from "../../components/SkillWork";
import { Section } from "../../components/ui";
import { FlowCard, workflowUrl } from "../../components/work/Flows";
import { SuggestedSkills } from "../../components/work/SkillExtras";
import { plural, when } from "../../lib/format";
import { OUTPUTS, SKILLS, skillUrl } from "../../lib/links";
import { AgentCard, type Heartbeat } from "./Agents";

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
  const reviewing = skills?.waiting ?? [];
  const fresh = agents && workflows && prompts && !team.length && !flows.length && !prompts.length;
  const parts: Part[] = [
    {
      title: "Compose",
      question: "How you ask",
      text: "A prompt box with your skills, agents, docs and library to pick from. See the whole prompt, improve it and save it.",
      to: "/work/compose",
      count: prompts ? plural(prompts.length, "saved prompt") : undefined,
    },
    {
      title: "Workspace",
      question: "Where you think",
      text: "Your own docs, plans and links, by project. Private until you share them; your AI drafts from them when you ask.",
      to: "/work/workspace",
      count: workspace ? plural(workspace.items.length, "item") : undefined,
    },
    {
      title: "Skills",
      question: "How it makes things",
      text: "Procedures your AI follows, with their files. Run one here, or ask for it in any AI you connect.",
      to: SKILLS,
      count: skills ? plural(skills.skills.length, "skill") : undefined,
    },
    {
      title: "Agents",
      question: "Who does the work",
      text: "Roles written like a job description, pointing to the skills, references and context they need.",
      to: "/work/agents",
      count: agents ? plural(agents.length, "agent") : undefined,
    },
    {
      title: "Workflows",
      question: "When it runs",
      text: "Steps that run on a schedule, with a button or from any AI, and wait for your yes before anything that matters.",
      to: "/work/workflows",
      count: workflows ? plural(workflows.length, "workflow") : undefined,
    },
    {
      title: "Library",
      question: "What good looks like",
      text: "Guides to follow, references to read whole, and influences whose taste to borrow, kept current.",
      to: "/work/library",
      count: library ? plural(library.length, "item") : undefined,
    },
    {
      title: "Outputs",
      question: "What it made",
      text: "Every file your AI made, with what it was made from.",
      to: OUTPUTS,
      count: outputs ? plural(outputs.files.length, "file") : undefined,
    },
  ];
  return (
    <div className="work-tab work-overview">
      <p className="work-ladder">
        <strong>Show it</strong> once in Compose, <strong>write it down</strong> as a skill, <strong>hand it off</strong> to an agent with a
        schedule. Each part reads from your Brain, so the work stays current.
      </p>
      {fresh ? <StartHere /> : null}
      <div className="grid-2 overview-top">
        <Section
          title="Your team"
          actions={
            <Link className="small" to="/work/agents">
              Every agent
            </Link>
          }
        >
          <ul className="agent-roster compact" aria-label="Your team">
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
        <Section title="Waiting for you">
          {checks?.length || reviewing.length ? (
            <ul className="list" aria-label="Waiting for you">
              {(checks ?? []).map((run) => (
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
            <p className="muted small">Nothing waits for you. Checks in your workflows and new skills to approve show here.</p>
          )}
        </Section>
      </div>
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
            No workflows yet: give a skill or an agent a schedule, with a check before anything matters.{" "}
            <Link to="/work/workflows">Start from a template</Link>.
          </p>
        )}
      </Section>
      <WorthALook onWrite={(ask) => navigate(`${SKILLS}?new=1&ask=${encodeURIComponent(ask)}`)} />
      <LatestRuns limit={10} />
      <Section title="What each part is for">
        <ul className="work-parts" aria-label="The parts of Work">
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

/** The way in for an empty Work: the ladder, one step at a time. */
function StartHere() {
  const steps = [
    { title: "Ask once in Compose", text: "Write what you want with what goes with it, and see the whole prompt.", to: "/work/compose" },
    { title: "Write it down as a skill", text: "What you ask again and again, as a procedure your AI follows.", to: `${SKILLS}?new=1` },
    { title: "Give it a role", text: "An agent: a job description that points to the skills it uses.", to: "/work/agents/new" },
    { title: "Give it a schedule", text: "A workflow that runs it, with a check before anything matters.", to: "/work/workflows/new" },
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

/** Skills worth writing down, skills gone stale, agents whose pointers broke. */
function WorthALook({ onWrite }: { onWrite: (ask: string) => void }) {
  const { data } = useWorkAttention();
  const stale = data?.stale_skills ?? [];
  const broken = data?.broken_agents ?? [];
  return (
    <>
      <SuggestedSkills onWrite={onWrite} />
      {stale.length || broken.length ? (
        <Section title="Worth a look">
          <ul className="list" aria-label="Worth a look">
            {stale.map((skill) => (
              <li key={skill.name}>
                <Link to={skillUrl(skill.name)}>/{skill.name}</Link>
                <span className="muted small">
                  {" · "}what it loads changed since its last edit: {skill.changed.map((c) => c.title).join(", ")}
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
        </Section>
      ) : null}
    </>
  );
}

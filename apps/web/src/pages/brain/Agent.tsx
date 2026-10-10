// The Brain's knowledge agent: the model it works through (Claude Code on this computer, or a
// local model), its actions with what each did last, the questions it has for you, what it
// suggests as the Brain changes, the map of the Brain it reads (made by code), and the
// procedures it follows. Every change it suggests waits for your yes.

import { Bot } from "lucide-react";
import { Link } from "react-router";

import { useAgent, useAgentMap, useAgentSettings, useAgentSkills, useAgentSuggestions, useLoopRuns, useRunAgentAction } from "../../api/hooks";
import type { AgentAction, AgentModel, AgentOverview, AgentRun, LoopRun } from "../../api/types";
import { useAgentPanel } from "../../components/agent/AgentContext";
import { ActionTurn } from "../../components/agent/AgentPanel";
import { AgentQuestions } from "../../components/agent/AgentQuestions";
import { GoalStatus, Progress, Trend } from "../../components/goals/GoalParts";
import { Markdown } from "../../components/Markdown";
import { ErrorNote, Loading, Section } from "../../components/ui";
import { plural, when } from "../../lib/format";

export function AgentPage() {
  const { data: agent, isLoading, error } = useAgent();
  const panel = useAgentPanel();
  if (isLoading) return <Loading />;
  if (!agent) return <ErrorNote error={error} />;
  return (
    <div className="brain-overview agent-page">
      <section className="agent-intro">
        <p>
          <Bot className="title-icon" aria-hidden="true" /> The knowledge agent keeps your Brain accurate, tidy and aimed at your goals. It reads
          a map of everything in your Brain, made by code a moment ago, and follows a written procedure for each job, so any model can do the
          work without guessing. Nothing it suggests changes your Brain until you say yes.
        </p>
        <div className="row">
          <button type="button" className="primary" onClick={() => panel.openPanel()}>
            Talk to the agent
          </button>
        </div>
      </section>
      <AgentGoals goals={agent.goals ?? []} />
      <Models models={agent.models} value={agent.model} suggestions={agent.suggestions} />
      <Section title="Actions">
        <div className="agent-actions">
          {agent.actions.map((action) => (
            <ActionCard key={action.id} action={action} last={agent.runs.find((r) => r.action === action.id)} />
          ))}
        </div>
      </Section>
      <Section title="Questions for you">
        <AgentQuestions questions={agent.questions} />
      </Section>
      <Suggestions />
      <Section title="What it did">
        <Runs runs={agent.runs} />
        <RunSteps />
      </Section>
      <Section title="How it works">
        <MapView />
        <Procedures />
      </Section>
    </div>
  );
}

/** The goals it keeps, at the top: what it is for, measured by code. */
function AgentGoals({ goals }: { goals: NonNullable<AgentOverview["goals"]> }) {
  return (
    <Section title="Goals it keeps">
      {goals.length ? (
        <ul className="goal-rows">
          {goals.map((g) => (
            <li key={g.id} className="row wrap goal-row">
              <Link to={`/settings?tab=alignment&goal=${encodeURIComponent(g.id)}`}>{g.title}</Link>
              <Progress goal={g} />
              <GoalStatus goal={g} />
              <Trend values={g.trend} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">
          It can keep the Brain itself healthy with four goals, measured by code. <Link to="/settings?tab=alignment">Turn them on in Settings &gt; Alignment</Link>.
        </p>
      )}
    </Section>
  );
}

function Models({ models, value, suggestions }: { models: AgentModel[]; value: string; suggestions: boolean }) {
  const settings = useAgentSettings();
  const local = models.filter((m) => m.kind === "local");
  const choice = (m: AgentModel, detail: string) => (
    <label key={m.id} className={m.available ? "agent-model" : "agent-model unavailable"}>
      <input
        type="radio"
        name="agent-model"
        value={m.id}
        checked={m.id === value}
        disabled={!m.available || settings.isPending}
        onChange={() => settings.mutate({ model: m.id })}
      />
      <span>
        <strong>{m.label.replace(/ \(local\)$/, "")}</strong>
        <span className="muted small"> {detail}</span>
      </span>
    </label>
  );
  return (
    <Section title="The model it works through">
      <fieldset className="agent-models">
        <legend className="sr-only">Model</legend>
        {models.filter((m) => m.kind !== "local").map((m) => choice(m, m.detail))}
        {local.length ? (
          <>
            <p className="agent-models-group small">
              On this computer, through Ollama: free and private, but small, so they read a shorter map and are less careful. Good for a quick
              first pass.
            </p>
            {local.map((m) => choice(m, m.detail.replace(/^On this computer through Ollama, ?/, "")))}
          </>
        ) : null}
        {!local.length ? (
          <p className="muted small">
            Run a small model on this computer to save tokens: install Ollama, pull a model (for example <code>ollama pull qwen3:1.7b</code>), and
            it shows here.
          </p>
        ) : null}
      </fieldset>
      <label className="check">
        <input type="checkbox" checked={suggestions} disabled={settings.isPending} onChange={(event) => settings.mutate({ suggestions: event.target.checked })} />
        Suggest what to do as the Brain changes (bottom right of every page)
      </label>
      <ErrorNote error={settings.error} />
    </Section>
  );
}

function ActionCard({ action, last }: { action: AgentAction; last?: AgentRun }) {
  const run = useRunAgentAction();
  return (
    <article className="agent-action" aria-label={action.label}>
      <h3>{action.label}</h3>
      <p className="muted small">{action.blurb}</p>
      {action.serves ? (
        <p className="small">
          <Link to={`/settings?tab=alignment&goal=${encodeURIComponent(action.serves.id)}`}>Why I'm doing this</Link>: {action.serves.title} (
          {action.serves.words})
        </p>
      ) : null}
      {last ? (
        <p className="small">
          Last {when(last.at)}: {last.summary}
        </p>
      ) : null}
      <div className="row">
        <button type="button" className="primary" disabled={run.isPending} onClick={() => run.mutate({ action: action.id })}>
          Run it
        </button>
      </div>
      <ErrorNote error={run.error} />
      {run.data ? <ActionTurn key={run.data.id} jobId={run.data.id} action={action} /> : null}
    </article>
  );
}

function Suggestions() {
  const { data: suggestions } = useAgentSuggestions();
  const panel = useAgentPanel();
  if (!suggestions?.length) return null;
  return (
    <Section title="It suggests">
      <ul className="list agent-suggestions">
        {suggestions.map((s) => (
          <li key={s.key}>
            <span>{s.title}</span> <span className="muted small">{s.detail}</span>{" "}
            {s.action ? (
              <button type="button" className="link small" onClick={() => panel.openPanel({ action: s.action ?? undefined })}>
                Run it
              </button>
            ) : s.link ? (
              <Link className="small" to={s.link}>
                Open
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Runs({ runs }: { runs: AgentRun[] }) {
  if (!runs.length) return <p className="muted small">Nothing yet: run an action, or let it suggest one.</p>;
  return (
    <ol className="agent-runs">
      {runs.map((r) => (
        <li key={r.id}>
          <span className="small">
            <strong>{r.label}</strong> · {when(r.at)} · <span className="muted">{r.model}</span>
          </span>
          <span className="small">
            {r.summary}
            {r.proposed ? (
              <>
                {" "}
                <Link to="/catch-up">{plural(r.proposed, "suggestion")} in Catch up</Link>
              </>
            ) : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** How each run went, step by step (BL 17.8): the tool it called, what came back, what code
 * refused, and how it ended. */
function RunSteps() {
  const { data: runs } = useLoopRuns();
  if (!runs?.length) return null;
  return (
    <details className="sent-text">
      <summary>How each run went, step by step</summary>
      <ol className="agent-runs">
        {runs.map((run: LoopRun) => (
          <li key={run.id}>
            <span className="small">
              <strong>{run.action}</strong> · {when(run.at)} · {run.ending === "hand-up" ? `handed up: ${run.record.why ?? ""}` : "findings"}
              {run.record.model ? <span className="muted"> · {run.record.model}</span> : null}
            </span>
            <ol className="small">
              {(run.record.steps ?? []).map((step, index) => (
                <li key={index}>
                  {step.tool ? (
                    <>
                      Looked with <code>{step.tool}</code>
                      {step.result ? <span className="muted">: {step.result.slice(0, 160)}</span> : null}
                    </>
                  ) : (
                    <>Answered</>
                  )}
                  {step.problems.length ? <span className="warning"> Refused: {step.problems.join("; ")}</span> : null}
                </li>
              ))}
            </ol>
          </li>
        ))}
      </ol>
    </details>
  );
}

function MapView() {
  const { data: map, isLoading } = useAgentMap();
  return (
    <details className="sent-text">
      <summary>What it reads: the map of your Brain, made by code</summary>
      {isLoading ? <Loading /> : map ? <pre className="agent-map">{map.text}</pre> : null}
    </details>
  );
}

function Procedures() {
  const { data: skills } = useAgentSkills();
  return (
    <details className="sent-text">
      <summary>What it follows: a procedure for each job</summary>
      {(skills ?? []).map((s) => (
        <details key={s.name} className="agent-procedure">
          <summary>
            /{s.name}
            {s.own ? <span className="muted small"> (your own version)</span> : null}
          </summary>
          <p className="muted small">{s.description}</p>
          <div className="document compact">
            <Markdown text={s.text} />
          </div>
        </details>
      ))}
      <p className="muted small">
        They ship with Contxt. To change one, write a skill of the same name in your Brain: the agent then follows yours.
      </p>
    </details>
  );
}

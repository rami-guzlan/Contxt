// Settings > Alignment (goals plan 6.6 and 6.7): what your Brain is for, the goals that serve
// it, and the rules every AI follows. Three views: Goals (the purpose, your goals as links,
// agent goals with their measures), Rules (the startup context with its layers and budgets,
// the must-holds by domain, and your "how" and "never") and How these differ. An agent goal
// opens in a drawer (?goal=<id>).

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { get } from "../../api/client";
import { useChangeGoal, useGoal, useGoalSettings, useGoalSettingsSave, useGoalStarters, useLadder, useRunGoalChecks } from "../../api/hooks";
import type { GoalView } from "../../api/types";
import { GoalStatus, Progress, Trend, goalUrl } from "../../components/goals/GoalParts";
import { CopyBlock, ErrorNote, Loading, Section, Tabs } from "../../components/ui";
import { plural, when } from "../../lib/format";

const VIEWS = [
  { id: "goals", label: "Goals" },
  { id: "rules", label: "Rules" },
  { id: "differ", label: "How these differ" },
] as const;
type View = (typeof VIEWS)[number]["id"];

const KEEPERS: Record<string, string> = { "knowledge-agent": "Knowledge agent" };

/** The tab. `purpose` is the purpose interview and its text (Settings keeps that piece). */
export function Alignment({ purpose }: { purpose: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const view = (VIEWS.find((v) => v.id === params.get("view"))?.id ?? "goals") as View;
  const open = params.get("goal");
  const go = (next: Record<string, string | null>) => {
    const out = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v === null) out.delete(k);
      else out.set(k, v);
    }
    setParams(out, { replace: true });
  };
  return (
    <>
      <p className="lede">What your Brain is for, the goals that serve it, and the rules every AI follows.</p>
      <Tabs tabs={VIEWS} active={view} onChange={(next) => go({ view: next === "goals" ? null : next })} />
      {view === "goals" ? <GoalsView purpose={purpose} onOpen={(id) => go({ goal: id })} /> : null}
      {view === "rules" ? <RulesView /> : null}
      {view === "differ" ? <Differ /> : null}
      {open ? <AgentGoalDrawer id={open} onClose={() => go({ goal: null })} /> : null}
    </>
  );
}

function GoalsView({ purpose, onOpen }: { purpose: ReactNode; onOpen: (id: string) => void }) {
  const { data: ladder, isLoading, error } = useLadder();
  const starters = useGoalStarters();
  const check = useRunGoalChecks();
  const { data: settings } = useGoalSettings();
  const saveSettings = useGoalSettingsSave();
  if (!ladder) {
    // The purpose is the interview's own; it shows whatever the ladder is doing.
    return (
      <Section title="The Brain's purpose (your high-level Brain goal)">
        {purpose}
        {isLoading ? <Loading /> : <ErrorNote error={error} />}
      </Section>
    );
  }
  const keepers = new Map<string, GoalView[]>();
  for (const goal of ladder.agents) keepers.set(goal.kept_by ?? "", [...(keepers.get(goal.kept_by ?? "") ?? []), goal]);
  const off = ladder.starters.filter((s) => !s.on);
  return (
    <>
      <Section title="The Brain's purpose (your high-level Brain goal)" actions={<span className="muted small">Never ends</span>}>
        {purpose}
        {ladder.purpose.signals.length ? (
          <p className="small">
            <strong>How you'll know it's working:</strong> {ladder.purpose.signals.join(" | ")}
          </p>
        ) : null}
      </Section>
      <Section title="Your goals" actions={<Link to="/projects">Open</Link>}>
        {ladder.yours.length ? (
          <p className="small">
            {ladder.yours.map((g, i) => (
              <span key={g.id}>
                {i ? " | " : ""}
                <Link to={goalUrl(g.id)}>{g.title}</Link> ({g.words})
              </span>
            ))}
          </p>
        ) : (
          <p className="muted small">No goals yet: they are optional. They live in Goals and Projects.</p>
        )}
      </Section>
      <Section
        title="Agent goals"
        actions={
          ladder.agents.length ? (
            <button type="button" className="link small" disabled={check.isPending} onClick={() => check.mutate()}>
              {check.isPending ? "Checking..." : "Check now"}
            </button>
          ) : null
        }
      >
        {off.length ? (
          <div className="nudge small">
            <span>
              The knowledge agent can keep the Brain itself healthy with {plural(off.length, "goal")}: {off.map((s) => s.title).join("; ")}.
            </span>
            <button type="button" className="primary" disabled={starters.isPending} onClick={() => starters.mutate()}>
              Turn them on
            </button>
            <ErrorNote error={starters.error} />
          </div>
        ) : null}
        {[...keepers.entries()].map(([keeper, goals]) => (
          <div key={keeper} className="agent-goals">
            <h3 className="small">
              {KEEPERS[keeper] ?? keeper}
              {keeper === "knowledge-agent" ? <span className="muted"> keeps the Brain healthy; serves the purpose</span> : null}
            </h3>
            <ul className="goal-rows">
              {goals.map((g) => (
                <li key={g.id} className="row wrap goal-row">
                  <button type="button" className="link" onClick={() => onOpen(g.id)}>
                    {g.title}
                  </button>
                  <Progress goal={g} />
                  <GoalStatus goal={g} />
                  <Trend values={g.trend} />
                  <span className="muted small">{g.cadence}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <ErrorNote error={check.error} />
      </Section>
      <Section title="Weekly review">
        <label className="small">
          <input
            type="checkbox"
            checked={settings?.weekly_review ?? false}
            disabled={saveSettings.isPending}
            onChange={(event) => saveSettings.mutate({ weekly_review: event.target.checked })}
          />{" "}
          A short Friday card on Home: your goals, agent goals that moved, the week's notes, up to three next steps. Built by code.
        </label>
      </Section>
    </>
  );
}

function AgentGoalDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: goal, isLoading, error } = useGoal(id);
  const change = useChangeGoal(id);
  return (
    <aside className="card side-panel drawer" aria-label="Agent goal">
      <header className="row">
        <h2>{goal?.title ?? "Goal"}</h2>
        <button type="button" className="link small" onClick={onClose}>
          Close
        </button>
      </header>
      {isLoading ? <Loading /> : null}
      {goal ? (
        <div className="stack small">
          <div className="row">
            {goal.lifecycle === "active" ? (
              <button type="button" className="link small" onClick={() => change.mutate({ status: "paused" })}>
                Pause
              </button>
            ) : (
              <button type="button" className="link small" onClick={() => change.mutate({ status: "active" })}>
                Resume
              </button>
            )}
            <button type="button" className="link small" onClick={() => change.mutate({ status: "retired" })}>
              Retire
            </button>
          </div>
          <p>
            Owner: {KEEPERS[goal.kept_by ?? ""] ?? goal.kept_by ?? "You"} | Serves: {goal.serves.includes("you-goals") ? "the Brain's purpose" : goal.serves.join(", ") || "nothing named"} | Checked {goal.cadence}
          </p>
          {goal.why ? <p>Why: “{goal.why}”</p> : null}
          <p>
            <strong>Measure</strong> {goal.measure_words}. Now {goal.now ?? "no value yet"}. <GoalStatus goal={goal} /> <Trend values={goal.trend} />
          </p>
          <p className="muted">How it's worked on: its agent opens a task when it slips (one at a time), once tasks arrive. Until then a slip waits in Catch up.</p>
          <h3>History</h3>
          <ul>
            {goal.checks.slice(0, 8).map((c, i) => (
              <li key={i}>
                {when(c.at)}: {c.value ?? "no value"} ({c.status.replace("_", " ")}){c.note ? `. ${c.note}` : ""}
              </li>
            ))}
            {goal.started ? <li>Set {goal.started}.</li> : null}
          </ul>
        </div>
      ) : (
        <ErrorNote error={error} />
      )}
      <ErrorNote error={change.error} />
    </aside>
  );
}

interface Rules {
  kernel: { text: string; tokens: number; budget?: number; layers?: { name: string; tokens: number; budget?: number }[]; over_budget?: string[] };
  must_holds: { domain: string; notes: { id: string; title: string; text: string }[] }[];
  answers: { how?: string; never?: string; leave_out?: string };
}

function RulesView() {
  const { data, isLoading, error } = useQuery({ queryKey: ["goals", "rules"], queryFn: () => get<Rules>("/api/goals/rules") });
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  return (
    <>
      <Section title="What every AI is told first">
        <p className="muted small">
          The startup context: {data.kernel.tokens} tokens{data.kernel.budget ? ` of ${data.kernel.budget}` : ""}.
        </p>
        {data.kernel.layers?.length ? (
          <ul className="small">
            {data.kernel.layers.map((layer) => (
              <li key={layer.name}>
                {layer.name}: {layer.tokens} tokens{layer.budget ? ` of ${layer.budget}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
        <details>
          <summary className="small">The text</summary>
          <CopyBlock text={data.kernel.text} prose />
        </details>
      </Section>
      <Section title="Must-holds, by domain">
        {data.must_holds.length ? (
          data.must_holds.map((d) => (
            <div key={d.domain}>
              <h3 className="small">{d.domain}</h3>
              <ul className="small">
                {d.notes.map((n) => (
                  <li key={n.id}>{n.text}</li>
                ))}
              </ul>
            </div>
          ))
        ) : (
          <p className="muted small">No must-holds yet.</p>
        )}
      </Section>
      <Section title="How your AIs should work, and what they never do">
        {data.answers.how ? <p className="small pre">{data.answers.how}</p> : null}
        {data.answers.never ? <p className="small pre">Never: {data.answers.never}</p> : null}
        {data.answers.leave_out ? <p className="small pre">Leave out: {data.answers.leave_out}</p> : null}
        {!data.answers.how && !data.answers.never ? <p className="muted small">Your purpose interview has no answers for these yet.</p> : null}
      </Section>
    </>
  );
}

const DIFFER: [string, string][] = [
  ["The purpose", "Why your Brain exists. It never ends and has no target. A few signals show whether it is working, such as fewer corrections."],
  ["Your goals", "Optional: what you want to achieve beyond a single project. Each has a page where you plan it and check in. Your AIs help, but the call on how it is going stays yours."],
  ["Agent goals", "What your agents keep true. The knowledge agent's keep the Brain itself healthy. Code measures them, and a slip waits for you in Catch up."],
  ["Projects", "Bounded pieces of work, done by a date. Each has an objective, a sentence or two on the output it is chasing, which every agent working in it reads first."],
  ["Tasks", "Not goals. They are the work."],
  ["Rules", "Not goals either. A rule says how work must be done and reaches every brief where its topic comes up. A goal says what outcome you are after."],
];

function Differ() {
  return (
    <Section title="How these differ">
      <dl className="differ">
        {DIFFER.map(([term, text]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

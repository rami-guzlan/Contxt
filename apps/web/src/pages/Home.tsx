// Home: a calm cockpit. One sentence and one button (catch up, or all caught up) beside a health
// ring; what the Brain is for; the next few steps until they are done; three pictures (what your
// AIs used, what came in by source, the projects in motion); your AI apps with their last
// request; a box to ask what your Brain would hand over; see the difference; and ways to bring
// things in, including moving in what your other AIs already know. A new Brain opens the first
// run instead.

import { ArrowRight, Check, MoveRight, Sparkles } from "lucide-react";
import { Link, Navigate } from "react-router";

import { useAiApps, useBrainProjects, useCatchUp, useGoals, useHome, useModels, useNotes, useOnboarding, useWeekly } from "../api/hooks";
import type { BrainHealth, CatchUpPlan, Goals } from "../api/types";
import { BringIn } from "../components/BringIn";
import { ContextPreview } from "../components/ContextPreview";
import { SeeTheDifference } from "../components/Difference";
import { FirstVisitTip } from "../components/Tips";
import { ErrorNote, Loading, Section } from "../components/ui";
import { onDay, plural, when } from "../lib/format";
import { minutes, queueOf } from "../lib/catchup";

export function HomePage() {
  const { data: home, isLoading, error } = useHome();
  const { data: plan } = useCatchUp();
  const { data: goals } = useGoals();
  const { data: setup } = useOnboarding();
  if (isLoading) return <Loading />;
  if (!home) return <ErrorNote error={error} />;
  // A new Brain starts with the first run; it can be put aside, and comes back from Settings.
  const fresh = !!setup && setup.brain.available && setup.brain.own_entries < 5 && !setup.brain.projects;
  if (fresh && !setup?.completed_at && !setup?.dismissed_at && goals && !goals.exists) return <Navigate to="/welcome" replace />;
  return (
    <div className="page home">
      <FirstVisitTip id="home">
        Home tells you how your Brain is doing and what, if anything, needs you. When it says catch up, it is usually a few minutes.
      </FirstVisitTip>
      <p className="eyebrow">{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p>
      <h1>{home.workspace.name}</h1>
      {plan ? <Hero plan={plan} /> : null}
      {goals ? <GoalsLine goals={goals} /> : null}
      <NextSteps goals={goals} />
      <div className="cards-3">
        <UsedCard />
        {plan ? <CameInCard plan={plan} /> : null}
        <ProjectsCard />
      </div>
      <Apps />
      <Section title="Ask your Brain" tour="home-preview">
        <p className="muted small">Ask the way you would ask any AI, and see exactly what your Brain would hand it, and why. Nothing is recorded.</p>
        <ContextPreview />
      </Section>
      <Section title="See the difference">
        <SeeTheDifference suggestions={suggestionsFrom(goals)} />
      </Section>
      <div className="grid-2">
        <BringIn />
        <section className="bring-in move-in-card" aria-label="Move in">
          <h2>Move in what your AIs know</h2>
          <p className="muted">
            ChatGPT, Claude and Cursor already remember things about you, and your instruction files hold more. Bring them in once; you choose what
            stays.
          </p>
          <Link className="button" to="/move-in">
            <MoveRight className="button-icon" aria-hidden="true" />
            Move in
          </Link>
        </section>
      </div>
    </div>
  );
}

/** Requests to try both ways, made from the goals and the projects. */
function suggestionsFrom(goals: Goals | undefined): string[] {
  const out = ["What do you know about me and my goals?"];
  for (const project of (goals?.projects ?? []).slice(0, 2)) out.push(`Draft a short update on ${project}`);
  return out;
}

function Hero({ plan }: { plan: CatchUpPlan }) {
  const waiting = queueOf(plan).length;
  const health = plan.health;
  return (
    <section className={`hero${plan.caught_up ? " calm" : ""}`} aria-label="How your Brain is doing">
      <HealthRing health={health} />
      <div className="hero-text">
        {plan.caught_up ? (
          <p className="hero-line">
            <Check className="title-icon" aria-hidden="true" /> All caught up.
          </p>
        ) : (
          <p className="hero-line">
            {plural(waiting, "thing")} for you, {minutes(plan.seconds)}.
          </p>
        )}
        {plan.recap_first && plan.away_days ? (
          <p className="muted">You were away {plural(plan.away_days, "day")}. Catch up starts with what happened.</p>
        ) : plan.counts.handled ? (
          <p className="muted">
            {plural(plan.counts.handled, "thing")} went in on its own since {onDay(plan.since)}; each can be taken back.
          </p>
        ) : null}
        {health.unsaved.length ? (
          <p className="warning small">
            {plural(health.unsaved.length, "change")} live but not saved to your Brain's history (a save failed). The next change tries again.
          </p>
        ) : null}
        <div className="row">
          {plan.caught_up ? (
            <Link className="button" to="/catch-up">
              What went in
            </Link>
          ) : (
            <Link className="button primary" to="/catch-up">
              Catch up, {minutes(plan.seconds)}
              <ArrowRight className="button-icon" aria-hidden="true" />
            </Link>
          )}
        </div>
        {health.factors.length ? (
          <ul className="factors">
            {health.factors.map((factor) => (
              <li key={factor.key}>
                <span className="factor-name">{factor.label}</span> <span className="muted small">{factor.detail}</span>
                {factor.fix ? (
                  <Link className="small" to={factor.fix.to}>
                    {" "}
                    {factor.fix.label}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

export function HealthRing({ health, size = 96 }: { health: BrainHealth; size?: number }) {
  const r = 40;
  const circumference = 2 * Math.PI * r;
  const score = health.score ?? 0;
  const label = health.score === null ? "New" : String(health.score);
  return (
    <figure
      className={`health-ring ring-${health.label}`}
      aria-label={health.score === null ? "A new Brain: too new to score" : `Brain health ${health.score} of 100, ${health.label}`}
    >
      <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r={r} className="ring-track" />
        <circle cx="50" cy="50" r={r} className="ring-value" strokeDasharray={`${(circumference * score) / 100} ${circumference}`} transform="rotate(-90 50 50)" />
        <text x="50" y="56" textAnchor="middle" className="ring-text">
          {label}
        </text>
      </svg>
      <figcaption className="small muted">Brain health</figcaption>
    </figure>
  );
}

function GoalsLine({ goals }: { goals: Goals }) {
  if (!goals.exists) {
    return (
      <p className="goals-line">
        <Sparkles className="button-icon" aria-hidden="true" /> <Link to="/settings?tab=goals">Say what your Brain is for</Link>
        <span className="muted"> · everything you bring in is sifted against it</span>
      </p>
    );
  }
  return (
    <p className="goals-line">
      <span className="muted">Helping you:</span> {goals.purpose}{" "}
      <Link className="small" to="/settings?tab=goals">
        Change
      </Link>
    </p>
  );
}

/** What is left to set up, each gone once done. */
function NextSteps({ goals }: { goals: Goals | undefined }) {
  const { data: setup } = useOnboarding();
  const { data: apps } = useAiApps();
  const { data: projects } = useBrainProjects();
  const { data: notes } = useNotes();
  const { data: models } = useModels();
  if (!setup) return null;
  const asked = (apps ?? []).some((a) => a.last_request);
  const first = (projects ?? []).find((p) => p.active);
  const steps = [
    { done: !!goals?.exists, to: "/settings?tab=goals", label: "Say what your Brain is for", why: "Everything you bring in is sifted against it." },
    { done: asked, to: "/settings?tab=apps", label: "Connect an AI app", why: "Claude Code, Claude Desktop, Cursor or Codex: one step each." },
    {
      // nothing downloads on its own: until the person asks, the Brain matches by words
      done: !models || !models.matching.enabled || models.matching.present,
      to: "/settings?tab=computer",
      label: "Match by meaning",
      why: `Download the small model once (about ${models?.matching.about_mb ?? 70} MB). Until then your Brain matches by words.`,
    },
    { done: setup.brain.projects > 0, to: "/projects", label: "Start a project", why: "Your AI then knows where it stands." },
    {
      done: setup.brain.projects === 0 || setup.brain.files > 0,
      to: first ? `/projects/${encodeURIComponent(first.id)}` : "/projects",
      label: "Add its files",
      why: "Your AI quotes the part a request is about.",
    },
    { done: (notes ?? []).length > 0, to: "/capture", label: "Bring in a meeting or a file", why: "Watch it sift against your goals." },
  ].filter((step) => !step.done);
  if (!steps.length) return null;
  return (
    <section className="next-steps" aria-label="Next steps">
      <h2>Next steps</h2>
      <ol className="list">
        {steps.slice(0, 3).map((step) => (
          <li key={step.label}>
            <Link to={step.to}>{step.label}</Link> <span className="muted small">{step.why}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function UsedCard() {
  const { data: weeks } = useWeekly(8);
  const last = weeks?.[weeks.length - 1];
  const top = Math.max(1, ...(weeks ?? []).map((w) => w.packets));
  return (
    <section className="card picture" aria-label="What your AIs asked">
      <h3>What your AIs asked</h3>
      <p className="stat-big">{last ? last.packets : 0}</p>
      <p className="muted small">{last ? `requests this week, in ${plural(last.conversations, "chat")}` : "requests this week"}</p>
      <div className="bars" role="img" aria-label="Requests per week, last 8 weeks">
        {(weeks ?? []).map((w) => (
          <span key={w.start} className="bar" title={`${w.start}: ${plural(w.packets, "request")}`} style={{ height: `${Math.max(4, (100 * w.packets) / top)}%` }} />
        ))}
      </div>
      <Link className="small" to="/activity">
        What each one got
      </Link>
    </section>
  );
}

const SOURCES: [string, string][] = [
  ["chat", "Your AI's chats"],
  ["files", "Files"],
  ["you", "You"],
  ["ai_work", "AI work"],
  ["moved_in", "Moved in"],
  ["other", "Other"],
];

function CameInCard({ plan }: { plan: CatchUpPlan }) {
  const came = plan.recap.came_in;
  const total = came.total || 0;
  const shown = SOURCES.filter(([key]) => came.by_source[key]);
  return (
    <section className="card picture" aria-label="What came in">
      <h3>What came in</h3>
      <p className="stat-big">{total}</p>
      <p className="muted small">since {onDay(plan.recap.since)}</p>
      {total ? (
        <>
          <div className="split-bar" role="img" aria-label="What came in, by source">
            {shown.map(([key, name]) => (
              <span key={key} className={`seg seg-${key}`} style={{ width: `${(100 * (came.by_source[key] ?? 0)) / total}%` }} title={`${name}: ${came.by_source[key]}`} />
            ))}
          </div>
          <ul className="legend small">
            {shown.map(([key, name]) => (
              <li key={key}>
                <span className={`swatch seg-${key}`} aria-hidden="true" /> {name} {came.by_source[key]}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="muted small">Nothing new came in. What you and your AIs save shows here.</p>
      )}
    </section>
  );
}

function ProjectsCard() {
  const { data: projects } = useBrainProjects();
  const active = (projects ?? []).filter((p) => p.active).slice(0, 4);
  return (
    <section className="card picture" aria-label="Projects in motion">
      <h3>Projects in motion</h3>
      {active.length ? (
        <ul className="project-bars">
          {active.map((p) => {
            const days = p.updated ? (Date.now() - new Date(p.updated).getTime()) / 86_400_000 : 30;
            const fresh = Math.max(0.06, 1 - Math.min(days, 30) / 30);
            return (
              <li key={p.id}>
                <Link to={`/projects/${encodeURIComponent(p.id)}`}>{p.title}</Link>
                <span className="fresh-bar" aria-hidden="true">
                  <span style={{ width: `${100 * fresh}%` }} />
                </span>
                <span className="muted small">{p.updated ? `moved ${when(p.updated)}` : "not moved yet"}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted small">
          No projects yet. <Link to="/projects">Start one</Link> and your AI knows where it stands.
        </p>
      )}
    </section>
  );
}

/** Each AI app on this computer, connected or not, with its last request: calm, no red. */
function Apps() {
  const { data: apps } = useAiApps();
  const shown = (apps ?? []).filter((a) => a.found || a.connected || a.last_request);
  if (!shown.length) return null;
  return (
    <section className="apps-line" aria-label="Your AI apps">
      <ul className="chips">
        {shown.map((app) => (
          <li key={`${app.client}:${app.label}`} className="chip">
            <strong>{app.label}</strong>{" "}
            {app.last_request ? (
              <span className="muted">asked {when(app.last_request.at)}</span>
            ) : app.connected ? (
              <span className="muted">connected, no request yet</span>
            ) : (
              <Link to="/settings?tab=apps">Connect</Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

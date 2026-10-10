// Overview: is the Brain helping? One card per pillar, the Brain's effect, what is ready and what
// waits, the report card's lines, and how far the labels have come.

import { Section, Empty, ErrorNote, Loading } from "../../../components/ui";
import { when } from "../../../lib/format";
import { useTtbOverview } from "./api";
import { Chip, Sparkline, interval, readyWords, shown, type Go } from "./shared";
import type { Overview, Pillar, State } from "./types";

export function OverviewView({ state, go }: { state: State; go: Go }) {
  const { data, isLoading, error } = useTtbOverview();
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  const measured = data.pillars.some((p) => p.measured > 0);
  return (
    <>
      {!measured ? (
        <Empty why="Nothing has been measured yet. Run a check, and this page fills in.">
          <button type="button" className="primary" onClick={() => go("run")}>
            Go to Run
          </button>
        </Empty>
      ) : null}
      <ul className="ttb-pillars">
        {data.pillars.map((p) => (
          <PillarCard key={p.id} pillar={p} go={go} />
        ))}
      </ul>
      <Effect effect={data.effect} />
      <Section title="What is ready">
        <ul className="ttb-ready">
          {data.ready.map((row) => {
            const words = readyWords(row);
            return (
              <li key={`${row.suite}:${row.setup ?? ""}`}>
                <span>{row.suite}</span>
                <Chip tone={words.tone}>{words.text}</Chip>
              </li>
            );
          })}
        </ul>
      </Section>
      <Labels labels={data.labels} />
      <Card card={data.card} go={go} />
      {data.last ? (
        <p className="muted small">
          Last run: {data.last.kind}, {when(data.last.ended)}.{" "}
          <button type="button" className="link" onClick={() => go("history")}>
            See every run
          </button>
        </p>
      ) : null}
      <p className="muted small">{state.source === "lab" ? "Read from the connected Lab." : "Read from the checks on your own Brain."}</p>
    </>
  );
}

function PillarCard({ pillar, go }: { pillar: Pillar; go: Go }) {
  const head = pillar.headline;
  return (
    <li className="ttb-pillar">
      <h3>{pillar.name}</h3>
      {pillar.total === 0 ? (
        <p className="muted small">No bars set for this yet.</p>
      ) : (
        <p className="small">
          <strong>{pillar.met}</strong> of {pillar.total} bars met
          {pillar.confident ? `, ${pillar.confident} with confidence` : ""}
          {pillar.measured < pillar.total ? <span className="muted"> ({pillar.total - pillar.measured} not measured)</span> : null}
        </p>
      )}
      {head ? (
        <>
          <p className="ttb-big" aria-label={`${head.name}: ${shown(head.value, head.bar)}`}>
            {shown(head.value, head.bar)}
          </p>
          <p className="muted small">
            {head.name}
            {head.ci ? `, between ${interval(head.ci, head.bar)}` : ""}
          </p>
          <Sparkline values={pillar.trend} bar={head.bar} label={`${head.name} over runs`} />
        </>
      ) : (
        <p className="muted small">Not measured yet.</p>
      )}
      <button type="button" className="link small" onClick={() => go("gates")}>
        See the bars
      </button>
    </li>
  );
}

function Effect({ effect }: { effect: Overview["effect"] }) {
  return (
    <Section title="What your Brain adds">
      {effect && effect.value !== undefined ? (
        <>
          <p className="ttb-big">{shown(effect.value, { op: ">", value: 1 })}</p>
          <p className="muted small">
            How much better the work is with your Brain than without it
            {effect.ci ? `, between ${interval(effect.ci, { op: ">", value: 1 })}` : ""}
            {effect.n ? `, from ${effect.n} cases` : ""}. Above zero, with confidence, means it helps.
          </p>
        </>
      ) : (
        <p className="muted">
          Not measured yet. It compares the same work done with and without your Brain; the Lab's outcome runs, or See the difference under
          Run, measure it.
        </p>
      )}
    </Section>
  );
}

function Labels({ labels }: { labels: Overview["labels"] }) {
  const total = Number(labels.total ?? 0);
  const done = Number(labels.labeled ?? 0);
  const sitting = labels.sitting;
  if (!total && !sitting) return null;
  return (
    <Section title="Labels">
      {total ? (
        <>
          <progress max={total} value={done} aria-label="Requests labeled" />
          <p className="small">
            {done} of {total} requests labeled
            {labels.held_out ? `, ${labels.held_out} held out` : ""}.
          </p>
        </>
      ) : null}
      {sitting?.state ? (
        <p className="small">
          {sitting.state === "ready"
            ? `A labeling sitting is ready${sitting.minutes ? `, about ${sitting.minutes} minutes` : ""}.`
            : sitting.state === "done"
              ? "Labeling is done for now."
              : `A top-up is waiting${sitting.minutes ? `, about ${sitting.minutes} minutes` : ""}.`}
        </p>
      ) : (
        <p className="small muted">Label more of your requests in Activity to make the scores sharper.</p>
      )}
    </Section>
  );
}

function Card({ card, go }: { card: Overview["card"]; go: Go }) {
  if (!card) {
    return (
      <Section title="Report card">
        <p className="muted">
          What your AI's context costs by day, and how big briefs are. Run the Report card to see it.{" "}
          <button type="button" className="link" onClick={() => go("run")}>
            Go to Run
          </button>
        </p>
      </Section>
    );
  }
  const days = card.by_day ?? [];
  const most = Math.max(0.0001, ...days.map((d) => d.total_usd));
  const types = Object.entries(card.brief_tokens_by_type ?? {});
  return (
    <Section title="Report card">
      <p className="small">
        About <strong>{money(card.per_day_usd)}</strong> a day in the last {card.days ?? days.length} days (an estimate from token counts).
      </p>
      {days.length ? (
        <ol className="ttb-days" aria-label="Cost by day">
          {days.map((d) => (
            <li key={d.day}>
              <span className="ttb-day-bar" style={{ height: `${Math.max(4, (d.total_usd / most) * 48)}px` }} title={`${d.day}: ${money(d.total_usd)}`} />
              <span className="small muted">{d.day.slice(5)}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {types.length ? (
        <table className="table">
          <caption className="sr-only">Median brief size by kind of request</caption>
          <thead>
            <tr>
              <th scope="col">Kind of request</th>
              <th scope="col">Median brief</th>
            </tr>
          </thead>
          <tbody>
            {types.map(([kind, tokens]) => (
              <tr key={kind}>
                <th scope="row">{kind}</th>
                <td>{tokens} tokens</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </Section>
  );
}

function money(value: number | undefined): string {
  if (value === undefined) return "$0";
  return value >= 0.1 ? `$${value.toFixed(2)}` : `$${value.toFixed(4)}`;
}

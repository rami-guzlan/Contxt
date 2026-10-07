// The week in the Brain's supply chain, on Activity, Changes: what came in, what was decided,
// what waits, what went out to your AIs, and the health of what it holds.

import type { ReactNode } from "react";
import { Link } from "react-router";

import { useBrainFlow, useBrainGaps } from "../../api/hooks";
import type { BrainFlow } from "../../api/types";
import { Section } from "../../components/ui";
import { plural, when } from "../../lib/format";
import { unusedLabel } from "./shared";

/** The week in the supply chain: in, decided, waiting, handed out, and the stock's health. */
export function Week() {
  const { data: flow } = useBrainFlow(7);
  const { data: gaps } = useBrainGaps(30);
  if (!flow) return null;
  return (
    <Section title="This week">
      <dl className="flow">
        <Stat label="Came in" value={flow.came_in} to="/activity?tab=changes" />
        <Stat label="Kept" value={flow.approved} to="/activity?tab=changes&action=approved" />
        <Stat label="Waiting" value={flow.waiting} to="/catch-up" note={flow.oldest_waiting ? `oldest ${when(flow.oldest_waiting)}` : undefined} />
        <Stat label="Conversations served" value={flow.delivery.conversations ?? 0} to="/activity" />
        <Stat label="AI work served" value={flow.delivery.work_runs ?? 0} />
        <Stat label="Notes handed out" value={flow.delivery.entries ?? 0} to="/brain/entries?view=most" />
        <Stat label="Found nothing" value={flow.delivery.empty ?? 0} to="/brain/questions" attention={!!flow.delivery.empty} />
      </dl>
      <Stock flow={flow} gaps={gaps?.length ?? 0} />
    </Section>
  );
}

function Stat({ label: text, value, to, note, attention }: { label: string; value: number; to?: string; note?: string; attention?: boolean }) {
  const body = (
    <>
      <dt>{text}</dt>
      <dd>
        {value.toLocaleString()}
        {note ? <span className="muted small"> {note}</span> : null}
      </dd>
    </>
  );
  return <div className={attention ? "stat attention" : "stat"}>{to ? <Link to={to}>{body}</Link> : body}</div>;
}

function Stock({ flow, gaps }: { flow: BrainFlow; gaps: number }) {
  const { stock } = flow;
  const parts = [
    stock.due ? <Link key="due" to="/brain/entries?view=due">{plural(stock.due, "note")} due for a check</Link> : null,
    stock.disputed ? <Link key="disputed" to="/brain/entries?view=due">{stock.disputed} disputed</Link> : null,
    stock.unused_60_days ? (
      <Link key="unused" to="/brain/entries?view=unused">
        {stock.unused_60_days} {unusedLabel(flow.usage_since)}
      </Link>
    ) : null,
    gaps ? <Link key="gaps" to="/brain/questions">{plural(gaps, "question")} it couldn't answer in 30 days</Link> : null,
  ].filter(Boolean);
  return (
    <p className="muted small">
      {plural(stock.live, "live note")}; the ones in every conversation cost {stock.standing_tokens.toLocaleString()}{" "}
      tokens each time.
      {parts.length ? <> {parts.reduce<ReactNode[]>((all, part, i) => (i ? [...all, " · ", part] : [part]), [])}.</> : null}
    </p>
  );
}

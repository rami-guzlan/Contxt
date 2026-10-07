// What waits for the person, and the week in the supply chain: Home's view of the Brain.

import type { ReactNode } from "react";
import { Link } from "react-router";

import { useBrainFlow, useBrainGaps } from "../../api/hooks";
import type { BrainAttention, BrainFlow } from "../../api/types";
import { Empty, Section } from "../../components/ui";
import { plural, when } from "../../lib/format";
import { BrainChecks } from "./decided";
import { unusedLabel } from "./shared";

/** What waits for the person: proposals to review, and what in the Brain wants a look. */
export function Waiting({ waiting, attention }: { waiting: number; attention: BrainAttention | undefined }) {
  const checks = attention ? attention.clashes.length + attention.twins.length + attention.flagged.length + attention.recheck.length : 0;
  if (!waiting && !checks) return <Empty why="Nothing waits for you. What your AI suggests lands in Review." />;
  return (
    <>
      {waiting ? (
        <p>
          <Link className="button primary" to="/review">
            Review {plural(waiting, "suggestion")}
          </Link>
        </p>
      ) : null}
      {attention && checks ? <BrainChecks attention={attention} /> : null}
    </>
  );
}

/** The week in the supply chain: in, decided, waiting, handed out, and the stock's health. */
export function Week() {
  const { data: flow } = useBrainFlow(7);
  const { data: gaps } = useBrainGaps(30);
  if (!flow) return null;
  return (
    <Section title="This week">
      <dl className="flow">
        <Stat label="Came in" value={flow.came_in} to="/brain/history" />
        <Stat label="Approved" value={flow.approved} to="/brain/history?action=approved" />
        <Stat label="Waiting" value={flow.waiting} to="/review" note={flow.oldest_waiting ? `oldest ${when(flow.oldest_waiting)}` : undefined} />
        <Stat label="Conversations served" value={flow.delivery.conversations ?? 0} />
        <Stat label="AI work served" value={flow.delivery.work_runs ?? 0} />
        <Stat label="Entries handed out" value={flow.delivery.entries ?? 0} to="/brain/entries?view=most" />
        <Stat label="Found nothing" value={flow.delivery.empty ?? 0} to="/brain/gaps" attention={!!flow.delivery.empty} />
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
    stock.due ? <Link key="due" to="/brain/entries?view=due">{plural(stock.due, "entry", "entries")} due for a check</Link> : null,
    stock.disputed ? <Link key="disputed" to="/brain/entries?view=due">{stock.disputed} disputed</Link> : null,
    stock.unused_60_days ? (
      <Link key="unused" to="/brain/entries?view=unused">
        {stock.unused_60_days} {unusedLabel(flow.usage_since)}
      </Link>
    ) : null,
    gaps ? <Link key="gaps" to="/brain/gaps">{plural(gaps, "gap")} in 30 days</Link> : null,
  ].filter(Boolean);
  return (
    <p className="muted small">
      {plural(stock.live, "live entry", "live entries")}; the ones in every conversation cost {stock.standing_tokens.toLocaleString()}{" "}
      tokens each time.
      {parts.length ? <> {parts.reduce<ReactNode[]>((all, part, i) => (i ? [...all, " · ", part] : [part]), [])}.</> : null}
    </p>
  );
}

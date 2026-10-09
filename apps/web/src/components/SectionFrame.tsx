import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";

import { useBrainStatus } from "../api/hooks";
import { Empty, Loading } from "./ui";

export interface FrameTab {
  to: string;
  label: string;
  end?: boolean;
  badge?: number;
}

/** A place with tabs (the Brain, Work): its heading, its tabs, and what to do when no Brain is
 * connected. The tab's page renders below the tabs. */
export function SectionFrame({
  title,
  lede,
  tabs,
  stats,
  tour,
  className,
}: {
  title: string;
  lede: string;
  tabs: FrameTab[];
  stats?: ReactNode;
  tour: string;
  className: string;
}) {
  const { data: status, isLoading } = useBrainStatus();
  if (isLoading) return <Loading />;
  if (status && status.available === false) {
    return (
      <div className="page">
        <h1>{title}</h1>
        <Empty why="No Brain is connected. Run uv run contxt setup in the Contxt folder and restart the app: its knowledge, files and review queue then appear here." />
      </div>
    );
  }
  return (
    <div className={`page ${className}`}>
      <header className="brain-head">
        <div>
          <h1>{title}</h1>
          <p className="lede">{lede}</p>
        </div>
        {stats}
      </header>
      <nav className="brain-tabs" aria-label={`${title} sections`} data-tour={tour}>
        {tabs.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className="tab">
            {tab.label}
            {tab.badge ? <span className="badge">{tab.badge}</span> : null}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value ?? "…"}</dd>
    </div>
  );
}

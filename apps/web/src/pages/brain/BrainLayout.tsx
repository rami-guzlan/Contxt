import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";

import { useAgent, useBrainCatalog, useBrainFiles, useBrainGaps, useBrainStatus } from "../../api/hooks";
import { Empty, Loading } from "../../components/ui";

interface Tab {
  to: string;
  label: string;
  end?: boolean;
  badge?: number;
}

/** A Brain section's frame: its heading, its tabs, and what to do when no Brain is connected. */
function Frame({ title, lede, tabs, stats, tour }: { title: string; lede: string; tabs: Tab[]; stats?: ReactNode; tour: string }) {
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
    <div className="page brain">
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

// The Brain: what every AI you use can know, in the words it receives; its notes in full; its
// files; and the questions it could not answer, each one a thing to teach it. Its history lives
// in Activity, Changes.
export function BrainLayout() {
  const { data: catalog } = useBrainCatalog();
  const { data: files } = useBrainFiles();
  const { data: gaps } = useBrainGaps(30);
  const { data: agent } = useAgent();
  const fileCount = files ? files.references.length + files.assets.length : undefined;
  return (
    <Frame
      title="Brain"
      lede="What every AI you use can know. Nothing changes without you."
      tour="brain-tabs"
      tabs={[
        { to: "/brain", label: "What it knows", end: true },
        { to: "/brain/entries", label: "Notes" },
        { to: "/brain/files", label: "Files" },
        { to: "/brain/questions", label: "Questions", badge: gaps?.length ?? 0 },
        { to: "/brain/agent", label: "Knowledge agent", badge: agent?.questions.length ?? 0 },
      ]}
      stats={
        <dl className="stats">
          <Stat label="Notes" value={catalog?.entries.length} />
          <Stat label="Files" value={fileCount} />
          <Stat label="Skills" value={files?.skills.length} />
        </dl>
      }
    />
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value ?? "…"}</dd>
    </div>
  );
}

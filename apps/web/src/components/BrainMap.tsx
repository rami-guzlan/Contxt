// The Brain as a map: each area a tile sized by how much it holds and shaded by how much your AI
// used it this week, flagged when something in it wants a look. An area opens to its topics, a
// topic to its entries. The text stays one click away; the map is how you see the whole.

import { Link } from "react-router";

import { useBrainAttention, useBrainCatalog, useBrainProjects } from "../api/hooks";
import type { BrainAttention, BrainCatalog, BrainEntrySummary } from "../api/types";
import { plural, when } from "../lib/format";
import { entryUrl } from "../pages/brain/shared";
import { Empty, Loading } from "./ui";

/** How much of the week's use a tile had, against the busiest one: 0 (none) to 3. */
function heat(used: number, most: number): number {
  if (!used || !most) return 0;
  const share = used / most;
  return share >= 0.67 ? 3 : share >= 0.34 ? 2 : 1;
}

/** A tile's starting width: it grows with what the tile holds, so the map reads at a glance
 * (a busy area is wider than a thin one), within bounds that keep a label readable. */
function width(entries: number, compact: boolean): string {
  const px = compact ? 64 + entries * 5 : 96 + entries * 6;
  return `${Math.min(compact ? 260 : 380, Math.max(compact ? 110 : 140, px))}px`;
}

/** What wants a look, by entry: a clash, a near twin, a flag, a re-check. */
function checksByEntry(attention: BrainAttention | undefined): Map<string, number> {
  const out = new Map<string, number>();
  const add = (id: string) => out.set(id, (out.get(id) ?? 0) + 1);
  for (const clash of attention?.clashes ?? []) add(clash.entry_id);
  for (const twin of attention?.twins ?? []) add(twin.a);
  for (const item of [...(attention?.flagged ?? []), ...(attention?.recheck ?? [])]) add(item.id);
  return out;
}

interface Tile {
  key: string;
  label: string;
  entries: BrainEntrySummary[];
  used: number;
  checks: number;
  to: string;
}

function tiles(catalog: BrainCatalog, attention: BrainAttention | undefined): Tile[] {
  const usage = attention?.usage ?? {};
  const checks = checksByEntry(attention);
  return catalog.areas
    .map((area) => {
      const entries = catalog.entries.filter((e) => e.area === area.key);
      return {
        key: area.key,
        label: area.label,
        entries,
        used: entries.reduce((n, e) => n + (usage[e.id] ?? 0), 0),
        checks: entries.reduce((n, e) => n + (checks.get(e.id) ?? 0), 0),
        to: `/brain?area=${encodeURIComponent(area.key)}`,
      };
    })
    .sort((a, b) => b.entries.length - a.entries.length || a.label.localeCompare(b.label));
}

/** Every area of the Brain as a tile. `compact` for Home. */
export function BrainMap({ compact = false }: { compact?: boolean }) {
  const { data: catalog, isLoading } = useBrainCatalog();
  const { data: attention } = useBrainAttention();
  if (isLoading) return <Loading />;
  if (!catalog) return null;
  const all = tiles(catalog, attention);
  const filled = all.filter((tile) => tile.entries.length);
  if (!filled.length) {
    return (
      <div className="map-empty">
        <div className={compact ? "brain-map compact" : "brain-map"} aria-hidden="true">
          {(all.length ? all.map((t) => t.label) : ["About you", "Your work", "How you write"]).slice(0, 6).map((name) => (
            <div key={name} className="map-tile ghost">
              <span className="map-name">{name}</span>
            </div>
          ))}
        </div>
        <p className="muted">Your Brain's areas fill in as you add things: what you tell it, your files, and what your AI saves.</p>
      </div>
    );
  }
  const most = Math.max(...filled.map((t) => t.used));
  return (
    <div className={compact ? "brain-map compact" : "brain-map"} data-tour="brain-map">
      {filled.map((tile) => (
        <Link
          key={tile.key}
          to={tile.to}
          className={`map-tile heat-${heat(tile.used, most)}${tile.checks ? " flagged" : ""}`}
          style={{ flexGrow: tile.entries.length, flexBasis: width(tile.entries.length, compact) }}
          aria-label={`${tile.label}: ${plural(tile.entries.length, "entry", "entries")}${tile.used ? `, used ${plural(tile.used, "time")} this week` : ""}${tile.checks ? `, ${tile.checks} to check` : ""}`}
        >
          <span className="map-name">{tile.label}</span>
          <span className="map-count">{plural(tile.entries.length, "entry", "entries")}</span>
          {!compact && tile.used ? <span className="map-use">used {plural(tile.used, "time")} this week</span> : null}
          {tile.checks ? <span className="map-flag">{tile.checks} to check</span> : null}
        </Link>
      ))}
    </div>
  );
}

/** One area opened: its topics as tiles, each with the entries your AI used most. */
export function AreaMap({ areaKey }: { areaKey: string }) {
  const { data: catalog, isLoading } = useBrainCatalog();
  const { data: attention } = useBrainAttention();
  if (isLoading) return <Loading />;
  const area = catalog?.areas.find((a) => a.key === areaKey);
  if (!catalog || !area) return <Empty why="That area is not in the Brain." />;
  const usage = attention?.usage ?? {};
  const checks = checksByEntry(attention);
  const topics = area.topics
    .map((topic) => {
      const entries = catalog.entries
        .filter((e) => e.area === area.key && e.topic === topic.key)
        .sort((a, b) => (usage[b.id] ?? 0) - (usage[a.id] ?? 0) || a.title.localeCompare(b.title));
      return {
        topic,
        entries,
        used: entries.reduce((n, e) => n + (usage[e.id] ?? 0), 0),
        checks: entries.reduce((n, e) => n + (checks.get(e.id) ?? 0), 0),
      };
    })
    .filter((t) => t.entries.length)
    .sort((a, b) => b.entries.length - a.entries.length);
  const most = Math.max(0, ...topics.map((t) => t.used));
  return (
    <>
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/brain">Map</Link>
        <span aria-hidden="true">/</span>
        <span>{area.label}</span>
      </nav>
      {area.description ? <p className="lede">{area.description}</p> : null}
      {topics.length ? (
        <div className="brain-map topics">
          {topics.map(({ topic, entries, used, checks: flags }) => (
            <div
              key={topic.key}
              className={`map-tile topic heat-${heat(used, most)}${flags ? " flagged" : ""}`}
              style={{ flexGrow: entries.length, flexBasis: width(entries.length + 20, false) }}
            >
              <Link className="map-name" to={`/brain/entries?area=${encodeURIComponent(area.key)}&topic=${encodeURIComponent(topic.key)}`}>
                {topic.label}
              </Link>
              <span className="map-count">
                {plural(entries.length, "entry", "entries")}
                {used ? ` · used ${plural(used, "time")}` : ""}
              </span>
              <ul className="map-entries">
                {entries.slice(0, 4).map((entry) => (
                  <li key={entry.id}>
                    <Link to={entryUrl(entry.id)}>{entry.title}</Link>
                  </li>
                ))}
              </ul>
              {entries.length > 4 ? (
                <Link className="small" to={`/brain/entries?area=${encodeURIComponent(area.key)}&topic=${encodeURIComponent(topic.key)}`}>
                  All {entries.length}
                </Link>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <Empty why="Nothing is filed in this area yet." />
      )}
    </>
  );
}

/** The projects in motion as cards: where each stands and what is next. */
export function ProjectStrip({ limit = 6 }: { limit?: number }) {
  const { data: projects, isLoading } = useBrainProjects();
  if (isLoading) return <Loading />;
  const active = (projects ?? []).filter((p) => p.active).slice(0, limit);
  if (!active.length) {
    return (
      <Empty why="No projects yet. A project is work your AI follows: say its name in any chat and it knows where it stands.">
        <Link className="button" to="/projects">
          Start a project
        </Link>
      </Empty>
    );
  }
  return (
    <ul className="project-strip" data-tour="home-projects">
      {active.map((p) => (
        <li key={p.id} className="strip-card">
          <Link to={`/projects/${encodeURIComponent(p.id)}`} className="strip-card-title">
            {p.title}
          </Link>
          {p.next ? <span className="strip-card-next">Next: {p.next.length > 90 ? `${p.next.slice(0, 89)}…` : p.next}</span> : null}
          <span className="muted small">
            {p.files ? `${plural(p.files, "file")} · ` : ""}
            {p.updated ? when(p.updated) : "not updated yet"}
          </span>
        </li>
      ))}
    </ul>
  );
}

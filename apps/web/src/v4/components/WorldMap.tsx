// Brain › World (v4 backend plan, 13.5): the Brain as a world. Regions (areas and projects),
// entries as dots raised by level, relationships as lines filterable by type, a slider for
// what moved since, the lessons shelf, and the apps at the edge of the world. Selecting a dot
// opens the entry; selecting a line says why the two are connected.
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { get } from "../../api/client";
import { css } from "../css";
import { Failure, S } from "../ui";

interface Region {
  id: string;
  label: string;
  kind: "area" | "project";
  status: string;
}
interface Entry {
  id: string;
  title: string;
  region: string;
  level: string;
  kind: string;
}
interface Edge {
  from: string;
  to: string;
  type: string;
  source: string;
}
interface Moved {
  what: string;
  id: string;
  title: string;
  recorded: string;
}
interface World {
  overview: { text: string; state: "kept" | "draft" | "none" };
  regions: Region[];
  entries: Entry[];
  edges: Edge[];
  timeline: Moved[];
  lore: { id: string; title: string; region: string }[];
  apps: { name: string; seen: string; conversations: number }[];
  edge_types: string[];
}

const RADIUS: Record<string, number> = { canon: 7, confirmed: 6, kept: 5, tentative: 4, exhaust: 3 };
const W = 260;
const H = 150;
const COLS = 3;
const card = "background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:10px";

function since(days: number): string {
  const d = new Date(Date.now() - days * 86400000);
  return d.toISOString().slice(0, 10);
}

export function WorldMap() {
  const [days, setDays] = useState(30);
  const [type, setType] = useState("");
  const [picked, setPicked] = useState<{ kind: "entry"; entry: Entry } | { kind: "edge"; edge: Edge } | null>(null);
  const world = useQuery({
    queryKey: ["brain", "world", days],
    queryFn: () => get<World>(`/api/brain/world?since=${since(days)}`),
  });
  const w = world.data;
  const layout = useMemo(() => {
    const at: Record<string, { x: number; y: number }> = {};
    const boxes = (w?.regions ?? []).map((r, i) => ({ r, x: (i % COLS) * (W + 16), y: Math.floor(i / COLS) * (H + 16) }));
    for (const b of boxes) {
      const inside = (w?.entries ?? []).filter((e) => e.region === b.r.id);
      inside.forEach((e, j) => {
        const per = 9;
        at[e.id] = { x: b.x + 18 + (j % per) * 26, y: b.y + 44 + Math.floor(j / per) * 24 };
      });
    }
    return { boxes, at, height: Math.max(1, Math.ceil(boxes.length / COLS)) * (H + 16) };
  }, [w]);
  if (world.error) return <Failure error={world.error} retry={() => void world.refetch()} />;
  if (!w) return <span style={css(S.small)}>Drawing the world…</span>;
  const edges = w.edges.filter((e) => (!type || e.type === type) && layout.at[e.from] && layout.at[e.to]);
  const moved = new Set(w.timeline.map((m) => m.id));
  return (
    <div style={css("display:flex;flex-direction:column;gap:16px")}>
      <section aria-label="Overview" style={css(card)}>
        <span style={css("font:500 15px Geist")}>
          The world{w.overview.state === "draft" ? " (draft, not kept: it waits in Catch up)" : ""}
        </span>
        <span style={css("font:400 14px/1.6 Geist;white-space:pre-wrap")}>
          {w.overview.text || "No world overview kept yet. One is drafted after a distill once the Brain has regions."}
        </span>
      </section>
      <section aria-label="World map" style={css(card)}>
        <div style={css("display:flex;gap:12px;flex-wrap:wrap;align-items:center;font:400 13px Geist")}>
          <label style={css("display:flex;gap:6px;align-items:center")}>
            Lines
            <select aria-label="Relationship type" value={type} onChange={(e) => setType(e.target.value)} style={css("border:1px solid var(--line2);border-radius:10px;padding:6px 8px;background:var(--bg);color:var(--ink)")}>
              <option value="">All relationships</option>
              {w.edge_types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label style={css("display:flex;gap:6px;align-items:center")}>
            Moved in the last
            <input aria-label="Days back" type="range" min={1} max={90} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            {days} days ({moved.size} entries)
          </label>
        </div>
        <div style={css("overflow-x:auto")}>
          <svg role="img" aria-label="The Brain's regions, entries and relationships" viewBox={`0 0 ${COLS * (W + 16)} ${layout.height}`} style={css("width:100%;min-width:640px;height:auto")}>
            {layout.boxes.map(({ r, x, y }) => (
              <g key={r.id}>
                <rect x={x} y={y} width={W} height={H} rx={14} fill="none" stroke="currentColor" strokeOpacity={0.18} />
                <text x={x + 14} y={y + 24} fontSize={13} fill="currentColor">
                  {r.label}
                  {r.kind === "project" ? " · project" : ""}
                </text>
              </g>
            ))}
            {edges.map((e, i) => {
              const a = layout.at[e.from];
              const b = layout.at[e.to];
              if (!a || !b) return null;
              return (
                <line
                  key={`${e.from}-${e.to}-${i}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="currentColor"
                  strokeOpacity={0.35}
                  strokeWidth={2}
                  onClick={() => setPicked({ kind: "edge", edge: e })}
                  style={{ cursor: "pointer" }}
                >
                  <title>{`${e.from} ${e.type} ${e.to}`}</title>
                </line>
              );
            })}
            {w.entries.map((e) => {
              const p = layout.at[e.id];
              if (!p) return null;
              return (
                <circle
                  key={e.id}
                  cx={p.x}
                  cy={p.y}
                  r={RADIUS[e.level] ?? 4}
                  fill={moved.has(e.id) ? "var(--focus)" : "currentColor"}
                  fillOpacity={moved.has(e.id) ? 1 : 0.55}
                  onClick={() => setPicked({ kind: "entry", entry: e })}
                  style={{ cursor: "pointer" }}
                >
                  <title>{`${e.title} {${e.level}}`}</title>
                </circle>
              );
            })}
          </svg>
        </div>
        <span style={css(S.small)}>Dots are entries, larger the surer they are (canon, confirmed, kept, tentative, exhaust); filled ones moved in the window.</span>
        {picked?.kind === "entry" ? (
          <span style={css("font:400 13.5px Geist")}>
            <Link to={`/brain/notes/${encodeURIComponent(picked.entry.id)}`}>{picked.entry.title}</Link> · {picked.entry.level}
          </span>
        ) : null}
        {picked?.kind === "edge" ? (
          <span style={css("font:400 13.5px Geist")}>
            {picked.edge.from} {picked.edge.type} {picked.edge.to}, from its {picked.edge.source}.
          </span>
        ) : null}
      </section>
      <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:16px")}>
        <section aria-label="What moved" style={css(card)}>
          <span style={css("font:500 15px Geist")}>What moved</span>
          {w.timeline.length ? (
            w.timeline.slice(0, 12).map((m) => (
              <span key={`${m.id}-${m.recorded}-${m.what}`} style={css(S.small)}>
                {m.recorded.slice(0, 10)} {m.what}: {m.title}
              </span>
            ))
          ) : (
            <span style={css(S.small)}>Nothing moved in this window.</span>
          )}
        </section>
        <section aria-label="Lore" style={css(card)}>
          <span style={css("font:500 15px Geist")}>Lore</span>
          {w.lore.length ? (
            w.lore.map((l) => (
              <span key={l.id} style={css(S.small)}>
                {l.title} · {w.regions.find((r) => r.id === l.region)?.label ?? l.region}
              </span>
            ))
          ) : (
            <span style={css(S.small)}>No lessons yet.</span>
          )}
        </section>
        <section aria-label="The edge of the world" style={css(card)}>
          <span style={css("font:500 15px Geist")}>The edge of the world</span>
          {w.apps.length ? (
            w.apps.map((a) => (
              <span key={a.name} style={css(S.small)}>
                {a.name}: {a.conversations} conversations, last {a.seen.slice(0, 10)}
              </span>
            ))
          ) : (
            <span style={css(S.small)}>No app has read this Brain yet.</span>
          )}
        </section>
      </div>
    </div>
  );
}

// The Brain's front page: what your AI knows about you, as the sentences an AI receives. Your
// goals, who you are, how you like work done, your world (people, customers, the company and
// the rest), and your projects, each note with how often AIs used it this month. The map stays
// on top, sized by what each area holds and shaded by use.

import { Link, Navigate, useSearchParams } from "react-router";

import { useBrainInventory, useBrainProjects, useGoals } from "../../api/hooks";
import type { InventoryItem } from "../../api/types";
import { AreaMap, BrainMap } from "../../components/BrainMap";
import { FirstVisitTip } from "../../components/Tips";
import { ErrorNote, Loading, Section } from "../../components/ui";
import { plural, when } from "../../lib/format";
import { entryUrl } from "./shared";

const SHOWN = 8;

export function KnowsPage() {
  const [params] = useSearchParams();
  // Links from before: an entry, a filtered list of entries, or one area of the map.
  const entry = params.get("entry");
  if (entry) return <Navigate to={entryUrl(entry)} replace />;
  if (["topic", "kind", "show", "view"].some((key) => params.get(key))) return <Navigate to={`/brain/entries?${params.toString()}`} replace />;
  const area = params.get("area");
  if (area) {
    return (
      <div className="brain-overview">
        <AreaMap areaKey={area} />
      </div>
    );
  }
  return <Knows />;
}

function Knows() {
  const { data: inventory, isLoading, error } = useBrainInventory();
  const { data: goals } = useGoals();
  const { data: projects } = useBrainProjects();
  if (isLoading) return <Loading />;
  if (!inventory) return <ErrorNote error={error} />;
  const notes = inventory.filter((i) => i.type === "note" && i.live && i.kind !== "focus" && i.id !== goals?.id);
  const about = notes.filter((n) => n.kind === "identity");
  const how = notes.filter((n) => n.kind === "rule");
  const world = notes.filter((n) => n.kind !== "identity" && n.kind !== "rule");
  const byArea = new Map<string, InventoryItem[]>();
  for (const note of world) byArea.set(note.area_label || note.area, [...(byArea.get(note.area_label || note.area) ?? []), note]);
  const active = (projects ?? []).filter((p) => p.active);
  return (
    <div className="brain-overview knows">
      <FirstVisitTip id="brain">
        This is what your AIs can know, in the words they receive. Each request gets only the few notes it needs; open one to edit it.
      </FirstVisitTip>
      <BrainMap compact />
      <Section title="Your goals">
        {goals?.exists ? (
          <p>
            {goals.purpose}{" "}
            <Link className="small" to="/settings?tab=goals">
              All your answers
            </Link>
          </p>
        ) : (
          <p className="muted">
            Not said yet. <Link to="/settings?tab=goals">Say what your Brain is for</Link>: everything you bring in is sifted against it.
          </p>
        )}
      </Section>
      <Group title="About you" notes={about} more="/brain/entries?kind=identity" empty="Nothing yet about who you are. Tell it once, and every AI knows." />
      <Group title="How you like work done" notes={how} more="/brain/entries?kind=rule" empty="No rules or preferences yet." />
      {[...byArea.entries()]
        .sort((a, b) => b[1].length - a[1].length)
        .map(([name, list]) => (
          <Group key={name} title={name} notes={list} more={`/brain/entries?area=${encodeURIComponent(list[0]?.area ?? "")}`} />
        ))}
      <Section title="Your projects">
        {active.length ? (
          <ul className="list">
            {active.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${encodeURIComponent(p.id)}`}>{p.title}</Link>
                {p.current ? <span className="muted small"> · {p.current}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            No projects yet. <Link to="/projects">Start one</Link>.
          </p>
        )}
      </Section>
    </div>
  );
}

function Group({ title, notes, more, empty }: { title: string; notes: InventoryItem[]; more: string; empty?: string }) {
  if (!notes.length && !empty) return null;
  const shown = [...notes].sort((a, b) => b.uses.d30 - a.uses.d30).slice(0, SHOWN);
  return (
    <Section
      title={title}
      actions={
        notes.length > SHOWN ? (
          <Link className="button" to={more}>
            All {notes.length}
          </Link>
        ) : null
      }
    >
      {notes.length ? (
        <ul className="knows-list">
          {shown.map((note) => (
            <li key={note.id}>
              <p className="knows-text">{note.summary || note.title}</p>
              <p className="muted small">
                <Link to={entryUrl(note.id)}>{note.title}</Link>
                {" · "}
                {note.uses.d30 ? `used in ${plural(note.uses.d30, "chat")} this month` : note.uses.last ? `last used ${when(note.uses.last)}` : "not used yet"}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </Section>
  );
}

import { Link } from "react-router";

import { useActors, useMe } from "../api/hooks";
import type { WorkspaceEvent } from "../api/types";
import { describeEvent, subjectLink, when } from "../lib/format";
import { Empty } from "./ui";

export function ActivityList({ events }: { events: WorkspaceEvent[] | undefined }) {
  const { data: actors } = useActors();
  const { data: me } = useMe();
  const byId = new Map((actors ?? []).map((a) => [a.id, a]));
  if (!events?.length) return <Empty why="Nothing has happened here yet." />;
  return (
    <ol className="activity">
      {events.map((event) => {
        const href = subjectLink(event);
        const text = describeEvent(event, byId, me?.actor_id);
        return (
          <li key={event.id}>
            <time dateTime={event.at} title={event.at}>
              {when(event.at)}
            </time>
            {href ? <Link to={href}>{text}</Link> : <span>{text}</span>}
          </li>
        );
      })}
    </ol>
  );
}

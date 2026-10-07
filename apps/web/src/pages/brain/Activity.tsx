// Activity: everything that happened to the Brain, newest first, with who did it and why;
// and the undo points, each batch of decisions taken back as a unit.

import { useSearchParams } from "react-router";

import { useBrainActivity, useBrainPolicies } from "../../api/hooks";
import { Empty, ErrorNote, Loading, Tabs } from "../../components/ui";
import { ACTIONS, EventList } from "./events";
import { HistoryPage } from "./History";

const VIEWS = [
  { id: "events", label: "Everything that happened" },
  { id: "undo", label: "Undo points" },
] as const;

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "undo" ? "undo" : "events";
  const action = params.get("action") ?? "";
  const since = params.get("since") ?? "";

  function set(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  }

  return (
    <div className="activity-page">
      <Tabs tabs={VIEWS} active={view} onChange={(id) => set({ view: id === "events" ? "" : id })} />
      {view === "undo" ? (
        <HistoryPage />
      ) : (
        <>
          <div className="inventory-bar">
            <label className="inline-select">
              <span className="muted small">What</span>
              <select value={action} onChange={(event) => set({ action: event.target.value })}>
                <option value="">Everything</option>
                {ACTIONS.map(([key, name]) => (
                  <option key={key} value={key}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-select">
              <span className="muted small">Since</span>
              <input type="date" value={since} onChange={(event) => set({ since: event.target.value })} />
            </label>
          </div>
          <Events action={action} since={since} />
        </>
      )}
    </div>
  );
}

function Events({ action, since }: { action: string; since: string }) {
  const { data: events, isLoading, error } = useBrainActivity({
    action: action ? [action] : undefined,
    since: since ? `${since}T00:00:00Z` : undefined,
    limit: 300,
  });
  const { data: policies } = useBrainPolicies();
  if (isLoading) return <Loading />;
  if (!events) return <ErrorNote error={error} />;
  if (!events.length) {
    return <Empty why={action || since ? "Nothing like that happened in this window." : "Nothing has happened in the Brain yet."} />;
  }
  return <EventList events={events} approver={policies?.approver} />;
}

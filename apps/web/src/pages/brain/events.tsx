// The Brain's governed events, as sentences a person reads: who did what to which entry, when
// and why. The Activity page lists every one; an entry's page lists its own.

import { Link } from "react-router";

import type { BrainEvent } from "../../api/types";
import { label, when } from "../../lib/format";
import { entryUrl, ownerName } from "./shared";

export const ACTIONS: [string, string][] = [
  ["approved", "Approved"],
  ["auto-applied", "Saved straight in"],
  ["rejected", "Rejected"],
  ["edited", "Edited"],
  ["restored", "Restored to an earlier version"],
  ["updated", "Details changed"],
  ["verified", "Checked"],
  ["marked", "Marked stale or disputed"],
  ["archived", "Removed"],
  ["unarchived", "Brought back"],
  ["policy", "Policy changed"],
  ["reverted", "Undone"],
  ["redone", "Redone"],
];
const VERB = new Map(ACTIONS);

const FIELD_NAMES: Record<string, string> = {
  owner: "owner",
  review_days: "review cadence",
  review_by: "review date",
  classification: "sensitivity",
  area: "area",
  topic: "topic",
};

/** What happened, in one sentence, from the point of view of `about` (an entry) when given. */
export function describeEvent(event: BrainEvent, approver = "", about?: string): string {
  const who = event.by ? ownerName(event.by, approver) || event.by : "";
  const action = event.action;
  let text: string;
  if (about && event.note && event.note !== about && event.superseded?.includes(about)) {
    text = `Replaced by “${event.title ?? event.note}” when that was approved`;
  } else if (action === "marked") {
    text = `Marked ${event.state ?? "stale"}`;
  } else if (action === "updated" && event.fields) {
    const names = Object.keys(event.fields).map((k) => FIELD_NAMES[k] ?? k);
    text = `Changed its ${names.join(", ")}`;
  } else if (action === "restored") {
    text = `Restored to its version of ${event.from_at ? new Date(event.from_at).toLocaleDateString() : "an earlier date"}`;
  } else if (action === "policy") {
    text = `Changed the policy (${Object.keys(event.changes ?? {}).map((k) => label(k)).join(", ")})`;
  } else if (action === "verified") {
    text = event.confidence ? `Checked: ${label(event.confidence)}` : "Checked: still true";
  } else if (action === "reverted" || action === "redone") {
    const original = event.reverted ?? event.redone;
    text = `${action === "reverted" ? "Undid" : "Redid"} ${original ? VERB.get(original)?.toLowerCase() ?? original : "a decision"}`;
  } else if (action === "edited" && event.minor) {
    text = "Small fix";
  } else {
    text = VERB.get(action) ?? label(action);
  }
  if (who) text += ` by ${who}`;
  if (event.proposer && event.proposer !== event.by && (action === "approved" || action === "rejected")) {
    text += `, proposed by ${ownerName(event.proposer, approver) || event.proposer}`;
  }
  return text;
}

export function EventList({ events, approver, about }: { events: BrainEvent[]; approver?: string; about?: string }) {
  return (
    <ol className="history event-list">
      {events.map((event, index) => {
        const entry = event.note && event.note !== about ? event.note : null;
        // A procedure has no entry: it is named by its skill, or by its folder.
        const skill = entry || event.note ? null
          : event.skill ?? (event.path?.startsWith("skills/") ? event.path.split("/").pop() : null);
        // The chip names the action; the sentence beside it says the rest, not the verb again.
        const verb = VERB.get(event.action) ?? label(event.action);
        const sentence = describeEvent(event, approver, about);
        // "Checked: still true" reads "[Checked] still true" beside its chip.
        const rest = sentence.startsWith(verb) ? sentence.slice(verb.length).replace(/^:?\s*/, "") : sentence;
        return (
          <li key={`${event.at}-${event.action}-${index}`}>
            <span>
              <span className={`chip chip-${event.action}`}>{verb}</span> {rest}
              {entry ? (
                <>
                  {": "}
                  <Link to={entryUrl(entry)}>{event.title ?? entry}</Link>
                </>
              ) : skill ? (
                <>
                  {": "}
                  <Link to={`/skills/${encodeURIComponent(skill)}`}>/{skill}</Link>
                </>
              ) : null}
              {event.reason ? <span className="muted"> “{event.reason}”</span> : null}
            </span>
            <time dateTime={event.at}>{when(event.at)}</time>
          </li>
        );
      })}
    </ol>
  );
}

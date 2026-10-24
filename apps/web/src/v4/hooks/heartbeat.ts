// The heartbeat (/api/heartbeat): its status (polled quickly while a beat runs, so connector chips
// light as each is read), the regions it keeps, recent beats, Beat now, pause, settings, the
// connectors and undo of one line.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { get, post, put, query } from "../../api/client";

export type ConnectorStatus = "ok" | "off" | "unhealthy_sign_in" | "provider_limit" | "cannot_confirm_read_only" | "error";

export interface HbConnector {
  id: string;
  name: string;
  cli: string;
  cli_label: string;
  how: "mcp" | "computer" | "folder";
  how_label: string;
  cadence_minutes: number | null;
  feeds: string[];
  enabled: boolean;
  last_read_at: string | null;
  last_items: number;
  status: ConnectorStatus;
  status_line: string;
  tools: string[];
  found_in: string;
  present: boolean;
}

export interface HbBeat {
  id: string;
  status: "running" | "done" | "failed";
  trigger: string;
  started_at: string;
  finished_at: string | null;
  connectors: { id: string; name: string; read: boolean; status?: string; items?: number; new?: number }[];
  connectors_read: number;
  items: number;
  changes: number;
  waits: number;
  held: number;
  tokens: number | null;
  tokens_known: boolean;
  tokens_unknown: number;
  duration_ms: number | null;
  errors: string[];
  details: string[];
  nothing_new: boolean;
}

export type HbState = "ready" | "paused" | "quiet" | "unhealthy_sign_in" | "provider_limit" | "no_connectors";

export interface HbStatus {
  state: HbState;
  line: string;
  cadence: number;
  cadences: number[];
  quiet_hours: "off" | "night" | "nights_weekends";
  quiet_options: { id: string; label: string }[];
  in_quiet_hours: boolean;
  paused: boolean;
  cli: string;
  cli_label: string;
  signed_in: boolean | null;
  backoff: { reason: string; line: string; until: string } | null;
  last_beat: HbBeat | null;
  next_beat_at: string | null;
  running: { beat_id: string; reading: string | null; read: string[] } | null;
  connectors: HbConnector[];
  cost: { with_changes: number | null; nothing_new: number | null; beats: number; unknown: number };
}

export interface HbLine {
  id: string;
  beat_id: string;
  region: string;
  project: string | null;
  text: string;
  connector_id: string;
  connector: string;
  how: string;
  cli: string;
  cli_label: string;
  at: string;
  written_at: string;
  wrote: string;
  reason: string;
  status: "noted" | "applied" | "waiting" | "held" | "refused" | "undone";
  held: boolean;
  new_this_beat: boolean;
  proposal_id: string | null;
  checkpoint_id: string | null;
  source_id: string;
  can_undo: boolean;
}

export interface HbRegion {
  id: string;
  name: string;
  headline: string;
  headline_at: string | null;
  updated_at: string | null;
  lines: HbLine[];
  new_this_beat: number;
  projects: { id: string; title: string; status: string; at: string | null; from: string[] }[];
}

/** The heartbeat's status: every second while a beat runs, else every half minute. When a beat
 * finishes, the regions and the beats are read again. */
export function useHeartbeat() {
  const client = useQueryClient();
  const found = useQuery({
    queryKey: ["heartbeat", "status"],
    queryFn: () => get<HbStatus>("/api/heartbeat/status"),
    refetchInterval: (q) => (q.state.data?.running ? 1000 : 30000),
  });
  const running = Boolean(found.data?.running);
  const was = useRef(running);
  useEffect(() => {
    if (was.current && !running) {
      void client.invalidateQueries({ queryKey: ["heartbeat", "regions"] });
      void client.invalidateQueries({ queryKey: ["heartbeat", "beats"] });
      void client.invalidateQueries({ queryKey: ["brain"] });
    }
    was.current = running;
  }, [running, client]);
  return found;
}

export const useRegions = () => useQuery({ queryKey: ["heartbeat", "regions"], queryFn: () => get<HbRegion[]>("/api/heartbeat/regions") });

export const useBeats = (limit = 6) =>
  useQuery({ queryKey: ["heartbeat", "beats", limit], queryFn: () => get<HbBeat[]>(`/api/heartbeat/beats${query({ limit })}`) });

function useHeartbeatRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["heartbeat"] });
}

/** Beat now: it runs in the background; the status shows what it reads. */
export function useBeatNow() {
  const refresh = useHeartbeatRefresh();
  return useMutation({
    mutationFn: () => post<{ beat_id?: string; status?: string; skipped?: string; line?: string }>("/api/heartbeat/beat"),
    onSuccess: () => refresh(),
  });
}

export interface HbSettingsIn {
  cadence?: number;
  quiet_hours?: string;
  paused?: boolean;
}

export function useHeartbeatSettings() {
  const refresh = useHeartbeatRefresh();
  return useMutation({
    mutationFn: (changes: HbSettingsIn) => put<HbStatus>("/api/heartbeat/settings", changes),
    onSuccess: () => refresh(),
  });
}

export function useRescan() {
  const refresh = useHeartbeatRefresh();
  return useMutation({
    mutationFn: () => post<{ found: number; added: string[]; line: string; connectors: HbConnector[] }>("/api/heartbeat/connectors/rescan"),
    onSuccess: () => refresh(),
  });
}

export function useSetConnector() {
  const refresh = useHeartbeatRefresh();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => put<HbConnector>(`/api/heartbeat/connectors/${encodeURIComponent(id)}`, { enabled }),
    onSuccess: () => refresh(),
  });
}

export function useUndoLine() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post<HbLine & { line: string }>(`/api/heartbeat/lines/${encodeURIComponent(id)}/undo`),
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: ["heartbeat"] }), client.invalidateQueries({ queryKey: ["brain"] })]),
  });
}

/** "9:12" for a time today, else "Oct 21, 9:12". */
export function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function tokens(n: number | null | undefined): string {
  return n === null || n === undefined ? "tokens unknown" : `${n.toLocaleString("en-US")} tok`;
}

/** One beat in a line: what it read and changed, or that nothing was new. */
export function beatSummary(b: HbBeat): string {
  if (b.status === "failed") return `Stopped: ${b.errors[0] ?? "it could not finish"}`;
  if (b.status === "running") return "Beating…";
  const read = `${b.connectors_read} ${b.connectors_read === 1 ? "connector" : "connectors"}`;
  if (b.nothing_new) return `Nothing new · ${read}`;
  const parts = [read, `${b.items} ${b.items === 1 ? "item" : "items"}`, `${b.changes} ${b.changes === 1 ? "change" : "changes"}`];
  if (b.waits) parts.push(`${b.waits} ${b.waits === 1 ? "waits" : "wait"}`);
  if (b.held) parts.push(`${b.held} held back`);
  return parts.join(" · ");
}

/** The cost line, from the beats' own records. */
export function costLine(status: HbStatus | undefined): string {
  const cost = status?.cost;
  if (!cost || !cost.beats) return "No beats yet, so there is no cost to show";
  const changed = cost.with_changes !== null ? `About ${cost.with_changes.toLocaleString("en-US")} tokens a beat with changes` : "";
  const none = cost.nothing_new !== null ? `${cost.nothing_new.toLocaleString("en-US")} with none` : "";
  const said = [changed, none].filter(Boolean).join(", ");
  const plan = ` on your ${status?.cli_label ?? "CLI"} plan`;
  if (!said) return `The CLI did not say what the last ${cost.beats} beats used`;
  return `${said.charAt(0).toUpperCase()}${said.slice(1)}${plan}`;
}

// Data hooks for Settings > Test the Brain. Reads are plain queries; the only writes are
// starting and cancelling a run, connecting a Lab's folder, and a read-only "watch".

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { del, get, post, query } from "../../../api/client";
import type {
  ActiveRun,
  CaseFull,
  CasePage,
  Compare,
  GateRow,
  LiveReply,
  Overview,
  ProgressEvent,
  RunRow,
  State,
  Summary,
  WatchReply,
} from "./types";

const BASE = "/api/test-the-brain";
const KEY = ["test-the-brain"] as const;

export const ttbKeys = {
  all: KEY,
  state: [...KEY, "state"] as const,
  overview: [...KEY, "overview"] as const,
  gates: [...KEY, "gates"] as const,
  runs: (kind?: string) => [...KEY, "runs", kind ?? ""] as const,
};

export function useTtbState() {
  return useQuery({
    queryKey: ttbKeys.state,
    queryFn: () => get<State>(BASE),
    refetchInterval: (q) => (q.state.data?.running ? 1500 : 15_000),
  });
}

export function useTtbOverview() {
  return useQuery({ queryKey: ttbKeys.overview, queryFn: () => get<Overview>(`${BASE}/overview`) });
}

export function useTtbGates() {
  return useQuery({ queryKey: ttbKeys.gates, queryFn: () => get<{ gates: GateRow[]; run: string | null }>(`${BASE}/gates`) });
}

export function useTtbRuns(kind?: string) {
  return useQuery({
    queryKey: ttbKeys.runs(kind),
    queryFn: () => get<{ runs: RunRow[] }>(`${BASE}/runs${query({ kind })}`),
  });
}

export function useTtbRun(run: string | undefined) {
  return useQuery({
    queryKey: [...KEY, "run", run],
    queryFn: () => get<Summary>(`${BASE}/runs/${encodeURIComponent(run ?? "")}`),
    enabled: !!run,
  });
}

export interface CaseFilters {
  kind?: string;
  result?: string;
  suite?: string;
  gate?: string;
  offset?: number;
}

export function useTtbCases(run: string | undefined, filters: CaseFilters) {
  return useQuery({
    queryKey: [...KEY, "cases", run, filters],
    queryFn: () => get<CasePage>(`${BASE}/runs/${encodeURIComponent(run ?? "")}/cases${query({ ...filters, limit: 100 })}`),
    enabled: !!run,
  });
}

export function useTtbCase(run: string | undefined, id: string | undefined) {
  return useQuery({
    queryKey: [...KEY, "case", run, id],
    queryFn: () => get<CaseFull>(`${BASE}/runs/${encodeURIComponent(run ?? "")}/cases/${encodeURIComponent(id ?? "")}`),
    enabled: !!run && !!id,
  });
}

export function useTtbCompare(a: string | undefined, b: string | undefined) {
  return useQuery({
    queryKey: [...KEY, "compare", a, b],
    queryFn: () => get<Compare>(`${BASE}/compare${query({ a, b })}`),
    enabled: !!a && !!b && a !== b,
  });
}

function useRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: KEY });
}

export interface StartBody {
  kind: string;
  suite?: string | null;
  confirm?: boolean;
  request?: string | null;
}

export function useStartRun() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: StartBody) => post<ActiveRun>(`${BASE}/runs`, body),
    onSuccess: refresh,
  });
}

export function useCancelRun() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (run: string) => post<ActiveRun>(`${BASE}/runs/${encodeURIComponent(run)}/cancel`), onSuccess: refresh });
}

export function useConnectLab() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (folder: string) => post<State>(`${BASE}/lab`, { folder }), onSuccess: refresh });
}

export function useDisconnectLab() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: () => del<State>(`${BASE}/lab`), onSuccess: refresh });
}

export function useWatch() {
  return useMutation({
    mutationFn: (body: { request?: string; run?: string; case?: string }) => post<WatchReply>(`${BASE}/watch`, body),
  });
}

/** The run in progress (or the last one this app started) and its events so far, polled while
 * `poll` is true. A new run starts its events from the top. */
export function useLiveRun(poll: boolean) {
  const [active, setActive] = useState<ActiveRun | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const cursor = useRef(0);
  const current = useRef<string | null>(null);
  const client = useQueryClient();
  const wasRunning = useRef(false);

  const refresh = useCallback(async () => {
    let found = await get<LiveReply>(`${BASE}/live${query({ after: cursor.current })}`);
    const id = found.active ? `${found.active.ticket ?? ""}/${found.active.run ?? ""}` : null;
    if (id !== current.current) {
      current.current = id;
      cursor.current = 0;
      setEvents([]);
      if (found.next > 0 || found.events.length) found = await get<LiveReply>(`${BASE}/live${query({ after: 0 })}`);
    }
    cursor.current = found.next;
    if (found.events.length) setEvents((seen) => [...seen, ...found.events]);
    setActive(found.active);
    const running = found.active?.state === "running";
    if (wasRunning.current && !running) void client.invalidateQueries({ queryKey: KEY });
    wasRunning.current = running;
  }, [client]);

  useEffect(() => {
    void refresh().catch(() => undefined);
    if (!poll) return;
    const timer = setInterval(() => void refresh().catch(() => undefined), active?.state === "running" ? 800 : 3000);
    return () => clearInterval(timer);
  }, [poll, refresh, active?.state]);

  return { active, events, refresh };
}

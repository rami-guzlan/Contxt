// The Test Bench's three panels (Release 1 plan, 15.3): the same request with no brain, the
// full brain and the custom packet, by the same runner and model, without tools. An estimate
// comes first, and a run only happens when Run is pressed.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { get, post } from "../../api/client";
import { css } from "../css";
import type { BenchExclude } from "../hooks/brain";
import { Btn, Failure, S } from "../ui";

interface BenchPanel {
  mode: "none" | "full" | "custom";
  status: string;
  output: string;
  packet: string;
  tokens_in: number | null;
  tokens_out: number | null;
  cost: number | null;
  ms: number | null;
  measured: boolean;
  error: string | null;
}

interface BenchRun {
  id: string;
  status: string;
  runner: string;
  model: string | null;
  provider: string;
  brain_version: string;
  panels: BenchPanel[];
}

interface BenchEstimate {
  provider: string;
  panels: { mode: string; tokens_in: number; cost: number | null }[];
}

const LABEL: Record<string, string> = { none: "No brain", full: "Full brain", custom: "Custom" };
const RUNNERS = [
  ["claude", "Claude Code"],
  ["codex", "Codex"],
  ["gemini", "Gemini CLI"],
] as const;

const money = (n: number | null | undefined) => (n == null ? "price unknown" : `$${n.toFixed(4)}`);

export function BenchPanels({ request, left }: { request: string; left: BenchExclude }) {
  const [runner, setRunner] = useState("claude");
  const [model, setModel] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const body = { request, runner, model, exclude: left };
  const estimate = useMutation({ mutationFn: () => post<BenchEstimate>("/api/bench/estimate", body) });
  const start = useMutation({
    mutationFn: () => post<BenchRun>("/api/bench/runs", body),
    onSuccess: (run) => setRunId(run.id),
  });
  const run = useQuery({
    queryKey: ["bench", "run", runId],
    queryFn: () => get<BenchRun>(`/api/bench/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2000 : false),
  });
  const r = run.data;
  return (
    <section
      aria-label="Run it three ways"
      style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:12px")}
    >
      <span style={css("font:500 15px Geist")}>Run it three ways</span>
      <span style={css(S.small)}>The same request with no brain, your full brain, and your custom packet, by the same model, with no tools.</span>
      <div style={css("display:flex;gap:8px;flex-wrap:wrap;align-items:center")}>
        <label style={css("font:400 13px Geist;display:flex;gap:6px;align-items:center")}>
          Runner
          <select value={runner} onChange={(e) => setRunner(e.target.value)} style={css("border:1px solid var(--line2);border-radius:10px;padding:6px 8px;background:var(--bg);color:var(--ink)")}>
            {RUNNERS.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label style={css("font:400 13px Geist;display:flex;gap:6px;align-items:center")}>
          Model
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="the CLI's default"
            style={css("border:1px solid var(--line2);border-radius:10px;padding:6px 8px;background:var(--bg);color:var(--ink);width:180px")}
          />
        </label>
        <Btn onClick={() => estimate.mutate()} disabled={estimate.isPending}>
          {estimate.isPending ? "Estimating…" : "Estimate"}
        </Btn>
        <Btn kind="primary" onClick={() => start.mutate()} disabled={start.isPending || r?.status === "running"}>
          {r ? "Re-run" : "Run"}
        </Btn>
      </div>
      {estimate.data ? (
        <span style={css(S.small)}>
          Sends this request and its packet to {estimate.data.provider}:{" "}
          {estimate.data.panels.map((p) => `${LABEL[p.mode]} about ${p.tokens_in.toLocaleString()} tokens (${money(p.cost)})`).join(" · ")}. Estimated.
        </span>
      ) : null}
      {estimate.error ? <Failure error={estimate.error} retry={() => estimate.mutate()} /> : null}
      {start.error ? <Failure error={start.error} retry={() => start.mutate()} /> : null}
      {r ? (
        <>
          <span style={css(S.small)}>
            {r.provider} received the request{r.panels.some((p) => p.mode !== "none") ? " and the packet" : ""}. Brain {r.brain_version}.
          </span>
          <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px")}>
            {r.panels.map((p) => (
              <div key={p.mode} aria-label={LABEL[p.mode]} style={css("border:1px solid var(--line2);border-radius:16px;padding:12px;display:flex;flex-direction:column;gap:8px")}>
                <span style={css("font:500 14px Geist")}>{LABEL[p.mode]}</span>
                {p.status === "done" ? (
                  <>
                    <div style={css("font:400 13.5px/1.55 Geist;white-space:pre-wrap")}>{p.output}</div>
                    <span style={css("font:400 11.5px 'Geist Mono';color:var(--muted)")}>
                      {p.tokens_in ?? "?"} in · {p.tokens_out ?? "?"} out{p.measured ? "" : " (est.)"} · {money(p.cost)} · {p.ms != null ? `${(p.ms / 1000).toFixed(1)} s` : "time unknown"}
                    </span>
                  </>
                ) : p.status === "failed" ? (
                  <span style={css(S.small)}>{p.error}</span>
                ) : (
                  <span style={css(S.small)}>{p.status === "running" ? "Answering…" : "Waiting for its turn…"}</span>
                )}
              </div>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}

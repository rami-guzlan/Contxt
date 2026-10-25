// Test Bench tests, suites and scoring (Release 1 plan, 15.4 and 15.5): save the request as a
// test in the Brain's folder, run a suite, see each answer with the grader's score, score it
// yourself (yours overrides the model's), and the summary.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { del, get, post, put } from "../../api/client";
import { css } from "../css";
import type { BenchExclude } from "../hooks/brain";
import { Btn, Failure, S } from "../ui";

interface BenchTest {
  id: string;
  suite: string;
  name: string;
  request: string;
  rubric?: string[];
  gold?: string;
}
interface BenchSuite {
  id: string;
  name: string;
  description: string;
  after_distill: boolean;
  tests: BenchTest[];
}
interface Score {
  by: "model" | "human";
  overall: number;
  criteria: { criterion: string; result: string }[];
  reason: string;
  thumbs: string | null;
  edits: string | null;
}
interface Result {
  id: string;
  test: string | null;
  mode: string;
  output: string;
  error: string | null;
  grade_error: string | null;
  brain_version: string;
  score: Score | null;
  model_score: Score | null;
}
interface SuiteRun {
  id: string;
  suite: string;
  status: string;
  tests: number;
  error: string | null;
  results: Result[];
}
interface Summary {
  by_mode: { mode: string; wins: number; compared: number; win_rate: number | null }[];
  suites: { suite: string; versions: { brain_version: string; runs: number; average: number }[] }[];
  sections: { section: string; with: number; without: number }[];
  sections_note: string;
  scored: number;
}

const LABEL: Record<string, string> = { none: "No brain", full: "Full brain", custom: "Custom" };
const field = "border:1px solid var(--line2);border-radius:10px;padding:6px 8px;background:var(--bg);color:var(--ink);font:400 13px Geist";
const card = "background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:12px";

function ScoreLine({ score, gradeError }: { score: Score | null; gradeError: string | null }) {
  if (!score) return <span style={css(S.small)}>{gradeError ? `Not graded: ${gradeError}` : "Not scored yet."}</span>;
  const who = score.by === "human" ? "Your score" : "Grader";
  const met = score.criteria.map((c) => `${c.criterion || "criterion"}: ${c.result}`).join(" · ");
  return (
    <span style={css(S.small)}>
      {who} {score.overall}/5{score.reason ? `, ${score.reason}` : ""}{met ? ` (${met})` : ""}
    </span>
  );
}

function YourScore({ result, onScored }: { result: Result; onScored: () => void }) {
  const [edits, setEdits] = useState("");
  const [note, setNote] = useState("");
  const send = useMutation({
    mutationFn: (thumbs: string) => post(`/api/bench/results/${result.id}/score`, { thumbs, edits, note }),
    onSuccess: onScored,
  });
  return (
    <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
      <select aria-label="Edits needed" value={edits} onChange={(e) => setEdits(e.target.value)} style={css(field)}>
        <option value="">Edits needed?</option>
        <option value="none">No edits</option>
        <option value="light">Light edits</option>
        <option value="heavy">Heavy edits</option>
      </select>
      <input aria-label="Note" placeholder="A note (optional)" value={note} onChange={(e) => setNote(e.target.value)} style={css(field + ";width:160px")} />
      <Btn onClick={() => send.mutate("up")} disabled={send.isPending}>Good</Btn>
      <Btn onClick={() => send.mutate("down")} disabled={send.isPending}>Not good</Btn>
      {send.error ? <Failure error={send.error} /> : null}
    </div>
  );
}

export function BenchSuites({ request, left }: { request: string; left: BenchExclude }) {
  const qc = useQueryClient();
  const [suite, setSuite] = useState("quality");
  const [name, setName] = useState("");
  const [rubric, setRubric] = useState("");
  const [gold, setGold] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const suites = useQuery({ queryKey: ["bench", "suites"], queryFn: () => get<{ suites: BenchSuite[] }>("/api/bench/suites") });
  const summary = useQuery({ queryKey: ["bench", "summary"], queryFn: () => get<Summary>("/api/bench/summary") });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["bench", "suites"] });
    void qc.invalidateQueries({ queryKey: ["bench", "summary"] });
    void qc.invalidateQueries({ queryKey: ["bench", "suite-run"] });
  };
  const save = useMutation({
    mutationFn: () =>
      post<BenchTest>(`/api/bench/suites/${suite}/tests`, {
        name: name || request.slice(0, 60),
        request,
        rubric: rubric.split("\n").filter((r) => r.trim()),
        gold,
        exclude: left.sections.length + left.ids.length ? left : {},
      }),
    onSuccess: () => {
      setName("");
      setRubric("");
      setGold("");
      refresh();
    },
  });
  const act = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: refresh });
  const run = useMutation({
    mutationFn: (id: string) => post<{ id: string }>(`/api/bench/suites/${id}/run`, { modes: ["none", "full"] }),
    onSuccess: (r) => setRunId(r.id),
  });
  const progress = useQuery({
    queryKey: ["bench", "suite-run", runId],
    queryFn: () => get<SuiteRun>(`/api/bench/suite-runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2000 : false),
  });
  const done = progress.data;
  const s = summary.data;
  return (
    <>
      <section aria-label="Save as a test" style={css(card)}>
        <span style={css("font:500 15px Geist")}>Save as a test</span>
        <span style={css(S.small)}>Tests live in your Brain's folder (bench/&lt;suite&gt;/&lt;test&gt;.yaml), so your quality bar travels with it.</span>
        <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
          <input aria-label="Suite" value={suite} onChange={(e) => setSuite(e.target.value)} style={css(field + ";width:140px")} />
          <input aria-label="Test name" placeholder="Test name" value={name} onChange={(e) => setName(e.target.value)} style={css(field + ";flex:1;min-width:160px")} />
        </div>
        <textarea aria-label="Rubric" placeholder="Rubric: one criterion per line" value={rubric} onChange={(e) => setRubric(e.target.value)} rows={3} style={css(field)} />
        <textarea aria-label="Gold example" placeholder="A gold example (optional)" value={gold} onChange={(e) => setGold(e.target.value)} rows={2} style={css(field)} />
        <div>
          <Btn kind="primary" onClick={() => save.mutate()} disabled={!request.trim() || save.isPending}>
            Save test
          </Btn>
        </div>
        {save.error ? <Failure error={save.error} retry={() => save.mutate()} /> : null}
      </section>

      <section aria-label="Suites" style={css(card)}>
        <span style={css("font:500 15px Geist")}>Suites</span>
        {suites.error ? <Failure error={suites.error} retry={() => void suites.refetch()} /> : null}
        {suites.data?.suites.length === 0 ? <span style={css(S.small)}>No tests yet. Save the request above as your first one.</span> : null}
        {suites.data?.suites.map((su) => (
          <div key={su.id} aria-label={`Suite ${su.name}`} style={css("border:1px solid var(--line2);border-radius:16px;padding:12px;display:flex;flex-direction:column;gap:8px")}>
            <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
              <span style={css("font:500 14px Geist;flex:1")}>{su.name}</span>
              <label style={css("font:400 12.5px Geist;display:flex;gap:4px;align-items:center")}>
                <input
                  type="checkbox"
                  checked={su.after_distill}
                  onChange={(e) => act.mutate(() => put(`/api/bench/suites/${su.id}`, { name: su.name, description: su.description, after_distill: e.target.checked }))}
                />
                Run after each distill
              </label>
              <Btn kind="primary" onClick={() => run.mutate(su.id)} disabled={run.isPending || done?.status === "running"}>
                Run suite
              </Btn>
              <Btn onClick={() => act.mutate(() => del(`/api/bench/suites/${su.id}`))}>Delete suite</Btn>
            </div>
            {su.tests.map((t) => (
              <div key={t.id} style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
                <span style={css("font:400 13px Geist;flex:1;min-width:0")}>
                  {t.name} <span style={css("color:var(--muted)")}>· {t.rubric?.length ?? 0} criteria</span>
                </span>
                <Btn onClick={() => act.mutate(() => post(`/api/bench/suites/${su.id}/tests/${t.id}/duplicate`))}>Duplicate</Btn>
                <Btn onClick={() => act.mutate(() => del(`/api/bench/suites/${su.id}/tests/${t.id}`))}>Delete</Btn>
              </div>
            ))}
          </div>
        ))}
        {act.error ? <Failure error={act.error} /> : null}
        {run.error ? <Failure error={run.error} /> : null}
        {done ? (
          <div aria-label="Suite results" style={css("display:flex;flex-direction:column;gap:10px")}>
            <span style={css(S.small)}>
              {done.status === "running" ? `Running ${done.suite}: ${done.results.length} answers so far…` : `${done.suite}: ${done.results.length} answers.`}
              {done.error ? ` ${done.error}` : ""}
            </span>
            {done.results.map((r) => (
              <div key={r.id} style={css("border-top:1px solid var(--line2);padding-top:8px;display:flex;flex-direction:column;gap:6px")}>
                <span style={css("font:500 13px Geist")}>
                  {r.test} · {LABEL[r.mode] ?? r.mode} · Brain {r.brain_version}
                </span>
                <div style={css("font:400 13px/1.5 Geist;white-space:pre-wrap")}>{r.error ?? r.output}</div>
                <ScoreLine score={r.score} gradeError={r.grade_error} />
                <YourScore result={r} onScored={refresh} />
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {s && s.scored > 0 ? (
        <section aria-label="Summary" style={css(card)}>
          <span style={css("font:500 15px Geist")}>Summary</span>
          <span style={css(S.small)}>
            Win rate:{" "}
            {s.by_mode
              .filter((m) => m.compared)
              .map((m) => `${LABEL[m.mode]} ${Math.round((m.win_rate ?? 0) * 100)}% of ${m.compared}`)
              .join(" · ") || "run a suite in two modes to compare"}
          </span>
          {s.suites.map((su) => (
            <span key={su.suite} style={css(S.small)}>
              {su.suite}: {su.versions.map((v) => `Brain ${v.brain_version} ${v.average}/5 (${v.runs})`).join(" · ")}
            </span>
          ))}
          {s.sections.length ? (
            <span style={css(S.small)}>
              With and without each section: {s.sections.map((x) => `${x.section} ${x.with} vs ${x.without}`).join(" · ")}. {s.sections_note}
            </span>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

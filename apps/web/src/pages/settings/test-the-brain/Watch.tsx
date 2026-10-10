// Watch it work: pick a case, or type a request, and watch it pass through the pipeline the way
// the System Map draws it, with each stage's count in and out and its time. A typed request runs
// read only: it is routed on your Brain and recorded nowhere, so it counts as no request, in
// usage or in evals.

import { useEffect, useRef, useState, type FormEvent } from "react";

import { ErrorNote, Section } from "../../../components/ui";
import { useTtbCases, useTtbRuns, useWatch } from "./api";
import { FlowMap } from "./FlowMap";
import { Chip } from "./shared";
import type { State, WatchReply } from "./types";

export function Watch({ state, run, caseId }: { state: State; run?: string; caseId?: string }) {
  const runs = useTtbRuns();
  const latest = run ?? runs.data?.runs[0]?.run;
  const cases = useTtbCases(latest, {});
  const watch = useWatch();
  const [text, setText] = useState("");
  const [picked, setPicked] = useState(caseId ?? "");
  const [replay, setReplay] = useState(0);
  const started = useRef<string | null>(null);

  // Arriving from a case: watch it at once.
  useEffect(() => {
    if (run && caseId && started.current !== `${run}/${caseId}`) {
      started.current = `${run}/${caseId}`;
      setPicked(caseId);
      watch.mutate({ run, case: caseId });
    }
  }, [run, caseId, watch]);

  const onType = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    setReplay(0);
    watch.mutate({ request: text.trim() });
  };
  const onCase = () => {
    if (latest && picked) {
      setReplay(0);
      watch.mutate({ run: latest, case: picked });
    }
  };
  const drawn = watch.data;
  return (
    <>
      <Section title="What to watch">
        <form className="ttb-watch-form" onSubmit={onType}>
          <label className="field">
            <span className="field-label">Type a request</span>
            <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="For example: write a headline for the site" />
          </label>
          <button type="submit" className="primary" disabled={watch.isPending || !text.trim()}>
            Watch it work
          </button>
        </form>
        {cases.data?.cases.length ? (
          <div className="row">
            <label className="field">
              <span className="field-label">Or pick a case from the latest run</span>
              <select value={picked} onChange={(e) => setPicked(e.target.value)}>
                <option value="">Choose a case</option>
                {cases.data.cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title || c.id}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" disabled={!picked || watch.isPending} onClick={onCase}>
              Watch this case
            </button>
          </div>
        ) : null}
        <p className="muted small">
          Read only. {state.source === "lab" ? "A saved case is drawn from the Lab's own record." : "It is routed on a copy of your Brain's index."} Nothing is
          recorded, so it counts as no request in usage or evals. {" "}
          <Chip tone="neutral">marked as a test</Chip>
        </p>
        <ErrorNote error={watch.error} />
      </Section>
      {watch.isPending ? <p className="muted">Routing the request…</p> : null}
      {drawn ? <Drawn drawn={drawn} replay={replay} onReplay={() => setReplay((n) => n + 1)} /> : null}
    </>
  );
}

function Drawn({ drawn, replay, onReplay }: { drawn: WatchReply; replay: number; onReplay: () => void }) {
  return (
    <Section
      title={drawn.from_record ? "From the saved case" : "How the request went"}
      actions={
        <button type="button" className="link" onClick={onReplay}>
          Play it again
        </button>
      }
    >
      {drawn.request ? (
        <p className="ttb-request">
          <span className="muted small">The request</span>
          <br />“{drawn.request}”
        </p>
      ) : null}
      <FlowMap stages={drawn.stages} replay={replay} />
      <p className="muted small">
        {drawn.ms !== undefined ? `Routed in ${drawn.ms} ms. ` : ""}
        {drawn.tokens ? `The brief is ${drawn.tokens} tokens. ` : ""}
        {drawn.mode ? `Mode: ${drawn.mode}. ` : ""}
        {drawn.engine ? "Stages filled from the retrieval engine's own record." : ""}
      </p>
      {drawn.notes.length ? (
        <>
          <h4>What it gets</h4>
          <ul className="ttb-notes">
            {drawn.notes.map((n) => (
              <li key={`${n.id}:${n.outcome}`} className="ttb-note-row">
                <div className="row">
                  <strong>{n.title || n.id}</strong>
                  <Chip tone={n.outcome === "delivered" || n.outcome === "must hold" ? "done" : "neutral"}>{n.outcome}</Chip>
                  {n.label ? <Chip tone={n.label === "noise" ? "active" : n.label === "needed_missed" ? "blocked" : "ready"}>{n.label.replace(/_/g, " ")}</Chip> : null}
                </div>
                {n.why ? <p className="small muted">{n.why}</p> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </Section>
  );
}

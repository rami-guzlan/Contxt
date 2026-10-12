// Settings > Test the Brain: run the Brain's tests, watch them run, and see how the Brain is
// doing and how it works. Seven views. It reads one results contract, from a Lab the owner
// connected by folder or, with none, from the checks this app runs on its own Brain, and it
// writes nothing except starting and cancelling a run.

import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import { ErrorNote, Loading, Tabs } from "../../../components/ui";
import { useConnectLab, useDisconnectLab, useTtbState } from "./api";
import { Cases } from "./Cases";
import { Gates } from "./Gates";
import { History } from "./History";
import { OverviewView } from "./Overview";
import { RunView } from "./Run";
import { VIEWS, type Go, type View } from "./shared";
import { ThisComputer } from "./ThisComputer";
import type { State } from "./types";
import { Watch } from "./Watch";
import "./test-the-brain.css";

export function TestTheBrain() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("view") ?? "";
  const view: View = (VIEWS.find((v) => v.id === asked)?.id as View | undefined) ?? "overview";
  const { data: state, isLoading, error } = useTtbState();

  const go: Go = (next, extra = {}) => setParams({ tab: "test", view: next, ...extra });
  const detail = (key: string) => params.get(key) ?? undefined;

  if (isLoading) return <Loading />;
  if (!state) return <ErrorNote error={error} />;
  return (
    <div className="ttb">
      <p className="lede">
        Run your Brain's tests, watch them run, and see how it is doing and how it works. This page reads results and starts or cancels a
        run. It never approves, labels or changes anything in your Brain.
      </p>
      <Source state={state} />
      <div className="ttb-views">
        <Tabs tour="ttb-views" tabs={VIEWS} active={view} onChange={(next) => go(next)} />
      </div>
      {view === "overview" ? <OverviewView state={state} go={go} /> : null}
      {view === "run" ? <RunView state={state} go={go} /> : null}
      {view === "gates" ? <Gates go={go} /> : null}
      {view === "cases" ? <Cases state={state} go={go} run={detail("run")} caseId={detail("case")} gate={detail("gate")} /> : null}
      {view === "watch" ? <Watch state={state} run={detail("run")} caseId={detail("case")} /> : null}
      {view === "computer" ? <ThisComputer state={state} /> : null}
      {view === "history" ? <History go={go} a={detail("a")} b={detail("b")} /> : null}
    </div>
  );
}

function Source({ state }: { state: State }) {
  const connect = useConnectLab();
  const disconnect = useDisconnectLab();
  const [folder, setFolder] = useState("");
  const [asking, setAsking] = useState(false);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    connect.mutate(folder.trim(), {
      onSuccess: () => {
        setAsking(false);
        setFolder("");
      },
    });
  };
  const lab = state.lab;
  return (
    <section className="ttb-source" aria-label="Where the tests come from">
      {lab ? (
        <>
          <p>
            <strong>{lab.name ?? "A Lab"}</strong>
            <span className="muted small"> read from {lab.folder}</span>
          </p>
          <p className="muted small">
            Runs start in the Lab, with a short list of settings and none of this app's own. The Brain under test is the Lab's, never your own.
          </p>
          <div className="row">
            <button type="button" className="link" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              Disconnect this Lab
            </button>
          </div>
        </>
      ) : (
        <>
          <p>
            <strong>{state.builtin?.name ?? "Checks on your own Brain"}</strong>
            <span className="muted small"> no Lab connected</span>
          </p>
          <p className="muted small">
            These checks read a copy of your own Brain and change nothing in it. Have a test Lab? Point this page at its folder once, and it shows
            and runs everything the Lab has.
          </p>
          {asking ? (
            <form className="inline-form" onSubmit={onSubmit}>
              <label className="field">
                <span className="field-label">The Lab's folder</span>
                <input value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="The folder that holds lab.contract.json" required />
              </label>
              <button type="submit" className="primary" disabled={connect.isPending || !folder.trim()}>
                Connect
              </button>
              <button type="button" className="link" onClick={() => setAsking(false)}>
                Cancel
              </button>
            </form>
          ) : (
            <div className="row">
              <button type="button" onClick={() => setAsking(true)}>
                Connect a Lab
              </button>
            </div>
          )}
        </>
      )}
      <ErrorNote error={connect.error ?? disconnect.error} />
      {state.error ? (
        <p className="error" role="alert">
          {state.error} Fix the Lab's folder, or disconnect it to use the checks on your own Brain.
        </p>
      ) : null}
    </section>
  );
}

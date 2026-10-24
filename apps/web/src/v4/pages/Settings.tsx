// Settings (v4 slice 16): Your AI apps, Approval and auto-governance, On this computer, Test the
// Brain, Backups. Every value is read from the server; what a later phase brings stays visible
// and marked Later.

import { useState } from "react";
import { useSearchParams } from "react-router";

import {
  backupUrl,
  useAiApps,
  useBackups,
  useCheckRunners,
  useConnectApp,
  useDownloadModels,
  useDownloadSpeech,
  useLocalModels,
  useMakeBackup,
  useModels,
  useRunners,
  useSpeech,
} from "../../api/hooks";
import type { AiApp, RunnerStatus } from "../../api/types";
import { useForgetLearned, usePolicy, useSetPolicy, type Policy } from "../api";
import { HeartbeatSettings } from "../components/HeartbeatSettings";
import { css } from "../css";
import { useCancelTtb, useRunnerSignIn, useStartTtb, useTtbCases, useTtbGates, useTtbOverview, useTtbRuns, useTtbState, useTtbWatch, type TtbBar, type TtbRunKind } from "../hooks/agents";
import { Btn, Empty, Failure, Later, Loaded, Loading, Modal, S, Status, plural, when } from "../ui";
import { AskBrainFirst, TabRow } from "./Agents";

type Tab = "apps" | "approval" | "computer" | "test" | "backups";
const TABS: [Tab, string][] = [
  ["apps", "Your AI apps"],
  ["approval", "Approval and auto-governance"],
  ["computer", "On this computer"],
  ["test", "Test the Brain"],
  ["backups", "Backups"],
];
const SURFACE = "background:var(--surface);border-radius:20px;box-shadow:var(--shadow)";
const ROW = "display:flex;align-items:center;gap:14px;padding:13px 0;border:0;border-top:1px solid var(--line);background:transparent;text-align:left;color:var(--ink);width:100%;flex-wrap:wrap";
const PILL = (on: boolean) =>
  `padding:6px 13px;border-radius:99px;font:500 12.5px Geist;border:1px solid ${on ? "var(--ink)" : "var(--line2)"};background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink)"}`;
const OK = "font:500 13px Geist;color:oklch(0.5 0.12 150)";

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const found = params.get("tab") as Tab | null;
  const tab: Tab = TABS.some(([id]) => id === found) ? (found as Tab) : "apps";
  return (
    <div className="gn-page" style={css("max-width:1080px;margin:0 auto;padding:56px 64px 96px;display:flex;flex-direction:column;gap:44px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <h1 style={css(S.h1)}>Settings</h1>
      </div>
      <div style={css("margin-top:-22px")}>
        <TabRow value={tab} options={TABS} onChange={(id) => setParams(id === "apps" ? {} : { tab: id })} label="Settings" />
      </div>
      {tab === "apps" ? <Apps /> : null}
      {tab === "approval" ? <Approval /> : null}
      {tab === "computer" ? <Computer /> : null}
      {tab === "test" ? <TestTheBrain /> : null}
      {tab === "backups" ? <Backups /> : null}
    </div>
  );
}

function initials(label: string): string {
  return label
    .split(/[\s()]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

// ------------------------------------------------------------------ Your AI apps

function Apps() {
  const q = useAiApps();
  const connect = useConnectApp();
  const [asking, setAsking] = useState<AiApp | null>(null);
  const [copied, setCopied] = useState("");
  const copy = (key: string, text: string) => {
    void navigator.clipboard?.writeText(text).catch(() => undefined);
    setCopied(key);
    setTimeout(() => setCopied(""), 1600);
  };
  return (
    <div style={css("display:flex;flex-direction:column;gap:28px")}>
      <span style={css("font:400 17px Geist;color:var(--ink2)")}>Connect once. Every chat in that app has your Brain.</span>
      <Loaded q={q} empty={(list) => (list.length ? null : <Empty title="No AI apps found on this computer">Install Claude Code, Codex, Gemini CLI or Claude Desktop, then press Try again.</Empty>)}>
        {(list) => (
          <>
            <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px")}>
              {list.map((a) => {
                const status = a.connected ? "Connected" : a.found ? "Found · not connected yet" : "Not found on this computer";
                const cmd = a.setup?.command ?? a.setup?.config ?? "";
                return (
                  <div key={a.client + a.label} style={css(`${SURFACE};padding:20px;display:flex;flex-direction:column;gap:14px`)}>
                    <div style={css("display:flex;align-items:center;gap:12px")}>
                      <span aria-hidden style={css("width:40px;height:40px;border-radius:12px;background:var(--soft);font:500 11px Geist;color:var(--ink2);display:flex;align-items:center;justify-content:center")}>
                        {initials(a.label)}
                      </span>
                      <div style={css("display:flex;flex-direction:column")}>
                        <span style={css("font:500 15px Geist")}>{a.label}</span>
                        <span style={css(a.connected ? "font:400 13px Geist;color:oklch(0.5 0.12 150)" : "font:400 13px Geist;color:var(--muted)")}>{status}</span>
                      </div>
                    </div>
                    {!a.connected && a.setup && cmd ? (
                      <div style={css("display:flex;flex-direction:column;gap:8px")}>
                        <span style={css("font:400 13px Geist;color:var(--ink2)")}>{a.setup.command ? "Paste this in a terminal, once:" : `Add this to ${a.setup.file ?? "its settings file"}:`}</span>
                        <div style={css("display:flex;align-items:flex-start;gap:8px;padding:10px 12px;border-radius:12px;background:var(--code)")}>
                          <span style={css("font:400 12px 'Geist Mono';color:#eeece6;flex:1;white-space:pre-wrap;word-break:break-all")}>{cmd}</span>
                          <button type="button" onClick={() => copy(a.client, cmd)} style={css("font:500 12px Geist;color:#fff;padding:4px 10px;border-radius:99px;background:#3a3935;border:0")}>
                            {copied === a.client ? "Copied" : "Copy"}
                          </button>
                        </div>
                        {a.setup.note ? <span style={css(S.small)}>{a.setup.note}</span> : null}
                        <div style={css("display:flex;gap:12px;flex-wrap:wrap")}>
                          <button type="button" onClick={() => void q.refetch()} style={css("border:0;background:transparent;padding:2px 0;font:500 13px Geist;color:var(--ink)")}>
                            I ran it →
                          </button>
                          {a.found && a.client !== "other" ? (
                            <button type="button" onClick={() => setAsking(a)} style={css("border:0;background:transparent;padding:2px 0;font:500 13px Geist;color:var(--ink2)")}>
                              Connect it for me
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                    {!a.connected && !a.setup && a.client !== "other" ? <span style={css(S.small)}>Set up a Brain first (contxt setup), then connect this app.</span> : null}
                  </div>
                );
              })}
            </div>
            <div style={css("display:flex;flex-direction:column")}>
              <span style={css("font:500 15px Geist;margin-bottom:8px")}>The last request from each</span>
              {list.filter((a) => a.last_request).length === 0 ? (
                <span style={css(S.muted)}>No app has asked your Brain anything yet.</span>
              ) : (
                list
                  .filter((a) => a.last_request)
                  .map((a) => (
                    <div key={a.client + a.label} style={css(ROW)}>
                      <span style={css("font:500 14px Geist;width:150px")}>{a.label}</span>
                      <span style={css("font:400 15px Geist;flex:1;color:var(--ink2);min-width:200px")}>{a.last_request?.request}</span>
                      <span style={css(S.muted)}>{when(a.last_request?.at)}</span>
                    </div>
                  ))
              )}
              <div style={css("display:flex;gap:8px;padding-top:14px;flex-wrap:wrap")}>
                <Btn kind="ghostSm" disabled title="Not available yet">
                  Send a test request
                </Btn>
                <Btn kind="ghostSm" disabled title="Not available yet">
                  Remove an app
                </Btn>
                <span style={css("align-self:center;font:400 12px Geist;color:var(--muted)")}>Not available here yet: remove the Brain from an app in that app's own settings.</span>
              </div>
            </div>
          </>
        )}
      </Loaded>
      <Runners />
      <AskBrainFirst />
      {asking ? (
        <Modal title={`Connect ${asking.label}?`} eyebrow="YOUR AI APPS" onClose={() => setAsking(null)}>
          <span style={css("font:400 14px/1.55 Geist;color:var(--ink2)")}>
            This adds your Brain to {asking.label}'s own settings{asking.setup?.file ? ` (${asking.setup.file})` : ""}. The settings file is copied beside itself first, so you can put it back.
          </span>
          {connect.data ? (
            <>
              <Status kind={connect.data.connected ? "searchable" : "failed"}>{connect.data.connected ? "Connected" : "Not connected"}</Status>
              {connect.data.backup ? <span style={css(S.small)}>The earlier settings were kept at {connect.data.backup}.</span> : null}
              <Btn kind="ghostSm" onClick={() => setAsking(null)}>
                Close
              </Btn>
            </>
          ) : (
            <div style={css("display:flex;gap:8px")}>
              <Btn kind="primarySm" disabled={connect.isPending} onClick={() => connect.mutate(asking.client)}>
                {connect.isPending ? "Connecting…" : "Yes, connect it"}
              </Btn>
              <Btn kind="ghostSm" onClick={() => setAsking(null)}>
                Cancel
              </Btn>
            </div>
          )}
          {connect.error ? <Failure error={connect.error} /> : null}
        </Modal>
      ) : null}
    </div>
  );
}

function runnerState(r: RunnerStatus): { st: string; ok: boolean } {
  if (!r.installed) return { st: "Not installed", ok: false };
  if (r.signed_in === false) return { st: "Signed out", ok: false };
  if (r.signed_in === null) return { st: "Installed · sign-in unknown", ok: true };
  return { st: "● Ready", ok: true };
}

/** The AI CLIs on this computer: installed, signed in, and a way to sign in. */
function Runners({ title = "The app's own AI work" }: { title?: string }) {
  const q = useRunners();
  const check = useCheckRunners();
  const signIn = useRunnerSignIn();
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <div style={css("display:flex;flex-direction:column;gap:6px")}>
      <span style={css("font:500 15px Geist")}>{title}</span>
      <span style={css("font:400 14px Geist;color:var(--ink2);margin-bottom:8px")}>Summaries, the knowledge agent and runs go through an AI CLI on this computer. It keeps its own sign-in.</span>
      <Loaded q={q} empty={(list) => (list.length ? null : <Empty title="No AI CLIs known">The server lists none.</Empty>)}>
        {(list) =>
          list.map((r) => {
            const { st, ok } = runnerState(r);
            return (
              <div key={r.id} style={css(ROW)}>
                <span style={css("font:400 15px Geist;width:260px")}>{r.label} on this computer</span>
                <span style={css("font:400 14px Geist;color:var(--ink2);flex:1;min-width:200px")}>
                  {r.installed ? [r.version, r.detail].filter(Boolean).join(" · ") || "Installed" : r.install ? `Install: ${r.install}` : r.detail || "Not found"}
                </span>
                <span style={css(ok ? OK : "font:500 13px Geist;color:var(--ink)")}>{st}</span>
                {r.installed && r.signed_in === false ? (
                  <Btn kind="ghostSm" disabled={signIn.isPending} onClick={() => signIn.mutate(r.id)}>
                    Sign in
                  </Btn>
                ) : null}
              </div>
            );
          })
        }
      </Loaded>
      {signIn.data ? (
        <span style={css(S.small)}>
          {signIn.data.opened ? "A terminal opened: sign in there, then press Check again." : `Couldn't open a terminal. Run ${signIn.data.command} in one, then press Check again.`}
        </span>
      ) : null}
      {signIn.error ? <Failure error={signIn.error} /> : null}
      {error ? <Failure error={error} /> : null}
      <Btn
        kind="ghostSm"
        style="align-self:flex-start;margin-top:8px"
        disabled={checking}
        onClick={() => {
          setChecking(true);
          setError(null);
          check()
            .catch((e: unknown) => setError(e))
            .finally(() => setChecking(false));
        }}
      >
        {checking ? "Checking…" : "Check again"}
      </Btn>
    </div>
  );
}

// ------------------------------------------------------------------ Approval and auto-governance

const PRESET: Record<string, [string, string]> = {
  personal: ["Personal", "Only new rules and conflicts wait. Facts go straight in, with undo."],
  careful: ["Careful", "Everything your AI picks up waits for you."],
  regulated: ["Regulated", "Everything waits, and every change is signed and logged."],
};
const RETRIEVAL: Record<string, [string, string]> = {
  relaxed: ["Relaxed", "Sends more: a weaker match still goes to your AI. Fewer misses, more to read."],
  standard: ["Standard", "The measured default for your Brain."],
  careful: ["Careful", "Sends less: a match has to be stronger, and it says “nothing found” more often."],
};
const ORIGIN: Record<string, string> = { app: "From you, in the app", chat: "From an AI chat", folder: "From a folder (Scout)" };
const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

function Approval() {
  const q = usePolicy();
  return <Loaded q={q}>{(p) => <ApprovalBody policy={p} />}</Loaded>;
}

function ApprovalBody({ policy }: { policy: Policy }) {
  const set = useSetPolicy();
  const forget = useForgetLearned();
  const [adv, setAdv] = useState(false);
  const [capText, setCapText] = useState(String(policy.auto_daily_cap));
  const [add, setAdd] = useState({ type: policy.capture_types[0] ?? "", origin: policy.capture_origins[0] ?? "", area: "*" });
  const capture = (policy.capture ?? {}) as Record<string, Record<string, string>>;
  const standing = policy.standing ?? [];
  const change = (changes: Partial<Policy>) => set.mutate(changes);
  const capNum = Number(capText);
  const capOk = Number.isInteger(capNum) && capNum >= 0 && capNum <= 1000;
  return (
    <div style={css("display:flex;flex-direction:column;gap:28px")}>
      <div style={css(`${SURFACE};padding:26px;display:flex;flex-direction:column;gap:18px`)}>
        <div style={css("display:flex;flex-direction:column;gap:6px")}>
          <span style={css("font:400 28px Newsreader")}>Auto-governance</span>
          <span style={css("font:500 12.5px Geist;color:var(--muted)")}>
            {plural(policy.auto_applied_today, "change")} applied by itself today · pauses itself at {policy.auto_daily_cap} a day
          </span>
          <span style={css("font:400 15px/1.55 Geist;color:var(--ink2);max-width:600px")}>
            Let what you trust go straight in. Each standing permission below covers one kind of piece from one place, in one area or all of them. You see everything it applied, with undo, instead of saying yes first.
          </span>
        </div>
        <div role="radiogroup" aria-label="How this Brain is governed" style={css("display:flex;gap:8px;flex-wrap:wrap;align-items:center")}>
          {(
            [
              ["governed", "Governed", "Suggestions wait in Catch up for your yes."],
              ["auto", "Auto", "Trusted pieces go in by themselves, with undo, capped and pausable."],
            ] as const
          ).map(([id, label, hint]) => (
            <button
              key={id}
              role="radio"
              aria-checked={policy.mode === id}
              disabled={set.isPending}
              onClick={() => change({ mode: id })}
              style={css(
                `display:flex;flex-direction:column;gap:2px;text-align:left;padding:12px 16px;border-radius:14px;color:var(--ink);${
                  policy.mode === id ? "background:var(--soft);border:1.5px solid var(--ink)" : "background:transparent;border:1px solid var(--line2)"
                }`,
              )}
            >
              <span style={css("font:500 14px Geist")}>{label}</span>
              <span style={css("font:400 12px Geist;color:var(--muted)")}>{hint}</span>
            </button>
          ))}
          {policy.mode === "auto" ? (
            <Btn kind="ghostSm" disabled={set.isPending} onClick={() => change({ auto_paused: !policy.auto_paused })}>
              {policy.auto_paused ? "Resume Auto" : "Pause Auto"}
            </Btn>
          ) : null}
          {policy.mode === "auto" && policy.auto_paused ? <Status kind="disputed">Paused by you: everything waits</Status> : null}
        </div>
        {policy.mode === "auto" ? <HeartbeatSettings /> : null}
        <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px")}>
          {[
            ["Rules from a chat or folder still wait", "What changes how every AI behaves never goes in from a chat or a folder by itself."],
            ["Every change has an undo", "Applied changes show in Activity with an undo point."],
            [`Pauses itself at ${policy.auto_daily_cap} changes a day`, "After that, everything waits for you until tomorrow."],
          ].map(([t, d]) => (
            <div key={t} style={css("padding:14px 16px;border-radius:14px;background:var(--soft);display:flex;flex-direction:column;gap:3px")}>
              <span style={css("font:500 13px Geist")}>{t}</span>
              <span style={css("font:400 12px/1.45 Geist;color:var(--ink2)")}>{d}</span>
            </div>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (capOk) change({ auto_daily_cap: capNum });
          }}
          style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}
        >
          <label style={css("display:flex;align-items:center;gap:8px;font:400 14px Geist")}>
            Daily cap
            <input aria-label="Daily cap" inputMode="numeric" value={capText} onChange={(e) => setCapText(e.target.value)} style={css(`${S.input};width:72px;padding:6px 10px;text-align:center`)} />
            changes a day
          </label>
          <Btn kind="ghostSm" type="submit" disabled={set.isPending || !capOk || capNum === policy.auto_daily_cap}>
            Save
          </Btn>
          {!capOk ? <span style={css(S.small)}>A whole number from 0 to 1000.</span> : null}
        </form>
        <div style={css("display:flex;flex-direction:column")}>
          <span style={css("font:500 12px Geist;color:var(--muted);padding-bottom:6px")}>Standing permissions</span>
          {standing.length === 0 ? <span style={css(S.muted)}>None yet. Everything follows the table below.</span> : null}
          {standing.map((r, i) => (
            <div key={`${r.type}-${r.origin}-${r.area}`} style={css("display:flex;align-items:center;gap:10px;padding:10px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
              <span style={css(`font:400 14px Geist;flex:1;min-width:220px;${r.paused ? "color:var(--muted)" : ""}`)}>
                {cap(r.type)} · {ORIGIN[r.origin] ?? r.origin} · {r.area === "*" || !r.area ? "any area" : r.area}
              </span>
              {r.paused ? <Status kind="excluded">Paused</Status> : <Status kind="searchable">Goes straight in</Status>}
              <Btn kind="ghostSm" disabled={set.isPending} onClick={() => change({ standing: standing.map((x, j) => (j === i ? { ...x, paused: !x.paused } : x)) })}>
                {r.paused ? "Resume" : "Pause"}
              </Btn>
              <Btn kind="link" disabled={set.isPending} onClick={() => change({ standing: standing.filter((_, j) => j !== i) })}>
                Remove
              </Btn>
            </div>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (add.type && add.origin) change({ standing: [...standing, { ...add, paused: false }] });
            }}
            style={css("display:flex;gap:8px;align-items:center;padding-top:10px;border-top:1px solid var(--line);flex-wrap:wrap")}
          >
            <span style={css("font:400 13px Geist;color:var(--ink2)")}>Let in</span>
            <select aria-label="Kind" value={add.type} onChange={(e) => setAdd({ ...add, type: e.target.value })} style={css(`${S.input};padding:6px 10px;font-size:13px`)}>
              {policy.capture_types.map((t) => (
                <option key={t} value={t}>
                  {cap(t)}
                </option>
              ))}
            </select>
            <select aria-label="From" value={add.origin} onChange={(e) => setAdd({ ...add, origin: e.target.value })} style={css(`${S.input};padding:6px 10px;font-size:13px`)}>
              {policy.capture_origins.map((o) => (
                <option key={o} value={o}>
                  {ORIGIN[o] ?? o}
                </option>
              ))}
            </select>
            <select aria-label="Area" value={add.area} onChange={(e) => setAdd({ ...add, area: e.target.value })} style={css(`${S.input};padding:6px 10px;font-size:13px`)}>
              <option value="*">Any area</option>
              {policy.areas.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <Btn kind="ghostSm" type="submit" disabled={set.isPending || !add.type || !add.origin}>
              Add
            </Btn>
          </form>
        </div>
      </div>
      <div style={css("display:flex;flex-direction:column;gap:14px")}>
        <span style={css("font:500 15px Geist")}>What waits for your yes?</span>
        <div role="radiogroup" aria-label="What waits for your yes" style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px")}>
          {policy.presets.map((id) => {
            const on = policy.preset === id;
            const [name, desc] = PRESET[id] ?? [cap(id), ""];
            return (
              <button
                key={id}
                role="radio"
                aria-checked={on}
                disabled={set.isPending}
                onClick={() => change({ preset: id })}
                style={css(
                  `padding:18px;border-radius:18px;display:flex;flex-direction:column;gap:6px;text-align:left;border:0;${on ? "background:var(--ink);color:var(--bg)" : "background:var(--surface);color:var(--ink);box-shadow:var(--shadow)"}`,
                )}
              >
                <span style={css("font:500 15px Geist")}>{name}</span>
                <span style={css("font:400 13px/1.45 Geist;opacity:.75")}>{desc}</span>
              </button>
            );
          })}
        </div>
        <span style={css(S.small)}>Choosing a preset starts the table below fresh from it.</span>
        <button type="button" aria-expanded={adv} onClick={() => setAdv(!adv)} style={css("align-self:flex-start;border:0;background:transparent;padding:6px 0;font:500 13px Geist;color:var(--ink2)")}>
          {adv ? "Hide the details" : "Show the details, by kind and where it came from"}
        </button>
        {adv ? (
          <div style={css(`${SURFACE};padding:4px 22px;overflow-x:auto`)}>
            <div style={css("display:flex;padding:12px 0;font:500 12px Geist;color:var(--muted);min-width:520px")}>
              <span style={css("flex:1.3")}>Kind</span>
              {policy.capture_origins.map((o) => (
                <span key={o} style={css("flex:1")}>
                  {ORIGIN[o] ?? o}
                </span>
              ))}
            </div>
            {Object.keys(capture).length === 0 ? <span style={css(S.muted)}>The server returned no table.</span> : null}
            {Object.entries(capture).map(([kind, origins]) => (
              <div key={kind} style={css("display:flex;align-items:center;border-top:1px solid var(--line);min-width:520px")}>
                <span style={css("flex:1.3;font:400 15px Geist")}>{cap(kind)}</span>
                {policy.capture_origins.map((o) => {
                  const v = origins[o] ?? "wait";
                  return (
                    <span key={o} style={css("flex:1;padding:8px 0")}>
                      <button
                        type="button"
                        aria-label={`${cap(kind)} ${ORIGIN[o] ?? o}: ${v === "wait" ? "waits" : "goes in"}`}
                        disabled={set.isPending}
                        onClick={() => change({ capture: { ...capture, [kind]: { ...origins, [o]: v === "wait" ? "apply" : "wait" } } } as Partial<Policy>)}
                        style={css(`border:0;background:transparent;padding:4px 0;font:400 13px Geist;color:${v === "wait" ? "oklch(0.58 0.13 35)" : "var(--ink2)"}`)}
                      >
                        {v === "wait" ? "Waits" : "Goes in"}
                      </button>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <div style={css("display:flex;flex-direction:column;gap:12px")}>
        <span style={css("font:500 15px Geist")}>How much it sends your AI</span>
        <div role="radiogroup" aria-label="How much it sends your AI" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
          {policy.retrieval_policies.map((id) => (
            <button key={id} role="radio" aria-checked={policy.retrieval_policy === id} disabled={set.isPending} onClick={() => change({ retrieval_policy: id as Policy["retrieval_policy"] })} style={css(PILL(policy.retrieval_policy === id))}>
              {RETRIEVAL[id]?.[0] ?? cap(id)}
            </button>
          ))}
        </div>
        {policy.retrieval_policies.map((id) => (
          <span key={id} style={css(`font:400 13.5px/1.5 Geist;color:${policy.retrieval_policy === id ? "var(--ink)" : "var(--muted)"}`)}>
            <b style={css("font-weight:500")}>{RETRIEVAL[id]?.[0] ?? cap(id)}:</b> {RETRIEVAL[id]?.[1] ?? ""}
          </span>
        ))}
      </div>
      <div style={css("display:flex;flex-direction:column")}>
        <span style={css("font:500 15px Geist;margin-bottom:4px")}>Learned from your undos</span>
        <span style={css("font:400 13px Geist;color:var(--muted);margin-bottom:8px")}>Rules it made from changes you took back. Forget one and it stops applying.</span>
        {policy.learned.length === 0 ? <span style={css(S.muted)}>Nothing learned yet.</span> : null}
        {policy.learned.map((r) => (
          <div key={r.id} style={css(ROW)}>
            <div style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
              <span style={css("font:400 15px Geist")}>{r.says}</span>
              <span style={css(S.small)}>
                {[cap(r.type), ORIGIN[r.origin] ?? r.origin, r.area, when(r.at)].filter(Boolean).join(" · ")}
              </span>
            </div>
            <Btn kind="ghostSm" disabled={forget.isPending} onClick={() => forget.mutate(r.id)}>
              Forget
            </Btn>
          </div>
        ))}
        {forget.error ? <Failure error={forget.error} /> : null}
      </div>
      {set.error ? <Failure error={set.error} /> : null}
      {set.isPending ? <Loading what="Saving" /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ On this computer

function Computer() {
  const models = useModels();
  const speech = useSpeech();
  const local = useLocalModels();
  const getModel = useDownloadModels();
  const getSpeech = useDownloadSpeech();
  const [asking, setAsking] = useState<"matching" | "speech" | null>(null);
  const m = models.data?.matching;
  const s = speech.data;
  return (
    <div style={css("display:flex;flex-direction:column;gap:32px")}>
      <div style={css("display:flex;flex-direction:column;gap:6px")}>
        <span style={css("font:500 15px Geist;margin-bottom:8px")}>Local models</span>
        <div style={css(ROW)}>
          <span style={css("font:400 15px Geist;width:260px")}>Matching by meaning</span>
          <span style={css("font:400 14px Geist;color:var(--ink2);flex:1;min-width:200px")}>
            {models.isLoading
              ? "Checking…"
              : m?.present
                ? `Local model${m.model ? `, ${m.model}` : ""}${m.about_mb ? `, ${m.about_mb} MB` : ""}`
                : `Not on this computer. Search matches exact words only, with lower recall: paraphrases can be missed. Its quality is reported separately.${m?.about_mb ? ` About ${m.about_mb} MB, once.` : ""}`}
          </span>
          {models.error ? <Failure error={models.error} retry={() => void models.refetch()} /> : null}
          {m?.present ? <span style={css(OK)}>● On</span> : m?.downloading ? <Status kind="indexing">Downloading…</Status> : m ? <Status kind="partial">Words-only search</Status> : null}
          {m && !m.present && !m.downloading ? (
            <Btn kind="ghostSm" onClick={() => setAsking("matching")}>
              Download
            </Btn>
          ) : null}
        </div>
        {m?.error ? <span style={css(S.small)}>The last download stopped: {m.error}</span> : null}
        <div style={css(ROW)}>
          <span style={css("font:400 15px Geist;width:260px")}>Speech to text</span>
          <span style={css("font:400 14px Geist;color:var(--ink2);flex:1;min-width:200px")}>
            {speech.isLoading ? "Checking…" : s?.present ? `Local model, ${s.model}${s.about_mb ? `, ${s.about_mb} MB` : ""}` : `Not on this computer. Recordings can't be turned into text here.${s?.about_mb ? ` About ${s.about_mb} MB, once.` : ""}`}
          </span>
          {speech.error ? <Failure error={speech.error} retry={() => void speech.refetch()} /> : null}
          {s?.present && s.ready ? <span style={css(OK)}>● On</span> : s?.downloading ? <Status kind="indexing">Downloading…</Status> : s?.present ? <Status kind="partial">Present · not ready</Status> : s ? <Status kind="captured">Off</Status> : null}
          {s && !s.present && !s.downloading ? (
            <Btn kind="ghostSm" onClick={() => setAsking("speech")}>
              Download
            </Btn>
          ) : null}
        </div>
        {s?.error ? <span style={css(S.small)}>The last download stopped: {s.error}</span> : null}
        <span style={css("font:400 13px Geist;color:var(--muted);padding-top:8px")}>Local models and a GPU are optional. Nothing in this release needs one.</span>
      </div>
      <div style={css("display:flex;flex-direction:column;gap:6px")}>
        <span style={css("font:500 15px Geist;margin-bottom:8px")}>This computer</span>
        <Loaded q={local}>
          {(d) => (
            <>
              <div style={css(ROW)}>
                <span style={css("font:400 15px Geist;width:260px")}>Machine</span>
                <span style={css("font:400 14px Geist;color:var(--ink2);flex:1")}>
                  {d.machine ? [d.machine.system, `${d.machine.ram_gb} GB memory`, d.machine.gpu ? `${d.machine.gpu}${d.machine.gpu_gb ? `, ${d.machine.gpu_gb} GB` : ""}` : "no GPU found"].join(" · ") : "Not read yet"}
                </span>
                <span style={css(S.muted)}>{d.setup_label ?? ""}</span>
              </div>
              {(d.roles ?? []).map((r) => (
                <div key={r.role} style={css(ROW)}>
                  <span style={css("font:400 15px Geist;width:260px")}>{r.label}</span>
                  <span style={css("font:400 14px Geist;color:var(--ink2);flex:1")}>{r.model ?? "None set · optional"}</span>
                </div>
              ))}
              {d.engine ? (
                <div style={css(ROW)}>
                  <span style={css("font:400 15px Geist;width:260px")}>Retrieval engine</span>
                  <span style={css("font:400 14px Geist;color:var(--ink2);flex:1")}>{d.engine.ready ? "Runs in full here" : `Falls back: ${d.engine.reason}`}</span>
                </div>
              ) : null}
            </>
          )}
        </Loaded>
      </div>
      <Runners />
      <span style={css("font:400 13px Geist;color:var(--muted)")}>
        The app runs at {window.location.host || "this computer"}. Your chosen AI provider receives what each job or request sends; every receipt shows exactly what.
      </span>
      {asking ? (
        <Modal title={asking === "matching" ? "Download the meaning model?" : "Download the speech model?"} eyebrow="ON THIS COMPUTER" onClose={() => setAsking(null)}>
          <span style={css("font:400 14px/1.55 Geist;color:var(--ink2)")}>
            {asking === "matching"
              ? `About ${m?.about_mb ?? "70"} MB, fetched once. Then search matches by meaning on this computer, not only by exact words.`
              : `About ${s?.about_mb ?? "480"} MB, fetched once. Then recordings turn into text on this computer.`}
          </span>
          <div style={css("display:flex;gap:8px")}>
            <Btn
              kind="primarySm"
              disabled={getModel.isPending || getSpeech.isPending}
              onClick={() => (asking === "matching" ? getModel : getSpeech).mutate(undefined, { onSuccess: () => setAsking(null) })}
            >
              Yes, download it
            </Btn>
            <Btn kind="ghostSm" onClick={() => setAsking(null)}>
              Cancel
            </Btn>
          </div>
          {getModel.error ? <Failure error={getModel.error} /> : null}
          {getSpeech.error ? <Failure error={getSpeech.error} /> : null}
        </Modal>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ Test the Brain

type TestTab = "overview" | "run" | "gates" | "cases" | "watch" | "history";
const TEST_TABS: [TestTab, string][] = [
  ["overview", "Overview"],
  ["run", "Run"],
  ["gates", "Gates"],
  ["cases", "Cases"],
  ["watch", "Watch it work"],
  ["history", "History"],
];

function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "not measured";
  return Number.isInteger(v) ? String(v) : v.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function bar(b: TtbBar | null): string {
  return b ? `bar ${b.op} ${num(b.value)}` : "no bar";
}

function TestTheBrain() {
  const [tab, setTab] = useState<TestTab>("overview");
  const state = useTtbState();
  const cancel = useCancelTtb();
  const running = state.data?.running;
  return (
    <div style={css("display:flex;flex-direction:column;gap:22px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap")}>
        <TabRow value={tab} options={TEST_TABS} onChange={setTab} label="Test the Brain" />
        {running ? (
          <div style={css("display:flex;align-items:center;gap:10px")}>
            <span role="status" style={css("font:400 14px Geist;color:var(--ink2)")}>
              Running {running.kind ?? ""}… {running.message}
            </span>
            {running.run ? (
              <Btn kind="ghostSm" disabled={cancel.isPending} onClick={() => cancel.mutate(running.run ?? "")}>
                Cancel
              </Btn>
            ) : null}
          </div>
        ) : null}
      </div>
      {state.error ? <Failure error={state.error} retry={() => void state.refetch()} /> : null}
      {state.data?.error ? <Failure error={new Error(state.data.error)} /> : null}
      {cancel.error ? <Failure error={cancel.error} /> : null}
      {tab === "overview" ? <TestOverview /> : null}
      {tab === "run" ? <TestRun kinds={state.data?.status?.run_kinds} busy={Boolean(running)} loading={state.isLoading} /> : null}
      {tab === "gates" ? <TestGates /> : null}
      {tab === "cases" ? <TestCases /> : null}
      {tab === "watch" ? <TestWatch /> : null}
      {tab === "history" ? <TestHistory /> : null}
      {state.data?.builtin?.waits.length ? (
        <div style={css("display:flex;flex-direction:column")}>
          <span style={css("font:500 13px Geist;color:var(--muted);padding-bottom:6px")}>What waits</span>
          {state.data.builtin.waits.map((w) => (
            <div key={w.suite} style={css(ROW)}>
              <span style={css("font:400 14px Geist;flex:1")}>{w.suite}</span>
              <span style={css(S.muted)}>{w.note || w.state}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function TestOverview() {
  const q = useTtbOverview();
  return (
    <Loaded q={q}>
      {(o) => (
        <div style={css("display:flex;flex-direction:column;gap:18px")}>
          <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>
            Is the Brain helping? Each pillar is measured against your own cases. {o.last ? `Last run ${when(o.last.ended)}${o.last.valid ? "" : ", not valid"}.` : "Nothing has run yet: start a check under Run."}
          </span>
          {o.pillars.length === 0 ? (
            <Empty title="No pillars measured yet">Run a check under Run; its results show here.</Empty>
          ) : (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px")}>
              {o.pillars.map((p) => (
                <div key={p.id} style={css(`${SURFACE};padding:20px;display:flex;flex-direction:column;gap:8px`)}>
                  <span style={css("font:400 15px Geist")}>{p.name}</span>
                  <span style={css("font:400 26px Newsreader")}>{p.headline ? num(p.headline.value) : "Not measured"}</span>
                  <span style={css(S.small)}>{p.headline ? `${p.headline.name} · ${bar(p.headline.bar)}` : "No gate measured yet"}</span>
                  <span style={css(S.small)}>
                    {p.met} of {plural(p.total, "gate")} met · {p.measured} measured
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Loaded>
  );
}

function TestRun({ kinds, busy, loading }: { kinds: TtbRunKind[] | undefined; busy: boolean; loading: boolean }) {
  const start = useStartTtb();
  const [confirm, setConfirm] = useState<TtbRunKind | null>(null);
  if (loading) return <Loading />;
  if (!kinds || kinds.length === 0) return <Empty title="No checks listed">This workspace lists no checks to run. Set up a Brain first (contxt setup).</Empty>;
  return (
    <div style={css("display:flex;flex-direction:column")}>
      {kinds.map((k) => (
        <div key={k.id} style={css(ROW)}>
          <div style={css("flex:1;min-width:240px;display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:400 15px Geist")}>{k.name}</span>
            <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{k.covers}</span>
            <span style={css(S.small)}>
              {k.paid ? "Uses your Claude Code plan" : "Free, on this computer"}
              {k.last?.at ? ` · last run ${when(k.last.at)}` : ""}
            </span>
          </div>
          <Btn kind="primarySm" disabled={busy || start.isPending} onClick={() => (k.paid ? setConfirm(k) : start.mutate({ kind: k.id }))}>
            Run
          </Btn>
        </div>
      ))}
      {start.error ? <Failure error={start.error} /> : null}
      {confirm ? (
        <Modal title={`Run ${confirm.name}?`} eyebrow="TEST THE BRAIN" onClose={() => setConfirm(null)}>
          <span style={css("font:400 14px/1.55 Geist;color:var(--ink2)")}>
            It uses your Claude Code plan
            {confirm.estimate?.calls ? `: about ${plural(confirm.estimate.calls, "call")}` : ""}
            {confirm.estimate?.seconds ? `, around ${Math.round(confirm.estimate.seconds / 60)} min` : ""}.
          </span>
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" disabled={start.isPending} onClick={() => start.mutate({ kind: confirm.id, confirm: true }, { onSuccess: () => setConfirm(null) })}>
              Yes, run it
            </Btn>
            <Btn kind="ghostSm" onClick={() => setConfirm(null)}>
              Cancel
            </Btn>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function TestGates() {
  const q = useTtbGates();
  return (
    <Loaded q={q} empty={(d) => (d.gates.length ? null : <Empty title="No gates yet">Gates appear once a check has run.</Empty>)}>
      {(d) => (
        <div style={css("display:flex;flex-direction:column")}>
          {d.gates.map((g) => (
            <div key={g.id} style={css(ROW)}>
              <span style={css("font:400 15px Geist;flex:1;min-width:200px")}>{g.name}</span>
              <span style={css(S.muted)}>
                {num(g.value)} · {bar(g.bar)}
                {g.n ? ` · ${g.n} cases` : ""}
              </span>
              <Status kind={g.met === true ? "confirmed" : g.met === false ? "failed" : "captured"}>{g.met === true ? "Met" : g.met === false ? "Not met" : "Not measured"}</Status>
            </div>
          ))}
        </div>
      )}
    </Loaded>
  );
}

function TestCases() {
  const o = useTtbOverview();
  const run = o.data?.last?.run;
  const q = useTtbCases(run);
  if (o.isLoading) return <Loading />;
  if (o.error) return <Failure error={o.error} retry={() => void o.refetch()} />;
  if (!run) return <Empty title="No run yet">Run a check under Run; its cases show here.</Empty>;
  return (
    <Loaded q={q} empty={(d) => (d.cases.length ? null : <Empty title="No cases in the last run">The last run kept no cases.</Empty>)}>
      {(d) => (
        <div style={css("display:flex;flex-direction:column")}>
          <span style={css(S.muted)}>
            The last run, {run}: {plural(d.total, "case")}.
          </span>
          {d.cases.map((c) => (
            <div key={c.id} style={css(ROW)}>
              <span style={css("font:400 15px Geist;flex:1;min-width:200px")}>{c.sensitive ? "A private case (its words aren't shown)" : c.title}</span>
              <span style={css("font:400 13px Geist;color:var(--muted);width:200px")}>{c.suite}</span>
              <Status kind={c.pass === true ? "confirmed" : c.pass === false ? "failed" : "captured"}>{c.pass === true ? "Pass" : c.pass === false ? "Fail" : "Not scored"}</Status>
            </div>
          ))}
        </div>
      )}
    </Loaded>
  );
}

function TestWatch() {
  const watch = useTtbWatch();
  const [text, setText] = useState("");
  const d = watch.data;
  return (
    <div style={css("display:flex;flex-direction:column;gap:14px")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) watch.mutate(text.trim());
        }}
        style={css(`${SURFACE};padding:22px;display:flex;flex-direction:column;gap:12px`)}
      >
        <span style={css("font:500 15px Geist")}>Watch one request go through your Brain</span>
        <div style={css("display:flex;gap:8px")}>
          <input aria-label="A request" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a request you'd give your AI" style={css(`${S.input};flex:1;min-width:0`)} />
          <Btn kind="primarySm" type="submit" disabled={watch.isPending || !text.trim()}>
            {watch.isPending ? "Routing…" : "Run"}
          </Btn>
        </div>
        <span style={css(S.small)}>Read only: it routes the request on this app's Brain and records nothing.</span>
      </form>
      {watch.error ? <Failure error={watch.error} /> : null}
      {d ? (
        <div style={css(`${SURFACE};padding:22px;display:flex;flex-direction:column;gap:4px`)}>
          <span style={css("font:400 20px Newsreader;padding-bottom:10px")}>“{d.request}”, step by step</span>
          {d.stages.map((s, i) => (
            <div key={s.id} style={css(ROW)}>
              <span style={css("font:500 13px 'Geist Mono';width:24px")}>{i + 1}</span>
              <span style={css("flex:1;font:400 15px Geist;min-width:160px")}>{s.name}</span>
              <span style={css(S.muted)}>
                {s.in !== null && s.out !== null ? `${s.in} → ${s.out}` : s.state}
                {s.note ? ` · ${s.note}` : ""}
              </span>
            </div>
          ))}
          {d.tokens ? <span style={css(S.small)}>{d.tokens} tokens in the brief.</span> : null}
          {d.notes.length ? (
            <div style={css("display:flex;flex-direction:column;padding-top:10px")}>
              <span style={css("font:500 13px Geist;color:var(--muted)")}>Notes it considered</span>
              {d.notes.map((n) => (
                <div key={n.id} style={css(ROW)}>
                  <span style={css("font:400 14px Geist;flex:1")}>{n.title}</span>
                  <span style={css(S.muted)}>
                    {n.outcome}
                    {n.why ? ` · ${n.why}` : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function TestHistory() {
  const q = useTtbRuns();
  return (
    <Loaded q={q} empty={(d) => (d.runs.length ? null : <Empty title="No runs yet">Run a check under Run; each run is kept here.</Empty>)}>
      {(d) => (
        <div style={css("display:flex;flex-direction:column")}>
          {d.runs.map((r) => (
            <div key={r.run} style={css(ROW)}>
              <span style={css("font:400 15px Geist;flex:1;min-width:200px")}>
                {when(r.ended ?? r.started)} · {r.kind}
              </span>
              <span style={css("font:400 14px Geist;color:var(--ink2)")}>
                {r.valid ? `${plural(r.metrics, "measure")} · ${r.failing} failing` : `Not valid${r.note ? `: ${r.note}` : ""}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </Loaded>
  );
}

// ------------------------------------------------------------------ Backups

function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} bytes`;
}

function Backups() {
  const q = useBackups();
  const make = useMakeBackup();
  return (
    <div style={css("display:flex;flex-direction:column;gap:18px")}>
      <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
        <Btn kind="primary" disabled={make.isPending} onClick={() => make.mutate()}>
          {make.isPending ? "Backing up…" : "Back up now"}
        </Btn>
      </div>
      {make.data ? (
        <span role="status" style={css("font:400 14px Geist;color:var(--ink2)")}>
          Backed up: {make.data.name}, {size(make.data.size)} · {plural(make.data.records, "record")}, {plural(make.data.files, "stored file")}, {plural(make.data.brain_files, "Brain file")}.
        </span>
      ) : null}
      {make.error ? <Failure error={make.error} /> : null}
      <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>Every change is also in git. Push your Brain to a private remote for a copy off this computer.</span>
      <Loaded q={q} empty={(list) => (list.length ? null : <Empty title="No backups yet">Press Back up now to make the first one.</Empty>)}>
        {(list) => (
          <div style={css("display:flex;flex-direction:column")}>
            {list.map((b) => (
              <div key={b.name} style={css(ROW)}>
                <span style={css("font:400 15px Geist;width:200px")}>{when(b.at)}</span>
                <span style={css("font:400 14px Geist;color:var(--ink2);flex:1;min-width:200px")}>
                  {b.name} · {size(b.size)}
                </span>
                <a href={backupUrl(b.name)} download style={css("padding:7px 14px;border-radius:99px;background:var(--soft);border:0;font:500 13px Geist;color:var(--ink);text-decoration:none")}>
                  Download
                </a>
              </div>
            ))}
          </div>
        )}
      </Loaded>
      <span style={css(S.small)}>
        Restoring stays a command, so nothing is overwritten by a click: stop the app and run <code>contxt restore</code> with the backup's file.
        <Later />
      </span>
    </div>
  );
}


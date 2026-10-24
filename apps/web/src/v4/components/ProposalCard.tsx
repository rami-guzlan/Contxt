// One proposed piece, as v4 draws it in Capture and Catch up: its id, what it does, its status,
// where it would go, the source (version, passage, speaker, when it applies), the source's own
// words, and Keep, Edit first or Skip. The same proposal record everywhere: deciding it here
// decides it in every view.

import { useState } from "react";

import { useBrainProjects, useLive } from "../../api/hooks";
import { type Proposal, useDecide, usePolicy, useUndo } from "../api";
import { css } from "../css";
import { Btn, Modal, S, Status } from "../ui";

const STATEMENT: Record<string, string> = {
  stated: "Stated in source",
  tentative: "Tentative · as said",
  conditional: "Conditional",
  confirmed: "Confirmed",
  disputed: "Disputed · waits for you",
};

export const HOMES: [string, string][] = [
  ["note", "Long-term memory"],
  ["kept", "Kept with a project"],
  ["sheet", "Context sheets"],
  ["progress", "Project progress"],
  ["task", "To-do in a project"],
  ["taste", "Taste profile"],
];

function speaker(p: Proposal): string {
  return p.source?.speaker && p.source.speaker !== "unknown" ? p.source.speaker : "Unknown";
}

export interface CardOutcome {
  id: string;
  kept: boolean;
  checkpoint?: string;
}

/** A proposal to decide. `onDone` hears the outcome, so a list can show Undo in its place. */
export function ProposalCard({ p, onDone, onBrain }: { p: Proposal; onDone?: (o: CardOutcome) => void; onBrain?: () => void }) {
  const decide = useDecide();
  const undo = useUndo();
  const [editing, setEditing] = useState(false);
  const [done, setDone] = useState<CardOutcome | null>(null);
  const after = p.body?.trim() || p.summary || p.title;
  const conflict = Boolean(p.conflicts) || p.statement_status === "disputed";

  function act(keep: boolean, extra: { body?: string; destination?: Record<string, string> } = {}) {
    decide.mutate([{ action: keep ? "approve" : "reject", proposal_id: p.id, ...extra }], {
      onSuccess: (r) => {
        const result = r.results[0];
        if (!result?.ok) return;
        const outcome = { id: p.id, kept: keep, checkpoint: r.checkpoint?.id };
        setDone(outcome);
        setEditing(false);
        onDone?.(outcome);
      },
    });
  }

  return (
    <article aria-label={`Proposal ${p.id}`} style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:20px 22px;display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
        <span style={css("font:500 12px 'Geist Mono'")}>{p.id}</span>
        <span style={css("padding:2px 9px;border-radius:6px;background:var(--soft);font:500 12px Geist")}>{p.operation}</span>
        {done ? (
          <Status kind={done.kept ? "indexing" : "skipped"}>{done.kept ? "Kept · indexing, not searchable yet" : "Skipped · not kept"}</Status>
        ) : (
          <Status kind={conflict ? "disputed" : "review"}>{conflict ? "Needs your decision" : "Awaiting review"}</Status>
        )}
        <span style={css("font:400 12px Geist;color:var(--muted);margin-left:auto")}>destination {p.destination || p.route_key}</span>
      </div>
      {p.target?.kind === "lesson" ? (
        <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
          <span style={css("width:10px;height:10px;border-radius:3px;background:oklch(0.66 0.1 185);flex:none")} />
          <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.05em;color:var(--ink2);flex:1")}>PROPOSED LESSON · NOT APPROVED YET</span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>Level if kept: kept, not verified</span>
        </div>
      ) : null}
      <button
        onClick={onBrain}
        disabled={!onBrain}
        title={onBrain ? "See where it lands on your Brain" : undefined}
        className="gn-hover"
        style={css("padding:14px 16px;border-radius:14px;border:1.5px dashed oklch(0.68 0.14 35);background:transparent;display:flex;flex-direction:column;gap:4px;text-align:left;color:var(--ink)")}
      >
        <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--ink2)")}>PROPOSED · NOT APPROVED YET</span>
        <span style={css("font:400 20px/1.35 Newsreader")}>{after}</span>
        {p.current_body ? (
          <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>
            Current · approved: <span style={css("text-decoration:line-through")}>{p.current_body.slice(0, 220)}</span>
          </span>
        ) : null}
        {onBrain ? <span style={css("font:400 12.5px Geist;color:var(--ink2)")}>See it on your Brain →</span> : null}
      </button>
      <dl style={css("margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:10px 18px;padding:12px 0 0;border-top:1px solid var(--line)")}>
        {[
          ["Source · version", p.source ? `${p.source.id}${p.source.version ? ` · ${p.source.version}` : ""}` : "No source recorded"],
          ["Passage", p.source?.locator || "Exact location unavailable"],
          ["Speaker", speaker(p)],
          ["Effective", p.effective || "Not stated"],
          ["Said as", STATEMENT[p.statement_status] ?? (p.statement_status || "Stated in source")],
        ].map(([k, v]) => (
          <div key={k} style={css("display:flex;flex-direction:column;gap:2px")}>
            <dt style={css("font:500 11.5px Geist;color:var(--muted)")}>{k}</dt>
            <dd style={css("margin:0;font:400 13.5px Geist;word-break:break-word")}>{v}</dd>
          </div>
        ))}
      </dl>
      {p.source?.excerpt ? (
        <blockquote style={css("margin:0;padding:10px 14px;border-radius:12px;background:var(--soft);font:400 15px/1.5 Newsreader")}>{p.source.excerpt}</blockquote>
      ) : null}
      {conflict && !done ? (
        <span style={css("font:400 12.5px/1.5 Geist;color:var(--ink2)")}>
          It says otherwise than what your Brain holds{p.conflicts ? ` (${p.conflicts})` : ""}. Nothing replaces the current record until you pick: older
          information imported later never overwrites it.
        </span>
      ) : null}
      {done ? (
        <div role="status" style={css("display:flex;gap:10px;align-items:center;padding:12px 14px;border-radius:14px;background:var(--soft);flex-wrap:wrap")}>
          <span style={css("font:400 13.5px/1.5 Geist;flex:1;min-width:220px")}>
            {done.kept
              ? "Kept. Keeping stores it; it doesn't verify it, and the original speaker stays. Indexing, not searchable yet."
              : "Skipped. Nothing in your Brain changed."}
          </span>
          {done.checkpoint ? (
            <button
              onClick={() => undo.mutate(done.checkpoint as string, { onSuccess: () => setDone(null) })}
              style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink)")}
            >
              Undo
            </button>
          ) : null}
        </div>
      ) : (
        <>
          <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
            <Btn kind="primarySm" onClick={() => act(true)} disabled={decide.isPending}>
              Keep
            </Btn>
            <Btn kind="ghostSm" onClick={() => setEditing(true)} disabled={decide.isPending}>
              Edit first
            </Btn>
            <Btn kind="ghostSm" onClick={() => act(false)} disabled={decide.isPending}>
              Skip
            </Btn>
          </div>
          <span style={css("font:400 12.5px/1.5 Geist;color:var(--ink2)")}>Keeping stores it. It doesn't make it true, and the speaker stays the speaker.</span>
          {decide.error ? <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>{(decide.error as Error).message}</span> : null}
        </>
      )}
      {editing ? <EditBeforeKeep p={p} onClose={() => setEditing(false)} onSave={(extra) => act(true, extra)} busy={decide.isPending} /> : null}
    </article>
  );
}

/** "Say it your way": the words, and where it goes (Goes to … › … · …). The original stays in
 * its history; what's kept is the owner's version. */
export function EditBeforeKeep({
  p,
  onClose,
  onSave,
  busy,
}: {
  p: Proposal;
  onClose: () => void;
  onSave: (extra: { body?: string; destination?: Record<string, string> }) => void;
  busy?: boolean;
}) {
  const policy = usePolicy();
  const projects = useBrainProjects();
  const live = useLive();
  const [text, setText] = useState(p.body?.trim() || p.summary || "");
  const [home, setHome] = useState("note");
  const [fields, setFields] = useState<Record<string, string>>({});
  const set = (k: string, v: string) => setFields((f) => ({ ...f, [k]: v }));
  const select = (k: string, label: string, options: [string, string][]) => (
    <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
      {label}
      <select value={fields[k] ?? ""} onChange={(e) => set(k, e.target.value)} style={css(S.input + ";font:500 13px Geist;padding:6px 8px")}>
        <option value="">Choose…</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
  const textField = (k: string, label: string) => (
    <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
      {label}
      <input value={fields[k] ?? ""} onChange={(e) => set(k, e.target.value)} style={css(S.input + ";font:400 13px Geist;padding:6px 8px")} />
    </label>
  );
  const projectOptions: [string, string][] = (projects.data ?? []).map((x) => [x.id, x.title]);
  const moved = home !== "note" || Object.values(fields).some(Boolean);

  function save() {
    const words = text.trim();
    const extra: { body?: string; destination?: Record<string, string> } = {};
    if (words && words !== (p.body?.trim() || "")) extra.body = words;
    if (moved) extra.destination = { destination: home, ...Object.fromEntries(Object.entries(fields).filter(([, v]) => v)) };
    onSave(extra);
  }

  return (
    <Modal title="Say it your way" eyebrow="EDIT BEFORE IT'S KEPT" onClose={onClose}>
      <div style={css("display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end")}>
        <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
          Goes to
          <select value={home} onChange={(e) => (setHome(e.target.value), setFields({}))} style={css(S.input + ";font:500 13px Geist;padding:6px 8px")}>
            {HOMES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        {home === "note" ? select("area", "Area", (policy.data?.areas ?? []).map((a) => [a, a])) : null}
        {home === "note"
          ? select("kind", "Kind", [
              ["fact", "Fact"],
              ["preference", "Preference"],
              ["rule", "Rule"],
              ["decision", "Decision"],
            ])
          : null}
        {["kept", "progress", "task"].includes(home) ? select("project", "Project", projectOptions) : null}
        {home === "kept"
          ? select("group", "Group", [
              ["facts", "Facts"],
              ["preferences", "Preferences"],
              ["rules", "Rules"],
            ])
          : null}
        {home === "sheet" ? select("sheet", "Sheet", (live.data?.sheets ?? []).map((s) => [s.id, s.title])) : null}
        {home === "sheet" ? textField("row", "Row") : null}
        {home === "sheet" ? textField("column", "Column") : null}
        {home === "task" ? textField("due", "Due") : null}
        {home === "taste"
          ? select("lens", "Lens", [
              ["looks", "Looks good"],
              ["feels", "Feels good"],
              ["works", "Works good"],
            ])
          : null}
        {home === "taste"
          ? select("kind", "Kind", [
              ["principle", "Principle"],
              ["avoid", "Words to avoid"],
              ["use", "Words to use"],
            ])
          : null}
      </div>
      <label htmlFor={`draft-${p.id}`} style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em")}>
        YOUR DRAFT · NOT SAVED
      </label>
      <textarea
        id={`draft-${p.id}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        style={css("border:1px solid var(--line2);border-radius:14px;padding:12px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 16px/1.55 Geist;resize:vertical")}
      />
      <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>One idea, in a sentence that stands on its own. The original stays in its history.</span>
      <div style={css("display:flex;justify-content:flex-end;gap:8px")}>
        <Btn kind="ghost" onClick={onClose}>
          Cancel
        </Btn>
        <Btn kind="primary" onClick={save} disabled={busy || !text.trim()}>
          Keep my edited version
        </Btn>
      </div>
    </Modal>
  );
}

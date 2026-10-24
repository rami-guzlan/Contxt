// The evidence receipt of one request, as v4 draws it under an answer: collapsed until opened,
// then what was sent (with tokens and how they were counted), what was opened in full, what
// didn't fit, what was already delivered in this conversation, and what's unknown. Built from
// the stored receipt, so it equals the delivery and never changes. Corrections only propose.

import { useState } from "react";

import { CORRECTIONS, type Receipt as ReceiptData, type ReceiptItem, useCorrect, useReceipt } from "../api";
import { css } from "../css";
import { RECEIPT_OPENED_KEY } from "../hooks/home";
import { Btn, Failure, Loading, S } from "../ui";

function items(rows: ReceiptItem[], key: (r: ReceiptItem) => string) {
  return rows.map((r) => ({ t: r.title || r.id, k: key(r) }));
}

function sections(r: ReceiptData) {
  return [
    {
      l: "Sent",
      n: `${r.sent.length} · ${r.tokens.packet.toLocaleString()} tokens`,
      items: items(r.sent, (x) => [x.form, x.tokens ? `${x.tokens} tok` : ""].filter(Boolean).join(" · ") || x.id),
    },
    {
      l: "Opened by the AI after the packet",
      n: r.pull_budget?.items ? `${r.opened.length} of ${r.pull_budget.items}` : String(r.opened.length),
      items: [
        ...r.opened.map((x) => ({ t: x.address ?? x.title ?? x.id, k: x.tokens ? `${x.tokens.toLocaleString()} tok` : "" })),
        ...(r.refused ?? []).map((x) => ({ t: `${x.address} · ${x.says}`, k: x.status === "over_pull_budget" ? "named only" : "not found" })),
      ],
      foot: r.pull_budget?.items
        ? `Pull budget: ${r.opened.length} of ${r.pull_budget.items} used, about ${r.pull_budget.used_tokens.toLocaleString()} of ${(r.pull_budget.tokens ?? 0).toLocaleString()} tokens. Pulls past the budget are named, not opened.`
        : "",
    },
    { l: "Didn't fit", n: String(r.did_not_fit.length), items: items(r.did_not_fit, (x) => x.why ?? "named, not sent") },
    { l: "Already delivered this session", n: String(r.already_delivered.length), items: items(r.already_delivered, (x) => x.id) },
    { l: "Unknown", n: String(r.unknown.length), items: r.unknown.map((u) => ({ t: u, k: "" })) },
  ];
}

/** Home's quick start counts a receipt opened (a per-viewer convenience). */
function markOpened() {
  try {
    window.localStorage.setItem(RECEIPT_OPENED_KEY, new Date().toISOString());
  } catch {
    // storage blocked: the quick start step can still be marked by hand
  }
}

export function ReceiptView({ id, defaultOpen = false }: { id: string; defaultOpen?: boolean }) {
  const q = useReceipt(id);
  const [open, setOpen] = useState(defaultOpen);
  const [correcting, setCorrecting] = useState(false);
  const r = q.data;
  const summary = r
    ? `${r.sent.length} sent · ${r.opened.length} opened · ${r.did_not_fit.length} didn't fit · ${r.tokens.total.toLocaleString()} tokens`
    : "";
  return (
    <div style={css("display:flex;flex-direction:column;border-radius:18px;border:1px solid var(--line);background:var(--surface)")}>
      <button
        onClick={() => {
          if (!open) markOpened();
          setOpen((v) => !v);
        }}
        aria-expanded={open}
        style={css("display:flex;align-items:center;gap:10px;padding:12px 18px;border:0;background:transparent;color:var(--ink);text-align:left;flex-wrap:wrap")}
      >
        <span style={css("font:500 13.5px Geist;flex:1;min-width:160px")}>
          Evidence receipt <span style={css("font:400 12px 'Geist Mono';color:var(--muted)")}>{id}</span>
        </span>
        <span style={css("font:400 12.5px Geist;color:var(--muted)")}>{summary}</span>
        <span aria-hidden="true" style={css("font:400 12px Geist;color:var(--muted)")}>
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open ? (
        <div style={css("display:flex;flex-direction:column;padding:0 18px 14px")}>
          {q.isLoading ? <Loading what="Reading the receipt" /> : null}
          {q.error ? <Failure error={q.error} retry={() => void q.refetch()} /> : null}
          {r ? (
            <>
              <div style={css("display:flex;flex-wrap:wrap;gap:6px 14px;padding:4px 0 10px;font:400 12px Geist;color:var(--muted)")}>
                <span>Scope: {r.scope.join(" › ") || "this Brain"}</span>
                {r.partition ? <span>Partition: {r.partition}</span> : null}
                <span>Tokens counted: {r.tokens.counted}</span>
                {r.tokens.budget ? <span>Budget: {r.tokens.budget.toLocaleString()}</span> : null}
              </div>
              {sections(r).map((s) => (
                <div key={s.l} style={css("display:flex;flex-direction:column;gap:6px;padding:12px 0;border-top:1px solid var(--line)")}>
                  <div style={css("display:flex;justify-content:space-between;gap:10px")}>
                    <span style={css("font:500 13px Geist")}>{s.l}</span>
                    <span style={css("font:400 12px Geist;color:var(--muted)")}>{s.n}</span>
                  </div>
                  {s.items.length === 0 ? <span style={css("font:400 13px Geist;color:var(--faint)")}>None</span> : null}
                  {s.items.map((x, i) => (
                    <div key={`${x.t}-${i}`} style={css("display:flex;gap:10px;font:400 13px/1.45 Geist;color:var(--ink2)")}>
                      <span style={css("flex:1")}>{x.t}</span>
                      <span style={css("font:400 11.5px 'Geist Mono';color:var(--muted);white-space:nowrap")}>{x.k}</span>
                    </div>
                  ))}
                  {"foot" in s && s.foot ? <span style={css("font:400 12px/1.45 Geist;color:var(--muted)")}>{s.foot}</span> : null}
                </div>
              ))}
              <details style={css("padding:10px 0;border-top:1px solid var(--line)")}>
                <summary style={css("font:500 13px Geist;cursor:pointer")}>The exact text it was handed</summary>
                <pre style={css("margin:8px 0 0;padding:12px 14px;border-radius:12px;background:var(--soft);font:400 11.5px/1.6 'Geist Mono';color:var(--ink2);white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto")}>
                  {r.text}
                </pre>
              </details>
              <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 0;border-top:1px solid var(--line)")}>
                <Btn kind="ghostSm" onClick={() => setCorrecting((v) => !v)}>
                  Something's wrong with this
                </Btn>
              </div>
              {correcting ? <Correct receipt={r} onDone={() => setCorrecting(false)} /> : null}
              <span style={css("font:400 12px/1.5 Geist;color:var(--muted);padding-top:10px;border-top:1px solid var(--line)")}>
                A receipt lists what was delivered. It isn't proof that nothing relevant was missed, and a named note or match score isn't a completeness check.
              </span>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Correct({ receipt, onDone }: { receipt: ReceiptData; onDone: () => void }) {
  const correct = useCorrect();
  const [kind, setKind] = useState("outdated");
  const [item, setItem] = useState("");
  const [note, setNote] = useState("");
  const options = [...receipt.sent, ...receipt.did_not_fit, ...receipt.opened];
  return (
    <div style={css("display:flex;flex-direction:column;gap:8px;padding:12px 14px;border-radius:14px;background:var(--soft)")}>
      <span style={css("font:500 13px Geist")}>What went wrong?</span>
      <div style={css(S.wrap)}>
        {CORRECTIONS.map(([k, l]) => (
          <button
            key={k}
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
            style={css(
              `padding:6px 12px;border-radius:99px;font:${kind === k ? 500 : 400} 12.5px Geist;${
                kind === k ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:var(--surface);color:var(--ink);border:1px solid var(--line2)"
              }`,
            )}
          >
            {l}
          </button>
        ))}
      </div>
      {options.length ? (
        <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
          Which item
          <select value={item} onChange={(e) => setItem(e.target.value)} style={css(S.input + ";font:400 13px Geist;padding:6px 8px")}>
            <option value="">None in particular</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title || o.id}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <textarea
        aria-label="What should it have been"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        placeholder="What should it have been? (optional)"
        style={css(S.input + ";font:400 14px Geist;resize:vertical")}
      />
      <span style={css("font:400 12px/1.5 Geist;color:var(--ink2)")}>
        A correction only proposes: a wrong or outdated item gets a "Still true?" card in Catch up. Nothing in your Brain changes until you decide.
      </span>
      <div style={css("display:flex;gap:8px")}>
        <Btn kind="primarySm" disabled={correct.isPending} onClick={() => correct.mutate({ id: receipt.id, kind, item, note }, { onSuccess: onDone })}>
          Send correction
        </Btn>
        <Btn kind="ghostSm" onClick={onDone}>
          Cancel
        </Btn>
      </div>
      {correct.error ? <Failure error={correct.error} /> : null}
    </div>
  );
}

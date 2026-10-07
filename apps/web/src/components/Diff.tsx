// Two versions of a text side by side, the words that differ marked: what is in the Brain now
// beside what a proposal would put there, or a doc beside a change suggested for it.

export interface Piece {
  text: string;
  kind: "same" | "added" | "removed";
}

const LIMIT = 1200; // pieces in the changed part of each side; past it, whole lines are compared

function words(text: string): string[] {
  return text.match(/\s+|[^\s]+/g) ?? [];
}

function lines(text: string): string[] {
  return text.match(/[^\n]*\n|[^\n]+/g) ?? [];
}

/** The difference from `before` to `after`, in reading order: word by word, or line by line
 * where a long text changed in many places. What both share at the start and the end is set
 * aside first, so a small change in a long doc is still marked word by word. */
export function diffWords(before: string, after: string): Piece[] {
  const out: Piece[] = [];
  const push = (text: string, kind: Piece["kind"]) => {
    if (!text) return;
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ text, kind });
  };
  const a = words(before);
  const b = words(after);
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let end = 0;
  while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end++;
  push(a.slice(0, start).join(""), "same");
  const midA = a.slice(start, a.length - end);
  const midB = b.slice(start, b.length - end);
  if (midA.length <= LIMIT && midB.length <= LIMIT) common(midA, midB, push);
  else {
    const la = lines(midA.join(""));
    const lb = lines(midB.join(""));
    if (la.length <= LIMIT && lb.length <= LIMIT) common(la, lb, push);
    else {
      push(midA.join(""), "removed");
      push(midB.join(""), "added");
    }
  }
  push(a.slice(a.length - end).join(""), "same");
  return out;
}

/** Walk two lists of pieces along their longest common subsequence. */
function common(a: string[], b: string[], push: (text: string, kind: Piece["kind"]) => void) {
  // The table is filled from the end, so the walk below reads forwards.
  const width = b.length + 1;
  const table = new Uint16Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i * width + j] =
        a[i] === b[j]
          ? (table[(i + 1) * width + j + 1] ?? 0) + 1
          : Math.max(table[(i + 1) * width + j] ?? 0, table[i * width + j + 1] ?? 0);
    }
  }
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(a[i] ?? "", "same");
      i++;
      j++;
    } else if ((table[(i + 1) * width + j] ?? 0) >= (table[i * width + j + 1] ?? 0)) {
      push(a[i] ?? "", "removed");
      i++;
    } else {
      push(b[j] ?? "", "added");
      j++;
    }
  }
  while (i < a.length) push(a[i++] ?? "", "removed");
  while (j < b.length) push(b[j++] ?? "", "added");
}

const FOLD_FROM = 6000; // characters across both sides past which unchanged stretches fold
const KEEP_LINES = 3; // lines of an unchanged stretch kept at each end when it folds

/** An unchanged stretch with its middle left out: the lines around a change stay readable. */
export function folded(text: string): string {
  const parts = text.split("\n");
  if (parts.length <= KEEP_LINES * 2 + 2) return text;
  const hidden = parts.length - KEEP_LINES * 2;
  return [...parts.slice(0, KEEP_LINES), `… ${hidden} unchanged lines …`, ...parts.slice(-KEEP_LINES)].join("\n");
}

export interface Side {
  label: string;
  title: string;
  body: string;
  note?: string;
}

/** How much of two texts is shared, 0 to 1: the words both keep, over the longer text. */
export function shared(pieces: Piece[], before: string, after: string): number {
  const same = pieces.filter((p) => p.kind === "same").reduce((n, p) => n + p.text.length, 0);
  return same / Math.max(before.length, after.length, 1);
}

/** Before and after, side by side: removed words struck on the left, added ones marked on
 * the right. Marks help only when one text rewrites the other; two notes written apart (a
 * near repeat, a contradiction) share too little, so they simply sit side by side. */
export function Compare({ before, after, marks = true }: { before: Side; after: Side; marks?: boolean }) {
  const diff = marks ? diffWords(before.body, after.body) : null;
  const pieces = diff && shared(diff, before.body, after.body) >= 0.5 ? diff : null;
  // In a long text (a skill, a long document) a small change is easy to miss among what stays:
  // long unchanged stretches are folded to their first and last lines.
  const fold = before.body.length + after.body.length > FOLD_FROM;
  const same = (text: string, index: number) => <span key={index}>{fold ? folded(text) : text}</span>;
  return (
    <div className="compare">
      <section className="compare-side before" aria-label={before.label}>
        <p className="compare-label">{before.label}</p>
        <h4>{before.title}</h4>
        <p className="compare-text">
          {pieces
            ? pieces
                .filter((p) => p.kind !== "added")
                .map((p, index) => (p.kind === "removed" ? <del key={index}>{p.text}</del> : same(p.text, index)))
            : before.body}
        </p>
        {before.note ? <p className="compare-note">{before.note}</p> : null}
      </section>
      <span className="compare-arrow" aria-hidden="true">
        →
      </span>
      <section className="compare-side after" aria-label={after.label}>
        <p className="compare-label">{after.label}</p>
        <h4>{after.title}</h4>
        <p className="compare-text">
          {pieces
            ? pieces
                .filter((p) => p.kind !== "removed")
                .map((p, index) => (p.kind === "added" ? <ins key={index}>{p.text}</ins> : same(p.text, index)))
            : after.body}
        </p>
        {after.note ? <p className="compare-note">{after.note}</p> : null}
      </section>
    </div>
  );
}

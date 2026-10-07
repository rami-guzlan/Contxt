// First-visit tips: one short line on the four pages a new person meets (Home, Capture, Brain,
// Skills), shown once and gone with "Got it". The first run teaches by doing; the Help menu has
// the rest. What was seen is kept in this browser only.

import { Lightbulb } from "lucide-react";
import { useState, type ReactNode } from "react";

const PREFIX = "contxt-tip-";

function seen(id: string): boolean {
  try {
    return window.localStorage.getItem(PREFIX + id) === "seen";
  } catch {
    return true; // no storage (a private window): no tips rather than the same tip forever
  }
}

/** Forget every tip seen, so each shows again (the Help menu offers this). */
export function resetTips(): void {
  try {
    for (const key of Object.keys(window.localStorage)) if (key.startsWith(PREFIX)) window.localStorage.removeItem(key);
  } catch {
    // nothing to forget
  }
}

export function FirstVisitTip({ id, children }: { id: string; children: ReactNode }) {
  const [shown, setShown] = useState(() => !seen(id));
  if (!shown) return null;
  return (
    <aside className="tip" role="note" aria-label="Tip">
      <Lightbulb className="button-icon" aria-hidden="true" />
      <p>{children}</p>
      <button
        type="button"
        className="link"
        onClick={() => {
          try {
            window.localStorage.setItem(PREFIX + id, "seen");
          } catch {
            // shown again next time; nothing breaks
          }
          setShown(false);
        }}
      >
        Got it
      </button>
    </aside>
  );
}

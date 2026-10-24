// The v4 design (docs/dev/plans/release1-plan.md) writes its styles inline as CSS text, the
// same way everywhere. `css("display:flex;gap:6px")` turns that text into a React style, so
// each screen keeps the design's exact values. Parsed once per distinct string.

import type { CSSProperties } from "react";

const cache = new Map<string, CSSProperties>();

function camel(name: string): string {
  if (name.startsWith("--")) return name; // a custom property stays as written
  return name.replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase());
}

/** A style object from CSS declarations ("a:b;c:d"). Later declarations win. */
export function css(text: string): CSSProperties {
  const kept = cache.get(text);
  if (kept) return kept;
  const out: Record<string, string> = {};
  // Split on semicolons outside parentheses (oklch(... / .2), url(...)).
  let depth = 0;
  let start = 0;
  const parts: string[] = [];
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === "(") depth += 1;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    else if (ch === ";" && depth === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(text.slice(start));
  for (const part of parts) {
    const at = part.indexOf(":");
    if (at <= 0) continue;
    const name = part.slice(0, at).trim();
    const value = part.slice(at + 1).trim();
    if (name && value) out[camel(name)] = value;
  }
  const style = out as CSSProperties;
  if (cache.size > 4000) cache.clear();
  cache.set(text, style);
  return style;
}

/** Several style texts, joined (the later wins), skipping empty ones. */
export function cx(...texts: (string | false | null | undefined)[]): CSSProperties {
  return css(texts.filter(Boolean).join(";"));
}

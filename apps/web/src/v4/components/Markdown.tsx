// A small, safe Markdown renderer. It builds React elements, never HTML strings, so nothing in
// a note, reference or skill can inject markup into the page, and links are kept only when
// they point at the web or at an email address. It covers what the Brain's files use:
// headings, paragraphs, lists, quotes, fenced code, tables, rules, emphasis and links.

import type { ReactNode } from "react";

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "rule" };

const HEADING = /^(#{1,6})\s+(.*)$/;
const RULE = /^(-{3,}|\*{3,}|_{3,})$/;
const BULLET = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
const TABLE_RULE = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/;

function cells(row: string): string[] {
  return row
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function startsBlock(line: string, next: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed.startsWith("```") ||
    HEADING.test(trimmed) ||
    RULE.test(trimmed) ||
    trimmed.startsWith(">") ||
    BULLET.test(line) ||
    (trimmed.startsWith("|") && TABLE_RULE.test(next.trim()))
  );
}

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const at = (index: number) => lines[index] ?? "";
  const blocks: Block[] = [];
  let i = 0;
  if (at(0).trim() === "---") {
    // Front matter (a skill's fields, say) is metadata, not prose.
    const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
    if (end > 0) i = end + 1;
  }
  while (i < lines.length) {
    const line = at(i);
    const trimmed = line.trim();
    if (!trimmed) {
      i++;
      continue;
    }
    if (trimmed.startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !at(i).trim().startsWith("```")) body.push(at(i++));
      i++;
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    const heading = HEADING.exec(trimmed);
    if (heading) {
      const text = (heading[2] ?? "").replace(/\s+#+\s*$/, "");
      blocks.push({ kind: "heading", level: (heading[1] ?? "#").length, text });
      i++;
      continue;
    }
    if (RULE.test(trimmed)) {
      blocks.push({ kind: "rule" });
      i++;
      continue;
    }
    if (trimmed.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && at(i).trim().startsWith(">")) body.push(at(i++).trim().replace(/^>\s?/, ""));
      blocks.push({ kind: "quote", text: body.join(" ") });
      continue;
    }
    if (trimmed.startsWith("|") && TABLE_RULE.test(at(i + 1).trim())) {
      const head = cells(trimmed);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && at(i).trim().startsWith("|")) rows.push(cells(at(i++).trim()));
      blocks.push({ kind: "table", head, rows });
      continue;
    }
    if (BULLET.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items: string[] = [];
      while (i < lines.length) {
        const match = BULLET.exec(at(i));
        if (match) {
          items.push(match[2] ?? "");
          i++;
        } else if (items.length && at(i).trim() && /^\s{2,}/.test(at(i))) {
          items[items.length - 1] += ` ${at(i++).trim()}`;
        } else {
          break;
        }
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    const body = [trimmed];
    i++;
    while (i < lines.length && at(i).trim() && !startsBlock(at(i), at(i + 1))) body.push(at(i++).trim());
    blocks.push({ kind: "paragraph", text: body.join(" ") });
  }
  return blocks;
}

// Code spans, strong, emphasis (underscores only at word edges, so note_budget stays plain),
// [text](url) links, and bare web addresses.
const INLINE =
  /(`[^`]+`)|(\*\*[^*]+\*\*|(?<![A-Za-z0-9])__[^_]+__(?![A-Za-z0-9]))|(\*[^*\s][^*]*\*|(?<![A-Za-z0-9])_[^_\s][^_]*_(?![A-Za-z0-9]))|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s)<>]+[^\s)<>.,;:!?'"])/;

function safeHref(url: string): string | null {
  return /^(https?:\/\/|mailto:)/i.test(url) ? url : null;
}

export function inline(text: string, prefix = "i"): ReactNode[] {
  const out: ReactNode[] = [];
  let rest = text;
  let n = 0;
  while (rest) {
    const match = INLINE.exec(rest);
    if (!match) {
      out.push(rest);
      break;
    }
    if (match.index > 0) out.push(rest.slice(0, match.index));
    const token = match[0];
    const key = `${prefix}-${n++}`;
    if (match[1]) {
      out.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (match[2]) {
      out.push(<strong key={key}>{inline(token.slice(2, -2), key)}</strong>);
    } else if (match[3]) {
      out.push(<em key={key}>{inline(token.slice(1, -1), key)}</em>);
    } else if (match[4]) {
      const [, label, url] = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token) ?? [];
      const href = safeHref(url ?? "");
      out.push(
        href ? (
          <a key={key} href={href} target="_blank" rel="noreferrer noopener">
            {inline(label ?? "", key)}
          </a>
        ) : (
          <span key={key}>{label}</span>
        ),
      );
    } else {
      out.push(
        <a key={key} href={token} target="_blank" rel="noreferrer noopener">
          {token}
        </a>,
      );
    }
    rest = rest.slice(match.index + token.length);
  }
  return out;
}

function renderBlock(block: Block, key: number): ReactNode {
  switch (block.kind) {
    case "heading": {
      const Tag = `h${Math.min(block.level + 1, 6)}` as "h2";
      // The page owns the h1; a document's own headings sit one level below it.
      return block.level === 1 ? (
        <h1 key={key}>{inline(block.text, `h${key}`)}</h1>
      ) : (
        <Tag key={key}>{inline(block.text, `h${key}`)}</Tag>
      );
    }
    case "paragraph":
      return <p key={key}>{inline(block.text, `p${key}`)}</p>;
    case "list": {
      const items = block.items.map((item, i) => <li key={i}>{inline(item, `l${key}-${i}`)}</li>);
      return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
    }
    case "quote":
      return <blockquote key={key}>{inline(block.text, `q${key}`)}</blockquote>;
    case "code":
      return (
        <pre key={key}>
          <code>{block.text}</code>
        </pre>
      );
    case "table":
      return (
        <div key={key} className="md-table">
          <table>
            <thead>
              <tr>
                {block.head.map((cell, i) => (
                  <th key={i}>{inline(cell, `th${key}-${i}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c}>{inline(cell, `td${key}-${r}-${c}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "rule":
      return <hr key={key} />;
  }
}

export function Markdown({ text, className = "markdown" }: { text: string; className?: string }) {
  return <div className={className}>{parseBlocks(text).map(renderBlock)}</div>;
}

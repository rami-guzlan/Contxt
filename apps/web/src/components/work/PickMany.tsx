// Pick any number from a list (skills, Library documents, projects, docs), in the order picked,
// with a search when the list is long. What is picked shows as chips that can be taken out.

import { useId, useState } from "react";

export interface PickOption {
  value: string;
  label: string;
  hint?: string;
}

export function PickMany({
  label,
  options,
  value,
  onChange,
  empty,
  max = 20,
  hint,
}: {
  label: string;
  options: PickOption[];
  value: string[];
  onChange: (values: string[]) => void;
  /** What none picked means, said on the closed control. */
  empty: string;
  max?: number;
  hint?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [find, setFind] = useState("");
  const wanted = find.trim().toLowerCase();
  const shown = options.filter((o) => !wanted || `${o.label} ${o.hint ?? ""}`.toLowerCase().includes(wanted));
  const labels = new Map(options.map((o) => [o.value, o.label]));
  const toggle = (picked: string) =>
    onChange(value.includes(picked) ? value.filter((v) => v !== picked) : [...value, picked].slice(0, max));
  return (
    <div className="field">
      <span className="field-label" id={`${id}-label`}>
        {label}
      </span>
      <div className="multi-pick">
        <button type="button" className="multi-pick-toggle" aria-expanded={open} aria-labelledby={`${id}-label`} onClick={() => setOpen(!open)}>
          {value.length ? `${value.length} chosen` : empty}
        </button>
        {open ? (
          <div className="multi-pick-panel">
            {options.length > 8 ? (
              <input type="search" aria-label={`Find in ${label.toLowerCase()}`} placeholder="Find" value={find} onChange={(event) => setFind(event.target.value)} />
            ) : null}
            <ul className="multi-pick-list" aria-label={label}>
              {shown.map((option) => (
                <li key={option.value}>
                  <label>
                    <input
                      type="checkbox"
                      checked={value.includes(option.value)}
                      disabled={!value.includes(option.value) && value.length >= max}
                      onChange={() => toggle(option.value)}
                    />
                    <span>{option.label}</span>
                    {option.hint ? <span className="muted small"> {option.hint}</span> : null}
                  </label>
                </li>
              ))}
              {!shown.length ? <li className="muted small">{options.length ? "Nothing matches." : "Nothing to pick yet."}</li> : null}
            </ul>
          </div>
        ) : null}
      </div>
      {value.length ? (
        <ol className="chips picked-skills" aria-label={`${label}: chosen`}>
          {value.map((picked) => (
            <li key={picked} className="chip">
              {labels.get(picked) ?? picked}{" "}
              <button type="button" className="link" aria-label={`Leave out ${labels.get(picked) ?? picked}`} onClick={() => toggle(picked)}>
                ×
              </button>
            </li>
          ))}
        </ol>
      ) : null}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  );
}

/** Lines of a textarea as a list, and back. */
export const linesOf = (text: string): string[] =>
  text
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*[-*]\s*/, "").trim())
    .filter(Boolean);

export const textOf = (lines: string[]): string => lines.join("\n");

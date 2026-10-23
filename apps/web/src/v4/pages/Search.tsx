// Search (⌘K), as v4's palette draws it: one field, then the pages of the app and what the
// Brain holds that matches, grouped: projects, Brain notes and captures. Enter opens the first.

import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useSearch } from "../../api/hooks";
import { css } from "../css";
import { Failure, Loading } from "../ui";

const PAGES: [string, string][] = [
  ["/ask", "Talk to your Brain"],
  ["/", "Home"],
  ["/capture", "Capture"],
  ["/brain/catch-up", "Catch up"],
  ["/projects", "Projects"],
  ["/brain", "Brain"],
  ["/agents", "Agents"],
  ["/activity", "Activity"],
  ["/settings", "Settings"],
];

interface Hit {
  key: string;
  label: string;
  kind: string;
  hue: number | null;
  to: string;
}

const dot = (h: number | null) => `width:6px;height:6px;border-radius:50%;flex:none;background:${h == null ? "var(--gray)" : `oklch(0.74 0.12 ${h})`}`;

function Group({ title, hits, go }: { title: string; hits: Hit[]; go: (to: string) => void }) {
  if (!hits.length) return null;
  return (
    <div role="group" aria-label={title} style={css("display:flex;flex-direction:column")}>
      <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--muted);padding:10px 14px 4px;text-transform:uppercase")}>{title}</span>
      {hits.map((r) => (
        <button
          key={r.key}
          type="button"
          className="gn-hover"
          onClick={() => go(r.to)}
          style={css("display:flex;align-items:center;gap:12px;padding:11px 14px;border:0;border-radius:12px;background:transparent;text-align:left;color:var(--ink)")}
        >
          <span aria-hidden="true" style={css(dot(r.hue))} />
          <span style={css("font:400 15px Geist;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap")}>{r.label}</span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>{r.kind}</span>
        </button>
      ))}
    </div>
  );
}

export function SearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const field = useRef<HTMLInputElement>(null);
  const term = q.trim();
  const search = useSearch(term);

  useEffect(() => field.current?.focus(), []);
  // The address keeps the words, so a search can be shared or reopened.
  useEffect(() => {
    const id = window.setTimeout(() => setParams(term ? { q: term } : {}, { replace: true }), 250);
    return () => window.clearTimeout(id);
  }, [term, setParams]);

  const low = term.toLowerCase();
  const pages: Hit[] = (low ? PAGES.filter(([, l]) => l.toLowerCase().includes(low)) : PAGES).map(([to, label]) => ({
    key: `page:${to}`,
    label,
    kind: "Page",
    hue: null,
    to,
  }));
  const data = term.length > 1 ? search.data : undefined;
  const projects: Hit[] = (data?.projects ?? []).map((p) => ({
    key: `project:${p.id}`,
    label: p.title,
    kind: "Project",
    hue: 320,
    to: `/projects/${encodeURIComponent(p.id)}`,
  }));
  const brain: Hit[] = (data?.brain ?? []).map((h) => ({
    key: `brain:${h.id}`,
    label: h.title,
    kind: h.kind ? `Brain · ${h.kind}` : "Brain",
    hue: 210,
    to: `/brain/notes/${encodeURIComponent(h.id)}`,
  }));
  const notes: Hit[] = (data?.notes ?? []).map((n) => ({
    key: `note:${n.id}`,
    label: n.title || "Untitled capture",
    kind: "Capture",
    hue: 35,
    to: `/capture/${encodeURIComponent(n.id)}`,
  }));
  const all = [...pages, ...projects, ...brain, ...notes];
  const found = projects.length + brain.length + notes.length;
  const go = (to: string) => navigate(to);
  const close = () => (window.history.length > 1 ? navigate(-1) : navigate("/"));

  return (
    <div className="gn-page" style={css("display:flex;justify-content:center;padding:14vh 20px 40px;box-sizing:border-box")}>
      <div role="search" style={css("width:600px;max-width:100%;align-self:flex-start;background:var(--surface);border-radius:20px;box-shadow:var(--shadow2);overflow:hidden")}>
        <input
          ref={field}
          type="search"
          aria-label="Search notes, projects, pages"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && all[0]) go(all[0].to);
            if (e.key === "Escape") close();
          }}
          placeholder="Search notes, projects, pages…"
          style={css("width:100%;box-sizing:border-box;border:0;border-bottom:1px solid var(--line);outline:none;padding:18px 22px;background:transparent;color:var(--ink);font:400 17px Geist")}
        />
        <div style={css("display:flex;flex-direction:column;padding:8px;max-height:60vh;overflow:auto")}>
          <Group title="Pages" hits={pages} go={go} />
          {term.length > 1 ? (
            search.isLoading ? (
              <div style={css("padding:0 14px")}>
                <Loading what="Searching your Brain" />
              </div>
            ) : search.error ? (
              <div style={css("padding:8px")}>
                <Failure error={search.error} retry={() => void search.refetch()} />
              </div>
            ) : (
              <>
                <Group title="Projects" hits={projects} go={go} />
                <Group title="Brain" hits={brain} go={go} />
                <Group title="Captures" hits={notes} go={go} />
                {!found ? (
                  <span role="status" style={css("padding:12px 14px;font:400 14px Geist;color:var(--muted)")}>
                    Nothing in your Brain or your captures matches “{term}”. Try fewer words, or ask your Brain instead.
                  </span>
                ) : (
                  <span role="status" style={css("position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)")}>
                    {found} found
                  </span>
                )}
              </>
            )
          ) : term ? (
            <span style={css("padding:12px 14px;font:400 13px Geist;color:var(--muted)")}>Type one more letter to search your Brain.</span>
          ) : null}
          {term ? (
            <button
              type="button"
              className="gn-hover"
              onClick={() => go(`/ask?q=${encodeURIComponent(term)}`)}
              style={css("display:flex;align-items:center;gap:12px;padding:11px 14px;border:0;border-radius:12px;background:transparent;text-align:left;color:var(--ink);margin-top:4px")}
            >
              <span aria-hidden="true" style={css(dot(null))} />
              <span style={css("font:400 15px Geist;flex:1")}>Ask your Brain: “{term}”</span>
              <span style={css("font:400 12px Geist;color:var(--muted)")}>Ask</span>
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

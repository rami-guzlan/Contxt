// Scout your folders (v4 isCapture, Release 1): the folders and file types it inspects, Scan
// now, the last successful inspection, and the real differences it found, each brought in as a
// capture or dismissed. Saves without a change and renames stay quiet. Watching folders,
// scheduled scans and connected tools are a later phase.

import { useState } from "react";
import { Link } from "react-router";

import { useBrainProjects } from "../../api/hooks";
import { type ScoutDifference, type ScoutOverview, useScan, useScout, useScoutDifference, useScoutSettings } from "../api";
import { css } from "../css";
import { Failure, Later, Loading, S, when } from "../ui";

const ERR = "font:400 13px Geist;color:oklch(0.55 0.17 28)";

function base(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

function size(bytes?: number): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Scout() {
  const scout = useScout();
  const settings = useScoutSettings();
  const scan = useScan();
  const diff = useScoutDifference();
  const projects = useBrainProjects();
  const [adding, setAdding] = useState(false);
  const [path, setPath] = useState("");
  const [project, setProject] = useState("");
  const [brought, setBrought] = useState<Record<string, string>>({});

  const data: ScoutOverview | undefined = scout.data;
  const folders = data?.folders ?? [];
  const projectName = (id: string | null | undefined) => (id ? (projects.data ?? []).find((p) => p.id === id)?.title ?? id : null);
  const result = scan.data;
  const quiet = (result?.found ?? []).filter((f) => f.quiet && f.kind === "renamed");

  function saveFolders(next: { path: string; project?: string | null }[], after?: () => void) {
    settings.mutate({ folders: next }, { onSuccess: () => after?.() });
  }

  return (
    <section
      aria-label="Scout"
      style={css("border-radius:22px;border:1px solid var(--line2);background:var(--surface);padding:20px;display:flex;flex-direction:column;gap:14px;min-width:0;box-sizing:border-box")}
    >
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:3px")}>
          <span style={css("font:400 28px Newsreader")}>Scout your folders</span>
          <span style={css("font:400 14px/1.5 Geist;color:var(--muted);max-width:560px")}>
            Pick folders and file types. When you press Scan now, Scout compares them with its last inspection and brings real differences here as proposals. Repeated saves and renames stay
            quiet.
          </span>
        </div>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending || !data || folders.length === 0}
          title={folders.length === 0 ? "Choose a folder first" : undefined}
          style={css("padding:9px 16px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 13.5px Geist")}
        >
          {scan.isPending ? "Scanning…" : "Scan now"}
        </button>
      </div>
      {scan.error ? (
        <span role="alert" style={css(ERR)}>
          {(scan.error as Error).message}
        </span>
      ) : null}
      {scout.isLoading ? (
        <Loading what="Loading Scout" />
      ) : scout.error ? (
        <Failure error={scout.error} retry={() => void scout.refetch()} />
      ) : data ? (
        <>
          <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px")}>
            <div style={css("padding:16px 18px;border-radius:18px;border:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;gap:8px")}>
              <span style={css("font:500 13px Geist;color:var(--muted)")}>Folders</span>
              {folders.length === 0 ? <span style={css("font:400 13px Geist;color:var(--ink2)")}>No folder chosen yet.</span> : null}
              {folders.map((f, i) => (
                <div key={f.path} style={css("display:flex;flex-direction:column;gap:6px;padding:8px 10px;border-radius:12px;background:var(--soft)")}>
                  <span style={css("font:400 13px 'Geist Mono';word-break:break-all")}>{f.path}</span>
                  <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
                    <label style={css("font:400 12px Geist;color:var(--muted);display:flex;gap:6px;align-items:center")}>
                      Project
                      <select
                        value={f.project ?? ""}
                        disabled={settings.isPending}
                        onChange={(e) => saveFolders(folders.map((g, j) => (j === i ? { ...g, project: e.target.value || null } : g)))}
                        style={css(S.input + ";font:400 12px Geist;padding:3px 6px")}
                      >
                        <option value="">No project</option>
                        {(projects.data ?? []).map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.title}
                          </option>
                        ))}
                        {f.project && !(projects.data ?? []).some((p) => p.id === f.project) ? <option value={f.project}>{f.project}</option> : null}
                      </select>
                    </label>
                    <button
                      onClick={() => saveFolders(folders.filter((_, j) => j !== i))}
                      disabled={settings.isPending}
                      aria-label={`Stop scouting ${f.path}`}
                      style={css("border:0;background:transparent;padding:0;font:500 12px Geist;color:var(--ink2);margin-left:auto")}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
              {adding ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!path.trim()) return;
                    saveFolders([...folders, { path: path.trim(), project: project || null }], () => {
                      setPath("");
                      setProject("");
                      setAdding(false);
                    });
                  }}
                  style={css("display:flex;flex-direction:column;gap:6px")}
                >
                  <label htmlFor="scout-path" style={css("font:500 12px Geist;color:var(--muted)")}>
                    Folder on this computer
                  </label>
                  <input
                    id="scout-path"
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                    placeholder="For example ~/Work/Notes"
                    style={css(S.input + ";font:400 13px 'Geist Mono'")}
                  />
                  <label style={css("font:400 12px Geist;color:var(--muted);display:flex;gap:6px;align-items:center")}>
                    Link to a project
                    <select value={project} onChange={(e) => setProject(e.target.value)} style={css(S.input + ";font:400 12px Geist;padding:3px 6px")}>
                      <option value="">No project</option>
                      {(projects.data ?? []).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div style={css("display:flex;gap:8px")}>
                    <button type="submit" disabled={!path.trim() || settings.isPending} style={css(S.primarySm)}>
                      {settings.isPending ? "Adding…" : "Add folder"}
                    </button>
                    <button type="button" onClick={() => setAdding(false)} style={css(S.ghostSm)}>
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <button onClick={() => setAdding(true)} style={css("align-self:flex-start;border:0;background:transparent;padding:2px 0;font:500 13px Geist;color:var(--ink)")}>
                  + Choose a folder
                </button>
              )}
            </div>
            <div style={css("padding:16px 18px;border-radius:18px;border:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;gap:10px")}>
              <span style={css("font:500 13px Geist;color:var(--muted)")}>Supported formats it inspects</span>
              <div role="group" aria-label="Formats" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
                {Object.entries(data.formats).map(([k, on]) => (
                  <button
                    key={k}
                    aria-pressed={on}
                    disabled={settings.isPending}
                    onClick={() => settings.mutate({ formats: { [k]: !on } })}
                    style={css(
                      `padding:5px 11px;border-radius:99px;border:1px solid ${on ? "var(--ink)" : "var(--line2)"};background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink2)"};font:500 12px 'Geist Mono';cursor:pointer`,
                    )}
                  >
                    .{k}
                  </button>
                ))}
              </div>
              <span role="status" style={css("font:400 13px Geist;color:var(--ink2);margin-top:auto")}>
                Last successful inspection: {data.last_inspection ? `${when(data.last_inspection)} · ${data.files_seen === 1 ? "1 file" : `${data.files_seen} files`}` : "none yet"}
              </span>
              {data.last_error ? (
                <span style={css(ERR)}>
                  The last scan failed ({when(data.last_error.at)}): {data.last_error.why}
                </span>
              ) : null}
            </div>
          </div>
          {settings.error ? (
            <span role="alert" style={css(ERR)}>
              {(settings.error as Error).message}
            </span>
          ) : null}
          <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:4px 22px")}>
            <span style={css("display:block;font:500 13px Geist;color:var(--muted);padding:14px 0 6px")}>Proposed differences</span>
            {data.differences.length === 0 && Object.keys(brought).length === 0 ? (
              <span style={css("display:block;font:400 14px Geist;color:var(--ink2);padding:13px 0;border-top:1px solid var(--line)")}>
                {data.last_inspection ? "No differences waiting." : "Scan to see what's new or changed."}
              </span>
            ) : null}
            {data.differences.map((d) => (
              <Difference key={d.id} d={d} project={projectName(d.project)} busy={diff.isPending} onAct={(act) => diff.mutate({ id: d.id, act }, { onSuccess: (r) => r.capture_id && setBrought((b) => ({ ...b, [d.path]: r.capture_id as string })) })} />
            ))}
            {Object.entries(brought).map(([p, id]) => (
              <div key={id} role="status" style={css("display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                <span style={css("flex:1;min-width:220px;font:400 14px Geist")}>{base(p)} is in Capture now.</span>
                <Link to={`/capture?source=${encodeURIComponent(id)}`} style={css("font:500 13px Geist;color:var(--ink)")}>
                  Open it →
                </Link>
              </div>
            ))}
            {(result?.unreadable ?? []).map((p) => (
              <div key={p} style={css("display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                <div style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
                  <span style={css("font:400 15px Geist")}>{base(p)} couldn’t be read</span>
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>Not inspected. Allow access to it, then Scan now again.</span>
                </div>
              </div>
            ))}
            {diff.error ? (
              <span role="alert" style={css(ERR + ";display:block;padding:8px 0")}>
                {(diff.error as Error).message}
              </span>
            ) : null}
            <span style={css("display:block;font:400 13px/1.5 Geist;color:var(--muted);padding:12px 0 14px;border-top:1px solid var(--line)")}>
              {result?.last_inspection ? `Scanned ${when(result.last_inspection)}: ${result.differences.length ? `${result.differences.length} waiting.` : "no new differences."} ` : ""}
              {quiet.length
                ? `${quiet.length === 1 ? "1 rename" : `${quiet.length} renames`} (${quiet
                    .slice(0, 3)
                    .map((q) => `${base(q.from ?? "")} → ${base(q.path)}`)
                    .join(", ")}) recognised and not proposed. `
                : ""}
              Saves without a content change and renames stay quiet: nothing is proposed for them.
            </span>
          </div>
        </>
      ) : null}
      <div style={css("display:flex;gap:16px;flex-wrap:wrap;font:400 13px Geist;color:var(--muted)")}>
        <span>
          Watch folders automatically
          <Later />
        </span>
        <span>
          Scheduled scans
          <Later />
        </span>
        <span>
          Search connected tools (Gmail, Slack, Drive)
          <Later />
        </span>
      </div>
    </section>
  );
}

function Difference({ d, project, busy, onAct }: { d: ScoutDifference; project: string | null; busy: boolean; onAct: (act: "bring-in" | "dismiss") => void }) {
  const what = d.kind === "new" ? "New file" : "Changed since the last scan";
  return (
    <div style={css("display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
      <div style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:400 15px Geist")}>
          {base(d.path)} {d.kind === "new" ? "is new" : "changed"}
        </span>
        <span style={css("font:400 13px Geist;color:var(--muted);word-break:break-all")}>
          {[what, size(d.size), project, when(d.at), d.path].filter(Boolean).join(" · ")}
        </span>
      </div>
      <button onClick={() => onAct("bring-in")} disabled={busy} style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink)")}>
        Bring in →
      </button>
      <button onClick={() => onAct("dismiss")} disabled={busy} style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink2)")}>
        Dismiss
      </button>
    </div>
  );
}

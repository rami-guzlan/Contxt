// The app's frame, as v4 draws it: the sidebar (Gnomon mark, the brain, search, + New, the
// sections, Settings, Help, light or dark, the workspace) and the page beside it.

import { type ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router";

import { useHome, useMe } from "../api/hooks";
import { useTheme } from "../lib/theme";
import { useProposals } from "./api";
import { AutoNotice } from "./components/AutoNotice";
import { css } from "./css";
import { Later, S } from "./ui";

const NAV: [string, string][] = [
  ["/", "Home"],
  ["/capture", "Capture"],
  ["/projects", "Projects"],
  ["/brain", "Brain"],
  ["/agents", "Agents"],
  ["/activity", "Activity"],
];

const NEW: [string, string, string][] = [
  ["/capture?paste=1", "Write or paste", "Saved to Capture, private until kept"],
  ["/capture?upload=1", "Upload a file", "A document, a recording or a spreadsheet"],
  ["/capture?record=1", "Record a meeting", "Transcribed on this computer"],
  ["/projects?new=1", "New project", "Context, Tasks, Files and Outputs"],
  ["/ask", "Ask your Brain", "An answer with its evidence"],
];

function navStyle(active: boolean): string {
  return `display:flex;align-items:center;gap:8px;padding:9px 12px;border:0;border-radius:10px;text-decoration:none;font:${
    active ? 500 : 400
  } 14px Geist;color:var(--ink);background:${active ? "var(--nav)" : "transparent"}`;
}

export function Shell({ children }: { children: ReactNode }) {
  const me = useMe();
  const home = useHome();
  const proposals = useProposals();
  const [theme, setTheme] = useTheme();
  const [help, setHelp] = useState(false);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const waiting = proposals.data?.length ?? 0;
  const name = me.data?.workspace?.name ?? home.data?.workspace?.name ?? "Your workspace";

  useEffect(() => {
    setHelp(false);
    setAdding(false);
    setOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        navigate("/search");
      }
      if (e.key === "Escape") {
        setHelp(false);
        setAdding(false);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [navigate]);

  const aside = (
    <nav
      aria-label="Main navigation"
      className={open ? "" : "gn-aside"}
      style={css(
        `width:232px;flex:none;box-sizing:border-box;overflow-y:auto;padding:20px 14px;display:flex;flex-direction:column;gap:2px;border-right:1px solid var(--line);background:var(--bg);${
          open ? "position:fixed;inset:0 auto 0 0;z-index:70;box-shadow:var(--shadow2)" : ""
        }`,
      )}
    >
      <button
        onClick={() => navigate("/ask")}
        title="Talk to your Brain"
        className="gn-hover"
        style={css("display:flex;align-items:center;gap:10px;padding:8px 10px;margin-bottom:10px;border:0;background:transparent;border-radius:12px;color:var(--ink);text-align:left")}
      >
        <span aria-hidden style={css("width:26px;height:26px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center")}>
          <span style={css("width:2px;height:11px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
        </span>
        <span style={css("font:500 15px Geist;letter-spacing:-.01em")}>Gnomon</span>
        <span style={css("margin-left:auto;font:400 11px Geist;color:var(--muted)")}>Ask</span>
      </button>
      <div style={css("display:flex;align-items:center;gap:10px;padding:9px 12px;margin:-2px 0 12px;border-radius:12px;border:1px solid var(--line2);background:var(--surface)")}>
        <span aria-hidden style={css("width:10px;height:10px;border-radius:50%;background:oklch(0.66 0.13 250);flex:none")} />
        <span style={css("display:flex;flex-direction:column;flex:1;min-width:0")}>
          <span style={css("font:500 13.5px Geist")}>Your brain</span>
          <span style={css("font:400 11.5px Geist;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis")}>
            More than one brain is a later phase
          </span>
        </span>
      </div>
      <button
        onClick={() => navigate("/search")}
        style={css("display:flex;align-items:center;gap:8px;padding:8px 10px;margin-bottom:12px;border:1px solid var(--line2);background:var(--surface);border-radius:10px;color:var(--muted);font:400 13px Geist;text-align:left")}
      >
        Search<span style={css("margin-left:auto;font:500 11px 'Geist Mono';color:var(--faint)")}>⌘K</span>
      </button>
      <div style={css("position:relative;margin:-4px 0 12px")}>
        <button
          aria-expanded={adding}
          onClick={() => setAdding((v) => !v)}
          style={css("width:100%;display:flex;align-items:center;gap:8px;padding:9px 12px;border:0;background:var(--ink);color:var(--bg);border-radius:10px;font:500 13px Geist")}
        >
          + New<span style={css("margin-left:auto;font:400 11px Geist;opacity:.6")}>hold Space to talk</span>
        </button>
        {adding ? (
          <div style={css("position:absolute;top:44px;left:0;right:0;background:var(--surface);border-radius:16px;box-shadow:var(--shadow2);padding:6px;z-index:25;display:flex;flex-direction:column")}>
            {NEW.map(([to, label, hint]) => (
              <button
                key={to}
                className="gn-hover"
                onClick={() => navigate(to)}
                style={css("display:flex;flex-direction:column;gap:2px;padding:10px 12px;border:0;border-radius:10px;background:transparent;text-align:left;color:var(--ink)")}
              >
                <span style={css("font:500 14px Geist")}>{label}</span>
                <span style={css("font:400 12px Geist;color:var(--muted)")}>{hint}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {NAV.map(([to, label]) => (
        <NavLink key={to} to={to} end={to === "/"} className="gn-hover" style={({ isActive }) => css(navStyle(isActive))}>
          {label}
          {to === "/brain" && waiting > 0 ? (
            <span style={css("margin-left:auto;font:500 11px Geist;background:oklch(0.74 0.12 35);color:#2a160e;border-radius:99px;padding:1px 8px")}>
              {waiting} new
            </span>
          ) : null}
        </NavLink>
      ))}
      <div style={css("margin-top:auto;display:flex;flex-direction:column;gap:2px;padding-top:10px;border-top:1px solid var(--line)")}>
        <NavLink to="/settings" className="gn-hover" style={({ isActive }) => css(navStyle(isActive))}>
          Settings
        </NavLink>
        <div style={css("position:relative")}>
          <button aria-expanded={help} className="gn-hover" onClick={() => setHelp((v) => !v)} style={css(navStyle(false) + ";width:100%;text-align:left")}>
            Help
          </button>
          {help ? (
            <div style={css("position:absolute;bottom:44px;left:0;width:280px;background:var(--surface);border-radius:16px;box-shadow:var(--shadow2);padding:8px;z-index:25;display:flex;flex-direction:column;gap:2px")}>
              <button className="gn-hover" onClick={() => navigate("/?tour=1")} style={css(navStyle(false))}>
                Take the 1-minute tour
              </button>
              <a className="gn-hover" href="/onboarding/index.html" style={css(navStyle(false))}>
                Open the guided onboarding
              </a>
              <button className="gn-hover" onClick={() => navigate("/?quickstart=1")} style={css(navStyle(false))}>
                Show the quick start on Home
              </button>
              <button className="gn-hover" onClick={() => navigate("/states")} style={css(navStyle(false))}>
                Empty, error and recovery states
              </button>
              <span style={css(S.eyebrow + ";padding:8px 12px 4px")}>SHORTCUTS</span>
              <div style={css("display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:0 12px 8px;font:400 12.5px Geist;color:var(--ink2)")}>
                <span style={css("font:500 11px 'Geist Mono'")}>⌘K</span>
                <span>Search everything</span>
                <span style={css("font:500 11px 'Geist Mono'")}>Space</span>
                <span>Hold to talk, anywhere</span>
                <span style={css("font:500 11px 'Geist Mono'")}>Esc</span>
                <span>Close what's open</span>
              </div>
            </div>
          ) : null}
        </div>
        <button className="gn-hover" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} style={css(navStyle(false) + ";width:100%;text-align:left")}>
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        <div style={css("display:flex;align-items:center;gap:10px;padding:10px 10px 0")}>
          <span aria-hidden style={css("width:28px;height:28px;border-radius:50%;background:var(--soft);display:flex;align-items:center;justify-content:center;font:500 12px Geist")}>
            {name.slice(0, 1).toUpperCase()}
          </span>
          <div style={css("display:flex;flex-direction:column;min-width:0")}>
            <span style={css("font:500 13px Geist;white-space:nowrap;overflow:hidden;text-overflow:ellipsis")}>{name}</span>
            <span style={css("font:400 11.5px Geist;color:var(--muted)")}>
              On this computer <Later what="cloud later" />
            </span>
          </div>
        </div>
      </div>
    </nav>
  );

  return (
    <div style={css("display:flex;height:100vh;background:var(--bg);color:var(--ink);overflow:hidden")}>
      {aside}
      {open ? <div onClick={() => setOpen(false)} style={css("position:fixed;inset:0;background:var(--scrim);z-index:65")} /> : null}
      <main style={css("flex:1;min-width:0;overflow-y:auto;position:relative")}>
        <button
          aria-label="Open the menu"
          onClick={() => setOpen(true)}
          className="gn-menu"
          style={css("position:sticky;top:12px;left:12px;z-index:20;padding:8px 12px;border-radius:99px;border:1px solid var(--line2);background:var(--surface);color:var(--ink);font:500 13px Geist")}
        >
          Menu
        </button>
        <AutoNotice />
        {children}
      </main>
    </div>
  );
}

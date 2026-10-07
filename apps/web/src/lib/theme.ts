// Light or dark: the person's choice, kept in this browser, else the system's. index.html applies
// a kept choice before the page paints, so the other one never flashes first.

import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
export const THEME_KEY = "workspace-theme";

export function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage blocked: the system's theme, for this visit
  }
}

function systemTheme(): Theme {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** The theme in use, and a way to choose one: the page follows at once and the choice is kept. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [chosen, setChosen] = useState<Theme | null>(storedTheme);
  const [system, setSystem] = useState<Theme>(systemTheme);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => setSystem(query.matches ? "dark" : "light");
    query.addEventListener?.("change", follow);
    return () => query.removeEventListener?.("change", follow);
  }, []);
  function choose(theme: Theme) {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // storage blocked: the choice holds until the page reloads
    }
    setChosen(theme);
  }
  return [chosen ?? system, choose];
}

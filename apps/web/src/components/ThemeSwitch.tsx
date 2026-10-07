// Light or dark in one click, at the foot of the menu beside Settings.

import { Moon, Sun } from "lucide-react";

import { useTheme } from "../lib/theme";

export function ThemeSwitch() {
  const [theme, choose] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const Icon = next === "light" ? Sun : Moon;
  return (
    <button type="button" className="nav-link theme-switch" title={`Switch to ${next} mode`} onClick={() => choose(next)}>
      <Icon className="nav-icon" aria-hidden="true" />
      {next === "light" ? "Light mode" : "Dark mode"}
    </button>
  );
}

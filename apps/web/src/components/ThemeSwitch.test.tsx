import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { THEME_KEY } from "../lib/theme";
import { ThemeSwitch } from "./ThemeSwitch";

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("light or dark", () => {
  it("switches in one click, both ways, and keeps the choice", async () => {
    const user = userEvent.setup();
    render(<ThemeSwitch />);
    // No choice yet: the system's theme (light here), so the button offers dark.
    await user.click(screen.getByRole("button", { name: "Dark mode" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    await user.click(screen.getByRole("button", { name: "Light mode" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
  });

  it("starts from the choice kept in this browser", () => {
    window.localStorage.setItem(THEME_KEY, "dark");
    render(<ThemeSwitch />);
    expect(screen.getByRole("button", { name: "Light mode" })).toHaveAttribute("title", "Switch to light mode");
  });
});

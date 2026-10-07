import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Compare, diffWords, folded } from "./Diff";

describe("word differences", () => {
  it("keeps what both say and marks what changed, in reading order", () => {
    expect(diffWords("Projects run six weeks.", "Projects run ten weeks.")).toEqual([
      { text: "Projects run ", kind: "same" },
      { text: "six", kind: "removed" },
      { text: "ten", kind: "added" },
      { text: " weeks.", kind: "same" },
    ]);
  });

  it("still marks one changed word in a long doc", () => {
    const long = "word ".repeat(3000);
    const pieces = diffWords(`${long}old ending`, `${long}new ending`);
    expect(pieces.filter((p) => p.kind !== "same")).toEqual([
      { text: "old", kind: "removed" },
      { text: "new", kind: "added" },
    ]);
  });

  it("compares whole lines where a long doc changed throughout", () => {
    const doc = (odd: string) => Array.from({ length: 900 }, (_, n) => `line ${n} ${n % 2 ? odd : "stays"}\n`).join("");
    const pieces = diffWords(doc("stays"), doc("moves"));
    expect(pieces[0]).toEqual({ text: "line 0 stays\nline 1 ", kind: "same" });
    expect(pieces).toContainEqual({ text: "line 2 stays\n", kind: "same" });
    expect(pieces).toContainEqual({ text: "line 3 stays\n", kind: "removed" });
    expect(pieces).toContainEqual({ text: "line 3 moves\n", kind: "added" });
  });

  it("handles one side empty", () => {
    expect(diffWords("", "New text")).toEqual([{ text: "New text", kind: "added" }]);
    expect(diffWords("Old text", "")).toEqual([{ text: "Old text", kind: "removed" }]);
  });

  it("shows the two versions side by side with the changes marked", () => {
    render(
      <Compare
        before={{ label: "In the Brain now", title: "Scale", body: "500+ hours a year" }}
        after={{ label: "Proposed", title: "Figures", body: "600+ hours a year" }}
      />,
    );
    const before = screen.getByRole("region", { name: "In the Brain now" });
    const after = screen.getByRole("region", { name: "Proposed" });
    expect(within(before).getByText("500+").tagName).toBe("DEL");
    expect(within(after).getByText("600+").tagName).toBe("INS");
  });

  it("does not mark two texts written apart, which share too little to compare word by word", () => {
    const { container } = render(
      <Compare
        before={{ label: "In the Brain now", title: "Scale", body: "Founded 1985, offices across EMEA and APAC." }}
        after={{ label: "Proposed", title: "Figures", body: "Studio delivers 600+ hours of bespoke content." }}
      />,
    );
    expect(container.querySelector("del, ins")).toBeNull();
    expect(screen.getByText("Studio delivers 600+ hours of bespoke content.")).toBeInTheDocument();
  });

  it("folds long unchanged stretches of a long text, so the change stands out", () => {
    const steps = Array.from({ length: 400 }, (_, i) => `Step ${i + 1}: keep this line as it is.`).join("\n");
    const before = `${steps}\nLast: send it.`;
    const after = `${steps}\nLast: check it, then send it.`;
    const { container } = render(
      <Compare before={{ label: "The skill now", title: "/posts", body: before }} after={{ label: "Proposed", title: "/posts", body: after }} />,
    );
    const now = within(screen.getByRole("region", { name: "The skill now" }));
    expect(now.getByText(/unchanged lines/)).toBeInTheDocument();
    expect(container.textContent).not.toContain("Step 200:");
    expect(within(screen.getByRole("region", { name: "Proposed" })).getByText("check it, then", { exact: false }).tagName).toBe("INS");
    expect(folded("a\nb")).toBe("a\nb");
  });
});

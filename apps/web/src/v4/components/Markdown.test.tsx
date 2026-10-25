import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, parseBlocks } from "./Markdown";

describe("markdown", () => {
  it("renders the shapes Brain notes and references use", () => {
    const { container } = render(
      <Markdown
        text={[
          "---",
          "name: brand-sheet",
          "---",
          "# Studio style guide",
          "",
          "Write **plain** words, *short* sentences and `code` spans.",
          "",
          "- One benefit per headline",
          "- Sentence case",
          "",
          "1. Gather",
          "2. Draft",
          "",
          "> Source: `guide.pdf`",
          "",
          "| Word | Use |",
          "| --- | --- |",
          "| leverage | never |",
          "",
          "```",
          "const x = 1;",
          "```",
        ].join("\n")}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Studio style guide" })).toBeInTheDocument();
    expect(container.querySelector("strong")?.textContent).toBe("plain");
    expect(container.querySelector("em")?.textContent).toBe("short");
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector("blockquote")?.textContent).toContain("guide.pdf");
    expect(screen.getByRole("table")).toHaveTextContent("leverage");
    expect(container.querySelector("pre code")?.textContent).toBe("const x = 1;");
    expect(container.textContent).not.toContain("name: brand-sheet");
  });

  it("never turns text into markup or unsafe links", () => {
    const { container } = render(
      <Markdown text={'<script>alert(1)</script> [bad](javascript:alert(1)) [ok](https://example.com) see https://example.org/x.'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
    const links = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(links).toEqual(["https://example.com", "https://example.org/x"]);
  });

  it("leaves underscores inside identifiers alone", () => {
    const { container } = render(<Markdown text="Set note_budget and include_notes in routing.json." />);
    expect(container.querySelector("em")).toBeNull();
  });

  it("parses a paragraph that runs over several lines as one", () => {
    expect(parseBlocks("First line\nsecond line\n\nNext")).toEqual([
      { kind: "paragraph", text: "First line second line" },
      { kind: "paragraph", text: "Next" },
    ]);
  });
});

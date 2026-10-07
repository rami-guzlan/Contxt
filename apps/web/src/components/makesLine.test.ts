import { describe, expect, it } from "vitest";

import { makesLine } from "./SkillWork";

describe("what a skill makes, said plainly", () => {
  it("names files, text, or both", () => {
    expect(makesLine(["pdf", "docx"], true)).toBe("Makes PDF and DOCX files");
    expect(makesLine(["post"], false)).toBe("Writes a post");
    expect(makesLine(["email"], false)).toBe("Writes an email");
    expect(makesLine(["copy", "post"], false)).toBe("Writes: copy, post");
    expect(makesLine(["image", "post"], true)).toBe("Makes image files and writes a post");
    expect(makesLine(["pdf", "image"], true)).toBe("Makes PDF and image files");
    expect(makesLine([], false)).toBe("");
  });
});

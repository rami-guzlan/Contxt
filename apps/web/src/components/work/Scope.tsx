// Whose an item is. In the solo app every scope is yours, so every item says "Yours"; the team
// edition will say Company, Department, Team or Person, and give each scope's admins a switcher
// to manage what that scope holds.

const WORDS: Record<string, string> = {
  company: "the company",
  dept: "a department",
  team: "a team",
  person: "you",
  agent: "an agent",
};

/** The scope an item is kept in, in words: "the company", "a department", "you". */
export function scopeWords(scope: string | null | undefined): string {
  const kind = String(scope ?? "").split(":", 1)[0] ?? "";
  return WORDS[kind] ?? "you";
}

export function ScopeChip({ scope }: { scope?: string | null }) {
  const title = scope && !scope.startsWith("person:")
    ? `Kept for ${scopeWords(scope)} (${scope}). In this app you own every scope, so it is yours to change.`
    : "Yours: only you see it and change it.";
  return (
    <span className="scope-chip" title={title}>
      Yours
    </span>
  );
}

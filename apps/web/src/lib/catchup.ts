// What Home, the navigation and Catch up share about the catch-up plan: its cards in the order
// they are shown, and the time it takes in words.

import type { CatchUpPlan, JudgmentCard, LegacyOffer, Nudge, Offer, QuickGroup, UpkeepCard } from "../api/types";

/** One card in the run, in the order it is shown. */
export type Item =
  | { kind: "legacy"; key: string; offer: LegacyOffer }
  | { kind: "judgment"; key: string; card: JudgmentCard }
  | { kind: "quick"; key: string; group: QuickGroup }
  | { kind: "upkeep"; key: string; card: UpkeepCard }
  | { kind: "offer"; key: string; offer: Offer }
  | { kind: "nudge"; key: string; nudge: Nudge };

export function queueOf(plan: CatchUpPlan): Item[] {
  return [
    ...(plan.legacy ? [{ kind: "legacy" as const, key: plan.legacy.key, offer: plan.legacy }] : []),
    ...plan.judgment.map((card) => ({ kind: "judgment" as const, key: card.key, card })),
    ...plan.quick.map((group) => ({ kind: "quick" as const, key: group.key, group })),
    ...plan.upkeep.map((card) => ({ kind: "upkeep" as const, key: card.key, card })),
    ...plan.offers.map((offer) => ({ kind: "offer" as const, key: offer.key, offer })),
    ...plan.nudges.map((nudge) => ({ kind: "nudge" as const, key: nudge.key, nudge })),
  ];
}

/** "about 3 minutes", "about a minute", "under a minute". */
export function minutes(seconds: number): string {
  if (!seconds) return "under a minute";
  const m = Math.ceil(seconds / 60);
  return m <= 1 ? "about a minute" : `about ${m} minutes`;
}

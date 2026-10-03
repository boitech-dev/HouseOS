// What changed, for the "What's new" sheet after an update (onboarding.tsx). Newest first; a
// person sees every release newer than the one they last saw (preference seen_release): the
// newest open, the ones they missed stacked below. Short on purpose: one line each, and where to find it. Words go through t() where shown.
import type { GlyphName } from "./design";

/** The release people are told about; bump it with a new entry below. */
export const RELEASE = "1.0";

export type News = { glyph: GlyphName | "nox"; title: string; text: string; go?: string };

export const WHATS_NEW: { version: string; items: News[] }[] = [
  {
    version: "1.0",
    items: [
      {
        glyph: "room.watch",
        title: "Any video link on the TV",
        text: "Watch → Web: paste a YouTube, TikTok or other link and it plays on the TV, no ads.",
        go: "/watch?kind=web",
      },
      {
        glyph: "room.games",
        title: "Your saves follow you",
        text: "Start on your phone, continue on the TV: each person's saves are kept by the house.",
      },
      {
        glyph: "room.me",
        title: "Your language, everywhere",
        text: "Dates, numbers and messages follow the app's language, and Nox answers in yours.",
      },
      {
        glyph: "nox",
        title: "Ask Nox how the house works",
        text: "The tour is Nox's first suggestion, and one tap on Nox when you're new.",
      },
    ],
  },
];

/** Every release newer than `seen` ("1.0"), newest first. */
export function unseen(seen: string) {
  const n = (v: string) => v.split(".").reduce((sum, part) => sum * 100 + Number(part || 0), 0);
  // A mark above RELEASE was left by a pre-release build: it counts as 1.0.
  const last = n(seen || "0") > n(RELEASE) ? n("1.0") : n(seen || "0");
  return WHATS_NEW.filter((r) => n(r.version) > last);
}

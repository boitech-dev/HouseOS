// Under each room's title: one real tip about that room, a different one each visit, so people
// learn the house as they use it. The same in every theme (a theme only sets the face they're in).
import { useState } from "react";
import { t } from "./i18n";

const TIPS: Record<string, string[]> = {
  listen: [
    "Paste a YouTube or SoundCloud link, or search a title: everyone takes turns.",
    "Every three hours, your veto skips or removes someone else's song.",
    "Speaker mode turns your phone into the house's speaker, even on Bluetooth.",
    "Auto play keeps the music going when the queue runs out.",
  ],
  watch: [
    "Filters find films by genre, decade, actor, director or theme.",
    "Web plays any video link on the TV, without ads.",
    "On a phone, share a video link to HouseOS to play it on the TV.",
    "The house list is one watchlist everyone adds to.",
  ],
  games: [
    "Ctrl+K finds your songs, films and games too: type a name and pick it.",
    "Your in-game save follows you: start on a phone, continue on the TV.",
    "An .ips or .bps patch turns a game you have into its romhack.",
    "Play together finds the games for two players or more.",
    "On a phone the pad is on screen; a Bluetooth controller works too.",
  ],
  house: [
    "Pin a note to the wall so everyone sees it first.",
    "Tick groceries in the shop: they're gone for everyone at once.",
    "Ticks and new tasks are kept offline and sent when you're back.",
  ],
  files: [
    "On a phone, Share → HouseOS sends a photo, a file or a link home.",
    "The films and songs the house keeps are here too, ready to download.",
    "Your space is private until you share something from it.",
  ],
  "smart-home": [
    "Lights, plugs, blinds and heating, from any phone in the house.",
    "Ask Nox to turn the living room lights off.",
  ],
  inbox: [
    "Write to one person or to the whole house.",
    "A number on your picture, top right, means new messages.",
  ],
  space: ["Make this room yours: art, news and your saved titles."],
  me: [
    "Pick your own theme: only you see it.",
    "Turn notifications on to hear about messages and finished downloads.",
  ],
  control: [
    "Health says what's failing, and what already fixed itself.",
    "Invite someone with a code, choosing exactly what they may use.",
  ],
};

/** A tip for the room, drawn once per visit. */
export function useTip(room?: string) {
  const [pick] = useState(() => Math.random());
  const tips = room ? TIPS[room] : undefined;
  return tips ? t(tips[Math.floor(pick * tips.length)]) : undefined;
}

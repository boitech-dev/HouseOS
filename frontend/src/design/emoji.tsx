// The emoji row for message composers: emoji here are content a person adds to a message, never
// icons (the design check leaves files named for emoji alone).
import { t } from "../i18n";

const EMOJI = [
  "🦇",
  "🌙",
  "✨",
  "🎶",
  "🍿",
  "👻",
  "🔥",
  "💜",
  "😂",
  "🥹",
  "😴",
  "🙏",
  "👍",
  "🎉",
  "🍕",
];

/** A row of emoji; a tap inserts one where the cursor is. */
export function EmojiTray({ onPick }: { onPick: (emoji: string) => void }) {
  return (
    <div className="ds-emoji" role="group" aria-label={t("Emoji")}>
      {EMOJI.map((emoji) => (
        <button
          key={emoji}
          type="button"
          aria-label={t("Add an emoji") + " " + emoji}
          onClick={() => onPick(emoji)}
        >
          {emoji}
        </button>
      ))}
    </div>
  );
}

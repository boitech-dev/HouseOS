// Art slots: the only places decoration may live (docs/design/SYSTEM.md). A theme fills a slot
// in its manifest (`slots`) with a scene generator or an image of its own; Base leaves them all
// empty, and every layout is right with every slot empty.
import { useEffect, useState } from "react";
import { t } from "../i18n";
import { hallShader, roomShader, sceneUrl, seedOf, timeBucket } from "../pixel";
import { SLOTS, type SlotFill } from "./generated/themes";
import { pictureFor, usePlace, useTheme, useThemeInfo } from "./theme";

export type SlotId = keyof typeof SLOTS;
export { SLOTS };
export type { SlotFill };

/** What the theme in force (or a scoped preview's) puts in a slot (undefined: nothing). */
export function useSlot(id: SlotId): SlotFill | undefined {
  const { room, scheme } = usePlace();
  return pictureFor(useThemeInfo()?.slots[id], room, scheme);
}

/** A slot as the theme fills it: a painted scene or an image, always decorative. */
export function Slot({
  id,
  className,
  width = 240,
  height = 72,
  lit = 0,
  seed = "",
}: {
  id: SlotId;
  className?: string;
  width?: number;
  height?: number;
  lit?: number;
  seed?: string;
}) {
  const fill = useSlot(id);
  if (!fill) return null;
  // An image: as the theme says (pixel art keeps hard edges by default; smooth art is smoothed;
  // "contain" shows it whole instead of filling the box).
  if (typeof fill === "string" || "image" in fill)
    return (
      <img
        className={className}
        src={typeof fill === "string" ? fill : fill.image}
        data-slot-rendering={typeof fill === "string" ? "pixel" : (fill.rendering ?? "pixel")}
        data-slot-fit={typeof fill === "string" ? "cover" : (fill.fit ?? "cover")}
        alt=""
        aria-hidden="true"
        draggable={false}
      />
    );
  if (fill.scene === "room") {
    const room = seedOf(seed || "room");
    const src = sceneUrl(
      "room:" + room + ":" + timeBucket(),
      160,
      72,
      roomShader({ w: 160, h: 72, seed: room }),
    );
    return <img className={className} src={src} alt="" aria-hidden="true" draggable={false} />;
  }
  return <Scene className={className} width={width} height={height} lit={lit} houseAt={0.5} />;
}

/** The house under the real sky (the "hall" scene generator), windows lit for `lit` residents. Re-rendered every 30 min. */
export function Scene({
  width = 192,
  height = 48,
  lit = 0,
  date,
  houseAt = 0.04,
  label,
  className = "",
}: {
  width?: number;
  height?: number;
  lit?: number;
  date?: Date;
  /** Horizontal position of the house, as a fraction of the width. */
  houseAt?: number;
  label?: string;
  className?: string;
}) {
  const [bucket, setBucket] = useState(timeBucket);
  useTheme(); // painted in the theme's colours
  useEffect(() => {
    const id = setInterval(() => setBucket(timeBucket()), 60000);
    return () => clearInterval(id);
  }, []);
  const at = date ?? new Date();
  const src = sceneUrl(
    `hall:${width}x${height}:${lit}:${houseAt}:${date ? timeBucket(date) : bucket}`,
    width,
    height,
    hallShader({
      w: width,
      h: height,
      lit,
      date: at,
      house: {
        x: Math.round(width * houseAt),
        y: Math.round(height * 0.14),
        w: Math.round(height * 1.5),
        h: Math.round(height * 0.86),
      },
    }),
  );
  return (
    <img
      className={"ds-scene " + className}
      src={src}
      width={width}
      height={height}
      alt={label ? t(label) : ""}
      aria-hidden={label ? undefined : true}
      draggable={false}
    />
  );
}

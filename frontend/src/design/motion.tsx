// Motion (the person's level, with the device's reduced-motion request) and pixel sprites, which
// animate only as far as motion allows and are drawn in the theme's colours.
import { useEffect, useRef, useState } from "react";
import { t } from "../i18n";
import { spriteSize, spriteUrl, type Grid } from "../sprites";
import { useTheme } from "./theme";

export type Motion = "still" | "subtle" | "full";
/** The motion level actually in force: the resident's choice, with the device's
 *  reduced-motion request meaning "still" unless they explicitly chose "full". */
export function effectiveMotion(): Motion {
  const chosen = document.documentElement.dataset.motion;
  if (chosen === "full") return "full";
  if (chosen === "still" || matchMedia("(prefers-reduced-motion: reduce)").matches) return "still";
  return "subtle";
}
const motionListeners = new Set<() => void>();
function publishMotion() {
  document.documentElement.dataset.motionEffective = effectiveMotion();
  motionListeners.forEach((listener) => listener());
}
if (typeof document !== "undefined") {
  new MutationObserver(publishMotion).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-motion"],
  });
  matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", publishMotion);
  publishMotion();
}
export function useMotion(): Motion {
  const [motion, setMotion] = useState(effectiveMotion);
  useEffect(() => {
    const update = () => setMotion(effectiveMotion());
    motionListeners.add(update);
    return () => void motionListeners.delete(update);
  }, []);
  return motion;
}

/** A pixel sprite. Several frames animate only when motion allows: ambient loops at
 *  "full", feedback animations (ambient=false) at "subtle" too; paused while hidden. */
export function Sprite({
  grid,
  frames,
  fps = 3,
  scale = 2,
  ambient = true,
  label,
  className = "",
  fit,
}: {
  grid?: Grid;
  frames?: readonly Grid[];
  fps?: number;
  scale?: number;
  ambient?: boolean;
  label?: string;
  className?: string;
  /** Draw into this box instead of the grid's own size (a redrawn piece in a fixed place). */
  fit?: { width: number; height: number } | false;
}) {
  const motion = useMotion();
  useTheme(); // drawn in the theme's colours
  const list = frames ?? (grid ? [grid] : []);
  const [index, setIndex] = useState(0);
  const animate = list.length > 1 && (motion === "full" || (!ambient && motion === "subtle"));
  useEffect(() => {
    if (!animate) return setIndex(0);
    const id = setInterval(() => {
      if (!document.hidden) setIndex((n) => n + 1);
    }, 1000 / fps);
    return () => clearInterval(id);
  }, [animate, fps]);
  const current = list[index % Math.max(1, list.length)];
  if (!current) return null;
  const { width, height } = spriteSize(current);
  return (
    <img
      className={"ds-sprite " + className}
      src={spriteUrl(current)}
      width={fit ? fit.width : width * scale}
      height={fit ? fit.height : height * scale}
      data-fit={fit ? "" : undefined}
      alt={label ? t(label) : ""}
      aria-hidden={label ? undefined : true}
      draggable={false}
    />
  );
}

/** Brings something that just appeared (an error, a question, the next step) into view, once
 *  per new value of `when`; nothing moves when it is already visible. `focus` picks a control
 *  inside it to focus. */
export function useReveal<T extends HTMLElement>(when: unknown, focus?: string) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!when) return;
    const frame = requestAnimationFrame(() => {
      // The person's motion setting (and the system's reduced motion) decide: still → a jump.
      const still = effectiveMotion() === "still";
      ref.current?.scrollIntoView({ block: "nearest", behavior: still ? "auto" : "smooth" });
      if (focus) ref.current?.querySelector<HTMLElement>(focus)?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [when]);
  return ref;
}

// Layers: pictures a theme moves (theme.json "layers", themes/README.md). Drawn behind a place's
// content, or `above` the page at a low opacity, and never catching a click. How much they move is
// the person's motion level: still shows the first frame, with nothing crossing or rising;
// subtle adds drifting, frames, crossings and half the particles; full adds all the particles
// and parallax (pictures following the pointer and the scroll by their depth).
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Layer } from "./generated/themes";
import { useMotion, type Motion } from "./motion";
import { usePlace, useThemeInfo } from "./theme";

export type LayerPlace = Layer["where"];

/** The theme's layers for one place, in the room shown. In a preview (a ThemeScope: pickers,
 *  the Workbench) they hold still, as Home shows them. */
export function ThemeLayers({
  where,
  above = false,
  under = false,
  playing = false,
}: {
  where: LayerPlace;
  /** The page's layers drawn over the content (grain, scanlines), not behind it. */
  above?: boolean;
  /** The layers behind the place's own picture (a sky seen through it); others go over it. */
  under?: boolean;
  /** Music is playing: layers marked `playing` move only then. */
  playing?: boolean;
}) {
  const info = useThemeInfo();
  const { preview, room, scheme } = usePlace();
  const motion = useMotion();
  // The place's size: a piece too big for it is drawn a whole step smaller, never cropped.
  const [box, setBox] = useState<[number, number] | null>(null);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!host) return;
    const watch = new ResizeObserver(() => setBox([host.clientWidth, host.clientHeight]));
    watch.observe(host);
    return () => watch.disconnect();
  }, [host]);
  const shown = (info?.layers ?? []).filter(
    (layer) =>
      layer.where === where &&
      !!layer.above === above &&
      !!layer.under === under &&
      (!layer.rooms || layer.rooms.includes(room)) &&
      (!layer.schemes || layer.schemes.includes(scheme as never)),
  );
  if (!shown.length) return null;
  const level: Motion = preview ? "still" : motion;
  return (
    <div
      ref={setHost}
      className="ds-layers"
      data-where={where}
      data-above={above || undefined}
      data-under={under || undefined}
      aria-hidden="true"
    >
      {shown.map((layer, n) => (
        <OneLayer key={n + layer.image} layer={layer} level={level} playing={playing} box={box} />
      ))}
    </div>
  );
}

const sizes = new Map<string, [number, number]>();
/** A picture's own size (for tiles, frames and pictures drawn at their size), once loaded. */
function useNaturalSize(src: string) {
  const [size, setSize] = useState(sizes.get(src));
  useEffect(() => {
    if (sizes.has(src)) return setSize(sizes.get(src));
    const image = new Image();
    image.onload = () => {
      sizes.set(src, [image.naturalWidth, image.naturalHeight]);
      setSize(sizes.get(src));
    };
    image.src = src;
  }, [src]);
  return size;
}

const POSITION: Record<string, string> = {
  center: "50% 50%",
  top: "50% 0%",
  bottom: "50% 100%",
  left: "0% 50%",
  right: "100% 50%",
  "top-left": "0% 0%",
  "top-right": "100% 0%",
  "bottom-left": "0% 100%",
  "bottom-right": "100% 100%",
};

function OneLayer({
  layer,
  level,
  playing,
  box,
}: {
  layer: Layer;
  level: Motion;
  playing: boolean;
  box: [number, number] | null;
}) {
  const size = useNaturalSize(layer.image);
  const fit = layer.fit ?? "cover";
  const frames = layer.frames?.count ?? 1;
  // A piece fits its place: its own scale when there's room; else the largest whole scale from 2
  // up (pixels stay square); below that, exactly the room there is (never cropped, never tiny).
  const room =
    size && box && box[1] > 0 ? Math.min(box[0] / (size[0] / frames), box[1] / size[1]) : 0;
  const scale =
    fit === "natural" && room && !layer.cross && room < (layer.scale ?? 1)
      ? room >= 2
        ? Math.floor(room)
        : room
      : (layer.scale ?? 1);
  const tile = size ? [(size[0] * scale) / frames, size[1] * scale] : null;
  const moving = level !== "still" && (!layer.playing || playing);
  if ((layer.particles || layer.cross) && level === "still") return null;
  const style = {
    "--layer-image": `url("${layer.image}")`,
    "--layer-opacity": layer.opacity ?? 1,
    "--layer-blend": layer.blend ?? "normal",
    "--layer-render": layer.rendering === "smooth" ? "auto" : "pixelated",
    "--layer-position": POSITION[layer.anchor ?? "center"],
    "--layer-size":
      fit === "cover" || fit === "contain"
        ? fit
        : size
          ? `${size[0] * scale}px ${size[1] * scale}px`
          : "auto",
    "--layer-repeat": fit === "repeat" ? "repeat" : fit === "repeat-x" ? "repeat-x" : "no-repeat",
    ...(tile && { "--layer-w": `${tile[0]}px`, "--layer-h": `${tile[1]}px` }),
  } as CSSProperties;
  if (layer.particles)
    return tile ? <Particles layer={layer} level={level} style={style} moving={moving} /> : null;
  return (
    <Moving
      layer={layer}
      level={level}
      moving={moving}
      tile={tile}
      style={style}
      piece={fit === "natural"}
      scale={scale}
    />
  );
}

/** One picture: the whole place (cover, contain, tiles) or a piece of its size at its anchor. */
function Moving({
  layer,
  level,
  moving,
  tile,
  style,
  piece,
  scale,
}: {
  layer: Layer;
  level: Motion;
  moving: boolean;
  tile: number[] | null;
  style: CSSProperties;
  piece: boolean;
  /** The scale it is drawn at (its own, or fitted to its place): its burst's bits follow it. */
  scale: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || !tile || !moving) return;
    const running: Animation[] = [];
    const [vx, vy] = layer.drift ?? [0, 0];
    // A drift moves the tiles by exactly one tile per loop: seamless, at any speed.
    if (vx)
      running.push(
        node.animate(
          { backgroundPositionX: ["0px", `${Math.sign(vx) * tile[0]}px`] },
          { duration: (tile[0] / Math.abs(vx)) * 1000, iterations: Infinity },
        ),
      );
    if (vy)
      running.push(
        node.animate(
          { backgroundPositionY: ["0px", `${Math.sign(vy) * tile[1]}px`] },
          { duration: (tile[1] / Math.abs(vy)) * 1000, iterations: Infinity },
        ),
      );
    if (layer.frames) {
      const fps = layer.frames.fps ?? 6;
      running.push(
        node.animate(
          { backgroundPositionX: ["0px", `${-tile[0] * layer.frames.count}px`] },
          {
            duration: (layer.frames.count / fps) * 1000,
            iterations: Infinity,
            easing: `steps(${layer.frames.count})`,
          },
        ),
      );
    }
    if (layer.cross) {
      // Across the place now and then: out of sight between crossings.
      const { seconds, every = seconds, from = "left" } = layer.cross;
      const [start, end] = {
        left: ["-100% 0", "100cqw 0"],
        right: ["100cqw 0", "-100% 0"],
        top: ["0 -100%", "0 100cqh"],
        bottom: ["0 100cqh", "0 -100%"],
      }[from];
      const share = seconds / every;
      running.push(
        node.animate(
          [
            // Seen only while the animation places it (hidden before it starts: no flash on load).
            { translate: start, opacity: layer.opacity ?? 1, offset: 0 },
            { translate: end, opacity: layer.opacity ?? 1, offset: share },
            { translate: end, opacity: 0, offset: 1 },
          ],
          {
            duration: every * 1000,
            iterations: Infinity,
            delay: Math.min(every / 3, 5) * 1000, // the first pass soon after the page opens
            fill: "backwards",
          },
        ),
      );
    }
    return () => running.forEach((animation) => animation.cancel());
  }, [moving, tile?.[0], tile?.[1], layer]);
  useParallax(ref, level === "full" ? (layer.depth ?? 0) : 0);
  const poke =
    piece && level !== "still" && tile && layer.poke && mouse.matches ? layer.poke : null;
  return (
    <div
      ref={ref}
      className="ds-layer"
      data-piece={piece || undefined}
      data-poke={poke ? "" : undefined}
      onClick={poke ? (event) => answer(event.currentTarget, poke, tile!, layer, scale) : undefined}
      data-crossing={layer.cross ? (layer.cross.from ?? "left") : undefined}
      data-anchor={layer.anchor ?? "center"}
      style={style}
    />
  );
}

// A piece that answers a click (theme.json layer "poke"): desktop only (a mouse), purely for fun.
const rests = new WeakMap<HTMLElement, Animation>();
const mouse = matchMedia("(hover: hover) and (pointer: fine)");
/** The reaction: its sheet played once over the piece, and maybe a few bits flying out. */
function answer(
  node: HTMLElement,
  poke: NonNullable<Layer["poke"]>,
  tile: number[],
  layer: Layer,
  scale: number,
) {
  const { count, fps = 10 } = poke.frames;
  const sheet = [`url("${poke.image ?? layer.image}")`, `url("${poke.image ?? layer.image}")`];
  const size = [`${tile[0] * count}px ${tile[1]}px`, `${tile[0] * count}px ${tile[1]}px`];
  const played = node.animate(
    {
      backgroundImage: sheet,
      backgroundSize: size,
      backgroundPositionX: ["0px", `${-tile[0] * count}px`],
    },
    { duration: (count / fps) * 1000, easing: `steps(${count})` },
  );
  // "stay": "random": the piece keeps one of the reaction's frames, a new one each click.
  if (poke.stay === "random")
    played.finished.then(
      () => {
        const at = `${-tile[0] * Math.floor(Math.random() * count)}px`;
        rests.get(node)?.cancel();
        rests.set(
          node,
          node.animate(
            { backgroundImage: sheet, backgroundSize: size, backgroundPositionX: [at, at] },
            { duration: 1, fill: "forwards" },
          ),
        );
      },
      () => {},
    );
  if (!poke.burst) return;
  const bits = new Image();
  bits.src = poke.burst.image;
  bits.onload = () => {
    const [w, h] = [bits.naturalWidth * scale, bits.naturalHeight * scale];
    for (let n = 0; n < poke.burst!.count; n++) {
      const bit = document.createElement("span");
      bit.className = "ds-layer__bit";
      bit.style.setProperty("--layer-image", `url("${poke.burst!.image}")`);
      bit.style.setProperty("--layer-w", `${w}px`);
      bit.style.setProperty("--layer-h", `${h}px`);
      bit.style.left = `${node.offsetLeft + node.offsetWidth / 2 - w / 2}px`;
      bit.style.top = `${node.offsetTop + node.offsetHeight / 2 - h / 2}px`;
      node.parentElement?.append(bit);
      const angle = (n / poke.burst!.count) * Math.PI * 2 + Math.random() * 0.6;
      const reach = 24 + Math.random() * 24;
      bit
        .animate(
          [
            { translate: "0 0", opacity: 1 },
            {
              translate: `${Math.cos(angle) * reach}px ${Math.sin(angle) * reach - 12}px`,
              opacity: 0,
            },
          ],
          { duration: 700 + Math.random() * 300, easing: "ease-out" },
        )
        .finished.then(
          () => bit.remove(),
          () => bit.remove(),
        );
    }
  };
}

/** A seeded spread, so the same theme scatters its particles the same way every time. */
function spread(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
}
const PATHS: Record<string, (x: number) => Keyframe[]> = {
  rise: (x) => [
    { translate: `${x}cqw 100cqh`, opacity: 0 },
    { opacity: 1, offset: 0.2 },
    { opacity: 0.8, offset: 0.7 },
    { translate: `${x + 4}cqw -10cqh`, opacity: 0 },
  ],
  fall: (x) => [
    { translate: `${x}cqw -10cqh`, opacity: 0 },
    { opacity: 1, offset: 0.15 },
    { translate: `${x - 6}cqw 100cqh`, opacity: 1 },
  ],
  float: (x) => [
    { translate: `${x}cqw 60cqh`, opacity: 0 },
    { translate: `${x + 5}cqw 40cqh`, opacity: 1, offset: 0.5 },
    { translate: `${x + 10}cqw 20cqh`, opacity: 0 },
  ],
  twinkle: () => [
    { opacity: 0, scale: 0.6 },
    { opacity: 1, scale: 1, offset: 0.5 },
    { opacity: 0, scale: 0.6 },
  ],
};

function Particles({
  layer,
  level,
  style,
  moving,
}: {
  layer: Layer;
  level: Motion;
  style: CSSProperties;
  moving: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { count, motion, seconds = 8 } = layer.particles!;
  const shown = level === "full" ? count : Math.ceil(count / 2);
  useEffect(() => {
    const node = ref.current;
    if (!node || !moving) return;
    const random = spread(count * 7919 + seconds);
    const running = [...node.children].map((child) => {
      const x = random() * 100;
      const y = random() * 100;
      const path = PATHS[motion](x);
      if (motion === "twinkle") (child as HTMLElement).style.translate = `${x}cqw ${y}cqh`;
      return child.animate(path, {
        duration: seconds * 1000 * (0.75 + random() * 0.5),
        delay: -random() * seconds * 1000,
        iterations: Infinity,
      });
    });
    return () => running.forEach((animation) => animation.cancel());
  }, [moving, shown, motion, seconds]);
  if (!moving) return null;
  return (
    <div ref={ref} className="ds-layer" data-particles style={style}>
      {Array.from({ length: shown }, (_, n) => (
        <span key={n} />
      ))}
    </div>
  );
}

// Parallax: one listener for every layer with a depth, moving it up to 24px against the pointer
// and a little with the scroll. Only at full motion; nothing listens when no layer needs it.
const deep = new Map<HTMLElement, number>();
let pointer = [0, 0];
let queued = 0;
function place() {
  queued = 0;
  const scroll = Math.min(1, scrollY / innerHeight);
  for (const [node, depth] of deep)
    node.style.translate = `${-pointer[0] * depth * 24}px ${(-pointer[1] - scroll) * depth * 24}px`;
}
function moved(event?: PointerEvent) {
  if (event) pointer = [event.clientX / innerWidth - 0.5, event.clientY / innerHeight - 0.5];
  queued ||= requestAnimationFrame(place);
}
const onScroll = () => moved();
function useParallax(ref: React.RefObject<HTMLDivElement | null>, depth: number) {
  useEffect(() => {
    const node = ref.current;
    if (!node || !depth) return;
    if (!deep.size) {
      addEventListener("pointermove", moved, { passive: true });
      addEventListener("scroll", onScroll, { passive: true });
    }
    deep.set(node, depth);
    return () => {
      deep.delete(node);
      node.style.translate = "";
      if (!deep.size) {
        removeEventListener("pointermove", moved);
        removeEventListener("scroll", onScroll);
      }
    };
  }, [depth]);
}

// Code-only illustration for Midnight House: ordered-dither "shaders" rendered on a tiny
// canvas and scaled with nearest-neighbour. Every colour is a theme token (color.scene.*), so
// scenes, placeholders and sprites belong to the same world in any theme.
import { palette, themeKey } from "./design/theme";

const SCENE = {
  night0: "--c-scene-night-0",
  night1: "--c-scene-night-1",
  night2: "--c-scene-night-2",
  line: "--c-scene-line",
  lineHi: "--c-scene-line-hi",
  mist: "--c-scene-mist",
  cream: "--c-scene-cream",
  ember: "--c-scene-ember",
  emberHi: "--c-scene-ember-hi",
  emberDeep: "--c-scene-ember-deep",
  lilac: "--c-scene-lilac",
  moss: "--c-scene-moss",
} as const;
/** The scene colours of the theme in force. */
const PALETTE = new Proxy({} as Record<keyof typeof SCENE, string>, {
  get: (_, name: keyof typeof SCENE) => palette(SCENE)[name],
});

type RGB = readonly [number, number, number];
const rgbCache = new Map<string, RGB>();
function rgb(hex: string): RGB {
  let value = rgbCache.get(hex);
  if (!value) {
    value = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as unknown as RGB;
    rgbCache.set(hex, value);
  }
  return value;
}

// 8×8 Bayer matrix: thresholds in (0, 1).
const BAYER = [
  0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28,
  52, 20, 62, 30, 54, 22, 3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7,
  39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21,
];
export const threshold = (x: number, y: number) => (BAYER[(y & 7) * 8 + (x & 7)] + 0.5) / 64;

/** A pixel is either one colour, or a mix `[from, to, t]` resolved by ordered dithering. */
export type Shade = string | readonly [string, string, number] | null;
export type Shader = (x: number, y: number) => Shade;

export function paint(canvas: HTMLCanvasElement, shader: Shader) {
  const { width: w, height: h } = canvas;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const image = ctx.createImageData(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const shade = shader(x, y);
      if (!shade) continue;
      const hex =
        typeof shade === "string" ? shade : shade[2] > threshold(x, y) ? shade[1] : shade[0];
      const [r, g, b] = rgb(hex);
      image.data.set([r, g, b, 255], (y * w + x) * 4);
    }
  }
  ctx.putImageData(image, 0, 0);
}

const urlCache = new Map<string, string>();
/** Render once per key and reuse the PNG data URL (scenes change at most every 30 min). */
export function sceneUrl(key: string, w: number, h: number, shader: Shader) {
  key = themeKey() + ":" + key;
  let url = urlCache.get(key);
  if (!url) {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    paint(canvas, shader);
    url = canvas.toDataURL("image/png");
    if (urlCache.size > 64) urlCache.delete(urlCache.keys().next().value!);
    urlCache.set(key, url);
  }
  return url;
}

/** Deterministic 0..1 noise for stars, textures and seeds. */
export function hash(x: number, y: number, seed = 0) {
  let h = (x * 374761393 + y * 668265263 + seed * 2246822519) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export function seedOf(text: string) {
  let h = 2166136261;
  for (const char of text) h = Math.imul(h ^ char.charCodeAt(0), 16777619);
  return h >>> 0;
}

// ---------- time of day and the moon ----------
export type Daypart = "night" | "dusk" | "dawn" | "day";
export function daypart(date = new Date()): Daypart {
  const hour = date.getHours() + date.getMinutes() / 60;
  if (hour >= 21 || hour < 5) return "night";
  if (hour >= 18) return "dusk";
  if (hour < 8) return "dawn";
  return "day";
}

/** 0 = new moon, 0.5 = full moon. */
export function moonPhase(date = new Date()) {
  const synodic = 29.530588853;
  const days = (date.getTime() - Date.UTC(2000, 0, 6, 18, 14)) / 86400000;
  return (((days / synodic) % 1) + 1) % 1;
}

function moonLit(dx: number, dy: number, phase: number) {
  const edge = Math.sqrt(Math.max(0, 1 - dy * dy));
  const k = Math.cos(2 * Math.PI * phase) * edge;
  return phase < 0.5 ? dx > k : dx < -k;
}

const SKIES = (): Record<Daypart, { top: string; low: string; horizon: string; stars: number }> => ({
  night: { top: PALETTE.night0, low: PALETTE.night1, horizon: PALETTE.night2, stars: 0.012 },
  dusk: { top: PALETTE.night1, low: PALETTE.night2, horizon: PALETTE.emberDeep, stars: 0.005 },
  dawn: { top: PALETTE.night2, low: PALETTE.line, horizon: PALETTE.lilac, stars: 0.002 },
  day: { top: PALETTE.line, low: PALETTE.lineHi, horizon: PALETTE.mist, stars: 0 },
});

// ---------- the house ----------
type Box = { x: number; y: number; w: number; h: number };
const WINDOWS: readonly (readonly [number, number])[] = [
  [0.13, 0.36],
  [0.13, 0.58],
  [0.33, 0.56],
  [0.45, 0.56],
  [0.57, 0.56],
  [0.8, 0.47],
  [0.8, 0.66],
  [0.33, 0.76],
  [0.66, 0.76],
];

/** Where each window sits, so callers can light windows for residents who are around. */

function inTriangle(u: number, v: number, left: number, right: number, top: number, base: number) {
  if (v < top || v > base) return false;
  const half = ((right - left) / 2) * ((v - top) / (base - top));
  const mid = (left + right) / 2;
  return u >= mid - half && u <= mid + half;
}

function inHouse(u: number, v: number) {
  return (
    (u >= 0.18 && u <= 0.74 && v >= 0.46) ||
    inTriangle(u, v, 0.16, 0.76, 0.24, 0.46) ||
    (u >= 0.04 && u <= 0.23 && v >= 0.2) ||
    inTriangle(u, v, 0.02, 0.25, 0.02, 0.2) ||
    (u >= 0.71 && u <= 0.9 && v >= 0.32) ||
    inTriangle(u, v, 0.69, 0.92, 0.12, 0.32) ||
    (u >= 0.6 && u <= 0.65 && v >= 0.28 && v <= 0.46)
  );
}

/** Returns what the house covers at (u, v) in its own 0..1 box. */
function housePart(u: number, v: number, lit: number): "wall" | "edge" | "lit" | "dark" | null {
  if (!inHouse(u, v)) return null;
  for (let i = 0; i < WINDOWS.length; i++) {
    const [wx, wy] = WINDOWS[i];
    const du = u - wx;
    const dv = v - wy;
    const arch =
      dv < 0 ? Math.hypot(du / 0.026, dv / 0.03) <= 1 : Math.abs(du) <= 0.026 && dv <= 0.07;
    if (arch) return i < lit ? "lit" : "dark";
  }
  if (u >= 0.44 && u <= 0.5 && v >= 0.86) return "dark"; // door
  const edge = u < 0.2 || (v > 0.46 && v < 0.49) || u > 0.88;
  return edge ? "edge" : "wall";
}

export type HallOptions = { w: number; h: number; date?: Date; lit?: number; house?: Box };

/** The house on its hill under the real sky: the signature scene. */
export function hallShader({ w, h, date = new Date(), lit = 0, house }: HallOptions): Shader {
  const part = daypart(date);
  const sky = SKIES()[part];
  const phase = moonPhase(date);
  const hour = date.getHours() + date.getMinutes() / 60;
  const arc = ((hour + 6) % 24) / 24; // the moon crosses the strip through the night
  const moon = {
    x: w * (0.55 + 0.35 * Math.sin(arc * Math.PI)),
    y: h * 0.28,
    r: Math.max(3, h * 0.12),
  };
  const box = house ?? {
    x: Math.round(w * 0.04),
    y: Math.round(h * 0.18),
    w: Math.round(h * 1.5),
    h: Math.round(h * 0.82),
  };
  const windowColor = part === "day" ? PALETTE.emberDeep : PALETTE.ember;
  return (x, y) => {
    const u = (x - box.x) / box.w;
    const v = (y - box.y) / box.h;
    if (u >= 0 && u <= 1 && v >= 0 && v <= 1) {
      const piece = housePart(u, v, lit);
      // Moonlight catches roofs and the towers' left faces.
      if (piece && piece !== "lit" && (!inHouse(u, v - 1 / box.h) || !inHouse(u - 1 / box.w, v)))
        return part === "day" ? PALETTE.mist : PALETTE.lineHi;
      if (piece === "lit")
        return v - Math.floor(v * 40) / 40 < 0.01 ? PALETTE.emberHi : windowColor;
      if (piece === "dark") return PALETTE.night2;
      if (piece === "edge") return [PALETTE.night0, PALETTE.line, 0.35];
      if (piece === "wall")
        return [PALETTE.night0, PALETTE.night2, 0.25 + 0.2 * hash(x >> 1, y >> 1, 7)];
    }
    // hills and far rooftops
    const ridge = h * (0.78 + 0.06 * Math.sin(x * 0.07) + 0.03 * Math.sin(x * 0.23));
    if (y > ridge) return [PALETTE.night0, PALETTE.night1, 0.5 - (y - ridge) / h];
    const far = h * (0.7 + 0.05 * Math.sin(x * 0.13 + 1)) - (x % 23 < 4 ? h * 0.06 : 0);
    if (y > far) return [PALETTE.night1, PALETTE.night2, 0.35];
    // moon
    if (part !== "day") {
      const dx = (x - moon.x) / moon.r;
      const dy = (y - moon.y) / moon.r;
      if (dx * dx + dy * dy <= 1) return moonLit(dx, dy, phase) ? PALETTE.cream : sky.low;
    }
    if (sky.stars && hash(x, y, 3) < sky.stars && y < h * 0.6)
      return hash(x, y, 9) > 0.7 ? PALETTE.cream : PALETTE.mist;
    const t = y / (h * 0.8);
    if (t > 0.85) return [sky.low, sky.horizon, (t - 0.85) * 4];
    return [sky.top, sky.low, t];
  };
}

/** A quiet night texture for artwork that is still loading (true colour replaces it). */
export function placeholderUrl(seed: string, w = 24, h = 36) {
  const s = seedOf(seed);
  return sceneUrl("ph:" + s + ":" + w + "x" + h, w, h, (x, y) => [
    PALETTE.night1,
    PALETTE.night2,
    0.08 + 0.18 * (y / h) + 0.12 * hash(x >> 2, y >> 2, s),
  ]);
}

/** A 30-minute bucket so time-of-day scenes are re-rendered at most twice an hour. */
export const timeBucket = (date = new Date()) => Math.floor(date.getTime() / 1800000);

// ---------- your room ----------
/** A small bedroom at the real time of day: arched window onto the sky, desk and lamp,
 *  bed and shelf. `seed` varies the wallpaper and the books; the lamp glows after dusk. */
export function roomShader({
  w,
  h,
  date = new Date(),
  seed = 0,
}: {
  w: number;
  h: number;
  date?: Date;
  seed?: number;
}): Shader {
  const part = daypart(date);
  const sky = SKIES()[part];
  const phase = moonPhase(date);
  const lampOn = part !== "day";
  const win = { x: w * 0.12, y: h * 0.12, w: w * 0.24, h: h * 0.52 };
  const floor = h * 0.8;
  const desk = { x: w * 0.42, y: h * 0.6, w: w * 0.2 };
  const lamp = { x: desk.x + desk.w * 0.8, y: desk.y - h * 0.12 };
  const bed = { x: w * 0.66, y: h * 0.62, w: w * 0.3 };
  const shelf = { x: w * 0.68, y: h * 0.3, w: w * 0.26 };
  const moon = { x: win.x + win.w * 0.68, y: win.y + win.h * 0.32, r: Math.max(2, win.w * 0.14) };
  const books = [PALETTE.emberDeep, PALETTE.lilac, PALETTE.moss, PALETTE.ember, PALETTE.mist];
  return (x, y) => {
    // window: an arch cut in the wall, with a cross mullion
    const u = (x - win.x) / win.w;
    const v = (y - win.y) / win.h;
    const archTop =
      v < 0.35 ? Math.hypot((u - 0.5) / 0.5, (v - 0.35) / 0.35) <= 1 : u >= 0 && u <= 1;
    if (v >= 0 && v <= 1 && u >= -0.08 && u <= 1.08) {
      const inside = archTop && v <= 1;
      const frame =
        !inside &&
        (v < 0.35 ? Math.hypot((u - 0.5) / 0.58, (v - 0.35) / 0.43) <= 1 : u >= -0.08 && u <= 1.08);
      if (frame) return PALETTE.lineHi;
      if (inside) {
        if (Math.abs(u - 0.5) < 0.04 || Math.abs(v - 0.55) < 0.025) return PALETTE.line;
        if (part !== "day") {
          const dx = (x - moon.x) / moon.r;
          const dy = (y - moon.y) / moon.r;
          if (dx * dx + dy * dy <= 1) return moonLit(dx, dy, phase) ? PALETTE.cream : sky.low;
        }
        if (sky.stars && hash(x, y, 11) < sky.stars * 4) return PALETTE.cream;
        const ridge = win.y + win.h * (0.82 + 0.05 * Math.sin(x * 0.4));
        if (y > ridge) return [PALETTE.night0, PALETTE.night1, 0.4];
        return [sky.top, sky.horizon, v * 0.9];
      }
    }
    // floorboards
    if (y >= floor) {
      if (x >= w * 0.3 && x <= w * 0.62 && y >= floor + 2 && y <= h - 3)
        return [PALETTE.emberDeep, PALETTE.lilac, 0.15 + 0.2 * (((x >> 3) + (y >> 2)) & 1)]; // rug
      return (x + (y >> 2) * 7) % 19 === 0
        ? PALETTE.night1
        : [PALETTE.night2, PALETTE.emberDeep, 0.35];
    }
    // bed
    if (x >= bed.x && x <= bed.x + bed.w && y >= bed.y && y < floor) {
      if (y < bed.y + 3 && x < bed.x + bed.w * 0.28) return PALETTE.cream; // pillow
      if (y > floor - 3) return PALETTE.night0;
      return [PALETTE.night2, PALETTE.lilac, 0.28 + 0.1 * hash(x >> 1, y >> 1, seed)];
    }
    if (x >= bed.x - 2 && x <= bed.x && y >= bed.y - h * 0.14 && y < floor) return PALETTE.line; // headboard
    // desk and lamp
    if (y >= desk.y && y <= desk.y + 2 && x >= desk.x && x <= desk.x + desk.w)
      return PALETTE.lineHi;
    if (
      y > desk.y + 2 &&
      y < floor &&
      (Math.abs(x - desk.x - 1) < 1.5 || Math.abs(x - desk.x - desk.w + 1) < 1.5)
    )
      return PALETTE.line;
    if (Math.abs(x - lamp.x) <= 3 && y >= lamp.y && y <= lamp.y + 3)
      return lampOn ? PALETTE.emberHi : PALETTE.mist;
    if (Math.abs(x - lamp.x) < 1 && y > lamp.y + 3 && y < desk.y) return PALETTE.line;
    // shelf with books
    if (y >= shelf.y && y <= shelf.y + 1 && x >= shelf.x && x <= shelf.x + shelf.w)
      return PALETTE.lineHi;
    if (y < shelf.y && y >= shelf.y - 7 && x >= shelf.x + 2 && x <= shelf.x + shelf.w - 2) {
      const book = Math.floor((x - shelf.x) / 3);
      const tall = 4 + Math.floor(hash(book, 1, seed) * 4);
      if (y >= shelf.y - tall && (x - shelf.x) % 3 !== 0)
        return books[Math.floor(hash(book, 2, seed) * books.length)];
    }
    // wall: striped paper, warmed by the lamp after dusk
    const glow = lampOn
      ? Math.max(0, 1 - Math.hypot(x - lamp.x, (y - lamp.y) * 1.3) / (w * 0.22))
      : 0;
    const stripe = (x + (seed & 7)) % 12 < 1 ? 0.1 : 0;
    if (glow > 0.05) return [PALETTE.night2, PALETTE.emberDeep, glow * 0.6 + stripe];
    return part === "day"
      ? [PALETTE.line, PALETTE.lineHi, 0.3 + stripe]
      : [PALETTE.night2, PALETTE.line, 0.25 + stripe];
  };
}

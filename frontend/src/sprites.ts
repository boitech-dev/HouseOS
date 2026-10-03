// Hand-authored pixel sprites for Midnight House. Each sprite is a list of rows; each
// character is one pixel from COLORS ("." is transparent). Rows shorter than the widest
// row are padded, so a grid only has to be drawn, not counted.

import { palette, themeKey } from "./design/theme";

// Each letter is a theme token (color.sprite.*): a theme recolours every sprite at once.
const COLORS = {
  k: "--c-sprite-outline",
  n: "--c-sprite-dark",
  l: "--c-sprite-mid-dark",
  L: "--c-sprite-mid",
  m: "--c-sprite-mist",
  c: "--c-sprite-light",
  C: "--c-sprite-light-dim",
  e: "--c-sprite-accent",
  E: "--c-sprite-accent-hi",
  r: "--c-sprite-accent-deep",
  v: "--c-sprite-familiar",
  V: "--c-sprite-familiar-mid",
  w: "--c-sprite-familiar-deep",
  g: "--c-sprite-good",
  p: "--c-sprite-alert",
  P: "--c-sprite-paper",
  i: "--c-sprite-ink",
};

export type Grid = readonly string[];

// A theme's own sprites (sprites.json) use their own letters, each naming a color.sprite token:
// rewritten into this file's letters, they draw with the same code and the same colours.
const LETTER = Object.fromEntries(
  Object.entries(COLORS).map(([letter, variable]) => [
    variable.slice("--c-sprite-".length),
    letter,
  ]),
);
const grids = new WeakMap<object, Record<string, Grid>>(); // by the theme's sprites (renewed on change)
/** One piece as a theme redraws it ("nox.idle", "avatar.moon", "title.dj"…), or undefined. */
export function themeGrid(
  theme:
    | {
        id: string;
        sprites?: { palette?: Record<string, string>; glyphs?: Record<string, string[]> };
      }
    | undefined,
  id: string,
): Grid | undefined {
  if (!theme?.sprites?.glyphs) return undefined;
  let found = grids.get(theme.sprites);
  if (!found) {
    const palette = theme.sprites.palette ?? {};
    found = Object.fromEntries(
      Object.entries(theme.sprites.glyphs).map(([name, rows]) => [
        name,
        rows.map((row) =>
          [...row]
            .map((letter) => (letter === "." ? "." : (LETTER[palette[letter]] ?? ".")))
            .join(""),
        ),
      ]),
    );
    grids.set(theme.sprites, found);
  }
  return found[id];
}

const urls = new Map<string, Map<Grid, string>>();
/** Crisp SVG data URL in the theme's colours: horizontal runs of one colour become one rect. */
export function spriteUrl(grid: Grid) {
  const theme = themeKey();
  if (!urls.has(theme)) urls.set(theme, new Map());
  const cached = urls.get(theme)!;
  let url = cached.get(grid);
  if (url) return url;
  const colours: Record<string, string> = palette(COLORS);
  const width = Math.max(...grid.map((row) => row.length));
  const rects: string[] = [];
  grid.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const char = row[x];
      let end = x + 1;
      while (end < row.length && row[end] === char) end++;
      if (char !== "." && colours[char])
        rects.push(
          `<rect x="${x}" y="${y}" width="${end - x}" height="1" fill="${colours[char]}"/>`,
        );
      x = end;
    }
  });
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${grid.length}" width="${width}" height="${grid.length}" shape-rendering="crispEdges">${rects.join("")}</svg>`;
  url = "data:image/svg+xml," + encodeURIComponent(svg);
  cached.set(grid, url);
  return url;
}

/** The browser tab's icon: Nox in the theme's colours on a round tile of its surface. */
export function faviconUrl(grid: Grid) {
  const size = spriteSize(grid);
  const side = Math.max(size.width, size.height) + 4;
  const tile = palette({ bg: "--c-bg-surface" });
  const sprite = decodeURIComponent(spriteUrl(grid).slice("data:image/svg+xml,".length))
    .replace(/^<svg[^>]*>/, "")
    .replace(/<\/svg>$/, "");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${side} ${side}" shape-rendering="crispEdges">` +
    `<rect width="${side}" height="${side}" rx="${side / 4}" fill="${tile.bg}"/>` +
    `<g transform="translate(${(side - size.width) / 2} ${(side - size.height) / 2})">${sprite}</g></svg>`;
  return "data:image/svg+xml," + encodeURIComponent(svg);
}

export const spriteSize = (grid: Grid) => ({
  width: Math.max(...grid.map((row) => row.length)),
  height: grid.length,
});

// ---------- Nox, the house familiar ----------
const noxBody = [
  "..kvvvvvvvvvvk..",
  "..kwkvvvvvvkwk..",
  ".kwwkVvvvvVkwwk.",
  ".kwwwkVvvVkwwwk.",
  "..kwwwkVVkwwwk..",
  "...kkk.kk.kkk...",
];
export const NOX: Record<"idle" | "blink" | "listening" | "thinking" | "happy" | "error", Grid> = {
  idle: [
    "................",
    "...k........k...",
    "..kvk......kvk..",
    "..kvvk....kvvk..",
    "..kvvvkkkkvvvk..",
    "...kvvvvvvvvk...",
    "..kvvEkvvkEvvk..",
    ...noxBody,
  ],
  blink: [
    "................",
    "...k........k...",
    "..kvk......kvk..",
    "..kvvk....kvvk..",
    "..kvvvkkkkvvvk..",
    "...kvvvvvvvvk...",
    "..kvvkkvvkkvvk..",
    ...noxBody,
  ],
  listening: [
    "................",
    "...k........k...",
    "..kvk......kvk..",
    "..kvvk....kvvk..",
    "k.kvvvkkkkvvvk.k",
    "kk.kvvvvvvvvk.kk",
    "kwkkvEEvvEEvkkwk",
    "kwwkvEkvvkEvkwwk",
    "kwwwkvvvvvvkwwwk",
    "kwwwwkvvvvkwwwwk",
    ".kwwkkVvvVkkwwk.",
    "..kk.kVVVVk.kk..",
    ".....k.kk.k.....",
  ],
  thinking: [
    "..........e.e.e.",
    "...k........k...",
    "..kvk......kvk..",
    "..kvvk....kvvk..",
    "..kvvvkkkkvvvk..",
    "...kvvvvvvvvk...",
    "..kvvkEvvkEvvk..",
    ...noxBody,
  ],
  happy: [
    "..............g.",
    "...k........kg.g",
    "..kvk......kvkg.",
    "..kvvk....kvvk..",
    "..kvvvkkkkvvvk..",
    "...kvvvvvvvvk...",
    "..kvEvEvvEvEvk..",
    "..kvvvvppvvvvk..",
    ".kwwkVvvvvVkwwk.",
    ".kwwwkVvvVkwwwk.",
    "..kwwwkVVkwwwk..",
    "...kkk.kk.kkk...",
  ],
  error: [
    "................",
    "...k........k...",
    "..kvk......kvk..",
    "..kvvk....kvvk..",
    "..kvvvkkkkvvvk..",
    "...kvvvvvvvvk...",
    "..kvpvpvvpvpvk..",
    "..kvvpvvvvpvvk..",
    ".kwwkVvvvvVkwwk.",
    ".kwwwkVvvVkwwwk.",
    "..kwwwkVVkwwwk..",
    "...kkk.kk.kkk...",
  ],
};

// ---------- the candle (two flicker frames) ----------
const candleBase = ["...k...", "..ccC..", "..ccC..", "..ccC..", "..cCC..", ".rrrrr.", "rrErrrr"];
export const CANDLE: readonly Grid[] = [
  ["...e...", "..eE...", "..eEe..", "...e...", ...candleBase],
  ["...e...", "...Ee..", "..eEe..", "...e...", ...candleBase],
];

// ---------- dock icons (16×16) ----------
type Icon = "home" | "listen" | "watch" | "house" | "files" | "me" | "bulb" | "games" | "more";
export const ICONS: Record<Icon, Grid> = {
  home: [
    "................",
    "..k....k........",
    ".kLk..kLk.......",
    ".kLk.kLlLk......",
    ".kLkkLlllLk.....",
    ".kLkLlllllLk....",
    ".kLLlllllllLk...",
    "kkkkkkkkkkkkkk..",
    ".klekllllklek...",
    ".klrkllllklrk...",
    ".kllllllllllk...",
    ".klllkkkklllk...",
    ".klllkeeklllk...",
    ".klllkeeklllk...",
    "kkkkkkkkkkkkkk..",
  ],
  listen: [
    "................",
    "......kkkkkkkkk.",
    "......keEEEEEEk.",
    "......keeeeeeek.",
    "......kekkkkkek.",
    "......kek....kek",
    "......kek....kek",
    "......kek....kek",
    "......kek....kek",
    "..kkkkkek.kkkkek",
    ".keeeeeek.keeeek",
    "keEEeeeek.keEEek",
    "keeeeeek..keeeek",
    ".keeeek...keeek.",
    "..kkkk.....kkk..",
    "................",
  ],
  watch: [
    "....k.....k.....",
    ".....k...k......",
    "......k.k.......",
    ".kkkkkkkkkkkkk..",
    ".kLLLLLLLLLLLk..",
    ".kLkkkkkkkkkLk..",
    ".kLkeeEEEeekLk..",
    ".kLkeEEEEEekLk..",
    ".kLkeeEEEeekLk..",
    ".kLkreeeeerkLk..",
    ".kLkkkkkkkkkLk..",
    ".kLLLLLLLeLeLk..",
    ".kkkkkkkkkkkkk..",
    "...kk.....kk....",
  ],
  house: [
    "................",
    ".kkkkkkkkkkkkkk.",
    ".krrrrrrrrrrrrk.",
    ".krPPPPr.rPPPrk.",
    ".krPiiPr.rPiPrk.",
    ".krPPPPr.rPPPrk.",
    ".krPiiPr.rPiPrk.",
    ".krPPPPr.rPPPrk.",
    ".krrrrrr.rrrrrk.",
    ".krPPPPPPPPPrrk.",
    ".krPiiiiiPPPrrk.",
    ".krPPPPPPPPPrrk.",
    ".krrrrrrrrrrrrk.",
    ".kkkkkkkkkkkkkk.",
  ],
  // Files: an amber folder with a sheet of paper peeking out.
  files: [
    "................",
    "................",
    ".kkkkk..........",
    ".kEEEEk.........",
    ".kEEEEEkkkkkkkk.",
    ".kekPPPPPPPPkek.",
    ".kekPiiiiiPPkek.",
    ".kkkkkkkkkkkkkk.",
    ".kEEEEEEEEEEEEk.",
    ".kEEEEEEEEEEEEk.",
    ".kEEEEEEEEEEEEk.",
    ".keeeeeeeeeeeek.",
    ".kkkkkkkkkkkkkk.",
  ],
  me: [
    "................",
    ".....kkkkk......",
    "....kmmmmmk.....",
    "...kmmmmmmmk....",
    "...kmckmkcmk....",
    "...kmmmmmmmk....",
    "....kmmpmmk.....",
    ".....kkkkk......",
    "...kkLLLLLkk....",
    "..kLLLLLLLLLk...",
    "..kLLLLeLLLLk...",
    "..kkkkkkkkkkk...",
  ],
  // Games: a pad, its cross on the left and two buttons on the right.
  games: [
    "................",
    "................",
    "................",
    "...kkkkkkkkkk...",
    "..kLLLLLLLLLLk..",
    ".kLLkLLLLLLeLLk.",
    ".kLkkkLLLLeLrLk.",
    ".kLLkLLLLLLrLLk.",
    ".kLLLLLmmLLLLLk.",
    ".kLLLLkkkkLLLLk.",
    "..kLLk....kLLk..",
    "...kk......kk...",
  ],
  // More rooms (the phone dock's "+"): a plus on a tile.
  more: [
    "................",
    "................",
    "..kkkkkkkkkkkk..",
    ".kLLLLLLLLLLLLk.",
    ".kLLLLLkkLLLLLk.",
    ".kLLLLLkkLLLLLk.",
    ".kLLkkkkkkkkLLk.",
    ".kLLkkkkkkkkLLk.",
    ".kLLLLLkkLLLLLk.",
    ".kLLLLLkkLLLLLk.",
    ".kLLLLLLLLLLLLk.",
    "..kkkkkkkkkkkk..",
  ],
  // Smart home: a lit bulb.
  bulb: [
    "................",
    ".....kkkkkk.....",
    "....kEEEEEEk....",
    "...kEEcEEEEEk...",
    "...kEcEEEEEEk...",
    "...kEEEEEEeEk...",
    "...kEEEEEEeEk...",
    "....kEEEEeek....",
    ".....keEeek.....",
    ".....kmmmmk.....",
    ".....kLLLLk.....",
    ".....kmmmmk.....",
    "......kkkk......",
  ],
};

// ---------- transport glyphs (9×9) ----------
export const TRANSPORT: Record<"play" | "pause" | "next" | "previous" | "stop", Grid> = {
  play: [
    "kk.......",
    "kekk.....",
    "keeekk...",
    "keeeeekk.",
    "keeeeeeek",
    "keeeeekk.",
    "keeekk...",
    "kekk.....",
    "kk.......",
  ],
  pause: [
    "kkk..kkk.",
    "kek..kek.",
    "kek..kek.",
    "kek..kek.",
    "kek..kek.",
    "kek..kek.",
    "kek..kek.",
    "kek..kek.",
    "kkk..kkk.",
  ],
  next: [
    "k.....kk.",
    "kek...kek",
    "keek..kek",
    "keeek.kek",
    "keeeekkek",
    "keeek.kek",
    "keek..kek",
    "kek...kek",
    "k.....kk.",
  ],
  previous: [
    ".kk.....k",
    "kek...kek",
    "kek..keek",
    "kek.keeek",
    "kekkeeeek",
    "kek.keeek",
    "kek..keek",
    "kek...kek",
    ".kk.....k",
  ],
  stop: [
    "kkkkkkkk.",
    "keeeeeek.",
    "keeeeeek.",
    "keeeeeek.",
    "keeeeeek.",
    "keeeeeek.",
    "keeeeeek.",
    "kkkkkkkk.",
    ".........",
  ],
};

// ---------- resident avatars (12×12), matching the profile choices ----------
export const AVATARS: Record<"crest" | "moon" | "bat" | "raven" | "rose" | "ghost", Grid> = {
  moon: [
    "....kkkk....",
    "..kkcccck...",
    ".kcccckk....",
    ".kccck......",
    "kcccck......",
    "kcccck......",
    "kcccck......",
    ".kccck......",
    ".kccccck....",
    "..kkccccck..",
    "....kkkkk...",
  ],
  crest: [
    ".kkkkkkkkkk.",
    ".kLLLLLLLLk.",
    ".kLeLLLLeLk.",
    ".kLLLeeLLLk.",
    ".kLLeEEeLLk.",
    ".kLLLeeLLLk.",
    ".kLeLLLLeLk.",
    "..kLLLLLLk..",
    "...kLLLLk...",
    "....kLLk....",
    ".....kk.....",
  ],
  bat: [
    "..k......k..",
    ".kvk....kvk.",
    ".kvvkkkkvvk.",
    "..kvvvvvvk..",
    ".kvEkvvkEvk.",
    "kwkvvvvvvkwk",
    "kwwkVvvVkwwk",
    ".kwwkVVkwwk.",
    "..kk.kk.kk..",
  ],
  raven: [
    "....kkkk....",
    "...kLLLLk...",
    "..kLLeLLLk..",
    "kkkLLLLLLk..",
    "kmmkLLLLLk..",
    ".kkLLLLLLLk.",
    "...kLLLLLLLk",
    "...kLLLLLLk.",
    "....kkLkLk..",
    "......k.k...",
  ],
  rose: [
    "...kkkkk....",
    "..kppppppk..",
    ".kpkppppkpk.",
    ".kppkppkppk.",
    ".kpppkkpppk.",
    "..kppppppk..",
    "...kkkkkk...",
    ".....kg.....",
    "..kk.kg.....",
    "..kgkkg.....",
    "....kgk.....",
  ],
  ghost: [
    "...kkkkkk...",
    "..kcccccck..",
    ".kcccccccck.",
    ".kckkcckkck.",
    ".kcccccccck.",
    ".kcccmmccck.",
    ".kcccccccck.",
    ".kcccccccck.",
    ".kcckcckcck.",
    "..kk.kk.kk..",
  ],
};

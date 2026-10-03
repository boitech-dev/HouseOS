// The theme in force: which one (the person's choice, else the house's), in which scheme, applied
// as data-theme / data-scheme on <html>. The generated CSS does the rest (generated/themes.css).
import { createContext, useContext, useSyncExternalStore } from "react";
import { useI18n } from "../i18n";
import { DEFAULT_THEME, PARTS, THEMES, type Scheme, type ThemeInfo } from "./generated/themes";

const KEY = "houseos-theme";
const root = document.documentElement;

export type ThemeChoice = { theme?: string; scheme?: string };

/** A part of the page drawn in another theme (the Workbench, previews): its id, so identity
 *  (pixel or line) follows that theme rather than the one worn. */
export const ThemeScope = createContext("");
/** A theme that isn't in the list (Remix's unsaved draft): drawn from what the editor knows. */
export const PreviewInfo = createContext<ThemeInfo | null>(null);
/** A scoped preview's scheme, when it shows one other than the page's (pictures per scheme). */
export const SchemeScope = createContext("");

/** A theme made in the studio or imported (GET /themes): its stylesheet, and who may do what. */
export type Installed = ThemeInfo & {
  css: string;
  status: "draft" | "requested" | "shared";
  owner: { id: string; name: string };
  mine: boolean;
  version: number;
};
const INSTALLED = "houseos-installed-themes";
let installed: Installed[] = [];
let generation = 0; // counts installed stylesheets arrived, so caches keyed by the theme renew
const changes = new Set<() => void>();
/** Installed themes join the bundled ones: each one's stylesheet (only its tokens and fonts) is
 *  linked once, and whatever uses the list re-renders. Kept on this device so the last theme
 *  draws at once on the next start. */
export function setInstalled(list: Installed[]) {
  installed = list;
  // Only what may be worn here gets its stylesheet: the house's shared themes and your own.
  // (An administrator also sees others' requests, and previews one only on purpose.)
  const wanted = new Set(list.filter(wearable).map((item) => item.css));
  for (const node of document.querySelectorAll<HTMLLinkElement>("link[data-installed-theme]"))
    if (!wanted.has(node.getAttribute("href") ?? "")) node.remove();
  list.filter(wearable).forEach(link);
  try {
    localStorage.setItem(INSTALLED, JSON.stringify(list));
  } catch {}
  changes.forEach((changed) => changed());
}
const wearable = (item: Installed) => item.status === "shared" || item.mine;
/** Link one installed theme's stylesheet (once), e.g. to preview a request before sharing it. */
export function link(item: Installed) {
  if (document.querySelector(`link[href="${CSS.escape(item.css)}"]`)) return;
  const node = document.createElement("link");
  node.rel = "stylesheet";
  node.href = item.css;
  node.dataset.installedTheme = item.id;
  // Its colours arrive after it was applied: refresh the browser bar and redraw the art.
  node.addEventListener("load", () => {
    generation++;
    if (root.dataset.theme === item.id) apply(item.id, root.dataset.scheme as Scheme);
    changes.forEach((changed) => changed());
  });
  document.head.append(node);
}
export const allThemes = (): (ThemeInfo | Installed)[] => [...THEMES, ...installed];
/** The installed themes, re-rendering when they change. */
export function useInstalled() {
  return useSyncExternalStore(
    (changed) => (changes.add(changed), () => changes.delete(changed)),
    () => installed,
  );
}
/** A choice of a theme that is now another's: Base became the hidden root, Pure took its place. */
export const renamed = (id?: string) => (id === "base" ? "pure" : id);
const find = (id?: string) => allThemes().find((theme) => theme.id === renamed(id));

const device = () => (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");

/** The person's choice over the house's; an unknown id falls back to the house, then the default. */
export function resolve(person: ThemeChoice, house: ThemeChoice) {
  const info = find(person.theme) ?? find(house.theme) ?? find(DEFAULT_THEME) ?? THEMES[0];
  const wanted = (person.theme && find(person.theme) ? person.scheme : house.scheme) || "";
  const asked = wanted === "device" ? device() : wanted;
  const scheme: Scheme = info.schemes.includes(asked as Scheme)
    ? (asked as Scheme)
    : info.schemes[0];
  return { theme: info.id, scheme, follow: wanted === "device" };
}

/** Each part's variant in a theme (themes/_schema/parts.json), as the data attributes that pick
 *  its CSS: {"data-part-panel": "flat", …}. Set on <html>, and on any scoped preview. */
export function partData(id: string, info?: ThemeInfo | null): Record<string, string> {
  const theme = info ?? find(id);
  const own = theme?.parts ?? {};
  return Object.fromEntries([
    ...Object.entries(PARTS).map(([part, spec]) => [
      "data-part-" + part,
      own[part] ?? spec.default,
    ]),
    // A part with a picture of its own ("<part>.surface" slot): its layer is drawn (patterns.css).
    ...SURFACES.filter((part) => surfaceOf(theme, part)).map((part) => [
      "data-surface-" + part,
      "on",
    ]),
  ]);
}

/** The parts a theme can dress in a picture of its own: the slot "<part>.surface". */
export const SURFACES = ["rail", "dock", "nowbar", "panel", "sheet", "deck"] as const;
/** A slot's picture here: the room's own ("rooms") when the theme drew one, else the scheme's
 *  ("schemes"), else its picture. */
export function pictureFor<F>(fill: F, room: string, scheme = ""): F {
  const own = fill as
    | {
        image?: string;
        rooms?: Record<string, string | Record<string, string>>;
        schemes?: Record<string, string>;
      }
    | undefined;
  const mine = own?.rooms?.[room];
  const image = (typeof mine === "string" ? mine : mine?.[scheme]) ?? own?.schemes?.[scheme];
  return image ? ({ ...own, image } as F) : fill;
}
const surfaceOf = (
  theme: ThemeInfo | Installed | undefined,
  part: string,
  room = "home",
  scheme = "",
) => {
  const fill = pictureFor(theme?.slots?.[part + ".surface"], room, scheme);
  return fill && typeof fill === "object" && "image" in fill
    ? fill
    : typeof fill === "string"
      ? { image: fill }
      : null;
};
/** Each surface's picture as custom properties: how it fills its part (cover, contain, stretch,
 *  or slice: a 9-slice frame, corners kept whole), and whether it is pixel art. Every part gets
 *  its values ("none" without a picture), so a preview never shows the page's theme's pictures. */
export function surfaceVars(
  id: string,
  info?: ThemeInfo | null,
  room = "home",
  scheme = "",
): Record<string, string> {
  const theme = info ?? find(id);
  const vars: Record<string, string> = {};
  for (const part of SURFACES) {
    const fill = surfaceOf(theme, part, room, scheme) as {
      image: string;
      fit?: string;
      slice?: number;
      rendering?: string;
      anchor?: string;
    } | null;
    const url = fill ? `url("${fill.image}")` : "none";
    const slice = fill?.fit === "slice" ? Math.max(1, fill.slice ?? 16) : 0;
    vars["--surface-" + part] = slice ? "none" : url;
    vars["--surface-" + part + "-size"] =
      fill?.fit === "contain" ? "contain" : fill?.fit === "stretch" ? "100% 100%" : "cover";
    vars["--surface-" + part + "-border"] = slice
      ? `${url} ${slice} fill / ${slice}px / 0 stretch`
      : "none";
    vars["--surface-" + part + "-render"] =
      fill && fill.rendering !== "smooth" ? "pixelated" : "auto";
    vars["--surface-" + part + "-anchor"] = fill?.anchor ?? "center"; // cropped from the other end
  }
  return vars;
}

export function apply(theme: string, scheme: Scheme) {
  root.dataset.theme = theme;
  root.dataset.scheme = scheme;
  for (const name of root.getAttributeNames())
    if (name.startsWith("data-surface-")) root.removeAttribute(name);
  for (const [name, variant] of Object.entries(partData(theme))) root.setAttribute(name, variant);
  for (const [name, value] of Object.entries(surfaceVars(theme, null, root.dataset.room, scheme)))
    root.style.setProperty(name, value);
  const canvas = getComputedStyle(root).getPropertyValue("--c-bg-canvas").trim();
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", canvas);
  try {
    localStorage.setItem(KEY, JSON.stringify({ theme, scheme }));
  } catch {}
}

// The room shown (data-room on <html>: the theme's room colours, and its pictures for a room).
const rooms = new Set<() => void>();
export function setRoom(room: string) {
  if (root.dataset.room === room) return;
  root.dataset.room = room;
  if (root.dataset.theme)
    for (const [name, value] of Object.entries(
      surfaceVars(root.dataset.theme, null, room, root.dataset.scheme),
    ))
      root.style.setProperty(name, value);
  rooms.forEach((changed) => changed());
}
export const useRoom = () =>
  useSyncExternalStore(
    (changed) => (rooms.add(changed), () => rooms.delete(changed)),
    () => root.dataset.room ?? "home",
  );

/** Where pictures are drawn: the room and scheme shown, or a preview's (Home, its own scheme). */
export function usePlace() {
  const preview = !!useContext(ThemeScope) || !!useContext(PreviewInfo);
  const room = useRoom();
  const scoped = useContext(SchemeScope);
  const worn = useTheme().split("/")[1];
  return { preview, room: preview ? "home" : room, scheme: scoped || worn };
}

/** Before the first paint: the theme this device used last. */
export function restoreTheme() {
  try {
    setInstalled(JSON.parse(localStorage.getItem(INSTALLED) || "[]"));
    const last = JSON.parse(localStorage.getItem(KEY) || "{}");
    if (find(last.theme)) apply(last.theme, last.scheme);
  } catch {}
}

let follow: MediaQueryList | null = null;
let last: [ThemeChoice, ThemeChoice] = [{}, {}];
/** Apply the person's (or the house's) theme; with "follow the device", track its light/dark. */
export function applyChoice(person: ThemeChoice, house: ThemeChoice) {
  const chosen = resolve(person, house);
  last = [person, house];
  if (trying) return;
  apply(chosen.theme, chosen.scheme);
  follow?.removeEventListener("change", refollow);
  follow = chosen.follow ? matchMedia("(prefers-color-scheme: light)") : null;
  follow?.addEventListener("change", refollow);
  last = [person, house];
}
// Trying a theme on: worn on this device for a moment (nothing saved), then kept or taken off.
let trying: string | null = null;
const tries = new Set<() => void>();
export function tryOn(id: string | null) {
  trying = id && find(id) ? id : null;
  if (trying) apply(trying, find(trying)!.schemes[0]);
  else reapply();
  tries.forEach((changed) => changed());
}
export const useTryOn = () =>
  useSyncExternalStore(
    (changed) => (tries.add(changed), () => tries.delete(changed)),
    () => trying,
  );

/** After the installed themes changed: the choice may name one that has just arrived or gone. */
export const reapply = () => applyChoice(...last);
const refollow = () => applyChoice(...last);

// Anything that draws with theme colours in JS (sprites, scenes, QR codes, charts) re-renders
// when this changes, and caches by it.
function subscribe(changed: () => void) {
  const watch = new MutationObserver(changed);
  watch.observe(root, { attributes: true, attributeFilter: ["data-theme", "data-scheme"] });
  changes.add(changed);
  return () => {
    watch.disconnect();
    changes.delete(changed);
  };
}
const snapshot = () => `${root.dataset.theme ?? ""}/${root.dataset.scheme ?? ""}/${generation}`;

/** The theme in force, as a key: "carved-night/dark/0" (id, scheme, stylesheets arrived). */
export function useTheme() {
  return useSyncExternalStore(subscribe, snapshot);
}

/** The theme drawing this part of the page: a scoped preview's (ThemeScope), else the one worn. */
export function useThemeInfo(): ThemeInfo | undefined {
  const worn = useTheme().split("/")[0];
  const scoped = useContext(ThemeScope);
  const draft = useContext(PreviewInfo);
  return draft ?? find(scoped || worn);
}

/** A token's value in force right now (for canvas, QR codes and other JS-drawn things). */
export function token(name: string, element: Element = root) {
  return getComputedStyle(element).getPropertyValue(name).trim();
}

const palettes = new Map<string, Record<string, string>>();
/** Colours for JS drawing (sprites, scenes), read once per theme: {key: token value}. */
export function palette<K extends string>(tokens: Record<K, string>): Record<K, string> {
  const key = snapshot() + JSON.stringify(tokens);
  let found = palettes.get(key);
  if (!found) {
    const style = getComputedStyle(root);
    found = Object.fromEntries(
      Object.entries<string>(tokens).map(([name, variable]) => [
        name,
        style.getPropertyValue(variable).trim(),
      ]),
    );
    palettes.set(key, found);
  }
  return found as Record<K, string>;
}
/** The theme in force, as a cache key (outside React). */
export const themeKey = snapshot;

/** QR codes stay dark on light to scan in any theme: the theme's text and ground, darker first. */
export function qrColours() {
  const light = (hex: string) =>
    [1, 3, 5].reduce((sum, i) => sum + parseInt(hex.slice(i, i + 2), 16), 0);
  const [dark, bright] = [token("--c-fg-default"), token("--c-bg-canvas")].sort(
    (a, b) => light(a) - light(b),
  );
  return { dark, light: bright };
}

/** The theme's own words for a place (flavour: "room.listen.kicker"…), in the person's language;
 *  undefined when the theme has none (Base has none: plain labels only). */
export function useFlavor(key: string): string | undefined {
  const theme = useThemeInfo()?.id;
  const { language } = useI18n();
  const texts = find(theme)?.flavor[key];
  return texts ? (language === "fr" ? texts.fr : texts.en) : undefined;
}

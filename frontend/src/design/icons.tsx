// Icons by name. Control icons are Lucide line icons (their stroke follows --icon-stroke); identity
// glyphs (rooms, Nox, transport) follow the theme: pixel sprites in a pixel theme, line icons
// otherwise. Avatars are a person's own picture and stay pixel sprites in every theme.
import {
  AlertCircle, ArrowLeft, ArrowRight, ArrowUp, Ban, Bell, Bird, Blinds, Bookmark, Bot, Brush,
  CalendarDays, Cast, Clapperboard, Compass, Disc3, Feather, Footprints, Headphones, KeyRound, Pin,
  Popcorn, Timer, TrendingDown, TrendingUp,
  Check, ChevronDown, ChevronLeft, ChevronRight, ChevronsUp, ChevronUp, CircleDot, Clock, Cloud,
  Copy, Download, Droplets, Eye, EyeOff, Fan, File, FileAudio, FileImage, FileText, FileVideo, Film,
  Filter, Folder, FolderPlus, HardDrive, Heart, History, House, Image, Inbox, Info, Library,
  Lightbulb, Link2, ListMusic, LogOut, ListPlus, ListTodo, ListVideo, ListX, LoaderCircle, Lock, Mail, Menu,
  MessageCircle, Mic, Minus, Moon, MoreHorizontal, Music, Music2, Newspaper, Palette, Paperclip,
  PartyPopper, Pause, Pencil, Play, Plug, Plus, Power, Radio, RefreshCw, RotateCcw, RotateCw,
  Search, Send, Settings2, Shield, ShieldCheck, ShoppingBasket, Shuffle, Siren, SkipBack,
  SkipForward, SlidersHorizontal, Sparkles, Speaker, Square, Star, Sun, Thermometer, ToggleLeft,
  Trash2, TriangleAlert, Tv, Gamepad2, Undo2, Upload, User, Users, Volume2, VolumeX, WandSparkles, WifiOff,
  Wrench, X, createLucideIcon, type LucideIcon,
} from "lucide-react"; // prettier-ignore
import { AVATARS, NOX, ICONS, TRANSPORT, spriteSize, themeGrid, type Grid } from "../sprites";
import { Sprite } from "./motion";
import { useThemeInfo } from "./theme";

/** Nox's line mark in themes without pixel art: a bat, drawn like the Lucide icons (24 × 24). */
const Bat = createLucideIcon("Bat", [
  [
    "path",
    {
      d: "M 12 6.4 L 13.3 3.6 L 14 7.8 C 16 5.7 19 5.3 22 7.1 C 20.5 8.5 19.8 11.3 19.8 14.1 C 18.6 12.4 17.2 12.3 16 13.1 C 15.2 14.8 14 16.9 12 19.7 C 10 16.9 8.8 14.8 8 13.1 C 6.8 12.3 5.4 12.4 4.2 14.1 C 4.2 11.3 3.5 8.5 2 7.1 C 5 5.3 8 5.7 10 7.8 L 10.7 3.6 Z",
      key: "bat",
    },
  ],
]);

const LINE = {
  add: Plus, alert: AlertCircle, archive: Library, back: ArrowLeft, basket: ShoppingBasket, bell: Bell,
  bird: Bird, brush: Brush, clapperboard: Clapperboard, compass: Compass, disc: Disc3, feather: Feather,
  footprints: Footprints, headphones: Headphones, key: KeyRound, pin: Pin, popcorn: Popcorn, timer: Timer,
  "trend-down": TrendingDown, "trend-up": TrendingUp,
  blinds: Blinds, block: Ban, bookmark: Bookmark, bot: Bot, calendar: CalendarDays, cast: Cast,
  check: Check, "chevron-down": ChevronDown, "chevron-left": ChevronLeft, "chevron-right": ChevronRight,
  "chevron-up": ChevronUp, "chevrons-up": ChevronsUp, clock: Clock, close: X, cloud: Cloud, copy: Copy,
  dot: CircleDot, download: Download, drop: Droplets, edit: Pencil, fan: Fan, file: File,
  "file-audio": FileAudio, "file-image": FileImage, "file-text": FileText, "file-video": FileVideo,
  film: Film, filter: Filter, folder: Folder, "folder-add": FolderPlus, forward: ArrowRight, heart: Heart,
  hide: EyeOff, history: History, home: House, image: Image, inbox: Inbox, info: Info, light: Lightbulb,
  link: Link2, "list-add": ListPlus, "list-clear": ListX, "list-music": ListMusic, "list-todo": ListTodo,
  "list-video": ListVideo, loading: LoaderCircle, lock: Lock, "log-out": LogOut, mail: Mail, menu: Menu,
  message: MessageCircle, mic: Mic, minus: Minus, moon: Moon, more: MoreHorizontal, music: Music,
  "music-alt": Music2, newspaper: Newspaper, next: SkipForward, offline: WifiOff, palette: Palette,
  paperclip: Paperclip, party: PartyPopper, pause: Pause, people: Users, person: User, play: Play,
  plug: Plug, power: Power, previous: SkipBack, radio: Radio, redo: RotateCw, refresh: RefreshCw,
  replay: RotateCcw, search: Search, send: Send, settings: Settings2, shield: Shield,
  "shield-check": ShieldCheck, show: Eye, shuffle: Shuffle, siren: Siren, sliders: SlidersHorizontal,
  sparkles: Sparkles, speaker: Speaker, star: Star, stop: Square, storage: HardDrive, sun: Sun,
  thermometer: Thermometer, toggle: ToggleLeft, gamepad: Gamepad2, trash: Trash2, tv: Tv, undo: Undo2, up: ArrowUp,
  upload: Upload, volume: Volume2, "volume-off": VolumeX, wand: WandSparkles, warning: TriangleAlert,
  wrench: Wrench, nox: Bat,
} satisfies Record<string, LucideIcon>; // prettier-ignore
export type IconName = keyof typeof LINE;
/** Every control icon's name (the Workbench shows them all). */
export const ICON_NAMES = Object.keys(LINE) as IconName[];

/** A control icon. Decorative unless `label` is given. Sizes follow the text styles (s, m, l). */
export function Icon({
  name,
  size = "m",
  label,
}: {
  name: IconName;
  size?: "s" | "m" | "l";
  label?: string;
}) {
  const Line = LINE[name];
  return (
    <Line
      className="ds-icon"
      data-size={size}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      focusable={false}
    />
  );
}

// Identity glyphs: a pixel grid, or the line icon a theme without pixel art uses instead.
const GLYPHS: Record<string, [Grid, IconName]> = {
  "room.home": [ICONS.home, "home"],
  "room.listen": [ICONS.listen, "music"],
  "room.watch": [ICONS.watch, "tv"],
  "room.house": [ICONS.house, "list-todo"],
  "room.files": [ICONS.files, "folder"],
  "room.smart-home": [ICONS.bulb, "light"],
  "room.games": [ICONS.games, "gamepad"],
  "room.more": [ICONS.more, "add"],
  "room.me": [ICONS.me, "person"],
  "transport.play": [TRANSPORT.play, "play"],
  "transport.pause": [TRANSPORT.pause, "pause"],
  "transport.next": [TRANSPORT.next, "next"],
  "transport.previous": [TRANSPORT.previous, "previous"],
  "transport.stop": [TRANSPORT.stop, "stop"],
};
export type GlyphName = keyof typeof GLYPHS & string;

/** HouseOS's own drawing of a piece a theme may redraw (sprites.ids.json), if it has one. */
export function builtInPiece(id: string): Grid | undefined {
  const [group, name] = id.split(".");
  if (group === "avatar") return AVATARS[name as keyof typeof AVATARS];
  if (group === "nox") return NOX[name as keyof typeof NOX];
  return GLYPHS[id]?.[0];
}

/** Does the theme in force draw identity in pixels? */
export function usePixels() {
  return useThemeInfo()?.identity === "pixel";
}

/** A piece the theme in force redraws (sprites.json), by id: "nox.idle", "avatar.moon"… */
export function usePiece(id: string): Grid | undefined {
  return themeGrid(useThemeInfo(), id);
}

/** A room, transport or other identity mark, in the theme's own style. */
export function Glyph({
  name,
  size = "m",
  label,
}: {
  name: GlyphName;
  size?: "s" | "m" | "l";
  label?: string;
}) {
  const pixels = usePixels();
  const own = usePiece(name);
  const [grid, line] = GLYPHS[name];
  // The same box in every theme (a pixel sprite or a line icon, centred): sizes never follow identity.
  // A piece the theme redrew is drawn whatever its identity.
  return (
    <span className="ds-mark" data-size={size}>
      {own || pixels ? (
        <Sprite grid={own ?? grid} scale={size === "l" ? 3 : 2} label={label} />
      ) : (
        <Icon name={line} size={size} label={label} />
      )}
    </span>
  );
}

export type Mood = keyof typeof NOX;
/** Nox, the house's familiar, in the theme's style: the pixel bat, or the line bat. */
export function Mascot({
  mood = "idle",
  size = "m",
  label,
}: {
  mood?: Mood;
  size?: "s" | "m" | "l";
  label?: string;
}) {
  const pixels = usePixels();
  const info = useThemeInfo();
  const own = (m: Mood) => themeGrid(info, "nox." + m);
  if (!pixels && !own("idle"))
    return (
      <span
        className="ds-mark ds-mascot"
        data-mood={mood}
        data-size={size}
        role={label ? "img" : undefined}
        aria-label={label}
      >
        <Icon name={mood === "error" ? "alert" : "nox"} size={size} />
      </span>
    );
  // The theme's Nox where it drew one (a mood it left out: its idle), else the built-in.
  const nox = (m: Mood) => own(m) ?? (own("idle") ? own("idle")! : NOX[m]);
  const frames =
    mood === "idle"
      ? [nox("idle"), nox("idle"), nox("idle"), nox("blink")]
      : mood === "thinking"
        ? [nox("thinking"), nox("idle")]
        : [nox(mood)];
  return (
    <span className="ds-mark ds-mascot" data-size={size}>
      <Sprite
        frames={frames}
        scale={size === "l" ? 4 : size === "m" ? 3 : 2}
        ambient
        label={label}
      />
    </span>
  );
}

export type AvatarName = keyof typeof AVATARS;
export const AVATAR_NAMES = Object.keys(AVATARS) as AvatarName[];
/** A person's chosen picture (a pixel portrait in every theme, in the theme's colours). */
export function AvatarPicture({
  name,
  scale = 2,
  box,
}: {
  name?: string;
  scale?: number;
  /** The ring's inside, in px: a theme's own picture is scaled by whole pixels to fill it. */
  box?: number;
}) {
  const id: AvatarName = (name as AvatarName) in AVATARS ? (name as AvatarName) : "crest";
  // The theme's own picture, else the built-in one: scaled by whole pixels to fill the box.
  const grid = usePiece("avatar." + id) ?? AVATARS[id];
  if (!box) return <Sprite grid={grid} scale={scale} className="ds-avatar__picture" />;
  const { width, height } = spriteSize(grid);
  return (
    <Sprite
      grid={grid}
      scale={Math.max(1, Math.floor(box / Math.max(width, height)))}
      className="ds-avatar__picture"
    />
  );
}

/** A piece drawn at the whole-pixel scale that best fills a box (a medal in 32 px). */
export function PieceFill({ grid, box }: { grid: Grid; box: number }) {
  const { width, height } = spriteSize(grid);
  return <Sprite grid={grid} scale={Math.max(1, Math.floor(box / Math.max(width, height)))} />;
}

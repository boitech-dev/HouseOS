// The frame every page lives in (docs/design/SYSTEM.md, "The shell"): a slim status bar, the
// places (a rail on wide screens, a dock on phones with Ask in the middle), one Now bar for the
// music and the TV, the command palette (⌘K), toasts, and the sheets opened from here.
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  api,
  ApiError,
  clock,
  idempotency,
  items,
  percent,
  useData,
  useUser,
  type Obj,
} from "./api";
import { getLanguage, t, useI18n, type Language } from "./i18n";
import { CONTROL_PLACES, go } from "./nav";
import {
  Avatar,
  Badge,
  Button,
  type Command,
  CommandPalette,
  Glyph,
  type GlyphName,
  Icon,
  IconButton,
  List,
  ListRow,
  Mascot,
  Media,
  PageGuard,
  Progress,
  rank,
  Segmented,
  Sheet,
  Slider,
  Status,
  ToastRegion,
  toast,
  tone,
  useTheme,
} from "./design";
import { allThemes, setRoom, themeKey, tryOn, useThemeInfo, useTryOn } from "./design/theme";
import { NOX, faviconUrl, themeGrid } from "./sprites";
import type { ThemeInfo } from "./design/generated/themes";
import { Slot } from "./design/slots";
import { ThemeLayers } from "./design/theme_layers";
import { OnAir, StopAndClear, useCanControl, useMusicPlayback, usePosition } from "./music";
import { CinemaSleep, CinemaStop, CinemaTransport, useCinemaCurrent } from "./cinema";
import { RELEASE, unseen } from "./whats_new";
import { Assistant } from "./ask";
import { useWaiting } from "./outbox";
import "./shell.css";

type Place = { path: string; label: string; glyph: GlyphName; dock?: boolean };
const PLACES: Place[] = [
  { path: "/", label: "Home", glyph: "room.home", dock: true },
  { path: "/listen", label: "Listen", glyph: "room.listen", dock: true },
  { path: "/watch", label: "Watch", glyph: "room.watch", dock: true },
  { path: "/games", label: "Games", glyph: "room.games" },
  { path: "/house", label: "House", glyph: "room.house" },
  { path: "/smart-home", label: "Smart home", glyph: "room.smart-home" },
  { path: "/files", label: "Files", glyph: "room.files" },
];
/** The phone dock's More: the rooms past the dock (the rail's own), then Inbox and My space. */
const MORE: (Place & { icon?: Command["icon"] })[] = [
  ...PLACES.filter((place) => !place.dock),
  { path: "/inbox", label: "Inbox", glyph: "room.house", icon: "inbox" },
  { path: "/space", label: "My space", glyph: "room.me", icon: "person" },
];
/** Pages that belong to a place without being its doorway. */
const PARENT: Record<string, string> = {
  "/tv": "/watch",
  "/inbox": "/house",
  "/capture": "/files",
  "/party": "/listen",
  "/speaker": "/listen",
};
const inPlace = (path: string, place: string) => path === place || path.startsWith(place + "/");
const placeOf = (path: string) => PARENT[path] ?? (inPlace(path, "/games") ? "/games" : path);
/** Who made the theme worn (theme.json "credit"), small at the rail's foot: plain words. */
function Credit() {
  const credit = useThemeInfo()?.credit;
  const { language } = useI18n();
  return credit ? (
    <small className="shell__credit">{language === "fr" ? credit.fr : credit.en}</small>
  ) : null;
}

/** Each place has its own light: data-room on <html> (the theme's --c-room tokens). */
const ROOM: Record<string, string> = {
  "/": "home",
  "/listen": "listen",
  "/watch": "watch",
  "/house": "house",
  "/smart-home": "smart-home",
  "/inbox": "inbox",
  "/files": "files",
  "/games": "games",
  "/assistant": "ask",
  "/me": "me",
  "/space": "space",
  "/control": "control",
  "/party": "party",
  "/workshop": "me",
  "/workshop/remix": "me",
};

export type Live = "online" | "reconnecting" | "offline";
type Music = ReturnType<typeof useMusicPlayback>;

/** Title case for a shouted house name, so a display face stays legible. */
const houseTitle = (name: string) =>
  name === name.toUpperCase()
    ? name.toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase())
    : name;

function useRail(): [boolean, () => void] {
  const [narrow, setNarrow] = useState(() => {
    try {
      return localStorage.getItem("houseos.rail") === "icons";
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setNarrow((value) => {
      try {
        localStorage.setItem("houseos.rail", value ? "full" : "icons");
      } catch {}
      return !value;
    });
  return [narrow, toggle];
}

export function Shell({
  user,
  house,
  path,
  can,
  live,
  onSignOut,
  onLanguage,
  children,
}: {
  user: Obj;
  house: Obj;
  path: string;
  can: (route: string) => boolean;
  live: Live;
  onSignOut: () => Promise<void>;
  onLanguage: (language: Language) => Promise<void>;
  children: ReactNode;
}) {
  const music = useMusicPlayback(can("/listen"));
  const cinema = useCinemaCurrent(can("/watch"));
  const movie: Obj | null = cinema.error ? null : (cinema.data?.current ?? null);
  const [ask, setAsk] = useState<{
    message: string;
    source: "text" | "voice";
    purpose: "general" | "setup" | "themes";
    /** A code preset to run as the opening message (the tour). */
    preset?: string;
  } | null>(null);
  const [layer, setLayer] = useState<"" | "palette" | "activity" | "me" | "now" | "rooms">("");
  const [narrow, toggleRail] = useRail();
  // What the TV said after a command (a truthful stop, a refusal), shown on the Now bar.
  const [tvNote, setTvNote] = useState("");
  const movieChanged = (result?: Obj) => {
    setTvNote(result?.error?.message || "");
    void cinema.reload();
  };
  const canAsk = can("/assistant");
  const canControl = useCanControl();
  const activity = useData<Obj>("/activity", {
    interval: (data) => (items(data).length ? 4000 : 30000),
  });
  const inbox = useData<Obj>(can("/inbox") ? "/household/inbox?unread=true&limit=50" : null);
  const running = items(activity.data);
  const unread = can("/inbox") ? items(inbox.data).length : null;
  const openNox = (
    message = "",
    source: "text" | "voice" = "text",
    purpose: "general" | "setup" | "themes" = "general",
    preset?: string,
  ) => canAsk && setAsk({ message, source, purpose, preset });
  // Someone who never took Nox's tour: a dot on Nox, and one tap asks for it.
  const prefs = useData<Obj>("/preferences");
  const tour = canAsk && prefs.data && !prefs.data.tour_seen && user.role !== "guest";
  const tapNox = () => {
    if (!tour) return openNox();
    openNox(t("How does the house work?"), "text", "general", "tour");
    prefs.setData((p) => (p ? { ...p, tour_seen: true } : p));
  };
  // The music keys read the latest playback without re-binding the listener every second.
  const player = useRef({ music, canControl });
  player.current = { music, canControl };
  useEffect(() => {
    // ⌘K / Ctrl+K: the palette. Ctrl+←/→ previous and next song, Ctrl+↑/↓ volume, Ctrl+Space
    // pause and play (not while typing: there Ctrl+arrows move by word).
    // Any page may open Nox, optionally with a message to send:
    // dispatchEvent(new CustomEvent("houseos:ask", { detail: { message, source, purpose } })).
    // Any page may open the Now sheet: dispatchEvent(new Event("houseos:now")).
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setLayer((open) => (open === "palette" ? "" : "palette"));
        return;
      }
      if (!e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || (e.repeat && e.key === " ")) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest?.("input, textarea, select, [contenteditable='true']")) return;
      const { music, canControl } = player.current;
      if (!canControl || !music.data) return;
      const volume = Number(music.data.volume ?? 60);
      const step: Record<string, [string, number?]> = {
        ArrowLeft: ["previous"],
        ArrowRight: ["skip"],
        ArrowUp: ["volume", Math.min(100, volume + 5)],
        ArrowDown: ["volume", Math.max(0, volume - 5)],
        " ": [music.playing ? "pause" : "play"],
      };
      const act = step[e.key];
      if (!act) return;
      e.preventDefault();
      music
        .control(act[0], act[1])
        .then(
          () =>
            act[0] === "volume" && toast(t("Volume {n}").replace("{n}", percent(Number(act[1])))),
        )
        .catch((failure: unknown) => toast((failure as Error).message, { tone: "danger" }));
    };
    const open = (event: Event) => {
      const { message, source, purpose, preset } = (event as CustomEvent).detail || {};
      openNox(
        typeof message === "string" ? message : "",
        source === "voice" ? "voice" : "text",
        purpose === "setup" || purpose === "themes" ? purpose : "general",
        preset === "tour" ? preset : undefined,
      );
    };
    addEventListener("keydown", key);
    const now = () => setLayer("now");
    addEventListener("houseos:ask", open);
    addEventListener("houseos:now", now);
    return () => {
      removeEventListener("keydown", key);
      removeEventListener("houseos:ask", open);
      removeEventListener("houseos:now", now);
    };
  }, [canAsk]);
  // Leaving a page closes the layers opened from it.
  useEffect(() => setLayer((open) => (open === "now" ? open : "")), [path]);
  const here = placeOf(path);
  useLayoutEffect(() => setRoom(ROOM[here] ?? "home"), [here]);
  const places = PLACES.filter((place) => can(place.path));
  const mode =
    path === "/party"
      ? "party"
      : path.startsWith("/games/play/")
        ? "play"
        : path === "/assistant"
          ? "chat"
          : undefined;
  return (
    <div className="shell" data-rail={narrow ? "icons" : "full"} data-mode={mode}>
      <a className="skip" href="#main">
        {t("Skip to content")}
      </a>
      <div className="shell__backdrop" aria-hidden="true">
        <ThemeLayers where="page" under />
        <Slot id="page.backdrop" />
        <ThemeLayers where="page" />
      </div>
      <StatusBar
        house={house}
        user={user}
        live={live}
        running={running.length}
        unread={unread}
        onPalette={() => setLayer("palette")}
        onActivity={() => setLayer("activity")}
        onMe={() => setLayer("me")}
      />
      <nav className="shell__rail" aria-label={t("Main navigation")}>
        <a
          className="shell__crest"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            go("/");
          }}
        >
          <span>{houseTitle(house.name || "Midnight House")}</span>
        </a>
        <ul>
          {places.map((place) => (
            <li key={place.path}>
              <Door place={place} here={here} unread={place.path === "/house" ? unread : null} />
            </li>
          ))}
        </ul>
        <Slot id="rail.art" className="shell__rail-art" />
        <ThemeLayers where="rail-foot" />
        <ThemeLayers where="rail" />
        {canAsk && <AskCard admin={user.role === "admin"} tour={!!tour} onAsk={tapNox} />}
        <Credit />
        <IconButton
          className="shell__fold"
          icon={narrow ? "chevron-right" : "chevron-left"}
          size="s"
          label={narrow ? t("Show the names") : t("Icons only")}
          onClick={toggleRail}
        />
      </nav>
      <main id="main" tabIndex={-1} key={path} className="shell__main">
        <PageGuard>{children}</PageGuard>
      </main>
      <ThemeLayers where="page" above />
      <ToTop key={"top-" + path} />
      <TabIcon />
      <NowBar
        path={path}
        music={music}
        movie={path === "/" ? null : movie}
        note={tvNote}
        onOpen={() => setLayer("now")}
        onMovieChanged={movieChanged}
      />
      {/* Nox at the heart of the dock, raised above it, two rooms on each side. */}
      <nav className="shell__dock" aria-label={t("Mobile navigation")}>
        {places
          .filter((place) => place.dock)
          .slice(0, 2)
          .map((place) => (
            <Door key={place.path} place={place} here={here} unread={null} />
          ))}
        {canAsk && (
          <Button
            variant="quiet"
            className="shell__door shell__door--ask"
            onClick={tapNox}
            aria-label={tour ? t("Ask Nox · how the house works") : t("Ask Nox")}
          >
            <Mascot size="m" />
            {/* Nox's face says who: one word fits the dock in every language. */}
            <span>{t("Ask")}</span>
            {tour && <span className="shell__nox-dot" aria-hidden="true" />}
          </Button>
        )}
        {places
          .filter((place) => place.dock)
          .slice(2)
          .map((place) => (
            <Door key={place.path} place={place} here={here} unread={null} />
          ))}
        <Button
          variant="quiet"
          className="shell__door"
          aria-current={MORE.some((place) => place.path === here) ? "page" : undefined}
          onClick={() => setLayer("rooms")}
        >
          <Glyph name="room.more" />
          <span>{t("More")}</span>
          {!!unread && (
            <Badge label={t("{n} unread").replace("{n}", String(unread))}>{unread}</Badge>
          )}
        </Button>
      </nav>
      <Suspense fallback={null}>
        <Onboarding path={path} />
      </Suspense>
      <ToastRegion />
      <TryingOn />
      {layer === "palette" && (
        <CommandPalette
          commands={commands({
            can,
            user,
            music,
            movie,
            canControl,
            onMovieChanged: movieChanged,
          })}
          quick={quickActions({
            can,
            music,
            canControl,
            canAsk,
            onAsk: (text) => openNox(text),
          })}
          onAsk={canAsk ? (text) => openNox(text) : undefined}
          search={(text) => findInHouse(text, can)}
          onClose={() => setLayer("")}
        />
      )}
      {ask && (
        <Sheet
          title="Nox"
          place="side"
          onClose={() => setAsk(null)}
          actions={
            path !== "/assistant" && (
              <Button
                variant="quiet"
                size="s"
                onClick={() => {
                  setAsk(null);
                  go("/assistant");
                }}
              >
                {t("Full page")}
              </Button>
            )
          }
        >
          <Assistant
            key={ask.purpose + ask.message}
            purpose={ask.purpose}
            initialDraft={ask.message}
            autoSend={!!ask.message}
            autoPreset={ask.preset}
            autoSource={ask.source}
          />
        </Sheet>
      )}
      {layer === "rooms" && (
        <Sheet title={t("Rooms")} onClose={() => setLayer("")}>
          <List label={t("Rooms")}>
            {MORE.filter((place) => can(place.path)).map((place) => (
              <ListRow
                key={place.path}
                leading={place.icon ? <Icon name={place.icon} /> : <Glyph name={place.glyph} />}
                title={t(place.label)}
                meta={
                  place.path === "/inbox" && unread
                    ? t("{n} unread").replace("{n}", String(unread))
                    : undefined
                }
                href={place.path}
                onOpen={() => {
                  setLayer("");
                  go(place.path);
                }}
              />
            ))}
          </List>
        </Sheet>
      )}
      {layer === "activity" && (
        <Sheet title={t("In progress")} onClose={() => setLayer("")}>
          <ActivityList running={running} onOpen={() => setLayer("")} />
        </Sheet>
      )}
      {layer === "me" && (
        <Sheet title={user.name} onClose={() => setLayer("")}>
          <MeMenu
            user={user}
            house={house}
            unread={unread || 0}
            can={can}
            onSignOut={onSignOut}
            onLanguage={onLanguage}
          />
        </Sheet>
      )}
      {layer === "now" && (
        <Sheet title={t("Now playing")} onClose={() => setLayer("")}>
          <NowSheet
            music={music}
            movie={movie}
            onMovieChanged={movieChanged}
            onClose={() => setLayer("")}
          />
        </Sheet>
      )}
    </div>
  );
}

function Door({ place, here, unread }: { place: Place; here: string; unread: number | null }) {
  const current = here === place.path;
  return (
    <a
      href={place.path}
      className="shell__door"
      aria-current={current ? "page" : undefined}
      title={t(place.label)}
      onClick={(e) => {
        e.preventDefault();
        go(place.path);
      }}
    >
      <Glyph name={place.glyph} />
      <span>{t(place.label)}</span>
      {!!unread && <Badge label={t("{n} unread").replace("{n}", String(unread))}>{unread}</Badge>}
    </a>
  );
}

// ---------- the status bar ----------

function StatusBar({
  house,
  user,
  live,
  running,
  unread,
  onPalette,
  onActivity,
  onMe,
}: {
  house: Obj;
  user: Obj;
  live: Live;
  running: number;
  unread: number | null;
  onPalette: () => void;
  onActivity: () => void;
  onMe: () => void;
}) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);
  const preferences = house.preferences || {};
  const waiting = useWaiting(); // changes kept on this device until the house is reachable
  return (
    <header className="shell__status">
      <ThemeLayers where="status" under />
      <Slot id="status.backdrop" className="shell__sky" width={320} height={16} lit={3} />
      <ThemeLayers where="status" />
      <a
        className="shell__name"
        href="/"
        onClick={(e) => {
          e.preventDefault();
          go("/");
        }}
      >
        {houseTitle(house.name || "Midnight House")}
      </a>
      <Button variant="quiet" icon="search" className="shell__search" onClick={onPalette}>
        {t("Go to, do or ask…")}
        <kbd>{navigator.platform.includes("Mac") ? "⌘K" : "Ctrl K"}</kbd>
      </Button>
      <div className="shell__signs">
        {live !== "online" && (
          <Status tone={live === "offline" ? "danger" : "warning"} busy={live === "reconnecting"}>
            {t(live === "offline" ? "Offline" : "Reconnecting…")}
          </Status>
        )}
        {waiting > 0 && (
          <Status tone="warning">{t("{n} changes waiting").replace("{n}", String(waiting))}</Status>
        )}
        <time className="shell__clock tabular">
          {new Intl.DateTimeFormat(preferences.language || "en-GB", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: preferences.time_display === "12h",
            timeZone: preferences.timezone || "UTC",
          }).format(now)}
        </time>
        <IconButton
          icon="search"
          label={t("Go to, do or ask…")}
          className="shell__search-icon"
          onClick={onPalette}
        />
        {user.role === "admin" && (
          <IconButton
            icon="shield"
            label={t("Control Room")}
            className="shell__control"
            pressed={location.pathname === "/control"}
            onClick={() => go("/control")}
          />
        )}
        {running > 0 && (
          <Button
            variant="quiet"
            icon="loading"
            className="shell__sign"
            onClick={onActivity}
            aria-label={t("In progress: {n}").replace("{n}", String(running))}
          >
            <Badge tone="neutral">{running}</Badge>
          </Button>
        )}
        {/* New messages show on the avatar (and on Inbox in its menu), not as an icon of their own. */}
        <Button
          variant="quiet"
          className="shell__me"
          onClick={onMe}
          aria-label={
            unread
              ? t("Your account · {n} unread messages").replace("{n}", String(unread))
              : t("Your account")
          }
        >
          <Avatar
            name={user.name}
            decorative
            picture={user.avatar || preferences.avatar}
            tone={tone(user.id)}
          />
          {!!unread && <Badge>{unread}</Badge>}
        </Button>
      </div>
    </header>
  );
}

/** The rail's Nox (wide screens): a card of its own, and the way to set the AI up when it isn't. */
function AskCard({ admin, tour, onAsk }: { admin: boolean; tour: boolean; onAsk: () => void }) {
  const status = useData("/assistant/status?purpose=general");
  const ready = status.data?.available !== false;
  return (
    <div className="shell__ask-card" data-ready={ready || undefined}>
      <Button
        variant="quiet"
        className="shell__door shell__door--ask"
        onClick={onAsk}
        aria-label={tour ? t("Ask Nox · how the house works") : undefined}
      >
        <Mascot size="m" />
        <span>{t("Ask Nox")}</span>
        {tour && <span className="shell__nox-dot" aria-hidden="true" />}
      </Button>
      {tour && <small>{t("New here? Tap for a tour.")}</small>}
      {!ready &&
        (admin ? (
          <Button size="s" variant="link" onClick={() => go("/control?tab=ai")}>
            {t("Set up the AI")}
          </Button>
        ) : (
          <small>{t("Not set up yet")}</small>
        ))}
    </div>
  );
}

// ---------- the palette's search: what the house has by that name ----------

/** Songs kept here (they play next), films (their page opens) and games (they start). */
async function findInHouse(text: string, can: (route: string) => boolean): Promise<Command[]> {
  const q = encodeURIComponent(text);
  const read = (path: string, allowed: boolean) => (allowed ? api(path).catch(() => null) : null);
  const [songs, films, games] = await Promise.all([
    read("/files/library?kind=music&q=" + q, can("/listen") && can("/files")),
    read("/cinema/search?kind=movie&q=" + q, can("/watch")),
    read("/games?limit=4&q=" + q, can("/games")),
  ]);
  const playNext = async (song: Obj) => {
    const added = await api("/music/queue", "POST", {
      source_url: song.source_url,
      idempotency_key: idempotency(),
    });
    const state = await api("/music");
    // Already the next song when nothing else waits; otherwise moved up (a busy queue may refuse).
    await api("/music/queue/" + added.item_id + "/next", "POST", {
      expected_version: state.version,
    }).catch(() => {});
    toast(t("{title} plays next.").replace("{title}", song.title));
  };
  return [
    ...items(songs)
      .slice(0, 4)
      .map((song) => ({
        id: "song-" + song.id,
        label: t("Play next: {title}").replace("{title}", song.title),
        group: t("Your music"),
        icon: "music" as const,
        run: () => playNext(song),
      })),
    ...items(films)
      .slice(0, 3)
      .map((film) => ({
        id: "film-" + film.id,
        label: film.title + (film.year ? " (" + film.year + ")" : ""),
        group: t("Watch"),
        icon: "film" as const,
        run: () => go("/watch?title=" + encodeURIComponent(film.id)),
      })),
    ...items(games).map((game) => ({
      id: "game-" + game.id,
      label: (game.here ? t("Play {title}") : t("Open {title}")).replace("{title}", game.title),
      group: t("Games"),
      icon: "gamepad" as const,
      run: () =>
        game.here
          ? location.assign("/games/play/" + game.id) // its own page policy: a full load
          : go("/games?game=" + game.id),
    })),
  ];
}

// ---------- the palette's commands ----------

function commands({
  can,
  user,
  music,
  movie,
  canControl,
  onMovieChanged,
}: {
  can: (route: string) => boolean;
  user: Obj;
  music: Music;
  movie: Obj | null;
  canControl: boolean;
  onMovieChanged: (result?: Obj) => void;
}): Command[] {
  const place = (
    id: string,
    label: string,
    path: string,
    icon: Command["icon"],
    keywords = "",
    group = "Rooms",
  ): Command => ({
    id,
    label: t(label),
    // "Rooms": French "Places" (Emplacements) reads as file locations.
    group: t(group),
    icon,
    // English and the page's language: "musique" or "thème" find things too.
    keywords: keywords && keywords + " " + t(keywords),
    run: () => go(path),
  });
  const list: Command[] = [];
  const places: [string, string, string, Command["icon"], string?][] = [
    ["home", "Home", "/", "home"],
    ["listen", "Listen", "/listen", "music", "music queue songs"],
    ["watch", "Watch", "/watch", "tv", "films series anime"],
    [
      "games",
      "Games",
      "/games",
      "gamepad",
      "play retro console snes nes emulator roms controller moonlight",
    ],
    ["house", "House", "/house", "list-todo", "board"],
    ["tasks", "Tasks", "/house?tab=tasks", "list-todo"],
    ["groceries", "Groceries", "/house?tab=groceries", "basket", "shopping"],
    ["calendar", "Calendar", "/house?tab=calendar", "calendar"],
    ["numbers", "Numbers", "/house?tab=numbers", "trend-up", "stats titles medals"],
    ["inbox", "Inbox", "/inbox", "inbox", "messages"],
    ["files", "Files", "/files", "folder"],
    ["smart-home", "Smart home", "/smart-home", "light", "lights tv remote"],
    ["space", "My space", "/space", "person"],
    ["me", "Your preferences", "/me", "settings", "theme language motion legacy"],
    ["party", "Party mode", "/party", "party"],
    ["speaker", "Speaker mode", "/speaker", "speaker"],
    ["capture", "Capture", "/capture", "upload"],
  ];
  for (const [id, label, path, icon, words] of places)
    if (can(path.split("?")[0])) list.push(place(id, label, path, icon, words));
  // Each room's own places, found by name ("history", "radio", "security").
  const inside: [string, string, string, Command["icon"], string][] = [
    ["listen-library", "My music", "/listen?tab=library", "music-alt", "Listen"],
    ["listen-radio", "Radio", "/listen?tab=radio", "radio", "Listen"],
    ["listen-history", "History", "/listen?tab=history", "history", "Listen"],
    ["listen-auto", "Auto play", "/listen?tab=auto", "shuffle", "Listen"],
    ["house-wall", "House Wall", "/house?tab=board", "pin", "House"],
    ["games-continue", "Continue playing", "/games?shelf=continue", "play", "Games"],
    ["games-hacks", "Romhacks", "/games?shelf=hacks", "wand", "Games"],
  ];
  for (const [id, label, path, icon, group] of inside)
    if (can(path.split("?")[0])) list.push(place(id, label, path, icon, "", group));
  // Every settings section, found by any setting in it ("timezone", "password", "motion").
  const settings: [string, string, Command["icon"], string][] = [
    ["profile", "Profile", "person", "name picture avatar language interface legacy"],
    ["appearance", "Appearance", "palette", "theme dark light colours look"],
    ["comfort", "Comfort", "moon", "clock 12h 24h timezone sounds motion notifications"],
    ["security", "Security", "lock", "password sign out devices sessions"],
    ["films", "Films", "film", "subtitles audio language quality"],
    ["notifications", "Notifications", "bell", "push alerts phone"],
    ["memory", "Nox's memory", "bot", "remember forget assistant"],
  ];
  const allowed = (permission: string) =>
    user.role === "admin" || user.permissions?.includes(permission);
  const needs: Record<string, string> = {
    films: "cinema.use",
    notifications: "messages.read",
    memory: "assistant.use",
  };
  for (const [id, label, icon, words] of settings)
    if (!needs[id] || allowed(needs[id]))
      list.push(
        place("me-" + id, label, "/me?tab=" + id, icon, words + " " + t(words), "Your preferences"),
      );
  // Straight to the composer, ready to type (household.tsx reads ?new, /inbox ?with=new).
  const actions: [string, string, string, Command["icon"], string][] = [
    ["new-task", "New task", "/house?tab=tasks&new", "add", "task todo"],
    ["new-grocery", "Add to the groceries", "/house?tab=groceries&new", "basket", "shopping buy"],
    ["new-message", "New message", "/inbox?with=new", "message", "write send"],
  ];
  for (const [id, label, path, icon, words] of actions)
    if (can(path.split("?")[0])) list.push(place(id, label, path, icon, words, "Actions"));
  if (user.role === "admin") {
    list.push(
      place(
        "workshop",
        "Theme workshop",
        "/workshop",
        "brush",
        "themes design make your own workbench",
      ),
    );
    list.push(place("control", "Control Room", "/control", "shield", "admin settings"));
    for (const [id, icon, name, what] of CONTROL_PLACES)
      list.push(
        place(
          "control-" + id,
          name,
          "/control?tab=" + id,
          icon,
          what + " " + t(what),
          "Control Room",
        ),
      );
  }
  for (const theme of wearableThemes())
    list.push({
      id: "theme-" + theme.id,
      label: t("Wear {name}").replace("{name}", themeName(theme)),
      group: t("Themes"),
      icon: "palette",
      keywords: "theme look",
      run: () => wear(theme.id),
    });
  if (music.current && canControl) {
    const send = (action: string, value?: number) => () => music.control(action, value);
    const volume = music.data?.volume ?? 60;
    list.push(
      {
        id: "music-toggle",
        label: t(music.playing ? "Pause the music" : "Play the music"),
        group: t("Music"),
        icon: music.playing ? "pause" : "play",
        run: send(music.playing ? "pause" : "play"),
      },
      {
        id: "music-next",
        label: t("Next track"),
        group: t("Music"),
        icon: "next",
        run: send("skip"),
      },
      {
        id: "music-previous",
        label: t("Previous track"),
        group: t("Music"),
        icon: "previous",
        run: send("previous"),
      },
      {
        id: "music-louder",
        label: t("Louder"),
        group: t("Music"),
        icon: "volume",
        keywords: "volume up",
        keep: true,
        run: send("volume", Math.min(100, volume + 10)),
      },
      {
        id: "music-softer",
        label: t("Softer"),
        group: t("Music"),
        icon: "volume-off",
        keywords: "volume down quieter",
        keep: true,
        run: send("volume", Math.max(0, volume - 10)),
      },
    );
  }
  if (movie && !movie.phase)
    list.push({
      id: "tv-toggle",
      label: t(movie.state === "paused" ? "Resume the film" : "Pause the film"),
      group: t("TV"),
      icon: movie.state === "paused" ? "play" : "pause",
      run: () =>
        api("/cinema/workflows/" + movie.id + "/control", "POST", {
          version: movie.version,
          action: movie.state === "paused" ? "resume" : "pause",
        }).then(onMovieChanged),
    });
  return list;
}

const themeName = (theme: ThemeInfo) => (getLanguage() === "fr" ? theme.names.fr : theme.names.en);
/** The themes a person may wear: the bundled ones, and installed ones shared or their own. */
const wearableThemes = () =>
  allThemes().filter(
    (theme) => !theme.hidden && (!("status" in theme) || theme.status === "shared" || theme.mine),
  );
const wear = async (id: string) => {
  await api("/preferences", "PUT", { theme: id });
  dispatchEvent(new Event("house-settings-updated"));
};

/** The palette's numbered quick actions (Ctrl+K, then a digit): always in this order. */
function quickActions({
  can,
  music,
  canControl,
  canAsk,
  onAsk,
}: {
  can: (route: string) => boolean;
  music: Music;
  canControl: boolean;
  canAsk: boolean;
  onAsk: (text: string) => void;
}): Command[] {
  const add = (kind: string, data: Obj) =>
    api("/household/" + kind, "POST", { data, idempotency_key: idempotency() });
  const done = (text: string) => () => toast(text, { tone: "success" });
  const quick: Command[] = [
    {
      id: "q-song",
      label: t("Add a song"),
      group: t("Music"),
      icon: "music",
      mode: {
        label: t("Add a song"),
        placeholder: t("A song, an artist or a link"),
        rows: async (text) => {
          const query = text.trim();
          if (!query) return [];
          if (/^https?:\/\//i.test(query))
            return [
              {
                id: "link",
                label: t("Add this link to the queue"),
                group: t("Music"),
                icon: "link",
                run: () =>
                  api("/music/queue", "POST", {
                    source_url: query,
                    idempotency_key: idempotency(),
                  }).then(done(t("Added to the queue."))),
              },
            ];
          const found = await api(
            "/music/search?q=" + encodeURIComponent(query) + "&source=youtube&limit=6",
          );
          return items(found).map((song: Obj) => ({
            id: song.id,
            label: song.title,
            // Kept on the house disk: listed first, under their own heading, and they start at once.
            group: song.at_home ? t("At home") : song.uploader || t("Music"),
            icon: song.at_home ? ("home" as const) : ("music" as const),
            run: () =>
              api("/music/candidates", "POST", {
                candidate_id: song.id,
                idempotency_key: idempotency(),
              }).then(done(t("Added to the queue."))),
          }));
        },
      },
    },
    {
      id: "q-grocery",
      label: t("Add to the groceries"),
      group: t("House"),
      icon: "basket",
      mode: {
        label: t("Add to the groceries"),
        placeholder: t("One thing, then Enter (and the next)"),
        keep: true,
        // Already on the list is fine: say so, and ready for the next.
        submit: (text) =>
          add("groceries", { label: text }).then(done(t("Added to the groceries.")), (e) => {
            if (((e as ApiError).detail as Obj)?.code !== "DUPLICATE_REVIEW") throw e;
            toast(t("Already on the list."));
          }),
      },
    },
    {
      id: "q-message",
      label: t("Message someone"),
      group: t("Inbox"),
      icon: "message",
      mode: {
        label: t("Message someone"),
        placeholder: t("Who?"),
        rows: async (text) => {
          const me = (await api("/auth/me")).user?.id;
          return items(await api("/people"))
            .filter((person: Obj) => person.id !== me)
            .filter(
              (person: Obj) =>
                !text || rank([{ id: "", label: person.name, group: "" }], text).length,
            )
            .map((person: Obj) => ({
              id: person.id,
              label: person.name,
              group: t(person.home ? "Online now" : "Away"),
              icon: "person" as const,
              mode: {
                label: t("To {name}").replace("{name}", person.name),
                placeholder: t("Your message, then Enter to send"),
                submit: (body: string) =>
                  api("/household/messages", "POST", {
                    data: { title: "", body, recipient_ids: [person.id], attachments: [] },
                    idempotency_key: idempotency(),
                    allow_duplicate: false,
                  }).then(() => {
                    dispatchEvent(new Event("houseos:message-sent"));
                    toast(t("Sent."), { tone: "success" });
                  }),
              },
            }));
        },
      },
    },
    {
      id: "q-task",
      label: t("New task"),
      group: t("House"),
      icon: "list-todo",
      mode: {
        label: t("New task"),
        placeholder: t("What needs doing?"),
        submit: (text) => add("tasks", { title: text }).then(done(t("Task added."))),
      },
    },
    {
      id: "q-ask",
      label: t("Ask Nox"),
      group: "Nox",
      icon: "sparkles",
      disabled: !canAsk,
      mode: { label: t("Ask Nox"), placeholder: t("Anything, in your words"), submit: onAsk },
    },
    {
      id: "q-play",
      label: t(music.playing ? "Pause the music" : "Play the music"),
      group: t("Music"),
      icon: music.playing ? "pause" : "play",
      disabled: !music.current || !canControl,
      run: () => music.control(music.playing ? "pause" : "play"),
    },
    {
      id: "q-next",
      label: t("Next track"),
      group: t("Music"),
      icon: "next",
      disabled: !music.current || !canControl,
      run: () => music.control("skip"),
    },
    {
      id: "q-radio",
      label: t("Start a radio"),
      group: t("Music"),
      icon: "radio",
      mode: {
        label: t("Start a radio"),
        placeholder: t("A station, a genre or a city"),
        rows: async (text) =>
          items(
            await api(
              text.trim()
                ? "/music/radio?" + new URLSearchParams({ q: text.trim() })
                : "/music/radio/favorites",
            ),
          )
            .slice(0, 8)
            .map((station: Obj) => ({
              id: String(station.id),
              label: station.name,
              group: [station.country, (station.tags || "").split(",")[0]]
                .filter(Boolean)
                .join(" · "),
              icon: "radio" as const,
              run: () =>
                api(`/music/radio/${station.id}/queue`, "POST", {
                  idempotency_key: idempotency(),
                }).then(done(t("Added to the queue."))),
            })),
      },
    },
    {
      id: "q-theme",
      label: t("Change theme"),
      group: t("Themes"),
      icon: "palette",
      mode: {
        label: t("Change theme"),
        placeholder: t("A theme's name"),
        rows: (text) => {
          const all = wearableThemes().map((theme) => ({
            id: theme.id,
            label: themeName(theme),
            group: t("Themes"),
            icon: "palette" as const,
            run: () => wear(theme.id),
          }));
          return text.trim() ? rank(all, text) : all;
        },
      },
    },
  ];
  return quick.map((command) =>
    (command.id === "q-grocery" || command.id === "q-task") && !can("/house")
      ? { ...command, disabled: true }
      : command.id === "q-message" && !can("/inbox")
        ? { ...command, disabled: true }
        : command,
  );
}

/** A theme tried on (from the workshop or a share request): this device only, until kept or
 *  taken off. Keeping it makes it the person's own look everywhere. */
function TryingOn() {
  const trying = useTryOn();
  const theme = allThemes().find((item) => item.id === trying);
  if (!theme) return null;
  return (
    <aside className="shell__trying" aria-label={t("Trying a theme on")}>
      <Icon name="show" size="s" />
      <span>{t("Trying on {name}").replace("{name}", themeName(theme))}</span>
      <Button
        size="s"
        variant="primary"
        onClick={() =>
          void wear(theme.id).then(() => {
            tryOn(null);
            toast(t("It's your look now."), { tone: "success" });
          })
        }
      >
        {t("Keep it")}
      </Button>
      <Button size="s" variant="quiet" onClick={() => tryOn(null)}>
        {t("Take it off")}
      </Button>
    </aside>
  );
}

// ---------- the Now bar and sheet: the music and the TV, everywhere ----------

function NowBar({
  path,
  music,
  movie,
  note,
  onOpen,
  onMovieChanged,
}: {
  path: string;
  music: Music;
  movie: Obj | null;
  note: string;
  onOpen: () => void;
  onMovieChanged: (result?: Obj) => void;
}) {
  const [error, setError] = useState("");
  // Home shows what plays (music and TV), and so does Listen's full deck (on its queue only):
  // the bar would repeat it there. The deck says when it is on screen.
  const [deck, setDeck] = useState(false);
  useEffect(() => {
    const seen = (e: Event) => setDeck((e as CustomEvent<boolean>).detail);
    addEventListener("houseos:deck", seen);
    // The deck may have said so before this listened (both mount in one go).
    setDeck("deck" in document.documentElement.dataset);
    return () => removeEventListener("houseos:deck", seen);
  }, []);
  const canControl = useCanControl();
  const song: Obj | null = music.current && path !== "/" && !deck ? music.current : null;
  const [prefer, setPrefer] = useState<"music" | "tv">("tv");
  const source = movie && song ? prefer : movie ? "tv" : song ? "music" : null;
  const songPosition = usePosition(music).position;
  // The page keeps room at the bottom for the bar.
  const measure = useCallback((node: HTMLElement | null) => {
    const set = (height: number) =>
      document.documentElement.style.setProperty("--shell-now-h", height + "px");
    if (!node) return;
    const watch = new ResizeObserver(() => set(node.offsetHeight));
    set(node.offsetHeight);
    watch.observe(node);
    return () => {
      watch.disconnect();
      set(0);
    };
  }, []);
  if (!source) return null;
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const movieSend = (action: string, value?: number) =>
    run(() =>
      api("/cinema/workflows/" + movie!.id + "/control", "POST", {
        version: movie!.version,
        action,
        position: value,
      }).then(onMovieChanged),
    );
  const tv = source === "tv" && movie;
  const title = tv ? movie.title : song?.now_title || song?.title;
  const position = tv ? movie.checkpoint?.position || 0 : songPosition;
  const duration = tv ? movie.duration || 0 : song?.duration || 0;
  const playing = tv ? movie.state !== "paused" : music.playing;
  const detail = tv
    ? movie.phase
      ? t("Starting on {screen}…").replace("{screen}", movie.device || t("the TV"))
      : t(movie.state === "paused" ? "Paused on the TV" : "On the TV")
    : t(music.playing ? "Playing" : "Paused");
  return (
    <aside className="shell__now" ref={measure} aria-label={t("Now playing")}>
      {/* The song opens its player (Listen); the film opens the TV's controls and remote. */}
      <Button
        variant="quiet"
        className="shell__now-open"
        aria-label={(tv ? t("Open the TV controls") : t("Open the player")) + " · " + title}
        onClick={tv ? onOpen : () => go("/listen")}
      >
        <span className="shell__now-art" aria-hidden="true">
          {tv ? (
            <Media
              src={movie.media_id && "/api/v1/cinema/titles/" + movie.media_id + "/poster"}
              alt=""
              ratio="1 / 1"
            />
          ) : song?.art ? (
            <Media src={song.art} alt="" ratio="1 / 1" />
          ) : (
            <Glyph name="room.listen" />
          )}
        </span>
        <span className="shell__now-text">
          <span className="shell__now-title">{title}</span>
          <small>
            {detail}
            {duration > 0 &&
              !(tv && movie.phase) &&
              " · " + clock(position) + " / " + clock(duration)}
          </small>
        </span>
      </Button>
      {movie && song && (
        <Segmented
          label={t("Show")}
          size="s"
          value={source}
          onChange={setPrefer}
          options={[
            { value: "tv", label: t("TV"), icon: "tv" },
            { value: "music", label: t("Music"), icon: "music" },
          ]}
        />
      )}
      {(tv ? movie.volume_supported && !movie.phase : canControl) && (
        <span className="shell__now-volume">
          <Slider
            label={tv ? t("Movie volume") : t("Volume")}
            icon="volume"
            value={tv ? (movie.volume ?? 30) : (music.data?.volume ?? 60)}
            max={tv ? 75 : 100}
            onCommit={(value) =>
              tv ? void movieSend("volume", value) : void run(() => music.control("volume", value))
            }
          />
        </span>
      )}
      <span className="shell__now-keys">
        {!tv && canControl && (
          <IconButton
            icon="previous"
            label={t("Previous track")}
            disabled={!!song?.is_live}
            onClick={() => void run(() => music.control("previous"))}
          />
        )}
        {!(tv && movie.phase) && (tv || canControl) && (
          <IconButton
            icon={playing ? "pause" : "play"}
            label={t(playing ? "Pause" : tv ? "Resume" : "Play")}
            variant="secondary"
            onClick={() =>
              tv
                ? void movieSend(playing ? "pause" : "resume")
                : void run(() => music.control(playing ? "pause" : "play"))
            }
          />
        )}
        {!tv && canControl && (
          <IconButton
            icon="next"
            label={t("Next track")}
            onClick={() => void run(() => music.control("skip"))}
          />
        )}
      </span>
      {duration > 0 && (
        <span className="shell__now-line" aria-hidden="true">
          <i style={{ "--value": Math.min(1, position / duration) } as CSSProperties} />
        </span>
      )}
      {(error || note) && (
        <small role="alert" className="shell__now-error">
          {t(error || note)}
        </small>
      )}
    </aside>
  );
}

function NowSheet({
  music,
  movie,
  onMovieChanged,
  onClose,
}: {
  music: Music;
  movie: Obj | null;
  onMovieChanged: (result?: Obj) => void;
  onClose: () => void;
}) {
  const song = music.current;
  const { position } = usePosition(music);
  const [tab, setTab] = useState<"tv" | "music">(movie ? "tv" : "music");
  const shown = movie && song ? tab : movie ? "tv" : "music";
  const upNext = items(music.data)
    .filter((item) => item.id !== music.data?.current_id)
    .slice(0, 3);
  const open = (path: string) => () => {
    onClose();
    go(path);
  };
  if (!movie && !song) return <p>{t("Nothing is playing.")}</p>;
  return (
    <div className="shell__now-sheet">
      {movie && song && (
        <Segmented
          label={t("Show")}
          value={shown}
          onChange={setTab}
          options={[
            { value: "tv", label: t("TV"), icon: "tv" },
            { value: "music", label: t("Music"), icon: "music" },
          ]}
        />
      )}
      {shown === "tv" && movie && (
        <section className="shell__now-card" aria-label={t("On the TV")}>
          <div className="shell__now-head">
            <Media
              src={movie.media_id && "/api/v1/cinema/titles/" + movie.media_id + "/poster"}
              alt=""
            />
            <div>
              <h3>{movie.title}</h3>
              <p role="status">
                {movie.phase
                  ? t("Starting on {screen}…").replace("{screen}", movie.device || t("the TV"))
                  : t(movie.state === "paused" ? "Paused" : "Playing") +
                    (movie.device ? " · " + movie.device : "")}
              </p>
            </div>
          </div>
          {movie.phase ? (
            <CinemaStop current={movie} onChanged={onMovieChanged} />
          ) : (
            <>
              <CinemaTransport current={movie} onChanged={onMovieChanged} />
              <CinemaSleep workflow={movie} onWorkflow={() => onMovieChanged()} />
            </>
          )}
          <Button variant="link" onClick={open("/watch?workflow=" + movie.id)}>
            {t("Open in Watch")}
          </Button>
        </section>
      )}
      {shown === "music" && song && (
        <section className="shell__now-card" aria-label={t("House speakers")}>
          <div className="shell__now-head">
            {song.art ? (
              <Media src={song.art} alt="" ratio="1 / 1" />
            ) : (
              <Glyph name="room.listen" size="l" />
            )}
            <div>
              <h3>{song.title}</h3>
              <OnAir track={song} />
              {song.requester?.name && (
                <p>
                  {t("Added by")} {song.requester.name}
                </p>
              )}
            </div>
          </div>
          {song.duration > 0 && (
            <Slider
              label={t("Position")}
              value={Math.floor(position)}
              max={Math.floor(song.duration)}
              format={clock}
              onCommit={(value) => void music.control("seek", value)}
            />
          )}
          <div className="shell__now-transport">
            <IconButton
              icon="previous"
              size="l"
              label={t("Previous track")}
              disabled={song.is_live}
              onClick={() => void music.control("previous")}
            />
            <IconButton
              icon={music.playing ? "pause" : "play"}
              size="l"
              variant="primary"
              label={t(music.playing ? "Pause" : "Play")}
              onClick={() => void music.control(music.playing ? "pause" : "play")}
            />
            <IconButton
              icon="next"
              size="l"
              label={t("Next track")}
              onClick={() => void music.control("skip")}
            />
          </div>
          <Slider
            label={t("Volume")}
            value={music.data?.volume ?? 60}
            onCommit={(value) => void music.control("volume", value)}
          />
          <StopAndClear music={music} />
          {upNext.length > 0 && (
            <>
              <h4>{t("Up next")}</h4>
              <List label={t("Up next")}>
                {upNext.map((item) => (
                  <ListRow key={item.id} title={item.title} detail={item.requester?.name} />
                ))}
              </List>
            </>
          )}
          <Button variant="link" onClick={open("/listen")}>
            {t("Open Listen")}
          </Button>
        </section>
      )}
    </div>
  );
}

// ---------- activity and the "me" menu ----------

const ACTIVITY_LABELS: Record<string, string> = {
  finding_sources: "Finding sources",
  checking_sources: "Checking sources",
  preparing_film: "Preparing the film",
  sending_to_tv: "Sending to the TV",
  saving_film: "Saving the film",
  importing_playlist: "Importing the playlist",
};

function ActivityList({ running, onOpen }: { running: Obj[]; onOpen: () => void }) {
  if (!running.length)
    return <p>{t("Nothing is running. Everything you started has finished.")}</p>;
  return (
    <List label={t("In progress")}>
      {running.map((item) => (
        <ListRow
          key={item.id}
          title={t(ACTIVITY_LABELS[item.kind] || "Working")}
          detail={
            <>
              {item.title}
              <Progress
                label={t(ACTIVITY_LABELS[item.kind] || "Working")}
                busy={typeof item.progress !== "number"}
                value={item.progress || 0}
              />
            </>
          }
          href={item.href}
          onOpen={item.href ? onOpen : undefined}
        />
      ))}
    </List>
  );
}

function MeMenu({
  user,
  house,
  unread,
  can,
  onSignOut,
  onLanguage,
}: {
  user: Obj;
  house: Obj;
  unread: number;
  can: (route: string) => boolean;
  onSignOut: () => Promise<void>;
  onLanguage: (language: Language) => Promise<void>;
}) {
  const { language } = useI18n();
  const houseLanguages = items(useData("/languages").data).filter((l) => l.state === "ready");
  const spoken = houseLanguages.length
    ? houseLanguages
    : [
        { code: "en", name: "English" },
        { code: "fr", name: "Français" },
      ];
  const links: [string, string, Command["icon"]][] = [
    ["/me", "Your preferences", "settings"],
    ["/space", "My space", "person"],
    ["/files", "Files", "folder"],
    ["/inbox", "Inbox", "inbox"],
    ["/smart-home", "Smart home", "light"],
    ["/control", "Control Room", "shield"],
  ];
  return (
    <div className="shell__me-menu">
      <div className="shell__me-who">
        <Avatar
          name={user.name}
          picture={user.avatar || house.preferences?.avatar}
          tone={tone(user.id)}
          size="l"
        />
        <div>
          <strong>{user.name}</strong>
          <small>{t(user.role === "admin" ? "Administrator" : "Resident")}</small>
        </div>
      </div>
      <List label={t("Your places")}>
        {links
          .filter(([path]) => (path === "/control" ? user.role === "admin" : can(path)))
          .map(([path, label, icon]) => (
            <ListRow
              key={path}
              leading={<Icon name={icon!} />}
              title={t(label)}
              meta={
                path === "/inbox" && unread > 0 ? (
                  <Badge label={t("{n} unread").replace("{n}", String(unread))}>{unread}</Badge>
                ) : undefined
              }
              href={path}
            />
          ))}
      </List>
      <Segmented
        label={t("Language")}
        value={language}
        onChange={(code) => void onLanguage(code as Language)}
        options={spoken.map((l: Obj) => ({ value: l.code, label: l.name }))}
      />
      <Button variant="quiet" icon="back" onClick={() => void onSignOut()}>
        {t("Sign out")}
      </Button>
    </div>
  );
}

/** A small "back to top" once a long page (Watch's rows, history, lists) is well scrolled. */
/** The browser tab's icon follows the theme worn: its Nox, in its colours. */
function TabIcon() {
  useTheme();
  const info = useThemeInfo();
  const key = themeKey();
  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (link) link.href = faviconUrl(themeGrid(info, "nox.idle") ?? NOX.idle);
  }, [key, info]);
  return null;
}

function ToTop() {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    let frame = 0;
    const check = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setShown(scrollY > Math.max(900, innerHeight * 1.5)));
    };
    addEventListener("scroll", check, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      removeEventListener("scroll", check);
    };
  }, []);
  if (!shown) return null;
  return (
    <IconButton
      className="shell__totop"
      icon="up"
      variant="secondary"
      label={t("Back to top")}
      onClick={() => {
        scrollTo({
          top: 0,
          behavior:
            document.documentElement.dataset.motionEffective === "still" ? "auto" : "smooth",
        });
        document.getElementById("main")?.focus({ preventScroll: true });
      }}
    />
  );
}

// The welcomes themselves load only when one shows (most visits show none).
const OwnerSetup = lazy(() => import("./onboarding").then((m) => ({ default: m.OwnerSetup })));
const ResidentWelcome = lazy(() =>
  import("./onboarding").then((m) => ({ default: m.ResidentWelcome })),
);
const GuestWelcome = lazy(() => import("./onboarding").then((m) => ({ default: m.GuestWelcome })));
const WhatsNew = lazy(() => import("./onboarding").then((m) => ({ default: m.WhatsNew })));

/** Who sees which welcome, now. Mounted once in the shell. */
function Onboarding({ path }: { path: string }) {
  const user = useUser();
  const prefs = useData<Obj>(user ? "/preferences" : null);
  const admin = user?.role === "admin";
  const profile = useData<Obj>(admin ? "/account/profile" : null);
  const [closed, setClosed] = useState(false);
  // "Show the welcome again" (Control Room → Setup) opens "/?welcome": the owner's set-up again.
  const [forced, setForced] = useState(false);
  useEffect(() => {
    if (!new URLSearchParams(location.search).has("welcome")) return;
    setForced(true);
    setClosed(false);
  }, [path]);
  if (!user || !prefs.data || closed || path === "/join") return null;
  const p = prefs.data;
  const finish = async (change: Obj = {}) => {
    setClosed(true);
    try {
      await api("/preferences", "PUT", { onboarded: user.role, seen_release: RELEASE, ...change });
      dispatchEvent(new Event("house-settings-updated"));
      void prefs.reload();
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    }
  };
  if (admin) {
    if (!profile.data) return null;
    // The house's set-up, on Home (its steps open settings, and Home picks the step up again).
    if (forced || (!profile.data.welcome_dismissed && !p.onboarded))
      return path === "/" ? (
        <OwnerSetup
          forced={forced}
          onDone={() => {
            void api("/account/profile", "PATCH", { welcome_dismissed: true });
            void finish();
          }}
          onLater={() => setClosed(true)}
        />
      ) : null;
  } else if (!p.onboarded && user.role === "guest")
    return (
      <GuestWelcome
        name={user.name}
        tv={user.permissions?.includes("cinema.use")}
        onDone={() => void finish()}
      />
    );
  else if (!p.onboarded && !p.seen_release)
    return <ResidentWelcome onDone={(change) => void finish(change)} />;
  if (user.role === "guest") return null;
  const news = unseen(p.seen_release);
  return news.length ? <WhatsNew releases={news} onDone={() => void finish()} /> : null;
}

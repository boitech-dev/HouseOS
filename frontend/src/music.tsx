// Listen: the house's shared music. The queue is the heart of it (everyone takes turns); around
// it, one field to add anything, and the room's own places: My music, Radio, History, Auto play.
import { t } from "./i18n";
import { useState, useEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import {
  api,
  clock,
  useData,
  usePages,
  useUser,
  items,
  idempotency,
  date,
  percent,
  pretty,
  time,
  type Obj,
} from "./api";
import {
  Avatar,
  Badge,
  Button,
  Checkbox,
  Chip,
  ChipGroup,
  Cluster,
  ConfirmSheet,
  Field,
  Hint,
  Icon,
  IconButton,
  Input,
  List,
  ListHeading,
  ListRow,
  Media,
  Menu,
  MoreBelow,
  type NavItem,
  Notice,
  Page,
  PageHeader,
  Problem,
  ReviewDetails,
  Section,
  Segmented,
  Select,
  SearchInput,
  Sheet,
  Switch,
  Slider,
  Stack,
  Status,
  State,
  SubNav,
  Text,
  toast,
  tone,
  Toolbar,
  ThemeLayers,
} from "./design";
import { go } from "./nav";
import "./listen.css";

const ART = "/api/v1/music/art/";

const errorText = (e: unknown) => (e as Error).message;
const isLink = (text: string) => /^https?:\/\//i.test(text.trim());
/** A song from a service that can't play here: found by its name on YouTube instead. */
const elsewhere = (text: string) =>
  /^https:\/\/([\w-]+\.)*(spotify\.com|spotify\.link|deezer\.com|deezer\.page\.link|music\.apple\.com|tidal\.com)\//i.test(
    text.trim(),
  );
/** A whole playlist only when the link names no single video: a song opened from a mix or a
 *  playlist (watch?v=…&list=RD…&start_radio=1) is that one song. */
const isPlaylist = (text: string) => {
  if (/soundcloud\.com\/[^/]+\/sets\//i.test(text)) return true;
  if (/music\.youtube\.com\/browse\/MPREb_/i.test(text)) return true; // an album
  try {
    const url = new URL(text.trim());
    return (
      url.searchParams.has("list") &&
      !url.searchParams.has("v") &&
      !/youtu\.be$/i.test(url.hostname)
    );
  } catch {
    return false;
  }
};

/** A song's cover in a row. */
const Cover = ({ src }: { src?: string | null }) => (
  <Media src={src} alt="" ratio="1 / 1" className="listen-cover" />
);

function Requester({ person, auto }: { person?: Obj; auto?: string }) {
  if (auto)
    return (
      <span className="listen-who" title={t("Added by auto play")}>
        <Icon name="shuffle" size="s" /> {t("Auto play")}
      </span>
    );
  if (!person?.name) return null;
  return (
    <span className="listen-who" title={t("Added by") + " " + person.name}>
      <Avatar name={person.name} picture={person.avatar} tone={tone(person.id)} size="s" />
      <span>
        <span className="visually-hidden">{t("Added by")} </span>
        {person.name}
      </span>
    </span>
  );
}

/** Who did it ("played by" here, "uploaded by" in Files): everyone, or one person. */
export function PeopleFilter({
  value,
  onChange,
  label = "Played by",
  only,
}: {
  value: string;
  onChange: (id: string) => void;
  label?: string;
  /** Show only these people (those who have something here). */
  only?: string[];
}) {
  const people = useData("/people");
  const list = items(people.data).filter((person) => !only || only.includes(person.id));
  if (list.length < 2) return null;
  return (
    <Field label={t(label)}>
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("Everyone")}</option>
        {list.map((person) => (
          <option key={person.id} value={person.id}>
            {person.name}
          </option>
        ))}
      </Select>
    </Field>
  );
}

function preparationLabel(track: Obj) {
  if (track.download_state === "downloading") return t("Downloading audio…");
  if (track.status === "buffering") return t("Preparing audio…");
  if (["queued", "ready"].includes(track.status) && !track.downloaded && !track.is_live)
    return t("Waiting in the queue");
  if (["resolving", "pending_metadata"].includes(track.status)) return t("Finding the audio…");
  return "";
}
function soundCloudFallback(track: Obj) {
  return (
    track.source_url?.includes("youtube.com/") &&
    [
      "YOUTUBE_SIGN_IN_REQUIRED",
      "YOUTUBE_RATE_LIMITED",
      "SOURCE_UNAVAILABLE",
      "SOURCE_EXPIRED",
      "SOURCE_URL_EXPIRED",
      "SOURCE_TIMEOUT",
    ].includes(track.error_code)
  );
}
function findOnSoundCloud(track: Obj) {
  go(
    "/listen?source=soundcloud&q=" +
      encodeURIComponent(track.title === "Resolving source…" ? "" : track.title || ""),
  );
}
function Failure({ track }: { track: Obj }) {
  if (!track.error_code || track.requires_approval) return null;
  return (
    <Notice
      tone="danger"
      action={
        soundCloudFallback(track) && (
          <Button variant="link" size="s" onClick={() => findOnSoundCloud(track)}>
            {t("Find this song on SoundCloud")}
          </Button>
        )
      }
    >
      <span role="status">
        {track.error_message ? t(track.error_message) : pretty(track.error_code)}
      </span>
    </Notice>
  );
}

// Skip presses in a burst are gathered into one request (every player on the page shows the
// song they lead to at once), so the house only loads the song where the presses stop.
const skips = {
  waiting: 0, // pressed, not sent yet
  sending: 0, // sent, until the queue is read again
  timer: 0,
  burst: null as Promise<Obj> | null,
  send: null as null | (() => Promise<void>),
  listeners: new Set<() => void>(),
  changed: () => skips.listeners.forEach((listener) => listener()),
};
const SKIP_GATHER_MS = 350;
const skipsAhead = () => skips.waiting + skips.sending;
const followSkips = (listener: () => void) => {
  skips.listeners.add(listener);
  return () => void skips.listeners.delete(listener);
};

/** Shared direct controls; displayed progress is bounded interpolation of real observations. */
export function useMusicPlayback(enabled = true) {
  // Idle houses poll slowly: queue and playback changes also arrive as server events.
  const state = useData(enabled ? "/music" : null, {
    interval: (d) => (d?.current_id ? 3000 : 15000),
  });
  const ahead = useSyncExternalStore(followSkips, skipsAhead);
  const queue = items(state.data);
  const playingNow = queue.find((item) => item.id === state.data?.current_id);
  const next = queue.filter((item) => item.id !== playingNow?.id && item.status === "ready");
  const current = ahead ? next[Math.min(ahead, next.length) - 1] || playingNow : playingNow;
  const observation = state.data?.observation || {};
  const matches =
    !!current && observation.status === "observed" && observation.item_id === current.id;
  const running = matches && observation.idle === false && observation.paused === false;
  // Something moves (the position, or a live countdown): usePosition ticks, in the progress UI only.
  const moving = enabled && (running || !!current?.live_until);
  // An observation older than 6 s no longer counts as playing: re-render once when it expires.
  const [, expire] = useState(0);
  useEffect(() => {
    if (!running) return;
    const stale = setTimeout(() => expire((n) => n + 1), state.updatedAt + 6001 - Date.now());
    return () => clearTimeout(stale);
  }, [running, state.updatedAt]);
  // A song the house is starting (or skipping to) counts as playing: no Play/Paused flicker.
  const starting =
    state.data?.desired === "playing" &&
    (ahead > 0 || ["ready", "resolving", "buffering"].includes(current?.status));
  const playing = (running && !state.error && Date.now() - state.updatedAt <= 6000) || starting;
  const positionAt = (now: number) =>
    matches
      ? Math.min(
          current?.duration || Infinity,
          Math.max(0, Number(observation.position) || 0) +
            (running ? Math.min(Math.max(0, now - state.updatedAt), 6000) / 1000 : 0),
        )
      : 0;
  const control = async (action: string, value?: number | string) => {
    if (action === "skip") {
      skips.waiting += 1;
      skips.changed();
      clearTimeout(skips.timer);
      skips.burst ||= new Promise((resolve, reject) => {
        const send = async () => {
          const count = skips.waiting;
          skips.waiting = 0;
          skips.sending += count;
          skips.burst = null;
          try {
            resolve(
              await api("/music/control", "POST", {
                action: "skip",
                value: count,
                expected_version: state.data?.version,
                idempotency_key: idempotency(),
              }),
            );
            await state.reload();
          } catch (e) {
            reject(e);
          } finally {
            skips.sending -= count;
            skips.changed();
          }
        };
        skips.send = send;
      });
      skips.timer = window.setTimeout(() => void skips.send?.(), SKIP_GATHER_MS);
      return skips.burst;
    }
    const result = await api("/music/control", "POST", {
      action,
      value,
      expected_version: state.data?.version,
      idempotency_key: idempotency(),
    });
    await state.reload();
    return result;
  };
  return { ...state, current, playing, moving, positionAt, control };
}
type Playback = ReturnType<typeof useMusicPlayback>;

/** The song's position and the clock, ticking each second while something moves (visible tab):
 *  only the progress UI that calls this re-renders, not every holder of the playback. */
export function usePosition(music: Playback) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!music.moving) return;
    const tick = setInterval(() => {
      if (!document.hidden) setNow(Date.now());
    }, 1000);
    return () => clearInterval(tick);
  }, [music.moving]);
  return { position: music.positionAt(now), now };
}

export function useCanControl() {
  const user = useUser();
  return user?.role === "admin" || !!user?.permissions?.includes("music.control");
}

/** Runs a queue action, reporting failure instead of throwing. */
function useAction(reload: () => Promise<unknown>) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      setError("");
      await reload();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { error, setError, busy, run };
}

/** Adds a song by its link; the house starts playing at once when nothing is. */
const queueSong = (source_url: string) =>
  api("/music/queue", "POST", { source_url, idempotency_key: idempotency() });

// Why the speaker or TV chosen for the music is silent (the follower's last problem).
const SPEAKER_TROUBLE: Record<string, string> = {
  TARGET_OFFLINE:
    "The chosen speaker or TV didn't answer, so the music is silent there. Check it's on.",
  SPEAKER_REFUSED:
    "The chosen speaker refused the song. A grouped Sonos: choose the group's main speaker.",
  SERVER_ONLY_SONG:
    "This one plays only on the server's own speakers, not on the chosen speaker. The next song plays there again.",
};

// ---------- the deck: what the house is playing ----------
/** What a radio says it is playing, with a way to find that song. Speaker mode searches in a
 * new tab: leaving its page would stop the music on this device. */
export function OnAir({ track, keepPage = false }: { track?: Obj | null; keepPage?: boolean }) {
  if (!track?.now_title) return null;
  return (
    <p className="listen-onair">
      <Icon name="radio" size="s" />
      <span>{track.now_title}</span>
      <Button
        variant="link"
        size="s"
        onClick={() => {
          const url = "/listen?q=" + encodeURIComponent(track.now_title) + "&find=1";
          if (keepPage) window.open(url, "_blank", "noopener");
          else go(url);
        }}
      >
        {t("Find this song")}
      </Button>
    </p>
  );
}

export function Deck({
  music,
  compact = false,
  menu,
}: {
  music: Playback;
  compact?: boolean;
  /** More for the player (Listen: party mode, this device, the jukebox's settings). */
  menu?: ReactNode;
}) {
  const user = useUser();
  const { data, current, playing, reload } = music;
  const { position, now } = usePosition(music);
  const canControl = useCanControl();
  const { error, run } = useAction(reload);
  const favorite = useData(current ? "/music/current/favorite" : null);
  useEffect(() => {
    if (current) void favorite.reload();
  }, [current?.id]);
  const control = (action: string, value?: number | string) =>
    run(() => music.control(action, value));
  const version = { expected_version: data?.version };
  const liveLeft = current?.live_until ? current.live_until * 1000 - now : null;
  // Said in the deck's one status line, so the deck never changes size between songs.
  const preparing = current?.download_state === "downloading" ? t("Downloading audio…") : "";
  // The full deck tells the Now bar it needn't repeat the song (see shell.tsx).
  useEffect(() => {
    if (compact) return;
    document.documentElement.dataset.deck = "";
    dispatchEvent(new CustomEvent("houseos:deck", { detail: true }));
    return () => {
      delete document.documentElement.dataset.deck;
      dispatchEvent(new CustomEvent("houseos:deck", { detail: false }));
    };
  }, [compact]);
  return (
    <section
      className="listen-deck"
      data-compact={compact || undefined}
      aria-label={t("Now playing")}
    >
      <ThemeLayers where="deck" playing={playing} />
      <div className="listen-deck__art">
        <Media
          src={current?.art}
          alt={current ? t("Artwork") + " · " + current.title : ""}
          ratio="1 / 1"
        />
        <span className="listen-deck__badges">
          {current?.is_live && <Chip kind="tag">{t("Live")}</Chip>}
          {current?.streamed && <Chip kind="tag">{t("Streamed")}</Chip>}
        </span>
      </div>
      <div className="listen-deck__info">
        <div className="listen-deck__head">
          <Text style="label" tone="muted">
            {preparing ||
              (playing ? t("Playing now") : current ? t("Paused") : t("A little quiet, for now"))}
          </Text>
          {menu}
        </div>
        <h2 className="listen-deck__title">{current?.title || t("Nothing is playing.")}</h2>
        <p className="listen-deck__meta">
          {current ? (
            <>
              <Requester person={current.requester} auto={current.auto} />
              {current.uploader && <span>{current.uploader}</span>}
            </>
          ) : (
            t("Search a song, paste a link or pick a radio below.")
          )}
        </p>
        <OnAir track={current} />
      </div>
      {current && music.data?.plays_on === "cast" && music.data.output_problem && (
        <Notice
          tone="warning"
          action={
            user?.role === "admin" && (
              <Button variant="link" size="s" onClick={() => go("/control?tab=speakers")}>
                {t("Choose speakers")}
              </Button>
            )
          }
        >
          {t(SPEAKER_TROUBLE[music.data.output_problem] || SPEAKER_TROUBLE.TARGET_OFFLINE)}
        </Notice>
      )}
      {current && music.data?.plays_on === "nowhere" && (
        <Notice
          tone="warning"
          action={
            <Cluster>
              <Button variant="link" size="s" onClick={() => go("/speaker")}>
                {t("Play on this device")}
              </Button>
              {user?.role === "admin" && (
                <Button variant="link" size="s" onClick={() => go("/control?tab=speakers")}>
                  {t("Choose speakers")}
                </Button>
              )}
            </Cluster>
          }
        >
          {t("No speaker is playing this: this computer has none chosen.")}
        </Notice>
      )}
      {current?.retention_error && (
        <Text style="caption" tone="muted">
          {t("Plays now, but could not save to storage.")}
        </Text>
      )}
      {current && <Failure track={current} />}
      {current?.requires_approval &&
        current.is_live &&
        (current.owner_id === user?.id || canControl) && (
          <Button
            variant="primary"
            onClick={() =>
              void run(() => api("/music/queue/" + current.id + "/approve-live", "POST", version))
            }
          >
            {t("Play this live stream (up to 1 hour)")}
          </Button>
        )}
      {current?.is_live && liveLeft !== null && liveLeft < 15 * 60000 && canControl && (
        <Button
          onClick={() =>
            void run(async () => {
              const r = await api("/music/queue/" + current.id + "/renew-live", "POST", version);
              toast(r.status === "completed" ? t("One more hour of radio.") : pretty(r.status));
            })
          }
        >
          {t("Still listening? One more hour")}
        </Button>
      )}
      {current &&
        current.duration > 0 &&
        !current.is_live &&
        (canControl && !current.streamed ? (
          <Slider
            label={t("Playback position")}
            value={Math.round(position)}
            max={Math.floor(current.duration)}
            format={(value) => clock(value) + " / " + clock(current.duration)}
            onCommit={(value) => void control("seek", value)}
          />
        ) : (
          <Text style="caption" tone="muted" className="tabular">
            {clock(position) + " / " + clock(current.duration)}
          </Text>
        ))}
      <div className="listen-deck__keys">
        {canControl ? (
          <>
            <IconButton
              glyph="transport.previous"
              label={t("Previous track")}
              disabled={!current || current.is_live}
              onClick={() => void control("previous")}
            />
            <IconButton
              glyph={playing ? "transport.pause" : "transport.play"}
              size="l"
              variant="primary"
              label={playing ? t("Pause") : t("Play")}
              onClick={() => void control(playing ? "pause" : "play")}
            />
            <IconButton
              glyph="transport.next"
              label={t("Next track")}
              disabled={!current}
              onClick={() => void control("skip")}
            />
          </>
        ) : (
          current && (
            <Button
              onClick={() =>
                void run(async () => {
                  const r = await api("/music/queue/" + current.id + "/skip-vote", "POST", version);
                  toast(
                    t("{votes} of {threshold} skip votes")
                      .replace("{votes}", r.votes)
                      .replace("{threshold}", r.threshold),
                  );
                })
              }
            >
              {t("Vote to skip this track")}
            </Button>
          )
        )}
        {current && (
          <IconButton
            icon="heart"
            pressed={!!favorite.data?.favorite}
            label={
              favorite.data?.favorite
                ? t("Remove current track from favorites")
                : t("Favorite current track")
            }
            disabled={favorite.data?.item_id !== current.id || !favorite.data?.supported}
            onClick={() =>
              void run(async () => {
                if (favorite.data?.favorite && favorite.data.saved_id)
                  await api("/music/saved/" + favorite.data.saved_id, "DELETE");
                else await api("/music/current/favorite", "POST", { item_id: current.id });
                await favorite.reload();
              })
            }
          />
        )}
        {canControl && (
          <span className="listen-deck__volume">
            <Slider
              label={t("Volume")}
              icon="volume"
              value={data?.volume ?? 60}
              onCommit={(value) => void control("volume", value)}
            />
          </span>
        )}
      </div>
      {!canControl && current && current.owner_id !== user?.id && (
        <VetoButton row={current} music={music} />
      )}
      {!compact && <StopAndClear music={music} />}
      <Problem error={error || music.error || favorite.error} onRetry={reload} />
    </section>
  );
}

/** Stop (pause and release the speakers) and Clear queue, with a one-tap inline check. */
export function StopAndClear({ music }: { music: Playback }) {
  const canControl = useCanControl();
  const { error, busy, run } = useAction(music.reload);
  const [asking, setAsking] = useState(false);
  const waiting = items(music.data).filter((row) => row.id !== music.data?.current_id).length;
  if (!canControl || (!music.current && !waiting)) return null;
  const clear = () =>
    run(async () => {
      const prepared = await music.control("clear");
      if (prepared.confirmation_id) await api("/music/confirm/" + prepared.confirmation_id, "POST");
      setAsking(false);
    });
  return (
    <div className="listen-stopclear">
      {asking ? (
        <div role="group" aria-label={t("Clear queue")} className="listen-stopclear__ask">
          <Text style="body-s">
            {waiting === 1
              ? t("Remove 1 waiting song?")
              : waiting
                ? t("Remove {n} waiting songs?").replace("{n}", String(waiting))
                : t("Stop and clear the queue?")}
          </Text>
          <Cluster>
            <Button variant="danger" size="s" busy={busy} onClick={() => void clear()}>
              {t("Remove")}
            </Button>
            <Button variant="quiet" size="s" onClick={() => setAsking(false)}>
              {t("Keep")}
            </Button>
          </Cluster>
        </div>
      ) : (
        <Cluster>
          <Button
            size="s"
            icon="stop"
            disabled={busy || !music.current}
            onClick={() => void run(() => music.control("stop"))}
          >
            {t("Stop")}
          </Button>
          <Button size="s" variant="quiet" icon="list-clear" onClick={() => setAsking(true)}>
            {t("Clear queue")}
          </Button>
        </Cluster>
      )}
      <Problem error={error} />
    </div>
  );
}

function JukeboxSettings({
  music,
  control,
  onClose,
}: {
  music: Playback;
  control: (action: string, value?: number | string) => Promise<boolean>;
  onClose: () => void;
}) {
  const { data } = music;
  const admin = useUser()?.role === "admin";
  const [custom, setCustom] = useState(false),
    [minutes, setMinutes] = useState(300);
  return (
    <Sheet title={t("Jukebox settings")} onClose={onClose}>
      <Stack>
        <Field label={t("Repeat playback")}>
          <Segmented
            label={t("Repeat playback")}
            value={data?.repeat_mode || "off"}
            onChange={(mode) => void control("repeat", mode)}
            options={[
              { value: "off", label: t("Off") },
              { value: "one", label: t("Repeat song") },
              { value: "queue", label: t("Repeat queue") },
            ]}
          />
        </Field>
        <Cluster>
          <Button icon="volume-off" onClick={() => void control("mute", 1)}>
            {t("Mute")}
          </Button>
          <Button icon="volume" onClick={() => void control("mute", 0)}>
            {t("Unmute")}
          </Button>
        </Cluster>
        <Field label={t("Sleep timer")}>
          <Select
            defaultValue=""
            onChange={(e) => {
              setCustom(e.target.value === "custom");
              if (e.target.value !== "custom") void control("sleep", Number(e.target.value));
            }}
          >
            <option value="" disabled>
              {t("Set timer")}
            </option>
            <option value="0">{t("Off")}</option>
            <option value="15">{t("15 min")}</option>
            <option value="30">{t("30 min")}</option>
            <option value="60">{t("1 hour")}</option>
            {[2, 3, 4, 5].map((hours) => (
              <option key={hours} value={hours * 60}>
                {hours} h
              </option>
            ))}
            <option value="custom">{t("Custom")}</option>
          </Select>
        </Field>
        {custom && (
          <form
            className="listen-inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              void control("sleep", minutes);
            }}
          >
            <Field label={t("Custom sleep minutes")}>
              <Input
                type="number"
                min={1}
                max={1440}
                required
                value={minutes}
                onChange={(event) => setMinutes(Number(event.target.value))}
              />
            </Field>
            <Button type="submit">{t("Apply")}</Button>
          </form>
        )}
        {data?.sleep_at && (
          <Text style="body-s" tone="muted">
            {t("Music stops at")} {time(data.sleep_at)}
          </Text>
        )}
        {admin && <KeepSongs />}
      </Stack>
    </Sheet>
  );
}

/** The house's download choices (admins): the same settings as Control Room → House. */
function KeepSongs() {
  const house = useData("/admin/house-settings");
  const save = async (change: Obj) => {
    try {
      await api("/admin/house-settings", "PUT", change);
      await house.reload();
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    }
  };
  if (!house.data) return null;
  return (
    <>
      <Switch
        checked={house.data.music_keep_downloads ?? true}
        onChange={(on) => void save({ music_keep_downloads: on })}
        label={t("Keep the songs we play")}
        hint={t("Off: songs are downloaded to play, then deleted.")}
      />
      <Field label={t("Download ahead")}>
        <Select
          value={String(house.data.music_preload ?? 0)}
          onChange={(e) => void save({ music_preload: Number(e.target.value) })}
        >
          <option value="0">{t("The whole queue")}</option>
          {[1, 2, 3, 5, 10].map((n) => (
            <option key={n} value={n}>
              {n === 1
                ? t("The next song")
                : t("The next {count} songs").replace("{count}", String(n))}
            </option>
          ))}
        </Select>
      </Field>
    </>
  );
}

// ---------- the queue: everyone takes turns ----------
function QueueRow({
  row,
  music,
  onActions,
  up,
  down,
  first,
  glance = false,
}: {
  row: Obj;
  music: Playback;
  onActions: (song: Picked) => void;
  /** "Move up" puts it in front of this song (undefined: already as high as it goes). */
  up?: string;
  /** "Move down" puts it in front of this song, null for the end (undefined: already last). */
  down?: string | null;
  /** Already as early as "Play next" can put it (next song for an admin, else first of its owner's). */
  first: boolean;
  /** A glance (Home): the song only, reordering stays in Listen. */
  glance?: boolean;
}) {
  const user = useUser();
  const mine = row.owner_id === user?.id;
  const admin = user?.role === "admin";
  const canControl = useCanControl();
  const { run, error, busy } = useAction(music.reload);
  const version = { expected_version: music.data?.version };
  // Every song in the queue is waiting: only real progress is worth a word here.
  const preparing = row.status === "queued" && !row.download_state ? "" : preparationLabel(row);
  const move = (before?: string | null) =>
    void run(() => api("/music/queue/" + row.id, "PATCH", { ...version, before_item_id: before }));
  return (
    <ListRow
      leading={<Cover src={row.art} />}
      title={row.title}
      detail={
        <span className="listen-detail">
          <Requester person={row.requester} auto={row.auto} />
          {row.duration > 0 && <span className="tabular">{clock(row.duration)}</span>}
          {row.is_live && <span>{t("Live")}</span>}
        </span>
      }
      status={
        preparing
          ? {
              tone: "info",
              text: preparing,
              busy: row.status !== "queued" || row.download_state === "downloading",
            }
          : undefined
      }
      actions={
        !glance && (
          <>
            {!row.pinned && (
              <>
                <IconButton
                  className="listen-queue__step"
                  icon="chevron-up"
                  size="s"
                  disabled={busy || up === undefined}
                  label={t("Move up") + " · " + row.title}
                  onClick={() => move(up)}
                />
                <IconButton
                  className="listen-queue__step"
                  icon="chevron-down"
                  size="s"
                  disabled={busy || down === undefined}
                  label={t("Move down") + " · " + row.title}
                  onClick={() => move(down)}
                />
              </>
            )}
            {(mine || admin) && !row.pinned && (
              <IconButton
                icon="chevrons-up"
                size="s"
                disabled={busy || first}
                label={
                  (mine ? t("Play next among my songs") : t("Play right after this song")) +
                  " · " +
                  row.title
                }
                onClick={() =>
                  void run(() => api("/music/queue/" + row.id + "/next", "POST", version))
                }
              />
            )}
            {(mine || admin) && (
              <IconButton
                icon="close"
                size="s"
                disabled={busy}
                label={t("Remove from the queue") + " · " + row.title}
                onClick={() =>
                  void run(() =>
                    api(
                      "/music/queue/" + row.id + "?expected_version=" + music.data?.version,
                      "DELETE",
                    ),
                  )
                }
              />
            )}
            <IconButton
              icon="more"
              size="s"
              label={t("Song actions") + " · " + row.title}
              onClick={() => onActions({ row, up, down })}
            />
          </>
        )
      }
    >
      {(row.error_code && !row.requires_approval) ||
      (row.requires_approval && row.is_live && (mine || canControl)) ||
      error ? (
        <>
          <Failure track={row} />
          {row.requires_approval && row.is_live && (mine || canControl) && (
            <Button
              size="s"
              onClick={() =>
                void run(() => api("/music/queue/" + row.id + "/approve-live", "POST", version))
              }
            >
              {t("Allow this live stream (up to 1 hour)")}
            </Button>
          )}
          <Problem error={error} />
        </>
      ) : null}
    </ListRow>
  );
}

/** Everyone's one veto (back three hours after use): skips someone else's playing song or
 *  takes their waiting one out. Says when it is back while it reloads. */
function VetoButton({ row, music, onDone }: { row: Obj; music: Playback; onDone?: () => void }) {
  const { run, error, busy } = useAction(music.reload);
  const back = music.data?.veto_back_at;
  return (
    <>
      <Button
        variant="quiet"
        icon="block"
        disabled={busy || !!back}
        title={t("One veto each, back three hours after use.")}
        onClick={() =>
          void run(() =>
            api("/music/queue/" + row.id + "/veto", "POST", {
              expected_version: music.data?.version,
            }),
          ).then((ok) => ok && onDone?.())
        }
      >
        {back
          ? t("Veto back at {time}").replace(
              "{time}",
              date(back, { hour: "2-digit", minute: "2-digit" }),
            )
          : row.id === music.data?.current_id
            ? t("Veto this song (skip it)")
            : t("Veto this song (take it out)")}
      </Button>
      <Problem error={error} />
    </>
  );
}

/** A song picked in the queue, with where "Move up" and "Move down" put it (see QueueRow). */
type Picked = { row: Obj; up?: string; down?: string | null };

/** Whoever kept a song on the house, or an admin, may delete it from there. */
const mayForget = (row: Obj, user: Obj | null | undefined) =>
  !!row.kept_by && (row.kept_by === user?.id || user?.role === "admin");

/** Delete a queued song's kept file. Playing now, it plays to its end first (the speakers read
 *  their own copy); waiting, it leaves the queue unplayed. */
function ForgetSong({ row, music, onClose }: { row: Obj; music: Playback; onClose: () => void }) {
  const playing = row.id === music.data?.current_id;
  return (
    <ConfirmSheet
      title={t("Delete “{title}” from the house?").replace("{title}", row.title)}
      confirm={t("Delete")}
      danger
      onClose={onClose}
      onConfirm={async () => {
        await api("/music/queue/" + row.id + "/kept", "DELETE");
        toast(
          playing
            ? t("Deleted from the house. It plays to its end.")
            : t("Deleted from the house."),
        );
        await music.reload();
      }}
    >
      <Text>
        {playing
          ? t(
              "The song keeps playing to its end, then it's gone. Whoever wants it again adds it again.",
            )
          : t("It leaves the queue without playing. Whoever wants it again adds it again.")}
      </Text>
    </ConfirmSheet>
  );
}

function SongActions({
  row,
  up,
  down,
  music,
  onClose,
}: Picked & { music: Playback; onClose: () => void }) {
  const user = useUser();
  const admin = user?.role === "admin";
  const { run, error, busy } = useAction(music.reload);
  const mine = row.owner_id === user?.id;
  const version = { expected_version: music.data?.version };
  const [listing, setListing] = useState(false);
  const [forgetting, setForgetting] = useState(false);
  if (forgetting) return <ForgetSong row={row} music={music} onClose={onClose} />;
  const act = (fn: () => Promise<unknown>, done?: string) =>
    void run(fn).then((ok) => {
      if (!ok) return;
      if (done) toast(done);
      onClose();
    });
  return (
    <Sheet title={row.title} onClose={onClose}>
      <Stack space={2}>
        {!row.pinned && (up !== undefined || down !== undefined) && (
          <div className="listen-sheet__steps">
            <Button
              wide
              icon="chevron-up"
              disabled={busy || up === undefined}
              onClick={() =>
                act(() =>
                  api("/music/queue/" + row.id, "PATCH", { ...version, before_item_id: up }),
                )
              }
            >
              {t("Move up")}
            </Button>
            <Button
              wide
              icon="chevron-down"
              disabled={busy || down === undefined}
              onClick={() =>
                act(() =>
                  api("/music/queue/" + row.id, "PATCH", { ...version, before_item_id: down }),
                )
              }
            >
              {t("Move down")}
            </Button>
          </div>
        )}
        {(mine || admin) && (
          <Button
            wide
            icon="chevrons-up"
            disabled={busy}
            onClick={() => act(() => api("/music/queue/" + row.id + "/next", "POST", version))}
          >
            {mine ? t("Play next among my songs") : t("Play right after this song")}
          </Button>
        )}
        {!row.source_url?.startsWith("houseos-file:") && (
          <Button
            wide
            icon="heart"
            disabled={busy}
            onClick={() =>
              act(
                () =>
                  api("/music/saved", "POST", {
                    source_url: row.source_url,
                    idempotency_key: idempotency(),
                  }),
                t("Saved to your tracks."),
              )
            }
          >
            {t("Save to my tracks")}
          </Button>
        )}
        {row.source_url?.startsWith("https://") && (
          <Button wide icon="list-add" pressed={listing} onClick={() => setListing(!listing)}>
            {t("Add to playlist")}
          </Button>
        )}
        {listing && (
          <AddToPlaylist
            song={row}
            onDone={(text) => {
              setListing(false);
              toast(text);
            }}
          />
        )}
        {soundCloudFallback(row) && (
          <Button
            wide
            icon="search"
            onClick={() => {
              onClose();
              findOnSoundCloud(row);
            }}
          >
            {t("Find this song on SoundCloud")}
          </Button>
        )}
        {!mine && <VetoButton row={row} music={music} onDone={onClose} />}
        {(mine || admin) && (
          <Button
            wide
            variant="danger"
            icon="trash"
            disabled={busy}
            onClick={() =>
              act(() =>
                api(
                  "/music/queue/" + row.id + "?expected_version=" + music.data?.version,
                  "DELETE",
                ),
              )
            }
          >
            {t("Remove from the queue")}
          </Button>
        )}
        {mayForget(row, user) && (
          <Button wide variant="danger" icon="trash" onClick={() => setForgetting(true)}>
            {t("Delete from the house")}
          </Button>
        )}
        <Problem error={error} />
      </Stack>
    </Sheet>
  );
}

const QUEUE_PAGE = 30;

export function Queue({ music, limit }: { music: Playback; limit?: number }) {
  const user = useUser();
  const { run, error } = useAction(music.reload);
  const [selected, setSelected] = useState<Picked | null>(null);
  const auto = useData(limit ? null : "/music/auto");
  const pending = items(music.data).filter((row) => row.id !== music.data?.current_id);
  // A long queue draws 30 songs, then 30 more each time its end comes near (MoreBelow).
  const [drawn, setDrawn] = useState(QUEUE_PAGE);
  const shown = pending.slice(0, limit ?? drawn);
  const fair = !!music.data?.fair;
  const mine = pending.filter((row) => row.owner_id === user?.id).length;
  const group = (row: Obj) =>
    row.pinned
      ? "Right after this song"
      : row.auto
        ? "Auto play: after everyone's songs"
        : fair && row.round
          ? "round:" + row.round
          : "";
  const rows: ReactNode[] = [];
  shown.forEach((row, index) => {
    const label = group(row);
    if (label && label !== group(shown[index - 1] || {}))
      rows.push(
        <ListHeading key={"g" + label + index}>
          <span className="listen-round">
            {label === "Right after this song"
              ? t("Right after this song")
              : label === "Auto play: after everyone's songs"
                ? t("Auto play: after everyone's songs")
                : t("Round {n}").replace("{n}", label.slice(6))}
          </span>
        </ListHeading>,
      );
    // Anyone moves any waiting song one step (songs pinned "right after this one" stay put).
    const earlier = pending.slice(0, pending.indexOf(row)).filter((other) => !other.pinned);
    const line = pending.filter((other) => !other.pinned);
    const at = line.indexOf(row);
    rows.push(
      <QueueRow
        key={row.id}
        row={row}
        music={music}
        onActions={setSelected}
        glance={!!limit}
        up={at > 0 ? line[at - 1].id : undefined}
        down={at >= 0 && at < line.length - 1 ? (line[at + 2]?.id ?? null) : undefined}
        first={
          user?.role === "admin"
            ? pending[0]?.id === row.id
            : !earlier.some((other) => other.owner_id === row.owner_id)
        }
      />,
    );
  });
  return (
    <section
      className="listen-queue"
      aria-labelledby="listen-queue-title"
      data-empty={pending.length ? undefined : ""}
    >
      <Section
        title={
          <span id="listen-queue-title" className="listen-queue__title">
            {t("Up next")} <Badge tone="neutral">{pending.length}</Badge>
          </span>
        }
        actions={
          !limit && (
            <>
              {mine > 1 && (
                <Button
                  variant="quiet"
                  size="s"
                  icon="shuffle"
                  onClick={() =>
                    void run(() =>
                      api("/music/queue/shuffle-mine", "POST", {
                        expected_version: music.data?.version,
                      }),
                    )
                  }
                >
                  {t("Shuffle my songs")}
                </Button>
              )}
            </>
          )
        }
        lead={
          fair && !limit && pending.length > 0
            ? t("New songs take turns: one each per round. Anyone can then move them.")
            : undefined
        }
      >
        {!limit && <Unavailable music={music} />}
        {music.data?.last_veto && (
          <Text style="body-s" tone="muted" className="listen-vetoed">
            {t("{name} used their veto on “{title}”.")
              .replace("{name}", music.data.last_veto.by)
              .replace("{title}", music.data.last_veto.title || t("a song"))}
          </Text>
        )}
        <Problem error={error} />
        {pending.length ? (
          <>
            <List label={t("Up next")}>{rows}</List>
            {!limit && (
              <MoreBelow
                pages={{
                  more:
                    shown.length < pending.length
                      ? () => setDrawn((n) => n + QUEUE_PAGE)
                      : undefined,
                  loading: false,
                  items: shown,
                }}
              />
            )}
          </>
        ) : (
          <Text style="body-s" tone="muted">
            {music.current ? t("No songs queued next.") : t("Nothing queued. Add the first song.")}
          </Text>
        )}
        {!limit && auto.data && auto.data.mode !== "off" && (
          <Text style="body-s" tone="muted" className="listen-autoline">
            <Icon name="shuffle" size="s" />
            <span>
              <strong>{t("Auto play is on")}</strong> ·{" "}
              {auto.data.mode === "radio"
                ? t("a radio rotation, until someone adds a song")
                : t("the house's songs, until someone adds a song")}
            </span>
          </Text>
        )}
        {limit && pending.length > 0 && (
          <Button variant="link" onClick={() => go("/listen")}>
            {t("See the whole queue")} ({pending.length})
          </Button>
        )}
      </Section>
      {selected && <SongActions {...selected} music={music} onClose={() => setSelected(null)} />}
    </section>
  );
}

/** Auto play's next songs, in order: move, remove, or draw a new list (residents). */
function AutoPlaySheet({ onClose }: { onClose: () => void }) {
  const plan = useData("/music/auto/upcoming");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const list: Obj[] = plan.data?.items || [];
  const urls = list.map((song) => song.source_url);
  const change = async (body: Obj) => {
    setBusy(true);
    setError("");
    try {
      await api("/music/auto/upcoming", "PUT", { version: plan.data?.version ?? 0, ...body });
    } catch (e) {
      setError(errorText(e));
    } finally {
      await plan.reload();
      setBusy(false);
    }
  };
  const move = (from: number, to: number) => {
    const next = [...urls];
    next.splice(to, 0, next.splice(from, 1)[0]);
    void change({ urls: next });
  };
  const can = !!plan.data?.can_change;
  return (
    <Sheet title={t("Auto play: next songs")} onClose={onClose}>
      <Stack>
        <Text style="body-s" tone="muted">
          {t(
            "Played in this order whenever nobody has queued a song. Songs you remove stay out until you draw a new list.",
          )}
        </Text>
        {can && (
          <Button
            icon="shuffle"
            disabled={busy || !list.length}
            onClick={() => void change({ shuffle: true })}
          >
            {t("Draw a new random list")}
          </Button>
        )}
        <Problem error={error || plan.error} onRetry={plan.reload} />
        {!plan.data && !plan.error && <State kind="loading" />}
        <List>
          {list.map((song, index) => (
            <ListRow
              key={song.source_url}
              leading={<Cover src={song.art} />}
              title={song.title}
              meta={index + 1}
              detail={
                <span className="listen-detail">
                  {song.uploader && <span>{song.uploader}</span>}
                  <GenreTag genre={song.genre} />
                </span>
              }
              actions={
                can && (
                  <>
                    <IconButton
                      icon="chevron-up"
                      size="s"
                      label={t("Move up") + " · " + song.title}
                      disabled={busy || index === 0}
                      onClick={() => move(index, index - 1)}
                    />
                    <IconButton
                      icon="chevron-down"
                      size="s"
                      label={t("Move down") + " · " + song.title}
                      disabled={busy || index === list.length - 1}
                      onClick={() => move(index, index + 1)}
                    />
                    <IconButton
                      icon="close"
                      size="s"
                      label={t("Remove") + " · " + song.title}
                      disabled={busy}
                      onClick={() =>
                        void change({ urls: urls.filter((u) => u !== song.source_url) })
                      }
                    />
                  </>
                )
              }
            />
          ))}
        </List>
        {plan.data && !list.length && (
          <Text style="body-s" tone="muted">
            {t("Auto play isn't playing the house's kept songs right now.")}
          </Text>
        )}
      </Stack>
    </Sheet>
  );
}

// ---------- adding: one field for search, links and playlists ----------
/** An empty queue offers a start: the house's own songs, a few stations, or a song of yours. */
// News, talk and sport stations are not a way to start the music.
const NOT_MUSIC =
  /news|talk|politic|sport|relig|christ|islam|quran|bible|gospel|info|actualit|nachricht|noticia/i;
const musical = (station: Obj) => !NOT_MUSIC.test(`${station.name} ${station.tags || ""}`);

function QuickStarts({ music }: { music: Playback }) {
  const auto = useData("/music/auto"),
    songs = useData("/music/quick-songs"),
    favourites = useData("/music/radio/favorites");
  const popular = useData(
    favourites.data && !items(favourites.data).length
      ? "/music/radio?order=trending&https=true"
      : null,
  );
  const { run, error, busy } = useAction(music.reload);
  const stations = (
    items(favourites.data).filter(musical).length
      ? items(favourites.data).filter(musical)
      : items(popular.data).filter(musical)
  ).slice(0, 2);
  const kept = auto.data?.kept || 0;
  const start = (fn: () => Promise<unknown>) => () => void run(fn);
  return (
    <section className="listen-starts" aria-label={t("Start the music")}>
      <Text as="h2" style="title-s">
        {t("Ideas")}
      </Text>
      <List label={t("Start the music")}>
        {items(songs.data).map((song: Obj) => (
          <ListRow
            key={song.source_url}
            leading={<Cover src={song.art} />}
            title={song.title || t("Untitled song")}
            detail={song.why === "missed" ? t("not heard for a while") : t("played a lot lately")}
            onOpen={busy ? undefined : start(() => queueSong(song.source_url))}
          />
        ))}
        {auto.data?.can_change && kept > 0 && auto.data?.mode === "off" && (
          <ListRow
            leading={<Icon name="shuffle" />}
            title={t("Play the house's songs")}
            detail={t("{n} songs kept, by the whole house").replace("{n}", String(kept))}
            onOpen={
              busy
                ? undefined
                : start(() =>
                    api("/music/auto", "PUT", { mode: "library", genres: [], stations: [] }),
                  )
            }
          />
        )}
        {stations.map((r: Obj) => (
          <ListRow
            key={r.id}
            leading={<Icon name="radio" />}
            title={r.name}
            detail={
              [r.country, (r.tags || "").split(",")[0]].filter(Boolean).join(" · ") || t("Radio")
            }
            onOpen={
              busy
                ? undefined
                : start(() =>
                    api(`/music/radio/${r.id}/queue`, "POST", { idempotency_key: idempotency() }),
                  )
            }
          />
        ))}
        <ListRow
          leading={<Icon name="sparkles" />}
          title={t("Let Nox pick")}
          detail={t("a few songs for the mood")}
          onOpen={() =>
            dispatchEvent(
              new CustomEvent("houseos:ask", {
                detail: { message: t("Pick a few songs for right now and queue them.") },
              }),
            )
          }
        />
      </List>
      <Problem error={error} />
    </section>
  );
}

const SEARCH_PAGE = 15;
export function AddBar({
  music,
  onResults,
}: {
  music: Playback;
  /** Told when results show or go, so the page can give them the ideas' place. */
  onResults?: (shown: boolean) => void;
}) {
  const params = () => new URLSearchParams(location.search);
  const [text, setText] = useState(params().get("q") || ""),
    [source, setSource] = useState(
      params().get("source") === "soundcloud" ? "soundcloud" : "youtube",
    ),
    [results, setResults] = useState<Obj[] | null>(null),
    [asked, setAsked] = useState({ query: "", from: "youtube", limit: 0 }),
    [added, setAdded] = useState<Set<string>>(new Set()),
    [playlist, setPlaylist] = useState<Obj | null>(null);
  const { run, error, setError, busy } = useAction(music.reload);
  const input = useRef<HTMLInputElement>(null);
  const idle = !!music.data?.autoplay_on_add;
  useEffect(() => {
    const prefill = () => {
      const next = params();
      if (!next.get("q")) return;
      setText(next.get("q") || "");
      setSource(next.get("source") === "soundcloud" ? "soundcloud" : "youtube");
      // "Find this song" (from the radio) searches straight away.
      if (next.get("find")) void submit(next.get("q") || "", "youtube");
      requestAnimationFrame(() => {
        input.current?.scrollIntoView({ block: "center" });
        input.current?.focus({ preventScroll: true });
      });
    };
    prefill();
    window.addEventListener("popstate", prefill);
    return () => window.removeEventListener("popstate", prefill);
  }, []);
  useEffect(() => onResults?.(!!results), [results]);
  const link = isLink(text);
  const submit = (query = text, from = source) =>
    run(async () => {
      if (elsewhere(query)) {
        // Spotify & co.: the song's name, then its versions on YouTube to pick from.
        query = (await api("/music/link-song?url=" + encodeURIComponent(query.trim()))).query;
        from = "youtube";
        setText(query);
      }
      const link = isLink(query);
      const text = query;
      if (link && isPlaylist(text)) {
        const r = await api("/music/playlists/preview", "POST", {
          source_url: text.trim(),
          idempotency_key: idempotency(),
        });
        if (!r.confirmation_id) throw new Error(pretty(r.code || r.status));
        setPlaylist(r);
      } else if (link) {
        await queueSong(text.trim());
        setText("");
        toast(idle ? t("Starting…") : t("Added to the queue."));
      } else {
        const r = await api(
          "/music/search?q=" +
            encodeURIComponent(text) +
            "&source=" +
            from +
            "&limit=" +
            SEARCH_PAGE,
        );
        if (r.status !== "completed") throw new Error(pretty(r.code || r.status));
        setResults(items(r));
        setAsked({ query: text, from, limit: SEARCH_PAGE });
        setAdded(new Set());
      }
    });
  // More results: the same search asked for more, new ones appended (the first stay put).
  const more = () =>
    run(async () => {
      const limit = Math.min(50, asked.limit + SEARCH_PAGE);
      const r = await api(
        "/music/search?q=" +
          encodeURIComponent(asked.query) +
          "&source=" +
          asked.from +
          "&limit=" +
          limit,
      );
      if (r.status !== "completed") throw new Error(pretty(r.code || r.status));
      const known = new Set((results || []).map((row) => row.source_url));
      setResults([...(results || []), ...items(r).filter((row) => !known.has(row.source_url))]);
      setAsked({ ...asked, limit });
    });
  return (
    <section className="listen-add" aria-label={t("Add music")}>
      <form
        className="listen-add__field"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <span className="listen-add__input">
          <Icon name="search" size="s" />
          <Input
            ref={input}
            id="listen-add-input"
            aria-label={t("Search music")}
            placeholder={t("Paste a link, or search a song, an artist, a playlist…")}
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
          />
        </span>
        {!link && (
          <Select
            aria-label={t("Music source")}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="youtube">{t("YouTube")}</option>
            <option value="soundcloud">{t("SoundCloud")}</option>
          </Select>
        )}
        <Button type="submit" variant="primary" busy={busy}>
          {!link
            ? t("Search")
            : isPlaylist(text)
              ? t("Preview playlist")
              : idle
                ? t("Play")
                : t("Add to queue")}
        </Button>
      </form>
      <Text style="caption" tone="muted">
        {t("A song, an artist, a playlist, a YouTube or SoundCloud link. Or just ask Nox.")}
      </Text>
      <Problem error={error} />
      {results && (
        <div className="listen-add__head">
          <Text style="label" tone="muted">
            {t("Results for “{query}”").replace("{query}", asked.query)}
          </Text>
          <Button variant="quiet" size="s" icon="close" onClick={() => setResults(null)}>
            {t("Close")}
          </Button>
        </div>
      )}
      {results && (
        <List label={t("Search results")}>
          {results.map((r) => (
            <ListRow
              key={r.id}
              leading={<Cover src={r.thumbnail ? ART + "candidate/" + r.id : r.art || null} />}
              title={r.title}
              detail={
                <span className="listen-detail">
                  {r.at_home && <Badge tone="success">{t("At home")}</Badge>} {r.uploader}{" "}
                  <span className="tabular">{clock(r.duration)}</span>
                </span>
              }
              actions={
                <Button
                  size="s"
                  disabled={added.has(r.id)}
                  aria-label={
                    (added.has(r.id) ? t("Added") : idle ? t("Play") : t("Add to queue")) +
                    " · " +
                    r.title
                  }
                  onClick={() =>
                    void run(async () => {
                      await api("/music/candidates", "POST", {
                        candidate_id: r.id,
                        idempotency_key: idempotency(),
                      });
                      setAdded(new Set(added).add(r.id));
                    })
                  }
                >
                  {added.has(r.id) ? t("Added") : idle ? t("Play") : t("Add to queue")}
                </Button>
              }
            />
          ))}
          {!results.length && (
            <li>
              <Text style="body-s" tone="muted">
                {t("Nothing found. Try other words.")}
              </Text>
            </li>
          )}
          {results.length > 0 && asked.limit < 50 && results.length >= asked.limit - 3 && (
            <li className="listen-results__more">
              <Button busy={busy} onClick={() => void more()}>
                {t("More results")}
              </Button>
            </li>
          )}
        </List>
      )}
      {playlist && (
        <PlaylistPreview
          url={text.trim()}
          preview={playlist}
          onClose={() => setPlaylist(null)}
          onDone={(text) => {
            setPlaylist(null);
            setText("");
            toast(text);
            setError("");
            void music.reload();
          }}
        />
      )}
    </section>
  );
}

function PlaylistPreview({
  url,
  preview,
  onClose,
  onDone,
}: {
  url: string;
  preview: Obj;
  onClose: () => void;
  onDone: (notice: string) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const tracks = items(preview);
  const total = preview.total || tracks.length;
  const keep = async () => {
    setBusy(true);
    try {
      const kept = await api(LISTS + "/import", "POST", { url, name: preview.title || undefined });
      onDone(t("Kept as “{name}” in My music.").replace("{name}", kept.name));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      title={preview.title || t("Playlist")}
      onClose={onClose}
      footer={
        <Cluster>
          <Button icon="list-add" disabled={busy} onClick={() => void keep()}>
            {t("Keep as a playlist")}
          </Button>
          <Button
            variant="primary"
            busy={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await api(
                  "/music/playlists/" + preview.confirmation_id + "/confirm",
                  "POST",
                );
                onDone(
                  (r.status === "running"
                    ? t("{n} songs added. The rest keeps coming in; follow it in activity.")
                    : t("{n} songs added to the queue.")
                  ).replace("{n}", String(r.added)),
                );
              } catch (e) {
                setError(errorText(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("Queue {n} songs").replace("{n}", String(total))}
          </Button>
        </Cluster>
      }
    >
      <Stack>
        <Text style="body-s" tone="muted">
          {t("{n} songs").replace("{n}", String(total))}
          {total > tracks.length && " · " + t("the rest is added in the background")}
        </Text>
        <ol className="listen-preview">
          {tracks.slice(0, 50).map((track, i) => (
            <li key={i}>{track.title}</li>
          ))}
        </ol>
        {total > 50 && (
          <Text style="body-s" tone="muted">
            {t("…and {n} more").replace("{n}", String(total - 50))}
          </Text>
        )}
        <Problem error={error} />
      </Stack>
    </Sheet>
  );
}

// ---------- the room's places: radio, my music, history, auto play ----------
const RADIO_ORDERS: [string, string][] = [
  ["popular", "Popular"],
  ["trending", "Trending"],
  ["liked", "Most liked"],
  ["new", "New"],
  ["random", "Surprise me"],
];
// Well-loved free, ad-light networks, one tap away (each is a name search in the directory).
const RADIO_COLLECTIONS = [
  "SomaFM",
  "Radio Paradise",
  "FIP",
  "KEXP",
  "Jazz24",
  "Nightride FM",
  "NTS",
];

function RadioPlace({ idle }: { idle: boolean }) {
  const [query, setQuery] = useState(""),
    [filters, setFilters] = useState({ tag: "", country: "", language: "", order: "popular" }),
    [phones, setPhones] = useState(false),
    [page, setPage] = useState(0),
    [surprise, setSurprise] = useState(0),
    [searched, setSearched] = useState("");
  const path =
    "/music/radio?" +
    new URLSearchParams({
      q: searched,
      ...filters,
      page: String(page),
      ...(phones ? { https: "true" } : {}),
      ...(filters.order === "random" ? { n: String(surprise) } : {}),
    });
  const stations = useData(path),
    facets = useData<Obj>("/music/radio/facets"),
    favorites = useData("/music/radio/favorites");
  const { run, error } = useAction(favorites.reload);
  const pick = (change: Partial<typeof filters>) => {
    setFilters((current) => ({ ...current, ...change }));
    setPage(0);
  };
  const genres: string[] = facets.data?.genres || [];
  const row = (r: Obj, saved = false) => (
    <ListRow
      key={(saved ? "f" : "s") + r.id}
      leading={<Cover src={r.favicon ? "/api/v1/music/radio/" + r.id + "/art" : null} />}
      title={r.name}
      detail={[
        r.country,
        r.language,
        r.bitrate ? `${r.codec} ${r.bitrate} kbps` : r.codec,
        r.https ? t("plays on phones") : "",
      ]
        .filter(Boolean)
        .join(" · ")}
      actions={
        <>
          <Button
            size="s"
            aria-label={(idle ? t("Play") : t("Add")) + " · " + r.name}
            onClick={() =>
              void run(async () => {
                await api(`/music/radio/${r.id}/queue`, "POST", { idempotency_key: idempotency() });
                toast(
                  idle
                    ? t("Station starting…")
                    : t("Station queued. It plays when its turn comes."),
                );
              })
            }
          >
            {idle ? t("Play") : t("Add")}
          </Button>
          <IconButton
            icon="heart"
            size="s"
            pressed={saved}
            label={(saved ? t("Remove favorite") : t("Favorite")) + " · " + r.name}
            onClick={() =>
              void run(() =>
                api(
                  saved
                    ? `/music/radio/favorites/${r.favorite_id}`
                    : `/music/radio/${r.id}/favorite`,
                  saved ? "DELETE" : "POST",
                ),
              )
            }
          />
        </>
      }
    />
  );
  return (
    <Stack space={5}>
      <form
        className="listen-inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          setSearched(query);
          setPage(0);
        }}
      >
        <Input
          aria-label={t("Radio station name")}
          placeholder={t("Station name…")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" variant="primary" icon="search">
          {t("Find radio")}
        </Button>
      </form>
      <Segmented
        label={t("Order stations")}
        value={filters.order}
        onChange={(order) => {
          if (order === "random") setSurprise((n) => n + 1);
          pick({ order });
        }}
        options={RADIO_ORDERS.map(([value, label]) => ({ value, label: t(label) }))}
      />
      <Toolbar label={t("Radio filters")}>
        <Select
          aria-label={t("Radio genre")}
          value={filters.tag}
          onChange={(e) => pick({ tag: e.target.value })}
        >
          <option value="">{t("All genres")}</option>
          {genres.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("Radio country")}
          value={filters.country}
          onChange={(e) => pick({ country: e.target.value })}
        >
          <option value="">{t("Every country")}</option>
          {(facets.data?.countries || []).map((c: Obj) => (
            <option key={c.code} value={c.code}>
              {c.name} ({c.stations})
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("Radio language")}
          value={filters.language}
          onChange={(e) => pick({ language: e.target.value })}
        >
          <option value="">{t("Every language")}</option>
          {(facets.data?.languages || []).map((l: string) => (
            <option key={l}>{l}</option>
          ))}
        </Select>
        <Checkbox
          label={t("Plays on phones too")}
          checked={phones}
          onChange={(e) => (setPhones(e.target.checked), setPage(0))}
        />
      </Toolbar>
      <ChipGroup label={t("Collections")}>
        {RADIO_COLLECTIONS.map((name) => (
          <Chip
            key={name}
            kind="filter"
            selected={searched === name}
            onToggle={() => {
              setQuery(name);
              setSearched(name);
              pick({ tag: "", country: "", language: "" });
            }}
          >
            {name}
          </Chip>
        ))}
      </ChipGroup>
      <Problem error={error || stations.error || favorites.error} />
      {items(favorites.data).length > 0 && (
        <Section title={t("Your stations")} level={3}>
          <List>{items(favorites.data).map((r) => row(r, true))}</List>
        </Section>
      )}
      <Section title={t("Explore stations")} level={3}>
        {!stations.data ? (
          <State kind="loading" />
        ) : (
          <List>{items(stations.data).map((r) => row(r))}</List>
        )}
        <Cluster>
          <Button
            variant="quiet"
            icon="chevron-left"
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
          >
            {t("Previous stations")}
          </Button>
          <Text style="numeric" tone="muted">
            {t("Page")} {page + 1}
          </Text>
          <Button
            variant="quiet"
            iconEnd="chevron-right"
            disabled={items(stations.data).length === 0 || filters.order === "random"}
            onClick={() => setPage(page + 1)}
          >
            {t("More stations")}
          </Button>
        </Cluster>
      </Section>
      <Text style="caption" tone="muted">
        {t("Live stations from the community directory. Stations may include their own ads.")}
      </Text>
    </Stack>
  );
}

type Rotation = { id: string; name: string; songs: number | null; minutes: number | null };

/** When the queue runs dry, the house keeps playing: kept songs (all, or by genre, by who kept or
 *  played them and when), or a rotation of favourite stations, each for a few songs or minutes.
 *  Requests go first. */
function AutoPlace() {
  const user = useUser();
  // While the house sorts songs into genres, the counts are read again every 20 s.
  const auto = useData<Obj>("/music/auto", { interval: (d) => d?.sorting && 20000 }),
    favorites = useData("/music/radio/favorites");
  const { run, error, busy } = useAction(auto.reload);
  const [source, setSource] = useState(""),
    [genres, setGenres] = useState<string[] | null>(null),
    [people, setPeople] = useState<string[] | null>(null),
    [days, setDays] = useState<string | null>(null),
    [stations, setStations] = useState<Rotation[] | null>(null);
  const saved = auto.data;
  const savedMode: string = saved?.mode || "off";
  // Where it plays from: the one being edited, else the one saved (kept songs by default).
  const current = source || (savedMode === "off" ? "library" : savedMode);
  const dirty =
    genres !== null ||
    people !== null ||
    days !== null ||
    stations !== null ||
    (!!source && source !== savedMode);
  const chosen: string[] = genres ?? saved?.genres ?? [];
  const whose: string[] = people ?? saved?.people ?? [];
  const since: string = days ?? String(saved?.days ?? "");
  const togglePerson = (id: string) =>
    setPeople(whose.includes(id) ? whose.filter((p) => p !== id) : [...whose, id]);
  const rotation: Rotation[] = stations ?? saved?.stations ?? [];
  const toggleGenre = (genre: string) =>
    setGenres(chosen.includes(genre) ? chosen.filter((g) => g !== genre) : [...chosen, genre]);
  const toggleStation = (r: Obj) =>
    setStations(
      rotation.some((s) => s.id === r.id)
        ? rotation.filter((s) => s.id !== r.id)
        : [...rotation, { id: r.id, name: r.name, songs: 3, minutes: null }],
    );
  const [query, setQuery] = useState(""),
    [searched, setSearched] = useState("");
  const found = useData(
    current === "radio" && searched ? "/music/radio?" + new URLSearchParams({ q: searched }) : null,
  );
  // Your favourites first, or what you searched; stations already in the rotation are hidden.
  const offers = items(searched ? found.data : favorites.data)
    .filter((r: Obj) => !rotation.some((s) => s.id === r.id))
    .slice(0, 12);
  const change = (id: string, patch: Partial<Rotation>) =>
    setStations(rotation.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  const apply = (next: string) =>
    run(async () => {
      await api("/music/auto", "PUT", {
        mode: next,
        genres: chosen,
        people: whose,
        days: since ? Number(since) : null,
        stations: next === "radio" ? rotation : [],
      });
      setSource("");
      setGenres(null);
      setPeople(null);
      setDays(null);
      setStations(null);
      toast(next === "off" ? t("Auto play is off.") : t("Auto play saved."));
    });
  const settings = (
    <Stack space={5}>
      <Switch
        checked={savedMode !== "off"}
        disabled={!saved?.can_change || busy || (current === "radio" && !rotation.length)}
        onChange={(on) => void apply(on ? current : "off")}
        label={t("Auto play")}
        hint={
          saved && !saved.can_change
            ? t("Residents choose the auto play.")
            : t("When the queue runs out, the house keeps playing. Requests always go first.")
        }
      />
      <Field label={t("Plays from")}>
        <Segmented
          label={t("Plays from")}
          value={current}
          disabled={!saved?.can_change}
          onChange={setSource}
          options={[
            { value: "library", label: t("Kept songs") },
            { value: "radio", label: t("Radio rotation") },
          ]}
        />
      </Field>
      {current === "library" && (
        <Section
          level={3}
          title={t("Kept songs")}
          lead={
            (saved?.kept ?? 0) +
            " " +
            t("songs kept on this house's disk.") +
            " " +
            t("Narrow them down, or pick nothing for all.")
          }
        >
          {!!saved?.people_kept?.length && (
            <ChipGroup label={t("Kept or played by")}>
              {saved.people_kept.map((p: Obj) => (
                <Chip
                  key={p.id}
                  kind="person"
                  count={p.count}
                  selected={whose.includes(p.id)}
                  onToggle={() => togglePerson(p.id)}
                >
                  {p.id === user?.id ? t("Me") : p.name}
                </Chip>
              ))}
            </ChipGroup>
          )}
          <Field label={t("Kept or played")}>
            <Segmented
              label={t("Kept or played")}
              value={since}
              disabled={!saved?.can_change}
              onChange={setDays}
              options={[
                { value: "", label: t("All time") },
                { value: "7", label: t("This week") },
                { value: "30", label: t("This month") },
                { value: "90", label: t("3 months") },
                { value: "365", label: t("This year") },
              ]}
            />
          </Field>
          <ChipGroup label={t("Genres")}>
            {(saved?.genres_kept || []).map((g: Obj) => (
              <Chip
                key={g.genre}
                kind="filter"
                count={g.count}
                selected={chosen.includes(g.genre)}
                onToggle={() => toggleGenre(g.genre)}
              >
                {t(g.genre)}
              </Chip>
            ))}
          </ChipGroup>
          <SortGenres />
        </Section>
      )}
      {current === "radio" && (
        <Section
          level={3}
          title={t("Radio rotation")}
          lead={
            t("Stations take turns, in this order.") +
            " " +
            t("Stations that don't say what's on change after about 6 minutes a song.")
          }
        >
          {!!rotation.length && (
            <List label={t("Radio rotation")}>
              {rotation.map((on) => (
                <ListRow
                  key={on.id}
                  title={on.name}
                  actions={
                    <span className="listen-rotation__limit">
                      <Input
                        type="number"
                        min={1}
                        max={on.songs ? 50 : 240}
                        aria-label={t("How long") + " · " + on.name}
                        value={on.songs ?? on.minutes ?? 30}
                        onChange={(e) =>
                          change(
                            on.id,
                            on.songs
                              ? { songs: Number(e.target.value) }
                              : { minutes: Number(e.target.value) },
                          )
                        }
                      />
                      <Select
                        aria-label={t("Unit") + " · " + on.name}
                        value={on.songs ? "songs" : "minutes"}
                        onChange={(e) =>
                          change(
                            on.id,
                            e.target.value === "songs"
                              ? { songs: 3, minutes: null }
                              : { songs: null, minutes: 30 },
                          )
                        }
                      >
                        <option value="songs">{t("songs")}</option>
                        <option value="minutes">{t("minutes")}</option>
                      </Select>
                      <IconButton
                        icon="close"
                        size="s"
                        label={t("Remove") + " · " + on.name}
                        onClick={() => toggleStation(on)}
                      />
                    </span>
                  }
                />
              ))}
            </List>
          )}
          <form
            className="listen-inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              setSearched(query.trim());
            }}
          >
            <Input
              type="search"
              aria-label={t("Find a station")}
              placeholder={t("Find a station")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button type="submit" icon="search">
              {t("Search")}
            </Button>
          </form>
          <List>
            {offers.map((r: Obj) => (
              <ListRow
                key={r.id}
                leading={<Icon name="radio" />}
                title={r.name}
                actions={
                  <Button size="s" icon="add" onClick={() => toggleStation(r)}>
                    {t("Add")}
                  </Button>
                }
              />
            ))}
          </List>
          {searched && !items(found.data).length ? (
            <Text style="body-s" tone="muted">
              {t("No station found.")}
            </Text>
          ) : (
            !offers.length && (
              <Text style="body-s" tone="muted">
                {t("Search a station to add it.")}
              </Text>
            )
          )}
        </Section>
      )}
      {saved?.can_change && (dirty || savedMode === "off") && (
        <Button
          variant="primary"
          busy={busy}
          disabled={current === "radio" && !rotation.length}
          onClick={() => void apply(current)}
        >
          {savedMode === current ? t("Save") : t("Start auto play")}
        </Button>
      )}
      <Problem error={error} />
    </Stack>
  );
  return (
    <div className="listen-autoplace">
      {settings}
      {savedMode === "library" && (
        <Section level={3} title={t("Next up")}>
          <AutoNext limit={8} />
        </Section>
      )}
    </div>
  );
}

/** Auto play's next planned songs (kept songs mode), with the way to change the list. */
function AutoNext({ limit }: { limit: number }) {
  const plan = useData("/music/auto/upcoming");
  const [all, setAll] = useState(false);
  const next: Obj[] = (plan.data?.items || []).slice(0, limit);
  if (!next.length) return null;
  return (
    <>
      <List label={t("Auto play: next songs")}>
        {next.map((song) => (
          <ListRow
            key={song.source_url}
            leading={<Cover src={song.art} />}
            title={song.title}
            detail={
              <span className="listen-detail">
                {song.uploader && <span>{song.uploader}</span>}
                <GenreTag genre={song.genre} />
              </span>
            }
          />
        ))}
      </List>
      <Button size="s" variant="quiet" icon="list-music" onClick={() => setAll(true)}>
        {t("See and change the list")}
      </Button>
      {all && <AutoPlaySheet onClose={() => setAll(false)} />}
    </>
  );
}

/** A song's genre as a small tag; nothing when it is unknown. */
function GenreTag({ genre }: { genre?: string }) {
  return genre && genre !== "other" ? <span className="listen-genre">{t(genre)}</span> : null;
}

function HistoryPlace({ idle }: { idle: boolean }) {
  const [by, setBy] = useState(""),
    [adding, setAdding] = useState("");
  const history = usePages("/music/history?limit=30" + (by ? "&by=" + by : ""), (data) =>
    data.next_before ? "before=" + encodeURIComponent(data.next_before) : null,
  );
  const { run, error, busy } = useAction(history.reload);
  return (
    <Stack>
      <Toolbar label={t("Played in this house")}>
        <PeopleFilter value={by} onChange={setBy} />
      </Toolbar>
      <Problem error={error || history.error} onRetry={history.reload} />
      <List label={t("Played in this house")}>
        {history.items.map((row) => {
          const local = row.source_url?.startsWith("houseos-file:");
          return (
            <ListRow
              key={row.id}
              leading={<Cover src={row.art} />}
              title={row.title || t("Untitled song")}
              detail={
                <span className="listen-detail">
                  <Requester person={row.requester} />
                  <GenreTag genre={row.genre} />
                  {row.played_at && <span>{time(row.played_at)}</span>}
                  {row.plays > 1 && <span>{t("{n} plays").replace("{n}", String(row.plays))}</span>}
                </span>
              }
              actions={
                <>
                  <Button
                    size="s"
                    aria-label={(idle ? t("Play") : t("Add to queue")) + " · " + (row.title || "")}
                    title={local ? t("Open local audio from Files") : undefined}
                    disabled={busy || row.replay_supported === false || local}
                    onClick={() => void run(() => queueSong(row.source_url))}
                  >
                    {idle ? t("Play") : t("Add")}
                  </Button>
                  <IconButton
                    icon="heart"
                    size="s"
                    pressed={!!row.favorite}
                    label={
                      (row.favorite ? t("Remove saved track") : t("Save track")) +
                      " · " +
                      (row.title || "")
                    }
                    disabled={busy || row.favorite_supported === false || local}
                    onClick={() =>
                      void run(async () => {
                        if (row.favorite && row.saved_id) {
                          await api("/music/saved/" + row.saved_id, "DELETE");
                          history.patch(row.id, { favorite: false, saved_id: null });
                        } else {
                          const saved = await api<Obj>("/music/saved", "POST", {
                            source_url: row.source_url,
                            idempotency_key: idempotency(),
                          });
                          history.patch(row.id, { favorite: true, saved_id: saved?.id });
                        }
                      })
                    }
                  />
                  {row.source_url?.startsWith("https://") && (
                    <IconButton
                      icon="list-add"
                      size="s"
                      pressed={adding === row.id}
                      label={t("Add to playlist") + " · " + (row.title || "")}
                      onClick={() => setAdding(adding === row.id ? "" : row.id)}
                    />
                  )}
                </>
              }
            >
              {adding === row.id && (
                <AddToPlaylist
                  song={row}
                  onDone={(text) => {
                    setAdding("");
                    toast(text);
                  }}
                />
              )}
            </ListRow>
          );
        })}
      </List>
      {!history.loading && !history.error && !history.items.length && (
        <State kind="empty" title={t("No listening history yet.")} />
      )}
      <MoreBelow pages={history} />
    </Stack>
  );
}

// ---------- My music: saved songs and playlists ----------
const LISTS = "/music/library/playlists";

/** "Add to playlist", under the song: one of your playlists, or a new one named here. */
function AddToPlaylist({ song, onDone }: { song: Obj; onDone: (notice: string) => void }) {
  const lists = useData(LISTS);
  const [name, setName] = useState("");
  const { run, error, busy } = useAction(lists.reload);
  const add = (list: string, fn: () => Promise<Obj>) =>
    void run(async () => {
      const r = await fn();
      onDone(
        (r.added === false ? t("Already in {name}") : t("Added to {name}")).replace("{name}", list),
      );
    });
  return (
    <div className="listen-pick" role="group" aria-label={t("Add to playlist")}>
      <ChipGroup label={t("Your playlists")}>
        {items(lists.data).map((p) => (
          <Chip
            key={p.id}
            kind="filter"
            count={p.items?.length || 0}
            onToggle={
              busy
                ? undefined
                : () =>
                    add(p.name, () =>
                      api(LISTS + "/" + p.id + "/songs", "POST", { source_url: song.source_url }),
                    )
            }
          >
            {p.name}
          </Chip>
        ))}
      </ChipGroup>
      <form
        className="listen-inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          add(name.trim(), () => api(LISTS, "POST", { name, source_urls: [song.source_url] }));
        }}
      >
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={120}
          placeholder={t("New playlist name")}
          aria-label={t("New playlist name")}
        />
        <Button type="submit" icon="add" disabled={busy || !name.trim()}>
          {t("Create")}
        </Button>
      </form>
      <Problem error={error} />
    </div>
  );
}

/** Reviewing songs before they join the shared queue, in place. */
function QueueReview({
  review,
  music,
  onClose,
}: {
  review: Obj;
  music: Playback;
  onClose: (notice?: string) => void;
}) {
  const { run, error, busy } = useAction(music.reload);
  const songs = items(review);
  return (
    <Section
      title={review.names?.join(" + ")}
      lead={
        t("{n} songs").replace("{n}", String(review.total)) +
        (review.total > songs.length
          ? " · " + t("the first {n} are added").replace("{n}", String(songs.length))
          : "")
      }
    >
      <div role="region" aria-label={t("Review before queueing")} className="ds-stack">
        <ol className="listen-preview">
          {songs.slice(0, 50).map((song) => (
            <li key={song.source_url}>{song.title || song.source_url}</li>
          ))}
        </ol>
        {songs.length > 50 && (
          <Text style="body-s" tone="muted">
            {t("…and {n} more").replace("{n}", String(songs.length - 50))}
          </Text>
        )}
        <Text style="body-s" tone="muted">
          {t("Songs already waiting are skipped, and the queue keeps taking turns.")}
        </Text>
        <Problem error={error} />
        <Cluster>
          <Button
            variant="primary"
            busy={busy}
            onClick={() =>
              void run(async () => {
                const r = await api(
                  "/music/playlists/" + review.confirmation_id + "/confirm",
                  "POST",
                );
                onClose(t("{n} songs added to the queue.").replace("{n}", String(r.added)));
              })
            }
          >
            {t("Add {n} songs to the queue").replace("{n}", String(songs.length))}
          </Button>
          <Button variant="quiet" onClick={() => onClose()}>
            {t("Cancel")}
          </Button>
        </Cluster>
      </div>
    </Section>
  );
}

/** One playlist: its songs with art, in order, to move or take out. */
function PlaylistView({
  id,
  version,
  reloadLists,
  onBack,
  onQueue,
  onDelete,
}: {
  id: string;
  version?: number;
  reloadLists: () => Promise<unknown>;
  onBack: () => void;
  onQueue: (ids: string[], shuffle?: boolean) => void;
  onDelete: () => void;
}) {
  const detail = useData(LISTS + "/" + id);
  const { run, error, busy } = useAction(() => Promise.all([detail.reload(), reloadLists()]));
  const [renaming, setRenaming] = useState(false),
    [deleting, setDeleting] = useState(false),
    [adding, setAdding] = useState(false);
  useEffect(() => {
    // Songs added from elsewhere (History, a song's actions) bump the version.
    if (version && detail.data && detail.data.version !== version) void detail.reload();
  }, [version]);
  const p = detail.data,
    songs = items(p),
    urls = songs.map((song) => song.source_url as string);
  const edit = (change: Obj) =>
    void run(() => api(LISTS + "/" + id, "PATCH", { expected_version: p?.version, ...change }));
  const move = (i: number, by: number) => {
    const next = [...urls];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    edit({ source_urls: next });
  };
  const minutes = songs.reduce((sum, song) => sum + (song.duration || 0), 0);
  const home = songs.filter((song) => song.at_home).length;
  // Sorting rewrites the playlist's order once (move songs by hand afterwards).
  const sort = (by: string) => {
    const key = (song: Obj) => String(song[by] || "~").toLocaleLowerCase();
    edit({
      source_urls: [...songs].sort((a, b) => key(a).localeCompare(key(b))).map((s) => s.source_url),
    });
  };
  return (
    <Stack>
      <div>
        <Button variant="quiet" size="s" icon="back" onClick={onBack}>
          {t("All playlists")}
        </Button>
      </div>
      {renaming ? (
        <form
          className="listen-inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            edit({ name: new FormData(e.currentTarget).get("name") });
            setRenaming(false);
          }}
        >
          <Input
            name="name"
            defaultValue={p?.name}
            maxLength={120}
            required
            autoFocus
            aria-label={t("Playlist name")}
          />
          <Button type="submit">{t("Save")}</Button>
          <Button variant="quiet" onClick={() => setRenaming(false)}>
            {t("Cancel")}
          </Button>
        </form>
      ) : (
        <Section
          title={p?.name}
          lead={
            t("{n} songs").replace("{n}", String(songs.length)) +
            (minutes > 0 ? " · " + clock(minutes) : "") +
            (songs.length
              ? " · " +
                t("{n} of {total} at home")
                  .replace("{n}", String(home))
                  .replace("{total}", String(songs.length))
              : "")
          }
          actions={
            <>
              <IconButton
                icon="edit"
                label={t("Rename") + " · " + (p?.name || "")}
                onClick={() => setRenaming(true)}
              />
              <IconButton
                icon="trash"
                label={t("Delete playlist") + " · " + (p?.name || "")}
                aria-expanded={deleting}
                onClick={() => setDeleting(!deleting)}
              />
            </>
          }
        >
          <span />
        </Section>
      )}
      <Cluster>
        <Button
          variant="primary"
          icon="play"
          disabled={busy || !songs.length}
          onClick={() => onQueue([id])}
        >
          {t("Play this playlist")}
        </Button>
        <Button icon="shuffle" disabled={busy || !songs.length} onClick={() => onQueue([id], true)}>
          {t("Shuffle into the queue")}
        </Button>
        <Button icon="add" onClick={() => setAdding(true)}>
          {t("Add songs")}
        </Button>
        {songs.length > 1 && (
          <Select
            aria-label={t("Sort the playlist")}
            value=""
            disabled={busy}
            onChange={(e) => e.target.value && sort(e.target.value)}
          >
            <option value="">{t("Sort by…")}</option>
            <option value="genre">{t("Genre")}</option>
            <option value="uploader">{t("Artist")}</option>
            <option value="title">{t("Title")}</option>
          </Select>
        )}
      </Cluster>
      {adding && (
        <AddSongs
          id={id}
          name={p?.name || ""}
          onClose={() => {
            setAdding(false);
            void detail.reload();
            void reloadLists();
          }}
        />
      )}
      {deleting && (
        <Notice
          tone="danger"
          action={
            <Cluster>
              <Button variant="danger" size="s" onClick={onDelete}>
                {t("Delete")}
              </Button>
              <Button variant="quiet" size="s" onClick={() => setDeleting(false)}>
                {t("Keep")}
              </Button>
            </Cluster>
          }
        >
          <span role="alert">{t("Delete this playlist? Its songs stay in History.")}</span>
        </Notice>
      )}
      <Problem error={error || detail.error} onRetry={detail.reload} />
      <List>
        {songs.map((song, i) => (
          <ListRow
            key={song.source_url}
            leading={<Cover src={song.art} />}
            title={song.title || t("Untitled song")}
            detail={<SongDetail song={song} />}
            actions={
              <>
                <IconButton
                  icon="chevron-up"
                  size="s"
                  label={t("Move up") + " · " + (song.title || "")}
                  disabled={busy || i === 0}
                  onClick={() => move(i, -1)}
                />
                <IconButton
                  icon="chevron-down"
                  size="s"
                  label={t("Move down") + " · " + (song.title || "")}
                  disabled={busy || i === songs.length - 1}
                  onClick={() => move(i, 1)}
                />
                <IconButton
                  icon="close"
                  size="s"
                  label={t("Remove from playlist") + " · " + (song.title || "")}
                  disabled={busy}
                  onClick={() =>
                    edit({ source_urls: urls.filter((url) => url !== song.source_url) })
                  }
                />
              </>
            }
          />
        ))}
      </List>
      {p && !songs.length && (
        <State kind="empty" title={t("No songs yet.")}>
          {t("No songs yet. Use Add to playlist on a saved song, in History or on a queued song.")}
        </State>
      )}
    </Stack>
  );
}

/** Songs the house keeps on its own disk: find them by name, genre or artist, queue them, or
 * `pick` them (a playlist's Add songs). */
function HouseSongs({ music, pick }: { music?: Playback; pick?: (song: Obj) => Promise<unknown> }) {
  const [q, setQ] = useState(""),
    [genre, setGenre] = useState(""),
    [sort, setSort] = useState("recent"),
    [adding, setAdding] = useState(""),
    [done, setDone] = useState<Set<string>>(new Set());
  const query = new URLSearchParams({ kind: "music", q, genre, sort }).toString();
  const pages = usePages("/files/library?" + query, (data) =>
    data.next_offset != null ? "offset=" + data.next_offset : null,
  );
  const first = useData("/files/library?" + query);
  const { run, busy, error } = useAction(async () => {});
  const genres: Obj[] = first.data?.facets?.genres || [];
  const act = (song: Obj, fn: () => Promise<unknown>) =>
    void run(async () => {
      await fn();
      setDone(new Set(done).add(song.source_url));
    });
  return (
    <Stack>
      <Text style="body-s" tone="muted">
        {t("{n} songs on this house's disk: they play without the internet.").replace(
          "{n}",
          String(first.data?.total ?? "…"),
        )}
      </Text>
      <div className="listen-filters">
        <SearchInput
          label={t("Find a song")}
          placeholder={t("Title or artist")}
          value={q}
          onChange={setQ}
        />
        <Select aria-label={t("Genre")} value={genre} onChange={(e) => setGenre(e.target.value)}>
          <option value="">{t("Every genre")}</option>
          {genres.map((g) => (
            <option key={g.genre} value={g.genre}>
              {t(g.genre)} · {g.count}
            </option>
          ))}
        </Select>
        <Select aria-label={t("Order")} value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="recent">{t("Newest first")}</option>
          <option value="plays">{t("Most played")}</option>
          <option value="title">{t("Title")}</option>
          <option value="artist">{t("Artist")}</option>
        </Select>
      </div>
      <Problem error={error || first.error || pages.error} onRetry={first.reload} />
      <List label={t("On this house")}>
        {pages.items.map((song) => (
          <ListRow
            key={song.id}
            leading={<Cover src={song.art} />}
            title={song.title}
            detail={
              <span className="listen-detail">
                {song.artist && <span>{song.artist}</span>}
                <GenreTag genre={song.genre} />
              </span>
            }
            actions={
              pick ? (
                <Button
                  size="s"
                  icon={done.has(song.source_url) ? "check" : "add"}
                  disabled={busy || done.has(song.source_url)}
                  onClick={() => act(song, () => pick(song))}
                >
                  {done.has(song.source_url) ? t("Added") : t("Add")}
                </Button>
              ) : (
                <>
                  <IconButton
                    icon="add"
                    size="s"
                    disabled={busy}
                    label={t("Add to queue") + " · " + song.title}
                    onClick={() =>
                      act(song, async () => {
                        await queueSong(song.source_url);
                        toast(t("Added to the queue."));
                        await music?.reload();
                      })
                    }
                  />
                  <IconButton
                    icon="list-add"
                    size="s"
                    pressed={adding === song.id}
                    label={t("Add to playlist") + " · " + song.title}
                    onClick={() => setAdding(adding === song.id ? "" : song.id)}
                  />
                </>
              )
            }
          >
            {adding === song.id && (
              <AddToPlaylist
                song={song}
                onDone={(text) => {
                  setAdding("");
                  toast(text);
                }}
              />
            )}
          </ListRow>
        ))}
      </List>
      <MoreBelow pages={pages} />
    </Stack>
  );
}

/** A playlist's Add songs: from the house's own songs, a search, or a link. */
function AddSongs({ id, name, onClose }: { id: string; name: string; onClose: () => void }) {
  const [from, setFrom] = useState("home"),
    [text, setText] = useState(""),
    [results, setResults] = useState<Obj[] | null>(null),
    [added, setAdded] = useState<Set<string>>(new Set());
  const { run, error, busy } = useAction(async () => {});
  const add = async (song: Obj) => {
    await api(LISTS + "/" + id + "/songs", "POST", { source_url: song.source_url });
    setAdded((known) => new Set(known).add(song.source_url));
  };
  return (
    <Sheet title={t("Add songs to {name}").replace("{name}", name)} onClose={onClose}>
      <Stack>
        <Segmented
          label={t("From")}
          value={from}
          onChange={setFrom}
          options={[
            { value: "home", label: t("On this house") },
            { value: "search", label: t("Search") },
            { value: "link", label: t("A link") },
          ]}
        />
        {from === "home" && <HouseSongs pick={add} />}
        {from !== "home" && (
          <form
            className="listen-inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                if (from === "link") {
                  await add({ source_url: text.trim() });
                  setText("");
                  toast(t("Added to {name}").replace("{name}", name));
                  return;
                }
                const r = await api(
                  "/music/search?q=" + encodeURIComponent(text) + "&limit=" + SEARCH_PAGE,
                );
                if (r.status !== "completed") throw new Error(pretty(r.code || r.status));
                setResults(items(r));
              });
            }}
          >
            <Input
              value={text}
              required
              type={from === "link" ? "url" : "search"}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                from === "link" ? t("A YouTube or SoundCloud song link") : t("Song or artist")
              }
              aria-label={from === "link" ? t("Song link") : t("Search music")}
            />
            <Button type="submit" busy={busy} icon={from === "link" ? "add" : "search"}>
              {from === "link" ? t("Add") : t("Search")}
            </Button>
          </form>
        )}
        <Problem error={error} />
        {from === "search" && results && (
          <List label={t("Search results")}>
            {results.map((r) => (
              <ListRow
                key={r.id}
                leading={<Cover src={r.thumbnail ? ART + "candidate/" + r.id : null} />}
                title={r.title}
                detail={r.uploader || undefined}
                actions={
                  <Button
                    size="s"
                    icon={added.has(r.source_url) ? "check" : "add"}
                    disabled={busy || added.has(r.source_url)}
                    onClick={() => void run(() => add(r))}
                  >
                    {added.has(r.source_url) ? t("Added") : t("Add")}
                  </Button>
                }
              />
            ))}
          </List>
        )}
      </Stack>
    </Sheet>
  );
}

/** A song's artist, genre and length. */
function SongDetail({ song }: { song: Obj }) {
  return (
    <span className="listen-detail">
      {song.uploader && <span>{song.uploader}</span>}
      <GenreTag genre={song.genre} />
      {song.duration > 0 && <span className="tabular">{clock(song.duration)}</span>}
    </span>
  );
}

/** Songs still in "other": look up their genres again (Auto play, My music, Files → Music).
 * Shows only when there are some and this person may; says so while it runs. */
export function SortGenres() {
  const auto = useData<Obj>("/music/auto", { interval: (d) => d?.sorting && 20000 });
  const { run, error, busy } = useAction(auto.reload);
  const state = auto.data;
  const other = state?.genres_kept?.find((g: Obj) => g.genre === "other")?.count || 0;
  if (state?.sorting)
    return (
      <Status tone="info" busy>
        {t("Sorting songs into genres, a few a minute…")}
      </Status>
    );
  if (!state?.can_change || !other) return null;
  return (
    <div>
      {/* its own block: the button keeps its size in a stretching stack */}
      <Button
        size="s"
        icon="sparkles"
        disabled={busy}
        onClick={() =>
          void run(async () => {
            const r = await api("/music/auto/sort-genres", "POST");
            toast(
              t("Looking up {n} songs: about {m} min.")
                .replace("{n}", r.songs)
                .replace("{m}", r.minutes),
            );
          })
        }
      >
        {t("Sort the “other” songs") + " · " + other}
      </Button>
      <Problem error={error} />
    </div>
  );
}

function Library({ music, initial }: { music: Playback; initial: "playlists" | "saved" | "home" }) {
  const saved = useData("/music/saved"),
    lists = useData(LISTS);
  const user = useUser();
  const canFiles = user?.role === "admin" || user?.permissions?.includes("files.read");
  const files = useData(canFiles ? "/files?scope=personal&limit=200" : null);
  const [tab, setTab] = useState<"playlists" | "saved" | "home">(initial),
    [open, setOpen] = useState(""),
    [picked, setPicked] = useState<string[]>([]),
    [review, setReview] = useState<Obj | null>(null),
    [preview, setPreview] = useState<Obj | null>(null),
    [adding, setAdding] = useState(""),
    [fromQueue, setFromQueue] = useState(false),
    [localFile, setLocalFile] = useState("");
  const { run, error, busy } = useAction(() => Promise.all([saved.reload(), lists.reload()]));
  const idle = !!music.data?.autoplay_on_add;
  const playlists = items(lists.data),
    tracks = items(saved.data);
  const queueable = items(music.data).filter(
    (i) =>
      i.source_url?.startsWith("https://") &&
      ["ready", "playing", "paused", "buffering"].includes(i.status),
  );
  const prepare = (ids: string[], shuffle = false) =>
    void run(async () => setReview(await api(LISTS + "/queue", "POST", { ids, shuffle })));
  const done = (text?: string) => {
    setReview(null);
    setPicked([]);
    if (text) toast(text);
  };
  return (
    <Stack space={5}>
      <Segmented
        label={t("Show")}
        value={tab}
        onChange={setTab}
        options={[
          { value: "playlists", label: t("Playlists") + " · " + playlists.length },
          { value: "saved", label: t("Saved songs") + " · " + tracks.length },
          ...(canFiles && user?.role !== "guest"
            ? [{ value: "home" as const, label: t("On this house") }]
            : []),
        ]}
      />
      <SortGenres />
      <Problem error={error || saved.error || lists.error} />
      {review ? (
        <QueueReview review={review} music={music} onClose={done} />
      ) : tab === "home" ? (
        <HouseSongs music={music} />
      ) : tab === "playlists" && open ? (
        <PlaylistView
          id={open}
          version={playlists.find((p) => p.id === open)?.version}
          reloadLists={lists.reload}
          onBack={() => setOpen("")}
          onQueue={prepare}
          onDelete={() =>
            void run(async () => {
              await api(LISTS + "/" + open, "DELETE");
              setPicked(picked.filter((x) => x !== open));
              setOpen("");
              toast(t("Playlist deleted."));
            })
          }
        />
      ) : tab === "playlists" ? (
        <>
          {lists.data && !playlists.length && (
            <State
              kind="empty"
              title={t("Playlists keep songs together")}
              art={<Icon name="list-music" size="l" />}
            >
              <p>
                {t(
                  "Name one below, fill it when you like, then play it, shuffle it or queue several at once.",
                )}
              </p>
              <ul className="listen-tips">
                <li>
                  <Icon name="heart" size="s" /> {t("Heart a song, then add it from Saved songs.")}
                </li>
                <li>
                  <Icon name="list-add" size="s" />{" "}
                  {t("Tap Add to playlist on a song in History or in the queue.")}
                </li>
                <li>
                  <Icon name="list-music" size="s" />{" "}
                  {t("Or start one with the songs in the queue right now.")}
                </li>
              </ul>
            </State>
          )}
          <form
            className="listen-inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              void run(async () => {
                const made = await api(LISTS, "POST", {
                  name: new FormData(form).get("name"),
                  item_ids: fromQueue ? queueable.map((i) => i.id) : [],
                });
                form.reset();
                setFromQueue(false);
                toast(t("Playlist saved."));
                setOpen(made.id);
              });
            }}
          >
            <Input
              name="name"
              maxLength={120}
              required
              placeholder={t("Name a new playlist")}
              aria-label={t("Playlist name")}
            />
            <Button type="submit" icon="add" disabled={busy}>
              {t("Create")}
            </Button>
          </form>
          {queueable.length > 0 && (
            <Checkbox
              label={t("Start it with the {n} songs in the queue").replace(
                "{n}",
                String(queueable.length),
              )}
              checked={fromQueue}
              onChange={(e) => setFromQueue(e.target.checked)}
            />
          )}
          <form
            className="listen-inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              void run(async () => {
                const kept = await api(LISTS + "/import", "POST", {
                  url: String(new FormData(form).get("url")).trim(),
                });
                form.reset();
                toast(
                  (kept.total > kept.items.length
                    ? t("“{name}” imported: the rest of its songs keep coming in.")
                    : t("“{name}” imported.")
                  ).replace("{name}", kept.name),
                );
                setOpen(kept.id);
              });
            }}
          >
            <Input
              name="url"
              type="url"
              required
              placeholder={t("Or paste a YouTube or SoundCloud playlist link")}
              aria-label={t("Playlist link to import")}
            />
            <Button type="submit" icon="download" disabled={busy}>
              {t("Import")}
            </Button>
          </form>
          <List label={t("Playlists")}>
            {playlists.map((p) => (
              <ListRow
                key={p.id}
                leading={
                  <Checkbox
                    hideLabel
                    label={t("Select") + " · " + p.name}
                    checked={picked.includes(p.id)}
                    onChange={(e) =>
                      setPicked(
                        e.target.checked ? [...picked, p.id] : picked.filter((x) => x !== p.id),
                      )
                    }
                  />
                }
                title={p.name}
                detail={t("{n} songs").replace("{n}", String(p.items?.length || 0))}
                actions={
                  <>
                    <IconButton
                      icon="play"
                      size="s"
                      label={t("Play this playlist") + " · " + p.name}
                      disabled={busy || !p.items?.length}
                      onClick={() => prepare([p.id])}
                    />
                    <IconButton
                      icon="chevron-right"
                      size="s"
                      label={t("Open") + " · " + p.name}
                      onClick={() => setOpen(p.id)}
                    />
                  </>
                }
              />
            ))}
          </List>
          {picked.length > 0 && (
            <div className="listen-selbar" role="region" aria-label={t("Selected playlists")}>
              <Text style="label">{t("{n} selected").replace("{n}", String(picked.length))}</Text>
              <Button variant="primary" size="s" busy={busy} onClick={() => prepare(picked)}>
                {t("Queue them")}
              </Button>
              <Button size="s" icon="shuffle" disabled={busy} onClick={() => prepare(picked, true)}>
                {t("Shuffled")}
              </Button>
              <IconButton icon="close" size="s" label={t("Clear")} onClick={() => setPicked([])} />
            </div>
          )}
        </>
      ) : (
        <>
          <List label={t("Saved songs")}>
            {tracks.map((track) => (
              <ListRow
                key={track.id}
                leading={<Cover src={track.art} />}
                title={track.title || t("Untitled song")}
                detail={<SongDetail song={track} />}
                actions={
                  <>
                    <IconButton
                      icon={idle ? "play" : "add"}
                      size="s"
                      disabled={busy}
                      label={(idle ? t("Play") : t("Add to queue")) + " · " + (track.title || "")}
                      onClick={() =>
                        void run(async () => {
                          await queueSong(track.source_url);
                          await music.reload();
                        })
                      }
                    />
                    <IconButton
                      icon="list-add"
                      size="s"
                      pressed={adding === track.id}
                      label={t("Add to playlist") + " · " + (track.title || "")}
                      onClick={() => setAdding(adding === track.id ? "" : track.id)}
                    />
                    <IconButton
                      icon="heart"
                      size="s"
                      pressed
                      disabled={busy}
                      label={t("Remove saved track") + " · " + (track.title || "")}
                      onClick={() => void run(() => api("/music/saved/" + track.id, "DELETE"))}
                    />
                  </>
                }
              >
                {adding === track.id && (
                  <AddToPlaylist
                    song={track}
                    onDone={(text) => {
                      setAdding("");
                      toast(text);
                    }}
                  />
                )}
              </ListRow>
            ))}
          </List>
          {saved.data && !tracks.length && (
            <State
              kind="empty"
              title={t("Tap the heart on a song to keep it here.")}
              art={<Icon name="heart" size="l" />}
            />
          )}
          {canFiles && (
            <Section level={3} title={t("Play a local audio file")}>
              <form
                className="listen-inline-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(async () =>
                    setPreview(
                      await api("/music/local/preview", "POST", {
                        file_id: localFile,
                        idempotency_key: idempotency(),
                      }),
                    ),
                  );
                }}
              >
                <Select
                  aria-label={t("Your stored audio")}
                  value={localFile}
                  onChange={(e) => setLocalFile(e.target.value)}
                  required
                >
                  <option value="">{t("Choose a finalized audio file")}</option>
                  {items(files.data)
                    .filter((f) => f.mime?.startsWith("audio/"))
                    .map((f) => (
                      <option value={f.id} key={f.id}>
                        {f.name}
                      </option>
                    ))}
                </Select>
                <Button type="submit" disabled={!localFile || busy}>
                  {t("Review sharing this audio")}
                </Button>
              </form>
              <Text style="caption" tone="muted">
                {t(
                  "Its title and sound become shared with the house. Your original file stays private.",
                )}
              </Text>
              <Problem error={files.error} />
            </Section>
          )}
        </>
      )}
      {preview && (
        <Sheet
          title={t("Review local audio")}
          onClose={() => setPreview(null)}
          footer={
            <Button
              variant="primary"
              busy={busy}
              onClick={() =>
                void run(async () => {
                  await api("/music/local/" + preview.confirmation_id + "/confirm", "POST");
                  toast(t("Added to the queue."));
                  setPreview(null);
                  await music.reload();
                })
              }
            >
              {t("Confirm adding to shared queue")}
            </Button>
          }
        >
          <Stack>
            <ReviewDetails value={preview.preview} />
            <Text style="body-s" tone="muted">
              {t("This adds only the reviewed selection.")}
            </Text>
          </Stack>
        </Sheet>
      )}
    </Stack>
  );
}

// ---------- the room ----------
const TABS = ["queue", "library", "radio", "history", "auto"] as const;
type Tab = (typeof TABS)[number];
/** The place in the room: ?tab=… (and the old #saved link opens My music's saved songs). */
function readTab(): Tab {
  if (location.hash === "#saved") return "library";
  const tab = new URLSearchParams(location.search).get("tab") as Tab;
  return TABS.includes(tab) ? tab : "queue";
}

/** Listen: the add field, the room's places, and at its heart the house's fair queue. */
export function Music() {
  const music = useMusicPlayback();
  const canControl = useCanControl();
  const [tab, setTab] = useState<Tab>(readTab);
  const [settings, setSettings] = useState(false);
  const [forgetting, setForgetting] = useState(false);
  const user = useUser();
  // Search results take the ideas' place beside the queue, so nothing below them moves.
  const [found, setFound] = useState(false);
  const idle = !!music.data?.autoplay_on_add;
  // "Find this song" (from the Now sheet, anywhere in the room) opens the queue with the search.
  useEffect(() => {
    const follow = () => setTab(readTab());
    window.addEventListener("popstate", follow);
    return () => window.removeEventListener("popstate", follow);
  }, []);
  const waiting = items(music.data).filter((row) => row.id !== music.data?.current_id).length;
  const open = (next: string) => {
    const url = new URL(location.href);
    if (next === "queue") url.searchParams.delete("tab");
    else url.searchParams.set("tab", next);
    url.hash = "";
    history.replaceState({}, "", url.pathname + url.search);
    setTab(next as Tab);
  };
  const places: NavItem[] = [
    { id: "queue", label: t("The queue"), icon: "list-music", count: waiting },
    { id: "library", label: t("My music"), icon: "archive" },
    { id: "radio", label: t("Radio"), icon: "radio" },
    { id: "history", label: t("History"), icon: "history" },
    { id: "auto", label: t("Auto play"), icon: "shuffle" },
  ];
  const control = (action: string, value?: number | string) =>
    music.control(action, value).then(
      () => true,
      () => false,
    );
  return (
    <Page>
      <PageHeader
        room="listen"
        title={t("Listen")}
        hint={
          <Hint id="listen">
            {t(
              "Paste a YouTube or SoundCloud link, search a song or pick a radio. The queue takes turns: everyone gets a song in.",
            )}
          </Hint>
        }
      />
      <SubNav label={t("Listen")} value={tab} onChange={open} items={places} />
      <section className="listen-place" aria-label={places.find((p) => p.id === tab)?.label}>
        {tab === "queue" && (
          <div className="listen-console">
            <AddBar music={music} onResults={setFound} />
            <div className="listen-deckcol">
              <Deck
                music={music}
                menu={
                  <Menu
                    label={t("More music")}
                    items={[
                      { label: t("Party mode"), icon: "party", onSelect: () => go("/party") },
                      {
                        label: t("Play on this device"),
                        icon: "speaker",
                        onSelect: () => go("/speaker"),
                      },
                      ...(canControl
                        ? [
                            {
                              label: t("Jukebox settings"),
                              icon: "settings" as const,
                              onSelect: () => setSettings(true),
                            },
                          ]
                        : []),
                      ...(music.current && mayForget(music.current, user)
                        ? [
                            {
                              label: t("Delete from the house after this song"),
                              icon: "trash" as const,
                              danger: true,
                              onSelect: () => setForgetting(true),
                            },
                          ]
                        : []),
                    ]}
                  />
                }
              />
              <DeckSide onAuto={() => open("auto")} />
            </div>
            <AutoAhead />
            <Queue music={music} />
            {!found && <QuickStarts music={music} />}
          </div>
        )}
        {tab === "library" && (
          <Library music={music} initial={location.hash === "#saved" ? "saved" : "playlists"} />
        )}
        {tab === "radio" && <RadioPlace idle={idle} />}
        {tab === "history" && <HistoryPlace idle={idle} />}
        {tab === "auto" && <AutoPlace />}
      </section>
      {settings && (
        <JukeboxSettings music={music} control={control} onClose={() => setSettings(false)} />
      )}
      {forgetting && music.current && (
        <ForgetSong row={music.current} music={music} onClose={() => setForgetting(false)} />
      )}
    </Page>
  );
}

/** Songs of yours that turned out removed or private: they left the queue; one quiet notice
 * offers other versions (found by their title), which take their place in their playlist too. */
function Unavailable({ music }: { music: Playback }) {
  const gone = useData("/music/unavailable", { interval: 30000 });
  const [open, setOpen] = useState(false);
  const list = items(gone.data);
  if (!list.length) return null;
  return (
    <>
      <Notice
        tone="info"
        action={
          <Button size="s" onClick={() => setOpen(true)}>
            {t("Pick other versions")}
          </Button>
        }
      >
        {(list.length === 1
          ? t("“{title}” was removed or made private.")
          : t("{n} songs were removed or made private.")
        )
          .replace("{title}", list[0].title)
          .replace("{n}", String(list.length))}
      </Notice>
      {open && (
        <Sheet title={t("Other versions")} onClose={() => setOpen(false)}>
          <Stack>
            {list.map((song) => (
              <Alternatives
                key={song.id}
                song={song}
                onDone={() => {
                  void gone.reload();
                  void music.reload();
                }}
              />
            ))}
          </Stack>
        </Sheet>
      )}
    </>
  );
}

function Alternatives({ song, onDone }: { song: Obj; onDone: () => void }) {
  const found = useData("/music/search?limit=3&q=" + encodeURIComponent(song.title));
  const { run, busy, error } = useAction(async () => onDone());
  return (
    <Section
      level={3}
      title={song.title}
      actions={
        <Button
          size="s"
          variant="quiet"
          disabled={busy}
          onClick={() => void run(() => api("/music/unavailable/" + song.id, "DELETE"))}
        >
          {t("Dismiss")}
        </Button>
      }
    >
      <Problem error={error || found.error} />
      {!found.data && <State kind="loading" />}
      <List label={t("Other versions")}>
        {items(found.data).map((r) => (
          <ListRow
            key={r.id}
            leading={<Cover src={r.thumbnail ? ART + "candidate/" + r.id : null} />}
            title={r.title}
            detail={r.uploader || undefined}
            actions={
              <Button
                size="s"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    api("/music/unavailable/" + song.id + "/replace", "POST", {
                      source_url: r.source_url,
                      idempotency_key: idempotency(),
                    }),
                  )
                }
              >
                {t("Use this one")}
              </Button>
            }
          />
        ))}
      </List>
    </Section>
  );
}

/** Under the deck: the ways to play (auto play, party, this device) in sight. */
function DeckSide({ onAuto }: { onAuto: () => void }) {
  const auto = useData("/music/auto");
  return (
    <div className="listen-side">
      <div className="listen-side__ways">
        <Button
          size="s"
          icon="shuffle"
          pressed={!!auto.data?.mode && auto.data.mode !== "off"}
          onClick={onAuto}
        >
          {t("Auto play")}
        </Button>
        <Button size="s" icon="party" onClick={() => go("/party")}>
          {t("Party")}
        </Button>
        <Button size="s" icon="speaker" onClick={() => go("/speaker")}>
          {t("Play here")}
        </Button>
      </div>
    </div>
  );
}

/** What auto play has planned after the queue, and the way to change it: a block of its own, so
 *  a long queue or a tall player never pushes it out of reach (listen.css places it). */
function AutoAhead() {
  const auto = useData("/music/auto");
  if (auto.data?.mode !== "library") return null;
  return (
    <section className="listen-auto" aria-label={t("After the queue, auto play plays")}>
      <Text style="label" tone="muted">
        {t("After the queue, auto play plays")}
      </Text>
      <AutoNext limit={4} />
    </section>
  );
}

/** Home's window onto the jukebox: what plays and the next three. */
export function MusicPanel() {
  const music = useMusicPlayback();
  // Nothing at all to play: one line and the way to Listen, not an empty deck.
  if (music.data && !music.current && !items(music.data).length)
    return (
      <div className="listen-panel">
        <Text tone="muted">{t("Nothing is playing.")}</Text>
        <Button variant="primary" onClick={() => go("/listen")}>
          {t("Choose some music")}
        </Button>
      </div>
    );
  return (
    <div className="listen-panel">
      <Deck music={music} compact />
      {music.data && !items(music.data).length ? (
        <Button variant="primary" onClick={() => go("/listen")}>
          {t("Choose some music")}
        </Button>
      ) : (
        <Queue music={music} limit={3} />
      )}
    </div>
  );
}

// ---------- Speaker mode: this phone or computer plays along with the house ----------
const SPEAKER_VOLUME = "houseos.speaker.volume";
const DRIFT = 1.5;

/** Keeps the screen awake while `active`: a phone that locks stops following the house and the
 *  next song never loads. The lock drops whenever the page is hidden, so it is taken again. */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | undefined,
      left = false;
    const take = () => {
      if (document.visibilityState !== "visible") return;
      navigator.wakeLock
        .request("screen")
        .then((sentinel) => (left ? void sentinel.release() : (lock = sentinel)))
        .catch(() => {});
    };
    take();
    document.addEventListener("visibilitychange", take);
    return () => {
      left = true;
      document.removeEventListener("visibilitychange", take);
      void lock?.release().catch(() => {});
    };
  }, [active]);
}

/** One tap to start (browsers only play sound after a tap), then an <audio> element follows
 *  the house clock: the same song, position and pause as the house, with its own volume. */
export function Speaker() {
  const music = useMusicPlayback();
  const { current, data, playing } = music;
  const { position, now } = usePosition(music);
  const player = useRef<HTMLAudioElement>(null);
  const [on, setOn] = useState(false),
    [problem, setProblem] = useState(""),
    // The browser or phone stopped the sound (the page was left, another app took the audio):
    // it plays again, in step, as soon as the page is back (or with one tap).
    [held, setHeld] = useState(false),
    [volume, setVolume] = useState(() => {
      try {
        return Number(localStorage.getItem(SPEAKER_VOLUME) ?? 1);
      } catch {
        return 1;
      }
    });
  // iPhone and iPad ignore a page's audio volume: only the phone's own buttons change it.
  const [fixedVolume] = useState(() => {
    const probe = new Audio();
    probe.volume = 0.5;
    return probe.volume !== 0.5;
  });
  useWakeLock(on);
  const loaded = !!current && data?.observation?.item_id === current.id;
  const source = current ? "/api/v1/music/audio/" + current.id : "";
  const ours = useRef(false); // the next "pause" is ours (a stop, a new song), not the browser's
  const quiet = (audio: HTMLAudioElement) => {
    if (!audio.paused) ours.current = true;
    audio.pause();
  };
  const play = (audio: HTMLAudioElement) =>
    audio
      .play()
      .then(() => setHeld(false))
      .catch((e) => e.name !== "AbortError" && setHeld(true));
  // A hidden page stops polling (api.ts); while playing here it keeps following the house, so the
  // next song still starts with the screen off or another app in front.
  useEffect(() => {
    if (!on) return;
    const follow = setInterval(() => void (document.hidden && music.reload()), 3000);
    const back = () => !document.hidden && setHeld(false);
    document.addEventListener("visibilitychange", back);
    return () => {
      clearInterval(follow);
      document.removeEventListener("visibilitychange", back);
    };
  }, [on]);
  // Follow the house every second: same song, same place, same pause.
  useEffect(() => {
    const audio = player.current;
    if (!on || !audio) return;
    if (!current || !loaded || !playing) {
      quiet(audio);
      return;
    }
    if (audio.dataset.item !== current.id) {
      quiet(audio);
      audio.dataset.item = current.id;
      audio.src = source;
      setProblem("");
    }
    if (!current.is_live && audio.readyState >= 1 && Math.abs(audio.currentTime - position) > DRIFT)
      audio.currentTime = position;
    if (audio.paused && !problem && !(held && document.hidden)) void play(audio);
  }, [on, current?.id, loaded, playing, now, held]);
  useEffect(() => {
    if (player.current) player.current.volume = volume;
    try {
      localStorage.setItem(SPEAKER_VOLUME, String(volume));
    } catch {
      /* private mode: this visit only */
    }
  }, [volume]);
  // The lock screen and headphone buttons show the song; pausing there stops playing here.
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = current
      ? new MediaMetadata({
          title: current.now_title || current.title,
          artist: current.uploader || current.requester?.name || "",
          artwork: current.art ? [{ src: current.art }] : [],
        })
      : null;
    navigator.mediaSession.setActionHandler("pause", () => setOn(false));
    navigator.mediaSession.setActionHandler("play", () => setOn(true));
    // Leaving the page hands the lock screen's buttons back.
    return () => {
      navigator.mediaSession.setActionHandler("pause", null);
      navigator.mediaSession.setActionHandler("play", null);
      navigator.mediaSession.metadata = null;
    };
  }, [current?.id, current?.now_title]);
  useEffect(() => {
    if (!on && player.current) quiet(player.current);
    if (!on) setHeld(false);
  }, [on]);
  const start = () => {
    const audio = player.current;
    setOn(true);
    setProblem("");
    // Start inside the tap, where every browser allows sound.
    if (audio && current && loaded && playing) {
      if (audio.dataset.item !== current.id) {
        quiet(audio);
        audio.dataset.item = current.id;
        audio.src = source;
      }
      void play(audio);
    }
  };
  // Why a song cannot play here, in the server's own words.
  const explain = async () => {
    const response = await fetch(source, {
      credentials: "same-origin",
      redirect: "manual",
      headers: { Range: "bytes=0-0" },
    }).catch(() => null);
    const detail = response && response.status >= 400 && (await response.json().catch(() => null));
    setProblem(detail?.detail || "This song cannot play on this device.");
  };
  return (
    <Page width="narrow">
      <PageHeader kicker={t("Speaker mode")} title={t("Play the house music here")} />
      <section className="listen-speaker" aria-label={t("Now playing")}>
        <Media src={current?.art} alt="" ratio="1 / 1" />
        <div>
          <Text as="h2" style="title-l">
            {current?.title || t("Nothing is playing in the house.")}
          </Text>
          <p role="status">
            {!current
              ? t("Start a song in Listen; it plays here too.")
              : !playing
                ? t("The house is paused.")
                : on
                  ? t("Playing here, in step with the house.")
                  : t("Playing in the house.")}
          </p>
          <OnAir track={current} keepPage />
        </div>
      </section>
      {on && held && (
        <Notice tone="info">
          <Stack space={2}>
            <Text>{t("Your browser paused the music when you left this page.")}</Text>
            <Button variant="primary" icon="play" onClick={start}>
              {t("Play here again")}
            </Button>
          </Stack>
        </Notice>
      )}
      {on ? (
        <Button icon="stop" onClick={() => setOn(false)}>
          {t("Stop playing here")}
        </Button>
      ) : (
        <Button variant="primary" size="l" icon="speaker" onClick={start}>
          {t("Play here")}
        </Button>
      )}
      {fixedVolume ? (
        <Text style="body-s" tone="muted">
          {t("Use the phone's volume buttons.")}
        </Text>
      ) : (
        <Slider
          label={t("Volume on this device")}
          showLabel
          value={Math.round(volume * 100)}
          onChange={(value) => setVolume(value / 100)}
          format={percent}
        />
      )}
      {problem && <Notice tone="warning">{t(problem)}</Notice>}
      <Problem error={music.error} onRetry={music.reload} />
      <Text style="caption" tone="muted">
        {t(
          "Keep this page open; it keeps playing behind other apps where the browser allows it, and picks up in step when you come back. Pause, the next song and seeking follow the house; the volume here is yours.",
        )}
      </Text>
      <audio
        ref={player}
        preload="auto"
        onLoadedMetadata={(e) => {
          if (!current?.is_live) e.currentTarget.currentTime = position;
        }}
        onError={() => void explain()}
        // The browser paused it (not the house, not us): say so, and play again when it can.
        onPause={(e) => {
          if (!ours.current && on && !e.currentTarget.ended) setHeld(true);
          ours.current = false;
        }}
        // Ask for the next song at once, even while the page is hidden.
        onEnded={() => void music.reload()}
      />
    </Page>
  );
}

import { useState, type CSSProperties, type ReactNode } from "react";
import { bytes, number, useData, type Obj } from "./api";
import { t, useI18n } from "./i18n";
import { themeGrid } from "./sprites";
import { useThemeInfo } from "./design/theme";
import { PieceFill } from "./design/icons";
import {
  Avatar as Face,
  Icon,
  type IconName,
  List,
  ListRow,
  Mascot,
  Media,
  Problem,
  Progress,
  Section,
  Segmented,
  State,
  Surface,
  Text,
  tone,
} from "./design";

/** House titles: whoever leads holds it; stars (up to 3) say how far they have gone. */
const TITLES: Record<string, [IconName, string, string]> = {
  dj: ["headphones", "Head DJ", "{n} songs played"],
  explorer: ["compass", "Explorer", "{n} different songs"],
  night_owl: ["moon", "Night owl", "{n} songs between midnight and 5"],
  early_bird: ["bird", "Early bird", "{n} songs before 9 am"],
  weekend: ["party", "Weekend DJ", "{n} songs on weekends"],
  genre_guardian: ["music-alt", "Keeper of {genre}", "{n} {genre} songs"],
  broken_record: ["disc", "Broken record", "{n} plays of {song}"],
  marathon: ["footprints", "Marathoner", "{n} min in one go: {song}"],
  radio_host: ["radio", "Radio host", "{n} radio stations tuned in"],
  task_hero: ["brush", "Task hero", "{n} tasks done"],
  grocery_runner: ["basket", "Grocery runner", "{n} groceries bought"],
  planner: ["calendar", "Planner", "{n} events planned"],
  wall_poet: ["pin", "Wall poet", "{n} notes on the wall"],
  courier: ["feather", "Courier", "{n} messages sent"],
  curator: ["key", "Curator", "{n} songs kept as favourites"],
  high_scorer: ["gamepad", "Die-hard", "{n} hours played"],
  collector: ["archive", "Collector", "{n} games brought"],
  game_hopper: ["sparkles", "Game hopper", "{n} different games played"],
  console_hopper: ["tv", "Console hopper", "{n} consoles played"],
  romhacker: ["wand", "Romhacker", "{n} romhacks added"],
};
/** The same lines for exactly one ("1 note on the wall", not "1 notes"). */
const ONE: Record<string, string> = {
  "{n} songs played": "{n} song played",
  "{n} different songs": "{n} different song",
  "{n} songs between midnight and 5": "{n} song between midnight and 5",
  "{n} songs before 9 am": "{n} song before 9 am",
  "{n} songs on weekends": "{n} song on weekends",
  "{n} {genre} songs": "{n} {genre} song",
  "{n} plays of {song}": "{n} play of {song}",
  "{n} radio stations tuned in": "{n} radio station tuned in",
  "{n} tasks done": "{n} task done",
  "{n} groceries bought": "{n} grocery bought",
  "{n} events planned": "{n} event planned",
  "{n} notes on the wall": "{n} note on the wall",
  "{n} messages sent": "{n} message sent",
  "{n} songs kept as favourites": "{n} song kept as a favourite",
  "{n} hours played": "{n} hour played",
  "{n} games brought": "{n} game brought",
  "{n} different games played": "{n} different game played",
  "{n} romhacks added": "{n} romhack added",
};
const TOTAL = Object.keys(TITLES).length; // 20: the backend's list, kept a multiple of five
const NUDGES: Record<string, string> = {
  dj: "{n} more songs and you're Head DJ",
  explorer: "{n} new songs and you're the Explorer",
  night_owl: "{n} more late-night songs and you're the Night owl",
  early_bird: "{n} more morning songs and you're the Early bird",
  weekend: "{n} more weekend songs and you're the Weekend DJ",
  radio_host: "{n} more stations and you're the Radio host",
  task_hero: "{n} more tasks and you're the Task hero",
  grocery_runner: "{n} more groceries and you're the Grocery runner",
  planner: "{n} more events and you're the Planner",
};
// The theme's chart colours (color.data.1–8).
const GENRE_TONES = Array.from({ length: 8 }, (_, i) => `var(--c-data-${i + 1})`);

const fill = (text: string, values: Obj) => fillTheme(t(text), values);
/** Fills {n}, {song}… in words already in the person's language (a theme's own, or translated). */
const fillTheme = (text: string, values: Obj) =>
  text.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));

const Avatar = ({ person }: { person: Obj }) => (
  <Face name="" picture={person.avatar} tone={tone(person.id)} size="s" />
);

/** What Nox says about the numbers: picked by code, a different line each day. */
function quip(data: Obj) {
  const music = data.music,
    by = (key: string) => data.titles.find((title: Obj) => title.key === key);
  const lines: string[] = [];
  if (music.week > music.last_week && music.week > 0)
    lines.push(fill("The house is on fire this week: {n} songs already", { n: music.week }));
  if (by("dj")) lines.push(fill("{name} is holding the aux cable hostage", by("dj").person));
  if (by("night_owl"))
    lines.push(fill("Someone plays music at 3 am… {name}, I see you", by("night_owl").person));
  if (by("broken_record"))
    lines.push(
      fill("{name} really, really likes “{song}”", {
        ...by("broken_record").person,
        ...by("broken_record"),
      }),
    );
  if (music.genres[0])
    lines.push(fill("This house runs on {genre}", { genre: t(music.genres[0].name) }));
  if (!lines.length) return t("Play a few songs and I'll start keeping score.");
  return lines[Math.floor(Date.now() / 86400000) % lines.length];
}

const hoursOf = (seconds: number) =>
  seconds >= 3600
    ? Math.round(seconds / 360) / 10 + " h"
    : Math.max(1, Math.round(seconds / 60)) + " min";

/** A ring and its legend: each genre's share of the time listened or watched. */
export function GenreRing({ genres, label }: { genres: Obj[]; label: string }) {
  const total = genres.reduce((sum, g) => sum + (g.seconds || 0), 0) || 1;
  let angle = 0;
  const ring = genres
    .map((genre, i) => {
      const from = angle;
      angle += (360 * genre.seconds) / total;
      return `${GENRE_TONES[i % GENRE_TONES.length]} ${from}deg ${angle}deg`;
    })
    .join(", ");
  return (
    <div className="stats__genres">
      <span
        className="stats__donut"
        style={{ "--ring": ring } as CSSProperties}
        role="img"
        aria-label={
          label + ": " + genres.map((g) => t(g.name) + " " + hoursOf(g.seconds)).join(", ")
        }
      />
      <ul>
        {genres.map((genre, i) => (
          <li
            key={genre.name}
            style={{ "--tone": GENRE_TONES[i % GENRE_TONES.length] } as CSSProperties}
          >
            <i aria-hidden="true" />
            {t(genre.name)} <small>{Math.round((100 * genre.seconds) / total)}%</small>{" "}
            <small className="tabular">{hoursOf(genre.seconds)}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

const TABS = [
  ["music", "Music"],
  ["titles", "House titles"],
  ["films", "Films & series"],
  ["games", "Games"],
] as const;
type Tab = (typeof TABS)[number][0];
const TAB_KEY = "houseos.stats.tab";
function rememberedTab(): Tab {
  try {
    const saved = localStorage.getItem(TAB_KEY);
    return TABS.some(([key]) => key === saved) ? (saved as Tab) : "music";
  } catch {
    return "music";
  }
}

/** A number worth knowing, with its word. */
function Stat({ icon, value, label }: { icon: IconName; value: number; label: string }) {
  return (
    <Surface material="raised" className="stats__stat">
      <Icon name={icon} />
      <Text style="title-l" className="tabular">
        {number(Number(value))}
      </Text>
      <Text style="caption" tone="muted">
        {label}
      </Text>
    </Surface>
  );
}

/** A labelled bar: `share` 0–1 of the longest, in a person's or a chart colour. */
function Bar({
  who,
  share,
  colour,
  value,
}: {
  who: ReactNode;
  share: number;
  colour: string;
  value: string;
}) {
  return (
    <li style={{ "--value": share, "--tone": colour } as CSSProperties}>
      <span className="stats__who">{who}</span>
      <span className="stats__bar" aria-hidden="true">
        <i />
      </span>
      <b className="tabular">{value}</b>
    </li>
  );
}

/** The house's numbers, shared by Home and House → Numbers (refreshed every two minutes). */
export const useHouseStats = () => useData<Obj>("/stats/house", { interval: 120000 });

/** Nox's line about the numbers. */
export function NoxSays({ data }: { data: Obj }) {
  return (
    <aside className="stats__nox">
      <Mascot mood="happy" size="s" />
      <p>{quip(data)}</p>
    </aside>
  );
}

/** The house in numbers: music habits, house titles, film nights and the disk, with a bit of fun. */
export function HouseStats({ storage = false }: { storage?: boolean }) {
  const stats = useHouseStats();
  const [tab, setTab] = useState<Tab>(rememberedTab);
  const data = stats.data;
  const choose = (next: Tab) => {
    setTab(next);
    try {
      localStorage.setItem(TAB_KEY, next);
    } catch {
      // private window: the choice lasts until the page closes
    }
  };
  return (
    <Section title={t("The house in numbers")}>
      <Problem error={stats.error} onRetry={stats.reload} />
      {!data ? (
        !stats.error && <State kind="loading" title={t("Counting…")} />
      ) : (
        <div className="stats">
          <NoxSays data={data} />
          <Segmented
            label={t("What to show")}
            value={tab}
            onChange={choose}
            options={TABS.map(([value, label]) => ({ value, label: t(label) }))}
          />
          {tab === "music" && <MusicNumbers music={data.music} />}
          {tab === "titles" &&
            (data.titles.length > 0 || data.week?.length > 0 ? (
              <Titles data={data} />
            ) : (
              <State kind="empty" title={t("Play a few songs and I'll start keeping score.")} />
            ))}
          {tab === "films" && <FilmNumbers movies={data.movies} />}
          {tab === "games" && <GameNumbers games={data.games} />}
          {storage && <StorageTile />}
        </div>
      )}
    </Section>
  );
}

function MusicNumbers({ music }: { music: Obj }) {
  return (
    <>
      <MusicStats music={music} />
      <div className="stats__pair">
        <Djs music={music} />
        {music.genres.length > 0 && (
          <div className="stats__block">
            <Text as="h3" style="label">
              {t("What the house listens to")}
            </Text>
            <GenreRing genres={music.genres} label={t("Time listened by genre")} />
            <Text style="body-s" tone="muted">
              {t("By time listened, radio included.")}
            </Text>
          </div>
        )}
      </div>
      <TopSongs music={music} />
      <ListenClock music={music} />
    </>
  );
}

/** Songs played, hours, different songs, this week against the last. */
export function MusicStats({ music }: { music: Obj }) {
  return (
    <div className="stats__stats">
      <Stat icon="music" value={music.plays} label={t("songs played")} />
      <Stat icon="timer" value={music.hours} label={t("hours of music")} />
      <Stat icon="disc" value={music.songs} label={t("different songs")} />
      <Stat
        icon={music.week >= music.last_week ? "trend-up" : "trend-down"}
        value={music.week}
        label={t("this week") + " · " + fill("{n} last week", { n: music.last_week })}
      />
    </div>
  );
}

/** Who plays the most, as bars in each person's colour. */
export function Djs({ music }: { music: Obj }) {
  if (!music.djs.length) return null;
  const topDj = Math.max(1, ...music.djs.map((dj: Obj) => dj.plays));
  return (
    <div className="stats__block">
      <Text as="h3" style="label">
        {t("Who plays the most")}
      </Text>
      <ul className="stats__bars">
        {music.djs.map((dj: Obj) => (
          <Bar
            key={dj.id}
            who={
              <>
                <Avatar person={dj} /> {dj.name}
              </>
            }
            share={dj.plays / topDj}
            colour={tone(dj.id)}
            value={String(dj.plays)}
          />
        ))}
      </ul>
    </div>
  );
}

/** The most played songs, numbered. */
export function TopSongs({ music, limit }: { music: Obj; limit?: number }) {
  const songs: Obj[] = (music.top_songs || []).slice(0, limit);
  if (!songs.length) return null;
  return (
    <div className="stats__block">
      <Text as="h3" style="label">
        {t("Top songs")}
      </Text>
      <List label={t("Top songs")}>
        {songs.map((song: Obj, i: number) => (
          <ListRow
            key={i}
            leading={
              <span className="stats__song">
                <b className="tabular">{i + 1}</b>
                <Media src={song.art} alt="" ratio="1 / 1" className="stats__art" />
              </span>
            }
            title={song.title && song.title !== "?" ? song.title : t("Untitled song")}
            detail={song.artist && song.artist !== "?" ? song.artist : undefined}
            meta={<span className="tabular">×{song.plays}</span>}
          />
        ))}
      </List>
    </div>
  );
}

/** Songs by hour of the day, the night hours marked. */
export function ListenClock({ music }: { music: Obj }) {
  const peak = Math.max(1, ...(music.hours_of_day || [1]));
  return (
    <div className="stats__block">
      <Text as="h3" style="label">
        {t("When the house listens")}
      </Text>
      <div className="stats__clock" role="img" aria-label={t("Songs played by hour of the day")}>
        {music.hours_of_day.map((count: number, hour: number) => (
          <i
            key={hour}
            title={hour + "h · " + count}
            style={{ "--value": Math.max(0.04, count / peak) } as CSSProperties}
            data-night={hour < 6 || hour >= 22 || undefined}
          />
        ))}
      </div>
      <div className="stats__clock-axis tabular" aria-hidden="true">
        <span>0h</span>
        <span>6h</span>
        <span>12h</span>
        <span>18h</span>
        <span>24h</span>
      </div>
    </div>
  );
}

/** A period on the screen: films finished, episodes, hours. */
export function FilmStats({ block }: { block: Obj }) {
  return (
    <div className="stats__stats">
      <Stat icon="clapperboard" value={block.finished ?? 0} label={t("films finished")} />
      <Stat icon="tv" value={block.episodes ?? 0} label={t("episodes")} />
      <Stat icon="popcorn" value={block.hours ?? 0} label={t("hours on screen")} />
    </div>
  );
}

const KINDS: [string, IconName, string][] = [
  ["film", "film", "Films"],
  ["series", "tv", "Series"],
  ["anime", "sparkles", "Anime"],
];

/** This week, this month or all time: two choices beside a heading. */
function Period<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (value: T) => void;
  options: [T, string][];
}) {
  return (
    <Segmented
      label={t("Period")}
      size="s"
      value={value}
      onChange={onChange}
      options={options.map(([key, label]) => ({ value: key, label: t(label) }))}
    />
  );
}

/** Film nights: this month or all time, split into films, series and anime, and by genre. */
function FilmNumbers({ movies }: { movies: Obj }) {
  const [period, setPeriod] = useState<"month" | "ever">("month");
  const block: Obj = movies?.[period] || {};
  const kinds: Obj = block.kinds || {};
  const most = Math.max(0.1, ...KINDS.map(([key]) => kinds[key] || 0));
  return (
    <>
      <div className="stats__head">
        <Text as="h3" style="label">
          {t("Film nights")}
        </Text>
        <Period
          value={period}
          onChange={setPeriod}
          options={[
            ["month", "This month"],
            ["ever", "All time"],
          ]}
        />
      </div>
      <FilmStats block={block} />
      {block.hours > 0 ? (
        <div className="stats__pair">
          <div className="stats__block">
            <Text as="h3" style="label">
              {t("Films, series or anime")}
            </Text>
            <ul className="stats__bars">
              {KINDS.map(([key, icon, label], i) => (
                <Bar
                  key={key}
                  who={
                    <>
                      <Icon name={icon} size="s" /> {t(label)}
                    </>
                  }
                  share={(kinds[key] || 0) / most}
                  colour={GENRE_TONES[i]}
                  value={(kinds[key] || 0) + " h"}
                />
              ))}
            </ul>
          </div>
          {block.genres?.length > 0 && (
            <div className="stats__block">
              <Text as="h3" style="label">
                {t("What the house watches")}
              </Text>
              <GenreRing genres={block.genres} label={t("Time watched by genre")} />
            </div>
          )}
        </div>
      ) : (
        <State
          kind="empty"
          title={
            period === "month"
              ? t("Nothing watched this month yet.")
              : t("Watch a film and it shows up here.")
          }
        />
      )}
    </>
  );
}

/** Games: hours, games played, sessions, the library; who plays, on which consoles; the top games. */
function GameNumbers({ games }: { games?: Obj }) {
  if (!games?.hours && !games?.sessions)
    return <State kind="empty" title={t("Play a game and it shows up here.")} />;
  const most = Math.max(0.1, ...games.players.map((p: Obj) => p.hours));
  return (
    <>
      <div className="stats__stats">
        <Stat icon="timer" value={games.hours} label={t("hours played")} />
        <Stat icon="gamepad" value={games.played} label={t("games played")} />
        <Stat icon="play" value={games.sessions} label={t("sessions")} />
        <Stat icon="archive" value={games.library} label={t("games in the house")} />
      </div>
      <div className="stats__pair">
        {games.players.length > 0 && (
          <div className="stats__block">
            <Text as="h3" style="label">
              {t("Who plays")}
            </Text>
            <ul className="stats__bars">
              {games.players.map((p: Obj) => (
                <Bar
                  key={p.id}
                  who={
                    <>
                      <Avatar person={p} /> {p.name}
                    </>
                  }
                  share={p.hours / most}
                  colour={tone(p.id)}
                  value={p.hours + " h"}
                />
              ))}
            </ul>
          </div>
        )}
        {games.consoles.length > 0 && (
          <div className="stats__block">
            <Text as="h3" style="label">
              {t("Consoles")}
            </Text>
            <GenreRing genres={games.consoles} label={t("Time played by console")} />
          </div>
        )}
      </div>
      {games.top.length > 0 && (
        <div className="stats__block">
          <Text as="h3" style="label">
            {t("Top games")}
          </Text>
          <List label={t("Top games")}>
            {games.top.map((game: Obj, i: number) => (
              <ListRow
                key={game.id}
                leading={
                  <span className="stats__song">
                    <b className="tabular">{i + 1}</b>
                    <Media src={game.art} alt="" ratio="1 / 1" className="stats__art" />
                  </span>
                }
                title={game.title}
                detail={game.system}
                meta={<span className="tabular">{game.hours} h</span>}
                href={"/games?game=" + game.id}
              />
            ))}
          </List>
        </div>
      )}
    </>
  );
}

/** House titles, two ways: this week (a fresh race; nobody holds more than two while others
 *  score) and all time (the long-run leaders, with up to 3 stars). */
/** A title's name and medal as the theme in force has them (flavour title.<key>.name, sprite
 *  title.<key>), else HouseOS's own; the star mark too (flavour title.star.mark). */
function useTitleLook() {
  const info = useThemeInfo();
  const { language } = useI18n();
  const words = (key: string) => {
    const own = info?.flavor[key];
    return own ? (language === "fr" ? own.fr : own.en) : undefined;
  };
  return {
    name: (key: string, fallback: string) => words("title." + key + ".name") ?? t(fallback),
    star: words("title.star.mark") ?? "★",
    medal: (key: string, icon: IconName) => {
      const grid = themeGrid(info, "title." + key);
      return grid ? <PieceFill grid={grid} box={32} /> : <Icon name={icon} />;
    },
  };
}

export function Titles({ data, compact = false }: { data: Obj; compact?: boolean }) {
  const look = useTitleLook();
  const [period, setPeriod] = useState<"week" | "ever">(data.week?.length ? "week" : "ever");
  const list: Obj[] = (period === "week" ? data.week : data.titles) || [];
  return (
    <div className="stats__block">
      <div className="stats__head">
        <Text as="h3" style="label">
          {!compact && t("House titles") + " "}
          <span className="tabular">
            {fill("{n} of {total} taken", { n: list.length, total: TOTAL })}
          </span>
        </Text>
        <Period
          value={period}
          onChange={setPeriod}
          options={[
            ["week", "This week"],
            ["ever", "All time"],
          ]}
        />
      </div>
      {list.length ? (
        <ul className="stats__titles">
          {list.map((title: Obj) => {
            const [icon, name, many] = TITLES[title.key] || ["star", title.key, "{n}"];
            const detail = title.value === 1 ? ONE[many] || many : many;
            const values = {
              n: title.value,
              song: title.song || "",
              genre: title.genre ? t(title.genre) : "",
            };
            return (
              <Surface
                as="li"
                material="raised"
                key={title.key}
                title={fill(detail, values)}
                style={{ "--tone": tone(title.person.id) } as CSSProperties}
              >
                {look.medal(title.key, icon)}
                <strong>
                  {fillTheme(look.name(title.key, name), values)}
                  {title.stars > 0 && (
                    <span
                      className="stats__stars"
                      aria-label={fill("{n} of 3 stars", { n: title.stars })}
                    >
                      {look.star.repeat(title.stars)}
                    </span>
                  )}
                </strong>
                <span className="stats__who">
                  <Avatar person={title.person} /> <span>{title.person.name}</span>
                </span>
                <Text style="caption" tone="muted">
                  {fill(detail, values)}
                </Text>
              </Surface>
            );
          })}
          {Object.entries(TITLES)
            .filter(([key]) => !compact && !list.some((title: Obj) => title.key === key))
            .map(([key, [icon, name]]) => (
              <Surface
                as="li"
                material="sunken"
                key={key}
                data-locked=""
                title={t("Nobody holds it yet")}
              >
                {look.medal(key, icon)}
                <strong>{fillTheme(look.name(key, name), { genre: t("a genre") })}</strong>
                <Text style="caption" tone="muted">
                  {t("Nobody holds it yet")}
                </Text>
              </Surface>
            ))}
        </ul>
      ) : (
        <State kind="empty" title={t("Nothing yet this week: the first song takes a title.")} />
      )}
      <Whisper you={data.you} />
    </div>
  );
}

/** Nox's aside for the viewer: the titles they hold, and the one they could take next. */
function Whisper({ you }: { you?: Obj }) {
  if (!you) return null;
  const next = you.next && NUDGES[you.next.key] && fill(NUDGES[you.next.key], { n: you.next.n });
  const holds =
    you.holds?.length > 0 &&
    fill(you.holds.length > 1 ? "You hold {n} titles" : "You hold a title", {
      n: you.holds.length,
    });
  if (!next && !holds) return null;
  return (
    <p className="stats__nox">
      <Mascot size="s" />
      <span>{[holds, next].filter(Boolean).join(" · ")}</span>
    </p>
  );
}

/** The disk, as one part of the numbers (for those allowed to see storage). */
function StorageTile() {
  const state = useData("/music/storage", { interval: 60000 });
  const disk = state.data?.disk,
    categories = state.data?.categories;
  const names: Record<string, string> = {
    music: "Music",
    movies: "Movies",
    files: "Files",
    other: "Other",
  };
  return (
    <section className="stats__block" aria-labelledby="stats-storage">
      <Text as="h3" style="label">
        <span id="stats-storage">{t("House storage")}</span>
      </Text>
      <Problem error={state.error} onRetry={state.reload} />
      {!disk ? (
        !state.error && <State kind="loading" title={t("Checking storage…")} />
      ) : (
        <>
          <div className="stats__disk">
            <Icon name="storage" />
            <strong>
              {bytes(disk.free_bytes)} {t("free")}
            </strong>
            <Text style="body-s" tone="muted">
              {bytes(disk.used_bytes)} {t("used")} / {bytes(disk.total_bytes)}
            </Text>
          </div>
          <Progress
            label={t("Drive space used")}
            value={disk.used_bytes / (disk.total_bytes || 1)}
          />
          <div className="stats__stats">
            {Object.entries(names).map(([key, name]) => (
              <Surface material="sunken" key={key} className="stats__stat">
                <Text style="caption" tone="muted">
                  {t(name)}
                </Text>
                <strong className="tabular">{bytes(categories?.[key] || 0)}</strong>
              </Surface>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

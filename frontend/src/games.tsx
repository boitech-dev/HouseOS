// Games (D33): the house's own games, like Watch for films. Shelves, search and filters; a game's
// sheet with its versions, your saves and where to play it: here (in the browser, nothing to
// install) or on the TV (Moonlight). Adding: an upload, a link, or a folder the admin points at.
import { t } from "./i18n";
import { useEffect, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  bytes,
  date,
  items,
  percent,
  useData,
  usePages,
  useUser,
  type Obj,
} from "./api";
import {
  Button,
  Chip,
  ChipGroup,
  ConfirmSheet,
  Field,
  FileButton,
  IconButton,
  Input,
  List,
  ListRow,
  Media,
  MediaCard,
  MoreBelow,
  Notice,
  Page,
  PageHeader,
  Problem,
  Progress,
  SearchInput,
  Segmented,
  Select,
  Sheet,
  Shelf,
  State,
  Status,
  Switch,
  Text,
  toast,
} from "./design";
import { message } from "./messages";
import { go } from "./nav";
import { transferFile } from "./file_transfer";
import "./games.css";

const COVER = "132px";
const FEW = 12; // up to this many games, one grid: shelves would show the same few again and again
const ROWS: Record<string, [string, string]> = {
  continue: ["Continue playing", "played=true&sort=played"],
  favourites: ["Your favourites", "favourites=true"],
  recent: ["Just added", "sort=added"],
  together: ["Play together", "players=2"],
  hacks: ["Romhacks and translations", "hacks=true"],
};
type Filters = {
  q: string;
  system: string;
  genre: string;
  players: string;
  decade: string;
  hacks: boolean;
  here: boolean;
  favourites: boolean;
  sort: string;
};
const NONE: Filters = {
  q: "",
  system: "",
  genre: "",
  players: "",
  decade: "",
  hacks: false,
  here: false,
  favourites: false,
  sort: "title",
};
const query = (f: Filters) =>
  Object.entries(f)
    .filter(([, v]) => v !== "" && v !== false)
    .map(([k, v]) => k + "=" + encodeURIComponent(String(v)))
    .join("&");
const filtering = (f: Filters) => query({ ...f, sort: "title" }) !== "sort=title";
export const when = (at?: number | null) =>
  at ? date(at * 1000, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const rowLabel = (id: string, systems: Obj) =>
  id.startsWith("system:") ? systems[id.slice(7)]?.name || id.slice(7) : t(ROWS[id]?.[0] || id);

/** A box: the game's own cover, whole, on the theme's sunken ground; its title instead when there
 *  is no picture (or it never arrives). */
export function Cover({ game }: { game: Obj }) {
  const [broken, setBroken] = useState(false);
  return (
    <span className="games-cover">
      {game.art?.box && !broken ? (
        <img src={game.art.box} alt="" loading="lazy" onError={() => setBroken(true)} />
      ) : (
        <span className="games-cover__title">{game.title}</span>
      )}
    </span>
  );
}

/** "42%" of a link's download, when the site said how big it is. */
function downloaded(progress?: Obj | null) {
  if (!progress?.total) return "";
  return percent(Math.min(99, Math.floor((progress.bytes / progress.total) * 100)));
}

function Card({ game, onOpen }: { game: Obj; onOpen: () => void }) {
  const badge = game.state === "downloading"
    ? downloaded(game.progress) || t("Downloading…")
    : game.state === "failed"
      ? t("Didn't work")
      : game.hack
        ? t("Hack")
        : game.versions > 1
          ? t("{n} versions").replace("{n}", String(game.versions))
          : null; // prettier-ignore
  return (
    <li className="games-card">
      <MediaCard
        media={<Cover game={game} />}
        badge={badge}
        title={game.title}
        meta={[game.system_name, game.year].filter(Boolean).join(" · ") || t("Which console?")}
        onOpen={onOpen}
      />
    </li>
  );
}

export function Games() {
  const params = new URLSearchParams(location.search);
  const me = useUser();
  const admin = me?.role === "admin";
  const [filters, setFilters] = useState<Filters>(NONE),
    [text, setText] = useState(""),
    [more, setMore] = useState(false),
    [open, setOpen] = useState(params.get("game") || ""),
    [sheet, setSheet] = useState<"" | "add" | "add-link" | "setup">(() => {
      const asked = params.get("sheet") || "";
      return asked === "add" || asked === "add-link" || asked === "setup" ? asked : "";
    }),
    [view, setView] = useState<"mine" | "catalogue">(
      params.get("view") === "catalogue" ? "catalogue" : "mine",
    ),
    [shelf, setShelf] = useState(params.get("shelf") || "");
  useEffect(() => {
    const follow = () => {
      const next = new URLSearchParams(location.search);
      setShelf(next.get("shelf") || "");
      setOpen(next.get("game") || "");
    };
    addEventListener("popstate", follow);
    return () => removeEventListener("popstate", follow);
  }, []);
  const shelves = useData("/games/shelves", {
    // Faster while a game downloads or is being named, so it appears as soon as it's ready.
    interval: (d) => (/"downloading"|"identifying":true/.test(JSON.stringify(d || {})) ? 3000 : 0),
  });
  const tv = useData("/games/tv", { interval: (d) => (d?.playing || d?.waiting ? 5000 : 60000) });
  const data = shelves.data || {};
  const systems: Obj = data.systems || {};
  const present = (data.rows || [])
    .filter((row: Obj) => row.id.startsWith("system:"))
    .map((row: Obj) => row.id.slice(7));
  const set = (change: Partial<Filters>) => setFilters((f) => ({ ...f, ...change }));
  const openGame = (id: string) => {
    setOpen(id);
    history.replaceState(history.state, "", location.pathname + "?game=" + id);
  };
  const card = (game: Obj) => <Card key={game.id} game={game} onOpen={() => openGame(game.id)} />;
  const seeAll = (id: string) => {
    history.pushState({ shelf: true }, "", "/games?shelf=" + encodeURIComponent(id));
    setShelf(id);
    scrollTo({ top: 0 });
  };
  const listPath = shelf
    ? "/games?" +
      (shelf.startsWith("system:") ? "system=" + shelf.slice(7) : ROWS[shelf]?.[1] || "")
    : "/games?" + query(filters);
  const empty = shelves.data && !data.total;
  return (
    <Page width="wide">
      <PageHeader
        room="games"
        title={t("Games")}
        actions={
          <>
            <Button icon="film" variant="quiet" onClick={() => go("/watch")}>
              {t("Watch")}
            </Button>
            <Button icon="add" variant="primary" onClick={() => setSheet("add")}>
              {t("Add games")}
            </Button>
            {admin && (
              <IconButton
                icon="settings"
                label={t("Set up games")}
                onClick={() => setSheet("setup")}
              />
            )}
          </>
        }
      />
      <OnTv tv={tv.data} onStop={() => void api("/games/tv/stop", "POST").then(tv.reload)} />
      <Segmented
        label={t("What to show")}
        value={view}
        onChange={setView}
        options={[
          { value: "mine", label: t("In the house") },
          { value: "catalogue", label: t("Catalogue") },
        ]}
      />
      {view === "catalogue" ? (
        <Catalogue
          systems={systems}
          first={present[0]}
          onOpen={openGame}
          onAdd={() => setSheet("add-link")}
        />
      ) : (
        <>
          {!empty && (
            <form
              className="games-search"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                set({ q: text.trim() });
              }}
            >
              <div className="games-search__field">
                <SearchInput
                  label={t("Search games")}
                  placeholder={t("A game, a series, a studio…")}
                  value={text}
                  onChange={(value) => {
                    setText(value);
                    if (!value) set({ q: "" });
                  }}
                />
              </div>
              <div className="games-tools">
                <ChipGroup label={t("Consoles")}>
                  {present.map((key: string) => (
                    <Chip
                      key={key}
                      kind="filter"
                      selected={filters.system === key}
                      onToggle={() => set({ system: filters.system === key ? "" : key })}
                    >
                      {systems[key]?.name || key}
                    </Chip>
                  ))}
                </ChipGroup>
                <Select
                  aria-label={t("Sort")}
                  value={filters.sort}
                  onChange={(e) => set({ sort: e.target.value })}
                >
                  <option value="title">{t("A to Z")}</option>
                  <option value="added">{t("Just added")}</option>
                  <option value="played">{t("Last played")}</option>
                  <option value="plays">{t("Most played")}</option>
                  <option value="year">{t("Newest first")}</option>
                </Select>
                <Button
                  icon="sliders"
                  variant="quiet"
                  aria-expanded={more}
                  onClick={() => setMore(!more)}
                >
                  {t("Filters")}
                </Button>
              </div>
              {more && <FilterPanel value={filters} onChange={set} />}
            </form>
          )}
          <Problem error={shelves.error} onRetry={shelves.reload} />
          {empty ? (
            <State
              kind="empty"
              title={t("Bring your games")}
              action={
                <Button icon="add" variant="primary" onClick={() => setSheet("add")}>
                  {t("Add games")}
                </Button>
              }
            >
              {t(
                "Upload a game file from any device, paste a link to one, or point the house at the folder where you keep them. HouseOS never downloads games by itself.",
              )}
            </State>
          ) : shelf || filtering(filters) || filters.sort !== "title" || data.total <= FEW ? (
            <Grid
              path={listPath}
              card={card}
              title={shelf ? rowLabel(shelf, systems) : undefined}
              onBack={
                shelf
                  ? () => {
                      if (history.state?.shelf) history.back();
                      else {
                        history.replaceState(null, "", "/games");
                        setShelf("");
                      }
                    }
                  : undefined
              }
            />
          ) : (
            (data.rows || [])
              // One console only: its row would repeat the others.
              .filter((row: Obj) => !row.id.startsWith("system:") || present.length > 1)
              .map((row: Obj) => (
                <Shelf
                  key={row.id}
                  title={rowLabel(row.id, systems)}
                  item={COVER}
                  action={
                    (row.count ?? items(row).length) > items(row).length ? (
                      <Button
                        variant="link"
                        size="s"
                        aria-label={t("See all") + " · " + rowLabel(row.id, systems)}
                        onClick={() => seeAll(row.id)}
                      >
                        {row.count
                          ? t("See all {n}").replace("{n}", String(row.count))
                          : t("See all")}
                      </Button>
                    ) : undefined
                  }
                >
                  {items(row).map(card)}
                </Shelf>
              ))
          )}
        </>
      )}
      {open && (
        <GameSheet
          key={open}
          id={open}
          onOpen={openGame}
          onClose={() => {
            setOpen("");
            history.replaceState(history.state, "", shelf ? "/games?shelf=" + shelf : "/games");
          }}
          onTv={tv.reload}
        />
      )}
      {(sheet === "add" || sheet === "add-link") && (
        // From the catalogue, the person usually holds a link: that tab first.
        <AddSheet from={sheet === "add-link" ? "link" : "upload"} onClose={() => setSheet("")} />
      )}
      {sheet === "setup" && <SetupSheet tv={tv.data} onClose={() => setSheet("")} />}
    </Page>
  );
}

/** Every game known for a console (the open libretro lists), what the house has marked, and
 *  the romhacks with their pages. Names, facts and covers only: the games are yours to bring. */
/** The house's Find link with this game's details, each encoded, filled in one pass; opened in
 *  a new tab. */
export function findUrl(template: string, game: Obj) {
  const values: Record<string, string> = {
    title: game.title || "",
    console: game.console || "",
    system: game.system || "",
    region: game.region || "",
    filename: game.file || "",
    crc32: game.key || "",
  };
  return template.replace(/\{(\w+)\}/g, (_, key) => encodeURIComponent(values[key] ?? ""));
}
function openFind(template: string, game: Obj) {
  window.open(findUrl(template, game), "_blank", "noopener,noreferrer");
}

function Catalogue({
  systems,
  first,
  onOpen,
  onAdd,
}: {
  systems: Obj;
  first?: string;
  onOpen: (id: string) => void;
  onAdd: () => void;
}) {
  const house = useData("/house-settings");
  const find: string = house.data?.games_find_url || "";
  const [system, setSystem] = useState(first || "snes"),
    [hacks, setHacks] = useState(false),
    [text, setText] = useState(""),
    [q, setQ] = useState(""),
    [picked, setPicked] = useState<Obj | null>(null);
  const path =
    "/games/catalogue?system=" +
    system +
    (hacks ? "&hacks=true" : "") +
    (q ? "&q=" + encodeURIComponent(q) : "");
  // The first look at a console downloads its lists behind; this read watches until they are in.
  const head = useData(path, { interval: (d) => (d?.preparing ? 4000 : 0) });
  const pages = usePages(path, (data) =>
    data.next_offset != null ? "offset=" + data.next_offset : null,
  );
  return (
    <section className="games-stack" aria-label={t("Catalogue")}>
      <form
        className="games-search__field"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(text.trim());
        }}
      >
        <Select
          aria-label={t("Console")}
          value={system}
          onChange={(e) => setSystem(e.target.value)}
        >
          {Object.entries(systems).map(([key, s]) => (
            <option key={key} value={key}>
              {(s as Obj).name}
            </option>
          ))}
        </Select>
        <SearchInput
          label={t("Search the catalogue")}
          placeholder={t("A game, a studio, a genre…")}
          value={text}
          onChange={(value) => {
            setText(value);
            if (!value) setQ("");
          }}
        />
        <Switch label={t("Romhacks")} checked={hacks} onChange={setHacks} />
      </form>
      <Text style="caption" tone="muted">
        {t(
          "From the open libretro database (the No-Intro, Redump and FBNeo lists, with genres, years and covers): free, no account, nothing to link. Yours are marked; for the others, bring your own copy.",
        )}
      </Text>
      {head.data?.preparing && (
        <Status tone="info" busy>
          {t("Getting this console's game list (the first time only, about a minute)…")}
        </Status>
      )}
      <Problem error={pages.error} onRetry={pages.reload} />
      <ul className="games-grid">
        {pages.items.map((game) => (
          <li key={game.id} className="games-card" data-have={game.have ? "" : undefined}>
            <MediaCard
              media={<Cover game={{ ...game, system_name: systems[system]?.name }} />}
              badge={game.have ? t("In the house") : game.hack || hacks ? t("Hack") : null}
              title={game.title}
              meta={[game.year, game.genre].filter(Boolean).join(" · ")}
              onOpen={() => (game.have ? onOpen(game.have) : setPicked(game))}
            />
          </li>
        ))}
      </ul>
      <MoreBelow pages={pages} />
      {picked && (
        <Sheet title={picked.title} place="side" onClose={() => setPicked(null)}>
          <div className="games-sheet">
            <div className="games-sheet__head">
              <Cover game={{ ...picked, system_name: systems[system]?.name }} />
              <div className="games-sheet__facts">
                <Text style="body-s" tone="muted">
                  {[
                    systems[system]?.name,
                    picked.year,
                    picked.genre,
                    picked.players > 1
                      ? t("{n} players").replace("{n}", String(picked.players))
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </Text>
                {(picked.developer || picked.publisher) && (
                  <Text style="body-s">
                    {[picked.developer, picked.publisher]
                      .filter((v, i, a) => v && a.indexOf(v) === i)
                      .join(" · ")}
                  </Text>
                )}
                {picked.base && (
                  <Text style="body-s">
                    {t("A romhack of {game}").replace("{game}", picked.base)}
                  </Text>
                )}
              </div>
            </div>
            {picked.base ? (
              <Notice
                tone="info"
                title={
                  picked.base_have ? t("You have the original") : t("You'll need the original")
                }
                action={
                  picked.homepage ? (
                    <Button
                      size="s"
                      icon="link"
                      onClick={() => window.open(picked.homepage, "_blank", "noopener")}
                    >
                      {t("The hack's page")}
                    </Button>
                  ) : undefined
                }
              >
                {picked.base_have
                  ? t(
                      "Get its patch (.ips or .bps) from the hack's page, then open your game → Add a romhack patch.",
                    )
                  : t(
                      "A romhack is a patch for a game you have: bring {game} first, then add the patch from the hack's page.",
                    ).replace("{game}", picked.base)}
              </Notice>
            ) : (
              <Notice
                tone="info"
                title={t("Not in the house")}
                action={
                  <>
                    {find && (
                      <Button
                        size="s"
                        icon="search"
                        onClick={() =>
                          openFind(find, { ...picked, console: systems[system]?.name, system })
                        }
                      >
                        {t("Search online")}
                      </Button>
                    )}
                    <Button size="s" variant="primary" icon="add" onClick={onAdd}>
                      {t("Add your copy")}
                    </Button>
                  </>
                }
              >
                {find
                  ? t(
                      "Search online opens a web search in a new tab. Found it? Add your copy: paste its download link, or upload the file.",
                    )
                  : t("Upload your own copy, or paste a link to it.")}
              </Notice>
            )}
          </div>
        </Sheet>
      )}
    </section>
  );
}

function FilterPanel({
  value,
  onChange,
}: {
  value: Filters;
  onChange: (f: Partial<Filters>) => void;
}) {
  const all = useData("/games?limit=1");
  const facets = all.data?.facets || {};
  const genres = Object.entries((facets.genres || {}) as Record<string, number>).sort(
    (a, b) => b[1] - a[1],
  );
  const decades = Object.keys(facets.decades || {}).sort();
  return (
    <div className="games-filters">
      <ChipGroup label={t("Genre")}>
        {genres.slice(0, 16).map(([genre, count]) => (
          <Chip
            key={genre}
            kind="filter"
            count={count}
            selected={value.genre === genre}
            onToggle={() => onChange({ genre: value.genre === genre ? "" : genre })}
          >
            {genre}
          </Chip>
        ))}
      </ChipGroup>
      <div className="games-filters__row">
        <Select
          aria-label={t("Decade")}
          value={value.decade}
          onChange={(e) => onChange({ decade: e.target.value })}
        >
          <option value="">{t("Any year")}</option>
          {decades.map((d) => (
            <option key={d} value={d}>
              {d.slice(2)}s
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("Players")}
          value={value.players}
          onChange={(e) => onChange({ players: e.target.value })}
        >
          <option value="">{t("Any number of players")}</option>
          <option value="2">{t("2 players or more")}</option>
          <option value="3">{t("3 players or more")}</option>
          <option value="4">{t("4 players")}</option>
        </Select>
      </div>
      <div className="games-filters__row">
        <Switch
          label={t("Plays here")}
          checked={value.here}
          onChange={(here) => onChange({ here })}
        />
        <Switch
          label={t("Romhacks")}
          checked={value.hacks}
          onChange={(hacks) => onChange({ hacks })}
        />
        <Switch
          label={t("Favourites")}
          checked={value.favourites}
          onChange={(favourites) => onChange({ favourites })}
        />
        <Button variant="link" size="s" onClick={() => onChange({ ...NONE, q: value.q })}>
          {t("Clear filters")}
        </Button>
      </div>
    </div>
  );
}

function Grid({
  path,
  card,
  title,
  onBack,
}: {
  path: string;
  card: (game: Obj) => ReactNode;
  title?: string;
  onBack?: () => void;
}) {
  const pages = usePages(path, (data) =>
    data.next_offset != null ? "offset=" + data.next_offset : null,
  );
  return (
    <section className="games-stack" aria-label={title || t("Games")}>
      {onBack && (
        <div className="games-grid__head">
          <Button variant="quiet" icon="back" onClick={onBack}>
            {t("Back")}
          </Button>
          <Text as="h2" style="title-m">
            {title}
          </Text>
        </div>
      )}
      <Problem error={pages.error} onRetry={pages.reload} />
      {!pages.loading && !pages.items.length ? (
        <State kind="empty" title={t("No game matches")} />
      ) : (
        <ul className="games-grid">{pages.items.map(card)}</ul>
      )}
      <MoreBelow pages={pages} />
    </section>
  );
}

/** What the TV is playing, with a way to stop it from any phone. */
function OnTv({ tv, onStop }: { tv?: Obj | null; onStop: () => void }) {
  if (!tv?.playing) return null;
  return (
    <Notice
      tone="success"
      title={t("On the TV: {title}").replace("{title}", tv.playing.title || t("a game"))}
      action={
        <Button size="s" icon="stop" onClick={onStop}>
          {t("Stop")}
        </Button>
      }
    >
      {t("{name}'s save.").replace("{name}", tv.playing.player || "")}
    </Notice>
  );
}

// ---------- a game ----------

function GameSheet({
  id,
  onOpen,
  onClose,
  onTv,
}: {
  id: string;
  onOpen: (id: string) => void;
  onClose: () => void;
  onTv: () => void;
}) {
  const game = useData("/games/" + id, {
    interval: (d) => ((d as Obj | null)?.state === "downloading" ? 3000 : 0),
  });
  const me = useUser();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [tvSheet, setTvSheet] = useState(false),
    [removing, setRemoving] = useState(false),
    [fixing, setFixing] = useState(false);
  const g = game.data;
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await game.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  // A full page load: the player's page comes with its own security policy (WebAssembly).
  const playHere = (state?: string) =>
    location.assign("/games/play/" + id + (state ? "?state=" + encodeURIComponent(state) : ""));
  const playTv = () =>
    act(async () => {
      await api("/games/tv/play", "POST", { game_id: id });
      setTvSheet(true);
      onTv();
    });
  const patch = async (file: File) => {
    const entry = await transferFile(file, {
      actorId: me!.id,
      scope: "media",
      onProgress: () => {},
    });
    const made = await api("/games/" + id + "/patch", "POST", {
      file_id: entry.id,
      version: entry.version,
    });
    toast(t("Added: {title}").replace("{title}", made.title));
    onOpen(made.id);
  };
  const facts = g
    ? [
        g.system_name,
        g.year,
        g.genre,
        g.players > 1 ? t("{n} players").replace("{n}", String(g.players)) : "",
      ]
        .filter(Boolean)
        .join(" · ")
    : "";
  return (
    <Sheet title={g?.title || t("Game")} place="side" wide onClose={onClose}>
      <Problem error={game.error || error} onRetry={game.error ? game.reload : undefined} />
      {g && (
        <div className="games-sheet">
          <div className="games-sheet__head">
            <Cover game={g} />
            <div className="games-sheet__facts">
              <Text style="body-s" tone="muted">
                {facts}
              </Text>
              {(g.developer || g.publisher) && (
                <Text style="body-s">
                  {[g.developer, g.publisher]
                    .filter((v, i, a) => v && a.indexOf(v) === i)
                    .join(" · ")}
                </Text>
              )}
              {g.hack && g.base && (
                <Text style="body-s">{t("A romhack of {game}").replace("{game}", g.base)}</Text>
              )}
              {!!g.tags?.length && (
                <ChipGroup label={t("Version")}>
                  {g.tags.map((tag: string) => (
                    <Chip key={tag}>{tag}</Chip>
                  ))}
                </ChipGroup>
              )}
              <div className="games-sheet__play">
                <Button
                  variant="primary"
                  icon="play"
                  disabled={!g.here || g.missing || busy}
                  onClick={() => playHere()}
                >
                  {t("Play here")}
                </Button>
                {g.tv && (
                  <Button icon="tv" disabled={busy || g.missing} onClick={() => void playTv()}>
                    {t("Play on the TV")}
                  </Button>
                )}
                <IconButton
                  icon="heart"
                  label={g.favourite ? t("Remove from favourites") : t("Add to favourites")}
                  aria-pressed={!!g.favourite}
                  onClick={() =>
                    void act(() => api("/games/" + id + "/favourite", "PUT", { on: !g.favourite }))
                  }
                />
              </div>
              {!g.here && !g.needs_bios && g.system && (
                <Text style="caption" tone="muted">
                  {t("This console is too big for a browser: it plays on the TV.")}
                </Text>
              )}
            </div>
          </div>
          {g.state === "downloading" && (
            <Notice tone="info" title={t("Downloading it into the house…")}>
              <Progress
                label={t("Download")}
                busy={!g.progress?.total}
                value={g.progress?.total ? g.progress.bytes / g.progress.total : 0}
              />
              {g.progress?.total
                ? t("{percent} · {done} of {total}")
                    .replace("{percent}", downloaded(g.progress))
                    .replace("{done}", bytes(g.progress.bytes))
                    .replace("{total}", bytes(g.progress.total))
                : t("{done} so far").replace("{done}", bytes(g.progress?.bytes || 0))}
            </Notice>
          )}
          {g.state === "failed" && (
            <Notice tone="danger" title={t("The download didn't work")}>
              {message(g.error)} {t("Delete this one before adding the link again.")}
            </Notice>
          )}
          {g.needs_bios && g.state === "ready" && (
            <Notice tone="warning" title={t("It needs its console's BIOS")}>
              {t(
                "A small file from the console itself ({files}). An admin adds it in Games → Set up; HouseOS never downloads it.",
              ).replace("{files}", (g.bios_names || []).join(", "))}
            </Notice>
          )}
          {!g.system && g.state !== "failed" && <PickSystem id={id} onDone={game.reload} />}
          {g.missing && (
            <Notice tone="danger">{t("This game's file is gone from its folder.")}</Notice>
          )}
          {g.versions?.length > 1 && (
            <section className="games-sheet__section" aria-label={t("Versions")}>
              <Text as="h3" style="title-s">
                {t("Versions")}
              </Text>
              <ChipGroup label={t("Versions")}>
                {g.versions.map((v: Obj) => (
                  <Chip
                    key={v.id}
                    kind="filter"
                    selected={v.id === id}
                    onToggle={() => v.id !== id && onOpen(v.id)}
                  >
                    {[v.region, ...(v.tags || []).filter((x: string) => x !== v.region)]
                      .filter(Boolean)
                      .join(" · ") || v.file}
                  </Chip>
                ))}
              </ChipGroup>
            </section>
          )}
          {(g.art?.title || g.art?.snap) && (
            <div className="games-sheet__shots">
              {g.art.title && <Media src={g.art.title} alt={t("Title screen")} ratio="4 / 3" />}
              {g.art.snap && <Media src={g.art.snap} alt={t("In the game")} ratio="4 / 3" />}
            </div>
          )}
          <Saves game={g} onContinue={playHere} onChanged={game.reload} />
          <section className="games-sheet__section" aria-label={t("This game")}>
            <div className="games-sheet__actions">
              {g.player?.file && me?.role !== "guest" && (
                <Button
                  icon="download"
                  variant="quiet"
                  onClick={() => (location.href = g.player.file)}
                >
                  {t("Download ({size})").replace("{size}", bytes(g.size || 0))}
                </Button>
              )}
              {g.system && g.size < 128 * 1024 * 1024 && (
                <FileButton
                  label={t("Add a romhack patch")}
                  accept=".ips,.bps"
                  variant="quiet"
                  onFiles={([file]) => void act(() => patch(file))}
                />
              )}
              {g.can_change && (
                <Button icon="edit" variant="quiet" onClick={() => setFixing(true)}>
                  {t("Fix details")}
                </Button>
              )}
              {g.can_change && (
                <Button icon="trash" variant="quiet" onClick={() => setRemoving(true)}>
                  {g.source === "folder" ? t("Hide") : t("Delete")}
                </Button>
              )}
            </div>
            {g.homepage && (
              <Text style="caption" tone="muted">
                <a href={g.homepage} target="_blank" rel="noreferrer noopener">
                  {t("The hack's page")}
                </a>
              </Text>
            )}
          </section>
        </div>
      )}
      {tvSheet && g && <TvSheet title={g.title} onClose={() => setTvSheet(false)} />}
      {fixing && g && <FixSheet game={g} onClose={() => setFixing(false)} onDone={game.reload} />}
      {removing && g && (
        <ConfirmSheet
          title={g.source === "folder" ? t("Hide this game?") : t("Delete this game?")}
          confirm={g.source === "folder" ? t("Hide") : t("Delete")}
          danger
          onClose={() => setRemoving(false)}
          onConfirm={async () => {
            await api("/games/" + id + "?version=" + g.version, "DELETE");
            toast(g.source === "folder" ? t("Hidden.") : t("Deleted."));
            onClose();
          }}
        >
          {g.source === "folder"
            ? t("It stays in its folder; the library stops showing it. Everyone's saves stay.")
            : t("Its file leaves the house. Everyone's saves stay, in case it comes back.")}
        </ConfirmSheet>
      )}
    </Sheet>
  );
}

function PickSystem({ id, onDone }: { id: string; onDone: () => void }) {
  const shelves = useData("/games/shelves");
  const systems: Obj = shelves.data?.systems || {};
  return (
    <Notice tone="warning" title={t("Which console is it?")}>
      <Select
        aria-label={t("Console")}
        value=""
        onChange={(e) => void api("/games/" + id, "PATCH", { system: e.target.value }).then(onDone)}
      >
        <option value="">{t("Pick the console")}</option>
        {Object.entries(systems).map(([key, s]) => (
          <option key={key} value={key}>
            {(s as Obj).name}
          </option>
        ))}
      </Select>
    </Notice>
  );
}

function FixSheet({
  game,
  onClose,
  onDone,
}: {
  game: Obj;
  onClose: () => void;
  onDone: () => void;
}) {
  const [title, setTitle] = useState(game.title);
  const [error, setError] = useState("");
  return (
    <Sheet
      title={t("Fix details")}
      place="center"
      onClose={onClose}
      footer={
        <Button
          variant="primary"
          onClick={() =>
            void api("/games/" + game.id, "PATCH", { title })
              .then(() => {
                onDone();
                onClose();
              })
              .catch((e) => setError(e.message))
          }
        >
          {t("Save")}
        </Button>
      }
    >
      <Problem error={error} />
      <Field label={t("Title")}>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <PickSystem id={game.id} onDone={onDone} />
    </Sheet>
  );
}

/** Your saves: the in-game one (every screen) and the snapshots you took. */
function Saves({
  game,
  onContinue,
  onChanged,
}: {
  game: Obj;
  onContinue: (state: string) => void;
  onChanged: () => void;
}) {
  const saves = game.saves || {};
  if (!saves.sram && !saves.states?.length) return null;
  return (
    <section className="games-sheet__section" aria-label={t("Your saves")}>
      <Text as="h3" style="title-s">
        {t("Your saves")}
      </Text>
      {saves.sram && (
        <Text style="body-s" tone="muted">
          {t("In-game save · {when} · the same on every screen").replace(
            "{when}",
            when(saves.sram.at),
          )}
        </Text>
      )}
      <ul className="games-saves">
        {(saves.states || []).map((s: Obj) => (
          <li key={s.name} className="games-save">
            {s.shot ? (
              <Media src={s.shot} alt="" ratio="4 / 3" />
            ) : (
              <span className="games-save__blank" />
            )}
            <Text style="caption">
              {when(s.at)} · {s.surface === "tv" ? t("on the TV") : t("here")}
            </Text>
            <span className="games-save__actions">
              {s.surface === "browser" && (
                <Button size="s" variant="primary" onClick={() => onContinue(s.name)}>
                  {t("Continue")}
                </Button>
              )}
              <IconButton
                icon="trash"
                size="s"
                label={t("Delete this save")}
                onClick={() =>
                  void api("/games/" + game.id + "/states/" + s.name, "DELETE").then(onChanged)
                }
              />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** After "Play on the TV": what to do on the TV, then what it's doing. */
function TvSheet({ title, onClose }: { title: string; onClose: () => void }) {
  const tv = useData("/games/tv", { interval: 4000 });
  const playing = tv.data?.playing;
  return (
    <Sheet title={t("On the TV")} place="center" onClose={onClose}>
      {playing ? (
        <Status tone="success">
          {t("Playing {title} on the TV. Change game from here any time.").replace(
            "{title}",
            playing.title,
          )}
        </Status>
      ) : (
        <ol className="games-steps">
          <li>
            {t("On the TV, open")} <strong>Moonlight</strong>.
          </li>
          <li>
            {t("Pick this house, then")} <strong>HouseOS</strong>.{" "}
            {t("{title} starts.").replace("{title}", title)}
          </li>
          <li>
            {t(
              "Play with a controller paired to the TV. To leave: L1 + R1 + Start + Select, then Quit.",
            )}
          </li>
        </ol>
      )}
      <Text style="caption" tone="muted">
        {t("First time? Install Moonlight on the TV (free), then pair it once in Games → Set up.")}
      </Text>
    </Sheet>
  );
}

// ---------- adding games ----------

const ROM_TYPES =
  ".nes,.fds,.sfc,.smc,.n64,.z64,.v64,.gb,.gbc,.gba,.nds,.vb,.md,.gen,.smd,.sms,.gg,.32x,.pce,.ngp,.ngc,.ws,.wsc,.a26,.a78,.lnx,.j64,.jag,.col,.zip,.7z,.iso,.bin,.cue,.chd,.pbp,.cso,.gdi,.cdi,.rvz,.gcz,.wbfs";

function AddSheet({ onClose, from = "upload" }: { onClose: () => void; from?: "upload" | "link" }) {
  const [tab, setTab] = useState<"upload" | "link">(from);
  return (
    <Sheet title={t("Add games")} place="side" onClose={onClose}>
      <Segmented
        label={t("How")}
        value={tab}
        onChange={setTab}
        options={[
          { value: "upload", label: t("Upload") },
          { value: "link", label: t("From a link") },
        ]}
      />
      {tab === "upload" ? <Uploads /> : <LinkForm onDone={onClose} />}
      <Text style="caption" tone="muted">
        {t(
          "Only games you own or may share (your cartridges' backups, homebrew). HouseOS never downloads games by itself.",
        )}
      </Text>
    </Sheet>
  );
}

function Uploads() {
  const me = useUser();
  const [rows, setRows] = useState<Obj[]>([]);
  const update = (name: string, change: Obj) =>
    setRows((all) => all.map((r) => (r.name === name ? { ...r, ...change } : r)));
  const upload = async (files: File[]) => {
    setRows((all) => [
      ...files.map((f) => ({ name: f.name, size: f.size, state: "waiting", offset: 0 })),
      ...all,
    ]);
    for (const file of files) {
      try {
        update(file.name, { state: "uploading" });
        const entry = await transferFile(file, {
          actorId: me!.id,
          scope: "media",
          onProgress: (p) => update(file.name, { offset: p.offset }),
        });
        const made = await api("/games/import", "POST", {
          file_id: entry.id,
          version: entry.version,
        });
        update(file.name, {
          state: made.system ? "added" : "pick",
          id: made.id,
          title: made.title,
        });
      } catch (e) {
        const detail = e instanceof ApiError && typeof e.detail === "object" ? e.detail : {};
        update(file.name, {
          state: detail.code === "GAME_DUPLICATE" ? "twin" : "failed",
          id: detail.id,
          error: (e as Error).message,
        });
      }
    }
  };
  const words: Record<string, string> = {
    waiting: "Waiting…",
    uploading: "Uploading…",
    added: "Added",
    pick: "Added: open it to pick its console",
    twin: "Already in the house",
    failed: "Didn't work",
  };
  return (
    <div className="games-add">
      <FileButton
        label={t("Choose game files")}
        multiple
        accept={ROM_TYPES}
        variant="primary"
        onFiles={(f) => void upload(f)}
      />
      <Text style="body-s" tone="muted">
        {t("Keep this page open while they upload. Zipped games are fine.")}
      </Text>
      <List label={t("Uploads")}>
        {rows.map((row) => (
          <ListRow
            key={row.name}
            title={row.title || row.name}
            detail={row.state === "failed" ? row.error : t(words[row.state])}
            meta={
              row.id && ["added", "pick", "twin"].includes(row.state) ? (
                <Button size="s" variant="link" onClick={() => go("/games?game=" + row.id)}>
                  {t("Open")}
                </Button>
              ) : undefined
            }
          >
            {row.state === "uploading" && (
              <Progress label={t("Upload progress")} value={row.offset / (row.size || 1)} />
            )}
          </ListRow>
        ))}
      </List>
    </div>
  );
}

function LinkForm({ onDone }: { onDone: () => void }) {
  const [url, setUrl] = useState(""),
    [error, setError] = useState("");
  return (
    <form
      className="games-add"
      onSubmit={(e) => {
        e.preventDefault();
        void api("/games/link", "POST", { url: url.trim() })
          .then(() => {
            toast(t("Downloading it into the house…"));
            onDone();
          })
          .catch((err) => setError(err.message));
      }}
    >
      <Field
        label={t("A link to a game file")}
        hint={t(
          "The game file itself, not the page it's on: the address ends in .zip, .iso, .chd… Disc games work best as one .iso or .chd.",
        )}
      >
        <Input
          value={url}
          inputMode="url"
          autoComplete="off"
          onChange={(e) => setUrl(e.target.value)}
        />
      </Field>
      <Problem error={error} />
      <Button type="submit" variant="primary" icon="download" disabled={!url.trim()}>
        {t("Add")}
      </Button>
    </form>
  );
}

/** Admin: the folders the house reads games from, in place. */
function Folders() {
  const folders = useData("/games/setup/folders", {
    interval: (d) => (items(d).some((f) => f.scanning) ? 5000 : 0),
  });
  const [path, setPath] = useState(""),
    [error, setError] = useState(""),
    [leaving, setLeaving] = useState<Obj | null>(null);
  const root = folders.data?.import_root || "";
  return (
    <div className="games-add">
      <form
        className="games-add"
        onSubmit={(e) => {
          e.preventDefault();
          setError("");
          void api("/games/setup/folders", "POST", { path: path.trim() })
            .then(() => {
              setPath("");
              void folders.reload();
            })
            .catch((err) => setError(err.message));
        }}
      >
        <Field
          label={t("Your games folder on this computer")}
          hint={t(
            "Inside {root}. Read where it is: nothing is copied or changed. One subfolder per console helps.",
          ).replace("{root}", root)}
        >
          <Input
            value={path}
            placeholder={root + "/Games"}
            onChange={(e) => setPath(e.target.value)}
          />
        </Field>
        <Problem error={error} />
        <Button type="submit" variant="primary" icon="folder-add" disabled={!path.trim()}>
          {t("Use this folder")}
        </Button>
      </form>
      <List label={t("Games folders")}>
        {items(folders.data).map((f) => (
          <ListRow
            key={f.id}
            title={f.path}
            detail={
              f.scanning
                ? t("Looking through it… (starts within a minute)")
                : t("{n} games").replace("{n}", String(f.count ?? 0)) +
                  (f.skipped
                    ? " · " + t("{n} files it couldn't place").replace("{n}", String(f.skipped))
                    : "")
            }
            actions={
              <>
                <IconButton
                  icon="refresh"
                  size="s"
                  label={t("Look again")}
                  onClick={() =>
                    void api("/games/setup/folders/" + f.id + "/scan", "POST").then(folders.reload)
                  }
                />
                <IconButton
                  icon="close"
                  size="s"
                  label={t("Stop using this folder")}
                  onClick={() => setLeaving(f)}
                />
              </>
            }
          />
        ))}
      </List>
      {folders.data?.hidden > 0 && (
        <Button
          variant="quiet"
          icon="show"
          onClick={() => void api("/games/setup/unhide", "POST").then(folders.reload)}
        >
          {t("Show the {n} hidden games again").replace("{n}", String(folders.data?.hidden))}
        </Button>
      )}
      {leaving && (
        <ConfirmSheet
          title={t("Stop using this folder?")}
          confirm={t("Stop using it")}
          onClose={() => setLeaving(null)}
          onConfirm={() => api("/games/setup/folders/" + leaving.id, "DELETE").then(folders.reload)}
        >
          {t(
            "Its games leave the library; the files stay in the folder, and everyone's saves stay.",
          )}
        </ConfirmSheet>
      )}
    </div>
  );
}

// ---------- set up (admin) ----------

/** Admin: the address "Search online" opens, with the game's details filled in. */
function FindLink() {
  const house = useData("/admin/house-settings");
  const [value, setValue] = useState<string | null>(null),
    [error, setError] = useState("");
  const current = value ?? house.data?.games_find_url ?? "";
  return (
    <form
      className="games-add"
      onSubmit={(e) => {
        e.preventDefault();
        setError("");
        if (current.trim() && !/^https?:\/\/\S+/i.test(current.trim()))
          return setError(t("Use a web address that starts with https://"));
        void api("/admin/house-settings", "PUT", { games_find_url: current.trim() })
          .then(() => toast(t("Saved.")))
          .catch((err) => setError(err.message));
      }}
    >
      <Field
        label={t("Find link")}
        hint={t(
          "Opened in a new tab for a game that isn't in the house, with the game's name, console, region, file name and checksum filled in (see GAMES.md). A web search by default; empty hides the button. Everyone here sees it: no passwords or keys.",
        )}
      >
        <Input
          value={current}
          inputMode="url"
          autoComplete="off"
          onChange={(e) => setValue(e.target.value)}
        />
      </Field>
      <Problem error={error} />
      <Button type="submit" variant="primary" disabled={value === null}>
        {t("Save")}
      </Button>
    </form>
  );
}

function SetupSheet({ tv, onClose }: { tv?: Obj | null; onClose: () => void }) {
  return (
    <Sheet title={t("Set up games")} place="side" wide onClose={onClose}>
      <section className="games-sheet__section">
        <Text as="h3" style="title-s">
          {t("Play on the TV")}
        </Text>
        <TvSetup tv={tv} />
      </section>
      <section className="games-sheet__section">
        <Text as="h3" style="title-s">
          {t("Search online")}
        </Text>
        <FindLink />
      </section>
      <section className="games-sheet__section">
        <Text as="h3" style="title-s">
          {t("Games folders")}
        </Text>
        <Folders />
      </section>
      <section className="games-sheet__section">
        <Text as="h3" style="title-s">
          {t("Console BIOS files")}
        </Text>
        <Bios />
      </section>
    </Sheet>
  );
}

function TvSetup({ tv }: { tv?: Obj | null }) {
  const devices = useData(tv?.ready ? "/games/tv/devices" : null);
  const [pin, setPin] = useState(""),
    [name, setName] = useState(t("Living-room TV")),
    [error, setError] = useState("");
  if (!tv?.ready)
    return (
      <Notice
        tone="info"
        title={tv?.native === false ? t("Not in this install") : t("Not set up yet")}
      >
        {tv?.native === false
          ? t(
              "TV play needs HouseOS installed directly on Linux (it uses this computer's screen and graphics card). Playing here, in any browser, works everywhere.",
            )
          : t(
              "Run docs/native/setup_games_host.py once on this computer (docs/GAMES.md). Playing here, in any browser, already works.",
            )}
      </Notice>
    );
  return (
    <div className="games-add">
      <Text style="body-s" tone="muted">
        {t(
          "Install Moonlight (free) on the TV, a phone or a laptop and open it: it shows a 4-digit code the first time. Type it here.",
        )}
      </Text>
      <form
        className="games-pair"
        onSubmit={(e) => {
          e.preventDefault();
          setError("");
          void api("/games/tv/pair", "POST", { pin, name })
            .then(() => {
              toast(t("Paired."));
              setPin("");
              void devices.reload();
            })
            .catch((err) => setError(err.message));
        }}
      >
        <Field label={t("Code")}>
          <Input
            value={pin}
            inputMode="numeric"
            maxLength={4}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          />
        </Field>
        <Field label={t("Name")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Button type="submit" variant="primary" disabled={pin.length !== 4}>
          {t("Pair")}
        </Button>
      </form>
      <Problem error={error || devices.error} />
      <List label={t("Paired screens")}>
        {items(devices.data).map((d) => (
          <ListRow
            key={d.id}
            title={d.name}
            actions={
              <IconButton
                icon="close"
                size="s"
                label={t("Unpair") + " · " + d.name}
                onClick={() => void api("/games/tv/devices/" + d.id, "DELETE").then(devices.reload)}
              />
            }
          />
        ))}
      </List>
    </div>
  );
}

function Bios() {
  const bios = useData("/games/bios");
  const put = async (name: string, file: File) => {
    await api("/games/bios/" + name, "PUT", file).catch(() => toast(t("That file didn't work.")));
    void bios.reload();
  };
  return (
    <>
      <Text style="body-s" tone="muted">
        {t(
          "Some consoles need a small file from the console itself. Bring your own; HouseOS never downloads them.",
        )}
      </Text>
      <List label={t("Console BIOS files")}>
        {items(bios.data).flatMap((s) =>
          s.files.map((f: Obj) => (
            <ListRow
              key={f.name}
              title={s.name + " · " + f.name}
              detail={f.present ? t("Here") : s.needed ? t("Needed to play") : t("Optional")}
              actions={
                <FileButton
                  label={f.present ? t("Replace") : t("Add")}
                  size="s"
                  variant="quiet"
                  onFiles={([file]) => void put(f.name, file)}
                />
              }
            />
          )),
        )}
      </List>
    </>
  );
}

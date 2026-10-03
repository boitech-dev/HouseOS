import { t } from "./i18n";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  api,
  useData,
  usePages,
  useUser,
  items,
  idempotency,
  bytes,
  pretty,
  time,
  type Obj,
} from "./api";
import {
  Button,
  Field,
  Hint,
  Icon,
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
  Panel,
  Problem,
  Progress,
  SearchInput,
  Segmented,
  Select,
  Sheet,
  Shelf,
  State,
  Text,
  Chip,
  ChipGroup,
  toast,
  type IconName,
} from "./design";
import { useReveal } from "./design/motion";
import { go } from "./nav";
import { JoinCode } from "./guest_code";
import { clock } from "./api";
import { DownloadProgress, Screens, SubtitlePicker, downloadActive, trackLanguage } from "./cinema";
import { CinemaUpload } from "./cinema_upload";
import { SharedWatchlist, ShareWatchlist } from "./shared_watchlist";
import { WebPlace } from "./watch_web";
import {
  ActiveFilters,
  Collections,
  DiscoverResults,
  EverythingRow,
  SeeAll,
  ForYouRow,
  FilterBar,
  FilterPanel,
  discoverPath,
  filtering,
  noFilters,
  POSTER,
  type Filters,
} from "./watch_explore";
import { OpenInPlayer } from "./player";
import "./watch.css";

const errorText = (e: unknown) => (e as Error).message;
/** "1:13:36", "73:36" or "4416" → seconds; null when it is not a time. */
export function parseTime(text: string): number | null {
  const parts = text.trim().split(":");
  if (!parts.length || parts.length > 3 || parts.some((p) => !/^\d{1,5}$/.test(p))) return null;
  return parts.reduce((total, part) => total * 60 + Number(part), 0);
}

/** A poster in a shelf or a grid: opens the title. `bar` is how far you got, in percent. */
function Poster({
  title,
  onOpen,
  meta,
  bar,
}: {
  title: Obj;
  onOpen: () => void;
  meta?: ReactNode;
  bar?: number;
}) {
  return (
    <li className="watch-poster">
      <MediaCard
        media={
          <>
            <Media src={title.poster || null} alt="" />
            {bar !== undefined && (
              <span className="watch-poster__bar" aria-hidden="true">
                <Progress label={t("Watched")} value={bar / 100} />
              </span>
            )}
          </>
        }
        title={title.series_title || title.title}
        meta={meta}
        onOpen={onOpen}
      />
    </li>
  );
}

// ---------- the page ----------
type Drawer =
  | ""
  | "sources"
  | "jellyfin"
  | "screens"
  | "downloads"
  | "queue"
  | "shared"
  | "cloud"
  | "history"
  | "guest";

/** The screening room: search, what to continue, your list, and the whole catalogue. What plays
 *  on a screen lives in the Now bar; where films come from lives in the Sources sheet. */
type OpenShelf = { label: string; path: string } | null;
/** The row open as a page (?shelf=<its list>&label=<its name>), or none. */
function readShelf(): OpenShelf {
  const params = new URLSearchParams(location.search);
  const path = params.get("shelf");
  return path?.startsWith("/cinema/") ? { path, label: params.get("label") || "" } : null;
}
const shelfUrl = (shelf: NonNullable<OpenShelf>) =>
  "/watch?" + new URLSearchParams({ shelf: shelf.path, label: shelf.label });

export function Watch() {
  const params = new URLSearchParams(location.search);
  // ?kind=web&text=… : a link sent from Capture (a phone's Share) to play on the TV.
  const [shared] = useState(() => (params.get("kind") === "web" ? params.get("text") || "" : ""));
  const [kind, setKind] = useState(params.get("kind") === "web" ? "web" : "movie"),
    [text, setText] = useState(""),
    [query, setQuery] = useState(""),
    [open, setOpen] = useState<Obj | null>(
      params.get("title")
        ? { id: params.get("title") }
        : params.get("workflow")
          ? { workflow: params.get("workflow") }
          : null,
    ),
    [drawer, setDrawer] = useState<Drawer>(""),
    [filters, setFilters] = useState<Filters>(noFilters),
    [showFilters, setShowFilters] = useState(false),
    [own, setOwn] = useState(0),
    [cloud, setCloud] = useState<Obj | null>(null),
    [shelf, setShelf] = useState(readShelf);
  // Links into Watch while already here ("Open in Watch", activity) reopen the right title.
  useEffect(() => {
    const follow = () => {
      const next = new URLSearchParams(location.search);
      if (next.get("title")) setOpen({ id: next.get("title") });
      else if (next.get("workflow")) setOpen({ workflow: next.get("workflow") });
      setShelf(readShelf()); // Back from a row's page
    };
    addEventListener("popstate", follow);
    return () => removeEventListener("popstate", follow);
  }, []);
  const shelves = useData("/cinema/shelves");
  const search = useData(
    query ? "/cinema/search?kind=" + kind + "&q=" + encodeURIComponent(query) : null,
  );
  const openTitle = (entry: Obj) => {
    setOpen(entry);
    history.replaceState(null, "", "/watch?title=" + encodeURIComponent(entry.id));
  };
  const poster = (title: Obj) => (
    <Poster key={title.id} title={title} meta={title.year} onOpen={() => openTitle(title)} />
  );
  const close = () => {
    setOpen(null);
    history.replaceState(history.state, "", shelf ? shelfUrl(shelf) : "/watch");
  };
  // A row's "See all" is a page of its own: the browser's Back returns to the rows.
  const seeAll = (label: string, path: string) => {
    history.pushState({ shelf: true }, "", shelfUrl({ label, path }));
    setShelf({ label, path });
    scrollTo({ top: 0 });
  };
  const leaveShelf = () => {
    if (history.state?.shelf) history.back();
    else {
      history.replaceState(null, "", "/watch");
      setShelf(null);
    }
  };
  // "More filters" opens below the fold on a phone: bring it into view.
  const filtersRef = useReveal<HTMLDivElement>(showFilters);
  const data = shelves.data || {};
  const me = useUser();
  const lists: [Drawer, IconName, string][] = [
    ["queue", "list-video", "My queue"],
    ["shared", "people", "House list"],
    ["history", "history", "History"],
    // A QR code for a guest to use the TV (and the music) for a few hours, without an account.
    ...(me?.role === "admin" || me?.permissions?.includes("invites.create")
      ? ([["guest", "party", "Guest code"]] as [Drawer, IconName, string][])
      : []),
  ];
  const opened = (next: (entry: Obj) => void) => (entry: Obj) => {
    setDrawer("");
    next(entry);
  };
  return (
    <Page width="wide">
      <PageHeader
        room="watch"
        title={t("Watch")}
        actions={
          <>
            {me?.permissions?.includes("games.play") || me?.role === "admin" ? (
              <Button icon="gamepad" variant="quiet" onClick={() => go("/games")}>
                {t("Games")}
              </Button>
            ) : null}
            <Button icon="storage" onClick={() => setDrawer("sources")}>
              {t("Sources")}
            </Button>
          </>
        }
        hint={
          <Hint id="watch">
            {t(
              "Pick a film or a show: I choose the best version (original audio, subtitles, quality). You only confirm to send it to the TV.",
            )}
          </Hint>
        }
      />
      <form
        className="watch-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(text.trim());
        }}
      >
        <Segmented
          label={t("Kind")}
          value={kind}
          onChange={setKind}
          options={[
            { value: "movie", label: t("Films") },
            { value: "series", label: t("Series") },
            { value: "anime", label: t("Anime") },
            { value: "web", label: t("Web") },
          ]}
        />
        {kind !== "web" && (
          <div className="watch-search__field">
            <SearchInput
              label={t("Search films and series")}
              placeholder={t("A film, a series, an actor…")}
              value={text}
              onChange={(value) => {
                setText(value);
                if (!value) setQuery("");
              }}
            />
            <Button type="submit" variant="primary">
              {t("Search")}
            </Button>
          </div>
        )}
      </form>
      {kind === "web" ? (
        <WebPlace initial={shared} />
      ) : (
        <>
          <div className="watch-tools">
            <FilterBar
              kind={kind}
              value={filters}
              onChange={setFilters}
              open={showFilters}
              onMore={() => setShowFilters(!showFilters)}
            />
            <nav className="watch-lists" aria-label={t("Your lists")}>
              {lists.map(([key, icon, label]) => (
                <Button
                  key={key}
                  size="s"
                  variant="quiet"
                  icon={icon}
                  onClick={() => setDrawer(key)}
                >
                  {t(label)}
                </Button>
              ))}
            </nav>
          </div>
          {showFilters && (
            <div ref={filtersRef} className="watch-filters-slot">
              <FilterPanel kind={kind} value={filters} onChange={setFilters} />
            </div>
          )}
          <ActiveFilters kind={kind} value={filters} onChange={setFilters} />
          {cloud && (
            <Notice
              title={t("Debrid file:") + " " + cloud.title}
              action={
                <Button size="s" variant="quiet" onClick={() => setCloud(null)}>
                  {t("Cancel")}
                </Button>
              }
            >
              {t("Open its film or episode to play exactly this file.")}
            </Notice>
          )}
          {shelf ? (
            <SeeAll label={shelf.label} path={shelf.path} poster={poster} onBack={leaveShelf} />
          ) : query ? (
            <SearchResults
              kind={kind}
              query={query}
              filters={filters}
              search={search}
              poster={poster}
              onKeep={(more) => {
                // A person or a year joins the filters already chosen: each one narrows the list.
                setFilters((f) => ({
                  ...f,
                  ...more,
                  person: [...new Set([...(f.person || []), ...(more.person || [])])],
                }));
                setText("");
                setQuery("");
              }}
            />
          ) : filtering(filters) ? (
            <DiscoverResults path={discoverPath(kind, "", filters)} poster={poster} />
          ) : (
            <>
              <Problem error={shelves.error} onRetry={shelves.reload} />
              <PickUp data={data} kind={kind} onOpen={openTitle} onOwn={setOwn} />
              <EverythingRow kind={kind} poster={poster} onSeeAll={seeAll} />
              {own >= PICK_UP && <ForYouRow kind={kind} poster={poster} />}
              <Collections kind={kind} poster={poster} onSeeAll={seeAll} />
            </>
          )}
        </>
      )}
      {open && (
        <TitleSheet
          key={open.id || open.workflow}
          entry={open}
          onOpen={openTitle}
          cloudId={cloud?.id}
          onClose={close}
          onLaunched={(text) => {
            close();
            setCloud(null);
            toast(text);
          }}
          onPerson={(name) => {
            close();
            setFilters({ person: [name] });
            scrollTo({ top: 0 });
          }}
        />
      )}
      {drawer === "sources" && (
        <SourcesSheet
          sources={data.sources || {}}
          saved={data.saved?.length || 0}
          onPick={(next) => (next === "disk" ? go("/files?scope=movies") : setDrawer(next))}
          onClose={() => setDrawer("")}
        />
      )}
      {drawer === "screens" && (
        <Sheet title={t("Screens")} place="side" onClose={() => setDrawer("")}>
          <Screens />
        </Sheet>
      )}
      {drawer === "jellyfin" && (
        <Sheet title="Jellyfin" place="side" wide onClose={() => setDrawer("")}>
          <JellyfinShelf kind={kind} onOpen={opened(openTitle)} />
        </Sheet>
      )}
      {drawer === "downloads" && <DownloadsSheet onClose={() => setDrawer("")} />}
      {drawer === "guest" && (
        <Sheet title={t("A guest at the TV")} place="center" onClose={() => setDrawer("")}>
          <JoinCode tv />
        </Sheet>
      )}
      {drawer === "queue" && (
        <QueueSheet onClose={() => setDrawer("")} onOpen={opened(openTitle)} />
      )}
      {drawer === "shared" && (
        <Sheet title={t("House list")} place="side" onClose={() => setDrawer("")}>
          <SharedWatchlist onOpen={(id) => opened(openTitle)({ id })} />
        </Sheet>
      )}
      {drawer === "history" && (
        <HistorySheet onClose={() => setDrawer("")} onOpen={opened(openTitle)} />
      )}
      {drawer === "cloud" && (
        <CloudSheet
          onClose={() => setDrawer("")}
          onPick={opened((entry) => {
            setCloud(entry);
            setText(
              String(entry.title)
                .replace(/[._]/g, " ")
                .split(/\s(?:19|20)\d\d/)[0],
            );
          })}
        />
      )}
    </Page>
  );
}

/** Where films come from: the screens, the house disk and the services the house uses. */
function SourcesSheet({
  sources,
  saved,
  onPick,
  onClose,
}: {
  sources: Obj;
  saved: number;
  onPick: (drawer: Drawer | "disk") => void;
  onClose: () => void;
}) {
  type Row = [Drawer | "disk", IconName, string, string];
  const rows: Row[] = [
    ["screens", "tv", "Screens", "The TVs, what they show, and their controls."],
    ["disk", "storage", "House disk", "Films and series saved in the house."],
    ...(sources.jellyfin
      ? [["jellyfin", "archive", "Jellyfin", "The whole Jellyfin library."] as Row]
      : []),
    ["downloads", "download", "Copies at home", "Copies being saved, and uploads."],
    // Files once opened through the debrid account: not on the house disk.
    ...(sources.real_debrid !== false
      ? [["cloud", "cloud", "Debrid history", "Files your debrid account opened before."] as Row]
      : []),
  ];
  return (
    <Sheet title={t("Sources")} place="side" onClose={onClose}>
      <List label={t("Sources")}>
        {rows.map(([key, icon, label, detail]) => (
          <ListRow
            key={key}
            leading={<Icon name={icon} />}
            title={t(label)}
            detail={t(detail)}
            meta={
              key === "disk" && saved > 0 ? <span className="tabular">{saved}</span> : undefined
            }
            onOpen={() => onPick(key)}
          />
        ))}
      </List>
    </Sheet>
  );
}

const fold = (text: string) =>
  text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();

/** What a search box's words mean as a filter: a person's exact name, a year (1999) or a decade
 *  (1990s). */
function asFilter(query: string, people: string[]): Filters | null {
  const person = people.find((name) => fold(name) === fold(query));
  if (person) return { person: [person] };
  const year = query.trim().match(/^((?:19|20)\d)(\d|0s)$/i);
  if (!year) return null;
  const from = Number(year[1] + (year[2].length === 1 ? year[2] : "0"));
  return { year_from: from, year_to: year[2].length === 1 ? from : from + 9 };
}

/** A search. A person's name, a year or a decade shows the catalogue for it, together with the
 *  filters already chosen (two people: the films with both), with the titles containing those
 *  words one tap away. Close names are offered as chips that join the filters. */
function SearchResults({
  kind,
  query,
  filters,
  search,
  poster,
  onKeep,
}: {
  kind: string;
  query: string;
  filters: Filters;
  search: ReturnType<typeof useData<Obj>>;
  poster: (title: Obj) => ReactNode;
  onKeep: (more: Filters) => void;
}) {
  const names = useData("/cinema/explore/people?kind=" + kind + "&q=" + encodeURIComponent(query));
  const list: string[] = (names.data?.items || []).slice(0, 4);
  const meant = asFilter(query, list);
  const [titles, setTitles] = useState(false);
  useEffect(() => setTitles(false), [query]);
  const all = (name: string) =>
    t(
      { anime: "Everything by {name}", series: "Series with {name}" }[kind] || "Films with {name}",
    ).replace("{name}", name);
  const combined: Filters = meant
    ? {
        ...filters,
        ...meant,
        person: [...new Set([...(filters.person || []), ...(meant.person || [])])],
      }
    : filters;
  const heading = [
    combined.person?.length ? all(combined.person.join(" & ")) : "",
    meant?.year_from && !meant.person
      ? meant.year_from === meant.year_to
        ? String(meant.year_from)
        : `${meant.year_from}–${meant.year_to}`
      : "",
  ]
    .filter(Boolean)
    .join(" · ");
  if (meant && !titles)
    return (
      <section className="watch-stack" aria-label={t("Search results")}>
        <div className="watch-seeall__head">
          <Text as="h2" style="title-m">
            {heading}
          </Text>
          <Button size="s" icon="add" onClick={() => onKeep(meant)}>
            {t("Keep as a filter")}
          </Button>
          <Button size="s" variant="quiet" onClick={() => setTitles(true)}>
            {t("Titles with “{q}” in the name instead").replace("{q}", query)}
          </Button>
        </div>
        <DiscoverResults path={discoverPath(kind, "", combined)} poster={poster} />
      </section>
    );
  return (
    <section className="watch-stack" aria-label={t("Search results")}>
      {list.length > 0 && (
        <>
          <Text style="label" tone="muted">
            {t("People: see all their work")}
          </Text>
          <ChipGroup label={t("People: see all their work")}>
            {list.map((name) => (
              <Chip
                key={name}
                kind="filter"
                icon="person"
                onToggle={() => onKeep({ person: [name] })}
              >
                {all(name)}
              </Chip>
            ))}
          </ChipGroup>
          <Text style="label" tone="muted">
            {t("Titles with “{q}” in the name").replace("{q}", query)}
          </Text>
        </>
      )}
      {/* With filters on, titles are searched inside them. */}
      {filtering(filters) ? (
        <DiscoverResults path={discoverPath(kind, query, filters)} poster={poster} />
      ) : (
        <>
          <Problem error={search.error} onRetry={search.reload} />
          {search.loading && !search.data && <State kind="loading" />}
          <ul className="watch-grid" aria-label={t("Search results")}>
            {items(search.data).map(poster)}
          </ul>
          {search.data && !items(search.data).length && (
            <State kind="empty" title={t("Nothing by that name")}>
              {t("Try another spelling or kind.")}
            </State>
          )}
        </>
      )}
    </section>
  );
}

/** The id a saved file carries in its name ("Title-<uuid>.mkv"): never shown. */
const FILE_ID = /[-_ .][0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]+/i;
/** At least this many cards in Your picks: recommendations fill the row until your own replace them. */
const PICK_UP = 9;
/** One compact row for what is yours in this tab: resume, next episode, saved on the house disk,
 *  the Jellyfin library and your list, each tagged; recommendations fill it up to nine. */
function PickUp({
  data,
  kind,
  onOpen,
  onOwn,
}: {
  data: Obj;
  kind: string;
  onOpen: (entry: Obj) => void;
  /** How many cards are the resident's own (the "For you" row shows once they fill the row). */
  onOwn: (count: number) => void;
}) {
  const library = useData("/cinema/library?kind=" + (kind === "anime" ? "series" : kind));
  const cards: { key: string; card: Obj; open: Obj; tag: string; bar?: number }[] = [];
  const seen = new Set<string>();
  // The same film can come twice (saved on the disk, and Jellyfin indexing that same file under
  // its file name, "Title-<id>"): one card per title, the first reason wins.
  const name = (card: Obj) =>
    String(card.series_title || card.title || "")
      .replace(FILE_ID, "")
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim()
      .toLowerCase();
  const add = (key: string, card: Obj, open: Obj, tag: string, bar?: number) => {
    if (card.tab && card.tab !== kind) return; // films in Films, series in Series, anime in Anime
    if (seen.has(key) || (name(card) && seen.has("title:" + name(card)))) return;
    seen.add(key);
    if (name(card)) seen.add("title:" + name(card));
    cards.push({ key, card, open, tag, bar });
  };
  for (const card of data.continue || [])
    add(
      card.parent_id || card.media_id,
      card,
      {
        id: card.action === "next" ? card.media_id : card.parent_id || card.media_id,
        season: card.season,
        episode: card.episode,
      },
      card.action === "next"
        ? `${t("Next")} · S${card.season}E${card.episode}`
        : (card.season != null ? `S${card.season}E${card.episode} · ` : "") + clock(card.position),
      card.action === "next"
        ? undefined
        : Math.min(100, (100 * card.position) / (card.duration || 1)),
    );
  for (const card of data.saved || [])
    add(card.media_id, card, { id: card.media_id }, t("On the disk"));
  for (const title of items(library.data)) add(title.id, title, title, "Jellyfin");
  for (const card of data.watchlist || [])
    add(
      card.parent_id || card.media_id,
      card,
      { id: card.parent_id || card.media_id },
      t("My list"),
    );
  // Then what you watched lately (finished films too), before any suggestion.
  for (const card of data.recent || [])
    if (cards.length < PICK_UP)
      add(
        card.parent_id || card.media_id,
        card,
        { id: card.parent_id || card.media_id },
        t("Watched"),
      );
  const own = cards.length;
  useEffect(() => onOwn(own), [own]);
  const forYou = useData(own < PICK_UP ? "/cinema/for-you?kind=" + kind : null);
  for (const title of items(forYou.data))
    if (cards.length < PICK_UP) add(title.id, title, title, t("For you"));
  const popular = useData(
    own < PICK_UP && forYou.data && cards.length < PICK_UP ? "/cinema/explore?kind=" + kind : null,
  );
  for (const title of items(popular.data))
    if (cards.length < PICK_UP) add(title.id, title, title, t("Popular"));
  if (!cards.length) return null;
  return (
    <Shelf title={t("Your picks")} item={POSTER}>
      {cards.map(({ key, card, open, tag, bar }) => (
        <Poster key={key} title={card} meta={tag} bar={bar} onOpen={() => onOpen(open)} />
      ))}
    </Shelf>
  );
}

/** The Jellyfin library, whole, in a sheet (opened from Sources). */
function JellyfinShelf({ kind, onOpen }: { kind: string; onOpen: (entry: Obj) => void }) {
  const pages = usePages("/cinema/library?kind=" + (kind === "anime" ? "series" : kind), (data) =>
    data.next_offset ? "offset=" + data.next_offset : null,
  );
  return (
    <div className="watch-stack">
      <Problem error={pages.error} />
      <ul className="watch-grid" aria-label="Jellyfin">
        {pages.items.map((title) => (
          <Poster key={title.id} title={title} onOpen={() => onOpen(title)} />
        ))}
      </ul>
      {!pages.loading && !pages.items.length && (
        <State kind="empty" title={t("Nothing in the Jellyfin library for this kind yet.")} />
      )}
      <MoreBelow pages={pages} />
    </div>
  );
}

// ---------- one title ----------
function TitleSheet({
  entry,
  cloudId,
  onClose,
  onLaunched,
  onPerson,
  onOpen,
}: {
  entry: Obj;
  cloudId?: string;
  onClose: () => void;
  onLaunched: (notice: string) => void;
  /** More by this director, actor or studio. */
  onPerson?: (name: string) => void;
  /** Opens another title (from "More like this"). */
  onOpen?: (title: Obj) => void;
}) {
  const [title, setTitle] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [season, setSeason] = useState<number | undefined>(entry.season),
    [episode, setEpisode] = useState<number | undefined>(entry.episode),
    [workflowId, setWorkflowId] = useState<string | undefined>(entry.workflow),
    [listed, setListed] = useState<boolean | null>(null),
    [sharing, setSharing] = useState(false);
  useEffect(() => {
    let alive = true;
    (async () => {
      let id = entry.id;
      if (!id && entry.workflow) id = (await api("/cinema/workflows/" + entry.workflow)).media_id;
      let found = await api("/cinema/titles/" + id);
      if (found.parent_id) {
        setSeason(found.season);
        setEpisode(found.episode);
        found = await api("/cinema/titles/" + found.parent_id);
      }
      if (!alive) return;
      setTitle(found);
      setListed(!!found.progress?.watchlist);
    })().catch((e) => alive && setError(errorText(e)));
    return () => {
      alive = false;
    };
  }, [entry.id, entry.workflow]);
  const episodes: Obj[] = (title?.episodes || []).filter(
    (e: Obj) => Number.isInteger(e.season) && Number.isInteger(e.episode),
  );
  const series = title?.kind === "series" || episodes.length > 0;
  // A series opens on the episode to watch next: the one in progress, else after the last seen.
  useEffect(() => {
    if (!series || episode != null || !episodes.length) return;
    const regular = episodes.filter((e) => e.season > 0);
    const list = regular.length ? regular : episodes;
    const started = list.filter((e) => e.progress?.position > 0 || e.progress?.watched);
    const last = started[started.length - 1];
    const pick =
      last &&
      !last.progress?.watched &&
      (last.progress?.position || 0) < (last.progress?.duration || 1) * 0.92
        ? last
        : last
          ? list[list.indexOf(last) + 1] || last
          : list[0];
    setSeason(pick.season);
    setEpisode(pick.episode);
  }, [series, episodes.length]);
  const seasons = [...new Set(episodes.map((e) => e.season))].sort((a, b) => a - b);
  const chosen = episodes.find((e) => e.season === season && e.episode === episode);
  const progress = series ? chosen?.progress || {} : title?.progress || {};
  const ready = !!title && (!series || (season != null && episode != null));
  const toggleList = async () => {
    try {
      await api("/cinema/state/" + title!.id, "PUT", { watchlist: !listed });
      setListed(!listed);
    } catch (e) {
      setError(errorText(e));
    }
  };
  const people: string[] = title
    ? [...(title.director || []), ...(title.studios || []), ...(title.cast || []).slice(0, 4)]
    : [];
  return (
    <Sheet title={title?.title || t("Loading…")} place="side" wide onClose={onClose}>
      <Problem error={error} />
      {!title && !error && <State kind="loading" />}
      {title && (
        <div className="watch-title">
          <div className="watch-title__intro">
            <Media
              src={title.poster}
              alt={t("Poster") + " · " + title.title}
              className="watch-title__poster"
            />
            <Text tone="muted" className="watch-title__meta">
              {[
                title.year,
                (title.genres || [])
                  .slice(0, 3)
                  .map((g: string) => t(g))
                  .join(", "),
              ]
                .filter(Boolean)
                .join(" · ")}
              {title.rating && (
                <span className="watch-title__rating">
                  <Icon name="star" size="s" />
                  {title.rating}
                </span>
              )}
            </Text>
            {title.description && <Text className="watch-title__about">{title.description}</Text>}
          </div>
          <div className="watch-title__actions">
            <Button icon="bookmark" pressed={!!listed} onClick={() => void toggleList()}>
              {t(listed ? "In my list" : "Add to my list")}
            </Button>
            <Button icon="people" aria-expanded={sharing} onClick={() => setSharing(!sharing)}>
              {t("Suggest to the house")}
            </Button>
            <QueueButton title={title} season={season} episode={episode} />
          </div>
          {sharing && <ShareWatchlist titleId={title.id} />}
          {onPerson && people.length > 0 && (
            <ChipGroup label={t("More with")}>
              {people.map((name) => (
                <Chip key={name} kind="filter" icon="person" onToggle={() => onPerson(name)}>
                  {name}
                </Chip>
              ))}
            </ChipGroup>
          )}
          {series && (
            <section className="watch-stack" aria-label={t("Episodes")}>
              <Field label={t("Season")}>
                <Select
                  value={season ?? ""}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setSeason(next);
                    setEpisode(episodes.find((x) => x.season === next)?.episode);
                    setWorkflowId(undefined);
                  }}
                >
                  {seasons.map((s) => (
                    <option key={s} value={s}>
                      {s === 0 ? t("Specials") : s}
                    </option>
                  ))}
                </Select>
              </Field>
              <List label={t("Episodes")}>
                {episodes
                  .filter((e) => e.season === season)
                  .map((e) => (
                    <ListRow
                      key={e.episode}
                      leading={<span className="tabular watch-episode__number">{e.episode}</span>}
                      title={e.title || t("Episode") + " " + e.episode}
                      meta={
                        e.progress?.watched
                          ? t("Seen")
                          : e.progress?.position > 0
                            ? clock(e.progress.position)
                            : undefined
                      }
                      selected={e.episode === episode}
                      onOpen={() => {
                        setEpisode(e.episode);
                        setWorkflowId(undefined);
                      }}
                    />
                  ))}
              </List>
            </section>
          )}
          {ready && (
            <Tonight
              key={title.id + ":" + season + ":" + episode + ":" + (cloudId || "")}
              title={title}
              cloudId={cloudId}
              season={series ? season : undefined}
              episode={series ? episode : undefined}
              resumeAt={!progress.watched && progress.position > 30 ? progress.position : 0}
              workflowId={workflowId}
              onWorkflow={setWorkflowId}
              onLaunched={onLaunched}
            />
          )}
          {onOpen && <MoreLikeThis titleId={title.id} onOpen={onOpen} />}
        </div>
      )}
    </Sheet>
  );
}

/** Same franchise (anime) and "More like this": MyAnimeList members' picks for anime, the same
 *  director, cast and themes for films and series. */
function MoreLikeThis({ titleId, onOpen }: { titleId: string; onOpen: (title: Obj) => void }) {
  const similar = useData("/cinema/titles/" + titleId + "/similar");
  const poster = (title: Obj) => (
    <Poster key={title.id} title={title} meta={title.year} onOpen={() => onOpen(title)} />
  );
  const data = similar.data;
  if (!data) return null;
  return (
    <>
      {data.franchise?.length > 0 && (
        <Shelf title={t("Same series")} item="112px">
          {data.franchise.map(poster)}
        </Shelf>
      )}
      {data.items?.length > 0 && (
        <Shelf title={t("More like this")} item="112px">
          {data.items.map(poster)}
        </Shelf>
      )}
      {data.items?.length > 0 && (
        <Text style="body-s" tone="muted">
          {t(
            data.source === "myanimelist"
              ? "Recommended by MyAnimeList members."
              : "Chosen by shared themes, genres and people.",
          )}
        </Text>
      )}
    </>
  );
}

function QueueButton({
  title,
  season,
  episode,
}: {
  title: Obj;
  season?: number;
  episode?: number;
}) {
  const [queued, setQueued] = useState(false),
    [busy, setBusy] = useState(false);
  return (
    <Button
      icon="list-video"
      busy={busy}
      disabled={queued}
      onClick={async () => {
        setBusy(true);
        try {
          await api("/cinema/queue", "POST", {
            media_id: title.id,
            season,
            episode,
            idempotency_key: idempotency(),
          });
          setQueued(true);
        } catch (e) {
          toast(errorText(e), { tone: "danger" });
        } finally {
          setBusy(false);
        }
      }}
    >
      {queued ? t("In my queue") : t("Watch later")}
    </Button>
  );
}

// ---------- tonight: the suggestion, reviewed in one glance, played in one tap ----------
type Pick = "version" | "audio" | "subtitles" | "screen" | "start" | "";

/** Why versions were set aside, in words (codes from the server's checks). */
const SETBACKS: [string, string][] = [
  ["VIDEO_MODE_UNSUPPORTED", "their picture format doesn't suit your TV"],
  ["QUALITY_MISMATCH", "their resolution is above your limit"],
  ["AUDIO_INCOMPATIBLE", "their sound can't be played"],
  ["SUBTITLE", "their subtitles would need converting"],
  ["TORRENT_PLAYER", "the torrent player isn't running on this computer"],
  ["NO_PEERS", "nobody is sharing them right now"],
  ["DEBRID", "they aren't ready on the debrid service"],
  ["NOT_READY", "they aren't ready on the debrid service"],
  ["PROBE", "they didn't answer in time"],
];
function setbackText(codes: string[]) {
  const said = codes.map(
    (code) => SETBACKS.find(([key]) => code.includes(key))?.[1] || "they didn't pass the check",
  );
  return [...new Set(said)].map((text) => t(text)).join(", ") + ".";
}

/** While versions are checked: what is happening, why it takes a moment, and that it moves. */
function Checking({ progress }: { progress?: Obj }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="watch-stack" role="status">
      <Progress
        busy={!progress}
        value={progress ? progress.checked / Math.max(1, progress.total) : 0}
        steps={progress?.total ? progress.total * 4 : 12}
        label={t("Checking versions")}
      />
      <p className="watch-checking">
        {progress
          ? t("Checking versions for your TV… {n}/{total}")
              .replace("{n}", String(progress.checked))
              .replace("{total}", String(progress.total))
          : t("Looking for versions…")}
        <small className="tabular"> {seconds}s</small>
      </p>
      {progress && progress.round > 1 && progress.setbacks?.length > 0 && (
        <Text style="body-s" tone="muted">
          {t("The first ones didn't fit:")} {setbackText(progress.setbacks)}{" "}
          {t("Trying the next best.")}
        </Text>
      )}
      {seconds >= 12 && (
        <Text style="body-s" tone="muted">
          {t(
            "Each check reads a few megabytes to be sure it plays here; nothing is downloaded. It can take up to a minute.",
          )}
        </Text>
      )}
    </div>
  );
}

/** One choice in an options sheet (a version, a track, a screen). */
function Choice({
  title,
  detail,
  chosen,
  onPick,
}: {
  title: ReactNode;
  detail?: ReactNode;
  chosen: boolean;
  onPick: () => void;
}) {
  return (
    <ListRow
      title={title}
      detail={detail}
      selected={chosen}
      meta={chosen ? <Icon name="check" size="s" /> : undefined}
      onOpen={onPick}
    />
  );
}

function Tonight({
  title,
  cloudId,
  season,
  episode,
  resumeAt,
  workflowId,
  onWorkflow,
  onLaunched,
}: {
  title: Obj;
  cloudId?: string;
  season?: number;
  episode?: number;
  resumeAt: number;
  workflowId?: string;
  onWorkflow: (id: string) => void;
  onLaunched: (notice: string) => void;
}) {
  const user = useUser();
  const devices = useData("/cinema/devices"),
    preferences = useData("/cinema/preferences");
  const [operation, setOperation] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [pick, setPick] = useState<Pick>(""),
    [sourceId, setSourceId] = useState(""),
    [audio, setAudio] = useState<string | null>(null),
    [subtitle, setSubtitle] = useState<string | null>(null),
    [deviceId, setDeviceId] = useState(""),
    [start, setStart] = useState<number>(resumeAt),
    [askReplace, setAskReplace] = useState(false);
  const screens = items(devices.data).filter((d) => d.adapter !== "dlna"); // music-only
  const screen = screens.find((d) => d.id === deviceId);
  useEffect(() => {
    if (deviceId || !screens.length || !preferences.data) return;
    const preferred = screens.find((d) => d.id === preferences.data!.preferred_device);
    setDeviceId((preferred || screens.find((d) => d.adapter === "cast") || screens[0]).id);
  }, [screens.length, preferences.data]);
  // Opening the card looks for versions and checks the three best at once.
  const started = useRef(false);
  useEffect(() => {
    if (workflowId || started.current || !deviceId) return;
    // Settle first: stepping through episodes should not check versions for each one.
    let alive = true;
    const timer = setTimeout(() => {
      started.current = true;
      void api("/cinema/operations/discover", "POST", {
        media_id: title.id,
        season,
        episode,
        device_id: deviceId,
        cloud_id: cloudId,
        suggest: true,
        idempotency_key: idempotency(),
      })
        .then((result) => {
          if (!alive) return; // the resident moved to another episode meanwhile
          if (result.workflow_id) onWorkflow(result.workflow_id);
          else setOperation(result.operation_id);
        })
        .catch((e) => alive && setError(errorText(e)));
    }, 600);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [deviceId, workflowId]);
  const op = useData(operation && !workflowId ? "/cinema/operations/" + operation : null, {
    interval: (data) =>
      (!data || !["failed", "unverified", "cancelled"].includes(data.status)) && 1500,
  });
  useEffect(() => {
    const result = op.data;
    if (!result) return;
    if (result.workflow_id) onWorkflow(result.workflow_id);
    else if (["failed", "unverified", "cancelled"].includes(result.status))
      setError(result.error?.message || t("Could not look for versions. Try again."));
  }, [op.data]);
  const flow = useData(workflowId ? "/cinema/workflows/" + workflowId : null, {
    interval: (data) =>
      !!data &&
      ["preparing", "discovered", "awaiting_preparation_confirmation"].includes(data.state) &&
      2000,
  });
  const workflow = flow.data;
  const candidates: Obj[] = workflow?.choice_set?.candidates || [];
  const candidate = candidates.find((c) => c.id === sourceId) || candidates[0];
  // External subtitles attach to the release; they show up on the selected summary.
  const attached =
    workflow?.selected_source?.id === candidate?.id ? workflow?.selected_source?.subtitles : null;
  const subtitleTracks: Obj[] = attached || candidate?.subtitles || [];
  const audioId = audio ?? candidate?.suggested_audio?.id ?? candidate?.audio?.[0]?.id;
  const subtitleId =
    subtitle ?? (candidate?.suggested_subtitle ? candidate.suggested_subtitle.id : "off");
  const audioTrack = candidate?.audio?.find((a: Obj) => a.id === audioId);
  const subtitleTrack = subtitleTracks.find((s) => s.id === subtitleId);
  const noScreen = !!devices.data && !screens.length;
  const onScreen = ["command_sent", "playing_observed", "paused"].includes(workflow?.state);
  const checking = !noScreen && (workflow?.state === "preparing" || (!workflow && !error));
  const progress = workflow?.suggestion_progress;
  const busyScreen = screen && !["idle", "stopped", "unknown", "unverified"].includes(screen.state);
  const launch = async (replace = false) => {
    setBusy(true);
    setAskReplace(false);
    try {
      const result = await api("/cinema/workflows/" + workflow!.id + "/launch", "POST", {
        version: replace ? (flow.data?.version ?? workflow!.version) : workflow!.version,
        source_id: candidate.id,
        device_id: deviceId,
        audio_track: audioId,
        subtitle_track: subtitleId,
        position: start,
        replace,
      });
      if (result.error) throw new Error(result.error.message);
      if (result.state === "awaiting_playback_confirmation") {
        // Something else plays on that screen: ask before replacing it.
        await flow.reload();
        setAskReplace(true);
        return;
      }
      onLaunched(
        t("Sending {title} to {screen}…")
          .replace("{title}", title.title)
          .replace("{screen}", screen?.name || t("the TV")),
      );
    } catch (e) {
      setError(errorText(e));
      await flow.reload();
    } finally {
      setBusy(false);
    }
  };
  const tryMore = async () => {
    setBusy(true);
    try {
      // The server picks the next most promising versions (not simply the next in the list).
      await api("/cinema/workflows/" + workflow!.id + "/suggest-more", "POST", {
        version: workflow!.version,
      });
      setError("");
      await flow.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const keepCopy = async () => {
    try {
      const prepared = await api("/cinema/workflows/" + workflow!.id + "/save-local", "POST", {
        version: workflow!.version,
        source_id: candidate.id,
      });
      if (prepared.confirmation_id)
        await api("/cinema/confirmations/" + prepared.confirmation_id, "POST");
      toast(t("Saving a copy at home. Follow it in Sources, Copies at home."));
    } catch (e) {
      setError(errorText(e));
    }
  };
  const quality = (c: Obj) =>
    [
      // The server's class (a 1920×800 crop is 1080p); the height only for older answers.
      (c.resolution || c.height) >= 2000
        ? "4K"
        : c.resolution || c.height
          ? (c.resolution || c.height) + "p"
          : "",
      c.hdr && c.hdr !== "sdr" ? (c.hdr === "dolby_vision" ? "Dolby Vision" : "HDR") : "",
    ]
      .filter(Boolean)
      .join(" · ");
  const origin = (c: Obj) =>
    c.layer === "LOCAL"
      ? t("In the house")
      : c.rd_cached
        ? "Debrid"
        : c.cache_evidence === "p2p"
          ? t("Torrent")
          : t("Online");
  const trackName = (track?: Obj) =>
    track
      ? [
          trackLanguage(track.language),
          track.channels > 2 ? (track.channels === 6 ? "5.1" : track.channels + " ch") : "",
        ]
          .filter(Boolean)
          .join(" ")
      : t("None");
  const subtitleName = (track?: Obj) =>
    track
      ? trackLanguage(track.language) +
        " · " +
        t(track.external || track.uploaded ? "added" : "in the file") +
        (track.forced ? " · " + t("forced") : "")
      : t("None");
  const startLabel = start
    ? (start === resumeAt ? t("Resume at") : t("Start at")) + " " + clock(start)
    : t("From the beginning");
  // A row opens its choices; version and tracks wait for a version to exist.
  const row = (key: Pick, label: string, value: ReactNode, note?: ReactNode) => (
    <ListRow
      key={key}
      title={t(label)}
      detail={value}
      meta={note}
      onOpen={!candidate && key !== "screen" && key !== "start" ? undefined : () => setPick(key)}
    />
  );
  const close = () => setPick("");
  // A question or a dead end below the fold scrolls into view (the sheet does not grow unseen).
  const replaceRef = useReveal<HTMLDivElement>(askReplace, '[data-variant="primary"]');
  const noneRef = useReveal<HTMLDivElement>(!checking && !!workflow && !candidate);
  return (
    <section className="watch-tonight" aria-label={t("Tonight")}>
      <Text as="h3" style="title-l">
        {t("Tonight")}
      </Text>
      {checking && <Checking progress={progress} />}
      {noScreen && (
        <Notice title={t("No screen yet")}>
          {t("No screen is set up yet. An admin can add one in the Control Room.")}
        </Notice>
      )}
      {onScreen && (
        <Notice tone="success">{t("On the TV now. Control it from the player below.")}</Notice>
      )}
      {!checking && workflow && !candidate && (
        <div ref={noneRef}>
          <Notice
            tone="warning"
            action={
              workflow.source_total > 0 && (
                <Button size="s" busy={busy} onClick={() => void tryMore()}>
                  {t("Check other versions")}
                </Button>
              )
            }
          >
            {workflow.suggestion_progress?.setbacks?.length
              ? t("None of the versions checked plays on this screen:") +
                " " +
                setbackText(workflow.suggestion_progress.setbacks)
              : workflow.error?.message || t("No version is ready yet.")}
          </Notice>
        </div>
      )}
      {!noScreen && (
        <>
          <List label={t("Tonight")}>
            {row(
              "version",
              "Version",
              candidate ? [origin(candidate), quality(candidate)].filter(Boolean).join(" · ") : "—",
              candidate?.size ? bytes(candidate.size) : undefined,
            )}
            {row(
              "audio",
              "Audio",
              candidate ? trackName(audioTrack) : "—",
              candidate?.suggested_audio?.id === audioId &&
                candidate?.why?.includes("original audio")
                ? t("original")
                : undefined,
            )}
            {row("subtitles", "Subtitles", candidate ? subtitleName(subtitleTrack) : "—")}
            {row(
              "screen",
              "Screen",
              screen?.name || t("Choose a screen"),
              busyScreen ? t("in use: this replaces it") : undefined,
            )}
            {row("start", "Start", startLabel)}
          </List>
          {candidate?.warnings?.length > 0 && (
            <Text style="body-s" tone="muted">
              {candidate.warnings.map((w: string) => t(w)).join(" ")}
            </Text>
          )}
          <Problem error={error || flow.error || op.error || devices.error} />
          <Button
            variant="primary"
            size="l"
            wide
            glyph="transport.play"
            busy={busy}
            disabled={!candidate || !deviceId || workflow?.state === "preparing" || onScreen}
            onClick={() => void launch()}
          >
            {busyScreen ? t("Replace and play on the TV") : t("Play on the TV")}
          </Button>
          {candidate && workflow && (
            // Or on this device: VLC streams the chosen version as it is, nothing is kept.
            <span className="watch-screen__actions">
              <OpenInPlayer
                path={"/cinema/workflows/" + workflow.id + "/player-link"}
                title={title.title}
                body={{ source_id: candidate.id }}
              />
            </span>
          )}
        </>
      )}
      {askReplace && (
        <div ref={replaceRef}>
          <Notice
            tone="warning"
            title={(workflow?.plan?.playing_title
              ? t("{title} is still playing on {screen}. Replace it?").replace(
                  "{title}",
                  workflow.plan.playing_title,
                )
              : t("Something is playing on {screen}. Replace it?")
            ).replace("{screen}", screen?.name || t("the TV"))}
            action={
              <span className="watch-screen__actions">
                <Button size="s" variant="primary" onClick={() => void launch(true)}>
                  {t("Replace")}
                </Button>
                <Button size="s" variant="quiet" onClick={() => setAskReplace(false)}>
                  {t("Cancel")}
                </Button>
              </span>
            }
          >
            {t("Not on your TV? It may be on another input.")}
          </Notice>
        </div>
      )}
      {candidate &&
        (user?.role === "admin" || user?.permissions?.includes("files.shared.write")) && (
          <div>
            <Button variant="link" size="s" icon="download" onClick={() => void keepCopy()}>
              {t("Keep a copy at home")}
            </Button>
          </div>
        )}

      {pick === "version" && (
        <Sheet
          title={t("Version")}
          onClose={close}
          footer={
            workflow?.source_total > candidates.length && (
              <Button
                disabled={busy || checking}
                onClick={() => {
                  close();
                  void tryMore();
                }}
              >
                {t("Check other versions")} ({(workflow?.source_total || 0) - candidates.length})
              </Button>
            )
          }
        >
          <List label={t("Version")}>
            {candidates.map((c) => (
              <Choice
                key={c.id}
                title={[origin(c), quality(c), c.size ? bytes(c.size) : ""]
                  .filter(Boolean)
                  .join(" · ")}
                detail={
                  <>
                    <span>{(c.why || []).map((w: string) => t(w)).join(" · ")}</span>
                    <span className="watch-release">{String(c.release).replace(FILE_ID, "")}</span>
                  </>
                }
                chosen={c.id === candidate?.id}
                onPick={() => {
                  setSourceId(c.id);
                  setAudio(null);
                  setSubtitle(null);
                  close();
                }}
              />
            ))}
          </List>
        </Sheet>
      )}
      {pick === "audio" && candidate && (
        <Sheet title={t("Audio")} onClose={close}>
          <List label={t("Audio")}>
            {candidate.audio.map((a: Obj) => (
              <Choice
                key={a.id}
                title={trackName(a)}
                detail={[a.codec, a.title, a.commentary ? t("commentary") : ""]
                  .filter(Boolean)
                  .join(" · ")}
                chosen={a.id === audioId}
                onPick={() => {
                  setAudio(a.id);
                  close();
                }}
              />
            ))}
          </List>
        </Sheet>
      )}
      {pick === "subtitles" && candidate && (
        <Sheet title={t("Subtitles")} onClose={close}>
          <List label={t("Subtitles")}>
            <Choice
              title={t("None")}
              chosen={subtitleId === "off"}
              onPick={() => {
                setSubtitle("off");
                close();
              }}
            />
            {subtitleTracks.map((s: Obj) => (
              <Choice
                key={s.id}
                title={subtitleName(s)}
                detail={[s.codec, s.sdh ? "SDH" : "", s.title].filter(Boolean).join(" · ")}
                chosen={s.id === subtitleId}
                onPick={() => {
                  setSubtitle(s.id);
                  close();
                }}
              />
            ))}
          </List>
          <SubtitlePicker
            mediaId={title.id}
            workflow={workflow!}
            sourceId={candidate.id}
            season={season}
            episode={episode}
            onWorkflow={(next) => {
              void flow.reload();
              const added = next.selected_source?.subtitles?.at?.(-1);
              if (added) setSubtitle(added.id);
            }}
          />
        </Sheet>
      )}
      {pick === "screen" && (
        <Sheet title={t("Screen")} onClose={close}>
          {screens.length ? (
            <List label={t("Screen")}>
              {screens.map((d) => (
                <Choice
                  key={d.id}
                  title={d.name}
                  detail={t(pretty(d.state))}
                  chosen={d.id === deviceId}
                  onPick={() => {
                    setDeviceId(d.id);
                    close();
                  }}
                />
              ))}
            </List>
          ) : (
            <State kind="not-configured" title={t("No screen yet")}>
              {t("No screen is set up yet. An admin can add one in the Control Room.")}
            </State>
          )}
        </Sheet>
      )}
      {pick === "start" && (
        <StartSheet
          resumeAt={resumeAt}
          value={start}
          duration={candidate?.duration}
          onPick={(value) => {
            setStart(value);
            close();
          }}
          onClose={close}
        />
      )}
    </section>
  );
}

function StartSheet({
  resumeAt,
  value,
  duration,
  onPick,
  onClose,
}: {
  resumeAt: number;
  value: number;
  duration?: number;
  onPick: (seconds: number) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState(value && value !== resumeAt ? clock(value) : ""),
    [error, setError] = useState("");
  return (
    <Sheet title={t("Start")} onClose={onClose}>
      <div className="watch-stack">
        <List label={t("Start")}>
          {resumeAt > 0 && (
            <Choice
              title={t("Resume at") + " " + clock(resumeAt)}
              chosen={value === resumeAt}
              onPick={() => onPick(resumeAt)}
            />
          )}
          <Choice title={t("From the beginning")} chosen={value === 0} onPick={() => onPick(0)} />
        </List>
        <form
          className="watch-inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            const seconds = parseTime(text);
            if (seconds == null) return setError(t("Write a time like 1:13:36."));
            if (duration && seconds >= duration) return setError(t("That is after the end."));
            onPick(seconds);
          }}
        >
          <Field label={t("Start at a time")} error={error}>
            <Input
              inputMode="numeric"
              placeholder="1:13:36"
              aria-label={t("Start time")}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary">
            {t("Use this time")}
          </Button>
        </form>
      </div>
    </Sheet>
  );
}

// ---------- drawers ----------
function DownloadsSheet({ onClose }: { onClose: () => void }) {
  const user = useUser();
  const downloads = useData("/cinema/downloads", {
    interval: (data) => items(data).some(downloadActive) && 3000,
  });
  const [error, setError] = useState("");
  const rows = items(downloads.data);
  return (
    <Sheet title={t("Copies at home")} place="side" onClose={onClose}>
      <div className="watch-stack">
        {/* The saved films themselves: play here, download, or open in VLC on a phone. */}
        <Button icon="folder" onClick={() => go("/files?scope=movies")}>
          {t("Films at home: play, download or open in VLC")}
        </Button>
        {(user?.role === "admin" || user?.permissions?.includes("files.shared.write")) && (
          <CinemaUpload actorId={user?.id} onAdded={() => void downloads.reload()} />
        )}
        <Problem error={error || downloads.error} onRetry={downloads.reload} />
        {downloads.data && !rows.length && (
          <State kind="empty" title={t("Nothing saved at home yet.")}>
            {t("Use “Keep a copy at home” on a film.")}
          </State>
        )}
        {rows.length > 0 && (
          <List label={t("Copies at home")}>
            {rows.map((w) => (
              <ListRow
                key={w.id}
                leading={<Icon name="film" />}
                title={
                  typeof w.title === "string" ? w.title : w.title?.title || t("Movie download")
                }
                actions={
                  downloadActive(w) && (
                    <Button
                      size="s"
                      variant="quiet"
                      onClick={async () => {
                        try {
                          await api("/cinema/workflows/" + w.id + "/cancel", "POST", {
                            version: w.version,
                          });
                          await downloads.reload();
                        } catch (e) {
                          setError(errorText(e));
                        }
                      }}
                    >
                      {t("Cancel download")}
                    </Button>
                  )
                }
              >
                <DownloadProgress workflow={w} />
                <Problem error={w.error?.message} />
              </ListRow>
            ))}
          </List>
        )}
      </div>
    </Sheet>
  );
}

function QueueSheet({ onClose, onOpen }: { onClose: () => void; onOpen: (entry: Obj) => void }) {
  const queue = useData("/cinema/queue");
  const [error, setError] = useState(""),
    [confirming, setConfirming] = useState(false);
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setError("");
      await queue.reload();
    } catch (e) {
      setError(errorText(e));
    }
  };
  const rows = items(queue.data);
  return (
    <Sheet
      title={t("My queue")}
      place="side"
      onClose={onClose}
      footer={
        !!queue.data?.total &&
        !confirming && (
          <Button variant="quiet" icon="list-clear" onClick={() => setConfirming(true)}>
            {t("Clear my queue")}
          </Button>
        )
      }
    >
      <div className="watch-stack">
        <Problem error={error || queue.error} onRetry={queue.reload} />
        {confirming && (
          <Notice
            tone="warning"
            action={
              <span className="watch-screen__actions">
                <Button
                  size="s"
                  variant="danger"
                  onClick={() =>
                    void act(() =>
                      api("/cinema/queue/clear", "POST", {
                        revision: queue.data!.revision,
                        idempotency_key: idempotency(),
                      }),
                    ).then(() => setConfirming(false))
                  }
                >
                  {t("Confirm clear queue")}
                </Button>
                <Button size="s" variant="quiet" onClick={() => setConfirming(false)}>
                  {t("Cancel")}
                </Button>
              </span>
            }
          >
            {t("Remove every queued title? Playback and history stay.")}
          </Notice>
        )}
        {queue.data && !rows.length && (
          <State kind="empty" title={t("Nothing queued.")}>
            {t("Use “Watch later” on a title.")}
          </State>
        )}
        {rows.length > 0 && (
          <List label={t("My queue")}>
            {rows.map((item) => (
              <ListRow
                key={item.queue_id}
                title={item.title}
                detail={item.episode != null ? `S${item.season} · E${item.episode}` : undefined}
                onOpen={() => onOpen({ id: item.id, season: item.season, episode: item.episode })}
                actions={
                  <IconButton
                    icon="close"
                    size="s"
                    label={t("Remove") + " · " + item.title}
                    onClick={() => void act(() => api("/cinema/queue/" + item.queue_id, "DELETE"))}
                  />
                }
              />
            ))}
          </List>
        )}
      </div>
    </Sheet>
  );
}

function HistorySheet({ onClose, onOpen }: { onClose: () => void; onOpen: (entry: Obj) => void }) {
  const [offset, setOffset] = useState(0);
  const history = useData("/cinema/state?filter=history&offset=" + offset);
  const [error, setError] = useState("");
  const rows = items(history.data);
  return (
    <Sheet
      title={t("History")}
      place="side"
      onClose={onClose}
      footer={
        (offset > 0 || history.data?.next_offset != null) && (
          <>
            <Button
              variant="quiet"
              icon="chevron-left"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              {t("Newer")}
            </Button>
            <Button
              variant="quiet"
              iconEnd="chevron-right"
              disabled={history.data?.next_offset == null}
              onClick={() => setOffset(history.data!.next_offset)}
            >
              {t("Older")}
            </Button>
          </>
        )
      }
    >
      <div className="watch-stack">
        <Problem error={error || history.error} onRetry={history.reload} />
        {history.data && !rows.length && <State kind="empty" title={t("Nothing watched yet.")} />}
        {rows.length > 0 && (
          <List label={t("History")}>
            {rows.map((row) => (
              <ListRow
                key={row.media_id}
                title={
                  row.series_title
                    ? row.series_title + " · S" + row.season + "E" + row.episode
                    : row.title
                }
                detail={
                  (row.watched ? t("Seen") : clock(row.position)) +
                  " · " +
                  time(row.last_watched_at)
                }
                onOpen={() =>
                  onOpen({
                    id: row.parent_id || row.media_id,
                    season: row.season,
                    episode: row.episode,
                  })
                }
                actions={
                  <Button
                    size="s"
                    variant="quiet"
                    aria-label={t("Forget") + " · " + row.title}
                    onClick={async () => {
                      try {
                        await api("/cinema/state/" + row.media_id + "/history", "DELETE");
                        await history.reload();
                      } catch (e) {
                        setError(errorText(e));
                      }
                    }}
                  >
                    {t("Forget")}
                  </Button>
                }
              />
            ))}
          </List>
        )}
      </div>
    </Sheet>
  );
}

function CloudSheet({ onClose, onPick }: { onClose: () => void; onPick: (entry: Obj) => void }) {
  const cloud = useData("/cinema/cloud");
  const rows = items(cloud.data);
  return (
    <Sheet title={t("Debrid history")} place="side" onClose={onClose}>
      <div className="watch-stack">
        <Text style="body-s" tone="muted">
          {t(
            "Files your debrid account opened before (they live on the debrid service, not on the house disk). Pick one, then open its film or series.",
          )}
        </Text>
        <Problem error={cloud.error} onRetry={cloud.reload} />
        {cloud.data && !rows.length && <State kind="empty" />}
        {rows.length > 0 && (
          <List label={t("Debrid history")}>
            {rows.map((entry) => (
              <ListRow
                key={entry.id}
                leading={<Icon name="cloud" />}
                title={entry.title}
                detail={[entry.size ? bytes(entry.size) : "", t(pretty(entry.state))]
                  .filter(Boolean)
                  .join(" · ")}
                onOpen={() => onPick(entry)}
              />
            ))}
          </List>
        )}
      </div>
    </Sheet>
  );
}

/** Home's window onto the screening room: what to continue, else what's on your list, else what
 *  you watched last. With none of it, one line and the way in. */
export function WatchPanel() {
  const shelves = useData("/cinema/shelves");
  const data = shelves.data || {};
  const [title, cards]: [string, Obj[]] = data.continue?.length
    ? [t("Continue watching"), data.continue]
    : data.watchlist?.length
      ? [t("On your list"), data.watchlist]
      : [t("Watched lately"), data.recent || []];
  return (
    <Panel className="home-watch" icon="film" title={title} href="/watch">
      {cards.length ? (
        <ul className="home-watch__posters">
          {cards.slice(0, 4).map((card: Obj) => (
            <Poster
              key={card.media_id + ":" + (card.episode ?? "")}
              title={card}
              meta={
                card.action === "next"
                  ? t("Next") + " · S" + card.season + "E" + card.episode
                  : card.position
                    ? clock(card.position)
                    : undefined
              }
              onOpen={() =>
                go(
                  "/watch?title=" +
                    encodeURIComponent(
                      card.action === "next" ? card.media_id : card.parent_id || card.media_id,
                    ),
                )
              }
            />
          ))}
        </ul>
      ) : (
        <Text style="body-s" tone="muted">
          {shelves.data ? t("Nothing on the go. Find a film for tonight.") : t("Loading…")}
        </Text>
      )}
    </Panel>
  );
}

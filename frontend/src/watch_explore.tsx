import { t } from "./i18n";
import { useState, type ReactNode } from "react";
import { number, useData, usePages, items, type Obj } from "./api";
import {
  Badge,
  Button,
  Checkbox,
  Chip,
  ChipGroup,
  Field,
  Input,
  MoreBelow,
  Problem,
  Select,
  Shelf,
  State,
  Text,
  useNear,
} from "./design";

/** Filters for the whole catalogue (local indexes: instant, and they work offline). Every
 *  chip narrows the list further: two people, a genre and a theme all have to match. */
export type Filters = {
  year_from?: number;
  year_to?: number;
  genre?: string[];
  tag?: string[];
  person?: string[];
  award?: string;
  short?: boolean;
  sort?: string;
};
export const noFilters: Filters = {};
/** A poster's width in a shelf. */
export const POSTER = "128px";
export const filtering = (f: Filters) =>
  !!(
    f.year_from ||
    f.year_to ||
    f.genre?.length ||
    f.tag?.length ||
    f.person?.length ||
    f.award ||
    f.short ||
    f.sort
  );

export function discoverPath(kind: string, q: string, f: Filters) {
  const p = new URLSearchParams({ kind });
  if (q) p.set("q", q);
  if (f.year_from) p.set("year_from", String(f.year_from));
  if (f.year_to) p.set("year_to", String(f.year_to));
  if (f.genre?.length) p.set("genre", f.genre.join(","));
  if (f.tag?.length) p.set("tag", f.tag.join(","));
  if (f.person?.length) p.set("person", f.person.join("|"));
  if (f.award) p.set("award", f.award);
  if (f.short)
    p.set(kind === "anime" ? "max_episodes" : "max_minutes", kind === "anime" ? "13" : "90");
  if (f.sort) p.set("sort", f.sort);
  return "/cinema/explore?" + p;
}

const toggle = (list: string[] | undefined, value: string, most = 4) =>
  (list || []).includes(value)
    ? (list || []).filter((x) => x !== value)
    : [...(list || []), value].slice(-most);

/** Names from the catalogue as you type: tap one to add it (several narrow the list). */
export function PeoplePicker({
  kind,
  chosen,
  onPick,
}: {
  kind: string;
  chosen: string[];
  onPick: (name: string) => void;
}) {
  const [text, setText] = useState("");
  const names = useData(
    text.trim().length >= 2
      ? "/cinema/explore/people?kind=" + kind + "&q=" + encodeURIComponent(text.trim())
      : null,
  );
  const suggestions: string[] = (names.data?.items || []).filter(
    (name: string) => !chosen.includes(name),
  );
  const pick = (name: string) => {
    onPick(name);
    setText("");
  };
  return (
    <div className="watch-stack">
      <Field label={t(kind === "anime" ? "Studio" : "Director or actor")}>
        <Input
          value={text}
          placeholder={kind === "anime" ? "Studio Ghibli" : "Denis Villeneuve"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            if (suggestions[0] || text.trim()) pick(suggestions[0] || text.trim());
          }}
        />
      </Field>
      {suggestions.length > 0 && (
        <ChipGroup label={t("Suggestions")}>
          {suggestions.map((name) => (
            <Chip key={name} kind="person" icon="add" onToggle={() => pick(name)}>
              {name}
            </Chip>
          ))}
        </ChipGroup>
      )}
      {text.trim().length >= 2 && names.data && !suggestions.length && (
        <Text style="body-s" tone="muted">
          {t("Nobody by that name in the catalogue.")}
        </Text>
      )}
    </div>
  );
}

const facetsPath = (kind: string) => "/cinema/explore/facets?kind=" + kind;
/** "1990s", "Années 1990": named in the page's language. */
const decadeName = (d: number | string) => t("{decade}s").replace("{decade}", String(d));
const shortLabel = (kind: string) =>
  t(kind === "anime" ? "Short series (13 episodes or less)" : "Under 90 minutes");
/** The filters behind "More filters" (genre and sort sit in the bar). */
const moreCount = (f: Filters) =>
  (f.year_from || f.year_to ? 1 : 0) +
  (f.person?.length || 0) +
  (f.tag?.length || 0) +
  (f.award ? 1 : 0) +
  (f.short ? 1 : 0);
const THEMES_SHOWN = 8;

/** Under the search field: a genre to add, the order, and "More filters". */
export function FilterBar({
  kind,
  value,
  onChange,
  open,
  onMore,
}: {
  kind: string;
  value: Filters;
  onChange: (f: Filters) => void;
  open: boolean;
  onMore: () => void;
}) {
  const facets = useData(facetsPath(kind)).data;
  const genres: string[] = (facets?.genres || []).filter(
    (genre: string) => !value.genre?.includes(genre),
  );
  const count = moreCount(value);
  return (
    <div className="watch-filterbar">
      <Select
        aria-label={t("Genre")}
        value=""
        disabled={!genres.length}
        onChange={(e) =>
          e.target.value && onChange({ ...value, genre: toggle(value.genre, e.target.value, 3) })
        }
      >
        <option value="">{t("Genre")}</option>
        {genres.map((genre) => (
          <option key={genre} value={genre}>
            {t(genre)}
          </option>
        ))}
      </Select>
      <Select
        aria-label={t("Sort")}
        value={value.sort || "known"}
        onChange={(e) =>
          onChange({ ...value, sort: e.target.value === "known" ? undefined : e.target.value })
        }
      >
        <option value="known">{t("Best known")}</option>
        <option value="newest">{t("Newest")}</option>
        <option value="oldest">{t("Oldest")}</option>
        {kind === "anime" && <option value="rated">{t("Best rated")}</option>}
      </Select>
      <Button
        variant={open ? "secondary" : "quiet"}
        icon="sliders"
        aria-expanded={open}
        aria-controls="watch-more-filters"
        className="watch-filter-toggle"
        onClick={onMore}
      >
        <span className="watch-filter-toggle__label">{t("More filters")}</span>
        {count > 0 && (
          <>
            {" "}
            <Badge label={t("{n} in use").replace("{n}", String(count))}>{count}</Badge>
          </>
        )}
      </Button>
    </div>
  );
}

/** "More filters": when, who, awards, length and themes, in a few dense columns. */
export function FilterPanel({
  kind,
  value,
  onChange,
}: {
  kind: string;
  value: Filters;
  onChange: (f: Filters) => void;
}) {
  const facets = useData(facetsPath(kind));
  const [allThemes, setAllThemes] = useState(false);
  const f = facets.data;
  const set = (change: Filters) => onChange({ ...value, ...change });
  if (f && !f.ready)
    return (
      <div className="watch-filters" id="watch-more-filters">
        <Text style="body-s" tone="muted">
          {t("Filters are getting ready: the catalogue list builds in the background.")}
        </Text>
      </div>
    );
  const [first, last] = f?.years || [1920, new Date().getFullYear()];
  const years = Array.from({ length: last - first + 1 }, (_, i) => last - i);
  const decades = [...new Set(years.map((y) => y - (y % 10)))];
  const decade =
    value.year_from && value.year_to === value.year_from + 9 && value.year_from % 10 === 0
      ? value.year_from
      : "";
  const yearMenu = (label: string, key: "year_from" | "year_to") => (
    <Field label={t(label)}>
      <Select
        value={value[key] ?? ""}
        onChange={(e) => set({ [key]: Number(e.target.value) || undefined })}
      >
        <option value="">{t(key === "year_from" ? "Any year" : "Today")}</option>
        {years
          .filter((y) =>
            key === "year_from"
              ? !value.year_to || y <= value.year_to
              : y >= (value.year_from || 0),
          )
          .map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
      </Select>
    </Field>
  );
  const tags: Obj[] = f?.tags || [];
  const shownTags = allThemes
    ? tags
    : tags.filter((tag, i) => i < THEMES_SHOWN || value.tag?.includes(tag.key));
  return (
    <div className="watch-filters" id="watch-more-filters">
      <Problem error={facets.error} onRetry={facets.reload} />
      <div className="watch-filters__cell">
        <Field label={t("Decade")}>
          <Select
            value={decade}
            onChange={(e) => {
              const d = Number(e.target.value);
              set(
                d ? { year_from: d, year_to: d + 9 } : { year_from: undefined, year_to: undefined },
              );
            }}
          >
            <option value="">{t("Any decade")}</option>
            {decades.map((d) => (
              <option key={d} value={d}>
                {decadeName(d)}
              </option>
            ))}
          </Select>
        </Field>
        <div className="watch-filters__pair">
          {yearMenu("From", "year_from")}
          {yearMenu("To", "year_to")}
        </div>
      </div>
      <div className="watch-filters__cell">
        <PeoplePicker
          kind={kind}
          chosen={value.person || []}
          onPick={(name) => set({ person: toggle(value.person, name) })}
        />
      </div>
      <div className="watch-filters__cell">
        {!!f?.awards?.length && (
          <Field label={t("Award")}>
            <Select
              value={value.award || ""}
              onChange={(e) => set({ award: e.target.value || undefined })}
            >
              <option value="">{t("Any award")}</option>
              {f.awards.map((award: Obj) => (
                <option key={award.key} value={award.key}>
                  {t(award.label)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Checkbox
          label={shortLabel(kind)}
          checked={!!value.short}
          onChange={(e) => set({ short: e.target.checked || undefined })}
        />
      </div>
      {!!tags.length && (
        <fieldset className="watch-filters__themes">
          <legend>{t("Themes")}</legend>
          <ChipGroup label={t("Themes")}>
            {shownTags.map((tag) => (
              <Chip
                key={tag.key}
                kind="filter"
                selected={!!value.tag?.includes(tag.key)}
                onToggle={() => set({ tag: toggle(value.tag, tag.key) })}
              >
                {t(tag.label)}
              </Chip>
            ))}
            {tags.length > THEMES_SHOWN && (
              <Button
                variant="link"
                size="s"
                aria-expanded={allThemes}
                onClick={() => setAllThemes(!allThemes)}
              >
                {allThemes
                  ? t("Fewer")
                  : t("+{n} more").replace("{n}", String(tags.length - shownTags.length))}
              </Button>
            )}
          </ChipGroup>
        </fieldset>
      )}
    </div>
  );
}

/** The filters in use, each removable in one tap. */
export function ActiveFilters({
  kind,
  value,
  onChange,
}: {
  kind: string;
  value: Filters;
  onChange: (f: Filters) => void;
}) {
  // Labels only matter for tags and awards; no request while nothing needs one.
  const facets = useData(value.tag?.length || value.award ? facetsPath(kind) : null);
  const label = (list: Obj[] | undefined, key: string) =>
    t(list?.find((x) => x.key === key)?.label || key);
  const chips: [string, Filters][] = [];
  if (value.year_from || value.year_to)
    chips.push([
      value.year_from && value.year_to === value.year_from + 9 && value.year_from % 10 === 0
        ? decadeName(value.year_from)
        : (value.year_from || "…") + "–" + (value.year_to || "…"),
      { year_from: undefined, year_to: undefined },
    ]);
  for (const genre of value.genre || [])
    chips.push([t(genre), { genre: (value.genre || []).filter((x) => x !== genre) }]);
  for (const tag of value.tag || [])
    chips.push([
      label(facets.data?.tags, tag),
      { tag: (value.tag || []).filter((x) => x !== tag) },
    ]);
  for (const name of value.person || [])
    chips.push([name, { person: (value.person || []).filter((x) => x !== name) }]);
  if (value.award) chips.push([label(facets.data?.awards, value.award), { award: undefined }]);
  if (value.short) chips.push([shortLabel(kind), { short: undefined }]);
  if (!chips.length) return null;
  return (
    <ChipGroup label={t("Filters in use")}>
      {chips.map(([text, change]) => (
        <Chip key={text} kind="filter" selected onRemove={() => onChange({ ...value, ...change })}>
          {text}
        </Chip>
      ))}
      <Button variant="link" size="s" onClick={() => onChange(noFilters)}>
        {t("Clear all")}
      </Button>
    </ChipGroup>
  );
}

/** Results for the filters (and the typed words, if any), growing as you scroll. */
export function DiscoverResults({
  path,
  poster,
}: {
  path: string;
  poster: (title: Obj) => ReactNode;
}) {
  const pages = usePages(path, (data) =>
    data.next_offset != null ? "offset=" + data.next_offset : null,
  );
  const total = useData(path).data?.total;
  return (
    <section className="watch-stack" aria-label={t("Search results")}>
      <Problem error={pages.error} onRetry={pages.reload} />
      {total != null && (
        <Text style="body-s" tone="muted">
          {t("{n} titles").replace("{n}", number(total))}
        </Text>
      )}
      <ul className="watch-grid" aria-label={t("Search results")}>
        {pages.items.map(poster)}
      </ul>
      {!pages.loading && !pages.error && total === 0 && (
        <State kind="empty" title={t("Nothing matches these filters")}>
          {t("Remove a filter to see more.")}
        </State>
      )}
      <MoreBelow pages={pages} />
    </section>
  );
}

/** A sideways row that keeps loading as you scroll it (arrows or swipe). */
export function ExploreRow({
  label,
  path,
  poster,
  action,
  onSeeAll,
}: {
  label: string;
  path: string;
  poster: (title: Obj) => ReactNode;
  action?: ReactNode;
  /** "See all": the row opens as a page of its own. */
  onSeeAll?: (label: string, path: string) => void;
}) {
  // A row loads when it nears the screen: opening Watch asks for the first few, not all.
  const [near, ref] = useNear<HTMLDivElement>();
  const pages = usePages(near ? path : null, (data) =>
    data.next_offset != null ? "offset=" + data.next_offset : null,
  );
  const settled = near && !pages.loading;
  if (settled && !pages.error && !pages.items.length) return null; // an empty row leaves no gap
  return (
    <div ref={ref} className="watch-row-slot">
      {pages.error ? (
        <Problem error={label + ": " + pages.error} onRetry={pages.reload} />
      ) : pages.items.length ? (
        <Shelf
          title={label}
          item={POSTER}
          action={
            action ||
            (onSeeAll && (
              <Button
                variant="link"
                size="s"
                aria-label={t("See all") + " · " + label}
                onClick={() => onSeeAll(label, path)}
              >
                {t("See all")}
              </Button>
            ))
          }
        >
          {pages.items.map(poster)}
          <MoreBelow pages={pages} item />
        </Shelf>
      ) : (
        <div className="watch-row-waiting" aria-hidden="true" />
      )}
    </div>
  );
}

/** Every title of the tab, best known first: the endless first row. */
export function EverythingRow({
  kind,
  poster,
  onSeeAll,
}: {
  kind: string;
  poster: (title: Obj) => ReactNode;
  onSeeAll: (label: string, path: string) => void;
}) {
  const label =
    { movie: "All films", series: "All series", anime: "All anime" }[kind] || "All films";
  return (
    <ExploreRow
      label={t(label)}
      path={"/cinema/explore?kind=" + kind}
      poster={poster}
      onSeeAll={onSeeAll}
    />
  );
}

/** One row opened as a page: every title in it, a grid that keeps loading as you scroll. */
export function SeeAll({
  label,
  path,
  poster,
  onBack,
}: {
  label: string;
  path: string;
  poster: (title: Obj) => ReactNode;
  onBack: () => void;
}) {
  const pages = usePages(path, (data) =>
    data.next_offset != null ? "offset=" + data.next_offset : null,
  );
  return (
    <section className="watch-stack" aria-label={label}>
      <div className="watch-seeall__head">
        <Button variant="quiet" icon="back" onClick={onBack}>
          {t("Back")}
        </Button>
        <Text as="h2" style="title-m">
          {label}
        </Text>
      </div>
      <Problem error={pages.error} onRetry={pages.reload} />
      <ul className="watch-grid" aria-label={label}>
        {pages.items.map(poster)}
      </ul>
      <MoreBelow pages={pages} />
    </section>
  );
}

/** Like the last things this person watched in this tab (none until they watch something). */
export function ForYouRow({ kind, poster }: { kind: string; poster: (title: Obj) => ReactNode }) {
  const rows = useData("/cinema/for-you?kind=" + kind);
  const list = items(rows.data);
  if (!list.length) return null;
  return (
    <Shelf title={t("Recommended for you")} item={POSTER}>
      {list.map(poster)}
    </Shelf>
  );
}

/** Classic genres, then this week's niche collections; each row grows sideways, "See all"
 *  opens it as a page. */
export function Collections({
  kind,
  poster,
  onSeeAll,
}: {
  kind: string;
  poster: (title: Obj) => ReactNode;
  onSeeAll: (label: string, path: string) => void;
}) {
  const rows = useData("/cinema/collections?kind=" + kind);
  return (
    <>
      {items(rows.data).map((row) => {
        const label = t(row.title).replace("{name}", row.name || "");
        const query = new URLSearchParams({ kind, sort: row.sort || "known" });
        for (const [key, value] of Object.entries(row.query || {})) query.set(key, String(value));
        return (
          <ExploreRow
            key={row.key}
            label={label}
            path={"/cinema/explore?" + query}
            poster={poster}
            onSeeAll={onSeeAll}
          />
        );
      })}
    </>
  );
}

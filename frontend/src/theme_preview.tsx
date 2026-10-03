// A theme drawn as a small, still copy of the app: the status bar, the rail, a room's header,
// panels, a list, the Now bar. Every piece is the real design system in that theme (scoped with
// data-theme), so what you see is what wearing it would look like. Used by the Workshop's tour
// (with numbered parts), Remix's live preview, the theme pickers and an admin's review.
import { useState, type CSSProperties, type ReactNode } from "react";
import { api } from "./api";
import { go } from "./nav";
import { t, useI18n } from "./i18n";
import {
  Avatar,
  Button,
  Field,
  Glyph,
  type GlyphName,
  Icon,
  Input,
  List,
  ListRow,
  Mascot,
  Media,
  Notice,
  PageHeader,
  Panel,
  Select,
  Sheet,
  Slot,
  ThemeLayers,
  Stack,
  Status,
  Text,
  toast,
} from "./design";
import {
  allThemes,
  partData,
  PreviewInfo,
  SchemeScope,
  surfaceVars,
  ThemeScope,
  tryOn,
  useTheme,
  useThemeInfo,
} from "./design/theme";
import { PieceFill } from "./design/icons";
import type { Scheme, ThemeInfo } from "./design/generated/themes";
import { themeGrid } from "./sprites";
import "./theme_preview.css";

/** Hand a theme to Nox's studio: it reads what is there and finishes it with the person. */
export function handToNox(id: string, name: string) {
  const message = t(
    "Take over my theme “{name}” (id {id}): read what I made, keep what works, and finish it with me. Ask me what I want first.",
  )
    .replace("{name}", name)
    .replace("{id}", id);
  dispatchEvent(new CustomEvent("houseos:ask", { detail: { purpose: "themes", message } }));
}

/** The parts a tour points at, in reading order (the numbers on the preview). */
export const PREVIEW_PARTS = [
  "page",
  "status",
  "rail",
  "header",
  "panel",
  "pieces",
  "titles",
  "list",
  "nowbar",
] as const;
export type PreviewPart = (typeof PREVIEW_PARTS)[number];

const DOORS: [GlyphName, string][] = [
  ["room.home", "Home"],
  ["room.listen", "Listen"],
  ["room.watch", "Watch"],
  ["room.house", "House"],
  ["room.smart-home", "Smart home"],
];

function Medal({ id, icon }: { id: string; icon: "headphones" | "compass" }) {
  const info = useThemeInfo();
  const grid = themeGrid(info, "title." + id);
  return grid ? <PieceFill grid={grid} box={32} /> : <Icon name={icon} />;
}

function TitleName({ id, fallback }: { id: string; fallback: string }) {
  const info = useThemeInfo();
  const { language } = useI18n();
  const own = info?.flavor["title." + id + ".name"];
  return <>{own ? (language === "fr" ? own.fr : own.en) : t(fallback)}</>;
}

/** A numbered marker on a part (tour only): a button that says which part it is. */
function Mark({
  part,
  marks,
  picked,
  onPick,
}: {
  part: PreviewPart;
  marks?: boolean;
  picked?: PreviewPart;
  onPick?: (part: PreviewPart) => void;
}) {
  if (!marks) return null;
  return (
    <Button
      size="s"
      variant={picked === part ? "primary" : "secondary"}
      className="mini__mark"
      aria-label={t("Part {n}").replace("{n}", String(PREVIEW_PARTS.indexOf(part) + 1))}
      aria-pressed={picked === part}
      onClick={() => onPick?.(part)}
    >
      {PREVIEW_PARTS.indexOf(part) + 1}
    </Button>
  );
}

export function ThemePreview({
  theme,
  scheme,
  info,
  scale = 0.5,
  marks = false,
  picked,
  onPick,
  label,
}: {
  /** The theme's id (its stylesheet must be linked: bundled ones always are). */
  theme: string;
  scheme?: string;
  /** A theme not in the list yet (Remix's unsaved draft): what the interface knows of it. */
  info?: ThemeInfo;
  scale?: number;
  /** Numbered markers on each part (the Workshop's tour). */
  marks?: boolean;
  picked?: PreviewPart;
  onPick?: (part: PreviewPart) => void;
  label?: string;
}) {
  const mark = (part: PreviewPart) => (
    <Mark part={part} marks={marks} picked={picked} onPick={onPick} />
  );
  const body: ReactNode = (
    <>
      {mark("page")}
      <div className="mini__backdrop" aria-hidden="true">
        <Slot id="page.backdrop" />
        <ThemeLayers where="page" />
      </div>
      <div className="mini__status">
        {mark("status")}
        <Slot id="status.backdrop" className="mini__sky" width={320} height={16} />
        <ThemeLayers where="status" />
        <strong className="mini__brand">{t("Our house")}</strong>
        <span className="mini__search">
          <Icon name="search" size="s" /> {t("Go to, do or ask…")}
        </span>
        <Icon name="inbox" size="s" />
        <Avatar name={t("You")} picture="crest" tone="var(--c-person-1)" size="s" decorative />
      </div>
      <div className="mini__body">
        <nav className="mini__rail" aria-label={t("Main navigation")}>
          {mark("rail")}
          {DOORS.map(([glyph, name], i) => (
            <span key={glyph} className="mini__door" data-current={i === 0 || undefined}>
              <Glyph name={glyph} /> {t(name)}
            </span>
          ))}
          <Slot id="rail.art" className="mini__rail-art" />
          <ThemeLayers where="rail" />
          <span className="mini__door mini__ask">
            <Mascot size="s" /> {t("Ask Nox")}
          </span>
        </nav>
        <main className="mini__page">
          <div className="mini__header">
            {mark("header")}
            <PageHeader room="home" title={t("Good evening")} />
          </div>
          <div className="mini__panels">
            <div className="mini__panel">
              {mark("panel")}
              <Panel icon="music" title={t("Now playing")}>
                <div className="mini__deck">
                  <Media src={null} alt="" ratio="1 / 1" />
                  <span>
                    <strong>{t("A song for the evening")}</strong>
                    <small>{t("Auto play")}</small>
                  </span>
                </div>
                <span className="mini__keys">
                  <Glyph name="transport.previous" />
                  <Glyph name="transport.pause" />
                  <Glyph name="transport.next" />
                </span>
              </Panel>
            </div>
            <div className="mini__panel">
              {mark("pieces")}
              <Panel icon="people" title={t("Who is around")}>
                <span className="mini__faces">
                  {(["crest", "moon", "bat", "raven", "rose", "ghost"] as const).map((pic, i) => (
                    <Avatar
                      key={pic}
                      name={pic === "crest" ? "Alex" : ""}
                      picture={pic}
                      tone={`var(--c-person-${i + 1})`}
                      size="s"
                    />
                  ))}
                </span>
                <span className="mini__nox">
                  <Mascot size="l" mood="happy" />
                  <Notice tone="success">{t("Everything is in order.")}</Notice>
                </span>
              </Panel>
            </div>
            <div className="mini__panel">
              {mark("titles")}
              <Panel icon="star" title={t("House titles")}>
                <ul className="mini__titles">
                  <li>
                    <Medal id="dj" icon="headphones" />
                    <strong>
                      <TitleName id="dj" fallback="Head DJ" />
                    </strong>
                    <small>{t("{n} songs played").replace("{n}", "42")}</small>
                  </li>
                  <li>
                    <Medal id="explorer" icon="compass" />
                    <strong>
                      <TitleName id="explorer" fallback="Explorer" />
                    </strong>
                    <small>{t("{n} different songs").replace("{n}", "18")}</small>
                  </li>
                </ul>
              </Panel>
            </div>
            <div className="mini__panel mini__list">
              {mark("list")}
              <Panel icon="list-todo" title={t("Today")}>
                <List>
                  <ListRow title={t("Water the plants")} detail={t("Due today")} />
                  <ListRow
                    title={t("Film night")}
                    detail={t("8 pm")}
                    status={{ tone: "info", text: t("Tonight") }}
                  />
                </List>
                <Status tone="success">{t("Done")}</Status>
              </Panel>
            </div>
          </div>
        </main>
      </div>
      <div className="mini__now">
        {mark("nowbar")}
        <Glyph name="room.listen" />
        <span>
          <strong>{t("A song for the evening")}</strong>
          <small>{t("Playing")}</small>
        </span>
        <Glyph name="transport.pause" />
      </div>
    </>
  );
  const scoped = (
    <section
      className="ds-scope mini"
      data-theme={theme}
      data-scheme={scheme}
      data-room="home"
      data-marks={marks || undefined}
      {...partData(info ? "" : theme, info)}
      style={
        {
          "--mini-zoom": scale,
          ...surfaceVars(info ? "" : theme, info, "home", scheme),
        } as CSSProperties
      }
      aria-label={label ?? t("A preview of the theme")}
      inert={!marks}
    >
      {body}
    </section>
  );
  return (
    <ThemeScope.Provider value={info ? "" : theme}>
      <SchemeScope.Provider value={scheme ?? ""}>
        {info ? <PreviewInfo.Provider value={info}>{scoped}</PreviewInfo.Provider> : scoped}
      </SchemeScope.Provider>
    </ThemeScope.Provider>
  );
}

// ---------- starting: a copy of a theme, named, then the editor ----------
export function StartTheme({
  source,
  name,
  onClose,
}: {
  source?: string;
  name?: string;
  onClose: () => void;
}) {
  const { language } = useI18n();
  const nameOf = (theme: ThemeInfo) => (language === "fr" ? theme.names.fr : theme.names.en);
  const worn = useTheme().split("/")[0] || "base";
  const [chosen, setFrom] = useState(source || "");
  const from = chosen || worn;
  const [title, setTitle] = useState(name || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const id = (text: string) =>
    text
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 32) || "my-theme";
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const made = await api("/themes/remix", "POST", {
        source: from,
        id: id(title) + "-" + Math.random().toString(36).slice(2, 6),
        names: { en: title.trim(), fr: title.trim() },
      });
      if (!made.passed) throw new Error((made.failures || []).join(" · ") || t("It didn't start"));
      onClose();
      go("/workshop/remix?id=" + made.id);
    } catch (e) {
      setError((e as Error).message);
      toast((e as Error).message, { tone: "danger" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      title={t("Start a theme")}
      place="center"
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t("Cancel")}
          </Button>
          <Button
            variant="primary"
            busy={busy}
            disabled={!title.trim()}
            onClick={() => void start()}
          >
            {t("Start")}
          </Button>
        </>
      }
    >
      <Stack space={4}>
        <Field label={t("Its name")}>
          <Input
            value={title}
            maxLength={32}
            data-autofocus=""
            placeholder={t("Night bathhouse")}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field
          label={t("Start from")}
          hint={t("Base is the plainest; any other starts from its look.")}
        >
          <Select value={from} onChange={(e) => setFrom(e.target.value)}>
            {allThemes()
              .filter(
                (theme) =>
                  !theme.hidden &&
                  (!("status" in theme) || theme.status === "shared" || theme.mine),
              )
              .map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {nameOf(theme)}
                </option>
              ))}
          </Select>
        </Field>
        <div className="workshop-card__preview">
          <ThemePreview theme={from} scale={0.4} />
        </div>
        {error && <Text tone="danger">{error}</Text>}
      </Stack>
    </Sheet>
  );
}

/** A theme in a picker: its own picture of Home when it has one (bundled themes: the tour's card,
 *  art/card-<scheme>.webp), else its app drawn live. */
export function ThemeLook({
  theme,
  scheme,
  scale,
}: {
  theme: ThemeInfo;
  scheme?: string;
  scale: number;
}) {
  const shown = (
    scheme && theme.schemes.includes(scheme as Scheme) ? scheme : theme.schemes[0]
  ) as Scheme;
  return theme.cards?.[shown] ? (
    <img className="theme-card" src={theme.cards[shown]} alt="" loading="lazy" />
  ) : (
    <ThemePreview theme={theme.id} scheme={shown} scale={scale} label="" />
  );
}

// ---------- picking a look (the onboardings: onboarding.tsx) ----------
/** The themes, big, to pick one; each is tried on behind the sheet as it's chosen (the caller
 *  takes it off with tryOn(null)). In the pickers' order; the house's theme is marked as the
 *  default: keeping it means following the house. */
export function LookPicker({
  value,
  house,
  scale = 0.26,
  onChange,
}: {
  value: string;
  /** The house's default theme. */
  house: string;
  /** How big each preview is drawn (0.26: 312 px wide). */
  scale?: number;
  onChange: (id: string) => void;
}) {
  const { language } = useI18n();
  const themes = allThemes().filter(
    (theme) => !theme.hidden && (!("status" in theme) || theme.status === "shared" || theme.mine),
  );
  return (
    <div className="look-pick" role="radiogroup" aria-label={t("Themes")}>
      {themes.map((theme) => (
        <Button
          key={theme.id}
          variant="quiet"
          className="look-pick__one"
          role="radio"
          aria-checked={value === theme.id}
          onClick={() => {
            onChange(theme.id);
            tryOn(theme.id);
          }}
        >
          <ThemeLook theme={theme} scale={scale} />
          <strong>
            {language === "fr" ? theme.names.fr : theme.names.en}
            {theme.id === house && " · " + t("the house's")}
          </strong>
          <small>{language === "fr" ? theme.description.fr : theme.description.en}</small>
        </Button>
      ))}
    </div>
  );
}

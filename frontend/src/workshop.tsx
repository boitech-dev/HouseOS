// The theme workshop (/workshop, everyone who lives here): how a theme is built, part by part, on
// a live copy of the app; ideas to start from; every piece; and the three ways to make one (by hand
// here with Remix, with Nox, or with the kit and an agent of your own).
import { useEffect, useState, type ReactNode } from "react";
import { useUser } from "./api";
import { t, useI18n } from "./i18n";
import { go } from "./nav";
import {
  Button,
  Cluster,
  Field,
  Grid,
  Icon,
  type IconName,
  Page,
  PageHeader,
  Section,
  Select,
  Stack,
  SubNav,
  Text,
} from "./design";
import { allThemes, tryOn, useTheme } from "./design/theme";
import type { ThemeInfo } from "./design/generated/themes";
import { PARTS, PIECES, SLOTS } from "./design/generated/themes";
import { StartTheme, ThemePreview, PREVIEW_PARTS, type PreviewPart } from "./theme_preview";
import { Workbench } from "./workbench";
import "./workshop.css";

const TABS = ["tour", "ideas", "pieces", "make"] as const;
type Tab = (typeof TABS)[number];

/** What shapes each part of the tour: its tokens, variants, slots, pieces and words. */
const PART_INFO: Record<
  PreviewPart,
  { title: string; what: string; tokens: string; variants?: string; slots?: string; more?: string }
> = {
  page: {
    title: "The page",
    what: "The ground under everything: a colour, a faint repeating texture, or a whole picture behind every room under a veil that keeps text readable.",
    tokens: "part.page.bg · part.page.texture · part.page.scrim",
    slots: "page.backdrop",
  },
  status: {
    title: "The top bar",
    what: "The house's name, the search, the inbox and you. A strip of art may run behind it.",
    tokens: "part.status.bg · part.status.border · part.status.texture · part.status.art-opacity",
    slots: "status.backdrop",
    more: "The house's name is written in the brand text style (text.brand).",
  },
  rail: {
    title: "The rail and the dock",
    what: "The rooms: a rail on wide screens, a dock at the bottom of phones, Nox at its heart. Each room's mark can be redrawn; each bar can wear a picture of its own, and a picture may sit at the rail's foot.",
    tokens: "part.rail.* · part.dock.* · color.room.*",
    variants: "dock: flush or floating",
    slots: "rail.surface · dock.surface · rail.art",
    more: "Room marks: room.home, room.listen… in sprites.json.",
  },
  header: {
    title: "A room's header",
    what: "The room's title and a tip about the room under it (HouseOS's own, in every theme). It can be plain, carry a banner picture, or wear a ribbon.",
    tokens: "part.header.fg · part.header.kicker · part.header.banner-fade · text.display-l",
    variants: "header: plain, banner or ribbon",
    slots: "header.banner",
  },
  panel: {
    title: "Panels",
    what: "The modules of Home and other windows onto a place: a card, no card with a hairline, or an edge only. A picture can dress every panel: a whole picture, or a frame drawn once (9-slice) that fits boxes of any size, with transparency for shaped boxes.",
    tokens:
      "part.panel.bg · part.panel.border · part.panel.radius · part.panel.shadow · part.panel.texture",
    variants: "panel: card, flat or outlined",
    slots: "panel.surface · sheet.surface",
  },
  pieces: {
    title: "Avatars and Nox",
    what: "People's pictures and the house's familiar. A theme redraws them as pixel pieces: the five pictures people pick, Nox in each of its moods.",
    tokens: "color.sprite.* (the pieces' colours) · radius.avatar · color.person.*",
    more: "Pieces: avatar.moon … avatar.ghost, nox.idle … nox.error in sprites.json.",
  },
  titles: {
    title: "House titles and medals",
    what: "Who leads the house's leaderboards. A theme names each title in its own words and draws its medal.",
    tokens: "the raised material",
    more: "Words: title.<title>.name and title.star.mark in flavor.json. Medals: title.<title> in sprites.json.",
  },
  list: {
    title: "Lists, buttons and fields",
    what: "Rows, controls, chips and states: sizes never change, their colours, corners, edges and type do. Empty states can carry a picture; their words stay HouseOS's (what's empty, what to do).",
    tokens:
      "color.* · radius.control · radius.chip · text.* · material.sunken (fields) · material.raised",
    slots: "state.empty",
  },
  nowbar: {
    title: "The Now bar",
    what: "What plays, on every page: floating over the page, or docked across it.",
    tokens:
      "part.nowbar.bg · part.nowbar.border · part.nowbar.radius · part.nowbar.shadow · part.nowbar.texture",
    variants: "nowbar: floating or docked",
    slots: "nowbar.surface",
    more: "Its keys are the transport pieces: transport.play, pause, next… in sprites.json.",
  },
};

/** Ideas to start from: a world, not a colour. Each becomes a remix of Base or a talk with Nox. */
const IDEAS: [string, string][] = [
  ["Pocket pet", "A 90s keychain pet: a candy shell, an LCD window, a pixel hatchling as Nox."],
  ["Night bathhouse", "Wet mosaic tile, a vermilion curtain, steam and a mountain mural."],
  ["Country station", "Cream enamel signs, navy lettering, one signal-red, ink stamps for medals."],
  ["Seaside radio", "Salt-faded blues, a transistor's dial, postcards pinned to the wall."],
  ["Greenhouse", "Glass panes, terracotta, seed-packet labels, a snail as the familiar."],
  ["Star chart", "Ink-blue paper, gold constellations, a telescope's round window."],
];

function useTab(): [Tab, (tab: Tab) => void] {
  const read = (): Tab => {
    const tab = new URLSearchParams(location.search).get("tab") as Tab;
    return TABS.includes(tab) ? tab : "tour";
  };
  const [tab, setTab] = useState<Tab>(read);
  useEffect(() => {
    const back = () => setTab(read());
    addEventListener("popstate", back);
    return () => removeEventListener("popstate", back);
  }, []);
  return [
    tab,
    (next) => {
      setTab(next);
      history.replaceState(null, "", next === "tour" ? "/workshop" : "/workshop?tab=" + next);
    },
  ];
}

const nameOf = (theme: ThemeInfo, language: string) =>
  language === "fr" ? theme.names.fr : theme.names.en;
const wearable = () =>
  allThemes().filter(
    (theme) => !theme.hidden && (!("status" in theme) || theme.status === "shared" || theme.mine),
  );

export function Workshop() {
  const [tab, setTab] = useTab();
  const [starting, setStarting] = useState<{ source?: string; name?: string } | null>(null);
  const user = useUser();
  return (
    <Page width="wide">
      <PageHeader
        room="me"
        kicker={t("Make it yours")}
        title={t("Theme workshop")}
        lead={t(
          "How a theme is made, part by part, and everything you need to make your own: by hand here, with Nox, or with your own tools.",
        )}
        actions={
          <Button variant="primary" icon="brush" onClick={() => setStarting({})}>
            {t("Start a theme")}
          </Button>
        }
      />
      <SubNav
        label={t("Theme workshop")}
        value={tab}
        onChange={(id) => setTab(id as Tab)}
        items={[
          { id: "tour", label: t("Tour"), icon: "compass" },
          { id: "ideas", label: t("Ideas"), icon: "sparkles" },
          { id: "pieces", label: t("Every piece"), icon: "palette" },
          { id: "make", label: t("Make one"), icon: "brush" },
        ]}
      />
      {tab === "tour" && <Tour onStart={() => setStarting({})} />}
      {tab === "ideas" && <Ideas onStart={(idea) => setStarting(idea)} />}
      {tab === "pieces" && <Pieces />}
      {tab === "make" && <Make onStart={() => setStarting({})} admin={user?.role === "admin"} />}
      {starting && (
        <StartTheme
          source={starting.source}
          name={starting.name}
          onClose={() => setStarting(null)}
        />
      )}
    </Page>
  );
}

// ---------- the tour: the app, numbered, and what shapes each part ----------
function Tour({ onStart }: { onStart: () => void }) {
  const { language } = useI18n();
  const [picked, setPicked] = useState<PreviewPart>("page");
  // The theme worn, until another is picked (the worn one may still be arriving).
  const worn = useTheme().split("/")[0] || "base";
  const [chosen, setShown] = useState("");
  const shown = chosen || worn;
  const info = PART_INFO[picked];
  const themes = wearable();
  return (
    <Stack space={6}>
      <div className="workshop-tour">
        <div className="workshop-tour__stage">
          <Field label={t("Draw it in")}>
            <Select value={shown} onChange={(e) => setShown(e.target.value)}>
              {themes.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {nameOf(theme, language)}
                </option>
              ))}
            </Select>
          </Field>
          <div className="workshop-tour__frame">
            <ThemePreview
              theme={shown}
              marks
              picked={picked}
              onPick={setPicked}
              scale={0.62}
              label={t("The app, its parts numbered")}
            />
          </div>
          <Text style="caption" tone="muted">
            {t("Pick a number to see what shapes that part.")}
          </Text>
        </div>
        <section className="workshop-part" aria-live="polite">
          <ol className="workshop-part__list">
            {PREVIEW_PARTS.map((part, i) => (
              <li key={part}>
                <Button
                  variant={part === picked ? "secondary" : "quiet"}
                  size="s"
                  aria-pressed={part === picked}
                  onClick={() => setPicked(part)}
                >
                  <span className="workshop-part__n">{i + 1}</span> {t(PART_INFO[part].title)}
                </Button>
              </li>
            ))}
          </ol>
          <div className="workshop-part__card">
            <Text as="h2" style="title-m">
              {PREVIEW_PARTS.indexOf(picked) + 1}. {t(info.title)}
            </Text>
            <Text>{t(info.what)}</Text>
            <dl>
              <dt>{t("Tokens")}</dt>
              <dd>
                <code>{info.tokens}</code>
              </dd>
              {info.variants && (
                <>
                  <dt>{t("Variants")}</dt>
                  <dd>{info.variants}</dd>
                </>
              )}
              {info.slots && (
                <>
                  <dt>{t("Art slot")}</dt>
                  <dd>
                    <code>{info.slots}</code> · {SLOTS[info.slots as keyof typeof SLOTS]?.size}
                  </dd>
                </>
              )}
              {info.more && (
                <>
                  <dt>{t("Also")}</dt>
                  <dd>{t(info.more)}</dd>
                </>
              )}
            </dl>
          </div>
        </section>
      </div>
      <Section
        title={t("From an idea to your screen")}
        lead={t(
          "Every theme, whoever makes it, goes the same way. Sizes never change: a theme can't break a room.",
        )}
      >
        <ol className="workshop-steps">
          {(
            [
              [
                "feather",
                "A brief",
                "One world, in a few lines: a place, an era, a thing. What it feels like, what it must never be.",
              ],
              [
                "palette",
                "Colours and type",
                "Seven seed colours make every shade; three faces for titles, reading and numbers. The checks keep text legible.",
              ],
              [
                "brush",
                "Parts, art and pieces",
                "Style each part, pick variants, fill the art slots, redraw Nox, the avatars and the medals, and name the house titles.",
              ],
              [
                "sparkles",
                "Life",
                "Steam, clouds, a train now and then: pictures the app moves, as far as each person's motion setting allows.",
              ],
              [
                "shield-check",
                "Checked, then worn",
                "The checks name anything unreadable or too big. Wear it yourself; an administrator shares it with the house.",
              ],
            ] as [IconName, string, string][]
          ).map(([icon, title, text], i) => (
            <li key={title}>
              <span className="workshop-steps__n">
                <Icon name={icon} />
              </span>
              <strong>
                {i + 1}. {t(title)}
              </strong>
              <Text style="body-s" tone="muted">
                {t(text)}
              </Text>
            </li>
          ))}
        </ol>
        <Cluster>
          <Button variant="primary" icon="brush" onClick={onStart}>
            {t("Start a theme")}
          </Button>
          <Button icon="sparkles" onClick={() => go("/workshop?tab=ideas")}>
            {t("See ideas")}
          </Button>
        </Cluster>
      </Section>
    </Stack>
  );
}

// ---------- ideas: the house's themes, and worlds to start from ----------
function Ideas({ onStart }: { onStart: (idea: { source?: string; name?: string }) => void }) {
  const { language } = useI18n();
  return (
    <Stack space={7}>
      <Section
        title={t("Themes in this house")}
        lead={t("Try one on for a moment, or start your own from it.")}
      >
        <Grid min="320px">
          {wearable().map((theme) => (
            <article key={theme.id} className="workshop-card">
              <div className="workshop-card__preview">
                <ThemePreview theme={theme.id} scale={0.27} label={nameOf(theme, language)} />
              </div>
              <strong>{nameOf(theme, language)}</strong>
              <Text style="body-s" tone="muted">
                {language === "fr" ? theme.description.fr : theme.description.en}
              </Text>
              <Cluster space={2}>
                <Button size="s" icon="show" onClick={() => tryOn(theme.id)}>
                  {t("Try it on")}
                </Button>
                <Button
                  size="s"
                  variant="quiet"
                  icon="brush"
                  onClick={() => onStart({ source: theme.id })}
                >
                  {t("Remix it")}
                </Button>
              </Cluster>
            </article>
          ))}
        </Grid>
      </Section>
      <Section
        title={t("Worlds to start from")}
        lead={t(
          "The best themes are one particular place or thing, followed everywhere: the mascot, the medals and the words belong to it too. Evoke it; never copy someone's characters or logos.",
        )}
      >
        <Grid min="260px">
          {IDEAS.map(([name, text]) => (
            <article key={name} className="workshop-idea">
              <strong>{t(name)}</strong>
              <Text style="body-s" tone="muted">
                {t(text)}
              </Text>
              <Cluster space={2}>
                <Button size="s" icon="brush" onClick={() => onStart({ name: t(name) })}>
                  {t("Start it by hand")}
                </Button>
                <Button
                  size="s"
                  variant="quiet"
                  icon="sparkles"
                  onClick={() =>
                    dispatchEvent(
                      new CustomEvent("houseos:ask", {
                        detail: { purpose: "themes", message: t(name) + ": " + t(text) },
                      }),
                    )
                  }
                >
                  {t("Make it with Nox")}
                </Button>
              </Cluster>
            </article>
          ))}
        </Grid>
      </Section>
    </Stack>
  );
}

// ---------- every piece: slots, redrawable pieces, parts, words, and the full specimen ----------
function Pieces() {
  return (
    <Stack space={7}>
      <Section
        title={t("What a theme can change")}
        lead={t(
          "The names to use in a theme's files. Each is optional: what a theme leaves out stays as HouseOS draws it.",
        )}
      >
        <Grid min="300px">
          <Catalogue
            title={t("Parts and their variants")}
            rows={Object.entries(PARTS).map(([part, spec]) => [
              part,
              Object.keys(spec.variants).join(" · "),
            ])}
          />
          <Catalogue
            title={t("Art slots")}
            rows={Object.entries(SLOTS).map(([slot, spec]) => [slot, spec.size])}
          />
          <Catalogue
            title={t("Pieces to redraw")}
            rows={Object.entries(
              Object.keys(PIECES).reduce<Record<string, string[]>>((groups, id) => {
                const [group, name] = id.split(".");
                (groups[group] ??= []).push(name);
                return groups;
              }, {}),
            ).map(([group, names]) => [group + ".*", names.join(", ")])}
          />
        </Grid>
      </Section>
      <Workbench bare />
    </Stack>
  );
}

function Catalogue({ title, rows }: { title: string; rows: [string, ReactNode][] }) {
  return (
    <article className="workshop-catalogue">
      <strong>{title}</strong>
      <dl>
        {rows.map(([name, text]) => (
          <div key={name}>
            <dt>
              <code>{name}</code>
            </dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

// ---------- make one: three ways ----------
function Make({ onStart, admin }: { onStart: () => void; admin: boolean }) {
  return (
    <Grid min="300px">
      <article className="workshop-way">
        <Icon name="brush" size="l" />
        <Text as="h2" style="title-m">
          {t("By hand, here")}
        </Text>
        <Text>
          {t(
            "Remix any theme: its colours, type, corners, surfaces, parts, pictures, pixel pieces and words, with a live preview. The checks keep it readable. No AI needed.",
          )}
        </Text>
        <Button variant="primary" icon="brush" onClick={onStart}>
          {t("Start a theme")}
        </Button>
      </article>
      <article className="workshop-way">
        <Icon name="sparkles" size="l" />
        <Text as="h2" style="title-m">
          {t("With Nox")}
        </Text>
        <Text>
          {t(
            "Tell Nox a feeling, a place or an era, or show a picture: it proposes three directions, builds the one you choose, draws its pieces and checks it.",
          )}
        </Text>
        <Button icon="sparkles" onClick={() => go("/control?tab=themes")}>
          {t("Open the theme studio")}
        </Button>
        {admin && (
          <Text style="caption" tone="muted">
            {t("Nox needs its own model for this: Control Room → AI → Theme studio.")}
          </Text>
        )}
      </article>
      <article className="workshop-way">
        <Icon name="file-text" size="l" />
        <Text as="h2" style="title-m">
          {t("With your own tools")}
        </Text>
        <Text>
          {t(
            "A theme is a folder of data. Export one as a file, change it with any editor or your own AI agent following the theme guide, check it with the theme kit, and bring the file back.",
          )}
        </Text>
        <pre className="workshop-way__code">
          {`python3 -m houseos.theme_kit new my-theme
python3 -m houseos.theme_kit check my-theme
python3 -m houseos.theme_kit pack my-theme`}
        </pre>
        <Cluster space={2}>
          <Button icon="download" onClick={() => go("/me?tab=appearance")}>
            {t("Export or bring a theme")}
          </Button>
          <Button
            variant="link"
            onClick={() =>
              window.open(
                "https://github.com/boitech-dev/HouseOS/blob/HEAD/themes/README.md",
                "_blank",
                "noopener",
              )
            }
          >
            {t("Read the theme guide")}
          </Button>
        </Cluster>
      </article>
    </Grid>
  );
}

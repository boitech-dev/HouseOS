// The Workbench (/workbench, everyone who lives here): every piece of the design system in every variant and state,
// in the theme in force, and side by side with other themes. For reviewing a theme or a component.
import { Fragment, useState, type CSSProperties, type ReactNode } from "react";
import { t, getLanguage } from "./i18n";
import { percent } from "./api";
import { Avatar, Badge, Button, Checkbox, Chip, ChipGroup, CommandPalette, ConfirmSheet, Disclosure, Divider, Field, Glyph, Grid, Hint, Icon, ICON_NAMES, IconButton, Input, Kbd, List, ListRow, Mascot, type Material, Media, MediaCard, Menu, Notice, Page, PageHeader, Panel as DsPanel, Progress, QuickAdd, Radio, Scene, SearchInput, Section, Segmented, Select, SettingsLayout, Sheet, type SheetPlace, Shelf, Skeleton, Slider, Stack, State, Status, SubNav, Surface, Switch, Text, Textarea, Tile, toast, Toolbar, Tooltip, useMotion } from "./design"; // prettier-ignore
import { allThemes, partData, SchemeScope, surfaceVars, ThemeScope } from "./design/theme";
import type { ThemeInfo } from "./design/generated/themes";
import { AVATARS, CANDLE, NOX } from "./sprites";
import { Sprite } from "./design/motion";

const MATERIALS: Material[] = [
  "surface",
  "raised",
  "sunken",
  "overlay",
  "inverse",
  "paper",
  "screen",
];
const at = (hour: number) => {
  const date = new Date();
  date.setHours(hour, 0, 0, 0);
  return date;
};

const ROOMS = ["home", "listen", "watch", "house", "files", "ask", "me", "control"];
const PEOPLE = [1, 2, 3, 4, 5, 6, 7, 8];
const SECTIONS: [string, string][] = [
  ["buttons", "Buttons"],
  ["fields", "Fields and choices"],
  ["status", "Status and people"],
  ["colours", "Colours"],
  ["icons", "Icons"],
  ["materials", "Materials"],
  ["text", "Text styles"],
  ["identity", "Identity"],
  ["parts", "Page parts"],
  ["states", "States"],
  ["settings", "Settings"],
  ["sheets", "Sheets"],
];

/** The whole specimen, drawn in whatever theme surrounds it (`scope` keeps ids apart when
 *  several are on the page). */
function Specimen({ scope = "", picker }: { scope?: string; picker?: ReactNode }) {
  const [sheet, setSheet] = useState<SheetPlace | "">("");
  const [confirm, setConfirm] = useState(false);
  const [palette, setPalette] = useState(false);
  const [on, setOn] = useState(true);
  const [kind, setKind] = useState("films");
  const [chips, setChips] = useState(["Drama"]);
  const [volume, setVolume] = useState(40);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState("board");
  const [setting, setSetting] = useState("");
  const motion = useMotion();
  return (
    <Stack space={7}>
      <PageHeader
        kicker={t("Design system")}
        title={picker ? t("Workbench") : t("A page title")}
        lead={t("Every piece of the interface, in every state. Motion in force:") + " " + motion}
        actions={
          <Button variant="primary" icon="palette" onClick={() => setPalette(true)}>
            {t("Command palette")}
          </Button>
        }
        hint={<Hint id="workbench-demo">{t("A one-time hint sits here, under the title.")}</Hint>}
      />
      {picker}
      <nav className="ds-cluster" aria-label={t("Sections")}>
        {SECTIONS.map(([id, title]) => (
          <Button
            key={id}
            variant="link"
            size="s"
            onClick={() =>
              document.getElementById("wb-" + scope + id)?.scrollIntoView({ behavior: "smooth" })
            }
          >
            {t(title)}
          </Button>
        ))}
      </nav>

      <Section title={t("Buttons")} id={"wb-" + scope + "buttons"}>
        {(["primary", "secondary", "quiet", "danger", "link"] as const).map((variant) => (
          <div key={variant} className="ds-cluster">
            <Text style="label" tone="muted">
              {variant}
            </Text>
            {(["s", "m", "l"] as const).map((size) => (
              <Button key={size} variant={variant} size={size} icon="play">
                {t("Play")} {size}
              </Button>
            ))}
            <Button variant={variant} disabled>
              {t("Disabled")}
            </Button>
            <Button variant={variant} busy>
              {t("Working…")}
            </Button>
          </div>
        ))}
        <div className="ds-cluster">
          <Button pressed icon="heart">
            {t("Pressed")}
          </Button>
          <IconButton icon="more" label={t("More")} />
          <IconButton icon="close" label={t("Close")} variant="secondary" />
          <Menu
            label={t("More")}
            items={[
              { label: t("Rename"), icon: "edit", onSelect: () => toast(t("Renamed.")) },
              { label: t("Delete"), icon: "trash", danger: true, onSelect: () => setConfirm(true) },
            ]}
          />
        </div>
      </Section>

      <Section title={t("Fields and choices")} id={"wb-" + scope + "fields"}>
        <Grid min="260px">
          <Field label={t("Name")} hint={t("As the house will see it.")}>
            <Input defaultValue="Visual" />
          </Field>
          <Field label={t("Password")} error={t("Use at least 12 characters.")}>
            <Input type="password" defaultValue="short" />
          </Field>
          <Field label={t("Room")}>
            <Select defaultValue="kitchen">
              <option value="kitchen">Kitchen</option>
              <option value="office">Office</option>
            </Select>
          </Field>
          <Field label={t("A note")}>
            <Textarea placeholder={t("Write something…")} />
          </Field>
          <SearchInput label={t("Search")} value={query} onChange={setQuery} />
          <Slider
            label={t("Volume")}
            value={volume}
            onCommit={setVolume}
            showLabel
            format={percent}
          />
        </Grid>
        <div className="ds-cluster">
          <Switch
            checked={on}
            onChange={setOn}
            label={t("Night mode")}
            hint={t("Applied at once.")}
          />
          <Checkbox label={t("Remember this device")} defaultChecked />
          <Radio label={t("Films")} name="demo-radio" defaultChecked />
          <Radio label={t("Series")} name="demo-radio" />
        </div>
        <Segmented
          label={t("Kind")}
          value={kind}
          onChange={setKind}
          options={[
            { value: "films", label: t("Films"), icon: "film" },
            { value: "series", label: t("Series"), icon: "tv" },
            { value: "anime", label: t("Anime") },
          ]}
        />
        <ChipGroup label={t("Genres")}>
          {["Drama", "Comedy", "Horror"].map((name) => (
            <Chip
              key={name}
              kind="filter"
              selected={chips.includes(name)}
              onToggle={() =>
                setChips((c) => (c.includes(name) ? c.filter((x) => x !== name) : [...c, name]))
              }
            >
              {name}
            </Chip>
          ))}
          <Chip kind="tag">{t("Downloaded")}</Chip>
          <Chip kind="count" count={12}>
            {t("Songs")}
          </Chip>
          <Chip kind="person" tone="var(--c-person-3)" onRemove={() => toast(t("Removed."))}>
            Alice
          </Chip>
        </ChipGroup>
      </Section>

      <Section title={t("Status and people")} id={"wb-" + scope + "status"}>
        <div className="ds-cluster">
          {(["neutral", "accent", "success", "warning", "danger", "info", "private"] as const).map(
            (tone) => (
              <Status key={tone} tone={tone}>
                {tone}
              </Status>
            ),
          )}
          <Status tone="info" busy>
            {t("Checking…")}
          </Status>
        </div>
        <div className="ds-cluster">
          <Badge>3</Badge>
          <Badge tone="neutral">12</Badge>
          <Badge tone="danger">!</Badge>
          {Object.keys(AVATARS).map((name, i) => (
            <Avatar
              key={name}
              name={name}
              picture={name}
              tone={`var(--c-person-${i + 1})`}
              home={i % 2 === 0}
            />
          ))}
          <Tooltip text={t("A short hint")}>
            <Kbd>Ctrl</Kbd>
          </Tooltip>
        </div>
        <Grid min="200px">
          <Progress label={t("Progress")} value={0.6} />
          <Progress label={t("Progress")} value={0.4} steps={12} />
          <Progress label={t("Progress")} busy />
          <Skeleton lines={2} />
        </Grid>
      </Section>

      <Section title={t("Colours")} id={"wb-" + scope + "colours"}>
        {(
          [
            ["Rooms", ROOMS.map((room) => ["--c-room-" + room, room])],
            ["People", PEOPLE.map((n) => ["--c-person-" + n, String(n)])],
            ["Charts", PEOPLE.map((n) => ["--c-data-" + n, String(n)])],
          ] as [string, string[][]][]
        ).map(([title, swatches]) => (
          <div key={title} className="ds-workbench__row">
            <Text style="label" tone="muted">
              {t(title)}
            </Text>
            <div className="ds-cluster">
              {swatches.map(([name, word]) => (
                <span key={name} className="ds-workbench__chip" title={name}>
                  <i style={{ "--swatch": `var(${name})` } as CSSProperties} />
                  {word}
                </span>
              ))}
            </div>
          </div>
        ))}
        <Grid min="220px">
          {(["neutral", "accent", "success", "warning", "danger", "info", "private"] as const).map(
            (tone) => (
              <Notice key={tone} tone={tone} title={tone}>
                {t("A notice in this tone.")}
              </Notice>
            ),
          )}
        </Grid>
      </Section>

      <Section title={t("Icons")} id={"wb-" + scope + "icons"}>
        <div className="ds-workbench__icons">
          {ICON_NAMES.map((name) => (
            <span key={name} title={name}>
              <Icon name={name} />
              <Text style="caption" tone="muted">
                {name}
              </Text>
            </span>
          ))}
        </div>
        <div className="ds-cluster">
          {(["s", "m", "l"] as const).map((size) => (
            <Glyph key={size} name="room.listen" size={size} label={"room.listen " + size} />
          ))}
          {(["s", "m", "l"] as const).map((size) => (
            <Mascot key={size} size={size} label={"Nox " + size} />
          ))}
          {(["s", "m", "l"] as const).map((size) => (
            <Avatar key={size} name="Alice" tone="var(--c-person-2)" size={size} />
          ))}
        </div>
      </Section>

      <Section title={t("Materials")} id={"wb-" + scope + "materials"}>
        <Grid min="160px">
          {MATERIALS.map((material) => (
            <Surface key={material} material={material} className="ds-workbench__swatch">
              <Text style="title-s">{material}</Text>
              <Text
                style="body-s"
                tone={material === "inverse" || material === "paper" ? undefined : "muted"}
              >
                {t("Text on it")}
              </Text>
            </Surface>
          ))}
        </Grid>
      </Section>

      <Section title={t("Text styles")} id={"wb-" + scope + "text"}>
        {(
          [
            "display-xl",
            "display-l",
            "display-m",
            "title-l",
            "title-m",
            "title-s",
            "body-l",
            "body-m",
            "body-s",
            "action",
            "label",
            "caption",
            "numeric",
          ] as const
        ).map((style) => (
          <Text key={style} as="p" style={style}>
            {style} · {t("A house, together.")} 12:45
          </Text>
        ))}
      </Section>

      <Section title={t("Identity")} id={"wb-" + scope + "identity"}>
        <div className="ds-cluster">
          {(
            [
              "room.home",
              "room.listen",
              "room.watch",
              "room.house",
              "room.files",
              "room.smart-home",
              "room.me",
              "transport.play",
              "transport.pause",
              "transport.next",
            ] as const
          ).map((name) => (
            <Glyph key={name} name={name} label={name} />
          ))}
          {(["idle", "listening", "thinking", "happy", "error"] as const).map((mood) => (
            <Mascot key={mood} mood={mood} label={mood} />
          ))}
          <Sprite frames={CANDLE} scale={3} fps={4} />
          <Sprite grid={NOX.happy} scale={3} />
        </div>
        <Grid min="200px">
          {[21, 6, 12, 18].map((hour) => (
            <Scene key={hour} date={at(hour)} lit={3} width={160} height={48} />
          ))}
        </Grid>
      </Section>

      <Section title={t("Page parts")} id={"wb-" + scope + "parts"}>
        <SubNav
          label={t("House")}
          value={tab}
          onChange={setTab}
          items={[
            { id: "board", label: t("Board") },
            { id: "tasks", label: t("Tasks"), count: 3 },
            { id: "groceries", label: t("Groceries") },
          ]}
        />
        <Toolbar label={t("Search")}>
          <SearchInput label={t("Search")} value={query} onChange={setQuery} />
          <Button icon="filter">{t("Filters")}</Button>
        </Toolbar>
        <Grid min="260px">
          <DsPanel icon="music" title={t("Now playing")} href="/listen">
            <Text tone="muted">{t("A panel: a window onto a place, on Home.")}</Text>
          </DsPanel>
          <DsPanel icon="star" title={t("House titles")}>
            <Progress label={t("Progress")} value={0.6} />
          </DsPanel>
        </Grid>
        <List label={t("Rows")}>
          <ListRow
            leading={<Icon name="music" />}
            title="Clair de Lune"
            detail="Claude Debussy"
            meta="5:00"
            onOpen={() => toast(t("Opened."))}
            actions={<IconButton icon="more" label={t("More")} />}
          />
          <ListRow
            leading={<Avatar name="Alice" picture="rose" tone="var(--c-person-4)" size="s" />}
            title="Alice"
            detail={t("Home")}
            status={{ tone: "success", text: t("Ready") }}
          />
          <ListRow
            leading={<Icon name="file-text" />}
            title="notes.txt"
            detail="2 KB"
            selected
            status={{ tone: "info", text: t("Uploading"), busy: true }}
          />
        </List>
        <Shelf
          title={t("Continue watching")}
          action={
            <Button variant="link" size="s">
              {t("See all")}
            </Button>
          }
        >
          {[
            "Spirited Away",
            "Paprika",
            "Perfect Blue",
            "Tokyo Godfathers",
            "Millennium Actress",
            "Your Name",
          ].map((title) => (
            <li key={title}>
              <MediaCard
                media={<Media alt={title} />}
                title={title}
                meta="2001"
                onOpen={() => toast(title)}
              />
            </li>
          ))}
        </Shelf>
        <Grid min="200px">
          <Tile
            glyph="room.listen"
            title={t("Listen")}
            value="3"
            detail={t("in the queue")}
            onOpen={() => toast(t("Listen"))}
          />
          <Tile
            glyph="room.house"
            title={t("House")}
            value="2"
            detail={t("tasks today")}
            onOpen={() => toast(t("House"))}
          />
          <Tile
            icon="inbox"
            title={t("Inbox")}
            value="0"
            detail={t("all read")}
            onOpen={() => toast(t("Inbox"))}
          />
        </Grid>
        <QuickAdd label={t("Add to the groceries")} onAdd={async (text) => toast(text)} />
        <Grid min="240px">
          <Notice tone="info">{t("Something to know.")}</Notice>
          <Notice tone="success" title={t("Ready")}>
            {t("All six essentials are set.")}
          </Notice>
          <Notice tone="warning">{t("Storage is almost full.")}</Notice>
          <Notice tone="danger" onDismiss={() => undefined}>
            {t("The TV didn't answer.")}
          </Notice>
          <Notice
            title={t("2 / 6 essentials ready")}
            action={<Button size="s">{t("Continue")}</Button>}
            onDismiss={() => undefined}
          >
            {t("Something to know.")}
          </Notice>
        </Grid>
        <Disclosure summary={t("More options")}>
          <Text>{t("Something to know.")}</Text>
        </Disclosure>
      </Section>

      <Section title={t("States")} id={"wb-" + scope + "states"}>
        <Grid min="220px">
          {(
            ["empty", "loading", "error", "offline", "not-configured", "no-permission"] as const
          ).map((kind) => (
            <Surface key={kind}>
              <State kind={kind} onRetry={kind === "error" ? () => undefined : undefined}>
                {kind === "loading" ? undefined : kind}
              </State>
            </Surface>
          ))}
        </Grid>
      </Section>

      <Section title={t("Settings")} id={"wb-" + scope + "settings"}>
        <SettingsLayout
          label={t("Settings")}
          value={setting}
          onChange={setSetting}
          overview={<Notice>{t("Pick a place on the left.")}</Notice>}
          groups={[
            {
              label: t("You"),
              items: [
                { id: "profile", label: t("Profile"), icon: "person" },
                { id: "appearance", label: t("Appearance"), icon: "palette" },
              ],
            },
            {
              label: t("House"),
              items: [
                {
                  id: "people",
                  label: t("People"),
                  icon: "people",
                  badge: <Badge tone="neutral">4</Badge>,
                },
              ],
            },
          ]}
        >
          <Section title={t("Appearance")} level={3}>
            <Divider />
          </Section>
        </SettingsLayout>
      </Section>

      <Section title={t("Sheets")} id={"wb-" + scope + "sheets"}>
        <div className="ds-cluster">
          {(["bottom", "side", "center"] as const).map((place) => (
            <Button key={place} onClick={() => setSheet(place)}>
              {t("Open a sheet")} ({place})
            </Button>
          ))}
          <Button
            onClick={() =>
              toast(t("Saved."), { action: { label: t("Undo"), run: () => undefined } })
            }
          >
            {t("Show a toast")}
          </Button>
        </div>
      </Section>

      {sheet && (
        <Sheet
          title={t("Change the audio")}
          place={sheet}
          onClose={() => setSheet("")}
          footer={
            <>
              <Button variant="quiet" onClick={() => setSheet("")}>
                {t("Cancel")}
              </Button>
              <Button variant="primary" onClick={() => setSheet("")}>
                {t("Apply")}
              </Button>
            </>
          }
        >
          <Stack>
            <Field label={t("Language")}>
              <Select defaultValue="fr">
                <option value="fr">Français</option>
                <option value="en">English</option>
              </Select>
            </Field>
            <Slider label={t("Volume")} value={volume} onCommit={setVolume} showLabel />
          </Stack>
        </Sheet>
      )}
      {confirm && (
        <ConfirmSheet
          title={t("Delete this?")}
          confirm={t("Delete")}
          danger
          onConfirm={() => toast(t("Deleted."))}
          onClose={() => setConfirm(false)}
        >
          <p>{t("It can't be brought back.")}</p>
        </ConfirmSheet>
      )}
      {palette && (
        <CommandPalette
          onClose={() => setPalette(false)}
          onAsk={(text) => toast(text)}
          quick={[
            {
              id: "q-song",
              label: t("Add a song"),
              group: t("Music"),
              icon: "music",
              mode: {
                label: t("Add a song"),
                placeholder: t("A song, an artist or a link"),
                submit: (text) => toast(text),
              },
            },
            {
              id: "q-grocery",
              label: t("Add to the groceries"),
              group: t("House"),
              icon: "basket",
              run: () => toast(t("Add to the groceries")),
            },
          ]}
          commands={[
            {
              id: "listen",
              label: t("Listen"),
              group: t("Rooms"),
              icon: "music",
              run: () => toast(t("Listen")),
            },
            {
              id: "watch",
              label: t("Watch"),
              group: t("Rooms"),
              icon: "tv",
              run: () => toast(t("Watch")),
            },
          ]}
        />
      )}
    </Stack>
  );
}

/** Other themes beside the one in force (each panel is scoped: data-theme on the panel). */
export function Workbench({ bare = false }: { bare?: boolean }) {
  const [compare, setCompare] = useState<string[]>([]);
  const [shown, setShown] = useState("");
  const themes = allThemes()
    .filter((theme) => !theme.hidden)
    .flatMap((theme) =>
      theme.schemes.map((scheme) => ({ key: theme.id + "/" + scheme, theme, scheme })),
    );
  const name = (theme: ThemeInfo, scheme: string) =>
    (getLanguage() === "fr" ? theme.names.fr : theme.names.en) +
    (theme.schemes.length > 1 ? " · " + t(scheme === "light" ? "Light" : "Dark") : "");
  const [theme, scheme] = shown.split("/");
  const picker = (
    <Section
      title={t("Draw it in")}
      lead={t(
        "Every piece below, in the theme you pick. Your own theme doesn't change; pixel art keeps the colours of the theme you wear.",
      )}
    >
      <ChipGroup label={t("Draw it in")}>
        <Chip kind="filter" selected={!shown} onToggle={() => setShown("")}>
          {t("The theme I wear")}
        </Chip>
        {themes.map(({ key, theme, scheme }) => (
          <Chip
            key={key}
            kind="filter"
            selected={shown === key}
            onToggle={() => setShown(shown === key ? "" : key)}
          >
            {name(theme, scheme)}
          </Chip>
        ))}
      </ChipGroup>
    </Section>
  );
  const Frame = bare ? Fragment : Page;
  return (
    <Frame {...(bare ? {} : { width: "wide" as const })}>
      {shown ? (
        <section
          className="ds-scope"
          data-theme={theme}
          data-scheme={scheme}
          {...partData(theme)}
          style={surfaceVars(theme, null, "home", scheme) as CSSProperties}
          aria-label={shown}
        >
          <ThemeScope.Provider value={theme}>
            <SchemeScope.Provider value={scheme}>
              <Specimen scope="shown-" picker={picker} />
            </SchemeScope.Provider>
          </ThemeScope.Provider>
        </section>
      ) : (
        <Specimen picker={picker} />
      )}
      <Section
        title={t("Compare themes")}
        lead={t("Each panel draws the same pieces in another theme.")}
      >
        <ChipGroup label={t("Themes")}>
          {themes.map(({ key, theme, scheme }) => (
            <Chip
              key={key}
              kind="filter"
              selected={compare.includes(key)}
              onToggle={() =>
                setCompare((c) => (c.includes(key) ? c.filter((x) => x !== key) : [...c, key]))
              }
            >
              {name(theme, scheme)}
            </Chip>
          ))}
        </ChipGroup>
      </Section>
      <div className="ds-workbench__compare">
        {compare.map((key) => {
          const [theme, scheme] = key.split("/");
          return <Panel key={key} theme={theme} scheme={scheme} />;
        })}
      </div>
    </Frame>
  );
}

function Panel({ theme, scheme }: { theme: string; scheme: string }): ReactNode {
  return (
    <section
      className="ds-scope"
      data-theme={theme}
      data-scheme={scheme}
      {...partData(theme)}
      style={surfaceVars(theme, null, "home", scheme) as CSSProperties}
      data-room="listen"
      aria-label={theme + " · " + scheme}
    >
      <ThemeScope.Provider value={theme}>
        <SchemeScope.Provider value={scheme}>
          <Specimen scope={theme + "-" + scheme + "-"} />
        </SchemeScope.Provider>
      </ThemeScope.Provider>
    </section>
  );
}

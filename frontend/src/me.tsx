// Me: a person's own settings (profile, look, comfort, security, films, notifications, Nox's
// memory and AI usage), as a list of places beside the chosen one (SettingsLayout).
import { t, getLanguage } from "./i18n";
import { useState, type CSSProperties, type ReactNode } from "react";
import { AI_PROVIDERS } from "./providers";
import { localStore } from "./local";
import { api, number, useData, useUser, items, pretty, time, type Obj } from "./api";
import { go } from "./nav";
import { Assistant } from "./ask";
import { ThemeLook, handToNox } from "./theme_preview";
import {
  allThemes,
  renamed,
  setInstalled,
  tryOn,
  useInstalled,
  useTheme,
  type Installed,
} from "./design/theme";
import type { ThemeInfo } from "./design/generated/themes";
import {
  Avatar,
  AVATAR_NAMES,
  AvatarPicture,
  Badge,
  Button,
  Checkbox,
  Cluster,
  ConfirmSheet,
  Disclosure,
  Field,
  Form,
  Icon,
  IconButton,
  Input,
  LinkButton,
  List,
  ListRow,
  Menu,
  Page,
  PageHeader,
  Problem,
  Radio,
  ReviewDetails,
  Section,
  Segmented,
  Select,
  type SettingsGroup,
  SettingsLayout,
  Sheet,
  State,
  Switch,
  Text,
  Textarea,
  tone,
  toast,
  FileButton,
} from "./design";
import "./me.css";

// Old links (#pref-comfort…) open the matching place.
const ANCHORS: Record<string, string> = {
  "pref-profile": "profile",
  "pref-comfort": "comfort",
  "pref-films": "films",
  "pref-security": "security",
  "pref-alerts": "notifications",
  "pref-memory": "memory",
  "pref-usage": "usage",
};
const initialPlace = () =>
  new URLSearchParams(location.search).get("tab") || ANCHORS[location.hash.slice(1)] || "";

export function Preferences({ user }: { user: Obj }) {
  const canCinema = user.role === "admin" || user.permissions?.includes("cinema.use");
  const canAssistant = user.role === "admin" || user.permissions?.includes("assistant.use");
  const canAlerts = user.role === "admin" || user.permissions?.includes("messages.read");
  const [place, setPlace] = useState(initialPlace);
  const open = (next: string) => {
    setPlace(next);
    history.replaceState(null, "", next ? "/me?tab=" + next : "/me");
    scrollTo({ top: 0 });
  };
  const groups: SettingsGroup[] = [
    {
      label: t("You"),
      items: [
        { id: "profile", label: t("Profile"), icon: "person" },
        { id: "appearance", label: t("Appearance"), icon: "palette" },
        { id: "comfort", label: t("Comfort"), icon: "moon" },
        { id: "security", label: t("Security"), icon: "lock" },
      ],
    },
    {
      label: t("Everyday"),
      items: [
        ...(canCinema ? [{ id: "films", label: t("Films"), icon: "film" as const }] : []),
        ...(canAlerts
          ? [{ id: "notifications", label: t("Notifications"), icon: "bell" as const }]
          : []),
      ],
    },
    {
      label: "Nox",
      items: canAssistant ? [{ id: "memory", label: t("Nox's memory"), icon: "bot" }] : [],
    },
  ].filter((group) => group.items.length) as SettingsGroup[];
  return (
    <Page>
      <PageHeader room="me" title={t("Your preferences")} />
      <SettingsLayout
        label={t("Your preferences")}
        groups={groups}
        value={place}
        onChange={open}
        overview={<MeOverview user={user} onOpen={open} nox={canAssistant} />}
      >
        {place === "profile" && <AccountPreferences />}
        {place === "appearance" && <Appearance />}
        {place === "comfort" && <Comfort />}
        {place === "security" && <Security user={user} />}
        {place === "films" && canCinema && <FilmPreferences />}
        {place === "notifications" && canAlerts && <PushPreferences />}
        {place === "memory" && canAssistant && <MemoryPreferences />}
      </SettingsLayout>
    </Page>
  );
}

/** The first thing on Me: who you are here and how the house looks for you. */
function MeOverview({
  user,
  onOpen,
  nox,
}: {
  user: Obj;
  onOpen: (place: string) => void;
  nox: boolean;
}) {
  const { data } = useData("/preferences");
  const house = useData("/house-settings");
  const sessions = useData("/auth/sessions");
  const memories = useData(nox ? "/assistant/memories" : null);
  const count = (template: string, n?: number | null) =>
    n == null ? "…" : t(template).replace("{n}", String(n));
  const current = useTheme().split("/")[0];
  const theme = allThemes().find((item) => item.id === current);
  return (
    <div className="ds-settings__overview me-overview">
      <div className="me-overview__who">
        <Avatar name={user.name} picture={user.avatar} tone={tone(user.id)} size="l" />
        <div>
          <Text as="h2" style="title-l">
            {user.name}
          </Text>
          <Text tone="muted">@{user.username}</Text>
        </div>
      </div>
      <List label={t("At a glance")}>
        <ListRow
          leading={<Icon name="palette" />}
          title={t("Look")}
          detail={
            (theme ? themeName(theme) : current) +
            (data && !data.theme ? " · " + t("same as the house") : "")
          }
          onOpen={() => onOpen("appearance")}
        />
        <ListRow
          leading={<Icon name="clock" />}
          title={t("Clock and time zone")}
          detail={
            (data?.time_display === "12h" ? t("12 hour") : t("24 hour")) +
            " · " +
            (data?.timezone || house.data?.timezone || "UTC")
          }
          onOpen={() => onOpen("comfort")}
        />
        <ListRow
          leading={<Icon name="lock" />}
          title={t("Security")}
          detail={count("{n} signed-in sessions", sessions.data && items(sessions.data).length)}
          onOpen={() => onOpen("security")}
        />
        {nox && (
          <ListRow
            leading={<Icon name="bot" />}
            title={t("Nox's memory")}
            detail={count(
              "{n} things Nox keeps in mind",
              memories.data && items(memories.data).length,
            )}
            onOpen={() => onOpen("memory")}
          />
        )}
      </List>
    </div>
  );
}

// ---------- Appearance: the theme, its light or dark, motion, and the interface ----------
const themeName = (theme: ThemeInfo) => (getLanguage() === "fr" ? theme.names.fr : theme.names.en);

/** Pick a theme among cards drawn in themselves; `house` adds a "Same as the house" switch above
 *  them (value "": follow the house, whose card then shows as the one in use). */
export function ThemePicker({
  label,
  value,
  scheme,
  onChange,
  house,
  own = false,
}: {
  label: string;
  value: string;
  scheme?: string;
  onChange: (id: string) => void;
  /** A person's own choice: their drafts are offered too. */
  own?: boolean;
  /** The house's theme, when the choice may follow it (value ""). */
  house?: ThemeInfo;
}) {
  useInstalled();
  // A person may wear their own drafts; the house only bundled and shared themes.
  value = renamed(value) ?? "";
  const themes = allThemes().filter(
    (theme) =>
      (!theme.hidden || theme.id === value) &&
      (!("status" in theme) || theme.status === "shared" || (own && theme.mine)),
  );
  const name = label.replace(/\W+/g, "-").toLowerCase();
  const shown = value || house?.id;
  return (
    <>
      {house && (
        <Switch
          checked={!value}
          onChange={(on) => onChange(on ? "" : house.id)}
          label={t("Same as the house")}
          hint={getLanguage() === "fr" ? house.names.fr : house.names.en}
        />
      )}
      <fieldset className="me-themes">
        <legend className="visually-hidden">{label}</legend>
        {themes.map((theme) => (
          <Radio
            key={theme.id}
            name={name}
            checked={shown === theme.id}
            onChange={() => onChange(theme.id)}
            label={<ThemeCard theme={theme} scheme={shown === theme.id ? scheme : undefined} />}
          />
        ))}
      </fieldset>
    </>
  );
}

/** A theme to pick, drawn in itself: the app in miniature (rail, panels, art, type), then its
 *  name in its own letters and a line about it. Every card the same size. */
function ThemeCard({ theme, scheme }: { theme: ThemeInfo; scheme?: string }) {
  const shown = scheme && theme.schemes.includes(scheme as never) ? scheme : theme.schemes[0];
  const fr = getLanguage() === "fr";
  return (
    <span className="ds-scope me-theme" data-theme={theme.id} data-scheme={shown}>
      {/* A picture of the theme: the name below says it (the radio's label). */}
      <span className="me-theme__look" aria-hidden="true">
        <ThemeLook theme={theme} scheme={shown} scale={0.16} />
      </span>
      <strong className="me-theme__name">{fr ? theme.names.fr : theme.names.en}</strong>
      <small className="me-theme__about">{fr ? theme.description.fr : theme.description.en}</small>
    </span>
  );
}

/** Light or dark, for a theme that has both. */
export function SchemeChoice({
  theme,
  value,
  onChange,
}: {
  theme?: ThemeInfo;
  value: string;
  onChange: (scheme: string) => void;
}) {
  if (!theme || theme.schemes.length < 2) return null;
  return (
    <Segmented
      label={t("Light or dark")}
      value={value}
      onChange={onChange}
      options={[
        { value: "", label: t("Theme's own") },
        { value: "dark", label: t("Dark") },
        { value: "light", label: t("Light") },
        { value: "device", label: t("Device") },
      ]}
    />
  );
}

const refreshInstalled = () =>
  api("/themes").then(
    (value) => setInstalled(value.items),
    () => {},
  );

/** Themes made here. Yours: wear, export, ask to share, remove. For an administrator (`admin`):
 *  what people ask to share, and what the house shares. Packs come in through the file field. */
export function MadeHere({ admin = false, onStudio }: { admin?: boolean; onStudio?: () => void }) {
  const list = useInstalled();
  const isAdmin = useUser()?.role === "admin";
  const [removing, setRemoving] = useState<Installed | null>(null);
  const [busy, setBusy] = useState(false);
  const shown = admin
    ? list.filter((item) => item.status !== "draft")
    : list.filter((item) => item.mine);
  const act = async (item: Installed, status: Installed["status"], done: string) => {
    try {
      await api(`/themes/${item.id}/status`, "PUT", { status });
      await refreshInstalled();
      toast(done);
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    }
  };
  const words: Record<Installed["status"], string> = {
    draft: t("Only you"),
    requested: admin ? t("{name} asks to share it") : t("Waiting for an administrator"),
    shared: t("Shared with the house"),
  };
  const importPack = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const made = await api<Installed & { replaced?: number | null }>(
        "/themes/import",
        "POST",
        body,
      );
      await refreshInstalled();
      toast(
        made.replaced
          ? t("{name} replaced your version {n}.")
              .replace("{name}", themeName(made))
              .replace("{n}", String(made.replaced))
          : t("{name} is ready to wear.").replace("{name}", themeName(made)),
      );
    } catch (e) {
      // A pack that fails its checks says which ones (the kit's own words).
      const failures = (e as { detail?: { failures?: string[] } }).detail?.failures ?? [];
      toast([(e as Error).message, ...failures.slice(0, 2)].join(" · "), { tone: "danger" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {shown.length ? (
        <List label={admin ? t("Themes people made") : t("Your themes")}>
          {shown.map((item) => (
            <ListRow
              key={item.id}
              leading={<Icon name="palette" />}
              title={themeName(item)}
              detail={words[item.status].replace("{name}", item.owner.name)}
              actions={
                <>
                  {admin && item.status === "requested" && (
                    <Button size="s" icon="show" onClick={() => tryOn(item.id)}>
                      {t("Try it on")}
                    </Button>
                  )}
                  {admin && item.status === "requested" && (
                    <Button
                      size="s"
                      onClick={() => void act(item, "shared", t("Shared with the house."))}
                    >
                      {t("Share")}
                    </Button>
                  )}
                  {!admin && item.mine && (
                    <Button
                      size="s"
                      icon="brush"
                      onClick={() => go("/workshop/remix?id=" + encodeURIComponent(item.id))}
                    >
                      {t("Edit")}
                    </Button>
                  )}
                  {!admin && item.mine && (
                    <Button
                      size="s"
                      icon="sparkles"
                      onClick={() => handToNox(item.id, themeName(item))}
                    >
                      {t("Ask Nox")}
                    </Button>
                  )}
                  <Menu
                    label={t("More for {name}").replace("{name}", themeName(item))}
                    items={[
                      { label: t("Try it on"), icon: "show" as const, onSelect: () => tryOn(item.id) },
                      ...(!admin && item.status === "draft" && isAdmin
                        ? [{ label: t("Share it with the house"), icon: "people" as const, onSelect: () => void act(item, "shared", t("Shared with the house.")) }]
                        : []),
                      ...(!admin && item.status === "draft" && !isAdmin
                        ? [{ label: t("Ask to share it with the house"), icon: "send" as const, onSelect: () => void act(item, "requested", t("An administrator will see your request.")) }]
                        : []),
                      ...(!admin && item.status === "requested"
                        ? [{ label: t("Take back the request"), icon: "undo" as const, onSelect: () => void act(item, "draft", t("Request taken back.")) }]
                        : []),
                      ...(admin && item.status !== "draft"
                        ? [{ label: item.status === "requested" ? t("Decline") : t("Stop sharing"), icon: "close" as const, onSelect: () => void act(item, "draft", t("It is back with its owner.")) }]
                        : []),
                      { label: t("Export as a file"), icon: "download" as const, onSelect: () => location.assign(`/api/v1/themes/${item.id}/pack`) },
                      { label: t("Remove"), icon: "trash" as const, danger: true, onSelect: () => setRemoving(item) },
                    ]} // prettier-ignore
                  />
                </>
              }
            />
          ))}
        </List>
      ) : (
        <Text tone="muted">
          {admin
            ? t("Nobody has asked to share a theme yet.")
            : t("None yet. Remix one, design one with Nox, or bring a .houseos-theme file.")}
        </Text>
      )}
      <Cluster space={2}>
        {onStudio && (
          <Button variant="primary" icon="brush" onClick={onStudio}>
            {t("Design a theme with Nox")}
          </Button>
        )}
        <FileButton
          label={t("Bring a theme file")}
          accept=".houseos-theme,application/zip"
          busy={busy}
          onFiles={([file]) => void importPack(file)}
        />
      </Cluster>
      {removing && (
        <ConfirmSheet
          title={t("Remove {name}?").replace("{name}", themeName(removing))}
          confirm={t("Remove")}
          danger
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await api(`/themes/${removing.id}`, "DELETE");
            setRemoving(null);
            await refreshInstalled();
          }}
        >
          <Text>
            {t("Anyone wearing it goes back to the house's theme. Export it first to keep a copy.")}
          </Text>
        </ConfirmSheet>
      )}
    </>
  );
}

/** Nox's theme studio: design a theme in conversation (its own model, tools and limits). */
export function Studio() {
  return (
    <Section
      title={t("Theme studio")}
      lead={t(
        "Tell Nox a feeling, a place or an era, or show a picture: it proposes three directions, builds the one you choose and checks it. You can wear it, keep changing it, or ask to share it with the house.",
      )}
    >
      <div className="me-studio">
        <Assistant purpose="themes" />
      </div>
    </Section>
  );
}

function Appearance() {
  const { data, error, reload } = useData("/preferences");
  const house = useData("/house-settings");
  const [busy, setBusy] = useState("");
  const houseTheme = allThemes().find((theme) => theme.id === house.data?.theme);
  const mine = allThemes().find((theme) => theme.id === data?.theme) ?? houseTheme;
  const save = async (change: Obj, done: string) => {
    setBusy(Object.keys(change)[0]);
    try {
      await api("/preferences", "PUT", change);
      window.dispatchEvent(new Event("house-settings-updated"));
      await reload();
      toast(done);
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <Section
        title={t("Theme")}
        lead={t("How HouseOS looks for you, on every device. Everyone else keeps their own.")}
      >
        <Problem error={error || house.error} onRetry={reload} />
        {data && (
          <ThemePicker
            label={t("Theme")}
            value={data.theme || ""}
            scheme={data.scheme}
            house={houseTheme}
            own
            onChange={(theme) => void save({ theme }, t("Theme changed."))}
          />
        )}
        {data && (
          <SchemeChoice
            theme={mine}
            value={data.scheme || ""}
            onChange={(scheme) => void save({ scheme }, t("Theme changed."))}
          />
        )}
        {busy === "theme" && <Text tone="muted">{t("Changing the theme…")}</Text>}
      </Section>
      <Section title={t("Motion")} lead={t("Animations, from none to lively.")}>
        {data && (
          <Segmented
            label={t("Motion")}
            value={data.motion || "subtle"}
            disabled={busy === "motion"}
            onChange={(motion) => {
              document.documentElement.dataset.motion = motion;
              void save({ motion }, t("Preferences saved."));
            }}
            options={[
              { value: "still", label: t("Still") },
              { value: "subtle", label: t("Subtle") },
              { value: "full", label: t("Full") },
            ]}
          />
        )}
      </Section>
    </>
  );
}

function Comfort() {
  const { data, error, reload } = useData("/preferences");
  return (
    <Section title={t("Comfort")}>
      <Problem error={error} onRetry={reload} />
      {data && (
        <Form
          onSubmit={async (f) => {
            await api("/preferences", "PUT", {
              timezone: f.get("timezone"),
              notifications: f.get("notifications") === "on",
              time_display: f.get("time_display"),
              sounds: f.get("sounds") === "on",
            });
            window.dispatchEvent(new Event("house-settings-updated"));
            await reload();
            toast(t("Preferences saved."));
          }}
        >
          <Field label={t("Clock display")}>
            <Select name="time_display" defaultValue={data.time_display || "24h"}>
              <option value="24h">{t("24 hour")}</option>
              <option value="12h">{t("12 hour")}</option>
            </Select>
          </Field>
          <Field label={t("Timezone")}>
            <Input name="timezone" defaultValue={data.timezone} />
          </Field>
          <Checkbox
            name="sounds"
            defaultChecked={data.sounds || false}
            label={t("Message sent sound on this browser")}
          />
          <Checkbox
            name="notifications"
            defaultChecked={data.notifications}
            label={t("Allow notification preferences")}
            hint={t("Browser push requires a supported browser and a separate permission grant.")}
          />
        </Form>
      )}
    </Section>
  );
}

function Security({ user }: { user: Obj }) {
  const sessions = useData("/auth/sessions");
  const [signOut, setSignOut] = useState(false);
  return (
    <>
      <Section title={t("Change password")}>
        <Form
          submit={t("Change password and sign out")}
          onSubmit={async (f) => {
            if (f.get("new_password") !== f.get("repeat_password"))
              throw new Error(t("New passwords do not match."));
            await api("/auth/password", "POST", {
              current_password: f.get("current_password"),
              new_password: f.get("new_password"),
            });
            await localStore("clear");
            location.assign("/");
          }}
        >
          {/* Tells password managers which account this is, so they offer only its password. */}
          <Input
            type="text"
            name="username"
            autoComplete="username"
            value={user?.username || ""}
            readOnly
            hidden
          />
          <Field label={t("Current password")}>
            <Input
              type="password"
              name="current_password"
              autoComplete="current-password"
              required
            />
          </Field>
          <Field label={t("New password")}>
            <Input
              type="password"
              name="new_password"
              autoComplete="new-password"
              minLength={12}
              maxLength={256}
              required
            />
          </Field>
          <Field
            label={t("Repeat new password")}
            hint={t(
              "Revokes all sessions and clears this browser’s device drafts. Upload or copy drafts before changing your password.",
            )}
          >
            <Input
              type="password"
              name="repeat_password"
              autoComplete="new-password"
              minLength={12}
              maxLength={256}
              required
            />
          </Field>
        </Form>
      </Section>
      <Section
        title={t("Signed-in sessions")}
        actions={
          <Button size="s" variant="danger" icon="power" onClick={() => setSignOut(true)}>
            {t("Sign out everywhere")}
          </Button>
        }
      >
        <Problem error={sessions.error} onRetry={sessions.reload} />
        <List label={t("Signed-in sessions")}>
          {items(sessions.data).map((s) => (
            <ListRow
              key={s.id}
              leading={<Icon name="lock" size="s" />}
              title={t("Session") + " " + s.id.slice(0, 8)}
              detail={t("Expires") + " " + time(s.expires_at)}
            />
          ))}
        </List>
      </Section>
      {signOut && (
        <ConfirmSheet
          title={t("Sign out every session, including this one?")}
          confirm={t("Sign out everywhere")}
          danger
          onClose={() => setSignOut(false)}
          onConfirm={async () => {
            await api("/auth/sessions", "DELETE");
            location.reload();
          }}
        >
          <Text>{t("Every device signed in to your account signs out, this one too.")}</Text>
        </ConfirmSheet>
      )}
    </>
  );
}

// ---------- Films: the languages you follow come before 4K ----------
const FILM_LANGUAGES = [
  "en", "fr", "es", "de", "it", "pt", "nl", "pl", "ru", "uk", "ja", "ko", "zh", "ar", "hi", "tr",
  "sv", "no", "da", "fi", "cs", "el", "he", "hu", "ro",
]; // prettier-ignore
function languageName(code: string) {
  try {
    const name = new Intl.DisplayNames([getLanguage()], { type: "language" }).of(code) || code;
    return name[0].toUpperCase() + name.slice(1);
  } catch {
    return code;
  }
}
function FilmPreferences() {
  const cinema = useData("/cinema/preferences");
  const devices = useData("/cinema/devices");
  return (
    <>
      <Problem error={cinema.error} onRetry={cinema.reload} />
      {cinema.data && (
        <FilmDefaults
          saved={cinema.data}
          devices={items(devices.data).filter((d) => d.adapter !== "dlna")}
          onSaved={async () => {
            toast(t("Cinema defaults saved."));
            await cinema.reload();
          }}
        />
      )}
    </>
  );
}
function FilmDefaults({
  saved,
  devices,
  onSaved,
}: {
  saved: Obj;
  devices: Obj[];
  onSaved: () => Promise<void>;
}) {
  const [languages, setLanguages] = useState<string[]>(
    saved.languages?.length
      ? saved.languages
      : [saved.subtitle_language, saved.audio_language, "en"].filter(
          (code, i, all) => code && all.indexOf(code) === i,
        ),
  );
  const [adding, setAdding] = useState("");
  const add = (code: string) =>
    code && !languages.includes(code) && setLanguages([...languages, code]);
  return (
    <Section title={t("Films and series")} lead={t("How HouseOS picks a version for you.")}>
      <Form
        submit={t("Save film choices")}
        onSubmit={async (f) => {
          await api("/cinema/preferences", "PUT", {
            ...saved,
            languages: languages.length ? languages : null,
            subtitle_language: f.get("subtitle_language") || null,
            maximum_resolution: Number(f.get("maximum_resolution")),
            quality: f.get("quality"),
            hdr: f.get("hdr"),
            autoplay: f.get("autoplay") === "on",
            always_subtitles: f.get("always_subtitles") === "on",
            preferred_device: f.get("preferred_device") || null,
            source_selection: f.get("source_selection"),
          });
          await onSaved();
        }}
      >
        <fieldset className="me-fieldset">
          <legend>{t("Languages you understand")}</legend>
          <Text style="body-s" tone="muted">
            {t(
              "Versions with sound or subtitles in these come first, even before 4K. The first one is the most comfortable: no subtitles needed.",
            )}
          </Text>
          <List label={t("Languages you understand")}>
            {languages.map((code, index) => (
              <ListRow
                key={code}
                leading={<span className="tabular">{index + 1}</span>}
                title={languageName(code)}
                meta={index === 0 ? <Badge tone="accent">{t("First")}</Badge> : undefined}
                actions={
                  <>
                    {index > 0 && (
                      <Button
                        size="s"
                        variant="quiet"
                        icon="up"
                        onClick={() => setLanguages([code, ...languages.filter((c) => c !== code)])}
                      >
                        {t("Make it the first")}
                      </Button>
                    )}
                    <IconButton
                      icon="close"
                      size="s"
                      label={t("Remove") + " · " + languageName(code)}
                      onClick={() => setLanguages(languages.filter((c) => c !== code))}
                    />
                  </>
                }
              />
            ))}
          </List>
          <Select
            aria-label={t("Add a language")}
            value={adding}
            onChange={(e) => {
              add(e.target.value);
              setAdding("");
            }}
          >
            <option value="">{t("+ Add a language")}</option>
            {FILM_LANGUAGES.filter((code) => !languages.includes(code)).map((code) => (
              <option key={code} value={code}>
                {languageName(code)}
              </option>
            ))}
          </Select>
        </fieldset>
        <Field label={t("Subtitles")}>
          <Select name="subtitle_language" defaultValue={saved.subtitle_language || ""}>
            <option value="">{t("In my first language, else the next one")}</option>
            {languages.map((code) => (
              <option key={code} value={code}>
                {t("Always {language} first").replace("{language}", languageName(code))}
              </option>
            ))}
          </Select>
        </Field>
        <Checkbox
          name="always_subtitles"
          defaultChecked={!!saved.always_subtitles}
          label={t("Always subtitles in my languages, even when I understand the sound")}
          hint={t(
            "Sound: the original version whenever it plays; a dub in your languages only when you would not follow the original. Subtitles come on by themselves when the sound isn't in your first language; switch them off on the film's card.",
          )}
        />
        <div className="me-row">
          <Field label={t("Picture")}>
            <Select name="quality" defaultValue={saved.quality}>
              <option value="auto">{t("Best that plays well")}</option>
              <option value="2160p">{t("4K")}</option>
              <option value="1080p">{t("1080p")}</option>
              <option value="720p">{t("720p")}</option>
            </Select>
          </Field>
          <Field label={t("Never above")}>
            <Select name="maximum_resolution" defaultValue={saved.maximum_resolution}>
              <option value="2160">{t("4K")}</option>
              <option value="1080">{t("1080p")}</option>
              <option value="720">{t("720p")}</option>
            </Select>
          </Field>
          <Field label={t("HDR")}>
            <Select name="hdr" defaultValue={saved.hdr}>
              <option value="auto">{t("Keep it when the TV can")}</option>
              <option value="prefer">{t("Prefer")}</option>
              <option value="avoid">{t("Avoid")}</option>
            </Select>
          </Field>
        </div>
        <div className="me-row">
          <Field label={t("Screen")}>
            <Select name="preferred_device" defaultValue={saved.preferred_device || ""}>
              <option value="">{t("Ask each time")}</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("When Nox chooses for me")}>
            <Select name="source_selection" defaultValue={saved.source_selection || "ask"}>
              <option value="ask">{t("Show me the best choices")}</option>
              <option value="best_compatible">{t("Take the most compatible")}</option>
            </Select>
          </Field>
        </div>
        <Checkbox
          name="autoplay"
          defaultChecked={saved.autoplay}
          label={t("Play the next episode by itself")}
        />
      </Form>
    </Section>
  );
}

// ---------- AI usage (also in the Control Room) ----------
/** A period's cost: the known dollars, even when a few requests (usually failed ones) have none. */
const usd = (r: Obj) =>
  r.unpriced_requests && !r.cost_microusd ? t("Unknown") : "$" + (r.cost_microusd / 1e6).toFixed(4);
/** One tap: real prices for the models this house uses, from OpenRouter's free public list. */
function PriceLookup({ asOf, onDone }: { asOf?: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false),
    [said, setSaid] = useState(""),
    [error, setError] = useState("");
  return (
    <div className="me-stack">
      <div>
        <Button
          icon="search"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const result = await api<Obj>("/admin/usage/prices", "POST");
              const missing = (result.missing || []).map((m: Obj) => m.model).join(", ");
              setSaid(
                t("{n} models priced.").replace("{n}", String(result.priced)) +
                  " " +
                  t("Requests the provider already priced keep that cost.") +
                  (missing
                    ? " " + t("No public price for: {models}.").replace("{models}", missing)
                    : ""),
              );
              setError("");
              onDone();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {t("Look up real prices")}
        </Button>
      </div>
      <Text style="body-s" tone="muted">
        {said ||
          t(
            "Only the models used in the last 30 days or assigned to Nox, from OpenRouter's free public list. Subscriptions (ChatGPT, Claude sign-in) are not priced by tokens.",
          )}
        {asOf && " " + t("Prices from {date}.").replace("{date}", time(asOf))}
      </Text>
      <Problem error={error} />
    </div>
  );
}

function Figure({ value, label }: { value: ReactNode; label: ReactNode }) {
  return (
    <div className="me-figure">
      <Text style="title-l" className="tabular">
        {value}
      </Text>
      <Text style="caption" tone="muted">
        {label}
      </Text>
    </div>
  );
}

export function Usage() {
  const [metric, setMetric] = useState("requests");
  const me = useUser();
  const people = useData(me?.role === "admin" ? "/admin/users" : null);
  const [range, setRange] = useState("7"),
    [provider, setProvider] = useState(""),
    [model, setModel] = useState(""),
    [user, setUser] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState("");
  const query = new URLSearchParams({
    days: range === "custom" ? "7" : range,
    ...(provider ? { provider } : {}),
    ...(model ? { model } : {}),
    ...(user ? { user_id: user } : {}),
    ...(range === "custom" && start && end ? { start, end } : {}),
  });
  const { data, error, reload } = useData("/usage?" + query);
  const totals = data?.totals || {};
  const max = Math.max(1, ...(data?.series || []).map((r: Obj) => Number(r[metric] || 0)));
  return (
    <Section title={t("AI usage")} lead={t("Clear costs. Private conversations.")}>
      <div className="me-filters">
        <Select
          aria-label={t("Usage date range")}
          value={range}
          onChange={(e) => setRange(e.target.value)}
        >
          <option value="1">{t("Today")}</option>
          <option value="7">{t("7 days")}</option>
          <option value="30">{t("30 days")}</option>
          <option value="custom">{t("Custom range")}</option>
        </Select>
        <Select
          aria-label={t("Provider filter")}
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="">{t("All providers")}</option>
          {AI_PROVIDERS.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </Select>
        <Input
          aria-label={t("Model filter")}
          placeholder={t("Model")}
          value={model}
          onChange={(e) => setModel(e.target.value)}
        />
        {me?.role === "admin" && (
          <Select
            aria-label={t("User filter")}
            value={user}
            onChange={(e) => setUser(e.target.value)}
          >
            <option value="">{t("All residents")}</option>
            {items(people.data).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        )}
      </div>
      {range === "custom" && (
        <div className="me-row">
          <Field label={t("From")}>
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label={t("Through")}>
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>
      )}
      <Problem error={error} onRetry={reload} />
      <div className="me-figures">
        <Figure
          value={totals.requests ?? "—"}
          label={
            t("Requests ·") +
            " " +
            (totals.subscription_requests || 0) +
            " " +
            t("native subscription")
          }
        />
        <Figure value={totals.input_tokens ?? "—"} label={t("Input tokens")} />
        <Figure value={totals.output_tokens ?? "—"} label={t("Output tokens")} />
        <Figure
          value={
            totals.requests > 0 && totals.requests === totals.subscription_requests
              ? t("Subscription")
              : totals.cost_microusd !== undefined
                ? usd(totals)
                : "—"
          }
          label={
            pretty(data?.cost_kind || "unknown") +
            " " +
            t("cost") +
            (totals.unpriced_requests > 0
              ? " · " +
                t("{n} requests without a cost (failed or unpriced)").replace(
                  "{n}",
                  String(totals.unpriced_requests),
                )
              : "")
          }
        />
        {totals.looked_up_requests > 0 && (
          <Figure
            value={
              "≈ $" +
              (totals.looked_up_microusd / 1e6).toFixed(totals.looked_up_microusd < 1e6 ? 4 : 2)
            }
            label={t("{n} requests at today's OpenRouter prices").replace(
              "{n}",
              String(totals.looked_up_requests),
            )}
          />
        )}
      </div>
      {me?.role === "admin" && <PriceLookup asOf={data?.prices_as_of} onDone={reload} />}
      <Text style="body-s" tone="muted">
        {t("Costs cover API requests only. Native subscription requests are counted separately;")}{" "}
        {totals.unknown_token_requests || 0}{" "}
        {t("requests have unreported token usage (excluded from token totals).")}
      </Text>
      <Field label={t("Graph")}>
        <Select value={metric} onChange={(e) => setMetric(e.target.value)}>
          {[
            "requests",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "cost_microusd",
            "tool_calls",
            "latency_ms",
            "failures",
          ].map((k) => (
            <option value={k} key={k}>
              {k === "cost_microusd" ? t("Cost (reported or estimated)") : pretty(k)}
            </option>
          ))}
        </Select>
      </Field>
      {data?.series?.length ? (
        <div className="me-chart" role="img" aria-label={pretty(metric) + " " + t("by day")}>
          {/* The scale: the top of the tallest bar, and the baseline. */}
          <div className="me-chart__axis" aria-hidden="true">
            <small>{metric === "cost_microusd" ? usd({ cost_microusd: max }) : number(max)}</small>
            <small>0</small>
          </div>
          <div className="me-chart__scroll">
            <div className="me-chart__bars">
              {data.series.map((r: Obj) => (
                <span
                  key={r.date}
                  title={
                    r.date +
                    ": " +
                    (metric === "cost_microusd" ? usd(r) : r[metric]) +
                    " " +
                    pretty(metric)
                  }
                  style={{ "--value": Number(r[metric] || 0) / max } as CSSProperties}
                />
              ))}
            </div>
            <div className="me-chart__dates">
              {data.series.map((r: Obj) => (
                <small key={r.date}>{r.date.slice(5)}</small>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <State kind="empty" title={t("No AI requests in this period.")} />
      )}
      <Disclosure summary={t("Accessible data table")}>
        <div className="me-table">
          <table>
            <thead>
              <tr>
                <th>{t("Date")}</th>
                <th>{t("Requests")}</th>
                <th>{t("Input")}</th>
                <th>{t("Output")}</th>
                <th>{t("Cached")}</th>
                <th>{t("Cost")}</th>
                <th>{t("Failures")}</th>
              </tr>
            </thead>
            <tbody>
              {(data?.series || []).map((r: Obj) => (
                <tr key={r.date}>
                  <td>{r.date}</td>
                  <td>{r.requests}</td>
                  <td>{r.input_tokens}</td>
                  <td>{r.output_tokens}</td>
                  <td>{r.cached_tokens}</td>
                  <td>{usd(r)}</td>
                  <td>{r.failures}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
      <Disclosure summary={t("Usage by person, provider and model")}>
        <div className="me-table">
          <table>
            <thead>
              <tr>
                <th>{t("Person")}</th>
                <th>{t("Provider / model")}</th>
                <th>{t("Requests")}</th>
                <th>{t("Provider-reported cost")}</th>
                <th>{t("Estimated cost")}</th>
                <th>{t("Unpriced requests")}</th>
              </tr>
            </thead>
            <tbody>
              {(data?.breakdown || []).map((r: Obj, i: number) => (
                <tr key={i}>
                  <td>
                    {items(people.data).find((p) => p.id === r.user_id)?.name ||
                      (r.user_id === me?.id ? t("You") : t("Resident"))}
                  </td>
                  <td>
                    {r.provider} / {r.model}
                  </td>
                  <td>{r.requests}</td>
                  <td>${(r.provider_reported_microusd / 1e6).toFixed(4)}</td>
                  <td>${(r.estimated_microusd / 1e6).toFixed(4)}</td>
                  <td>{r.unpriced_requests}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
      <Text style="body-s" tone="muted">
        {t("Provider-reported: $")}{" "}
        {(Number(totals.provider_reported_microusd || 0) / 1e6).toFixed(4)} {t("· Estimated: $")}{" "}
        {(Number(totals.estimated_microusd || 0) / 1e6).toFixed(4)} {t("· Unpriced requests:")}{" "}
        {totals.unpriced_requests || 0}
        {t(". Provider billing statements remain authoritative.")}
      </Text>
      <Text style="body-s" tone="muted">
        {t("Cached:")} {totals.cached_tokens ?? "—"} {t("· Tools:")} {totals.tool_calls ?? "—"}{" "}
        {t("· Failures:")} {totals.failures ?? "—"} · {data?.timezone || "UTC"}
      </Text>
    </Section>
  );
}

// ---------- Nox's memory ----------
// The three kinds of memory, each with what it is for (shown as a legend and in the list).
const MEMORY_KINDS: [string, "heart" | "pin" | "compass", string, string][] = [
  ["preference", "heart", "Preference", "what you like: “no horror films after 10 pm”"],
  ["fact", "pin", "Fact", "about you or the house: “my room is upstairs”, “Milo is vegetarian”"],
  [
    "instruction",
    "compass",
    "Instruction",
    "how Nox should act: “keep answers short”, “call me Lu”",
  ],
];
const kindOf = (kind: string) => MEMORY_KINDS.find(([k]) => k === kind) ?? MEMORY_KINDS[1];
function MemoryPreferences() {
  const [editing, setEditing] = useState<Obj | null>(null),
    [forgetting, setForgetting] = useState<Obj | null>(null),
    [allMemories, setAllMemories] = useState(false);
  const { data, error, reload } = useData("/assistant/memories");
  const memories = items(data);
  const expiry = (at?: string) =>
    at
      ? new Date(new Date(at).getTime() - new Date(at).getTimezoneOffset() * 60000)
          .toISOString()
          .slice(0, 16)
      : "";
  return (
    <Section title={t("Your assistant’s memory")} lead={t("Only what you choose to keep.")}>
      <Text>
        {t(
          "Things Nox should always know about you. With each message, it reads the few that share words with what you ask (up to five). Only you and Nox see them; add as many as you like.",
        )}
      </Text>
      <List label={t("Kinds of memory")}>
        {MEMORY_KINDS.map(([kind, icon, label, example]) => (
          <ListRow key={kind} leading={<Icon name={icon} />} title={t(label)} detail={t(example)} />
        ))}
      </List>
      <Text style="body-s" tone="muted">
        {t(
          "You can also tell Nox “remember that…” in a chat. An end date makes a memory forget itself (“I'm away until Sunday”).",
        )}
      </Text>
      <Problem error={error} onRetry={reload} />
      <Form
        submit={t("Add to Nox's memory")}
        reset
        onSubmit={async (f) => {
          await api("/assistant/memories", "POST", {
            text: f.get("text"),
            kind: f.get("kind"),
            expires_at: f.get("expires_at")
              ? new Date(String(f.get("expires_at"))).toISOString()
              : null,
          });
          await reload();
          toast(t("Remembered."));
        }}
      >
        <Field label={t("Remember this")}>
          <Textarea
            name="text"
            required
            maxLength={1000}
            rows={2}
            placeholder={t("I prefer films in the original version, with subtitles")}
          />
        </Field>
        <div className="me-row">
          <Field label={t("Kind")}>
            <Select name="kind" defaultValue="preference">
              {MEMORY_KINDS.map(([kind, , label]) => (
                <option key={kind} value={kind}>
                  {t(label)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("Forget it on (optional)")}>
            <Input name="expires_at" type="datetime-local" />
          </Field>
        </div>
      </Form>
      {memories.length > 0 && (
        <List label={t("Your assistant’s memory")}>
          {memories.slice(0, allMemories ? undefined : 8).map((m) => (
            <ListRow
              key={m.id}
              leading={<Icon name={kindOf(m.kind)[1]} label={t(kindOf(m.kind)[2])} />}
              title={m.text}
              detail={m.expires_at ? t("Forgotten on") + " " + time(m.expires_at) : undefined}
              actions={
                <>
                  <Button size="s" variant="quiet" icon="edit" onClick={() => setEditing(m)}>
                    {t("Edit memory")}
                  </Button>
                  <IconButton
                    icon="trash"
                    size="s"
                    label={t("Delete memory")}
                    onClick={() => setForgetting(m)}
                  />
                </>
              }
            />
          ))}
        </List>
      )}
      {!allMemories && memories.length > 8 && (
        <div>
          <Button variant="quiet" onClick={() => setAllMemories(true)}>
            {t("Show all {n}").replace("{n}", String(memories.length))}
          </Button>
        </div>
      )}
      {editing && (
        <Sheet title={t("Edit personal memory")} onClose={() => setEditing(null)}>
          <Form
            onSubmit={async (f) => {
              await api("/assistant/memories/" + editing.id, "PUT", {
                text: f.get("text"),
                kind: f.get("kind"),
                expires_at: f.get("expires_at")
                  ? new Date(String(f.get("expires_at"))).toISOString()
                  : null,
              });
              setEditing(null);
              await reload();
            }}
          >
            <Field label={t("Memory text")}>
              <Textarea name="text" defaultValue={editing.text} maxLength={1000} required />
            </Field>
            <Field label={t("Memory kind")}>
              <Select name="kind" defaultValue={editing.kind}>
                <option value="preference">{t("preference")}</option>
                <option value="fact">{t("fact")}</option>
                <option value="instruction">{t("instruction")}</option>
              </Select>
            </Field>
            <Field label={t("Expiry")}>
              <Input
                name="expires_at"
                type="datetime-local"
                defaultValue={expiry(editing.expires_at)}
              />
            </Field>
          </Form>
        </Sheet>
      )}
      {forgetting && (
        <ConfirmSheet
          title={t("Forget this memory?")}
          confirm={t("Delete memory")}
          danger
          onClose={() => setForgetting(null)}
          onConfirm={async () => {
            await api("/assistant/memories/" + forgetting.id, "DELETE");
            await reload();
          }}
        >
          <Text>{forgetting.text}</Text>
        </ConfirmSheet>
      )}
    </Section>
  );
}

// ---------- Notifications ----------
function PushPreferences() {
  const { data, error, reload } = useData("/notifications/push");
  const [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Section title={t("Notifications")} lead={t("Your inbox is always the source of truth.")}>
      <Problem error={error || failure} onRetry={reload} />
      <Text style="body-s" tone="muted">
        {t(
          "Push is optional and uses your browser’s delivery service. Message bodies stay off your lock screen.",
        )}
      </Text>
      <div>
        <Button
          variant="primary"
          icon="bell"
          busy={busy}
          disabled={!data?.configured}
          onClick={async () => {
            setBusy(true);
            try {
              // iPhone and iPad (16.4+) offer push only to a Home Screen app, never in a Safari tab.
              const appleTab =
                (/iP(hone|ad|od)/.test(navigator.userAgent) ||
                  (/Mac/.test(navigator.userAgent) && navigator.maxTouchPoints > 1)) &&
                !matchMedia("(display-mode: standalone)").matches;
              if (!("PushManager" in window) || !("serviceWorker" in navigator))
                throw new Error(
                  t(
                    appleTab
                      ? "On iPhone, add HouseOS to the Home Screen first (Share → Add to Home Screen), then turn notifications on."
                      : "Push is not supported here. Use your inbox.",
                  ),
                );
              const permission = await Notification.requestPermission();
              if (permission !== "granted") throw new Error(t("Notifications were not allowed."));
              // No service worker ever registers while this device does not trust the house's
              // own certificate, and `ready` would then wait forever.
              const reg = await Promise.race([
                navigator.serviceWorker.ready,
                new Promise<never>((_, fail) =>
                  setTimeout(
                    () =>
                      fail(
                        new Error(
                          t(
                            "Notifications need the house's certificate installed on this device (Control Room → Access → Download the certificate).",
                          ),
                        ),
                      ),
                    8000,
                  ),
                ),
              ]);
              const key = data!.application_server_key;
              const bytes = Uint8Array.from(
                atob(key.replaceAll("-", "+").replaceAll("_", "/")),
                (c) => c.charCodeAt(0),
              );
              const subscription = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: bytes,
              });
              await api("/notifications/push", "POST", subscription.toJSON());
              await reload();
              setFailure("");
            } catch (e) {
              setFailure(t((e as Error).message));
            } finally {
              setBusy(false);
            }
          }}
        >
          {t("Enable on this browser")}
        </Button>
      </div>
      {data && !data.configured && (
        <Text style="body-s" tone="muted">
          {t("Push delivery has not been configured by the administrator.")}
        </Text>
      )}
      {items(data?.subscriptions).length > 0 && (
        <List label={t("Browser subscriptions")}>
          {items(data?.subscriptions).map((x) => (
            <ListRow
              key={x.id}
              leading={<Icon name="bell" size="s" />}
              title={t("Browser subscription ·") + " " + time(x.created_at)}
              actions={
                <Button
                  size="s"
                  variant="quiet"
                  onClick={async () => {
                    await api("/notifications/push/" + x.id, "DELETE");
                    await reload();
                  }}
                >
                  {t("Revoke")}
                </Button>
              }
            />
          ))}
        </List>
      )}
      {data && (
        <Form
          onSubmit={async (f) => {
            await api("/notifications/preferences", "PUT", {
              quiet_start: f.get("start"),
              quiet_end: f.get("end"),
              timezone: f.get("timezone"),
              muted_categories: f.getAll("muted_categories"),
            });
            await reload();
            toast(t("Preferences saved."));
          }}
        >
          <Field label={t("Quiet-hours timezone")}>
            <Input name="timezone" defaultValue={data.preferences?.timezone || "UTC"} required />
          </Field>
          <fieldset className="me-fieldset">
            <legend>{t("Mute push categories")}</legend>
            {["message", "assignment", "reminder", "reminder_catchup"].map((category) => (
              <Checkbox
                key={category}
                name="muted_categories"
                value={category}
                defaultChecked={data.preferences?.muted_categories?.includes(category) || false}
                label={t(pretty(category))}
              />
            ))}
          </fieldset>
          <div className="me-row">
            <Field label={t("Quiet from")}>
              <Input
                name="start"
                type="time"
                defaultValue={data.preferences?.quiet_start || "23:00"}
              />
            </Field>
            <Field label={t("Until")}>
              <Input name="end" type="time" defaultValue={data.preferences?.quiet_end || "08:00"} />
            </Field>
          </div>
        </Form>
      )}
    </Section>
  );
}

// ---------- Profile ----------
function AccountPreferences() {
  const user = useUser();
  const profile = useData("/account/profile");
  const languages = useData("/languages");
  const [preview, setPreview] = useState<Obj | null>(null);
  return (
    <>
      <Section title={t("Your profile")}>
        <Problem error={profile.error} onRetry={profile.reload} />
        {profile.data && (
          <Form
            submit={t("Save profile")}
            onSubmit={async (f) => {
              profile.setData(
                await api("/account/profile", "PATCH", {
                  name: f.get("name"),
                  language: f.get("language"),
                  avatar: f.get("avatar"),
                  memory_enabled: f.get("memory_enabled") === "on",
                }),
              );
              toast(t("Profile saved."));
              window.dispatchEvent(new Event("house-settings-updated"));
            }}
          >
            <Field label={t("Display name")}>
              <Input
                name="name"
                defaultValue={profile.data.name}
                minLength={1}
                maxLength={80}
                required
              />
            </Field>
            <Field label={t("Preferred language")}>
              <Select name="language" defaultValue={profile.data.language}>
                {(items(languages.data).length
                  ? items(languages.data).filter((l) => l.state === "ready")
                  : [
                      { code: "en", name: "English" },
                      { code: "fr", name: "Français" },
                    ]
                ).map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </Select>
            </Field>
            <fieldset className="me-avatars">
              <legend>{t("Avatar")}</legend>
              {AVATAR_NAMES.map((a) => (
                <Radio
                  key={a}
                  name="avatar"
                  value={a}
                  defaultChecked={profile.data?.avatar === a}
                  aria-label={a === "crest" ? t("Initials") : t(a[0].toUpperCase() + a.slice(1))}
                  label={
                    a === "crest" ? (
                      <Avatar name={profile.data?.name || ""} tone={tone(user?.id)} />
                    ) : (
                      <AvatarPicture name={a} scale={3} />
                    )
                  }
                />
              ))}
            </fieldset>
            <Checkbox
              name="memory_enabled"
              defaultChecked={profile.data.memory_enabled}
              label={t("Allow my assistant to use my explicit memories")}
            />
          </Form>
        )}
      </Section>
      {profile.data && (
        <Section title={t("Your data")}>
          <div>
            <LinkButton icon="download" href="/api/v1/account/export" download>
              {t("Export my account data")}
            </LinkButton>
          </div>
          <Text style="body-s" tone="muted">
            {t(
              "The private JSON export includes your records and file metadata; download file contents separately.",
            )}
          </Text>
          <Disclosure summary={t("Delete my account")}>
            <Form
              submit={t("Review account deletion")}
              onSubmit={async () => setPreview(await api("/account/delete/prepare", "POST", {}))}
            >
              <Text>
                {t(
                  "Review the exact personal-data impact and retained shared records before confirming. The last administrator cannot delete their account.",
                )}
              </Text>
            </Form>
          </Disclosure>
        </Section>
      )}
      {preview && (
        <ConfirmSheet
          title={t("Review account deletion")}
          confirm={t("Delete my account with this exact impact")}
          danger
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            const r = await api("/account/delete/confirm/" + preview.confirmation_id, "POST", {});
            if (r.status !== "completed") throw new Error(t("Account deletion is not confirmed."));
            await localStore("clear");
            location.assign("/");
          }}
        >
          <ReviewDetails value={preview.preview} />
          <Text>{t("Also clears device-local drafts in this browser.")}</Text>
        </ConfirmSheet>
      )}
    </>
  );
}

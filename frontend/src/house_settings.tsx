import { useState } from "react";
import { api, useData, items, percent, type Obj } from "./api";
import {
  Button,
  Checkbox,
  Combobox,
  Field,
  Form,
  IconButton,
  Input,
  List,
  ListRow,
  Notice,
  Problem,
  Progress,
  Section,
  Select,
  Slider,
  State,
  Text,
  Textarea,
} from "./design";
import { t } from "./i18n";
import "./house_settings.css";

/** "Name: word, word" per line → the house's own genres. */
function parseGenres(text: string) {
  return text
    .split("\n")
    .map((line) => line.split(":"))
    .filter(([name, words]) => name?.trim() && words?.trim())
    .map(([name, ...rest]) => ({
      name: name.trim().slice(0, 40),
      words: rest
        .join(":")
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean)
        .slice(0, 20),
    }))
    .slice(0, 20);
}
const genreLines = (genres: { name: string; words: string[] }[] = []) =>
  genres.map((genre) => genre.name + ": " + genre.words.join(", ")).join("\n");

export function HouseSettingsAdmin() {
  const state = useData("/admin/house-settings");
  const [notice, setNotice] = useState("");
  const value = state.data;
  const gib = 1024 ** 3;
  return (
    <Section
      title={t("House settings")}
      lead={t("Everyone starts with these; each person can change their own in their profile.")}
    >
      <Problem error={state.error} onRetry={state.reload} />
      {!value && !state.error && <State kind="loading" />}
      {notice && <Notice tone="success">{notice}</Notice>}
      {value && (
        <Form
          key={JSON.stringify(value)}
          onSubmit={async (data) => {
            await api("/admin/house-settings", "PUT", {
              name: String(data.get("name")),
              timezone: String(data.get("timezone")),
              language: String(data.get("language") || value.language),
              motion: String(data.get("motion")),
              quiet_start: String(data.get("quiet_start")),
              quiet_end: String(data.get("quiet_end")),
              music_volume_cap: Number(data.get("music_volume_cap")),
              music_round_robin: data.get("music_round_robin") === "on",
              music_normalize: data.get("music_normalize") === "on",
              music_genre_lookup: data.get("music_genre_lookup") === "on",
              music_genres: parseGenres(String(data.get("music_genres") || "")),
              music_sleep_minutes: Number(data.get("music_sleep_minutes")),
              music_preload: Number(data.get("music_preload")),
              music_keep_downloads: data.get("music_keep_downloads") === "on",
              file_quota_bytes: Math.round(Number(data.get("file_quota_gib")) * gib),
              max_upload_bytes: Math.round(Number(data.get("max_upload_gib")) * gib),
            });
            setNotice(t("House defaults saved. Reload an open page to apply display defaults."));
            state.reload();
            window.dispatchEvent(new Event("house-settings-updated"));
          }}
        >
          <Section title={t("The house")} level={3}>
            {/* One per line, all as wide: the zone's "use this device's" and the languages
                below need the room a paired column doesn't have. */}
            <div className="house-settings-stack">
              <Field label={t("House name")}>
                <Input name="name" required maxLength={80} defaultValue={value.name} />
              </Field>
              <TimeZoneField value={value.timezone} />
              <HouseLanguages current={value.language} />
            </div>
          </Section>
          <Section title={t("Music")} level={3}>
            <VolumeCapField value={value.music_volume_cap} />
            <Checkbox
              name="music_round_robin"
              defaultChecked={value.music_round_robin}
              label={t("Take turns")}
              hint={t("One song per person each round, so nobody hogs the speakers.")}
            />
            <Checkbox
              name="music_normalize"
              defaultChecked={value.music_normalize ?? true}
              label={t("Even out songs")}
              hint={t(
                "A song uploaded much quieter than the rest plays 20 % louder, and one mastered dangerously loud plays 15 % softer. One fixed setting per song: drops, bass and the mix are never touched. Radio plays as is.",
              )}
            />
            <Checkbox
              name="music_genre_lookup"
              defaultChecked={value.music_genre_lookup ?? true}
              label={t("Find each song's genre online")}
              hint={t(
                "When a song's title doesn't say, HouseOS asks Deezer's free public catalogue once (the artist and title only, no account) for its genre and cover.",
              )}
            />
            <Field
              label={t("Download ahead")}
              hint={t(
                "Songs waiting in the queue are downloaded early, so the next one starts at once.",
              )}
            >
              <Select name="music_preload" defaultValue={String(value.music_preload ?? 0)}>
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
            <Checkbox
              name="music_keep_downloads"
              defaultChecked={value.music_keep_downloads ?? true}
              label={t("Keep the songs we play")}
              hint={t(
                "On: every song played stays in the house's library (Files → Music) and replays without the internet. Off: songs are downloaded to play, then deleted; at most 3 are downloaded ahead.",
              )}
            />
            <Field
              label={t("Genres of your own")}
              hint={t(
                "One genre per line: its name, a colon, then the words that mean it (in titles, artists or tags). They count first, for every song already played too.",
              )}
            >
              <Textarea
                name="music_genres"
                rows={3}
                placeholder={t("Anime songs: aimer, yoasobi, opening")}
                defaultValue={genreLines(value.music_genres)}
              />
            </Field>
            <Field label={t("Music stops by itself after")}>
              <Select
                name="music_sleep_minutes"
                defaultValue={String(value.music_sleep_minutes ?? 300)}
              >
                {[...new Set([0, 60, 120, 180, 300, 480, 720, value.music_sleep_minutes ?? 300])]
                  .sort((a, b) => a - b)
                  .map((minutes) => (
                    <option key={minutes} value={minutes}>
                      {minutes
                        ? minutes % 60
                          ? `${minutes} min`
                          : `${minutes / 60} h`
                        : t("Never")}
                    </option>
                  ))}
              </Select>
            </Field>
          </Section>
          <Section
            title={t("Quiet hours")}
            lead={t("No notification sounds between these times.")}
            level={3}
          >
            <Field label={t("From")}>
              <Input name="quiet_start" type="time" required defaultValue={value.quiet_start} />
            </Field>
            <Field label={t("To")}>
              <Input name="quiet_end" type="time" required defaultValue={value.quiet_end} />
            </Field>
          </Section>
          <Section title={t("Files")} level={3}>
            <Field label={t("Space per person (GiB)")}>
              <Input
                name="file_quota_gib"
                type="number"
                min={1}
                max={1024}
                step={1}
                required
                defaultValue={value.file_quota_bytes / gib}
              />
            </Field>
            <Field label={t("Largest single file (GiB)")}>
              <Input
                name="max_upload_gib"
                type="number"
                min={0.001}
                max={80}
                step={0.001}
                required
                defaultValue={value.max_upload_bytes / gib}
              />
            </Field>
          </Section>
          <Section title={t("Look")} level={3}>
            <Field label={t("Animations")}>
              <Select name="motion" defaultValue={value.motion}>
                <option value="still">{t("Still")}</option>
                <option value="subtle">{t("Subtle")}</option>
                <option value="full">{t("Full")}</option>
              </Select>
            </Field>
          </Section>
        </Form>
      )}
    </Section>
  );
}

/** The loudest music allowed: a slider, sent with the form. */
function VolumeCapField({ value }: { value: number }) {
  const [cap, setCap] = useState(value);
  return (
    <>
      <Slider
        label={t("Loudest music allowed")}
        showLabel
        min={0}
        max={100}
        step={5}
        value={cap}
        onChange={setCap}
        format={percent}
      />
      <Input type="hidden" name="music_volume_cap" value={cap} />
    </>
  );
}

/** Time zones by name, with the one this device uses one tap away. */
function TimeZoneField({ value }: { value: string }) {
  const [zone, setZone] = useState(value);
  const zones: string[] = (Intl as any).supportedValuesOf?.("timeZone") || [value];
  const here = Intl.DateTimeFormat().resolvedOptions().timeZone;
  // The device's own zone one tap away, under the field (a field keeps one control).
  return (
    <Field
      label={t("Time zone")}
      hint={
        here &&
        here !== zone && (
          <Button size="s" variant="quiet" icon="pin" onClick={() => setZone(here)}>
            {t("Use this device's")} ({here})
          </Button>
        )
      }
    >
      <Combobox
        name="timezone"
        required
        options={zones}
        value={zone}
        onChange={(e) => setZone(e.target.value)}
      />
    </Field>
  );
}

/** The language residents and guests start in, the ones being translated, and a one-tap way
 *  to add another: Nox (setup mode) receives a ready request and runs the translation. */
function HouseLanguages({ current }: { current: string }) {
  const list = useData("/languages", {
    interval: (data) => items(data).some((l) => l.state === "translating") && 5000,
  });
  const [wanted, setWanted] = useState(""),
    [error, setError] = useState("");
  const languages = items(list.data);
  const added = languages.filter((l) => !l.built_in);
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setError("");
      await list.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <Field
        label={t("Language for residents and guests")}
        hint={t("Administrators start in English. Everyone can switch in their profile.")}
      >
        <Select name="language" defaultValue={current}>
          {languages
            .filter((l) => l.state === "ready")
            .map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
        </Select>
      </Field>
      <div className="house-settings-languages">
        {added.length > 0 && (
          <List>
            {added.map((l: Obj) => (
              <ListRow
                key={l.code}
                title={l.name}
                status={
                  l.state === "ready"
                    ? { tone: "success", text: t("Ready") }
                    : l.state === "failed"
                      ? {
                          tone: "danger",
                          text: t("Stopped: {error}").replace("{error}", l.error || "?"),
                        }
                      : {
                          tone: "info",
                          busy: true,
                          text: t("Translating… {n}/{total}")
                            .replace("{n}", String(l.done))
                            .replace("{total}", String(l.total)),
                        }
                }
                actions={
                  <>
                    {l.state === "failed" && (
                      <Button
                        size="s"
                        variant="quiet"
                        icon="refresh"
                        onClick={() =>
                          void act(() =>
                            api("/admin/languages", "POST", { code: l.code, name: l.name }),
                          )
                        }
                      >
                        {t("Retry")}
                      </Button>
                    )}
                    <IconButton
                      icon="close"
                      size="s"
                      label={t("Remove") + " · " + l.name}
                      onClick={() => void act(() => api("/admin/languages/" + l.code, "DELETE"))}
                    />
                  </>
                }
              >
                {l.state === "translating" && (
                  <Progress value={l.done / Math.max(1, l.total)} label={t("Translating")} />
                )}
              </ListRow>
            ))}
          </List>
        )}
        <div className="house-settings-add">
          <Input
            aria-label={t("Another language")}
            placeholder={t("Another language: Polski, Deutsch, 日本語…")}
            value={wanted}
            maxLength={40}
            onChange={(e) => setWanted(e.target.value)}
          />
          <Button
            icon="sparkles"
            disabled={!wanted.trim()}
            onClick={() => {
              dispatchEvent(
                new CustomEvent("houseos:ask", {
                  detail: {
                    purpose: "setup",
                    message: t(
                      "Add {language} to the house: start translating the whole interface with language_add (use its ISO code and its own name), tell me how long it should take, and once it is ready, offer to make it the language for residents and guests.",
                    ).replace(/\{language\}/g, wanted.trim()),
                  },
                }),
              );
              setWanted("");
            }}
          >
            {t("Translate with Nox")}
          </Button>
        </div>
        <Text as="p" style="body-s" tone="muted">
          {t(
            "Nox's AI translates every screen once, in the background (about 30 requests, a few minutes); anything it misses stays in English.",
          )}
        </Text>
        <Problem error={error || list.error} />
      </div>
    </>
  );
}

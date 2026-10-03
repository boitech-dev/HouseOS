// Smart home: the house's TV remote (beside the rooms on a wide screen, above them otherwise), and what Home Assistant lets HouseOS control, room by room.
// Admins choose what the room shows; each person pins favourites. A tap shows the change at
// once, then the state Home Assistant actually reports afterwards.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, percent, useData, useUser, type Obj } from "./api";
import { getLanguage, t } from "./i18n";
import { go } from "./nav";
import {
  Badge,
  Button,
  Checkbox,
  ColorField,
  List,
  ListRow,
  Sheet,
  Chip,
  Disclosure,
  ChipGroup,
  Field,
  Glyph,
  Hint,
  Icon,
  IconButton,
  Notice,
  Page,
  PageHeader,
  Problem,
  SearchInput,
  Select,
  Slider,
  State,
  Status,
  Switch,
  Text,
  Toolbar,
  type IconName,
} from "./design";
import { showRemote, TvRemotes } from "./tvremote";
import "./smarthome.css";

/** Home Assistant states, in words. */
const STATES: Record<string, string> = {
  on: "Switched on",
  off: "Switched off",
  open: "Opened",
  opening: "Opening…",
  closed: "Closed",
  closing: "Closing…",
  locked: "Locked",
  unlocked: "Unlocked",
  playing: "Playing",
  paused: "Paused",
  idle: "Idle",
  heat: "Heat",
  cool: "Cool",
  auto: "Auto",
  cleaning: "Cleaning",
  docked: "Docked",
  returning: "Returning",
  disarmed: "Disarmed",
  armed_home: "Armed (home)",
  armed_away: "Armed (away)",
  unavailable: "Unavailable",
  unknown: "Unknown",
};
/** Buttons for actions that are neither a toggle, a slider nor the thermostat stepper. */
const BUTTONS: Record<string, string> = {
  turn_on: "Activate",
  press: "Press",
  play: "Play",
  pause: "Pause",
  start: "Start cleaning",
  return_to_base: "Back to dock",
  lock: "Lock",
  unlock: "Unlock",
  arm_home: "Arm (home)",
  arm_away: "Arm (away)",
  disarm: "Disarm",
  open: "Open",
  close: "Close",
};
// A TV or speaker has its own controls (MediaControls), not the plain buttons row.
const MEDIA = "media_player";
const PRESSES = new Set(["key", "stop", "next", "previous", "volume_up", "volume_down"]);
// Scenes, scripts and buttons have no lasting state worth showing (it is when they last ran).
const MOMENTARY = new Set(["scene", "script", "button"]);
// Scenes and routines live in their own quick row, not in the rooms.
const QUICK = new Set(["scene", "script"]);

/** Each kind of device: its icon, the colour of its light, and what it does in one line. */
type Kind = { icon: IconName; label: string; about: string; tone: string };
const KINDS: Record<string, Kind> = {
  light: {
    icon: "light",
    label: "Lights",
    about: "Tap to switch on or off; the slider dims.",
    tone: "var(--c-data-1)",
  },
  switch: {
    icon: "plug",
    label: "Switches and plugs",
    about: "Switches whatever is plugged in on or off.",
    tone: "var(--c-data-2)",
  },
  fan: {
    icon: "fan",
    label: "Fans",
    about: "Switches the fan on or off.",
    tone: "var(--c-data-3)",
  },
  cover: {
    icon: "blinds",
    label: "Blinds and shutters",
    about: "Open, stop or close; the percentage is how far open.",
    tone: "var(--c-data-4)",
  },
  climate: {
    icon: "thermometer",
    label: "Heating",
    about: "Set the temperature to reach; “Now” is the room’s temperature.",
    tone: "var(--c-data-3)",
  },
  scene: {
    icon: "sparkles",
    label: "Scenes",
    about: "Sets several devices at once, as prepared in Home Assistant.",
    tone: "var(--c-data-5)",
  },
  script: {
    icon: "wand",
    label: "Routines",
    about: "Runs a series of actions prepared in Home Assistant.",
    tone: "var(--c-data-5)",
  },
  button: {
    icon: "dot",
    label: "Buttons",
    about: "Presses once, like a doorbell.",
    tone: "var(--c-fg-muted)",
  },
  media_player: {
    icon: "speaker",
    label: "Speakers and players",
    about: "Play, pause and volume.",
    tone: "var(--c-data-4)",
  },
  input_boolean: {
    icon: "toggle",
    label: "House switches",
    about: "An on/off switch that Home Assistant’s automations follow.",
    tone: "var(--c-fg-muted)",
  },
  vacuum: {
    icon: "bot",
    label: "Robot vacuums",
    about: "Start cleaning or send it back to its dock.",
    tone: "var(--c-data-6)",
  },
  humidifier: {
    icon: "drop",
    label: "Humidifiers",
    about: "Switches the humidifier on or off.",
    tone: "var(--c-data-3)",
  },
  lock: {
    icon: "lock",
    label: "Locks",
    about: "Always asks you to confirm before anything is sent.",
    tone: "var(--c-danger-fg)",
  },
  alarm_control_panel: {
    icon: "shield-check",
    label: "Alarm",
    about: "Always asks you to confirm before anything is sent.",
    tone: "var(--c-danger-fg)",
  },
  siren: {
    icon: "siren",
    label: "Sirens",
    about: "Always asks you to confirm before anything is sent.",
    tone: "var(--c-danger-fg)",
  },
  valve: {
    icon: "drop",
    label: "Valves",
    about: "Always asks you to confirm before anything is sent.",
    tone: "var(--c-danger-fg)",
  },
};
const OTHER: Kind = {
  icon: "dot",
  label: "Other devices",
  about: "",
  tone: "var(--c-fg-muted)",
};
const kindOf = (domain: string) => KINDS[domain] ?? OTHER;
const KIND_ORDER = Object.keys(KINDS);

const offline = (e: Obj) =>
  e.state === "unavailable" || (e.state === "unknown" && !MOMENTARY.has(e.domain));
const lit = (e: Obj) =>
  ["on", "open", "playing", "heat", "cool", "auto", "cleaning"].includes(e.state);
const flatten = (data?: Obj | null): Obj[] =>
  (data?.areas || []).flatMap((area: Obj) => area.entities);

/** "5 minutes ago", in the resident's language. */
function ago(iso?: string | null) {
  const at = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(at)) return "";
  const seconds = (at - Date.now()) / 1000;
  const format = new Intl.RelativeTimeFormat(getLanguage(), { numeric: "auto" });
  for (const [unit, size] of [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ] as const)
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  return format.format(Math.round(seconds), "second");
}

/** The state in words: "On · 70 %", "Closed · 0 % open", "Unavailable"… */
function describe(e: Obj) {
  const a: Obj = e.attributes || {};
  if (MOMENTARY.has(e.domain) && !offline(e)) return "";
  const words = [t(STATES[e.state] || e.state)];
  if (e.domain === "light" && e.state === "on" && a.brightness_pct != null)
    words.push(percent(a.brightness_pct));
  if (e.domain === "cover" && e.state === "open" && a.current_position != null)
    words[0] = t("{n} open").replace("{n}", percent(a.current_position));
  if (e.domain === "media_player" && e.state !== "off") {
    const app = a.app_name || a.source;
    if (a.media_title) words.push(a.media_title);
    if (app && app !== a.media_title) words.push(app);
  }
  if (!e.actions?.length && a.unit_of_measurement) words[0] += " " + a.unit_of_measurement;
  return words.join(" · ").replace(/ %/g, "\u00a0%"); // "70 %" never breaks before the %
}

function matches(e: Obj, query: string) {
  const text = [e.name, e.area, t(kindOf(e.domain).label)].join(" ").toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .every((word) => text.includes(word));
}

export function SmartHome() {
  const admin = useUser()?.role === "admin";
  const house = useData<Obj>("/house-settings");
  const connected = !!house.data?.home_assistant;
  const remotes = useData<Obj>("/tv");
  const [choosing, setChoosing] = useState(false),
    [later, setLater] = useState(false),
    [refreshing, setRefreshing] = useState(false),
    [showOffline, setShowOffline] = useState(false),
    [room, setRoom] = useState(""),
    [query, setQuery] = useState("");
  // Live while the page is open: every 5 s, paused while the tab is hidden (useData).
  const { data, error, reload, setData } = useData<Obj>(connected ? "/home" : null, {
    interval: choosing ? 0 : 5000,
  });
  const all = flatten(data);
  const firstTime = admin && data && !data.curated && !later;
  const favorites: string[] = data?.favorites || [];
  const toggleFavorite = async (id: string) => {
    const next = favorites.includes(id) ? favorites.filter((x) => x !== id) : [...favorites, id];
    setData({ ...data, favorites: next });
    try {
      await api("/home/favorites", "PUT", { favorites: next });
    } finally {
      void reload();
    }
  };
  const hiddenOffline = all.filter(offline).length;
  // Rooms when Home Assistant knows them; otherwise one group per kind of device.
  const byArea = all.some((e) => e.area);
  const areas = [...new Set(all.map((e) => e.area).filter(Boolean))] as string[];
  const visible = all.filter(
    (e) =>
      (showOffline || !offline(e)) &&
      (!query.trim() || matches(e, query.trim())) &&
      (!room || e.area === room),
  );
  const quick = visible.filter((e) => QUICK.has(e.domain));
  const devices = visible.filter((e) => !QUICK.has(e.domain));
  const pinned = devices.filter((e) => favorites.includes(e.id));
  const groups = new Map<string, Obj[]>();
  const order = byArea
    ? (e: Obj) => e.area ?? ""
    : (e: Obj) => String(KIND_ORDER.indexOf(e.domain) + 100) + e.domain;
  for (const e of [...devices].sort((a, b) => (byArea ? 0 : order(a).localeCompare(order(b)))))
    if (!favorites.includes(e.id)) groups.set(order(e), [...(groups.get(order(e)) || []), e]);
  if (byArea && groups.has("")) {
    const elsewhere = groups.get("")!;
    groups.delete("");
    groups.set("", elsewhere); // devices without a room come last
  }
  const kinds = [...new Set(visible.map((e) => e.domain))].filter((d) => KINDS[d]);
  const chooser = connected && (choosing || firstTime);
  // The remote is always in reach: no extra tap (except while choosing what shows).
  const hasRemote = (remotes.data?.items || []).length > 0 && !chooser;
  return (
    <Page width="wide">
      <PageHeader
        room="smart-home"
        title={t("Smart home")}
        actions={
          <>
            {connected && admin && !choosing && !firstTime && (
              <Button icon="settings" onClick={() => setChoosing(true)}>
                {t("Choose what shows")}
              </Button>
            )}
            {connected && (
              <IconButton
                icon="refresh"
                busy={refreshing}
                label={t("Ask Home Assistant for every device’s state now")}
                onClick={async () => {
                  setRefreshing(true);
                  try {
                    await api("/home?refresh=true");
                    await reload();
                  } finally {
                    setRefreshing(false);
                  }
                }}
              />
            )}
          </>
        }
        hint={
          <Hint id="smart-home">
            {t(
              "Tap a device to switch it; I show what the house really reports afterwards. Star the ones you use most to pin them at the top.",
            )}
          </Hint>
        }
      />
      <div className="smart-home" data-remote={hasRemote || undefined}>
        {hasRemote && (
          <section className="smart-home__remote" aria-label={t("TV remote")}>
            <TvRemotes />
          </section>
        )}
        <div className="smart-home__main">
          {house.data && !connected && (
            <State
              kind="not-configured"
              title={t("No Home Assistant yet")}
              action={
                admin && (
                  <Button variant="primary" onClick={() => go("/control?tab=integrations")}>
                    {t("Connect Home Assistant")}
                  </Button>
                )
              }
            >
              {t(
                "Lights, heating and blinds appear here once an administrator connects Home Assistant.",
              )}
            </State>
          )}
          <Problem error={error} onRetry={reload} />
          {chooser ? (
            <Chooser
              first={!!firstTime}
              onClose={async (saved) => {
                setChoosing(false);
                if (!saved) setLater(true);
                await reload();
              }}
            />
          ) : (
            data && (
              <>
                {!all.length && (
                  <State kind="empty" title={t("Nothing to control yet")}>
                    {admin
                      ? t("No device is chosen for this room. Use “Choose what shows”.")
                      : t("An administrator hasn’t chosen any device for this room yet.")}
                  </State>
                )}
                {(all.length > 8 || areas.length > 1) && (
                  <Toolbar label={t("Find a device")}>
                    <SearchInput
                      label={t("Search devices")}
                      placeholder={t("Search a device or a room…")}
                      value={query}
                      onChange={setQuery}
                    />
                    {areas.length > 1 && (
                      <Select
                        aria-label={t("Room")}
                        value={room}
                        onChange={(e) => setRoom(e.target.value)}
                      >
                        <option value="">{t("Every room")}</option>
                        {areas.map((area) => (
                          <option key={area} value={area}>
                            {area}
                          </option>
                        ))}
                      </Select>
                    )}
                  </Toolbar>
                )}
                {quick.length > 0 && (
                  <section className="smart-quick" aria-labelledby="smart-quick-title">
                    <Text as="h2" style="label" tone="muted">
                      <span id="smart-quick-title">{t("Scenes and routines")}</span>
                    </Text>
                    <div className="smart-quick__row">
                      {quick.map((e) => (
                        <QuickButton key={e.id} entity={e} onChanged={reload} />
                      ))}
                    </div>
                  </section>
                )}
                <div className="smart-home__rooms">
                  {pinned.length > 0 && (
                    <Group
                      title={t("My favourites")}
                      favorite
                      entities={pinned}
                      favorites={favorites}
                      onFavorite={toggleFavorite}
                      onChanged={reload}
                    />
                  )}
                  {[...groups].map(([key, entities]) => (
                    <Group
                      key={key}
                      title={
                        byArea
                          ? entities[0].area || t("Elsewhere in the house")
                          : t(kindOf(entities[0].domain).label)
                      }
                      entities={entities}
                      favorites={favorites}
                      onFavorite={toggleFavorite}
                      onChanged={reload}
                    />
                  ))}
                </div>
                {(query.trim() || room) && !visible.length && (
                  <State kind="empty" title={t("No device matches this search.")} />
                )}
                {hiddenOffline > 0 && (
                  <div>
                    <Button
                      variant="quiet"
                      size="s"
                      pressed={showOffline}
                      onClick={() => setShowOffline(!showOffline)}
                    >
                      {showOffline
                        ? t("Hide unavailable devices")
                        : t("Show {n} unavailable").replace("{n}", String(hiddenOffline))}
                    </Button>
                  </div>
                )}
                {kinds.length > 0 && (
                  <Disclosure summary={t("How each kind of device works")}>
                    <dl className="smart-home__kinds">
                      {kinds.map((domain) => (
                        <div key={domain}>
                          <dt>{t(kindOf(domain).label)}</dt>
                          <dd>{t(kindOf(domain).about)}</dd>
                        </div>
                      ))}
                    </dl>
                  </Disclosure>
                )}
              </>
            )
          )}
        </div>
      </div>
    </Page>
  );
}

/** A room (or kind) of devices, with "All lights off / on" when it has lights. */
function Group({
  title,
  entities,
  favorites,
  favorite = false,
  onFavorite,
  onChanged,
}: {
  title: string;
  entities: Obj[];
  favorites: string[];
  favorite?: boolean;
  onFavorite: (id: string) => void;
  onChanged: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const lights = entities.filter((e) => e.domain === "light" && !offline(e) && !e.sensitive);
  const on = lights.filter((e) => e.state === "on").length;
  return (
    <section
      className="smart-room"
      data-full={entities.length > 8 || undefined}
      data-favorites={favorite || undefined}
      // a room grows with its devices, so a big room lays them side by side, not in a tall column
      style={{ "--devices": entities.length } as CSSProperties}
      aria-label={title}
    >
      <header className="smart-room__head">
        <Text as="h2" style="title-m">
          {favorite && <Icon name="star" size="s" />} {title}
        </Text>
        {lights.length > 0 && (
          <Text style="caption" tone="muted">
            {on
              ? t("{n} of {total} lights on")
                  .replace("{n}", String(on))
                  .replace("{total}", String(lights.length))
              : t("Lights off")}
          </Text>
        )}
        {lights.length > 1 && (
          <Button
            size="s"
            variant="quiet"
            icon="light"
            busy={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              const results = await Promise.allSettled(
                lights.map((e) =>
                  api("/home/" + encodeURIComponent(e.id) + "/action", "POST", {
                    action: on ? "turn_off" : "turn_on",
                    value: null,
                  }),
                ),
              );
              if (results.some((r) => r.status === "rejected"))
                setError(t("Some lights didn’t answer. Try again in a moment."));
              await onChanged();
              setBusy(false);
            }}
          >
            {on ? t("All lights off") : t("All lights on")}
          </Button>
        )}
      </header>
      <Problem error={error} />
      <div className="smart-room__grid">
        {entities.map((e) => (
          <Device
            key={e.id}
            entity={e}
            favorite={favorites.includes(e.id)}
            onFavorite={() => onFavorite(e.id)}
            onChanged={onChanged}
          />
        ))}
      </div>
    </section>
  );
}

/** A scene or routine: one tap runs it. */
function QuickButton({ entity, onChanged }: { entity: Obj; onChanged: () => Promise<unknown> }) {
  const [state, setState] = useState<"" | "busy" | "done" | "error">("");
  const kind = kindOf(entity.domain);
  return (
    <span className="smart-quick__item">
      <Button
        icon={kind.icon}
        busy={state === "busy"}
        disabled={offline(entity)}
        title={t(kind.about)}
        onClick={async () => {
          setState("busy");
          try {
            await api("/home/" + encodeURIComponent(entity.id) + "/action", "POST", {
              action: "turn_on",
              value: null,
            });
            setState("done");
            void onChanged();
          } catch {
            setState("error");
          }
        }}
      >
        {entity.name}
      </Button>
      {state === "done" && <Status tone="success">{t("Done")}</Status>}
      {state === "error" && <Status tone="danger">{t("Failed")}</Status>}
    </span>
  );
}

function Device({
  entity,
  favorite,
  onFavorite,
  onChanged,
}: {
  entity: Obj;
  favorite: boolean;
  onFavorite: () => void;
  onChanged: () => Promise<unknown>;
}) {
  const [shown, setShown] = useState<Obj>(entity),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [note, setNote] = useState(""),
    [peek, setPeek] = useState(false),
    [pending, setPending] = useState<Obj | null>(null),
    [closer, setCloser] = useState(false);
  const admin = useUser()?.role === "admin";
  const press = useRef<ReturnType<typeof setTimeout>>(undefined);
  // The house's latest reading wins, except while this card is waiting for its own answer.
  useEffect(() => {
    if (!busy) setShown(entity);
  }, [entity]);
  const attributes: Obj = shown.attributes || {};
  // What the device can do and the admin keeps on its panel (all it reports, unless taken off).
  const panel: Obj[] = shown.controls || [];
  const can = (action: string) =>
    shown.actions?.includes(action) &&
    panel.find((control) => control.id === action)?.shown !== false;
  const off = offline(shown);
  const kind = kindOf(shown.domain);
  const answered = (result: Obj) => {
    setShown(result.entity);
    // A key press or a volume step has no state to show: sent is all there is to say.
    setNote(
      result.status === "completed" || PRESSES.has(result.action)
        ? ""
        : t("Sent. Home Assistant doesn’t show the change yet."),
    );
  };
  const run = async (action: string, value?: number | string, guess?: Obj) => {
    const before = shown;
    setBusy(true);
    setError("");
    setNote("");
    if (guess) setShown({ ...shown, ...guess, attributes: { ...attributes, ...guess.attributes } });
    try {
      const result = await api("/home/" + encodeURIComponent(entity.id) + "/action", "POST", {
        action,
        value: value ?? null,
      });
      if (result.status === "needs_confirmation") {
        setShown(before);
        setPending({ ...result, action });
      } else answered(result);
      void onChanged();
    } catch (e) {
      setShown(before);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const on = lit(shown);
  const glowing = on && shown.domain === "light";
  const toggle = can("toggle");
  const changed = ago(shown.last_changed);
  return (
    <article
      data-domain={shown.domain}
      className="smart-device"
      data-on={on || undefined}
      data-lit={glowing || undefined}
      data-offline={off || undefined}
      data-peek={peek || undefined}
      style={{ "--kind": kind.tone } as CSSProperties}
      // Long-press on a phone shows when it last changed (hover does on desktop).
      onPointerDown={(e) => {
        if (e.pointerType === "touch") press.current = setTimeout(() => setPeek(true), 500);
      }}
      onPointerUp={() => clearTimeout(press.current)}
      onPointerLeave={() => {
        clearTimeout(press.current);
        setPeek(false);
      }}
    >
      <div className="smart-device__head">
        <span className="smart-device__icon" aria-hidden="true">
          {glowing ? <Glyph name="room.smart-home" /> : <Icon name={kind.icon} />}
        </span>
        <div className="smart-device__title">
          <strong>{shown.name}</strong>
          <small>{off ? t("Unavailable: Home Assistant can’t reach it") : describe(shown)}</small>
        </div>
        <IconButton
          icon="star"
          size="s"
          pressed={favorite}
          data-on={favorite || undefined}
          className="smart-device__star"
          label={favorite ? t("Remove from my favourites") : t("Add to my favourites")}
          onClick={onFavorite}
        />
        {admin && (
          <IconButton
            icon="sliders"
            size="s"
            className="smart-device__closer"
            label={t("Look closer: what {name} can do").replace("{name}", shown.name)}
            onClick={() => setCloser(true)}
          />
        )}
      </div>
      {shown.sensitive && (
        <Badge tone="private">
          <Icon name="lock" size="s" /> {t("Sensitive: asks to confirm")}
        </Badge>
      )}
      {toggle && (
        <Switch
          checked={shown.state === "on"}
          disabled={busy || off}
          label={shown.state === "on" ? t("Turn off") : t("Turn on")}
          onChange={() => run("toggle", undefined, { state: shown.state === "on" ? "off" : "on" })}
        />
      )}
      {can("brightness_pct") && (
        <Slider
          showLabel
          label={t("Brightness")}
          value={shown.state === "on" ? (attributes.brightness_pct ?? 100) : 0}
          format={(v) => v + "\u00a0%"}
          onCommit={(value) =>
            void run("brightness_pct", value, {
              state: value ? "on" : "off",
              attributes: { brightness_pct: value },
            })
          }
        />
      )}
      {can("color") && (
        <ColorField
          label={t("Colour")}
          value={attributes.color}
          disabled={busy || off}
          onCommit={(hex) => void run("color", hex, { state: "on", attributes: { color: hex } })}
        />
      )}
      {can("warmth") && (
        <Slider
          showLabel
          label={t("Warmth")}
          min={panel.find((c) => c.id === "warmth")?.min ?? 2000}
          max={panel.find((c) => c.id === "warmth")?.max ?? 6500}
          step={100}
          value={attributes.color_temp_kelvin ?? 3000}
          format={(v) => v + "\u00a0K"}
          onCommit={(value) =>
            void run("warmth", value, { state: "on", attributes: { color_temp_kelvin: value } })
          }
        />
      )}
      {can("percentage") && (
        <Slider
          showLabel
          label={t("Speed")}
          value={attributes.percentage ?? 0}
          format={(v) => v + "\u00a0%"}
          onCommit={(value) => void run("percentage", value, { attributes: { percentage: value } })}
        />
      )}
      {(["effect", "preset"] as const).map(
        (id) =>
          can(id) && (
            <Field key={id} label={id === "effect" ? t("Effect") : t("Mode")}>
              <Select
                value={(id === "effect" ? attributes.effect : attributes.preset_mode) ?? ""}
                disabled={busy || off}
                onChange={(e) => void run(id, e.target.value)}
              >
                <option value="" disabled>
                  {t("Choose…")}
                </option>
                {(panel.find((c) => c.id === id)?.options || []).map((option: string) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </Field>
          ),
      )}
      {shown.domain === MEDIA && !off && <MediaControls entity={shown} busy={busy} run={run} />}
      {shown.domain === "cover" && (
        <div className="smart-device__row">
          {can("open") && (
            <Button size="s" icon="chevron-up" disabled={busy || off} onClick={() => run("open")}>
              {t("Open")}
            </Button>
          )}
          {can("stop") && (
            <Button size="s" icon="stop" disabled={busy || off} onClick={() => run("stop")}>
              {t("Stop")}
            </Button>
          )}
          {can("close") && (
            <Button
              size="s"
              icon="chevron-down"
              disabled={busy || off}
              onClick={() => run("close")}
            >
              {t("Close")}
            </Button>
          )}
        </div>
      )}
      {can("set_temperature") && <Thermostat entity={shown} busy={busy || off} run={run} />}
      {shown.domain !== "cover" && shown.domain !== MEDIA && (
        <div className="smart-device__row">
          {shown.actions
            ?.filter((action: string) => BUTTONS[action] && !(toggle && action === "turn_on"))
            .map((action: string) => (
              <Button
                size="s"
                key={action}
                icon={action === "play" ? "play" : action === "pause" ? "pause" : undefined}
                disabled={busy || off || (action === "play" && shown.state === "playing")}
                onClick={() => run(action)}
              >
                {t(BUTTONS[action])}
              </Button>
            ))}
        </div>
      )}
      {pending && (
        <div role="alertdialog" aria-label={t("Confirm")}>
          <Notice
            tone="warning"
            title={t("Sensitive device. Confirm to send:")}
            action={
              <span className="smart-device__row">
                <Button
                  size="s"
                  variant="primary"
                  busy={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      answered(await api("/home/confirmations/" + pending.confirmation_id, "POST"));
                      void onChanged();
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setPending(null);
                      setBusy(false);
                    }
                  }}
                >
                  {t("Confirm")}
                </Button>
                <Button size="s" variant="quiet" onClick={() => setPending(null)}>
                  {t("Cancel")}
                </Button>
              </span>
            }
          >
            <strong>
              {t(
                pending.action === "toggle"
                  ? shown.state === "on"
                    ? "Turn off"
                    : "Turn on"
                  : pending.action === "turn_off"
                    ? "Turn off"
                    : BUTTONS[pending.action] || "Change",
              )}
            </strong>
          </Notice>
        </div>
      )}
      {note && <small className="smart-device__note">{note}</small>}
      <Problem error={error} />
      {closer && (
        <LookCloser
          entity={shown}
          onClose={() => setCloser(false)}
          onChanged={async () => {
            await onChanged();
          }}
        />
      )}
      {changed && (
        <time className="smart-device__changed" dateTime={shown.last_changed}>
          {t("Changed {when}").replace("{when}", changed)}
        </time>
      )}
    </article>
  );
}

// What each control is called on a device's panel (Look closer).
const CONTROL_NAMES: Record<string, string> = {
  brightness_pct: "Brightness",
  color: "Colour",
  warmth: "Warmth",
  effect: "Effect",
  percentage: "Speed",
  preset: "Mode",
  position: "Position",
  set_temperature: "Temperature",
  hvac_mode: "Heating mode",
  volume: "Volume",
  source: "Source",
};

/** Admins look closer at one device: everything Home Assistant reports about it, and every
 *  control HouseOS can draw from that, each kept on its panel or taken off. */
function LookCloser({
  entity,
  onClose,
  onChanged,
}: {
  entity: Obj;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const path = "/home/" + encodeURIComponent(entity.id);
  const seen = useData<Obj>(path + "/inspect");
  const [error, setError] = useState("");
  const controls: Obj[] = seen.data?.controls || [];
  const keep = async (id: string, shown: boolean) => {
    setError("");
    try {
      await api(path + "/controls", "PUT", {
        hidden: controls.filter((c) => (c.id === id ? !shown : !c.shown)).map((c) => c.id),
      });
      await Promise.all([seen.reload(), onChanged()]);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Sheet
      title={t("What {name} can do").replace("{name}", entity.name)}
      place="side"
      onClose={onClose}
    >
      <div className="smart-closer">
        <Text tone="muted">
          {t("Read from the device itself. Keep on its panel what the house should see.")}
        </Text>
        {seen.data && !controls.length && (
          <Text>{t("Nothing more to set here: it turns on and off.")}</Text>
        )}
        {controls.map((control) => (
          <Switch
            key={control.id}
            checked={control.shown}
            label={t(CONTROL_NAMES[control.id] || control.id)}
            hint={
              control.kind === "warmth"
                ? control.min + "–" + control.max + " K"
                : control.options?.length
                  ? control.options.slice(0, 6).join(", ") + (control.options.length > 6 ? "…" : "")
                  : undefined
            }
            onChange={(on) => void keep(control.id, on)}
          />
        ))}
        <Problem error={error || seen.error} onRetry={seen.reload} />
        {seen.data && (
          <Disclosure summary={t("Everything it reports")}>
            <List label={t("Everything it reports")}>
              {Object.entries(seen.data.reported || {}).map(([key, value]) => (
                <ListRow key={key} title={key} detail={String(value)} />
              ))}
            </List>
          </Disclosure>
        )}
      </div>
    </Sheet>
  );
}

/** The page's TV remote for this Home Assistant TV: the same name, or else the only TV remote
 *  with arrows when the house has only one TV with arrows. */
function useRemoteFor(entity: Obj) {
  const remotes: Obj[] = useData<Obj>("/tv").data?.items || [];
  const tvs = remotes.filter((r) => r.target === "tv" && r.capabilities?.dpad);
  const keyed = flatten(useData<Obj>("/home").data).filter((e) => e.actions?.includes("key"));
  const name = String(entity.name || "").toLowerCase();
  return (
    tvs.find((r) => String(r.name).toLowerCase() === name) ||
    (tvs.length === 1 && keyed.length === 1 ? tvs[0] : undefined)
  );
}

/** A TV or speaker: power, playback, volume (steps when a soundbar plays the sound, since the
 * TV's own level no longer changes what you hear), its source and, when its Home Assistant
 * integration has one, a remote with arrows. Each shows only if the device reports it. */
function MediaControls({
  entity,
  busy,
  run,
}: {
  entity: Obj;
  busy: boolean;
  run: (action: string, value?: number | string, guess?: Obj) => Promise<void>;
}) {
  const a: Obj = entity.attributes || {};
  const can = (action: string) => entity.actions?.includes(action);
  const [pad, setPad] = useState(false);
  const remote = useRemoteFor(entity);
  const asleep = ["off", "standby"].includes(entity.state);
  const playing = entity.state === "playing";
  const icon = (action: string, label: string, name: IconName, value?: string, on = false) =>
    can(action) && (
      <IconButton
        icon={name}
        size="s"
        variant={on ? "primary" : "secondary"}
        pressed={on || undefined}
        label={label}
        disabled={busy}
        onClick={() => void run(action, value)}
      />
    );
  const steps = can("volume_up") && (a.external_speakers || !can("volume"));
  const mute = a.is_volume_muted
    ? icon("unmute", t("Unmute"), "volume-off", undefined, true)
    : icon("mute", t("Mute"), "volume-off");
  return (
    <>
      <div className="smart-device__row">
        {asleep
          ? can("turn_on") && (
              <Button size="s" icon="power" disabled={busy} onClick={() => void run("turn_on")}>
                {t("Turn on")}
              </Button>
            )
          : icon("turn_off", t("Turn off"), "power")}
        {!asleep && (
          <>
            {icon("previous", t("Previous"), "previous")}
            {playing ? icon("pause", t("Pause"), "pause") : icon("play", t("Play"), "play")}
            {icon("stop", t("Stop"), "stop")}
            {icon("next", t("Next"), "next")}
          </>
        )}
      </div>
      {!asleep && can("volume") && !a.external_speakers && (
        // the level and mute on one line: mute never wraps alone onto a row of its own
        <div className="smart-device__volume">
          <Slider
            showLabel
            label={t("Volume")}
            value={a.volume_pct ?? 0}
            format={(v) => v + "\u00a0%"}
            onCommit={(value) => void run("volume", value, { attributes: { volume_pct: value } })}
          />
          {mute}
        </div>
      )}
      {!asleep && !(can("volume") && !a.external_speakers) && (steps || can("mute")) && (
        <div className="smart-device__row" role="group" aria-label={t("Volume")}>
          {steps && icon("volume_down", t("Volume down"), "minus")}
          {steps && (
            <span className="smart-device__level">
              <Icon name="volume" size="s" />
              {a.external_speakers ? t("Speakers") : (a.volume_pct ?? "")}
            </span>
          )}
          {steps && icon("volume_up", t("Volume up"), "add")}
          {mute}
        </div>
      )}
      {!asleep && can("source") && (
        <Field label={t("Source")}>
          <Select
            value={a.source_list?.includes(a.source) ? a.source : ""}
            disabled={busy}
            onChange={(e) =>
              void run("source", e.target.value, { attributes: { source: e.target.value } })
            }
          >
            {!a.source_list?.includes(a.source) && <option value="">{a.source || "–"}</option>}
            {(a.source_list || []).map((source: string) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {!asleep &&
        can("key") &&
        (remote ? (
          // The page's remote already has this TV's arrows: one remote on the page, not two.
          <div>
            <Button size="s" variant="quiet" icon="tv" onClick={() => showRemote(remote)}>
              {t("Remote: arrows and OK")}
            </Button>
          </div>
        ) : (
          <>
            <div>
              <Button
                size="s"
                variant="quiet"
                icon={pad ? "chevron-up" : "chevron-down"}
                aria-expanded={pad}
                onClick={() => setPad(!pad)}
              >
                {pad ? t("Hide the remote") : t("Remote: arrows and OK")}
              </Button>
            </div>
            {pad && (
              <div className="tv-remote__pad" role="group" aria-label={t("Arrows and OK")}>
                {(
                  [
                    ["BACK", "is-back", t("Back"), "undo"],
                    ["DPAD_UP", "is-up", t("Up"), "chevron-up"],
                    ["HOME", "is-home", t("Home"), "home"],
                    ["DPAD_LEFT", "is-left", t("Left"), "chevron-left"],
                    ["DPAD_RIGHT", "is-right", t("Right"), "chevron-right"],
                    ["DPAD_DOWN", "is-down", t("Down"), "chevron-down"],
                  ] as const
                ).map(([key, place, label, name]) => (
                  <IconButton
                    key={key}
                    icon={name}
                    variant="secondary"
                    className={"tv-remote__key " + place}
                    label={label}
                    disabled={busy}
                    onClick={() => void run("key", key)}
                  />
                ))}
                <Button
                  variant="primary"
                  className="tv-remote__key is-ok"
                  disabled={busy}
                  onClick={() => void run("key", "DPAD_CENTER")}
                >
                  {t("OK")}
                </Button>
              </div>
            )}
          </>
        ))}
    </>
  );
}

function Thermostat({
  entity,
  busy,
  run,
}: {
  entity: Obj;
  busy: boolean;
  run: (action: string, value?: number | string, guess?: Obj) => Promise<void>;
}) {
  const a: Obj = entity.attributes || {};
  const step = a.target_temp_step || 0.5,
    target = a.temperature;
  const set = (delta: number) => {
    const value = Math.min(a.max_temp ?? 35, Math.max(a.min_temp ?? 5, (target ?? 20) + delta));
    void run("set_temperature", value, { attributes: { temperature: value } });
  };
  return (
    <>
      <div className="smart-device__row smart-device__thermostat">
        <IconButton
          icon="minus"
          size="s"
          variant="secondary"
          label={t("Cooler")}
          disabled={busy}
          onClick={() => set(-step)}
        />
        <span>
          {t("Target")} <strong className="tabular">{target != null ? target + "°" : "–"}</strong>
        </span>
        <IconButton
          icon="add"
          size="s"
          variant="secondary"
          label={t("Warmer")}
          disabled={busy}
          onClick={() => set(step)}
        />
      </div>
      {a.current_temperature != null && (
        <Text style="caption" tone="muted">
          {t("Now")} {a.current_temperature}°
        </Text>
      )}
      {entity.actions.includes("hvac_mode") && (
        <Field label={t("Mode")}>
          <Select
            value={entity.state}
            disabled={busy}
            onChange={(e) => void run("hvac_mode", e.target.value, { state: e.target.value })}
          >
            {(a.hvac_modes || []).map((mode: string) => (
              <option key={mode} value={mode}>
                {t(STATES[mode] || mode)}
              </option>
            ))}
          </Select>
        </Field>
      )}
    </>
  );
}

/** The administrator picks what this room (and Nox) shows, grouped by room, with counts. */
function Chooser({ first, onClose }: { first: boolean; onClose: (saved: boolean) => void }) {
  const { data, error } = useData<Obj>("/home?choose=true");
  const all = flatten(data);
  const [picked, setPicked] = useState<Set<string> | null>(null),
    [query, setQuery] = useState(""),
    [internal, setInternal] = useState(false),
    [saving, setSaving] = useState(false),
    [failure, setFailure] = useState("");
  // First time, suggest what already works: shown by default and not offline.
  useEffect(() => {
    if (data && !picked)
      setPicked(new Set(all.filter((e) => e.shown && !(first && offline(e))).map((e) => e.id)));
  }, [data]);
  if (!data || !picked)
    return (
      <>
        <Problem error={error} />
        {!error && <State kind="loading" title={t("Asking Home Assistant for its devices…")} />}
      </>
    );
  const internalCount = all.filter((e) => e.internal).length;
  const offered = all.filter(
    (e) =>
      (internal || !e.internal || picked.has(e.id)) && (!query.trim() || matches(e, query.trim())),
  );
  const set = (ids: string[], value: boolean) => {
    const next = new Set(picked);
    ids.forEach((id) => (value ? next.add(id) : next.delete(id)));
    setPicked(next);
  };
  const areas = new Map<string, Obj[]>();
  for (const e of offered) areas.set(e.area ?? "", [...(areas.get(e.area ?? "") || []), e]);
  const kinds = new Map<string, string[]>();
  const byKind = (a: Obj, b: Obj) => KIND_ORDER.indexOf(a.domain) - KIND_ORDER.indexOf(b.domain);
  for (const e of all.filter((e) => !e.internal).sort(byKind))
    kinds.set(e.domain, [...(kinds.get(e.domain) || []), e.id]);
  return (
    <section className="smart-chooser" aria-labelledby="smart-chooser-title">
      <Notice title={<span id="smart-chooser-title">{t("Choose what this room shows")}</span>}>
        {t(
          "Home Assistant shares {n} devices. Tick the ones people here will use: everything else stays out of sight, for Nox too. New devices appear only once you choose them.",
        ).replace("{n}", String(all.length))}
      </Notice>
      <ChipGroup label={t("Choose by kind")}>
        {[...kinds].map(([domain, ids]) => {
          const every = ids.every((id) => picked.has(id));
          return (
            <Chip
              key={domain}
              kind="filter"
              icon={kindOf(domain).icon}
              selected={every}
              count={ids.length}
              onToggle={() => set(ids, !every)}
            >
              {t("All: {kind}").replace("{kind}", t(kindOf(domain).label))}
            </Chip>
          );
        })}
      </ChipGroup>
      <SearchInput
        label={t("Search devices")}
        placeholder={t("Search a device or a room…")}
        value={query}
        onChange={setQuery}
      />
      <div className="smart-home__rooms">
        {[...areas].map(([area, entities]) => {
          const ids = entities.map((e) => e.id);
          const count = ids.filter((id) => picked.has(id)).length;
          return (
            <section
              key={area}
              className="smart-room"
              data-full={entities.length > 8 || undefined}
              aria-label={area || t("Elsewhere in the house")}
            >
              <header className="smart-room__head">
                <Text as="h3" style="title-m">
                  {area || t("Elsewhere in the house")}
                </Text>
                <Text style="caption" tone="muted">
                  {t("{n} of {total} chosen")
                    .replace("{n}", String(count))
                    .replace("{total}", String(ids.length))}
                </Text>
                <Checkbox
                  checked={count === ids.length}
                  ref={(box: HTMLInputElement | null) => {
                    if (box) box.indeterminate = count > 0 && count < ids.length;
                  }}
                  onChange={() => set(ids, count < ids.length)}
                  label={t("Whole room")}
                />
              </header>
              <ul className="smart-pick">
                {entities.map((e) => (
                  <li
                    key={e.id}
                    data-muted={offline(e) || e.internal || undefined}
                    style={{ "--kind": kindOf(e.domain).tone } as CSSProperties}
                  >
                    <Checkbox
                      checked={picked.has(e.id)}
                      onChange={(event) => set([e.id], event.target.checked)}
                      label={
                        <span className="smart-pick__name">
                          <Icon name={kindOf(e.domain).icon} size="s" />
                          <span>
                            <strong>{e.name}</strong>
                            <small>
                              {t(kindOf(e.domain).label)}
                              {describe(e) && " · " + describe(e)}
                              {e.internal && " · " + t("Home Assistant setting")}
                            </small>
                          </span>
                        </span>
                      }
                    />
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      {internalCount > 0 && (
        <div>
          <Button
            variant="quiet"
            size="s"
            pressed={internal}
            onClick={() => setInternal(!internal)}
          >
            {internal
              ? t("Hide Home Assistant settings and diagnostics")
              : t("Show {n} Home Assistant settings and diagnostics").replace(
                  "{n}",
                  String(internalCount),
                )}
          </Button>
        </div>
      )}
      <Problem error={failure} />
      <div className="smart-chooser__bar">
        <Text style="title-s">{t("{n} devices chosen").replace("{n}", String(picked.size))}</Text>
        <Button variant="quiet" onClick={() => onClose(false)}>
          {first ? t("Not now") : t("Cancel")}
        </Button>
        <Button
          variant="primary"
          busy={saving}
          onClick={async () => {
            setSaving(true);
            setFailure("");
            try {
              await api("/home/selection", "PUT", { shown: [...picked] });
              onClose(true);
            } catch (e) {
              setFailure((e as Error).message);
              setSaving(false);
            }
          }}
        >
          {t("Done")}
        </Button>
      </div>
    </section>
  );
}

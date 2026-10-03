// The TV remote: one remote, and a choice of what it controls: the TV itself (through Home
// Assistant) or only the Chromecast / smart TV HouseOS casts to. Only the buttons the chosen
// target really has are shown. A press lights the button at once; the server says whether it
// was sent. Arrows, Enter and Backspace work while the remote has focus.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, ApiError, useData, type Obj } from "./api";
import { t } from "./i18n";
import {
  Button,
  Disclosure,
  Field,
  Form,
  Icon,
  IconButton,
  Input,
  Problem,
  Segmented,
  Select,
  Sheet,
  Slider,
  Status,
  Text,
  type IconName,
} from "./design";
import { useReveal } from "./design/motion";
import "./tvremote.css";

/** Server codes in words (the rest use the server's sentence). */
const CODES: Record<string, () => string> = {
  TV_UNREACHABLE: () => t("The TV didn't answer. Check it is on and on the same Wi-Fi."),
  TV_REMOTE_NOT_PAIRED: () =>
    t("The remote isn't set up on this TV yet. Choose Set up the remote."),
  TV_KEY_UNSUPPORTED: () => t("This TV doesn't have that button in HouseOS."),
  TV_INPUT_UNKNOWN: () => t("Choose one of the inputs this TV reports."),
  TV_PAIRING_CODE: () => t("That code didn't match. Start again to get a new code."),
  TV_PAIRING_EXPIRED: () => t("The code expired. Start again to get a new one."),
  TV_REMOTE_UNAVAILABLE: () => t("This server needs an update before it can be a TV remote."),
};
function sentence(e: unknown) {
  const code = e instanceof ApiError && typeof e.detail === "object" ? e.detail.code : "";
  return CODES[code]?.() || (e as Error).message;
}
// Apps a Google TV reports by package name; unknown packages are not shown.
const APPS: [string, string][] = [
  ["youtube", "YouTube"],
  ["netflix", "Netflix"],
  ["disney", "Disney+"],
  ["amazon", "Prime Video"],
  ["plex", "Plex"],
  ["spotify", "Spotify"],
  ["jellyfin", "Jellyfin"],
  ["launcher", "Home screen"],
];
function appName(app?: string) {
  if (!app) return "";
  if (!app.includes(".")) return app === "Backdrop" ? "" : app;
  const known = APPS.find(([part]) => app.toLowerCase().includes(part));
  return known ? (known[1] === "Home screen" ? t("Home screen") : known[1]) : "";
}
const KEYBOARD: Record<string, string> = {
  ArrowUp: "DPAD_UP",
  ArrowDown: "DPAD_DOWN",
  ArrowLeft: "DPAD_LEFT",
  ArrowRight: "DPAD_RIGHT",
  Enter: "DPAD_CENTER",
  Backspace: "BACK",
  "+": "VOLUME_UP",
  "=": "VOLUME_UP",
  "-": "VOLUME_DOWN",
};

const PICKED = "houseos.tv-remote.target";
/** True when this device's screen already has a TV remote with arrows (Home Assistant): then
 * pairing the device's own remote is optional, the TV's keys already reach what is on screen. */
export function steersScreen(remotes: Obj[], device: Obj) {
  return remotes.some((r) => r.id === device.id && r.target === "tv" && r.capabilities?.dpad);
}
const keyOf = (tv: Obj) => tv.id + ":" + tv.target;
const CALLED = "houseos:tv-remote";
/** Brings this TV up in the page's remote, scrolled into view and focused for its arrows. */
export function showRemote(tv: Obj) {
  dispatchEvent(new CustomEvent(CALLED, { detail: keyOf(tv) }));
}
function remembered() {
  try {
    return localStorage.getItem(PICKED) || "";
  } catch {
    return "";
  }
}

/** The house's TV remotes, inline on Smart home: the one you chose last, and a small switcher
 *  when there are several (by name, or by what it controls when two share a name). */
export function TvRemotes() {
  const { data, error, reload } = useData<Obj>("/tv");
  const [chosen, setChosen] = useState(remembered),
    [called, setCalled] = useState(0);
  const box = useReveal<HTMLDivElement>(called, ".tv-remote");
  const remotes: Obj[] = data?.items || [];
  // The one you chose last on this device, else the first TV itself, else the first device.
  const current =
    remotes.find((r) => keyOf(r) === chosen) ||
    remotes.find((r) => r.target === "tv") ||
    remotes[0];
  const choose = (key: string) => {
    setChosen(key);
    try {
      localStorage.setItem(PICKED, key);
    } catch {
      // private window: the choice lasts until the page closes
    }
  };
  // A device card's "Remote" button: this remote shows that TV, lit for a moment.
  useEffect(() => {
    const call = (e: Event) => {
      choose((e as CustomEvent<string>).detail);
      setCalled((n) => n + 1);
    };
    addEventListener(CALLED, call);
    return () => removeEventListener(CALLED, call);
  }, []);
  useEffect(() => {
    if (!called) return;
    const done = setTimeout(() => setCalled(0), 1500);
    return () => clearTimeout(done);
  }, [called]);
  const shared = new Set(remotes.map((r) => r.name)).size < remotes.length;
  return (
    <div className="tv-remotes" ref={box} data-called={called || undefined}>
      <Problem error={error} onRetry={reload} />
      {remotes.length > 1 && current && (
        <Segmented
          label={t("What the remote controls")}
          value={keyOf(current)}
          onChange={choose}
          options={remotes.map((r) => ({
            value: keyOf(r),
            label: shared
              ? r.target === "tv"
                ? t("The TV")
                : r.adapter === "dlna"
                  ? "DLNA"
                  : "Chromecast"
              : r.name,
            icon: r.target === "tv" ? "tv" : "cast",
          }))}
        />
      )}
      {current && (
        <Remote
          key={keyOf(current)}
          tv={current}
          onChanged={reload}
          covered={steersScreen(remotes, current)}
        />
      )}
    </div>
  );
}

function Remote({
  tv,
  onChanged,
  covered,
}: {
  tv: Obj;
  onChanged: () => Promise<unknown>;
  covered: boolean;
}) {
  const can: Obj = tv.capabilities || {};
  const state: Obj = tv.state || {};
  const [lit, setLit] = useState(""),
    [error, setError] = useState(""),
    [said, setSaid] = useState(""),
    [pairing, setPairing] = useState(false),
    [picked, setPicked] = useState("");
  useEffect(() => setPicked(""), [state.input]);
  // Presses go out in order, never blocking the next tap.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const refresh = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(refresh.current), []);
  const press = (key: string, label: string, input?: string) => {
    setLit(key);
    setTimeout(() => setLit((current) => (current === key ? "" : current)), 220);
    setError("");
    setSaid(label);
    queue.current = queue.current.then(async () => {
      try {
        await api("/tv/" + tv.id + "/remote", "POST", {
          key,
          input: input ?? null,
          target: tv.target || "device",
        });
        if (!key.startsWith("DPAD_") && key !== "BACK" && key !== "HOME") {
          clearTimeout(refresh.current);
          refresh.current = setTimeout(() => void onChanged(), 1500);
        }
      } catch (e) {
        setSaid("");
        setError(sentence(e));
      }
    });
  };
  // An exact level, sent once when the slider is let go; then what the TV reports.
  const setVolume = (level: number) => {
    setError("");
    setSaid(t("Volume") + " " + level);
    queue.current = queue.current.then(async () => {
      try {
        await api("/tv/" + tv.id + "/remote", "POST", {
          key: "VOLUME_SET",
          level,
          target: tv.target || "device",
        });
        await onChanged();
        clearTimeout(refresh.current);
        refresh.current = setTimeout(() => void onChanged(), 1500);
      } catch (e) {
        setSaid("");
        setError(sentence(e));
      }
    });
  };
  const has = (key: string) =>
    key.startsWith("DPAD_") || key === "BACK"
      ? can.dpad
      : key.startsWith("VOLUME_")
        ? can.volume
        : false;
  const onKey = (e: KeyboardEvent<HTMLElement>) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "SELECT" || tag === "INPUT" || e.altKey || e.ctrlKey || e.metaKey) return;
    const key = KEYBOARD[e.key];
    // Enter on a focused button presses that button; on the remote itself it is OK.
    if (!key || !has(key) || (e.key === "Enter" && e.target !== e.currentTarget)) return;
    e.preventDefault();
    press(key, BUTTON_NAMES[key]());
  };
  const key = (name: string, icon: IconName, className = "") => (
    <IconButton
      className={"tv-remote__key " + className}
      icon={icon}
      size="l"
      variant="secondary"
      data-lit={lit === name || undefined}
      label={BUTTON_NAMES[name]()}
      onClick={() => press(name, BUTTON_NAMES[name]())}
    />
  );
  const mute = can.mute && (
    <IconButton
      className="tv-remote__key is-mute"
      icon="volume-off"
      size="l"
      variant="secondary"
      pressed={!!state.muted}
      data-lit={lit === "VOLUME_MUTE" || undefined}
      label={BUTTON_NAMES.VOLUME_MUTE()}
      onClick={() => press("VOLUME_MUTE", BUTTON_NAMES.VOLUME_MUTE())}
    />
  );
  const play = can.playback && key("MEDIA_PLAY_PAUSE", "play", "is-play");
  const status =
    state.reachable === false
      ? t("Not reachable")
      : state.on === false
        ? tv.target === "tv"
          ? t("TV is off")
          : t("On standby")
        : state.title
          ? (state.playing === false ? t("Paused") : t("Playing")) + " · " + state.title
          : appName(state.app) || (state.on ? t("On") : "");
  const quiet = state.reachable === false || state.on === false;
  const pairingOffer = can.remote_pairable && !can.paired && (
    <>
      <Text style="body-s" tone="muted">
        {covered
          ? t("The TV remote already steers what is on screen.")
          : t("Arrows, OK and back on this Chromecast need a one-time pairing: it shows a code.")}
      </Text>
      <div>
        <Button
          variant={covered ? "secondary" : "primary"}
          size={covered ? "s" : "m"}
          onClick={() => setPairing(true)}
        >
          {covered ? t("Pair the Chromecast's own arrows (optional)") : t("Set up the remote")}
        </Button>
      </div>
    </>
  );
  return (
    <article
      className="tv-remote"
      data-quiet={quiet || undefined}
      tabIndex={0}
      aria-label={t("Remote for") + " " + tv.name}
      aria-describedby={can.dpad ? "tv-hint-" + tv.id : undefined}
      onKeyDown={onKey}
    >
      <div className="tv-remote__main">
        <header className="tv-remote__head">
          <div className="tv-remote__who">
            <Text as="h2" style="title-m">
              <Icon name={tv.target === "tv" ? "tv" : "cast"} size="s" /> {tv.name}
            </Text>
            {status && (
              <Status tone={state.reachable === false ? "danger" : quiet ? "neutral" : "success"}>
                {status}
              </Status>
            )}
          </div>
          {can.power && key("POWER", "power", "tv-remote__power")}
        </header>
        {can.input && (
          <Field label={t("Input")}>
            <Select
              value={picked || state.input || ""}
              onChange={(e) => {
                setPicked(e.target.value);
                press("INPUT", e.target.value, e.target.value);
              }}
            >
              {!(picked || state.input) && <option value="">{t("Choose an input")}</option>}
              {(tv.inputs || []).map((name: string) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </div>
      {can.dpad && (
        <div className="tv-remote__pad" role="group" aria-label={t("Arrows and OK")}>
          {key("BACK", "undo", "is-back")}
          {key("DPAD_UP", "chevron-up", "is-up")}
          {key("HOME", "home", "is-home")}
          {key("DPAD_LEFT", "chevron-left", "is-left")}
          <Button
            variant="primary"
            className="tv-remote__key is-ok"
            data-lit={lit === "DPAD_CENTER" || undefined}
            aria-label={BUTTON_NAMES.DPAD_CENTER()}
            onClick={() => press("DPAD_CENTER", BUTTON_NAMES.DPAD_CENTER())}
          >
            {t("OK")}
          </Button>
          {key("DPAD_RIGHT", "chevron-right", "is-right")}
          {mute}
          {key("DPAD_DOWN", "chevron-down", "is-down")}
          {play}
        </div>
      )}
      <div className="tv-remote__rest">
        {can.volume_level && (
          <div className="tv-remote__volume">
            <Slider
              label={t("Volume")}
              value={typeof state.volume === "number" ? state.volume : 0}
              onCommit={setVolume}
            />
            <b className="tabular">{typeof state.volume === "number" ? state.volume : ""}</b>
          </div>
        )}
        {((can.volume && !can.volume_level) || (!can.dpad && (mute || play))) && (
          <div className="tv-remote__row">
            {can.volume && !can.volume_level && (
              <div className="tv-remote__rocker" role="group" aria-label={t("Volume")}>
                {key("VOLUME_DOWN", "minus")}
                <span className="tv-remote__level" aria-hidden="true">
                  <Icon name="volume" size="s" />
                  {typeof state.volume === "number" && <b className="tabular">{state.volume}</b>}
                </span>
                {key("VOLUME_UP", "add")}
              </div>
            )}
            {!can.dpad && mute}
            {!can.dpad && play}
          </div>
        )}
        {!covered && pairingOffer}
        <Disclosure summary={t("About this remote")}>
          <Text style="caption" tone="muted">
            {tv.target === "tv"
              ? t("The TV itself, through Home Assistant: power, input, volume, its menus")
              : tv.adapter === "dlna"
                ? t("Smart TV (DLNA): volume only")
                : t("Only the Chromecast: its apps, volume and playback")}
          </Text>
          {tv.target === "tv" && (tv.inputs || []).length > 0 && (
            <Field
              label={t("Films switch to")}
              hint={t(
                "The input your Chromecast is plugged into: the TV turns on and goes there when a film starts.",
              )}
            >
              <Select
                value={tv.film_input ?? tv.film_input_now ?? ""}
                onChange={async (e) => {
                  try {
                    await api("/tv/" + tv.id + "/film-input", "PUT", { input: e.target.value });
                    await onChanged();
                  } catch (err) {
                    setError(sentence(err));
                  }
                }}
              >
                <option value="">{t("Don't switch the input")}</option>
                {(tv.inputs || []).map((name: string) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {covered && pairingOffer}
        </Disclosure>
        {can.dpad && (
          <p className="tv-remote__hint" id={"tv-hint-" + tv.id}>
            {t("Tap the remote, then use the arrows, Enter for OK and Backspace to go back.")}
          </p>
        )}
        <Problem error={error} />
      </div>
      <p className="visually-hidden" aria-live="polite">
        {said && t("Sent:") + " " + said}
      </p>
      {pairing && (
        <PairDialog tv={tv} onClose={() => setPairing(false)} onPaired={() => void onChanged()} />
      )}
    </article>
  );
}

const BUTTON_NAMES: Record<string, () => string> = {
  DPAD_UP: () => t("Up"),
  DPAD_DOWN: () => t("Down"),
  DPAD_LEFT: () => t("Left"),
  DPAD_RIGHT: () => t("Right"),
  DPAD_CENTER: () => t("OK"),
  BACK: () => t("Back"),
  HOME: () => t("Home"),
  VOLUME_UP: () => t("Volume up"),
  VOLUME_DOWN: () => t("Volume down"),
  VOLUME_MUTE: () => t("Mute"),
  MEDIA_PLAY_PAUSE: () => t("Play/pause"),
  POWER: () => t("Power"),
};

/** Pairing: the TV shows a code, the resident types it. Also used from Control Room → Devices. */
export function PairDialog({
  tv,
  onClose,
  onPaired,
}: {
  tv: Obj;
  onClose: () => void;
  onPaired?: () => void;
}) {
  const [step, setStep] = useState<"asking" | "code" | "done" | "failed">("asking"),
    [error, setError] = useState("");
  const start = async () => {
    setStep("asking");
    setError("");
    try {
      await api("/tv/" + tv.id + "/remote/pair", "POST");
      setStep("code");
    } catch (e) {
      setError(sentence(e));
      setStep("failed");
    }
  };
  useEffect(() => {
    void start();
  }, []);
  return (
    <Sheet title={t("Set up the remote")} onClose={onClose}>
      <div className="tv-pair">
        {step === "asking" && (
          <Status tone="info" busy>
            {t("Asking the TV for a code…")}
          </Status>
        )}
        {step === "failed" && (
          <>
            <Problem error={error} />
            <div>
              <Button icon="refresh" onClick={() => void start()}>
                {t("Try again")}
              </Button>
            </div>
          </>
        )}
        {step === "code" && (
          <>
            <Text>{t("Look at your TV: type the code it shows.")}</Text>
            <Form
              submit={t("Pair")}
              secondary={
                <Button variant="quiet" onClick={() => void start()}>
                  {t("Show a new code")}
                </Button>
              }
              onSubmit={async (f) => {
                try {
                  await api("/tv/" + tv.id + "/remote/pair/finish", "POST", {
                    code: String(f.get("code") || "").trim(),
                  });
                } catch (e) {
                  throw new Error(sentence(e));
                }
                setStep("done");
                onPaired?.();
              }}
            >
              <Field label={t("Code on the TV")}>
                <Input
                  name="code"
                  className="tv-pair__code tabular"
                  required
                  minLength={6}
                  maxLength={6}
                  pattern="[0-9A-Fa-f]{6}"
                  autoComplete="one-time-code"
                  autoCapitalize="characters"
                  spellCheck={false}
                  data-autofocus=""
                />
              </Field>
            </Form>
          </>
        )}
        {step === "done" && (
          <>
            <Text>
              {t("The remote is ready: arrows, OK, back and home now work on") +
                " " +
                tv.name +
                "."}
            </Text>
            <div>
              <Button variant="primary" onClick={onClose}>
                {t("Done")}
              </Button>
            </div>
          </>
        )}
      </div>
    </Sheet>
  );
}

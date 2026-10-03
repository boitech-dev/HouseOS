import { t, getLanguage } from "./i18n";
import { useState, useEffect } from "react";
import {
  api,
  clock,
  useData,
  bytes as sizeLabel,
  date,
  items,
  percent,
  pretty,
  time,
  type Obj,
} from "./api";
import { go } from "./nav";
import {
  Button,
  Checkbox,
  ConfirmSheet,
  Disclosure,
  Field,
  IconButton,
  Input,
  List,
  ListRow,
  Page,
  PageHeader,
  Problem,
  Progress,
  ReviewDetails,
  Select,
  Slider,
  Slot,
  State,
  Status,
  Text,
  type Tone,
  FileButton,
} from "./design";
import "./watch.css";

export function trackLanguage(code: string | undefined) {
  if (!code || code === "und") return t("Unknown language");
  try {
    return new Intl.DisplayNames([getLanguage()], { type: "language" }).of(code) || code;
  } catch {
    return code;
  }
}

/** A screen's state as a mark and a word. */
export function deviceTone(state: string): Tone {
  if (["playing", "playing_observed", "paused", "idle", "ready", "online"].includes(state))
    return "success";
  if (["unreachable", "offline", "failed", "error"].includes(state)) return "danger";
  if (["unknown", "unverified"].includes(state)) return "neutral";
  return "info";
}

/** The TV page (/tv): the house's screens, and a way to find something to watch. */
export function TV() {
  return (
    <Page>
      <PageHeader
        title={t("Screens")}
        room="watch"
        actions={
          <Button iconEnd="forward" onClick={() => go("/watch")}>
            {t("Find something to watch")}
          </Button>
        }
      />
      <Screens />
    </Page>
  );
}

/** Every screen a film can play on: its state, what it shows, and its own controls. */
export function Screens() {
  const { data, error, reload } = useData("/cinema/devices");
  const screens = items(data).filter((d) => d.adapter !== "dlna"); // music-only speakers and TVs
  return (
    <div className="watch-screens">
      <Slot id="watch.tv.bezel" className="watch-screens__art" />
      <Problem error={error} onRetry={reload} />
      {data && !screens.length && (
        <State kind="not-configured" title={t("A quiet screen.")}>
          {t("No playback destination configured.")}
        </State>
      )}
      {screens.map((d) => (
        <Destination key={d.id} device={d} reload={reload} />
      ))}
      <Button variant="quiet" size="s" icon="refresh" onClick={() => void reload()}>
        {t("Refresh TV state")}
      </Button>
    </div>
  );
}

export const downloadActive = (w: Obj) =>
  [
    "awaiting_playback_confirmation",
    "awaiting_preparation_confirmation",
    "preparing",
    "queued",
    "downloading",
  ].includes(w.state);

export function DownloadProgress({ workflow }: { workflow: Obj }) {
  const d =
      workflow.download ||
      (workflow.state === "completed"
        ? { phase: "completed", bytes: workflow.preview?.bytes, total: workflow.preview?.bytes }
        : {}),
    bytes = Math.max(0, Number(d.bytes) || 0),
    total = Math.max(0, Number(d.total) || 0);
  const done = total ? Math.min(100, Math.floor((bytes / total) * 100)) : 0;
  const phase =
    workflow.state === "cancelled"
      ? "cancelled"
      : workflow.state === "recovery_required"
        ? "failed"
        : workflow.state === "completed"
          ? "completed"
          : d.phase || workflow.state;
  return (
    <div className="watch-download" role="status" aria-live="polite">
      <Text>
        {t(
          (
            {
              awaiting_confirmation: "Ready to save: confirm this download",
              resolving: "Resolving your selected file",
              verifying: "Verifying the saved file",
              queued: "Waiting to download",
              downloading: "Downloading to your library",
              finalizing: "Finishing the saved file",
              completed: "Saved to your library",
              cancelled: "Download cancelled",
              failed: "Download failed",
            } as Record<string, string>
          )[phase] || pretty(phase),
        )}
      </Text>
      <Progress
        label={t("Download progress")}
        busy={!total && phase === "downloading"}
        value={total ? Math.min(bytes, total) / total : 0}
      />
      <Text style="caption" tone="muted">
        {sizeLabel(bytes)}
        {total
          ? " / " + sizeLabel(total) + " · " + percent(done)
          : " · " + t("Total size not yet known")}
        {d.updated_at &&
          " · " + t("Last update") + ": " + date(d.updated_at, { timeStyle: "medium" })}
      </Text>
    </div>
  );
}

export function SubtitlePicker({
  mediaId,
  workflow,
  sourceId,
  onWorkflow,
  season,
  episode,
}: {
  mediaId: string;
  workflow: Obj;
  sourceId?: string;
  onWorkflow: (w: Obj) => void;
  season?: number;
  episode?: number;
}) {
  const [language, setLanguage] = useState("fr"),
    [results, setResults] = useState<Obj[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Disclosure summary={t("Find an external subtitle")}>
      <Text style="body-s" tone="muted">
        {t(
          "Subtitles embedded in the selected release or supplied beside it work without an OpenSubtitles account. This optional fallback searches OpenSubtitles when the requested track is missing; its API requires an application key, and downloads use a provider quota.",
        )}
      </Text>
      <FileButton
        label={t("Upload SRT or WebVTT")}
        accept=".srt,.vtt,text/vtt,application/x-subrip"
        onFiles={async ([file]) => {
          if (file.size > 512000) {
            setError(t("Subtitle file must be under 500 KB"));
            return;
          }
          try {
            const text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
            onWorkflow(
              await api("/cinema/workflows/" + workflow.id + "/subtitles/upload", "POST", {
                version: workflow.version,
                source_id: sourceId,
                text,
                language,
                name: file.name.slice(0, 100),
              }),
            );
            setError("");
          } catch (error) {
            setError((error as Error).message);
          }
        }}
      />
      <form
        className="watch-inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const r = await api(
              "/cinema/titles/" +
                mediaId +
                "/subtitles?language=" +
                encodeURIComponent(language) +
                (season !== undefined ? "&season=" + season + "&episode=" + episode : ""),
            );
            setResults(items(r));
            setError("");
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Input
          aria-label={t("Subtitle language")}
          value={language}
          minLength={2}
          maxLength={3}
          onChange={(e) => setLanguage(e.target.value)}
        />
        <Button type="submit" icon="search" busy={busy}>
          {t("Search subtitles")}
        </Button>
      </form>
      {results.length > 0 && (
        <List label={t("Subtitles found")}>
          {results.map((r) => (
            <ListRow
              key={r.id}
              title={r.release || r.name || t("Subtitle")}
              detail={r.language + " · " + t("timing not verified")}
              onOpen={async () => {
                try {
                  onWorkflow(
                    await api("/cinema/workflows/" + workflow.id + "/subtitle", "POST", {
                      version: workflow.version,
                      source_id: sourceId,
                      subtitle_id: r.id,
                    }),
                  );
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            />
          ))}
        </List>
      )}
      <Problem error={error} />
    </Disclosure>
  );
}

function Destination({ device, reload }: { device: Obj; reload: () => Promise<void> }) {
  const current = useData("/cinema/devices/" + device.id + "/current");
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      setError("");
      await reload();
      await current.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="watch-screen" aria-label={device.name}>
      <div className="watch-screen__head">
        <Text as="h3" style="title-m">
          {device.name}
        </Text>
        <Status tone={deviceTone(device.state)}>{t(pretty(device.state || "unknown"))}</Status>
      </div>
      {current.data?.title && (
        <Text tone="muted">
          {current.data.title} · {t(pretty(current.data.state))}
        </Text>
      )}
      <div className="watch-screen__actions">
        <Button
          size="s"
          icon="plug"
          busy={busy}
          onClick={() => void act(() => api("/cinema/devices/" + device.id + "/inspect", "POST"))}
        >
          {t("Inspect connection")}
        </Button>
        {current.data?.workflow_id &&
          [true, false].map((participate) => (
            <Button
              key={String(participate)}
              size="s"
              variant="quiet"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await api(
                    "/cinema/workflows/" + current.data?.workflow_id + "/co-watch",
                    "POST",
                    { participate },
                  );
                  setNotice(
                    participate
                      ? "Your watch history will include this session."
                      : "This session will no longer update your watch history.",
                  );
                })
              }
            >
              {t(participate ? "Count this in my watch history" : "Stop counting my watch history")}
            </Button>
          ))}
      </div>
      <TVControls device={device} />
      {notice && <p role="status">{t(notice)}</p>}
      <Problem error={error || current.error} />
    </section>
  );
}

function TVControls({ device }: { device: Obj }) {
  const [open, setOpen] = useState(false),
    [action, setAction] = useState(""),
    [volume, setVolume] = useState<number | null>(null),
    [input, setInput] = useState(""),
    [preview, setPreview] = useState<Obj | null>(null),
    [result, setResult] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const observed = useData(open ? "/cinema/devices/" + device.id + "/tv" : null);
  const actions = [
    ["power_on", "Turn on", "power_on"],
    ["power_off", "Turn off", "power_off"],
    ["volume", "Set TV volume", "volume_absolute"],
    ["input", "Change input", "set_input"],
  ].filter(([, , cap]) => device.capabilities?.[cap] === true);
  const tv = observed.data;
  return (
    <Disclosure summary={t("TV power, input and volume")} onToggle={setOpen}>
      <Problem error={observed.error} onRetry={observed.reload} />
      {tv && (
        <form
          className="watch-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              setPreview(
                await api("/cinema/devices/" + device.id + "/tv-prepare", "POST", {
                  version: device.version,
                  action,
                  value:
                    action === "volume"
                      ? (volume ?? Math.round((tv.volume || 0) * 100))
                      : action === "input"
                        ? input || tv.input
                        : undefined,
                }),
              );
              setResult(null);
              setError("");
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Text tone="muted">
            {t("Observed TV state")}: {t(pretty(tv.state))} · {t("Input")}:{" "}
            {tv.input || t("Unknown")}
          </Text>
          <Field label={t("TV action")}>
            <Select value={action} onChange={(e) => setAction(e.target.value)} required>
              <option value="">{t("Choose a supported control")}</option>
              {actions.map(([value, label]) => (
                <option value={value} key={value}>
                  {t(label)}
                </option>
              ))}
            </Select>
          </Field>
          {action === "volume" && (
            <Slider
              showLabel
              label={t("TV volume percent")}
              min={0}
              max={75}
              value={volume ?? Math.round((tv.volume || 0) * 100)}
              onChange={setVolume}
              format={percent}
            />
          )}
          {action === "input" && (
            <Field label={t("TV input")}>
              <Select value={input || tv.input} onChange={(e) => setInput(e.target.value)}>
                {(tv.inputs || []).map((i: string) => (
                  <option key={i}>{i}</option>
                ))}
              </Select>
            </Field>
          )}
          <Text style="body-s" tone="muted">
            {t(
              "Display controls are separate from the selected movie and may interrupt another activity.",
            )}
          </Text>
          <div>
            <Button type="submit" busy={busy} disabled={!action}>
              {t("Review TV action")}
            </Button>
          </div>
        </form>
      )}
      <Problem error={error} />
      {result && (
        <>
          <ReviewDetails value={result} />
          <Problem error={result.error?.message || ""} />
        </>
      )}
      {preview && (
        <ConfirmSheet
          title={t("Review exact TV action")}
          confirm={t("Confirm TV action")}
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            setResult(
              await api("/cinema/device-confirmations/" + preview.confirmation_id, "POST", {}),
            );
            await observed.reload();
          }}
        >
          <ReviewDetails value={preview.preview} />
          <Text>{t("The current destination and activity must still match this preview.")}</Text>
        </ConfirmSheet>
      )}
    </Disclosure>
  );
}

export function useCinemaCurrent(enabled = true) {
  // Idle screens poll slowly: a film starting saves its workflow, which emits cinema.workflow.
  return useData(enabled ? "/cinema/current" : null, {
    interval: (d) => (d?.current ? 5000 : 20000),
  });
}

export function CinemaTransport({
  current,
  onChanged,
}: {
  current: Obj;
  onChanged: (result?: Obj) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [now, setNow] = useState(Date.now());
  // The receiver reports every few seconds; between reports the bar moves on its own.
  useEffect(() => {
    const id = setInterval(() => !document.hidden && setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const checkpoint = current.checkpoint || {};
  const since = checkpoint.at
    ? Math.max(
        0,
        (now - Date.parse(checkpoint.at + (checkpoint.at.endsWith("Z") ? "" : "Z"))) / 1000,
      )
    : 0;
  const position = Math.min(
    current.duration || Infinity,
    (checkpoint.position || 0) + (current.state === "playing_observed" ? Math.min(since, 30) : 0),
  );
  const send = async (action: string, position?: number) => {
    setBusy(true);
    try {
      const result = await api("/cinema/workflows/" + current.id + "/control", "POST", {
        version: current.version,
        action,
        position,
      });
      setError(result.error?.message || "");
      onChanged(result);
    } catch (e) {
      setError((e as Error).message);
      onChanged({ error: { message: (e as Error).message } });
    } finally {
      setBusy(false);
    }
  };
  const paused = current.state === "paused";
  return (
    <div className="watch-transport">
      {current.duration > 0 && current.can_seek && (
        <Slider
          label={t("Movie position")}
          value={Math.round(position)}
          max={Math.floor(current.duration)}
          format={(v) => clock(v) + " / " + clock(current.duration)}
          onCommit={(value) => void send("seek", value)}
        />
      )}
      {current.duration > 0 && !current.can_seek && (
        <Progress label={t("Movie position")} value={position / current.duration} />
      )}
      <div className="watch-transport__keys">
        {current.can_seek && (
          <IconButton
            icon="replay"
            size="l"
            disabled={busy}
            label={t("Back 30 seconds")}
            onClick={() => void send("seek", Math.max(0, position - 30))}
          />
        )}
        <IconButton
          glyph={paused ? "transport.play" : "transport.pause"}
          size="l"
          variant="primary"
          disabled={busy}
          label={t(paused ? "Resume" : "Pause")}
          onClick={() => void send(paused ? "resume" : "pause")}
        />
        {current.can_seek && (
          <IconButton
            icon="redo"
            size="l"
            disabled={busy}
            label={t("Forward 30 seconds")}
            onClick={() => void send("seek", Math.min(current.duration || 86400, position + 30))}
          />
        )}
      </div>
      <CinemaStop current={current} onChanged={onChanged} />
      {current.volume_supported && (
        <Slider
          label={t("Movie volume")}
          value={current.volume ?? 30}
          max={75}
          format={(v) => String(v)}
          onCommit={(value) => void send("volume", value)}
        />
      )}
      <Problem error={error} />
    </div>
  );
}

/** Stop the film on the screen and end its session; the place is saved for Your picks. */
export function CinemaStop({
  current,
  onChanged,
}: {
  current: Obj;
  onChanged: (result?: Obj) => void;
}) {
  const [busy, setBusy] = useState(false);
  const stop = async () => {
    setBusy(true);
    try {
      onChanged(
        await api("/cinema/workflows/" + current.id + "/control", "POST", {
          version: current.version,
          action: "stop",
        }),
      );
    } catch (e) {
      onChanged({ error: { message: (e as Error).message } });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="watch-stop">
      <Button
        icon="stop"
        busy={busy}
        aria-label={t("Stop the film and save my place")}
        onClick={() => void stop()}
      >
        {t("Stop")}
      </Button>
      <Text style="caption" tone="muted">
        {t("your place is saved")}
      </Text>
    </div>
  );
}

export function CinemaSleep({
  workflow,
  onWorkflow,
}: {
  workflow: Obj;
  onWorkflow: (value: Obj) => void;
}) {
  const options = useData("/cinema/workflows/" + workflow.id + "/sleep");
  const [preset, setPreset] = useState("60"),
    [minutes, setMinutes] = useState(60),
    [powerOff, setPowerOff] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const change = async (value: number) => {
    setBusy(true);
    try {
      onWorkflow(
        await api("/cinema/workflows/" + workflow.id + "/sleep", "POST", {
          version: workflow.version,
          minutes: value,
          power_off: powerOff,
        }),
      );
      setError("");
      await options.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const timer = workflow.sleep_timer;
  return (
    <Disclosure summary={t("Movie sleep timer")}>
      <Text style="body-s" tone="muted">
        {t(
          "Pause only this movie after the chosen delay. A changed or unverified playback session is left untouched.",
        )}
      </Text>
      <div className="watch-inline-form">
        <Field label={t("Delay")}>
          <Select value={preset} onChange={(e) => setPreset(e.target.value)}>
            {[1, 2, 3, 4, 5].map((h) => (
              <option key={h} value={h * 60}>
                {h} h
              </option>
            ))}
            <option value="custom">{t("Custom")}</option>
          </Select>
        </Field>
        {preset === "custom" && (
          <Field label={t("Minutes")}>
            <Input
              type="number"
              min="1"
              max="1440"
              value={minutes}
              onChange={(e) => setMinutes(Number(e.target.value))}
            />
          </Field>
        )}
      </div>
      {options.data?.power_off_available ? (
        <Checkbox
          checked={powerOff}
          onChange={(e) => setPowerOff(e.target.checked)}
          label={t("Also power off this supported display")}
        />
      ) : (
        <Text style="body-s" tone="muted">
          {t("Display power-off is unavailable until a supported TV integration is connected.")}
        </Text>
      )}
      {timer && (
        <Status tone={timer.error ? "danger" : "info"}>
          {t(pretty(timer.state))} · {time(timer.at)}
          {timer.error && " · " + timer.error.message}
        </Status>
      )}
      <div className="watch-screen__actions">
        <Button
          busy={busy}
          disabled={
            preset === "custom" && (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440)
          }
          onClick={() => void change(preset === "custom" ? minutes : Number(preset))}
        >
          {t("Set sleep timer")}
        </Button>
        {timer?.state === "scheduled" && (
          <Button variant="quiet" disabled={busy} onClick={() => void change(0)}>
            {t("Cancel timer")}
          </Button>
        )}
      </div>
      <Problem error={error || options.error} />
    </Disclosure>
  );
}

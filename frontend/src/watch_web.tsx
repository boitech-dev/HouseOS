// Watch → Web (D32): paste or share a video link, pick a screen, it plays. The house downloads it
// first (the best version up to 1080p, no ads), plays it like a film, and deletes it 6 h later.
import { t } from "./i18n";
import { useEffect, useState } from "react";
import { api, clock, date, items, percent, useData, type Obj } from "./api";
import {
  Button,
  Field,
  IconButton,
  Input,
  List,
  ListRow,
  Media,
  Notice,
  Problem,
  Progress,
  Select,
  State,
  Status,
  Text,
  toast,
} from "./design";
import { message } from "./messages";

const WORKING = ["queued", "reading", "downloading"];
const ON_SCREEN = ["command_sent", "playing_observed", "paused", "buffering"];

export function WebPlace({ initial = "" }: { initial?: string }) {
  const devices = useData("/cinema/devices"),
    preferences = useData("/cinema/preferences");
  // Faster while something is getting ready, so its progress moves.
  const list = useData("/cinema/web", {
    interval: (data) => (items(data).some((v) => WORKING.includes(v.state)) ? 1500 : 15000),
  });
  const screens = items(devices.data).filter((d) => d.adapter !== "dlna"); // DLNA: speakers
  const [deviceId, setDeviceId] = useState(""),
    [text, setText] = useState(initial),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (deviceId || !screens.length || !preferences.data) return;
    const preferred = screens.find((d) => d.id === preferences.data!.preferred_device);
    setDeviceId((preferred || screens.find((d) => d.adapter === "cast") || screens[0]).id);
  }, [screens.length, preferences.data]);
  const screenName = (id?: string) => screens.find((d) => d.id === id)?.name || t("the TV");
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await list.reload();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const play = (video: Obj, replace = false) =>
    act(() => api("/cinema/web/" + video.id + "/play", "POST", { device_id: deviceId, replace }));
  const videos = items(list.data);
  return (
    <div className="watch-web">
      <form
        className="watch-web__add"
        onSubmit={(e) => {
          e.preventDefault();
          void act(() =>
            api("/cinema/web", "POST", { text: text.trim(), device_id: deviceId }),
          ).then((ok) => {
            if (!ok) return;
            setText("");
            toast(t("Getting it ready for {screen}…").replace("{screen}", screenName(deviceId)));
          });
        }}
      >
        <Field
          label={t("A video link")}
          hint={t(
            "YouTube, TikTok, Instagram, Reddit, Dailymotion, a .mp4 link and many more. No ads: it starts in a few seconds while the house downloads it, and it's deleted 6 h after you watch it.",
          )}
        >
          <Input
            value={text}
            inputMode="url"
            autoComplete="off"
            placeholder={t("Paste a link")}
            onChange={(e) => setText(e.target.value)}
          />
        </Field>
        <div className="watch-web__go">
          {screens.length > 1 && (
            <Select
              aria-label={t("Screen")}
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
            >
              {screens.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          )}
          <Button
            type="submit"
            variant="primary"
            icon="play"
            busy={busy}
            disabled={!text.trim() || !deviceId}
          >
            {screens.length === 1
              ? t("Play on {screen}").replace("{screen}", screens[0].name)
              : t("Play")}
          </Button>
        </div>
      </form>
      {devices.data && !screens.length && (
        <Notice tone="info">{t("No screen yet: add the TV in Watch → Sources → Screens.")}</Notice>
      )}
      <Problem error={error || list.error} onRetry={error ? undefined : list.reload} />
      {list.data && !videos.length ? (
        <State kind="empty" title={t("Paste a video link to watch it on the TV")}>
          {t("On a phone: Share → HouseOS, then Play on the TV.")}
        </State>
      ) : (
        <List>
          {videos.map((video) => (
            <WebRow
              key={video.id}
              video={video}
              screen={screenName(video.device_id)}
              busy={busy}
              onPlay={(replace) => void play(video, replace)}
              onRemove={() =>
                void act(() => api("/cinema/web/" + video.id, "DELETE")).then(
                  (ok) => ok && toast(t("Removed.")),
                )
              }
            />
          ))}
        </List>
      )}
    </div>
  );
}

function WebRow({
  video,
  screen,
  busy,
  onPlay,
  onRemove,
}: {
  video: Obj;
  screen: string;
  busy: boolean;
  onPlay: (replace: boolean) => void;
  onRemove: () => void;
}) {
  const working = WORKING.includes(video.state);
  // On the TV: once ready, or already while the rest downloads (it plays from the first pieces).
  const showing =
    ["ready", "downloading"].includes(video.state) && ON_SCREEN.includes(video.workflow_state);
  // When the house deletes it: stated wherever it's being downloaded or kept.
  const until = video.delete_at
    ? date(video.delete_at, {
        weekday:
          new Date(video.delete_at).toDateString() === new Date().toDateString()
            ? undefined
            : "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  const title = video.title || new URL(video.url).hostname;
  // States go under the title, full width: beside it they squeeze it on a phone.
  const note =
    video.state === "queued"
      ? t("Waiting for the video before it")
      : video.state === "reading"
        ? t("Reading the link…")
        : showing
          ? t("On {screen}").replace("{screen}", screen)
          : "";
  return (
    <ListRow
      leading={
        <span className="watch-web__thumb">
          <Media src={video.poster} alt="" ratio="16 / 9" />
        </span>
      }
      title={title}
      detail={
        <span className="watch-web__detail">
          {[
            video.site,
            video.duration ? clock(video.duration) : "",
            video.height ? video.height + "p" : "",
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      }
      actions={
        <>
          {!working && (
            <IconButton
              icon="play"
              size="s"
              disabled={busy}
              label={t("Play again") + " · " + title}
              onClick={() => onPlay(false)}
            />
          )}
          {!showing && (
            <IconButton
              icon="close"
              size="s"
              disabled={busy}
              label={t("Remove") + " · " + title}
              onClick={onRemove}
            />
          )}
        </>
      }
    >
      {video.state === "downloading" && (
        <>
          <Progress
            value={video.progress ?? 0}
            busy={video.progress == null}
            label={t("Downloading…")}
          />
          <Text style="caption" tone="muted">
            {(showing ? t("Playing while it downloads") : t("Downloading…")) +
              (video.progress != null ? " " + percent(video.progress * 100) : "") +
              " · " +
              t("deleted from the house 6 h after you watch it")}
          </Text>
        </>
      )}
      {note && (
        <Status tone={showing ? "success" : "info"} busy={!showing}>
          {note}
        </Status>
      )}
      {video.state === "failed" && (
        <Status tone="danger">{message(video.error || "SOURCE_UNAVAILABLE")}</Status>
      )}
      {video.needs_replace && (
        <Notice
          tone="warning"
          action={
            <Button size="s" variant="primary" disabled={busy} onClick={() => onPlay(true)}>
              {t("Replace it")}
            </Button>
          }
        >
          {t("Something else is on {screen}.").replace("{screen}", screen)}
        </Notice>
      )}
      {video.state !== "downloading" && video.kept && (
        <Text style="caption" tone="muted">
          {until
            ? t("Kept until {time}, then deleted from the house.").replace("{time}", until)
            : t("Deleted from the house 6 h after you watch it.")}
        </Text>
      )}
      {video.state === "ready" && !video.kept && !showing && (
        <Text style="caption" tone="muted">
          {t("Deleted from the house after watching: Play again downloads it again.")}
        </Text>
      )}
    </ListRow>
  );
}

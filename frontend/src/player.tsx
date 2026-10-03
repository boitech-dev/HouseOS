import { t } from "./i18n";
import { api, type Obj } from "./api";
import { Button, toast } from "./design";

const PHONE = /Android|iPhone|iPad/.test(navigator.userAgent);

/** A film in another app (VLC, or any player that opens a web address): players send no sign-in,
 *  so the house makes a private link for this sign-in, good for 12 hours. The player streams it:
 *  nothing is copied to the device. Used for films kept at home (Files) and picked in Watch. */
export function OpenInPlayer({
  path,
  title,
  body = {},
}: {
  path: string;
  title: string;
  body?: Obj;
}) {
  const link = async () => location.origin + (await api(path, "POST", body)).url;
  const phone = async () => {
    const url = await link();
    // Android opens VLC by its package (the store when it isn't installed); iPhone by its scheme.
    location.href = navigator.userAgent.includes("Android")
      ? `intent:${url.replace(/^https?:/, "")}#Intent;scheme=${location.protocol.slice(0, -1)};package=org.videolan.vlc;type=video/*;end`
      : "vlc://" + url;
  };
  // A computer opens a one-line playlist with its video player (VLC, mpv…), which streams it.
  const computer = async () => {
    const list = `#EXTM3U\n#EXTINF:-1,${title.replace(/[\r\n]/g, " ")}\n${await link()}\n`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([list], { type: "audio/x-mpegurl" }));
    a.download = title.replace(/[\\/:*?"<>|]/g, "") + ".m3u";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  const copy = async () => {
    await navigator.clipboard.writeText(await link());
    toast(t("Link copied: paste it in your player (it works for 12 hours)."));
  };
  const run = (fn: () => Promise<void>) =>
    void fn().catch((e) => toast(e.message, { tone: "danger" }));
  return (
    <>
      {PHONE ? (
        <Button icon="play" onClick={() => run(phone)}>
          {t("Open in VLC")}
        </Button>
      ) : (
        <Button icon="play" onClick={() => run(computer)}>
          {t("Stream in VLC or another player")}
        </Button>
      )}
      <Button variant="quiet" icon="link" onClick={() => run(copy)}>
        {t("Copy a link for a player")}
      </Button>
    </>
  );
}

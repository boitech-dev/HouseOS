// Party mode: a tablet on the shelf runs the fair queue full screen, with a join code per guest.
import { t } from "./i18n";
import { useEffect, useState } from "react";
import { useUser } from "./api";
import { Button, IconButton, PageHeader, Sheet, Slider } from "./design";
import { go } from "./nav";
import { JoinCode } from "./guest_code";
import { AddBar, Deck, Queue, useMusicPlayback, useWakeLock } from "./music";
import "./party.css";

export function Party() {
  const music = useMusicPlayback();
  const user = useUser();
  const canInvite = user?.role === "admin" || !!user?.permissions?.includes("invites.create");
  const canControl = user?.role === "admin" || !!user?.permissions?.includes("music.control");
  const [sheet, setSheet] = useState<"" | "join" | "volume">("");
  // The shelf tablet stays lit while the party page is open.
  useWakeLock(true);
  // Full screen when the device allows it; leaving the page leaves it.
  useEffect(() => {
    return () => {
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    };
  }, []);
  return (
    <div className="party-room">
      <PageHeader
        room="party"
        title={t("Party")}
        actions={
          <>
            {canInvite && (
              <Button variant="primary" icon="party" onClick={() => setSheet("join")}>
                {t("Show a join code")}
              </Button>
            )}
            {/* On a phone the volume waits behind a button (party.css), the queue comes first. */}
            {canControl && (
              <IconButton
                className="party-volume"
                icon="volume"
                label={t("Volume")}
                variant="secondary"
                onClick={() => setSheet("volume")}
              />
            )}
            {document.fullscreenEnabled && (
              <Button
                variant="quiet"
                className="party-fullscreen"
                onClick={() =>
                  document.fullscreenElement
                    ? void document.exitFullscreen()
                    : void document.documentElement.requestFullscreen().catch(() => {})
                }
              >
                {t("Full screen")}
              </Button>
            )}
            <Button icon="back" className="party-leave" onClick={() => go("/listen")}>
              {t("Leave party mode")}
            </Button>
          </>
        }
      />
      <div className="party-stage">
        <Deck music={music} compact />
        <AddBar music={music} />
        <Queue music={music} />
      </div>
      {sheet === "join" && (
        <Sheet title={t("Let guests add songs")} place="center" onClose={() => setSheet("")}>
          <JoinCode />
        </Sheet>
      )}
      {sheet === "volume" && (
        <Sheet title={t("Volume")} place="bottom" onClose={() => setSheet("")}>
          <Slider
            label={t("Volume")}
            value={music.data?.volume ?? 60}
            onCommit={(value) => void music.control("volume", value)}
          />
        </Sheet>
      )}
    </div>
  );
}

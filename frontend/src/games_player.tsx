// A game in this browser (D33): EmulatorJS, fetched from the house the first time a console needs
// it (/emulator/…), the game file from the house, and your saves kept by the house, not the
// browser: the in-game save syncs every 30 s and on leaving, so it continues on any screen.
import { t } from "./i18n";
import { useEffect, useRef, useState } from "react";
import { api, useData } from "./api";
import { Button, IconButton, Problem, Spinner, Text, toHex, toast } from "./design";
import { when } from "./games";
import "./games.css";

const EMULATOR = "/emulator/4.2.3/";
type Anything = any;

const upload = (path: string, body: Blob | Uint8Array, method = "PUT") =>
  api(path, method, body).catch(() => {
    throw new Error(t("The save didn't reach the house."));
  });

export function GamePlayer({ id }: { id: string }) {
  const game = useData("/games/" + id);
  const tv = useData("/games/tv");
  const [saved, setSaved] = useState(0),
    [error, setError] = useState(""),
    [started, setStarted] = useState(false);
  const booted = useRef(false);
  const g = game.data;
  const ready = !!g;
  const leave = () => {
    // The emulator can't be taken apart in place: flush the save, then load the next page afresh.
    try {
      (window as Anything).EJS_emulator?.gameManager?.saveSaveFiles();
    } catch {
      /* not started */
    }
    setTimeout(() => (location.href = "/games?game=" + id), 300);
  };
  useEffect(() => {
    if (!g || booted.current) return;
    booted.current = true;
    if (!g.player?.core || !g.player?.file) {
      setError(t("This game doesn't play in a browser."));
      return;
    }
    const w = window as Anything;
    const state = new URLSearchParams(location.search).get("state");
    let last = "";
    let minute = 0;
    const sram = fetch("/api/v1/games/" + id + "/save", { credentials: "same-origin" }).then((r) =>
      r.status === 200 ? r.arrayBuffer() : null,
    );
    const keep = async (bytes: Uint8Array | null) => {
      if (!bytes?.length) return;
      const print = bytes.length + ":" + bytes.reduce((sum, b, i) => (sum + b * (i + 1)) % 1e9, 0);
      if (print === last) return; // unchanged since the last sync
      last = print;
      await upload("/games/" + id + "/save", bytes.slice());
      setSaved(Date.now() / 1000);
    };
    Object.assign(w, {
      EJS_player: "#games-stage",
      EJS_core: g.player.core,
      EJS_gameUrl: g.player.file,
      EJS_gameName: g.title,
      EJS_biosUrl: g.player.bios || "",
      EJS_pathtodata: EMULATOR,
      EJS_color: toHex(
        getComputedStyle(document.documentElement).getPropertyValue("--c-room").trim(),
      ),
      // Straight in after "Play here"; opened from a link or a reload, the browser wants a tap
      // first (sound), so the emulator shows its Start button.
      EJS_startOnLoaded: !!navigator.userActivation?.hasBeenActive,
      EJS_disableDatabases: true,
      EJS_disableAutoLang: false, // (its own meaning: false = no language file to fetch; English)
      EJS_defaultOptions: { "save-save-interval": "30" },
      EJS_loadStateURL: state ? "/api/v1/games/" + id + "/states/" + state : undefined,
      EJS_ready: () => w.EJS_emulator.on("saveSaveFiles", (bytes: Uint8Array) => void keep(bytes)),
      EJS_onGameStart: async () => {
        setStarted(true);
        minute = window.setInterval(() => {
          if (!document.hidden) void api("/games/" + id + "/played", "POST", { seconds: 60 });
        }, 60000);
        void api("/games/" + id + "/played", "POST", { seconds: 0, started: true });
        const bytes = await sram;
        if (!bytes) return;
        const manager = w.EJS_emulator.gameManager;
        const path: string = manager.getSaveFilePath();
        let folder = "";
        for (const part of path.split("/").slice(0, -1).filter(Boolean)) {
          folder += "/" + part;
          if (!manager.FS.analyzePath(folder).exists) manager.FS.mkdir(folder);
        }
        if (manager.FS.analyzePath(path).exists) manager.FS.unlink(path);
        manager.FS.writeFile(path, new Uint8Array(bytes));
        manager.loadSaveFiles();
      },
      EJS_onSaveState: async ({ state: bytes, screenshot }: Anything) => {
        try {
          const made = await upload("/games/" + id + "/states?surface=browser", bytes, "POST");
          if (screenshot)
            await upload("/games/" + id + "/states/" + made.name + "/shot", screenshot);
          setSaved(Date.now() / 1000);
          toast(t("Saved to the house."));
        } catch (e) {
          toast((e as Error).message);
        }
      },
      EJS_onLoadState: async () => {
        const list = await api("/games/" + id + "/states");
        const newest = (list.states || []).find((s: Anything) => s.surface === "browser");
        if (!newest) return toast(t("No snapshot yet: save one first."));
        const bytes = await fetch("/api/v1/games/" + id + "/states/" + newest.name).then((r) =>
          r.arrayBuffer(),
        );
        w.EJS_emulator.gameManager.loadState(new Uint8Array(bytes));
      },
      EJS_onSaveSave: async ({ save }: Anything) => {
        last = "";
        await keep(save);
        toast(t("Saved to the house."));
      },
    });
    const script = document.createElement("script");
    script.src = EMULATOR + "loader.js";
    script.onerror = () => setError(t("The emulator didn't load. Try again in a moment."));
    document.body.appendChild(script);
    // Time played: from the start, a minute at a time, only while the tab is seen.
    const hidden = () => {
      if (document.visibilityState === "hidden") w.EJS_emulator?.gameManager?.saveSaveFiles();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      clearInterval(minute);
      document.removeEventListener("visibilitychange", hidden);
      // Left by the browser's Back: the emulator is still in this page, so load the new one afresh.
      try {
        w.EJS_emulator?.gameManager?.saveSaveFiles();
      } catch {
        /* not started */
      }
      setTimeout(() => location.replace(location.href), 300);
    };
  }, [ready]); // once: the emulator boots a single time per page
  const playTv = () =>
    void api("/games/tv/play", "POST", { game_id: id })
      .then(() => {
        toast(t("Open Moonlight on the TV, then HouseOS."));
        leave();
      })
      .catch((e) => setError(e.message));
  return (
    <div className="games-player">
      <div className="games-player__bar">
        <IconButton icon="back" label={t("Back to Games")} onClick={leave} />
        <Text as="h1" style="title-s" className="games-player__title">
          {g?.title || t("Game")}
        </Text>
        <span className="games-player__saved" role="status">
          <Text style="caption" tone="muted">
            {saved
              ? t("Saved · {when}").replace("{when}", when(saved))
              : started
                ? t("Your save follows you")
                : ""}
          </Text>
        </span>
        {tv.data?.ready && g?.tv && (
          <Button size="s" variant="quiet" icon="tv" onClick={playTv}>
            {t("On the TV instead")}
          </Button>
        )}
      </div>
      <Problem error={error || game.error} />
      <div className="games-player__stage">
        {!started && !error && (
          <div className="games-player__loading">
            <Spinner />
            <Text tone="muted">
              {t("Getting the game ready… the first time, its emulator downloads too.")}
            </Text>
          </div>
        )}
        <div id="games-stage" />
      </div>
    </div>
  );
}

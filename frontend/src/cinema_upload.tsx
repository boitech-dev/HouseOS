import { useEffect, useRef, useState } from "react";
import { api, bytes, type Obj } from "./api";
import { t } from "./i18n";
import { transferFile } from "./file_transfer";
import { Button, FileButton, Problem, Progress, Text } from "./design";
import { localStore } from "./local";

export function CinemaUpload({ actorId, onAdded }: { actorId?: string; onAdded: () => void }) {
  const [progress, setProgress] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [stored, setStored] = useState<Obj | null>(null),
    [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const pendingKey = "cinema-library-import:" + actorId;
  useEffect(() => {
    let active = true;
    setStored(null);
    if (actorId)
      void localStore("get", pendingKey).then((value) => {
        if (active && value) setStored(value);
      });
    return () => {
      active = false;
    };
  }, [actorId, pendingKey]);
  const add = async (file: Obj) => {
    setBusy(true);
    setError("");
    setProgress((p) => ({ ...p, status: "indexing" }));
    try {
      await api("/cinema/library/import", "POST", { file_id: file.id, version: file.version });
      await localStore("delete", pendingKey);
      setStored(null);
      setProgress((p) => ({ ...p, status: "ready" }));
      onAdded();
    } catch (e) {
      setError((e as Error).message);
      setProgress((p) => ({ ...p, status: "import_failed" }));
    } finally {
      setBusy(false);
    }
  };
  const upload = async (file: File) => {
    if (!actorId) return;
    setBusy(true);
    setStored(null);
    setError("");
    controller.current = new AbortController();
    try {
      const entry = await transferFile(file, {
        actorId,
        scope: "media",
        signal: controller.current.signal,
        onProgress: setProgress,
      });
      await localStore("set", pendingKey, entry);
      setStored(entry);
      await add(entry);
    } catch (e) {
      setError((e as Error).message);
      setProgress((p) => ({
        ...p,
        status: controller.current?.signal.aborted ? "cancelled" : "interrupted",
      }));
    } finally {
      controller.current = null;
      setBusy(false);
    }
  };
  const cancelable = busy && ["preparing", "uploading"].includes(progress?.status);
  return (
    <section className="cinema-upload watch-stack" aria-label={t("Upload a movie")}>
      <FileButton
        label={t("Upload a movie")}
        accept="video/*,.mkv,.mp4,.m4v,.avi,.mov,.webm"
        disabled={busy || !actorId || !!stored}
        onFiles={([file]) => void upload(file)}
      />
      <Text style="body-s" tone="muted">
        {t(
          "Choose a video to keep in the house library. Keep this page open while it uploads; reselect the same file to resume an interrupted upload.",
        )}
      </Text>
      {progress && (
        <div className="watch-download" role="status">
          <Text style="title-s">{progress.name}</Text>
          <Text>
            {t(
              (
                {
                  preparing: "Preparing upload…",
                  uploading: "Uploading movie…",
                  "server finalizing": "Finishing upload…",
                  stored: "Upload stored",
                  indexing: "Adding to the local library…",
                  ready: "Saved locally. The library will show it after indexing.",
                  cancelled: "Upload cancelled.",
                  interrupted: "Upload interrupted. Reselect the same file to resume.",
                  import_failed: "Upload is saved. Retry adding it to the library.",
                } as Record<string, string>
              )[progress.status] || progress.status,
            )}
          </Text>
          <Progress
            label={t("Upload progress")}
            value={(progress.offset || 0) / (progress.size || 1)}
          />
          <Text style="caption" tone="muted">
            {bytes(progress.offset || 0)} / {bytes(progress.size || 0)}
          </Text>
          {cancelable && (
            <div>
              <Button size="s" variant="quiet" onClick={() => controller.current?.abort()}>
                {t("Cancel upload")}
              </Button>
            </div>
          )}
        </div>
      )}
      <Problem error={error} />
      {stored && !busy && (
        <div>
          <Button icon="refresh" onClick={() => void add(stored)}>
            {t("Retry adding to library")}
          </Button>
        </div>
      )}
    </section>
  );
}

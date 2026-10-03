import { useState } from "react";
import { api, useData, items, invalidate } from "./api";
import { t } from "./i18n";
import { Button, List, ListRow, Problem, State, Text, toast } from "./design";

export function ShareWatchlist({ titleId }: { titleId: string }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function change(method: string) {
    setBusy(true);
    try {
      await api("/cinema/shared-watchlist/" + titleId, method);
      toast(
        t(
          method === "PUT"
            ? "Title shared with the house. Your watch history stays private."
            : "Your sharing was removed. Your personal watchlist is unchanged.",
        ),
      );
      setError("");
      invalidate("cinema.watchlist_shared");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="watch-stack">
      <Text style="body-s" tone="muted">
        {t("Optional: share this title with the house. Progress and history remain private.")}
      </Text>
      <div className="watch-screen__actions">
        <Button size="s" icon="people" disabled={busy} onClick={() => void change("PUT")}>
          {t("Share with house")}
        </Button>
        <Button size="s" variant="quiet" disabled={busy} onClick={() => void change("DELETE")}>
          {t("Stop sharing")}
        </Button>
      </div>
      <Problem error={error} />
    </div>
  );
}

export function SharedWatchlist({ onOpen }: { onOpen: (mediaId: string) => void }) {
  const [offset, setOffset] = useState(0);
  const state = useData("/cinema/shared-watchlist?offset=" + offset);
  const rows = items(state.data);
  return (
    <div className="watch-stack">
      <Text style="body-s" tone="muted">
        {t("Titles residents explicitly shared. Personal lists and viewing history stay private.")}
      </Text>
      <Problem error={state.error} onRetry={state.reload} />
      {state.loading && !state.data && <State kind="loading" />}
      {state.data && !rows.length && (
        <State kind="empty" title={t("No shared titles on this page.")} />
      )}
      {rows.length > 0 && (
        <List label={t("House watchlist")}>
          {rows.map((row) => (
            <ListRow
              key={row.id}
              title={row.media.title + (row.media.year ? " · " + row.media.year : "")}
              detail={t("Shared by") + " " + row.shared_by.name}
              onOpen={() => onOpen(row.media.id)}
            >
              {row.mine && <ShareWatchlist titleId={row.media.id} />}
            </ListRow>
          ))}
        </List>
      )}
      <div className="watch-screen__actions">
        {offset > 0 && (
          <Button variant="quiet" onClick={() => setOffset(Math.max(0, offset - 100))}>
            {t("Previous")}
          </Button>
        )}
        {state.data?.next_offset != null && (
          <Button variant="quiet" onClick={() => setOffset(state.data!.next_offset)}>
            {t("Next")}
          </Button>
        )}
      </div>
    </div>
  );
}

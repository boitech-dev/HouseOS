import { useState } from "react";
import { plural, t } from "./i18n";
import { api, useData, type Obj } from "./api";
import { Button, Checkbox, Chip, ChipGroup, Problem, Sheet, Stack, Text, toast } from "./design";

/** A song's genre, tappable (residents): "+ Genre" when the house has none for it. */
export function GenreButton({ song, onChanged }: { song: Obj; onChanged: () => unknown }) {
  const [open, setOpen] = useState(false);
  const known = song.genre && song.genre !== "other";
  return (
    <>
      <Chip kind="filter" selected={!!known} onToggle={() => setOpen(true)}>
        {known ? t(song.genre) : "+ " + t("Genre")}
      </Chip>
      {open && <GenreSheet songs={[song]} onClose={() => setOpen(false)} onDone={onChanged} />}
    </>
  );
}

/** File songs under a genre by hand, and if asked every other song by their artist too. */
export function GenreSheet({
  songs,
  onClose,
  onDone,
}: {
  songs: Obj[];
  onClose: () => void;
  onDone: () => unknown;
}) {
  const one = songs.length === 1 ? songs[0] : null;
  const options = useData(
    "/music/genre" + (one ? "?source_url=" + encodeURIComponent(one.source_url) : ""),
  );
  const [chosen, setChosen] = useState<string>(one && one.genre !== "other" ? one.genre : "");
  const [all, setAll] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const others: number = options.data?.same_artist || 0;
  const save = async (genre: string) => {
    setBusy(true);
    setError("");
    try {
      const done = await api("/music/genre", "PUT", {
        source_urls: songs.map((s) => s.source_url),
        genre,
        same_artist: all,
      });
      toast(
        (genre ? t("Filed under {genre}.") : t("The house decides again.")).replace(
          "{genre}",
          t(genre),
        ) + (done.songs > 1 ? " · " + t("{n} songs").replace("{n}", String(done.songs)) : ""),
      );
      await onDone();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      title={
        one ? one.title || t("Genre") : t("Genre of {n} songs").replace("{n}", String(songs.length))
      }
      onClose={onClose}
      footer={
        <Button
          variant="primary"
          wide
          busy={busy}
          disabled={!chosen}
          onClick={() => void save(chosen)}
        >
          {t("Save")}
        </Button>
      }
    >
      <Stack>
        <Problem error={error || options.error} />
        <ChipGroup label={t("Genre")}>
          {(options.data?.choices || []).map((g: string) => (
            <Chip key={g} kind="filter" selected={chosen === g} onToggle={() => setChosen(g)}>
              {t(g)}
            </Chip>
          ))}
        </ChipGroup>
        {(others > 0 || !one) && (
          <Checkbox
            label={
              one
                ? plural(
                    others,
                    "Also the other song by this artist",
                    "Also the {n} other songs by this artist",
                  )
                : t("Also every other song by their artists")
            }
            checked={all}
            onChange={(e) => setAll(e.target.checked)}
          />
        )}
        <Text style="body-s" tone="muted">
          {t("Unsorted songs by the same artist follow your choice on their own.")}
        </Text>
        <Button variant="quiet" disabled={busy} onClick={() => void save("")}>
          {t("Let the house decide")}
        </Button>
      </Stack>
    </Sheet>
  );
}

import { go } from "./nav";
import { useState } from "react";
import { api, useData, items, bytes, type Obj } from "./api";
import {
  Button,
  ConfirmSheet,
  List,
  ListRow,
  Problem,
  Progress,
  Section,
  Select,
  Text,
  Tile,
  type IconName,
} from "./design";
import { t } from "./i18n";
import "./house_settings.css";
import "./me.css";
const TOP = 8;
const taken = (row: Obj) => row.used_bytes + row.reserved_bytes;

// What each kind of kept thing is called, and its icon.
const KINDS: Record<string, [string, IconName]> = {
  songs: ["Songs", "music"],
  films: ["Films", "film"],
  games: ["Games", "gamepad"],
  personal: ["People's files", "folder"],
  shared: ["Shared files", "people"],
  uploads: ["Music & film uploads", "upload"],
  trash: ["In the trash", "trash"],
};

/** Control Room → Storage: what the house keeps, counted by kind; the files themselves only
 * when you open a kind to browse it. */
export function StorageUsage() {
  const summary = useData("/admin/storage/summary");
  const [browse, setBrowse] = useState("");
  return (
    <>
      <Section title={t("What the house keeps")}>
        <Problem error={summary.error} onRetry={summary.reload} />
        {summary.data && (
          <>
            <Progress
              label={t("Storage drive")}
              value={summary.data.disk.used_bytes / (summary.data.disk.total_bytes || 1)}
            />
            <Text style="body-s" tone="muted">
              {t("{free} free of {total}")
                .replace("{free}", bytes(summary.data.disk.free_bytes))
                .replace("{total}", bytes(summary.data.disk.total_bytes))}
            </Text>
            <div className="control-tiles">
              {(summary.data.kinds as Obj[]).map((k) => (
                <Tile
                  key={k.key}
                  icon={KINDS[k.key]?.[1] || "storage"}
                  title={t(KINDS[k.key]?.[0] || k.key)}
                  value={bytes(k.bytes)}
                  detail={t("{n} items").replace("{n}", String(k.count))}
                  onOpen={
                    !k.count
                      ? undefined
                      : k.browse === "games"
                        ? () => go("/games")
                        : () => setBrowse(k.browse)
                  }
                />
              ))}
            </div>
          </>
        )}
      </Section>
      <PeopleSpace />
      {browse ? (
        <FilesBrowser initial={browse} onClose={() => setBrowse("")} />
      ) : (
        <div>
          <Button icon="folder" onClick={() => setBrowse("all")}>
            {t("Browse every file")}
          </Button>
        </div>
      )}
    </>
  );
}

/** Space per person, largest first. */
function PeopleSpace() {
  const data = useData("/admin/storage?kind=personal");
  const [allPeople, setAllPeople] = useState(false);
  // Largest first; the people who keep nothing wait behind "Show all".
  const people: Obj[] = [...(data.data?.people || [])].sort((a, b) => taken(b) - taken(a));
  const using = people.filter((p) => taken(p) > 0);
  const shown = allPeople ? people : using.slice(0, TOP);
  const meter = (label: string, row: Obj) => (
    <ListRow
      title={label}
      detail={
        <>
          {bytes(row.used_bytes)} {t("used ·")} {bytes(row.reserved_bytes)} {t("reserved ·")}{" "}
          {bytes(row.quota_bytes)} {t("limit")}
        </>
      }
    >
      <Progress
        label={label}
        value={(row.used_bytes + row.reserved_bytes) / (row.quota_bytes || 1)}
      />
    </ListRow>
  );
  return (
    <Section title={t("Space per person")}>
      <Problem error={data.error} onRetry={data.reload} />
      {data.data && (
        <>
          <List>{meter(t("Shared music & movies"), data.data.media)}</List>
          {shown.length > 0 ? (
            <div className="me-table storage-admin-people">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("Person")}</th>
                    <th scope="col">{t("Used")}</th>
                    <th scope="col">
                      <span className="visually-hidden">{t("Share of the limit")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((p) => (
                    <tr key={p.id}>
                      <th scope="row">{p.name}</th>
                      <td className="tabular">
                        {t("{used} of {limit}")
                          .replace("{used}", bytes(taken(p)))
                          .replace("{limit}", bytes(p.quota_bytes))}
                      </td>
                      <td>
                        <Progress label={p.name} value={taken(p) / (p.quota_bytes || 1)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Text tone="muted">{t("Nobody keeps files here yet.")}</Text>
          )}
          {people.length > using.slice(0, TOP).length && (
            <div>
              <Button size="s" variant="quiet" onClick={() => setAllPeople(!allPeople)}>
                {allPeople
                  ? t("Show fewer")
                  : t("Show all {n}").replace("{n}", String(people.length))}
              </Button>
            </div>
          )}
          <Text as="p" style="body-s" tone="muted">
            {t(
              "Drive usage includes other apps. Trash still uses space until permanently deleted. Downloaded music stays on the storage drive.",
            )}{" "}
            {t("House files live here:")} <code>{data.data.root}</code>
          </Text>
        </>
      )}
    </Section>
  );
}

/** Every file of a kind, largest first, to move to the trash, restore or delete. */
function FilesBrowser({ initial, onClose }: { initial: string; onClose: () => void }) {
  const [offset, setOffset] = useState(0),
    [owner, setOwner] = useState(""),
    [kind, setKind] = useState(initial),
    [review, setReview] = useState<Obj | null>(null);
  const data = useData(
    `/admin/storage?offset=${offset}&owner=${encodeURIComponent(owner)}&kind=${kind}`,
  );
  return (
    <Section
      title={t("Files")}
      actions={
        <Button size="s" variant="quiet" icon="close" onClick={onClose}>
          {t("Close")}
        </Button>
      }
    >
      <Problem error={data.error} onRetry={data.reload} />
      <div className="storage-admin-bar">
        <Select
          aria-label={t("Storage owner")}
          value={owner}
          onChange={(e) => {
            setOwner(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">{t("All users")}</option>
          {data.data?.people.map((p: Obj) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("Storage category")}
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setOffset(0);
          }}
        >
          <option value="all">{t("All files")}</option>
          <option value="personal">{t("Personal files")}</option>
          <option value="media">{t("Music & movies")}</option>
        </Select>
      </div>
      <List>
        {[...items(data.data), ...(data.data?.movies || []), ...(data.data?.music || [])].map(
          (r: Obj) => (
            <ListRow
              key={r.kind + r.id}
              title={r.name}
              detail={
                <>
                  {bytes(r.size)} · {data.data?.people.find((p: Obj) => p.id === r.owner_id)?.name}{" "}
                  · {r.scope} {r.trashed && t("· In Trash")}
                </>
              }
              actions={
                <>
                  <Button
                    size="s"
                    variant={r.kind !== "file" || r.trashed ? "danger" : "quiet"}
                    icon="trash"
                    onClick={() =>
                      setReview({
                        ...r,
                        action: r.kind !== "file" || r.trashed ? "delete" : "trash",
                      })
                    }
                  >
                    {t(r.kind !== "file" || r.trashed ? "Delete permanently" : "Move to Trash")}
                  </Button>
                  {r.trashed && (
                    <Button
                      size="s"
                      variant="quiet"
                      icon="undo"
                      onClick={() => setReview({ ...r, action: "restore" })}
                    >
                      {t("Restore")}
                    </Button>
                  )}
                </>
              }
            >
              <code className="storage-admin-path">{r.path}</code>
            </ListRow>
          ),
        )}
      </List>
      {review && (
        <ConfirmSheet
          title={t(
            review.action === "delete"
              ? "Delete permanently?"
              : review.action === "restore"
                ? "Restore this file?"
                : "Move this file to Trash?",
          )}
          confirm={t("Confirm")}
          danger={review.action === "delete"}
          onClose={() => setReview(null)}
          onConfirm={async () => {
            await api(`/admin/storage/${review.id}/reclaim`, "POST", {
              kind: review.kind,
              version: review.version,
              action: review.action,
              confirmed: true,
            });
            await data.reload();
          }}
        >
          <Text as="p">
            {review.name} · {bytes(review.size)}
          </Text>
          <Text as="p" style="body-s" tone="muted">
            {t(
              review.action === "delete"
                ? "This removes the local file from disk. It cannot be undone."
                : "The file remains on disk and can be restored.",
            )}
          </Text>
        </ConfirmSheet>
      )}
      <div className="storage-admin-bar">
        <Button
          variant="quiet"
          icon="chevron-left"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          {t("Previous")}
        </Button>
        <Button
          variant="quiet"
          iconEnd="chevron-right"
          disabled={data.data?.next_offset == null}
          onClick={() => setOffset(data.data!.next_offset)}
        >
          {t("Next")}
        </Button>
      </div>
    </Section>
  );
}

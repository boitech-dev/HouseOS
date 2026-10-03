import { transferFile, cancelUpload } from "./file_transfer";
import { StorageUsage } from "./storage_admin";
import { t } from "./i18n";
import { useTip } from "./tips";
import { useState, useRef, useEffect, type ReactNode } from "react";
import {
  api,
  useData,
  usePages,
  useUser,
  items,
  bytes,
  clock,
  date,
  percent,
  time,
  idempotency,
  type Obj,
} from "./api";
import { go } from "./nav";
import { ShareButtons } from "./custom_integrations";
import { claimIncomingShare, localStore } from "./local";
import { PeopleFilter, SortGenres } from "./music";
import { OpenInPlayer } from "./player";
import {
  Badge,
  Button,
  Checkbox,
  Chip,
  ChipGroup,
  ConfirmSheet,
  Disclosure,
  Field,
  Form,
  Hint,
  Icon,
  IconButton,
  type IconName,
  Input,
  LinkButton,
  List,
  ListRow,
  Media,
  MediaCard,
  MoreBelow,
  Notice,
  Page,
  PageHeader,
  Problem,
  Progress,
  ReviewDetails,
  SearchInput,
  Section,
  Segmented,
  Select,
  Sheet,
  State,
  Status,
  SubNav,
  Surface,
  Text,
  Textarea,
  toast,
  Toolbar,
  FileButton,
} from "./design";
import "./files.css";

type Scope = "personal" | "house" | "shared" | "music" | "movies" | "media" | "trash";
const SCOPES: [Scope, string, IconName, string][] = [
  ["personal", "My files", "lock", "Only you"],
  ["house", "House", "home", "Everyone at home"],
  ["shared", "Shared with me", "people", "From housemates"],
  ["music", "House music", "music-alt", "Every song kept"],
  ["movies", "Films & series", "film", "Films, series & anime at home"],
  ["media", "House media", "storage", "Imported media"],
  ["trash", "Trash", "trash", "Deleted, for 30 days"],
];
const STATUS: Record<string, "info" | "success" | "warning" | "danger"> = {
  uploading: "info",
  preparing: "info",
  stored: "success",
  interrupted: "warning",
  failed: "danger",
};

export function Files() {
  const [marked, setMarked] = useState<string[]>([]);
  // Checkboxes only while choosing several files: a phone's row keeps its width for the name.
  const [selecting, setSelecting] = useState(false);
  const [layout, setLayout] = useState<"list" | "grid">("list");
  const [scope, setScope] = useState<Scope>(() => {
      const asked = new URLSearchParams(location.search).get("scope") || "";
      return (
        ["personal", "house", "shared", "music", "movies"].includes(asked) ? asked : "personal"
      ) as Scope;
    }),
    [parent, setParent] = useState<Obj[]>([]),
    [q, setQ] = useState(""),
    [selected, setSelected] = useState<Obj | null>(null),
    [folder, setFolder] = useState(false),
    [error, setError] = useState(""),
    [upload, setUpload] = useState<Obj | null>(null),
    [preview, setPreview] = useState<Obj | null>(null),
    [owner, setOwner] = useState(""),
    [temporary, setTemporary] = useState(false);
  const [offset, setOffset] = useState(0);
  const tip = useTip("files");
  const library = scope === "music" || scope === "movies";
  const shared = ["house", "drop", "media"].includes(scope);
  const [shareHours, setShareHours] = useState("24");
  useEffect(() => {
    const identity = new URLSearchParams(location.search).get("file");
    if (identity)
      api("/files/" + encodeURIComponent(identity) + "/info")
        .then(setSelected)
        .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setOffset(0);
    setMarked([]);
  }, [scope, q, parent.map((p) => p.id).join(":")]);
  useEffect(() => setSelecting(false), [scope]);
  const input = useRef<HTMLInputElement>(null);
  const cancel = useRef(false);
  const pendingUpload = useRef<Obj | null>(null);
  const user = useUser();
  const mayChange = (r: Obj) =>
    r.owner_id === user?.id || (user?.role === "admin" && r.scope !== "personal");
  const canEdit = !!selected && mayChange(selected);
  const grants = useData(
    selected && canEdit && !selected.is_folder && !selected.trashed_at
      ? "/files/" + selected.id + "/grants"
      : null,
  );
  const path = library
    ? null
    : "/files?scope=" +
      scope +
      "&q=" +
      encodeURIComponent(q) +
      "&offset=" +
      offset +
      "&limit=100" +
      (parent.length ? "&parent_id=" + parent[parent.length - 1]?.id : "") +
      (shared && owner ? "&owner=" + owner : "");
  // "Temporary" house files (the drop area, gone after a week) show with the house's own.
  const drops = useData(
    scope === "house" && !parent.length
      ? "/files?scope=drop&limit=100&q=" + encodeURIComponent(q) + (owner ? "&owner=" + owner : "")
      : null,
  );
  const { data: listed, error: loadError, reload: reloadListed } = useData(path),
    data = drops.data ? { items: [...items(listed), ...items(drops.data)] } : listed,
    reload = async () => {
      await Promise.all([reloadListed(), drops.reload()]);
    },
    quota = useData(library ? null : "/files/quota?scope=" + scope),
    people = useData("/people");
  const rows = items(data);
  const transfer = async (file: File) => {
    setError("");
    cancel.current = false;
    try {
      if (!user?.id) throw new Error(t("Wait for your session to load, then retry."));
      await transferFile(file, {
        actorId: user.id,
        scope: scope === "house" && temporary ? "drop" : scope,
        parentId: parent[parent.length - 1]?.id,
        cancelled: () => cancel.current,
        onReservation: (r) => {
          pendingUpload.current = r;
        },
        onProgress: setUpload,
      });
      pendingUpload.current = null;
      await reload();
      await quota.reload();
    } catch (e) {
      setError((e as Error).message);
      setUpload((u) => (u ? { ...u, status: "interrupted" } : null));
    }
  };
  const prepare = async (action: string, extra: Obj = {}) => {
    try {
      setPreview(
        await api("/files/" + selected!.id + "/actions/prepare", "POST", {
          version: selected!.version,
          action,
          ...extra,
        }),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const bulk = async (action: string) => {
    try {
      setPreview(
        await api("/files/bulk/prepare", "POST", {
          items: rows
            .filter((f) => marked.includes(f.id))
            .map((f) => ({ id: f.id, version: f.version })),
          action,
        }),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const ownerName = (r: Obj) =>
    items(people.data).find((p) => p.id === r.owner_id)?.name || t("Owner");
  const open = (r: Obj) => (r.is_folder ? setParent((p) => [...p, r]) : setSelected(r));
  const pick = (r: Obj) =>
    selecting &&
    mayChange(r) && (
      <Checkbox
        hideLabel
        label={t("Select") + " · " + r.name}
        checked={marked.includes(r.id)}
        onChange={(e) =>
          setMarked((old) => (e.target.checked ? [...old, r.id] : old.filter((id) => id !== r.id)))
        }
      />
    );
  const place = SCOPES.find(([id]) => id === scope)!;
  return (
    <Page>
      <PageHeader
        room="files"
        title={t("Files")}
        lead={tip}
        actions={
          <>
            <Button icon="folder-add" onClick={() => setFolder(true)}>
              {t("Folder")}
            </Button>
            <Button
              variant="primary"
              icon="upload"
              disabled={!user?.id}
              onClick={() => input.current?.click()}
            >
              {t("Upload")}
            </Button>
          </>
        }
        hint={
          <Hint id="files">
            {t(
              "Your files stay yours unless you share them. The house library keeps every song played here and the films saved for offline.",
            )}
          </Hint>
        }
      />
      <Input
        hidden
        disabled={!user?.id}
        ref={input}
        type="file"
        multiple
        onChange={async (e) => {
          for (const f of Array.from(e.target.files || [])) await transfer(f);
        }}
      />
      <SubNav
        label={t("Places")}
        value={scope}
        onChange={(value) => {
          setScope(value as Scope);
          setParent([]);
          setOwner("");
        }}
        items={SCOPES.filter(([id]) => id !== "media" || user?.role === "admin").map(
          ([id, label, icon]) => ({ id, label: t(label), icon }),
        )}
      />
      {library && <Text tone="muted">{t(place[3])}</Text>}
      {scope === "house" && (
        <Checkbox
          checked={temporary}
          onChange={(e) => setTemporary(e.target.checked)}
          label={t("Upload as temporary: removed by itself after 7 days")}
        />
      )}
      {library && <HouseLibrary kind={scope as "music" | "movies"} />}
      {!library && (
        <section className="files-place" aria-label={t(place[1])}>
          <Toolbar label={t("Files")}>
            {parent.length > 0 && (
              <IconButton
                icon="back"
                label={t("Back")}
                onClick={() => setParent((p) => p.slice(0, -1))}
              />
            )}
            <span className="files-heading">
              <Text style="title-s" className="files-path">
                {parent.map((x) => x.name).join(" / ") || t("All files")}
              </Text>
              <Text style="caption" tone="muted">
                {t(place[3])}
              </Text>
            </span>
            <SearchInput
              label={t("Search filenames")}
              placeholder={t("Search filenames…")}
              value={q}
              onChange={setQ}
            />
            <Button
              variant="quiet"
              icon="check"
              pressed={selecting}
              className="files-select"
              onClick={() => {
                setSelecting(!selecting);
                setMarked([]);
              }}
            >
              {t("Select")}
            </Button>
            <Segmented
              label={t("File layout")}
              value={layout}
              onChange={setLayout}
              options={[
                { value: "list", label: t("List view"), icon: "menu" },
                { value: "grid", label: t("Grid view"), icon: "image" },
              ]}
            />
          </Toolbar>
          {shared && <PeopleFilter value={owner} onChange={setOwner} label="Uploaded by" />}
          <Problem error={error || loadError} onRetry={reload} />
          {upload && (
            <Surface material="raised" className="files-upload" role="status">
              <div className="files-upload__head">
                <Text style="title-s">{upload.name}</Text>
                <Status tone={STATUS[upload.status] || "info"} busy={upload.status === "uploading"}>
                  {t(upload.status)}
                </Status>
              </div>
              <Progress label={t("Upload progress")} value={upload.offset / (upload.size || 1)} />
              <div className="files-upload__head">
                {upload.status === "stored" || upload.status === "failed" ? (
                  // Finished: nothing to keep open, nothing to cancel.
                  <>
                    <Text style="caption" tone="muted">
                      {bytes(upload.size)}
                      {upload.status === "stored" && " · " + t("Saved")}
                    </Text>
                    <Button size="s" variant="quiet" onClick={() => setUpload(null)}>
                      {t("Close")}
                    </Button>
                  </>
                ) : (
                  <>
                    <Text style="caption" tone="muted">
                      {bytes(upload.offset)} / {bytes(upload.size)}{" "}
                      {t("· Keep this page open until stored.")}
                    </Text>
                    <Button
                      size="s"
                      variant="quiet"
                      disabled={!["uploading", "interrupted"].includes(upload.status)}
                      onClick={async () => {
                        cancel.current = true;
                        const u = pendingUpload.current;
                        try {
                          if (u) await cancelUpload(u);
                          pendingUpload.current = null;
                          setUpload(null);
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      {t("Cancel upload")}
                    </Button>
                  </>
                )}
              </div>
            </Surface>
          )}
          {layout === "list" && rows.length > 0 && (
            <List label={t("Files")}>
              {rows.map((r) => (
                <ListRow
                  key={r.id}
                  control={pick(r)}
                  leading={<FileIcon entry={r} />}
                  title={r.name}
                  detail={[
                    kindOf(r),
                    ownerName(r),
                    date(r.created_at),
                    !r.is_folder && bytes(r.size),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                  meta={
                    r.expires_at && (
                      <Badge tone="warning">
                        {t("Temporary · until {date}").replace("{date}", date(r.expires_at))}
                      </Badge>
                    )
                  }
                  onOpen={() => open(r)}
                  actions={
                    <>
                      {!r.is_folder && (
                        <LinkButton
                          variant="quiet"
                          size="s"
                          icon="download"
                          label={t("Download") + " · " + r.name}
                          href={"/api/v1/files/" + r.id + "/download"}
                        />
                      )}
                      <IconButton
                        icon="more"
                        size="s"
                        label={t("File actions") + " · " + r.name}
                        onClick={() => setSelected(r)}
                      />
                    </>
                  }
                />
              ))}
            </List>
          )}
          {layout === "grid" && rows.length > 0 && (
            <ul className="files-grid" aria-label={t("Files")}>
              {rows.map((r) => (
                <li key={r.id} className="files-card">
                  <span className="files-card__pick">{pick(r)}</span>
                  <MediaCard
                    media={<FileIcon entry={r} large />}
                    title={r.name}
                    meta={r.is_folder ? t("Folder") : bytes(r.size)}
                    onOpen={() => open(r)}
                  />
                </li>
              ))}
            </ul>
          )}
          {data && !rows.length && (
            <State kind="empty" title={t("A place for the things worth keeping.")}>
              {scope === "personal"
                ? t("Only you can see your personal files.")
                : t("Nothing here yet.")}
            </State>
          )}
          {(offset > 0 || data?.next_offset != null) && (
            <nav className="files-pages" aria-label={t("Pages")}>
              <Button
                variant="quiet"
                icon="chevron-left"
                disabled={!offset}
                onClick={() => setOffset((o) => Math.max(0, o - 100))}
              >
                {t("Previous files")}
              </Button>
              <Text style="caption" tone="muted">
                {t("Page")} {Math.floor(offset / 100) + 1}
              </Text>
              <Button
                variant="quiet"
                iconEnd="chevron-right"
                disabled={data?.next_offset == null}
                onClick={() => setOffset(data!.next_offset)}
              >
                {t("Next files")}
              </Button>
            </nav>
          )}
          {marked.length > 0 && (
            <div className="files-selbar" role="region" aria-label={t("Selection")}>
              <Text style="title-s">
                {marked.length} {t("selected")}
              </Text>
              {scope === "trash" ? (
                <>
                  <Button size="s" icon="undo" onClick={() => void bulk("restore")}>
                    {t("Restore")}
                  </Button>
                  <Button size="s" variant="danger" icon="trash" onClick={() => void bulk("purge")}>
                    {t("Delete permanently…")}
                  </Button>
                </>
              ) : (
                <Button size="s" icon="trash" onClick={() => void bulk("trash")}>
                  {t("Move to trash")}
                </Button>
              )}
              <Button
                size="s"
                variant="quiet"
                onClick={() => {
                  setMarked([]);
                  setSelecting(false);
                }}
              >
                {t("Clear selection")}
              </Button>
            </div>
          )}
        </section>
      )}
      <ExistingRoots />
      {quota.data && (
        <Text style="body-s" tone="muted">
          {bytes(quota.data.used_bytes)} {t("used ·")} {bytes(quota.data.reserved_bytes)}{" "}
          {t("reserved ·")} {bytes(quota.data.quota_bytes)} {t("limit")}
        </Text>
      )}
      {folder && (
        <Sheet title={t("New folder")} onClose={() => setFolder(false)}>
          <Form
            submit={t("Create")}
            onSubmit={async (f) => {
              await api("/files/folders", "POST", {
                name: f.get("name"),
                scope,
                parent_id: parent[parent.length - 1]?.id || null,
                idempotency_key: idempotency(),
              });
              setFolder(false);
              await reload();
            }}
          >
            <Field label={t("Folder name")}>
              <Input name="name" required maxLength={200} data-autofocus="" />
            </Field>
          </Form>
        </Sheet>
      )}
      {selected && !preview && (
        <FileSheet
          file={selected}
          canEdit={canEdit}
          folders={rows.filter(
            (f) => f.is_folder && f.id !== selected.id && f.id !== selected.parent_id,
          )}
          people={items(people.data)}
          grants={grants}
          shareHours={shareHours}
          onShareHours={setShareHours}
          error={error}
          onPrepare={(action, extra) => void prepare(action, extra)}
          onSaved={async () => {
            setSelected(null);
            await reload();
          }}
          onError={setError}
          onClose={() => setSelected(null)}
        />
      )}
      {preview && (
        <ConfirmSheet
          title={t("Review file change")}
          confirm={t("Confirm this change")}
          danger={JSON.stringify(preview.preview || {}).includes("purge")}
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            await api("/files/confirmations/" + preview.confirmation_id, "POST");
            setSelected(null);
            setMarked([]);
            await reload();
          }}
        >
          <Text>{t("This changes access or storage for the selected file.")}</Text>
          <ReviewDetails value={preview.preview || {}} />
        </ConfirmSheet>
      )}
    </Page>
  );
}

/** One file: see it, download it, and (when it's yours) rename, move, share or remove it. */
function FileSheet({
  file,
  canEdit,
  folders,
  people,
  grants,
  shareHours,
  onShareHours,
  error,
  onPrepare,
  onSaved,
  onError,
  onClose,
}: {
  file: Obj;
  canEdit: boolean;
  folders: Obj[];
  people: Obj[];
  grants: { data?: Obj | null; error?: string };
  shareHours: string;
  onShareHours: (value: string) => void;
  error: string;
  onPrepare: (action: string, extra?: Obj) => void;
  onSaved: () => Promise<void>;
  onError: (message: string) => void;
  onClose: () => void;
}) {
  const url = "/api/v1/files/" + file.id;
  const image = file.mime?.startsWith("image/") && !file.mime.includes("svg");
  const audio = file.mime?.startsWith("audio/");
  const video = file.mime === "video/mp4";
  const pdf = file.mime === "application/pdf";
  const live = !file.is_folder && !file.trashed_at;
  return (
    <Sheet title={file.name} place="side" onClose={onClose}>
      <div className="files-stack">
        {live && (
          <>
            {image && <img className="files-preview" alt={file.name} src={url + "/preview"} />}
            {audio && <audio controls src={url + "/preview"} />}
            {video && <video className="files-preview" controls src={url + "/preview"} />}
            <div className="files-actions">
              <LinkButton variant="primary" icon="download" href={url + "/download"}>
                {t("Download file")}
              </LinkButton>
              {pdf && (
                <LinkButton
                  icon="file-text"
                  href={url + "/preview"}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("Preview PDF in browser")}
                </LinkButton>
              )}
            </div>
            {!image && !audio && !video && !pdf && (
              <Text style="body-s" tone="muted">
                {t("This format is download-only; no inline preview is available.")}
              </Text>
            )}
          </>
        )}
        {canEdit && (
          <>
            <Section title={t("Name and place")} level={3}>
              <Form
                onSubmit={async (f) => {
                  await api("/files/" + file.id, "PATCH", {
                    version: file.version,
                    name: f.get("name"),
                    parent_id: f.get("parent_id") || null,
                  });
                  await onSaved();
                }}
              >
                <Field label={t("Name")}>
                  <Input name="name" defaultValue={file.name} required />
                </Field>
                <Field label={t("Move within this area")}>
                  <Select name="parent_id" defaultValue={file.parent_id || ""}>
                    <option value="">{t("Area root")}</option>
                    {file.parent_id && (
                      <option value={file.parent_id}>{t("Current folder")}</option>
                    )}
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </Form>
            </Section>
            {!file.trashed_at && (
              <Section title={t("Share")} level={3}>
                <div className="files-stack">
                  <div className="files-form-row">
                    <Field label={t("Shared access expires")}>
                      <Select value={shareHours} onChange={(e) => onShareHours(e.target.value)}>
                        <option value="2">{t("In 2 hours")}</option>
                        <option value="24">{t("In 24 hours")}</option>
                        <option value="168">{t("In 7 days")}</option>
                        <option value="0">{t("No automatic expiry")}</option>
                      </Select>
                    </Field>
                    <Field label={t("Share with a resident")}>
                      <Select
                        defaultValue=""
                        onChange={(e) => {
                          if (e.target.value)
                            onPrepare("share", {
                              recipient_id: e.target.value,
                              grant_expires_at: Number(shareHours)
                                ? new Date(Date.now() + Number(shareHours) * 3600000).toISOString()
                                : null,
                            });
                        }}
                      >
                        <option value="">{t("Choose a person…")}</option>
                        {people.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  {items(grants.data).length > 0 && (
                    <List label={t("Shared with")}>
                      {items(grants.data).map((grant) => (
                        <ListRow
                          key={grant.user_id}
                          leading={<Icon name="person" size="s" />}
                          title={t("Shared with") + " " + grant.name}
                          detail={
                            grant.expired
                              ? t("Expired")
                              : grant.expires_at
                                ? t("Until {date}").replace("{date}", time(grant.expires_at))
                                : t("No automatic expiry")
                          }
                          actions={
                            <Button
                              size="s"
                              variant="quiet"
                              onClick={() => onPrepare("unshare", { recipient_id: grant.user_id })}
                            >
                              {t("Revoke access")}
                            </Button>
                          }
                        />
                      ))}
                    </List>
                  )}
                  {items(grants.data).some((g) => !g.expired) && (
                    <div>
                      <Button
                        size="s"
                        icon="link"
                        onClick={() =>
                          navigator.clipboard
                            .writeText(location.origin + "/files?file=" + file.id)
                            .then(() => toast(t("Link copied.")))
                            .catch(() =>
                              onError("Could not copy. Use the address shown in your browser."),
                            )
                        }
                      >
                        {t("Copy private file link")}
                      </Button>
                    </div>
                  )}
                  <Text style="body-s" tone="muted">
                    {t(
                      "This link requires an authorized resident login. Expiry/revocation removes that resident's grant; house-visible files remain visible to the house.",
                    )}
                  </Text>
                  <Problem error={grants.error} />
                  <Field label={t("Change visibility")}>
                    <Select
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) onPrepare("scope", { scope: e.target.value });
                      }}
                    >
                      <option value="">{t("Choose destination…")}</option>
                      <option value="personal">{t("My Files")}</option>
                      <option value="house">{t("House")}</option>
                      <option value="drop">{t("House, temporary (7 days)")}</option>
                    </Select>
                  </Field>
                </div>
              </Section>
            )}
            <div className="files-actions">
              {file.trashed_at ? (
                <>
                  <Button icon="undo" onClick={() => onPrepare("restore")}>
                    {t("Restore")}
                  </Button>
                  <Button variant="danger" icon="trash" onClick={() => onPrepare("purge")}>
                    {t("Delete permanently…")}
                  </Button>
                </>
              ) : (
                <Button icon="trash" onClick={() => onPrepare("trash")}>
                  {t("Move to trash")}
                </Button>
              )}
            </div>
          </>
        )}
        {!canEdit && (
          <Text style="body-s" tone="muted">
            {t("Shared for viewing and download. Only its owner can change this file.")}
          </Text>
        )}
        <Problem error={error} />
      </div>
    </Sheet>
  );
}

// ---------- Capture: send something home ----------
export function Capture({ offlineActor }: { offlineActor?: Obj } = {}) {
  const user = useUser();
  const actorId = offlineActor?.id || user?.id;
  const [localNotice, setLocalNotice] = useState("");
  const [localRevision, setLocalRevision] = useState(0);
  const shareId = new URLSearchParams(location.search).get("share");
  const [text, setText] = useState(
      new URLSearchParams(location.search).get("text") ||
        new URLSearchParams(location.search).get("url") ||
        "",
    ),
    [saved, setSaved] = useState(false);
  // Show on the TV: the computer plays a YouTube link full screen, and the TV shows the computer.
  const tvAllowed =
    user?.role === "admin" ||
    !!user?.permissions?.some((p: string) => p === "home.control" || p === "cinema.use");
  const screen = useData<Obj>(tvAllowed ? "/tv/screen" : null);
  const [shown, setShown] = useState(""),
    [showing, setShowing] = useState(false);
  return (
    <Page>
      <PageHeader
        title={t("Send something home.")}
        lead={t(
          "Installed HouseOS can receive shared files on supported browsers. Otherwise select files below or paste a link.",
        )}
      />
      {shareId && (
        <IncomingShare
          id={shareId}
          actorId={actorId}
          actorName={offlineActor?.name || user?.name}
          offline={!!offlineActor || !navigator.onLine}
          onClaim={(value) => {
            if (value) setText(value);
            history.replaceState({}, "", "/capture");
            setLocalRevision((v) => v + 1);
            setLocalNotice("Share accepted into your device drafts. Upload is a separate action.");
          }}
        />
      )}
      <div className="files-capture">
        <Section title={t("A note for home")}>
          <Form
            disabled={!!offlineActor || !navigator.onLine}
            submit={t("Save at home")}
            secondary={
              // Drafts stay on this device: small, on the left, apart from saving at home.
              <span className="files-drafts">
                <Button
                  size="s"
                  variant="quiet"
                  onClick={async () => {
                    if (!actorId) return;
                    await localStore("set", "capture:" + actorId, text);
                    await localStore("set", "has_drafts", true);
                    setLocalNotice(
                      "Saved on this device, not uploaded. Browser storage can be evicted.",
                    );
                  }}
                >
                  {t("Save device draft")}
                </Button>
                <Button
                  size="s"
                  variant="quiet"
                  onClick={async () => {
                    const v = await localStore("get", "capture:" + actorId);
                    if (v) setText(v);
                    setLocalNotice(
                      v
                        ? "Device draft restored. Review before saving to the server."
                        : "No draft for this account.",
                    );
                  }}
                >
                  {t("Restore draft")}
                </Button>
              </span>
            }
            onSubmit={async () => {
              await api("/household/captures", "POST", {
                data: { text, url: /^https?:\/\//.test(text) ? text : null },
                idempotency_key: idempotency(),
              });
              setSaved(true);
              await localStore("delete", "capture:" + actorId);
            }}
          >
            <Field
              label={t("A link, a thought, a little reminder")}
              hint={t("Saved privately. Pasting a link never starts playback.")}
            >
              <Textarea
                rows={6}
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setSaved(false);
                }}
                required
              />
            </Field>
            {localNotice && (
              <p role="status" className="files-note">
                {t(localNotice)}
              </p>
            )}
            {saved && <Notice tone="success">{t("Saved at home.")}</Notice>}
            {/* A shared video link: watched on the TV instead (Watch → Web). */}
            {user?.permissions?.includes("cinema.use") && /https?:\/\/|\w\.\w+\//.test(text) && (
              <Button
                icon="tv"
                onClick={() => go("/watch?kind=web&text=" + encodeURIComponent(text))}
              >
                {t("Play this video on the TV")}
              </Button>
            )}
            {screen.data?.ready && /youtu\.?be/i.test(text) && (
              <Button
                icon="tv"
                busy={showing}
                onClick={async () => {
                  setShowing(true);
                  setShown("");
                  try {
                    await api("/tv/screen/show", "POST", { url: text });
                    setShown("sent");
                  } catch (e) {
                    setShown((e as Error).message);
                  } finally {
                    setShowing(false);
                  }
                }}
              >
                {t("Show on the TV from the computer")}
              </Button>
            )}
            {shown === "sent" && <Notice tone="success">{t("On its way to the TV.")}</Notice>}
            {shown && shown !== "sent" && <Notice tone="warning">{shown}</Notice>}
            {/* Your own integrations' buttons for shared links (custom_integrations.tsx). */}
            {text && <ShareButtons text={text} />}
          </Form>
        </Section>
        <div className="files-stack">
          {actorId && (
            <DeviceOutbox key={localRevision} actorId={actorId} offline={!!offlineActor} />
          )}
          <nav aria-label={t("Other ways")}>
            <List label={t("Other ways")}>
              {(
                [
                  ["upload", "Upload a file", "/files"],
                  ["music", "Queue some music", "/listen"],
                  ["pin", "Leave a house note", "/house"],
                  ["send", "Send to a resident", "/inbox"],
                ] as const
              ).map(([icon, label, href]) => (
                <ListRow key={href} leading={<Icon name={icon} />} title={t(label)} href={href} />
              ))}
            </List>
          </nav>
        </div>
      </div>
    </Page>
  );
}

function ExistingRoots() {
  const roots = useData("/files/roots");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Obj | null>(null),
    [directory, setDirectory] = useState("");
  useEffect(() => setOffset(0), [selected?.id, directory]);
  const entries = useData(
    selected
      ? "/files/roots/" +
          selected.id +
          "/entries?offset=" +
          offset +
          (directory ? "&directory_id=" + encodeURIComponent(directory) : "")
      : null,
  );
  return (
    <Disclosure summary={t("Existing read-only libraries")}>
      <Text style="body-s" tone="muted">
        {t("Only the folders deliberately shared by an administrator appear here.")}
      </Text>
      <Problem error={roots.error || entries.error} />
      {items(roots.data).length > 0 && (
        <ChipGroup label={t("Libraries")}>
          {items(roots.data).map((r) => (
            <Chip
              key={r.id}
              kind="filter"
              icon="folder"
              selected={selected?.id === r.id}
              onToggle={() => {
                setSelected(r);
                setDirectory("");
              }}
            >
              {r.name}
            </Chip>
          ))}
        </ChipGroup>
      )}
      {selected && (
        <>
          <div>
            <Button
              size="s"
              variant="quiet"
              icon="up"
              onClick={() => setDirectory(entries.data?.parent_id || "")}
            >
              {t("Up one folder")}
            </Button>
          </div>
          <List label={selected.name}>
            {items(entries.data).map((r) =>
              r.is_folder ? (
                <ListRow
                  key={r.id}
                  leading={<Icon name="folder" />}
                  title={r.name}
                  onOpen={() => setDirectory(r.id)}
                />
              ) : (
                <ListRow
                  key={r.id}
                  leading={<Icon name="file" />}
                  title={r.name}
                  actions={
                    <LinkButton
                      size="s"
                      variant="quiet"
                      icon="download"
                      href={
                        "/api/v1/files/roots/" +
                        selected.id +
                        "/download?file_id=" +
                        encodeURIComponent(r.id)
                      }
                    >
                      {t("Download")}
                    </LinkButton>
                  }
                />
              ),
            )}
          </List>
          <nav className="files-pages" aria-label={t("Pages")}>
            <Button
              variant="quiet"
              icon="chevron-left"
              disabled={!offset}
              onClick={() => setOffset((o) => Math.max(0, o - 200))}
            >
              {t("Previous entries")}
            </Button>
            <Text style="caption" tone="muted">
              {t("Page")} {Math.floor(offset / 200) + 1}
            </Text>
            <Button
              variant="quiet"
              iconEnd="chevron-right"
              disabled={entries.data?.next_offset == null}
              onClick={() => setOffset(entries.data!.next_offset)}
            >
              {t("Next entries")}
            </Button>
          </nav>
        </>
      )}
      {roots.data && !items(roots.data).length && (
        <Text tone="muted">{t("No existing folders have been shared.")}</Text>
      )}
    </Disclosure>
  );
}

// ---------- Control Room → Storage ----------
export function StorageAdmin() {
  const policy = useData("/files/admin/policy"),
    roots = useData("/files/roots"),
    people = useData("/people");
  const [preview, setPreview] = useState<Obj | null>(null),
    [revoking, setRevoking] = useState<Obj | null>(null);
  return (
    <>
      <StorageUsage />
      <UploadBackupPolicy />
      <Section title={t("Storage retention")} lead={t("Deletion is always explicit.")}>
        <Problem error={policy.error} onRetry={policy.reload} />
        {policy.data && (
          <Form
            onSubmit={async (f) => {
              await api("/files/admin/policy", "PUT", {
                permanent_delete_enabled: f.get("enabled") === "on",
                trash_retention_days: Number(f.get("days")),
              });
              await policy.reload();
              toast(t("Saved."));
            }}
          >
            <Checkbox
              name="enabled"
              defaultChecked={policy.data.permanent_delete_enabled}
              label={t("Enable irreversible scheduled trash cleanup")}
            />
            <Field label={t("Days to keep trash")}>
              <Input
                name="days"
                type="number"
                min="30"
                max="365"
                defaultValue={policy.data.trash_retention_days || 30}
              />
            </Field>
          </Form>
        )}
      </Section>
      <Section title={t("Share an existing read-only folder")}>
        <Form
          submit={t("Review")}
          onSubmit={async (f) => {
            setPreview(
              await api("/files/roots/prepare", "POST", {
                name: f.get("name"),
                path: f.get("path"),
                reader_ids: f.getAll("reader_ids"),
              }),
            );
          }}
        >
          <Field label={t("Display name")}>
            <Input name="name" required />
          </Field>
          <Field
            label={t("Folder inside the import root")}
            hint={t(
              "In Docker, choose a folder under /import: it is the folder set as HOUSEOS_IMPORT_DIR in .env (./import by default), and may be another disk or a NAS share.",
            )}
          >
            <Input name="path" required placeholder={t("/import/films")} />
          </Field>
          <fieldset className="files-people">
            <legend>{t("Allowed residents (none selected means all with file access)")}</legend>
            {items(people.data).map((p) => (
              <Checkbox key={p.id} name="reader_ids" value={p.id} label={p.name} />
            ))}
          </fieldset>
        </Form>
        <Problem error={roots.error} onRetry={roots.reload} />
        {items(roots.data).length > 0 && (
          <List label={t("Shared folders")}>
            {items(roots.data).map((r) => (
              <ListRow
                key={r.id}
                leading={<Icon name="folder" />}
                title={r.name}
                actions={
                  <Button size="s" variant="quiet" onClick={() => setRevoking(r)}>
                    {t("Revoke access")}
                  </Button>
                }
              />
            ))}
          </List>
        )}
      </Section>
      {preview && (
        <ConfirmSheet
          title={t("Review this read-only access grant")}
          confirm={t("Confirm folder access")}
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            await api("/files/roots/confirm/" + preview.confirmation_id, "POST");
            await roots.reload();
          }}
        >
          <ReviewDetails value={preview.preview || {}} />
        </ConfirmSheet>
      )}
      {revoking && (
        <ConfirmSheet
          title={t("Revoke this shared folder? Existing files will remain untouched.")}
          confirm={t("Revoke access")}
          danger
          onClose={() => setRevoking(null)}
          onConfirm={async () => {
            await api("/files/roots/" + revoking.id + "?version=" + revoking.version, "DELETE");
            await roots.reload();
          }}
        >
          <Text>{revoking.name}</Text>
        </ConfirmSheet>
      )}
    </>
  );
}

function DeviceOutbox({ actorId, offline }: { actorId: string; offline: boolean }) {
  const [rows, setRows] = useState<Obj[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [discarding, setDiscarding] = useState<Obj | null>(null);
  const prefix = "outbox:" + actorId + ":";
  const reload = async () => setRows(await localStore("list", prefix));
  useEffect(() => {
    void reload().catch((e) => setError(e.message));
  }, [actorId]);
  const add = async (files: File[] | FileList | null) => {
    if (!files) return;
    setError("");
    try {
      let total = rows.reduce((s, r) => s + r.file.size, 0);
      for (const file of Array.from(files)) {
        total += file.size;
        if (total > 100 * 1024 * 1024)
          throw new Error(
            t(
              "The device outbox is limited to 100 MB per account. Upload larger files directly when online.",
            ),
          );
        const id = idempotency();
        await localStore("set", prefix + id, { id, file, name: file.name });
        await localStore("set", "has_drafts", true);
      }
      setNotice("Saved on this device only. Browser storage may be evicted.");
      await reload();
    } catch (e) {
      setError((e as Error).message);
      await reload();
    }
  };
  const sync = async (row: Obj) => {
    setBusy(true);
    setError("");
    try {
      const me = await api("/auth/me");
      if (me.user.id !== actorId)
        throw new Error(t("Sign in to the account that owns this device draft."));
      // The draft id is the reservation's idempotency key, so a retry after an
      // interrupted finalize finds the stored upload instead of duplicating it.
      await transferFile(row.file, {
        actorId,
        scope: "personal",
        idempotencyKey: row.id,
        onProgress: (p) => {
          if (p.status === "uploading")
            setNotice(
              t("Uploading") +
                " " +
                row.name +
                ": " +
                percent((p.offset / (row.file.size || 1)) * 100),
            );
        },
      });
      await localStore("delete", prefix + row.id);
      setNotice(row.name + " is stored at home.");
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section title={t("Device file outbox")}>
      <Text style="body-s" tone="muted">
        {t(
          "Private to this account on this browser. Up to 100 MB; keep the page open during upload. These files are not backed up until stored at home.",
        )}
      </Text>
      <FileButton
        label={t("Keep files on this device")}
        multiple
        disabled={busy}
        onFiles={(files) => void add(files)}
      />
      <div>
        <Button
          size="s"
          variant="quiet"
          disabled={busy}
          onClick={async () => {
            const granted = await navigator.storage?.persist?.();
            setNotice(
              granted
                ? "Browser granted persistent device storage."
                : "Persistent storage was not granted. Keep another copy until upload completes.",
            );
          }}
        >
          {t("Request persistent device storage")}
        </Button>
      </div>
      {rows.length > 0 && (
        <List label={t("Device file outbox")}>
          {rows.map((r) => (
            <ListRow
              key={r.id}
              leading={<Icon name="file" />}
              title={r.name}
              detail={bytes(r.file.size) + " " + t("· Device-local")}
              actions={
                <>
                  <Button
                    size="s"
                    icon="upload"
                    disabled={busy || offline || !navigator.onLine}
                    onClick={() => void sync(r)}
                  >
                    {t("Upload to My Files")}
                  </Button>
                  <Button size="s" variant="quiet" disabled={busy} onClick={() => setDiscarding(r)}>
                    {t("Discard")}
                  </Button>
                </>
              }
            />
          ))}
        </List>
      )}
      {notice && (
        <p className="files-note" role="status">
          {t(notice)}
        </p>
      )}
      <Problem error={error} />
      {discarding && (
        <ConfirmSheet
          title={t("Delete the device-only copy of {name}?").replace("{name}", discarding.name)}
          confirm={t("Discard")}
          danger
          onClose={() => setDiscarding(null)}
          onConfirm={async () => {
            await localStore("delete", prefix + discarding.id);
            await reload();
          }}
        >
          <Text>{t("It was never uploaded; nothing else keeps it.")}</Text>
        </ConfirmSheet>
      )}
    </Section>
  );
}

function UploadBackupPolicy() {
  const policy = useData("/admin/backups/policy");
  const [preview, setPreview] = useState<Obj | null>(null);
  return (
    <Section title={t("Upload backups")} lead={t("Exactly which files are covered.")}>
      <Problem error={policy.error} onRetry={policy.reload} />
      {policy.data && (
        <>
          <Text>
            {bytes(policy.data.selected_bytes)} {t("currently selected ·")} {policy.data.schedule}
          </Text>
          <Text style="body-s" tone="muted">
            {policy.data.destination}. {policy.data.retention}
            {t(". Films saved from Watch are excluded.")}
          </Text>
          <Form
            submit={t("Review backup policy")}
            onSubmit={async (f) =>
              setPreview(
                await api("/admin/backups/policy/prepare", "POST", {
                  uploads_enabled: f.get("enabled") === "on",
                  scopes: f.getAll("scopes"),
                  max_bytes: Math.round(Number(f.get("gib")) * 1024 ** 3),
                }),
              )
            }
          >
            <Checkbox
              name="enabled"
              defaultChecked={policy.data.uploads_enabled}
              label={t("Enable upload-file backups")}
            />
            <fieldset className="files-people">
              <legend>{t("Areas to include")}</legend>
              {["personal", "house", "drop", "media"].map((scope) => (
                <Checkbox
                  key={scope}
                  name="scopes"
                  value={scope}
                  defaultChecked={policy.data?.scopes?.includes(scope)}
                  label={t(prettyArea(scope))}
                />
              ))}
            </fieldset>
            <Field label={t("Maximum selected data · GiB")}>
              <Input
                name="gib"
                type="number"
                min={1}
                max={100}
                step={1}
                defaultValue={policy.data.max_bytes / 1024 ** 3}
                required
              />
            </Field>
          </Form>
        </>
      )}
      {preview && (
        <ConfirmSheet
          title={t("Review upload-backup policy")}
          confirm={t("Confirm this backup policy")}
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            const r = await api("/admin/backups/policy/confirm/" + preview.confirmation_id, "POST");
            toast(
              r.status === "completed"
                ? t("Policy saved for the next scheduled backup. Existing archives are retained.")
                : t("Backend state: {status}").replace("{status}", r.status),
            );
            await policy.reload();
          }}
        >
          <ReviewDetails value={preview.preview} />
          <Text>{t("This machine-local copy is not off-machine disaster recovery.")}</Text>
        </ConfirmSheet>
      )}
    </Section>
  );
}
function prettyArea(scope: string) {
  return (
    {
      personal: "Personal files",
      house: "House",
      drop: "House, temporary",
      media: "Uploaded media",
    }[scope] || scope
  );
}

function IncomingShare({
  id,
  actorId,
  actorName,
  offline,
  onClaim,
}: {
  id: string;
  actorId?: string;
  actorName?: string;
  offline: boolean;
  onClaim: (text: string) => void;
}) {
  const [incoming, setIncoming] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [discarding, setDiscarding] = useState(false),
    [sent, setSent] = useState("");
  useEffect(() => {
    void localStore("get", "incoming:" + id)
      .then((v) => setIncoming(v || {}))
      .catch((e) => setError(e.message));
  }, [id]);
  const matches = incoming && (!incoming.expected_actor || incoming.expected_actor === actorId);
  return (
    <Section title={t("Incoming share")} lead={t("On this device, not uploaded.")}>
      <Problem error={error} />
      {sent ? (
        <Notice tone="success">{sent}</Notice>
      ) : !incoming ? (
        <State kind="loading" title={t("Reading this device’s incoming share…")} />
      ) : !incoming.id ? (
        <Text>
          {t("This share is no longer available on this browser. Select the original files again.")}
        </Text>
      ) : !matches ? (
        <Text>
          {t(
            "Sign in to the account active when this share arrived. These files have not been assigned to another resident.",
          )}
        </Text>
      ) : (
        <>
          <Text>{incoming.text}</Text>
          {/* A shared link straight to an integration (Show on the TV…): nothing to keep after. */}
          {!offline && incoming.text && (
            <ShareButtons
              text={incoming.text}
              onSent={(message) => {
                void localStore("delete", "incoming:" + id);
                setSent(message);
              }}
            />
          )}
          {incoming.files?.length > 0 && (
            <List label={t("Shared files")}>
              {incoming.files.map((f: File, i: number) => (
                <ListRow
                  key={i}
                  leading={<Icon name="file" />}
                  title={f.name}
                  meta={bytes(f.size)}
                />
              ))}
            </List>
          )}
          <Form
            disabled={offline || !actorId}
            submit={t("Keep this share for {name}").replace("{name}", actorName || t("my account"))}
            onSubmit={async () => {
              const me = await api("/auth/me");
              if (me.user.id !== actorId)
                throw new Error(t("Your account changed. Reload before accepting this share."));
              const result = await claimIncomingShare(id, actorId!);
              onClaim(result.text);
            }}
          >
            <Text>
              {t(
                "Confirm the destination account before these files become your device drafts. Nothing will upload automatically.",
              )}
            </Text>
            {offline && <Text>{t("Reconnect and verify your account before accepting.")}</Text>}
          </Form>
        </>
      )}
      {incoming?.id && !sent && (
        <div>
          <Button variant="quiet" icon="trash" onClick={() => setDiscarding(true)}>
            {t("Discard incoming share")}
          </Button>
        </div>
      )}
      {discarding && (
        <ConfirmSheet
          title={t("Discard this incoming device-only share?")}
          confirm={t("Discard")}
          danger
          onClose={() => setDiscarding(false)}
          onConfirm={async () => {
            await localStore("delete", "incoming:" + id);
            setIncoming({});
          }}
        >
          <Text>{t("It was never uploaded; nothing else keeps it.")}</Text>
        </ConfirmSheet>
      )}
    </Section>
  );
}

/** What the house keeps on its own disk: songs saved after their first play, and films
 *  saved for offline. Songs can be downloaded or queued; films open in Watch. */
const LIBRARY_SORTS = {
  music: [
    ["recent", "Newest kept"],
    ["played", "Last played"],
    ["plays", "Most played"],
    ["title", "Title A–Z"],
    ["artist", "Artist A–Z"],
    ["size", "Largest"],
  ],
  movies: [
    ["recent", "Newest saved"],
    ["title", "Title A–Z"],
    ["year", "Newest release"],
    ["size", "Largest"],
  ],
} as const;
const FILM_TYPES = [
  ["", "All"],
  ["film", "Films"],
  ["series", "Series"],
  ["anime", "Anime"],
] as const;

function HouseLibrary({ kind }: { kind: "music" | "movies" }) {
  const [q, setQ] = useState(""),
    [sort, setSort] = useState("recent"),
    [genre, setGenre] = useState(""),
    [by, setBy] = useState(""),
    [type, setType] = useState(""),
    [film, setFilm] = useState<Obj | null>(null),
    [removing, setRemoving] = useState<Obj | null>(null),
    [twice, setTwice] = useState(false);
  const admin = useUser()?.role === "admin";
  // Admins: songs that may be kept twice (two links to one song), to keep one.
  const dupes = useData(admin && kind === "music" ? "/files/library/duplicates" : null);
  const doubles: number = dupes.data?.count || 0;
  useEffect(() => {
    setSort("recent");
    setGenre("");
    setType("");
  }, [kind]);
  const base =
    "/files/library?" +
    new URLSearchParams({ kind, sort, q: q.trim(), genre, by, type }).toString();
  const head = useData(base); // the first page also carries the counts for the chips
  const pages = usePages(base, (d) => (d.next_offset != null ? "offset=" + d.next_offset : null));
  const rows = pages.items.filter((row) => !row.deleted);
  const facets = head.data?.facets;
  const types: Record<string, number> = facets?.types || {};
  const filtered = !!(q || genre || by || type);
  return (
    <section
      className="files-place"
      aria-label={t(kind === "music" ? "House music" : "Films, series & anime")}
    >
      <Text style="body-s" tone="muted">
        {kind === "music"
          ? t("Every song is saved here after its first play, so the next time it starts at once.")
          : t("Films, series and anime saved on the house disk play even without the internet.")}
      </Text>
      {kind === "music" && <SortGenres />}
      {doubles > 0 && (
        <Notice
          title={t("Possible duplicates ({n})").replace("{n}", String(doubles))}
          action={
            <Button size="s" onClick={() => setTwice(true)}>
              {t("Review")}
            </Button>
          }
        >
          {t("The same song may be kept twice. Keep one to free the space.")}
        </Notice>
      )}
      <Toolbar label={t("Search the library")}>
        <SearchInput
          label={t("Search the library")}
          placeholder={t(kind === "music" ? "Title or artist…" : "Search the library…")}
          value={q}
          onChange={setQ}
        />
        <Select aria-label={t("Sort")} value={sort} onChange={(e) => setSort(e.target.value)}>
          {LIBRARY_SORTS[kind].map(([key, label]) => (
            <option key={key} value={key}>
              {t(label)}
            </option>
          ))}
        </Select>
      </Toolbar>
      {kind === "movies" && (
        <ChipGroup label={t("Type")}>
          {FILM_TYPES.filter(([key]) => !key || types[key]).map(([key, label]) => (
            <Chip
              key={key}
              kind="filter"
              selected={type === key}
              count={key ? types[key] : undefined}
              onToggle={() => setType(key)}
            >
              {t(label)}
            </Chip>
          ))}
        </ChipGroup>
      )}
      {(facets?.genres || []).length > 1 && (
        <ChipGroup label={t("Genre")}>
          <Chip kind="filter" selected={!genre} onToggle={() => setGenre("")}>
            {t("All genres")}
          </Chip>
          {facets.genres.slice(0, 14).map((g: Obj) => (
            <Chip
              key={g.genre}
              kind="filter"
              selected={genre === g.genre}
              count={g.count}
              onToggle={() => setGenre(genre === g.genre ? "" : g.genre)}
            >
              {t(g.genre)}
            </Chip>
          ))}
        </ChipGroup>
      )}
      <PeopleFilter
        value={by}
        onChange={setBy}
        label={kind === "music" ? "Played by" : "Saved by"}
        only={Object.keys(facets?.people || {})}
      />
      {head.data && (
        <Text style="body-s" tone="muted">
          {head.data.total} {t(kind === "music" ? "songs" : "titles")}
        </Text>
      )}
      <Problem error={pages.error} onRetry={pages.reload} />
      {kind === "music" ? (
        rows.length > 0 && (
          <List label={t("House music")}>
            {rows.map((song) => (
              <ListRow
                key={song.id}
                leading={
                  song.art ? (
                    <Media src={song.art} alt="" ratio="1 / 1" className="files-cover" />
                  ) : (
                    <Icon name="music-alt" />
                  )
                }
                title={song.title}
                detail={[
                  song.artist,
                  song.genre && song.genre !== "other" ? t(song.genre) : "",
                  song.plays ? "×" + song.plays : "",
                  bytes(song.size),
                  song.first_by && t("first played by") + " " + song.first_by,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                actions={
                  <>
                    {song.source_url && (
                      <IconButton
                        icon="list-add"
                        size="s"
                        label={t("Add to queue") + " · " + song.title}
                        onClick={async () => {
                          await api("/music/queue", "POST", {
                            source_url: song.source_url,
                            idempotency_key: idempotency(),
                          });
                          toast(t("Added to the queue."));
                        }}
                      />
                    )}
                    <LinkButton
                      variant="quiet"
                      size="s"
                      icon="download"
                      label={t("Download") + " · " + song.title}
                      href={song.download}
                    />
                    {song.can_delete && (
                      <IconButton
                        icon="trash"
                        size="s"
                        label={t("Delete") + " · " + song.title}
                        onClick={() => setRemoving(song)}
                      />
                    )}
                  </>
                }
              />
            ))}
          </List>
        )
      ) : (
        <ul className="files-films" aria-label={t("Films, series & anime")}>
          {rows.map((film) => (
            <li key={film.id}>
              <MediaCard
                media={<Media src={film.poster} alt="" />}
                title={film.title}
                meta={[
                  film.year,
                  t(FILM_TYPES.find(([k]) => k === film.type)?.[1] || "Films"),
                  bytes(film.size),
                  film.saved_by,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                onOpen={() => setFilm(film)}
              />
            </li>
          ))}
        </ul>
      )}
      <MoreBelow pages={pages} />
      {twice && dupes.data && (
        <Duplicates
          groups={dupes.data.groups || []}
          onClose={() => setTwice(false)}
          onChanged={(deleted) => {
            deleted.forEach((id) => pages.patch(id, { deleted: true }));
            dupes.reload();
          }}
        />
      )}
      {film && (
        <SavedFilm film={film} onClose={() => setFilm(null)} onDelete={() => setRemoving(film)} />
      )}
      {removing && (
        <ConfirmSheet
          title={t("Delete “{title}” from the house disk?").replace("{title}", removing.title)}
          confirm={t("Delete")}
          danger
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await api(
              `/files/library/${kind}/${removing.id}?version=${removing.version}`,
              "DELETE",
            );
            pages.patch(removing.id, { deleted: true });
            if (film?.id === removing.id) setFilm(null);
          }}
        >
          <Text>{t("Whoever wants it again plays or saves it again.")}</Text>
        </ConfirmSheet>
      )}
      {head.data && !rows.length && !pages.loading && (
        <State
          kind="empty"
          title={t(
            filtered
              ? "Nothing matches these filters."
              : kind === "music"
                ? "No songs kept yet."
                : "No films saved yet.",
          )}
        >
          {t(
            filtered
              ? "Clear a filter to see more."
              : kind === "music"
                ? "Play something and it lands here."
                : "Save a film from Watch to keep it here.",
          )}
        </State>
      )}
    </section>
  );
}

/** Admins: kept songs that may be one song twice. Keep one (the others are deleted), delete
 * any, listen first, or say they aren't the same song. Deleting is the library's own delete. */
function Duplicates({
  groups,
  onClose,
  onChanged,
}: {
  groups: Obj[];
  onClose: () => void;
  onChanged: (deleted: string[]) => void;
}) {
  const [hearing, setHearing] = useState<Obj | null>(null),
    [asked, setAsked] = useState<{ keep?: Obj; songs: Obj[] } | null>(null),
    [error, setError] = useState("");
  const remove = async (songs: Obj[]) => {
    const deleted: string[] = [];
    try {
      for (const song of songs) {
        await api(song.delete, "DELETE");
        deleted.push(song.id);
      }
    } finally {
      if (deleted.some((id) => id === hearing?.id)) setHearing(null);
      onChanged(deleted);
    }
  };
  return (
    <>
      <Sheet title={t("Possible duplicates")} place="side" onClose={onClose}>
        <div className="files-stack">
          <Text style="body-s" tone="muted">
            {t("Songs kept twice from different links. The most played is suggested to keep.")}
          </Text>
          {hearing && (
            <div className="files-stack">
              <Text style="body-s">{hearing.title}</Text>
              <audio controls autoPlay src={hearing.download} />
            </div>
          )}
          <Problem error={error} />
          {!groups.length && <State kind="empty" title={t("No possible duplicates left.")} />}
          {groups.map((group) => (
            <section
              key={group.ids.join()}
              className="files-stack"
              aria-label={group.songs[0]?.title}
            >
              <List label={group.songs[0]?.title}>
                {group.songs.map((song: Obj) => (
                  <ListRow
                    key={song.id}
                    leading={
                      song.art ? (
                        <Media src={song.art} alt="" ratio="1 / 1" className="files-cover" />
                      ) : (
                        <Icon name="music-alt" />
                      )
                    }
                    title={song.title}
                    detail={[
                      song.uploader,
                      clock(song.duration),
                      bytes(song.size),
                      t("{n} plays").replace("{n}", String(song.plays || 0)),
                      song.kept_at && t("kept {date}").replace("{date}", time(song.kept_at)),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    status={
                      song.suggested ? { tone: "success", text: t("Suggested to keep") } : undefined
                    }
                    actions={
                      <>
                        <IconButton
                          icon={hearing?.id === song.id ? "stop" : "play"}
                          size="s"
                          label={
                            (hearing?.id === song.id ? t("Stop") : t("Listen")) + " · " + song.title
                          }
                          onClick={() => setHearing(hearing?.id === song.id ? null : song)}
                        />
                        <Button
                          size="s"
                          variant="secondary"
                          onClick={() =>
                            setAsked({
                              keep: song,
                              songs: group.songs.filter((other: Obj) => other.id !== song.id),
                            })
                          }
                        >
                          {t("Keep this one")}
                        </Button>
                        <IconButton
                          icon="trash"
                          size="s"
                          label={t("Delete") + " · " + song.title}
                          onClick={() => setAsked({ songs: [song] })}
                        />
                      </>
                    }
                  />
                ))}
              </List>
              <Button
                size="s"
                variant="quiet"
                icon="check"
                onClick={async () => {
                  setError("");
                  try {
                    await api("/files/library/duplicates/dismiss", "POST", { ids: group.ids });
                    onChanged([]);
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                {t("Not duplicates")}
              </Button>
            </section>
          ))}
        </div>
      </Sheet>
      {asked && (
        <ConfirmSheet
          title={
            asked.keep
              ? t("Keep “{title}” and delete the others?").replace("{title}", asked.keep.title)
              : t("Delete “{title}” from the house disk?").replace("{title}", asked.songs[0].title)
          }
          confirm={t("Delete")}
          danger
          onClose={() => setAsked(null)}
          onConfirm={() => remove(asked.songs)}
        >
          <Text>{asked.songs.map((song) => song.title).join(" · ")}</Text>
        </ConfirmSheet>
      )}
    </>
  );
}

/** A picture of what the file is: folder, image, sound, film, document or anything else. */
function FileIcon({ entry, large = false }: { entry: Obj; large?: boolean }) {
  const mime = String(entry.mime || "");
  const [broken, setBroken] = useState(false);
  let shown: ReactNode;
  // Pictures show themselves (a small server-made thumbnail); the icon stays as a fallback.
  if (!entry.is_folder && /^image\/(jpeg|png|webp|gif)$/.test(mime) && !broken)
    shown = (
      <img
        className="files-thumb"
        src={`/api/v1/files/${entry.id}/thumb?v=${entry.version || 1}`}
        alt=""
        loading="lazy"
        onError={() => setBroken(true)}
      />
    );
  else
    shown = (
      <Icon
        size={large ? "l" : "m"}
        name={
          entry.is_folder
            ? "folder"
            : mime.startsWith("image/")
              ? "file-image"
              : mime.startsWith("audio/")
                ? "file-audio"
                : mime.startsWith("video/")
                  ? "file-video"
                  : mime.includes("pdf") || mime.startsWith("text/") || mime.includes("document")
                    ? "file-text"
                    : "file"
        }
      />
    );
  return (
    <span
      className="files-icon"
      data-large={large || undefined}
      data-folder={entry.is_folder || undefined}
    >
      {shown}
    </span>
  );
}

/** "Image", "PDF", "Folder"… rather than a MIME type. */
function kindOf(entry: Obj) {
  const mime = String(entry.mime || "");
  if (entry.is_folder) return t("Folder");
  if (mime.includes("pdf")) return "PDF";
  const family = mime.split("/")[0];
  return t(
    { image: "Image", audio: "Sound", video: "Video", text: "Text" }[family] ||
      (mime.includes("zip") ? "Archive" : "File"),
  );
}

/** A film kept at home: play it right here when the browser can, or send it to the TV. */
function SavedFilm({
  film,
  onClose,
  onDelete,
}: {
  film: Obj;
  onClose: () => void;
  onDelete: () => void;
}) {
  // The row carries a full /api/v1 address; useData adds that prefix itself.
  const check = useData(film.browser ? film.browser.replace(/^\/api\/v1/, "") : null);
  const [playing, setPlaying] = useState(false);
  return (
    <Sheet title={film.title} place="side" onClose={onClose}>
      <div className="files-stack">
        {playing && check.data?.stream ? (
          <video className="files-preview" src={check.data.stream} controls autoPlay playsInline />
        ) : (
          <Media src={film.poster} alt={film.title} className="files-poster" />
        )}
        <Problem error={check.error} />
        {check.loading && !check.data && (
          <Status tone="info" busy>
            {t("Checking whether it plays here…")}
          </Status>
        )}
        {check.data && !check.data.playable && (
          <Text style="body-s" tone="muted">
            {t(check.data.reason)}
          </Text>
        )}
        <div className="files-actions">
          {check.data?.playable && !playing && (
            <Button variant="primary" glyph="transport.play" onClick={() => setPlaying(true)}>
              {t("Play here")}
            </Button>
          )}
          {film.watch && (
            <Button icon="tv" onClick={() => go(film.watch)}>
              {t("Send to the TV")}
            </Button>
          )}
          {film.download && (
            <LinkButton icon="download" href={film.download}>
              {t("Download")}
            </LinkButton>
          )}
          {film.player_link && <OpenInPlayer path={film.player_link} title={film.title} />}
          {film.can_delete && (
            <Button variant="danger" icon="trash" onClick={onDelete}>
              {t("Delete from the house disk")}
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}

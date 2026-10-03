import { t } from "./i18n";
import { useTip } from "./tips";
import { useState, useEffect, useId, useRef, type CSSProperties, type ReactNode } from "react";
import {
  api,
  useData,
  usePages,
  useUser,
  items,
  time,
  pretty,
  idempotency,
  bytes,
  date as dateLabel,
  formatter,
  type Obj,
} from "./api";
import { RichText } from "./ask";
import { HouseStats } from "./house_stats";
import { go } from "./nav";
import { sendOrKeep } from "./outbox";
import {
  Avatar,
  Badge,
  Button,
  Checkbox,
  Chip,
  ChipGroup,
  Cluster,
  ConfirmSheet,
  Disclosure,
  EmojiTray,
  Field,
  Form,
  Hint,
  Icon,
  IconButton,
  Input,
  List,
  ListRow,
  Menu,
  type MenuItem,
  Page,
  PageHeader,
  Problem,
  QuickAdd,
  SearchInput,
  Section,
  Segmented,
  Select,
  Sheet,
  State,
  Status,
  SubNav,
  Surface,
  SwatchPicker,
  Text,
  Textarea,
  toast,
  type Tone,
  tone,
  Toolbar,
} from "./design";
import "./house.css";

/** The calendar day `plus` days from today in the house's time zone, as YYYY-MM-DD. */
function dayInTimezone(zone: string, plus: number) {
  const date = new Date(dayKey(new Date(), zone) + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + plus);
  return date.toISOString().slice(0, 10);
}
// Adds that can wait on this device when the house can't be reached (outbox.ts).
const OFFLINE_SAFE = new Set(["groceries", "tasks", "board"]);
const KEPT = "Saved on this device: it reaches the house when you're back online.";

async function create(kind: string, data: Obj, allow_duplicate = false) {
  const body = { data, idempotency_key: idempotency(), allow_duplicate };
  if (!OFFLINE_SAFE.has(kind)) return api("/household/" + kind, "POST", body);
  const made = await sendOrKeep("/household/" + kind, "POST", body);
  if (made === "queued") toast(t(KEPT));
  return made;
}
/** Emoji go where the cursor is, in a plain (uncontrolled) textarea. */
const insertInto = (box: React.RefObject<HTMLTextAreaElement | null>) => (text: string) => {
  const area = box.current;
  if (!area) return;
  area.setRangeText(text, area.selectionStart, area.selectionEnd, "end");
  area.focus();
};

// ---------- the room's places ----------
type Place = "board" | "groceries" | "tasks" | "calendar" | "numbers" | "messages";
const PLACES: [Place, string][] = [
  ["board", "House Wall"],
  ["groceries", "Groceries"],
  ["tasks", "Tasks"],
  ["calendar", "Calendar"],
  ["numbers", "Numbers"],
  ["messages", "Inbox"],
];

/** House's header and its places, the same on /house and /inbox. */
function HouseHeader({
  place,
  onPlace,
  actions,
}: {
  place: Place;
  onPlace: (place: Place) => void;
  actions?: ReactNode;
}) {
  const groceries = useData("/household/groceries?state=open&limit=1"),
    tasks = useData("/household/tasks?state=open&limit=1"),
    inbox = useData("/household/inbox?unread=true&limit=50");
  const tip = useTip("house");
  const counts: Partial<Record<Place, number>> = {
    groceries: groceries.data?.total || 0,
    tasks: tasks.data?.total || 0,
    messages: items(inbox.data).length,
  };
  return (
    <>
      <PageHeader
        room={place === "messages" ? "inbox" : "house"}
        title={t(place === "messages" ? "Inbox" : "House")}
        lead={place === "messages" ? undefined : tip}
        actions={actions}
        hint={
          place === "messages" ? (
            <Hint id="inbox">
              {t(
                "Little notes between housemates. Link a file and they can download it straight from the house.",
              )}
            </Hint>
          ) : (
            <Hint id="house">
              {t(
                "The kitchen board: notes, groceries, tasks and the calendar. Tick the circle to finish a task; a private event stays yours alone.",
              )}
            </Hint>
          )
        }
      />
      <SubNav
        label={t("House")}
        value={place}
        onChange={(next) => onPlace(next as Place)}
        items={PLACES.map(([id, label]) => ({ id, label: t(label), count: counts[id] }))}
      />
    </>
  );
}

// ---------- editing a record ----------
const EDITOR_TITLES: Record<string, [string, string]> = {
  board: ["New note", "Edit note"],
  tasks: ["New task", "Edit task"],
  calendar: ["New event", "Edit event"],
  groceries: ["New grocery item", "Edit grocery item"],
};

/** The whole record in a sheet: a new one, or one you're allowed to change. */
function RecordEditor({
  kind,
  record,
  onDone,
  onClose,
  date,
}: {
  kind: string;
  date?: string;
  record?: Obj;
  onDone: () => void;
  onClose: () => void;
}) {
  const d = record?.data || {};
  const user = useUser();
  const body = useRef<HTMLTextAreaElement>(null);
  const house = useData("/house-settings"),
    preferences = useData("/preferences");
  // The calendar's own zone (the resident's, else the house's): times mean what the grid shows.
  const timezone =
    d.timezone ||
    (house.data && (preferences.data || preferences.error)
      ? preferences.data?.timezone || house.data.timezone
      : undefined);
  const [allDay, setAllDay] = useState(!!d.all_day);
  const { data: people } = useData("/people");
  const zoneLabel = timezone || t("Loading house timezone…");
  const formId = useId();
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const repeat = (name: string, value: string, disabled = false) => (
    <Field label={t("Repeat")}>
      <Select name={name} defaultValue={value} disabled={disabled}>
        <option value="">{t("Does not repeat")}</option>
        <option value="daily">{t("Every day")}</option>
        <option value="weekly">{t("Every week")}</option>
        <option value="monthly">{t("Every month")}</option>
      </Select>
    </Field>
  );
  const fold = (label: string, value: string) => (
    <Disclosure summary={t("Clock-change options")}>
      <Field label={t(label)}>
        <Select name="fold" defaultValue={value}>
          <option value="">{t("Ask me if ambiguous")}</option>
          <option value="0">{t("First occurrence")}</option>
          <option value="1">{t("Second occurrence")}</option>
        </Select>
      </Field>
    </Disclosure>
  );
  const save = async (f: FormData) => {
    let data: Obj = {};
    if (kind === "board")
      data = {
        title: f.get("title"),
        body: f.get("body"),
        importance: f.get("importance"),
        pinned: f.get("pinned") === "on",
        expires_at: f.get("expires_at")
          ? new Date(String(f.get("expires_at"))).toISOString()
          : null,
        attachments: f.getAll("attachments"),
      };
    if (kind === "tasks")
      data = {
        title: f.get("title"),
        note: f.get("body"),
        assignee_id: f.get("assignee_id") || null,
        due_date: f.get("due_date") || null,
        recurrence: d.template_id ? undefined : f.get("recurrence") || null,
        due_time: f.get("due_time") || null,
        timezone,
        fold: f.get("fold") === "" || f.get("fold") == null ? null : Number(f.get("fold")),
        status: f.get("status") || d.status || "open",
        private: f.get("private") === "on",
      };
    if (kind === "calendar")
      data = {
        title: f.get("title"),
        start: f.get("start"),
        end: f.get("end"),
        timezone,
        all_day: allDay,
        recurrence: f.get("recurrence") || null,
        participants: f.getAll("participants"),
        reminder_minutes: f.get("reminder") ? [Number(f.get("reminder"))] : [],
        location: f.get("location"),
        notes: f.get("body"),
        start_fold: f.get("fold") === "" || f.get("fold") == null ? null : Number(f.get("fold")),
        end_fold: f.get("fold") === "" || f.get("fold") == null ? null : Number(f.get("fold")),
        private: f.get("private") === "on",
      };
    if (kind === "groceries")
      data = {
        label: f.get("title"),
        quantity: f.get("quantity"),
        unit: f.get("unit"),
        note: f.get("body"),
      };
    if (record)
      await api("/household/" + kind + "/" + record.id, "PATCH", {
        version: record.version,
        data,
      });
    else await create(kind, data);
    onDone();
    onClose();
  };
  return (
    <Sheet
      title={t((EDITOR_TITLES[kind] || ["New", "Edit"])[record ? 1 : 0])}
      place="side"
      onClose={onClose}
      footer={
        // In the sheet's own footer: Save stays in sight however long the form is.
        <>
          <Button variant="quiet" onClick={onClose}>
            {t("Cancel")}
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="primary"
            busy={busy}
            disabled={["tasks", "calendar"].includes(kind) && !timezone}
          >
            {t("Save")}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="ds-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setBusy(true);
          try {
            await save(f);
          } catch (e) {
            setFailure((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={kind === "groceries" ? t("Item") : t("Title")}>
          <Input name="title" required defaultValue={d.title || d.label} maxLength={160} />
        </Field>
        <Field label={t("Details")}>
          <Textarea ref={body} name="body" defaultValue={d.body || d.note || d.notes} rows={4} />
        </Field>
        {kind === "board" && <EmojiTray onPick={insertInto(body)} />}
        {["tasks", "calendar"].includes(kind) && (!record || record.owner_id === user?.id) && (
          <Checkbox
            name="private"
            defaultChecked={!!d.private}
            label={t("Private: only you see it")}
          />
        )}
        {kind === "board" && (
          <>
            <Field label={t("Importance")}>
              <Select name="importance" defaultValue={d.importance || "normal"}>
                <option value="normal">{t("normal")}</option>
                <option value="important">{t("important")}</option>
                <option value="urgent">{t("urgent")}</option>
              </Select>
            </Field>
            <Checkbox name="pinned" defaultChecked={d.pinned} label={t("Pin to the wall")} />
            <Field label={t("Expires (optional)")}>
              <Input name="expires_at" type="datetime-local" />
            </Field>
            <FilePicker houseOnly initial={d.attachments || []} />
          </>
        )}
        {kind === "tasks" && (
          <>
            <Field label={t("Assign to")}>
              <Select name="assignee_id" defaultValue={d.assignee_id || ""}>
                <option value="">{t("Unassigned")}</option>
                {items(people).map((p) => (
                  <option key={p.id} value={p.id}>
                    {personLabels(items(people))[p.id]}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="house-form-row">
              <Field label={t("Due date")}>
                <Input type="date" name="due_date" defaultValue={d.due_date} />
              </Field>
              <Field label={t("Due time") + " · " + zoneLabel}>
                <Input name="due_time" type="time" defaultValue={d.due_time} />
              </Field>
            </div>
            <Field label={t("Status")}>
              <Select name="status" defaultValue={d.status || "open"}>
                <option value="open">{t("Open")}</option>
                <option value="in_progress">{t("In progress")}</option>
                <option value="done">{t("Done")}</option>
                <option value="cancelled">{t("Cancelled")}</option>
              </Select>
            </Field>
            {repeat("recurrence", d.recurrence || "", !!d.template_id)}
            {fold("Task time if it occurs twice", String(d.fold ?? ""))}
          </>
        )}
        {kind === "calendar" && (
          <>
            <Checkbox
              checked={allDay}
              onChange={(e) => setAllDay(e.target.checked)}
              label={t("All-day event (end date is exclusive)")}
            />
            <div className="house-form-row">
              <Field label={t("Starts") + " · " + zoneLabel}>
                <Input
                  name="start"
                  type={allDay ? "date" : "datetime-local"}
                  required
                  defaultValue={d.start || (date ? (allDay ? date : date + "T18:00") : undefined)}
                />
              </Field>
              <Field label={t("Ends") + " · " + zoneLabel}>
                <Input
                  name="end"
                  type={allDay ? "date" : "datetime-local"}
                  required
                  defaultValue={
                    d.end ||
                    (date
                      ? allDay
                        ? new Date(Date.parse(date + "T12:00:00Z") + 86400000)
                            .toISOString()
                            .slice(0, 10)
                        : date + "T19:00"
                      : undefined)
                  }
                />
              </Field>
            </div>
            {repeat("recurrence", d.recurrence || "")}
            <PeopleChips
              name="participants"
              label={t("Participants")}
              people={items(people)}
              initial={d.participants || []}
            />
            <Field label={t("Reminder")}>
              <Select name="reminder" defaultValue={d.reminder_minutes?.[0] ?? ""}>
                <option value="">{t("None")}</option>
                <option value="15">{t("15 minutes before")}</option>
                <option value="60">{t("1 hour before")}</option>
                <option value="1440">{t("1 day before")}</option>
              </Select>
            </Field>
            <Field label={t("Location")}>
              <Input name="location" defaultValue={d.location} />
            </Field>
            {fold("If the local time occurs twice", "")}
          </>
        )}
        {kind === "groceries" && (
          <div className="house-form-row">
            <Field label={t("Quantity")}>
              <Input name="quantity" defaultValue={d.quantity} />
            </Field>
            <Field label={t("Unit")}>
              <Input name="unit" defaultValue={d.unit} />
            </Field>
          </div>
        )}
        <Problem error={failure} />
      </form>
    </Sheet>
  );
}

// ---------- the wall ----------
// Note papers: the theme's soft tones, so every theme recolours them (and checks them).
const NOTE_TONES: [string, string][] = [
  ["", "Plain"],
  ["sun", "Sun"],
  ["leaf", "Leaf"],
  ["sky", "Sky"],
  ["rose", "Rose"],
  ["lilac", "Lilac"],
  ["sand", "Sand"],
];
const NOTE_FILTERS: [string, string][] = [
  ["all", "All"],
  ["pinned", "Pinned"],
  ["mine", "Mine"],
  ["urgent", "Urgent"],
];

/** The house wall: notes on coloured paper, pinned ones first. `compact` is Home's window onto
 * it (the latest notes, no filters). */
export function WallFeed({
  pageSize = 24,
  compact = false,
}: {
  pageSize?: number;
  compact?: boolean;
}) {
  const user = useUser();
  const [offset, setOffset] = useState(0),
    [draft, setDraft] = useState(""),
    [tone, setTone] = useState(""),
    [pinned, setPinned] = useState(false),
    [urgent, setUrgent] = useState(false),
    [filter, setFilter] = useState("all"),
    [sending, setSending] = useState(false),
    [sendError, setSendError] = useState("");
  const { data, error, reload, loading } = useData(
    `/household/board?include_expired=true&limit=${pageSize}&offset=${offset}`,
  );
  const notes = items(data).filter(
    (r) =>
      filter === "all" ||
      (filter === "pinned" && r.data.pinned) ||
      (filter === "mine" && r.owner_id === user?.id) ||
      (filter === "urgent" && r.data.importance === "urgent"),
  );
  return (
    <div className="house-wall" data-compact={compact || undefined}>
      <form
        className="house-wall__compose"
        data-tone={tone || undefined}
        onSubmit={async (e) => {
          e.preventDefault();
          if (sending || !draft.trim()) return;
          setSending(true);
          setSendError("");
          try {
            await create("board", {
              body: draft.trim(),
              color: tone,
              pinned,
              importance: urgent ? "urgent" : "normal",
            });
            setDraft("");
            setPinned(false);
            setUrgent(false);
            setOffset(0);
            await reload();
          } catch (e) {
            setSendError((e as Error).message);
          } finally {
            setSending(false);
          }
        }}
      >
        <Textarea
          aria-label={t("Your message to the house")}
          placeholder={t("A little message for the house…")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={compact ? 1 : 2}
          maxLength={10000}
          disabled={sending}
        />
        <div className="house-wall__tools">
          {!compact && (
            <SwatchPicker
              label={t("Paper")}
              value={tone}
              onChange={setTone}
              options={NOTE_TONES.map(([value, label]) => ({
                value,
                label: t(label),
                color: value ? `var(--note-${value})` : "var(--c-bg-raised)",
              }))}
            />
          )}
          {!compact && (
            <IconButton
              icon="pin"
              label={t("Pin it to the top")}
              pressed={pinned}
              onClick={() => setPinned(!pinned)}
            />
          )}
          {!compact && (
            <IconButton
              icon="alert"
              label={t("Urgent")}
              pressed={urgent}
              onClick={() => setUrgent(!urgent)}
            />
          )}
          <Button
            type="submit"
            variant="primary"
            icon="send"
            busy={sending}
            disabled={!draft.trim()}
          >
            {t("Send")}
          </Button>
        </div>
      </form>
      <Problem error={sendError || error} onRetry={reload} />
      {!compact && (
        <ChipGroup label={t("Show")}>
          {NOTE_FILTERS.map(([key, label]) => (
            <Chip key={key} kind="filter" selected={filter === key} onToggle={() => setFilter(key)}>
              {t(label)}
            </Chip>
          ))}
        </ChipGroup>
      )}
      {loading && !data && <State kind="loading" />}
      <div className="house-wall__notes">
        {notes.map((r) => (
          <Note
            key={r.id}
            note={r}
            mine={r.owner_id === user?.id || user?.role === "admin"}
            onChanged={reload}
          />
        ))}
      </div>
      {!loading && !notes.length && (
        <State
          kind="empty"
          title={t(
            filter === "all" ? "Leave the first note for your housemates." : "No notes here.",
          )}
        />
      )}
      {(offset > 0 || data?.has_more) && (
        <nav className="house-pages" aria-label={t("House wall pages")}>
          <Button
            variant="quiet"
            icon="chevron-left"
            disabled={loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - pageSize))}
          >
            {t("Newer messages")}
          </Button>
          <Text style="caption" tone="muted">
            {t("Page")} {Math.floor(offset / pageSize) + 1}
          </Text>
          <Button
            variant="quiet"
            iconEnd="chevron-right"
            disabled={loading || !data?.has_more}
            onClick={() => setOffset(offset + pageSize)}
          >
            {t("Older messages")}
          </Button>
        </nav>
      )}
    </div>
  );
}

/** One note: its paper, who and when, and (for its author or an admin) pin, edit, done, delete. */
function Note({ note, mine, onChanged }: { note: Obj; mine: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false),
    [text, setText] = useState(note.data.body || ""),
    [deleting, setDeleting] = useState(false);
  const change = async (data: Obj) => {
    try {
      await api("/household/board/" + note.id, "PATCH", { version: note.version, data });
      onChanged();
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    }
  };
  const d = note.data;
  const actions: MenuItem[] = [
    {
      label: t(d.pinned ? "Unpin" : "Pin to the top"),
      icon: "pin",
      onSelect: () => void change({ pinned: !d.pinned }),
    },
    { label: t("Edit"), icon: "edit", onSelect: () => setEditing(true) },
    {
      label: t(d.resolved ? "Not done yet" : "Mark done"),
      icon: "check",
      onSelect: () => void change({ resolved: !d.resolved }),
    },
    { label: t("Delete"), icon: "trash", onSelect: () => setDeleting(true) },
  ];
  return (
    <Surface
      as="article"
      material="paper"
      className="house-note"
      data-importance={d.importance || undefined}
      data-tone={d.color || undefined}
      data-done={d.resolved || undefined}
    >
      <div className="house-note__head">
        <Text style="caption" tone="muted">
          {d.pinned && <Icon name="pin" size="s" />}{" "}
          <strong>{note.author_name || t("Housemate")}</strong> · {time(note.created_at)}
        </Text>
        {mine && <Menu label={t("Note actions")} items={actions} />}
      </div>
      {d.importance && d.importance !== "normal" && (
        <Badge tone={d.importance === "urgent" ? "danger" : "warning"}>{t(d.importance)}</Badge>
      )}
      {d.title && (
        <Text as="h3" style="title-s">
          {d.title}
        </Text>
      )}
      {editing ? (
        <form
          className="house-note__edit"
          onSubmit={(e) => {
            e.preventDefault();
            void change({ body: text.trim() }).then(() => setEditing(false));
          }}
        >
          <Textarea
            aria-label={t("Note")}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
          />
          <Cluster>
            <Button type="submit" size="s" variant="primary" disabled={!text.trim()}>
              {t("Save")}
            </Button>
            <Button size="s" variant="quiet" onClick={() => setEditing(false)}>
              {t("Cancel")}
            </Button>
          </Cluster>
        </form>
      ) : (
        <p className="house-note__body">{d.body}</p>
      )}
      {d.expires_at && (
        <Text style="caption" tone="muted">
          {t("Until {date}").replace("{date}", time(d.expires_at))}
        </Text>
      )}
      <AttachmentLinks ids={d.attachments || []} />
      {deleting && (
        <ConfirmSheet
          title={t("Delete this note?")}
          confirm={t("Delete")}
          danger
          onClose={() => setDeleting(false)}
          onConfirm={async () => {
            await api("/household/board/" + note.id + "?version=" + note.version, "DELETE");
            setDeleting(false);
            onChanged();
          }}
        >
          {t("It leaves the wall for everyone.")}
        </ConfirmSheet>
      )}
    </Surface>
  );
}

// ---------- days and times ----------
function linkedCalendarDate() {
  const value = new URLSearchParams(location.search).get("date");
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))
    ? value
    : null;
}
export function dayKey(instant: Date, zone: string) {
  const parts = formatter(
    "day " + zone,
    () =>
      new Intl.DateTimeFormat("en", {
        timeZone: zone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }),
  ).formatToParts(instant);
  return ["year", "month", "day"]
    .map((name) => parts.find((p) => p.type === name)!.value)
    .join("-");
}
function eventOnDay(event: Obj, day: string, zone: string) {
  if (event.all_day) return event.start.slice(0, 10) <= day && event.end.slice(0, 10) > day;
  // End is exclusive, including events finishing exactly at midnight.
  if (event.start_utc && event.end_utc)
    return (
      dayKey(new Date(event.start_utc), zone) <= day &&
      dayKey(new Date(new Date(event.end_utc).getTime() - 1), zone) >= day
    );
  return String(event.start).slice(0, 10) === day; // DST ambiguity is shown for review, never guessed.
}
function monthDays(date: string, mode = "month") {
  const start = new Date(date + "T12:00:00Z");
  if (mode === "month") start.setUTCDate(1);
  start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
  return Array.from({ length: mode === "month" ? 42 : 7 }, (_, i) => {
    const day = new Date(start);
    day.setUTCDate(day.getUTCDate() + i);
    return day.toISOString().slice(0, 10);
  });
}
function monthLabel(date: string) {
  return dateLabel(date + "T12:00:00Z", { month: "long", year: "numeric", timeZone: "UTC" });
}
const dayLabel = (day: string) =>
  dateLabel(day + "T12:00:00Z", { dateStyle: "full", timeZone: "UTC" });

/** An empty circle; tap it, then confirm: the task moves to Done (Reopen brings it back). */
function TaskCheck({ task, onDone }: { task: Obj; onDone: () => unknown }) {
  const [asking, setAsking] = useState(false),
    [error, setError] = useState("");
  const complete = async () => {
    try {
      const sent = await sendOrKeep("/household/tasks/" + task.id + "/action", "POST", {
        version: task.version,
        action: "complete",
      });
      if (sent === "queued") toast(t(KEPT));
      setAsking(false);
      await onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!asking)
    return (
      <IconButton
        icon="check"
        size="s"
        variant="secondary"
        className="task-check"
        label={t("Mark done") + " · " + task.data.title}
        onClick={() => setAsking(true)}
      />
    );
  return (
    <span className="house-confirm" role="group" aria-label={t("Done?") + " · " + task.data.title}>
      <IconButton
        icon="check"
        size="s"
        variant="primary"
        label={t("Yes, done")}
        onClick={() => void complete()}
      />
      <Button size="s" variant="quiet" onClick={() => setAsking(false)}>
        {t("Not yet")}
      </Button>
      {error && <Problem error={error} />}
    </span>
  );
}

const VIEWS: Record<string, [string, string][]> = {
  tasks: [
    ["open", "To do"],
    ["done", "Done"],
    ["recurring", "Recurring"],
  ],
  groceries: [
    ["open", "To buy"],
    ["bought", "Bought"],
  ],
};

/** Names as people read them: two people who share a name get a number after it. */
function personLabels(people: Obj[]) {
  const total: Record<string, number> = {},
    seen: Record<string, number> = {};
  for (const p of people) total[p.name] = (total[p.name] || 0) + 1;
  return Object.fromEntries(
    people.map((p) => {
      if (total[p.name] < 2) return [p.id, p.name];
      seen[p.name] = (seen[p.name] || 0) + 1;
      return [p.id, `${p.name} (${seen[p.name]})`];
    }),
  ) as Record<string, string>;
}

/** Pick people with chips that wrap; the picked ones are sent with the form as `name`. */
function PeopleChips({
  name,
  label,
  people,
  initial = [],
  search = "",
}: {
  name: string;
  label: string;
  people: Obj[];
  initial?: string[];
  /** Show only the names that contain it (the picked ones stay picked). */
  search?: string;
}) {
  const [picked, setPicked] = useState<string[]>(initial);
  const labels = personLabels(people);
  const shown = people.filter((p) => labels[p.id].toLowerCase().includes(search.toLowerCase()));
  return (
    <div className="house-people">
      <Text style="label" tone="muted">
        {label}
      </Text>
      {picked.map((id) => (
        <Input key={id} type="hidden" name={name} value={id} />
      ))}
      <ChipGroup label={label}>
        {shown.map((p) => (
          <Chip
            key={p.id}
            kind="person"
            tone={tone(p.id)}
            selected={picked.includes(p.id)}
            onToggle={() =>
              setPicked(
                picked.includes(p.id) ? picked.filter((id) => id !== p.id) : [...picked, p.id],
              )
            }
          >
            {labels[p.id]}
          </Chip>
        ))}
      </ChipGroup>
    </div>
  );
}

/** Add a task in one line; when, who and how often unfold once you start, and Enter adds it. */
function TaskComposer({
  timezone,
  onAdded,
  onMore,
}: {
  timezone?: string;
  onAdded: () => Promise<unknown>;
  onMore: () => void;
}) {
  const [title, setTitle] = useState(""),
    [when, setWhen] = useState(""),
    [who, setWho] = useState(""),
    [repeat, setRepeat] = useState(""),
    [focused, setFocused] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const { data: people } = useData("/people");
  const labels = personLabels(items(people));
  const zone = timezone || "UTC";
  const saturday = (6 - new Date().getDay() + 7) % 7 || 7;
  const whens: [string, string][] = [
    ["", "Any time"],
    [dayInTimezone(zone, 0), "Today"],
    [dayInTimezone(zone, 1), "Tomorrow"],
    [dayInTimezone(zone, saturday), "This weekend"],
  ];
  const chip = (value: string, current: string, set: (v: string) => void, label: string) => (
    <Chip
      key={value || "none"}
      kind="filter"
      selected={current === value}
      onToggle={() => set(current === value && value ? "" : value)}
    >
      {label}
    </Chip>
  );
  // Folded to its one field until you use it; it stays open while anything is filled in.
  const open = focused || !!(title || when || who || repeat);
  return (
    <form
      className="task-composer"
      onFocus={() => setFocused(true)}
      onBlur={(e) => {
        // "More details…" opens a sheet and gets focus back when it closes: stay open for it.
        const next = e.relatedTarget as HTMLElement | null;
        if (!e.currentTarget.contains(next) && !next?.closest("dialog")) setFocused(false);
      }}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!title.trim() || !timezone) return;
        setBusy(true);
        try {
          await create("tasks", {
            title: title.trim(),
            due_date: when || null,
            assignee_id: who || null,
            recurrence: repeat || null,
            timezone,
            status: "open",
          });
          toast(t("Added: {title}").replace("{title}", title.trim()));
          setTitle("");
          setError("");
          await onAdded();
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="task-composer__line">
        <Input
          aria-label={t("New task")}
          placeholder={t("Bins out, call the plumber…")}
          value={title}
          maxLength={160}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Button
          type="submit"
          variant="primary"
          icon="add"
          busy={busy}
          disabled={!title.trim() || !timezone}
        >
          {t("Add")}
        </Button>
      </div>
      {open && (
        <div className="task-composer__options">
          <div className="task-composer__option">
            <Text style="label" tone="muted">
              {t("When")}
            </Text>
            <ChipGroup label={t("When")}>
              {whens.map(([value, label]) => chip(value, when, setWhen, t(label)))}
              <Input
                type="date"
                aria-label={t("Pick a date")}
                value={whens.some(([value]) => value === when) ? "" : when}
                onChange={(e) => setWhen(e.target.value)}
              />
            </ChipGroup>
          </div>
          <Field label={t("Who")}>
            <Select value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">{t("Anyone")}</option>
              {items(people).map((person) => (
                <option key={person.id} value={person.id}>
                  {labels[person.id]}
                </option>
              ))}
            </Select>
          </Field>
          <div className="task-composer__option">
            <Text style="label" tone="muted">
              {t("Repeat")}
            </Text>
            <ChipGroup label={t("Repeat")}>
              {[
                ["", "Once"],
                ["daily", "Every day"],
                ["weekly", "Every week"],
                ["monthly", "Every month"],
              ].map(([value, label]) => chip(value, repeat, setRepeat, t(label)))}
            </ChipGroup>
          </div>
          <div className="task-composer__more">
            <Button variant="link" size="s" onClick={onMore}>
              {t("More details…")}
            </Button>
          </div>
        </div>
      )}
      <Problem error={error} />
    </form>
  );
}

const statusTone = (status: string): Tone =>
  status === "done" ? "success" : status === "cancelled" ? "neutral" : "info";

// ---------- the House page ----------
export function Household({ storage = false }: { storage?: boolean }) {
  const user = useUser();
  const me = user?.id;
  const [linkedId, setLinkedId] = useState(new URLSearchParams(location.search).get("record"));
  const [calendarView, setCalendarView] = useState("month"),
    [calendarDate, setCalendarDate] = useState(linkedCalendarDate() || dayKey(new Date(), "UTC"));
  const house = useData("/house-settings");
  const preferences = useData("/preferences"),
    calendarZone = preferences.data?.timezone || house.data?.timezone || "UTC";
  const [selectedDay, setSelectedDay] = useState<string | null>(linkedCalendarDate());
  useEffect(() => {
    if (preferences.data && !linkedCalendarDate())
      setCalendarDate(dayKey(new Date(), calendarZone));
  }, [preferences.data?.timezone]);
  const [kind, setKind] = useState<Place>(
      (new URLSearchParams(location.search).get("tab") as Place) || "board",
    ),
    [editor, setEditor] = useState<Obj | boolean>(false),
    [removing, setRemoving] = useState<Obj | null>(null),
    [duplicate, setDuplicate] = useState(""),
    [error, setError] = useState(""),
    [q, setQ] = useState(""),
    [compose, setCompose] = useState(() => new URLSearchParams(location.search).has("new"));
  const [offset, setOffset] = useState(0),
    [view, setView] = useState("open");
  // The palette moves between tabs of this page ("Tasks", "New task", "Add to groceries").
  useEffect(() => {
    const follow = () => {
      if (location.pathname !== "/house") return;
      const url = new URLSearchParams(location.search);
      setKind((url.get("tab") as Place) || "board");
      setView("open");
      setCompose(url.has("new"));
    };
    addEventListener("popstate", follow);
    return () => removeEventListener("popstate", follow);
  }, []);
  // The tab names the page (main.tsx leaves /house's title to it).
  useEffect(() => {
    document.title =
      t(PLACES.find(([id]) => id === kind)?.[1] || "House") +
      " · " +
      (house.data?.name || "Midnight House");
  }, [kind, house.data?.name]);
  // ?new: open on the composer, ready to type.
  useEffect(() => {
    if (!compose || view !== "open") return;
    const field = document.querySelector<HTMLInputElement>(
      ".task-composer input, .ds-quick-add input",
    );
    if (!field) return;
    field.scrollIntoView({ block: "nearest" });
    field.focus({ preventScroll: true });
    setCompose(false);
    history.replaceState(null, "", "/house?tab=" + kind);
  }, [compose, kind, view]);
  const views = VIEWS[kind];
  const listed = kind === "groceries" || kind === "tasks" || kind === "calendar";
  const linked = useData(
    linkedId ? "/household/" + encodeURIComponent(kind) + "/" + encodeURIComponent(linkedId) : null,
  );

  useEffect(() => setOffset(0), [kind, q, view]);
  useEffect(() => setView("open"), [kind]);
  const {
    data,
    error: loadError,
    reload,
    loading,
  } = useData(
    kind === "groceries" || kind === "tasks"
      ? "/household/" +
          kind +
          "?q=" +
          encodeURIComponent(q) +
          "&offset=" +
          offset +
          "&limit=100" +
          (views ? "&state=" + view : "")
      : null,
  );
  const anchor = new Date(calendarDate + "T12:00:00");
  const rangeStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  rangeStart.setDate(rangeStart.getDate() - 7);
  const rangeEnd = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 8);
  const dateString = (d: Date) =>
    d.getFullYear() +
    "-" +
    String(d.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(d.getDate()).padStart(2, "0");
  const agenda = useData(
    kind === "calendar"
      ? "/household/calendar/agenda?start=" +
          dateString(rangeStart) +
          "&end=" +
          dateString(rangeEnd)
      : null,
  );
  const records: Obj[] =
    kind === "calendar"
      ? items(agenda.data)
          .map((a) => ({
            id: a.id,
            version: a.version,
            data: a,
            occurrence_id: a.occurrence_id,
            owner_id: a.owner_id,
            visibility: a.visibility,
          }))
          .filter((r) => !q || r.data.title.toLowerCase().includes(q.toLowerCase()))
      : items(data);
  // Ticks shown before the house confirms them (or while it can't be reached).
  const [ticked, setTicked] = useState<Record<string, boolean>>({});
  useEffect(() => setTicked({}), [data]);
  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setError("");
      await reload();
      await agenda.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  // An occurrence is a shifted copy: edit the event itself, loaded fresh.
  const editRecord = (r: Obj) =>
    kind === "calendar"
      ? void run(async () => setEditor(await api("/household/calendar/" + r.id)))
      : setEditor(r);
  // Only the author removes it (an admin, when it belongs to the house).
  const canRemove = (r: Obj) =>
    r.owner_id === me || (user?.role === "admin" && r.visibility === "house");
  const open = (place: Place) => {
    if (place === "messages") return go("/inbox");
    setKind(place);
    history.replaceState(null, "", "/house?tab=" + place);
  };
  /** A week back or on in the week view, else a month. */
  const shift = (step: number) => {
    const d = new Date(calendarDate + "T12:00:00Z");
    if (calendarView === "week") d.setUTCDate(d.getUTCDate() + 7 * step);
    else {
      d.setUTCDate(1);
      d.setUTCMonth(d.getUTCMonth() + step);
    }
    setCalendarDate(d.toISOString().slice(0, 10));
  };
  const task = (r: Obj, action: string, extra: Obj = {}) =>
    void run(() =>
      api("/household/tasks/" + r.id + "/action", "POST", {
        version: r.version,
        action,
        ...extra,
      }),
    );
  const more = (r: Obj): MenuItem[] => [
    ...(kind === "tasks" && view === "open"
      ? [
          r.data.assignee_id === me
            ? {
                label: t("Decline assignment"),
                icon: "undo" as const,
                onSelect: () => task(r, "decline"),
              }
            : { label: t("I'll do it"), icon: "person" as const, onSelect: () => task(r, "claim") },
          {
            label: t("Snooze until tomorrow"),
            icon: "clock" as const,
            onSelect: () =>
              task(r, "snooze", { due_date: dayInTimezone(r.data.timezone || "UTC", 1) }),
          },
        ]
      : []),
    {
      label: r.data.recurrence ? t("Edit series") : t("Edit"),
      icon: "edit",
      onSelect: () => editRecord(r),
    },
    {
      label: t("Copy link"),
      icon: "link",
      onSelect: () =>
        void navigator.clipboard
          ?.writeText(
            location.origin + "/house?tab=" + encodeURIComponent(kind) + "&record=" + r.id,
          )
          .then(() => toast(t("Link copied."))),
    },
    ...(canRemove(r)
      ? [
          {
            label: t("Remove item"),
            icon: "trash" as const,
            danger: true,
            onSelect: () => setRemoving(r),
          },
        ]
      : []),
  ];
  const detail = (r: Obj) =>
    [
      r.data.body || r.data.note || r.data.notes,
      [r.data.quantity, r.data.unit].filter(Boolean).join(" "),
      kind === "calendar"
        ? (r.data.all_day ? r.data.start : time(r.data.start_utc || r.data.start)) +
          " · " +
          r.data.timezone
        : view === "done" && r.data.completed_at
          ? t("Done") + " · " + time(r.data.completed_at)
          : r.data.due_date || (kind === "tasks" ? "" : time(r.created_at)),
    ]
      .filter(Boolean)
      .join(" · ");
  const search = (
    <SearchInput
      label={t("Search household")}
      placeholder={kind === "calendar" ? t("Find an event…") : t("Find something in the house…")}
      value={q}
      onChange={setQ}
    />
  );
  return (
    <Page>
      <HouseHeader
        place={kind}
        onPlace={open}
        actions={
          kind === "calendar" && (
            <Button variant="primary" icon="add" onClick={() => setEditor(true)}>
              {t("Add an event")}
            </Button>
          )
        }
      />
      {kind === "numbers" && <HouseStats storage={storage} />}
      {kind === "board" && <WallFeed />}
      {listed && (
        <section
          className="house-place"
          data-place={kind}
          aria-label={t(PLACES.find(([id]) => id === kind)![1])}
        >
          {kind !== "calendar" && (
            <Toolbar label={t("Show")}>
              {search}
              {views && (
                <Segmented
                  label={t("Show")}
                  value={view}
                  onChange={setView}
                  options={views.map(([value, label]) => ({ value, label: t(label) }))}
                />
              )}
            </Toolbar>
          )}
          <Problem
            error={error || loadError || (kind === "calendar" ? agenda.error : "")}
            onRetry={() => {
              void reload();
              void agenda.reload();
            }}
          />
          {kind === "tasks" && view === "open" && (
            <TaskComposer
              timezone={preferences.data?.timezone || house.data?.timezone}
              onAdded={reload}
              onMore={() => setEditor(true)}
            />
          )}
          {kind === "groceries" && view === "open" && (
            <QuickAdd
              label={t("Add to the groceries")}
              placeholder={t("Milk, coffee, something for tonight…")}
              onAdd={async (label) => {
                try {
                  await create("groceries", { label });
                } catch (e) {
                  if ((e as any).detail?.code !== "DUPLICATE_REVIEW") throw e;
                  setDuplicate(label);
                }
                await reload();
              }}
            />
          )}
          {kind === "calendar" && (
            <>
              <div className="house-calendar-bar">
                <div className="house-calendar-bar__nav">
                  <IconButton
                    icon="chevron-left"
                    label={t(calendarView === "week" ? "Previous week" : "Previous month")}
                    onClick={() => shift(-1)}
                  />
                  <Text as="h2" style="title-m" className="house-calendar-bar__month">
                    {monthLabel(calendarDate)}
                  </Text>
                  <IconButton
                    icon="chevron-right"
                    label={t(calendarView === "week" ? "Next week" : "Next month")}
                    onClick={() => shift(1)}
                  />
                  <Button
                    variant="quiet"
                    onClick={() => setCalendarDate(dayKey(new Date(), calendarZone))}
                  >
                    {t("Today")}
                  </Button>
                </div>
                <div className="house-calendar-bar__tools">
                  <Select
                    aria-label={t("Calendar view")}
                    value={calendarView}
                    onChange={(e) => setCalendarView(e.target.value)}
                  >
                    <option value="list">{t("Agenda")}</option>
                    <option value="week">{t("Week")}</option>
                    <option value="month">{t("Month")}</option>
                  </Select>
                  <Input
                    aria-label={t("Calendar date")}
                    className="house-calendar-bar__date"
                    type="date"
                    value={calendarDate}
                    onChange={(e) => {
                      if (e.target.value) setCalendarDate(e.target.value);
                    }}
                  />
                  {search}
                  <Menu
                    label={t("More calendar actions")}
                    items={[
                      {
                        label: t("Export calendar"),
                        icon: "download",
                        onSelect: () => location.assign("/api/v1/household/calendar/export.ics"),
                      },
                    ]}
                  />
                </div>
              </div>
              <Text style="caption" tone="muted">
                {t("Times shown in")} {calendarZone}
                {t(". Select a day for full details.")}
              </Text>
              {calendarView !== "list" && (
                <CalendarGrid
                  records={records}
                  date={calendarDate}
                  mode={calendarView}
                  onEdit={editRecord}
                  zone={calendarZone}
                  onDay={setSelectedDay}
                />
              )}
            </>
          )}
          {loading && !data && <State kind="loading" />}
          {(kind !== "calendar" || calendarView === "list") && records.length > 0 && (
            <List label={t(PLACES.find(([id]) => id === kind)![1])}>
              {records.map((r) => {
                const struck = r.data.purchased || r.data.status === "done";
                return (
                  <ListRow
                    key={r.occurrence_id || r.id}
                    leading={
                      kind === "tasks" && view === "open" ? (
                        <TaskCheck task={r} onDone={() => run(async () => {})} />
                      ) : kind === "groceries" ? (
                        <Checkbox
                          hideLabel
                          label={t("Bought") + " · " + r.data.label}
                          checked={ticked[r.id] ?? !!r.data.purchased}
                          onChange={() => {
                            // Ticks at once, even offline (it syncs when the house is back).
                            const value = !(ticked[r.id] ?? r.data.purchased);
                            setTicked({ ...ticked, [r.id]: value });
                            void run(async () => {
                              const sent = await sendOrKeep(
                                "/household/groceries/" + r.id,
                                "PATCH",
                                {
                                  version: r.version,
                                  data: { purchased: value },
                                },
                              );
                              if (sent === "queued") toast(t(KEPT));
                            });
                          }}
                        />
                      ) : undefined
                    }
                    title={
                      struck ? <s>{r.data.title || r.data.label}</s> : r.data.title || r.data.label
                    }
                    detail={detail(r) || undefined}
                    meta={
                      <>
                        {r.data.private && (
                          <Badge tone="private">
                            <Icon name="lock" size="s" /> {t("Private")}
                          </Badge>
                        )}
                        {(r.data.assignee_id === me ||
                          (r.data.participants || []).includes(me)) && (
                          <Badge tone="accent">{t("For you")}</Badge>
                        )}
                        {r.data.status && kind === "tasks" && view !== "open" && (
                          <Status tone={statusTone(r.data.status)}>
                            {t(pretty(r.data.status))}
                          </Status>
                        )}
                      </>
                    }
                    actions={
                      <>
                        {kind === "tasks" && view === "done" && (
                          <Button size="s" onClick={() => task(r, "reopen")}>
                            {t("Reopen")}
                          </Button>
                        )}
                        {kind === "groceries" && r.data.undo && (
                          <Button
                            size="s"
                            icon="undo"
                            onClick={() =>
                              void run(() =>
                                api("/household/groceries/" + r.id + "/undo", "POST", {
                                  version: r.version,
                                }),
                              )
                            }
                          >
                            {t("Undo")}
                          </Button>
                        )}
                        <Menu
                          label={t("More") + " · " + (r.data.title || r.data.label)}
                          items={more(r)}
                        />
                      </>
                    }
                  >
                    {(r.data.attachments || []).length > 0 && (
                      <AttachmentLinks ids={r.data.attachments} />
                    )}
                  </ListRow>
                );
              })}
            </List>
          )}
          {!loading && !records.length && (kind !== "calendar" || calendarView === "list") && (
            <State
              kind="empty"
              title={
                view === "done"
                  ? t("Finished tasks land here; Reopen puts one back.")
                  : view === "bought"
                    ? t("Ticked groceries land here; untick one to put it back on the list.")
                    : view === "recurring"
                      ? t("No repeating task yet: choose Repeat when you add one.")
                      : t("A little room for everyday things.")
              }
            />
          )}
          {kind !== "calendar" && (offset > 0 || data?.has_more) && (
            <nav className="house-pages" aria-label={t("Pages")}>
              <Button
                variant="quiet"
                icon="chevron-left"
                disabled={!offset}
                onClick={() => setOffset((o) => Math.max(0, o - 100))}
              >
                {t("Previous items")}
              </Button>
              <Text style="caption" tone="muted">
                {t("Page")} {Math.floor(offset / 100) + 1}
              </Text>
              <Button
                variant="quiet"
                iconEnd="chevron-right"
                disabled={!data?.has_more}
                onClick={() => setOffset((o) => o + 100)}
              >
                {t("Next items")}
              </Button>
            </nav>
          )}
        </section>
      )}
      {selectedDay && (
        <Sheet
          title={dayLabel(selectedDay)}
          onClose={() => setSelectedDay(null)}
          footer={
            <Button
              variant="primary"
              icon="add"
              onClick={() => {
                setCalendarDate(selectedDay);
                setSelectedDay(null);
                setEditor(true);
              }}
            >
              {t("Add an event")}
            </Button>
          }
        >
          <DayEvents
            events={records.filter((r) => eventOnDay(r.data, selectedDay, calendarZone))}
            zone={calendarZone}
            canRemove={canRemove}
            onEdit={(r) => {
              setSelectedDay(null);
              editRecord(r);
            }}
            onRemove={(r) => {
              setSelectedDay(null);
              setRemoving(r);
            }}
          />
        </Sheet>
      )}
      {linkedId && (
        <Sheet
          title={linked.data?.data?.title || linked.data?.data?.label || t("House item")}
          onClose={() => setLinkedId(null)}
          footer={
            linked.data && (
              <Button
                icon="edit"
                onClick={() => {
                  setEditor(linked.data!);
                  setLinkedId(null);
                }}
              >
                {t("Edit this item")}
              </Button>
            )
          }
        >
          <Problem error={linked.error} />
          {!linked.data && !linked.error && <State kind="loading" />}
          {linked.data && (
            <div className="house-stack">
              <Text>
                {linked.data.data.body ||
                  linked.data.data.note ||
                  linked.data.data.notes ||
                  linked.data.data.text}
              </Text>
              <Text style="body-s" tone="muted">
                {linked.data.data.start || linked.data.data.due_date} {linked.data.data.timezone}
              </Text>
              <AttachmentLinks ids={linked.data.data.attachments || []} />
            </div>
          )}
        </Sheet>
      )}
      {editor && (
        <RecordEditor
          kind={kind}
          date={kind === "calendar" ? calendarDate : undefined}
          record={typeof editor === "object" ? editor : undefined}
          onDone={() => {
            void reload();
            void agenda.reload();
          }}
          onClose={() => setEditor(false)}
        />
      )}
      {removing && (
        <ConfirmSheet
          title={
            kind === "calendar"
              ? removing.data.recurrence
                ? t("Remove this event and all its repeats?")
                : t("Remove this event?")
              : t("Remove this item?")
          }
          confirm={t("Remove")}
          danger
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await api(
              "/household/" + kind + "/" + removing.id + "?version=" + removing.version,
              "DELETE",
            );
            await reload();
            await agenda.reload();
          }}
        >
          <Text>{removing.data.title || removing.data.label}</Text>
        </ConfirmSheet>
      )}
      {duplicate && (
        <ConfirmSheet
          title={t("This item is already on the list. Add a separate item?")}
          confirm={t("Add")}
          onClose={() => setDuplicate("")}
          onConfirm={async () => {
            await create("groceries", { label: duplicate }, true);
            await reload();
          }}
        >
          <Text>{duplicate}</Text>
        </ConfirmSheet>
      )}
    </Page>
  );
}

/** A day's events, each with its time, place and notes. */
function DayEvents({
  events,
  zone,
  canRemove,
  onEdit,
  onRemove,
}: {
  events: Obj[];
  zone: string;
  canRemove: (r: Obj) => boolean;
  onEdit: (r: Obj) => void;
  onRemove: (r: Obj) => void;
}) {
  if (!events.length) return <State kind="empty" title={t("No house events on this day.")} />;
  return (
    <List label={t("Events")}>
      {events.map((r) => (
        <ListRow
          key={r.occurrence_id || r.id}
          title={
            <span role="heading" aria-level={3}>
              {r.data.title}
            </span>
          }
          detail={[
            r.data.all_day
              ? t("All day")
              : r.data.start_utc
                ? dateLabel(r.data.start_utc, {
                    dateStyle: "medium",
                    timeStyle: "short",
                    timeZone: zone,
                  }) +
                  " · " +
                  zone
                : t("Time needs daylight-saving review"),
            r.data.location,
          ]
            .filter(Boolean)
            .join(" · ")}
          actions={
            <>
              <Button size="s" icon="edit" onClick={() => onEdit(r)}>
                {t("View / edit event")}
              </Button>
              {canRemove(r) && (
                <IconButton
                  icon="trash"
                  size="s"
                  label={t("Remove event") + " · " + r.data.title}
                  onClick={() => onRemove(r)}
                />
              )}
            </>
          }
        >
          {r.data.notes && <Text>{r.data.notes}</Text>}
        </ListRow>
      ))}
    </List>
  );
}

function CalendarGrid({
  records,
  date,
  mode,
  onEdit,
  zone,
  onDay,
}: {
  records: Obj[];
  date: string;
  mode: string;
  onEdit: (r: Obj) => void;
  zone: string;
  onDay: (day: string) => void;
}) {
  const today = dayKey(new Date(), zone);
  return (
    <div className="house-calendar" data-mode={mode}>
      {Array.from({ length: 7 }, (_, i) =>
        // 1 January 2024 was a Monday: the weekday names in the page's language.
        dateLabel(new Date(2024, 0, 1 + i), { weekday: "short" }),
      ).map((day) => (
        <Text key={day} style="label" tone="muted" className="house-calendar__weekday">
          {day}
        </Text>
      ))}
      {monthDays(date, mode).map((day) => {
        const events = records.filter((r) => eventOnDay(r.data, day, zone));
        return (
          <div
            key={day}
            className="house-calendar__day"
            data-outside={day.slice(0, 7) !== date.slice(0, 7) || undefined}
            data-today={day === today || undefined}
          >
            <Button
              size="s"
              variant={day === today ? "primary" : "quiet"}
              aria-label={t("Events on {day}").replace("{day}", dayLabel(day))}
              onClick={() => onDay(day)}
            >
              {Number(day.slice(-2))}
            </Button>
            {events.slice(0, mode === "month" ? 3 : events.length).flatMap((r) => [
              // On a phone's month a mark only: the day button opens its events.
              <span
                key={"mark" + (r.occurrence_id || r.id)}
                className="house-calendar__mark"
                data-warning={r.data.schedule_error ? true : undefined}
                aria-hidden="true"
              />,
              <Button
                key={r.occurrence_id || r.id}
                size="s"
                variant="secondary"
                className="house-calendar__event"
                icon={r.data.schedule_error ? "warning" : undefined}
                onClick={() => onEdit(r)}
              >
                {!r.data.all_day && r.data.start_utc && (
                  <span className="tabular">
                    {dateLabel(r.data.start_utc, {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: zone,
                    })}{" "}
                  </span>
                )}
                {r.data.title}
              </Button>,
            ])}
            {mode === "month" && events.length > 3 && (
              <Button
                size="s"
                variant="link"
                className="house-calendar__more"
                onClick={() => onDay(day)}
              >
                +{events.length - 3}
                <span className="house-calendar__more-word"> {t("more")}</span>
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------- files in notes and messages ----------
/** Link files to a message or note. Your own files are opened to the recipients for 30
 *  days when you send; house files are already everyone's. */
function FilePicker({
  houseOnly = false,
  initial = [],
}: {
  houseOnly?: boolean;
  initial?: string[];
}) {
  const [open, setOpen] = useState(false),
    [q, setQ] = useState(""),
    [picked, setPicked] = useState<string[]>(initial);
  const search = q ? "&q=" + encodeURIComponent(q) : "";
  const mine = useData(open && !houseOnly ? "/files?scope=personal&limit=40" + search : null);
  const house = useData(open ? "/files?scope=house&limit=40" + search : null);
  const choices = [...items(mine.data), ...items(house.data)].filter(
    (file) => !file.is_folder && !picked.includes(file.id),
  );
  return (
    <div className="house-files">
      {picked.map((id) => (
        <Input key={id} type="hidden" name="attachments" value={id} />
      ))}
      {picked.length > 0 && (
        <ul className="house-files__picked" aria-label={t("Linked files")}>
          {picked.map((id) => (
            <li key={id}>
              <FileChip id={id} />
              <IconButton
                icon="close"
                size="s"
                label={t("Remove file")}
                onClick={() => setPicked(picked.filter((other) => other !== id))}
              />
            </li>
          ))}
        </ul>
      )}
      {picked.length < 10 && (
        <div>
          <Button
            size="s"
            variant="quiet"
            icon="paperclip"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {t("Link a file")}
          </Button>
        </div>
      )}
      {open && (
        <div className="house-stack">
          <SearchInput
            label={t("Find a file")}
            placeholder={t("Find a file…")}
            value={q}
            onChange={setQ}
          />
          <Problem error={mine.error || house.error} />
          {choices.length > 0 && (
            <List label={t("Files")}>
              {choices.slice(0, 30).map((file) => (
                <ListRow
                  key={file.id}
                  leading={<Icon name="file-text" size="s" />}
                  title={file.name}
                  meta={file.scope === "house" ? t("House") : t("Yours")}
                  onOpen={() => {
                    setPicked([...picked, file.id]);
                    setOpen(false);
                    setQ("");
                  }}
                />
              ))}
            </List>
          )}
          {!choices.length && (mine.data || house.data) && (
            <Text style="body-s" tone="muted">
              {t("No file by that name.")}
            </Text>
          )}
          {!houseOnly && (
            <Text style="body-s" tone="muted">
              {t("Your own files open to the recipients for 30 days.")}
            </Text>
          )}
        </div>
      )}
    </div>
  );
}

/** A linked file: its name and size, and a click downloads it from the house. */
function FileChip({ id, link = false }: { id: string; link?: boolean }) {
  const info = useData("/files/" + encodeURIComponent(id) + "/info");
  const name = info.data?.name || (info.error ? t("File no longer available") : "…");
  const body = (
    <>
      <Icon name="file-text" size="s" />
      <span className="house-file__name">{name}</span>
      {info.data?.size != null && <small className="tabular">{bytes(info.data.size)}</small>}
    </>
  );
  return link && !info.error ? (
    <a className="house-file" href={"/api/v1/files/" + encodeURIComponent(id) + "/download"}>
      {body}
    </a>
  ) : (
    <span className="house-file">{body}</span>
  );
}

function AttachmentLinks({ ids }: { ids: string[] }) {
  return ids.length ? (
    <div className="house-files__links">
      {ids.map((id) => (
        <FileChip key={id} id={id} link />
      ))}
    </div>
  ) : null;
}

// ---------- messages ----------
/** One message, the same in a thread and anywhere else. */
function Bubble({ r, byId, me }: { r: Obj; byId: Record<string, Obj>; me?: string }) {
  const author = byId[r.owner_id];
  const mine = r.owner_id === me;
  return (
    <article
      className="house-message"
      data-mine={mine || undefined}
      style={{ "--tone": tone(r.owner_id) } as CSSProperties}
    >
      <Text as="header" style="caption" tone="muted" className="house-message__head">
        <strong>{mine ? t("You") : author?.name || t("A housemate")}</strong> · {time(r.created_at)}
      </Text>
      {r.data.title && (
        <Text as="h3" style="title-s">
          {r.data.title}
        </Text>
      )}
      <RichText text={r.data.body} className="house-message__body" />
      <AttachmentLinks ids={r.data.attachments || []} />
    </article>
  );
}

/** When, briefly: the time today, the day otherwise. */
const when = (iso: string) => {
  const today = new Date().toDateString() === new Date(iso).toDateString();
  return dateLabel(
    iso,
    today ? { hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short" },
  );
};

const withKey = () => new URLSearchParams(location.search).get("with") || "";

/** Conversations: everyone you have written with, latest first; open one to read it all
 *  (older messages load on demand) and reply to the same people. */
export function InboxPage() {
  const talks = useData("/household/conversations");
  const inbox = useData("/household/inbox?unread=true&limit=50");
  const people = useData("/people");
  const me = useUser()?.id;
  const [open, setOpenState] = useState(withKey());
  const setOpen = (key: string) => {
    setOpenState(key);
    history.replaceState(null, "", key ? "/inbox?with=" + key : "/inbox");
  };
  // A new message, to someone already chosen (NewMessage reads ?to= when it opens).
  const write = (to?: string) => {
    history.replaceState(null, "", "/inbox?with=new" + (to ? "&to=" + to : ""));
    setOpenState("");
    setTimeout(() => setOpenState("new"));
  };
  // The palette's "New message" while this page is already open.
  useEffect(() => {
    const follow = () => setOpenState(withKey());
    addEventListener("popstate", follow);
    return () => removeEventListener("popstate", follow);
  }, []);
  const byId = Object.fromEntries(items(people.data).map((p) => [p.id, p]));
  const list = items(talks.data);
  const current = list.find((c) => c.key === open);
  const others = (c: Obj) => (c.people || []).filter((p: Obj) => p.id !== me);
  const names = (c: Obj) =>
    others(c)
      .map((p: Obj) => p.name)
      .join(", ") || t("Just you");
  // Assignments and reminders still arrive here; messages are counted per conversation.
  const notices = items(inbox.data).filter((r) => r.category !== "message");
  const read = async (r: Obj) => {
    await api("/household/inbox/" + r.id + "/read", "POST");
    await inbox.reload();
  };
  return (
    <Page>
      <HouseHeader
        place="messages"
        onPlace={(place) => (place === "messages" ? setOpen("") : go("/house?tab=" + place))}
      />
      <Problem error={talks.error} onRetry={talks.reload} />
      <div className="inbox-layout" data-open={open ? "" : undefined}>
        <div className="inbox-list">
          <Button variant="primary" icon="add" onClick={() => write()}>
            {t("New message")}
          </Button>
          {notices.length > 0 && (
            <div className="inbox-notices">
              <List label={t("Notices")}>
                {notices.map((r) => (
                  <ListRow
                    key={r.id}
                    leading={<Icon name={r.category === "update" ? "check" : "info"} size="s" />}
                    title={
                      r.category === "update"
                        ? t(
                            "Nox: HouseOS {version} is out. Update in Control Room, or ask me.",
                          ).replace("{version}", r.record_id)
                        : t(NOTICES[r.category] || "New notice")
                    }
                    detail={r.created_at ? when(r.created_at) : undefined}
                    actions={
                      <>
                        {r.category === "update" && (
                          <Button size="s" onClick={() => go("/control?tab=services")}>
                            {t("See the update")}
                          </Button>
                        )}
                        {r.category === "assignment" && (
                          <Button
                            size="s"
                            onClick={() => go("/house?tab=tasks&record=" + r.record_id)}
                          >
                            {t("Open task")}
                          </Button>
                        )}
                        <IconButton
                          icon="check"
                          size="s"
                          variant="quiet"
                          label={t("Mark read")}
                          onClick={() => void read(r)}
                        />
                      </>
                    }
                  />
                ))}
              </List>
            </div>
          )}
          <nav aria-label={t("Conversations")}>
            {list.length > 0 && (
              <List label={t("Conversations")}>
                {list.map((c) => (
                  <ListRow
                    key={c.key}
                    selected={c.key === open}
                    leading={
                      <span className="inbox-faces" aria-hidden="true">
                        {others(c)
                          .slice(0, 3)
                          .map((p: Obj) => (
                            <Avatar
                              key={p.id}
                              name={p.name}
                              picture={p.avatar}
                              tone={tone(p.id)}
                              size="s"
                            />
                          ))}
                      </span>
                    }
                    title={names(c)}
                    detail={
                      (c.last.owner_id === me ? t("You") + ": " : "") +
                      (c.last.data.title || c.last.data.body)
                    }
                    meta={
                      <>
                        <span className="tabular">{when(c.last.created_at)}</span>
                        {c.unread > 0 && (
                          <Badge label={t("{n} unread").replace("{n}", String(c.unread))}>
                            {c.unread}
                          </Badge>
                        )}
                      </>
                    }
                    onOpen={() => setOpen(c.key)}
                  />
                ))}
              </List>
            )}
            {talks.data && !list.length && (
              <State kind="empty" title={t("The courier is taking a little rest.")}>
                {t("Messages to you will arrive here.")}
              </State>
            )}
          </nav>
        </div>
        <section className="inbox-pane" aria-label={current ? names(current) : t("Inbox")}>
          {open === "new" ? (
            <NewMessage
              key={people.data ? "people" : "waiting"}
              people={items(people.data)}
              onSent={async () => {
                // The newest conversation is the one just written to.
                const fresh = await api("/household/conversations");
                await talks.reload();
                setOpen(items(fresh)[0]?.key || "");
              }}
              onClose={() => setOpen("")}
            />
          ) : current ? (
            <Conversation
              key={current.key}
              talk={current}
              title={names(current)}
              byId={byId}
              me={me}
              onChange={() => {
                void talks.reload();
                void inbox.reload();
              }}
              onClose={() => setOpen("")}
            />
          ) : (
            <State
              kind="empty"
              title={t(list.length ? "Pick a conversation, or start one" : "Start a conversation")}
            >
              <div className="inbox-start">
                {items(people.data)
                  .filter((p) => p.id !== me)
                  .map((p) => (
                    <Button key={p.id} variant="quiet" onClick={() => write(p.id)}>
                      <Avatar
                        name={p.name}
                        picture={p.avatar}
                        tone={tone(p.id)}
                        size="s"
                        decorative
                      />
                      {p.name}
                    </Button>
                  ))}
              </div>
            </State>
          )}
        </section>
      </div>
    </Page>
  );
}

function Conversation({
  talk,
  title,
  byId,
  me,
  onChange,
  onClose,
}: {
  talk: Obj;
  title: string;
  byId: Record<string, Obj>;
  me?: string;
  onChange: () => void;
  onClose: () => void;
}) {
  const [round, setRound] = useState(0);
  const pages = usePages("/household/conversations/" + talk.key + "?limit=30&v=" + round, (d) =>
    d.next_before ? "before=" + d.next_before : null,
  );
  const body = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null),
    reply = useRef<HTMLDivElement>(null);
  const [sent, setSent] = useState(0);
  const first = pages.items[0]?.id;
  useEffect(() => {
    if (!pages.loading) onChange(); // opening it marked it read
  }, [talk.key]);
  // Braces matter: scrollIntoView returns a promise in newer browsers, and an effect must not.
  // The newest message and the reply box, both above the dock (base.css's scroll padding).
  useEffect(() => {
    (reply.current || end.current)?.scrollIntoView({ block: "nearest" });
  }, [first]);
  const recipients = (talk.people || []).map((p: Obj) => p.id).filter((id: string) => id !== me);
  return (
    <div className="inbox-conversation">
      <header className="inbox-conversation__head">
        <IconButton
          icon="back"
          label={t("Conversations")}
          className="inbox-back"
          onClick={onClose}
        />
        <Text as="h2" style="title-l">
          {title}
        </Text>
      </header>
      <Problem error={pages.error} onRetry={pages.reload} />
      <div className="inbox-thread">
        {pages.more && (
          <Button size="s" variant="quiet" icon="chevron-up" onClick={pages.more}>
            {t("Show older messages")}
          </Button>
        )}
        {[...pages.items].reverse().map((r) => (
          <Bubble key={r.id} r={r} byId={byId} me={me} />
        ))}
        <div ref={end} />
      </div>
      {recipients.length > 0 && (
        <div className="inbox-reply" key={sent} ref={reply}>
          <Form
            submit={t("Send")}
            onSubmit={async (f) => {
              await create("messages", {
                body: String(f.get("body") || ""),
                recipient_ids: recipients,
                attachments: f.getAll("attachments"),
              });
              setSent((n) => n + 1);
              setRound((n) => n + 1);
              onChange();
              window.dispatchEvent(new Event("houseos:message-sent"));
            }}
          >
            <Field label={t("Reply")}>
              <Textarea ref={body} name="body" required maxLength={10000} rows={2} />
            </Field>
            <div className="inbox-tools">
              <EmojiTray onPick={insertInto(body)} />
              <FilePicker />
            </div>
          </Form>
        </div>
      )}
    </div>
  );
}

// One sentence per kind of notice: French can't build "New" + a noun (its gender changes).
const NOTICES: Record<string, string> = {
  assignment: "New assignment",
  reminder: "New reminder",
  reminder_catchup: "Missed reminder",
  budget: "Nox is close to its budget",
};

function NewMessage({
  people,
  onSent,
  onClose,
}: {
  people: Obj[];
  onSent: () => Promise<void>;
  onClose: () => void;
}) {
  const body = useRef<HTMLTextAreaElement>(null);
  const [search, setSearch] = useState("");
  // "Message Sam" from elsewhere (Home's who's-home) opens this with Sam already picked.
  const [to] = useState(() => new URLSearchParams(location.search).get("to") || "");
  // Below the notices on a phone: bring it into view, ready to pick who (or to write, if picked).
  useEffect(() => {
    const box = document.getElementById("inbox-new");
    box?.scrollIntoView({ block: "start" });
    if (to) body.current?.focus({ preventScroll: true });
    else box?.querySelector("input")?.focus({ preventScroll: true });
  }, [to]);
  return (
    <Section
      id="inbox-new"
      title={t("Send a message")}
      actions={<IconButton icon="close" label={t("Conversations")} onClick={onClose} />}
    >
      <Form
        submit={t("Send message")}
        onSubmit={async (f) => {
          if (!f.getAll("recipient_ids").length) throw new Error(t("Choose who to send it to."));
          await create("messages", {
            title: String(f.get("title") || ""),
            body: String(f.get("body") || ""),
            recipient_ids: f.getAll("recipient_ids"),
            attachments: f.getAll("attachments"),
          });
          window.dispatchEvent(new Event("houseos:message-sent"));
          await onSent();
        }}
      >
        <SearchInput label={t("Find a housemate")} value={search} onChange={setSearch} />
        <PeopleChips
          name="recipient_ids"
          label={t("Send to")}
          people={people}
          search={search}
          initial={to && people.some((p) => p.id === to) ? [to] : []}
        />
        <Field label={t("Subject")}>
          <Input name="title" maxLength={160} />
        </Field>
        <Field label={t("Message")}>
          <Textarea ref={body} name="body" required maxLength={10000} rows={4} />
        </Field>
        <div className="inbox-tools">
          <EmojiTray onPick={insertInto(body)} />
          <FilePicker />
        </div>
      </Form>
    </Section>
  );
}

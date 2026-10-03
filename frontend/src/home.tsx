import { t } from "./i18n";
import { useState } from "react";
import { VoiceButton } from "./voice";
import { api, date, useData, useUser, items, idempotency, type Obj } from "./api";
import { go } from "./nav";
import { Music, MusicPanel } from "./music";
import { WatchPanel } from "./watch";
import { useCinemaCurrent } from "./cinema";
import { dayKey, WallFeed } from "./household";
import {
  useHouseStats,
  NoxSays,
  MusicStats,
  Djs,
  TopSongs,
  ListenClock,
  FilmStats,
  Titles,
  GenreRing,
} from "./house_stats";
import {
  Avatar,
  Button,
  Checkbox,
  ConfirmSheet,
  Icon,
  type IconName,
  IconButton,
  Input,
  List,
  ListRow,
  Mascot,
  Notice,
  Page,
  Panel,
  Popover,
  Problem,
  QuickAdd,
  Slot,
  Text,
  ThemeLayers,
  Tile,
  tone,
} from "./design";
import "./home.css";

function greeting(date = new Date()) {
  const hour = date.getHours();
  return hour < 5
    ? "Good night"
    : hour < 12
      ? "Good morning"
      : hour < 18
        ? "Good afternoon"
        : "Good evening";
}

/** How many faces the greeting shows before "+N". */
const FACES = 6;

/** The house's dashboard: who is home, what plays, what today asks, the wall, and the house's
 *  numbers and titles, each a panel that opens its place. */
export function Home({
  guest = false,
  assistant = false,
}: {
  guest?: boolean;
  assistant?: boolean;
}) {
  const user = useUser();
  const people = useData(guest ? null : "/people", { interval: 30000 });
  if (guest)
    return (
      <Page>
        <header className="home-hero">
          <ThemeLayers where="hero" under />
          <Slot
            id="home.hero.backdrop"
            className="home-hero__scene"
            width={240}
            height={72}
            lit={1}
          />
          <ThemeLayers where="hero" />
          <div className="home-hero__words">
            <p className="home-hero__kicker">{t("You’re on the guest list")}</p>
            <h1>{t("Bring a little music.")}</h1>
          </div>
          {user?.permissions?.includes("cinema.use") && (
            <div className="home-hero__actions">
              <Button variant="primary" icon="tv" onClick={() => go("/watch")}>
                {t("Pick a film for the TV")}
              </Button>
            </div>
          )}
        </header>
        <Music />
      </Page>
    );
  // Everyone who lives here, those at home first.
  const everyone = [...items(people.data)].sort((a, b) => Number(!!b.home) - Number(!!a.home));
  const home = everyone.filter((person) => person.home);
  const first = String(user?.name || "").split(" ")[0];
  return (
    <Page>
      <header className="home-hero">
        <ThemeLayers where="hero" under />
        <Slot
          id="home.hero.backdrop"
          className="home-hero__scene"
          width={240}
          height={72}
          lit={Math.max(1, home.length)}
        />
        <ThemeLayers where="hero" />
        <div className="home-hero__words">
          <p className="home-hero__kicker">
            {date(Date.now(), { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <h1>
            {t(greeting())}
            {first && ", " + first}
          </h1>
          <Digest />
          {/* Beside who's home, so the row under the words stays clear of the picture. */}
          <div className="home-hero__people">
            {everyone.length > 0 && <Who everyone={everyone} me={user?.id} />}
            <Button
              className="home-hero__send"
              variant="quiet"
              size="s"
              icon="send"
              onClick={() => go("/capture")}
            >
              {t("Send something home")}
            </Button>
          </div>
        </div>
        {assistant && (
          <div className="home-hero__actions">
            <AskBar />
          </div>
        )}
      </header>
      {user?.role === "admin" && <SetupRow />}
      <Board />
    </Page>
  );
}

/** Who's home right now, as faces (nobody away: that isn't news). A click opens everyone, with a
 *  message for each, and for an admin a way to sign someone out of every device. */
function Who({ everyone, me }: { everyone: Obj[]; me?: string }) {
  const user = useUser();
  const [out, setOut] = useState<Obj | null>(null);
  const name = (person: Obj) => (person.id === me ? t("You") : person.name);
  const home = everyone.filter((person) => person.home);
  const words =
    home.length > 1
      ? t("{n} at home").replace("{n}", String(home.length))
      : home.length && home[0].id === me
        ? t("Just you at home")
        : t("Nobody else at home");
  return (
    <div className="home-who">
      <Popover
        label={t("Who is around")}
        trigger={
          <>
            <span className="home-who__faces" aria-hidden="true">
              {home.slice(0, FACES).map((person) => (
                <Avatar
                  key={person.id}
                  name={name(person)}
                  picture={person.avatar}
                  tone={tone(person.id)}
                  home
                  size="s"
                />
              ))}
            </span>
            <span>{words}</span>
          </>
        }
      >
        {(close) => (
          <List label={t("Who is around")}>
            {everyone.map((person) => (
              <ListRow
                key={person.id}
                leading={
                  <Avatar
                    name={name(person)}
                    picture={person.avatar}
                    tone={tone(person.id)}
                    home={!!person.home}
                    size="s"
                  />
                }
                title={name(person)}
                detail={t(person.home ? "Online now" : "Away")}
                actions={
                  person.id !== me && (
                    <>
                      <IconButton
                        icon="message"
                        size="s"
                        label={t("Message {name}").replace("{name}", person.name)}
                        onClick={() => {
                          close();
                          go("/inbox?with=new&to=" + encodeURIComponent(person.id));
                        }}
                      />
                      {user?.role === "admin" && (
                        <IconButton
                          icon="log-out"
                          size="s"
                          label={t("Sign {name} out everywhere").replace("{name}", person.name)}
                          onClick={() => {
                            close();
                            setOut(person);
                          }}
                        />
                      )}
                    </>
                  )
                }
              />
            ))}
          </List>
        )}
      </Popover>
      {out && (
        <ConfirmSheet
          title={t("Sign {name} out everywhere?").replace("{name}", out.name)}
          confirm={t("Sign out")}
          danger
          onConfirm={() => api("/admin/users/" + out.id + "/sign-out", "POST")}
          onClose={() => setOut(null)}
        >
          <Text>
            {t(
              "Every device they use asks for their password again. Nothing of theirs is deleted.",
            )}
          </Text>
        </ConfirmSheet>
      )}
    </div>
  );
}

/** Nox, the house manager, one line away: type or talk, and the answer opens in Nox. */
function AskBar() {
  const [text, setText] = useState("");
  const send = (message: string, source: "text" | "voice" = "text") => {
    if (!message.trim()) return;
    dispatchEvent(new CustomEvent("houseos:ask", { detail: { message: message.trim(), source } }));
    setText("");
  };
  return (
    <form
      className="home-ask"
      onSubmit={(e) => {
        e.preventDefault();
        send(text);
      }}
    >
      <Mascot size="s" />
      <Input
        aria-label={t("Ask Nox, your house manager")}
        placeholder={t("Ask Nox, your house manager…")}
        value={text}
        maxLength={2000}
        onChange={(e) => setText(e.target.value)}
      />
      <VoiceButton
        onText={(words, confident) =>
          confident && !text.trim()
            ? send(words, "voice")
            : setText((current) => (current ? current + " " : "") + words)
        }
      />
      <IconButton
        type="submit"
        icon="up"
        variant="primary"
        label={t("Send to Nox")}
        disabled={!text.trim()}
      />
    </form>
  );
}

/** One row for an admin while the house's essentials aren't all ready; hidden on this device
 *  once dismissed (the checklist stays in the Control Room). */
function SetupRow() {
  const key = "houseos.setup-row.hidden";
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
    }
  });
  const setup = useData<Obj>(hidden ? null : "/admin/setup");
  if (hidden || !setup.data || setup.data.done >= setup.data.needed) return null;
  return (
    <Notice
      title={setup.data.done + " / " + setup.data.needed + " " + t("essentials ready")}
      action={
        <Button size="s" iconEnd="forward" onClick={() => go("/control?tab=setup")}>
          {t("Continue setting up the house")}
        </Button>
      }
      onDismiss={() => {
        setHidden(true);
        try {
          localStorage.setItem(key, "1");
        } catch {
          // private window: hidden until the page closes
        }
      }}
    >
      {t("A few steps make everything work. Each one can wait.")}
    </Notice>
  );
}

/** While a film plays: what, and one tap to its controls in the Now sheet. */
function OnTheTv() {
  const cinema = useCinemaCurrent();
  const movie = cinema.error ? null : cinema.data?.current;
  if (!movie) return null;
  return (
    <Tile
      icon="tv"
      title={t(movie.phase ? "Starting on the TV" : "On the TV")}
      value={movie.title}
      detail={
        t(movie.state === "paused" ? "Paused" : "Playing") +
        (movie.device ? " · " + movie.device : "")
      }
      onOpen={() => dispatchEvent(new Event("houseos:now"))}
    />
  );
}

/** The dashboard: the day's band (what plays, today, what to watch), the numbers across, then the
 *  rest in flowing columns (see home.css). */
function Board() {
  const stats = useHouseStats();
  const data = stats.data;
  return (
    <div className="home-board">
      {/* Wide screens: what plays in one column (the deck and the next songs make it tall), the
          day's lists and what to watch in the other, each stacked at its own height (home.css). */}
      <div className="home-band">
        <div className="home-band__col">
          <Panel className="home-now" icon="music" title={t("Now playing")} href="/listen">
            <OnTheTv />
            <MusicPanel />
          </Panel>
        </div>
        <div className="home-band__col">
          <Groceries />
          <WatchPanel />
          <Today />
        </div>
      </div>
      <Panel
        className="home-numbers"
        icon="sparkles"
        title={t("The house in numbers")}
        href="/house?tab=numbers"
      >
        {data ? (
          <>
            <NoxSays data={data} />
            {/* The numbers and who plays at the left, what the house listens to as a ring. */}
            <div
              className="home-numbers__grid"
              data-ring={data.music.genres?.length > 0 || undefined}
            >
              <div className="home-numbers__main">
                <MusicStats music={data.music} />
                <Djs music={data.music} />
              </div>
              {data.music.genres?.length > 0 && (
                <div className="stats__block">
                  <Text as="h3" style="label">
                    {t("What the house listens to")}
                  </Text>
                  <GenreRing genres={data.music.genres} label={t("Time listened by genre")} />
                </div>
              )}
            </div>
          </>
        ) : (
          <Problem error={stats.error} onRetry={stats.reload} />
        )}
      </Panel>
      {/* Three columns that each stack their own panels (no shared rows, so no gaps under a
          short one); on narrower screens the columns dissolve into one grid (home.css). */}
      <div className="home-more">
        <div className="home-more__col">
          <Panel
            className="home-titles"
            icon="star"
            title={t("House titles")}
            href="/house?tab=numbers"
          >
            {data && <Titles data={data} compact />}
          </Panel>
        </div>
        <div className="home-more__col">
          <Panel className="home-wall" icon="pin" title={t("Wall")} href="/house?tab=board">
            <WallFeed pageSize={4} compact />
          </Panel>
          {data && (
            <Panel className="home-clock" icon="clock" title={t("When the house listens")}>
              <ListenClock music={data.music} />
            </Panel>
          )}
        </div>
        <div className="home-more__col">
          {data && data.music.top_songs.length > 0 && (
            <Panel
              className="home-top"
              icon="headphones"
              title={t("Top songs")}
              href="/house?tab=numbers"
            >
              <TopSongs music={data.music} limit={5} />
            </Panel>
          )}
          {data && (
            <Panel className="home-films" icon="film" title={t("Film nights")} href="/watch">
              <FilmStats block={data.movies?.month || {}} />
              {data.movies?.month?.genres?.length > 0 && (
                <GenreRing genres={data.movies.month.genres} label={t("Time watched by genre")} />
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

/** A group's head inside a panel: what, how many, and a link to its place. */
function GroupHead({
  icon,
  label,
  count,
  href,
}: {
  icon: IconName;
  label: string;
  count: string;
  href: string;
}) {
  return (
    <a
      className="home-group"
      href={href}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey) return;
        e.preventDefault();
        go(href);
      }}
    >
      <Icon name={icon} size="s" />
      <span>{label}</span>
      <b>{count}</b>
    </a>
  );
}

// `more`: only the first 100 were read, so "100+" rather than a wrong exact number.
const count = (n: number, one: string, many: string, more = false, none = "Nothing") =>
  n || more ? t(n === 1 && !more ? one : many).replace("{n}", n + (more ? "+" : "")) : t(none);

/** Under the greeting: what's waiting, in one line (each part opens its place). The same reads
 *  as the panels below, so it costs nothing. */
function Digest() {
  const user = useUser();
  const admin = user?.role === "admin";
  const prefs = useData("/preferences");
  const zone = prefs.data?.timezone || "UTC";
  const day = dayKey(new Date(), zone);
  const week = dayKey(new Date(Date.now() + 6 * 86400000), zone);
  const agenda = useData(
    prefs.data || prefs.error ? "/household/calendar/agenda?start=" + day + "&end=" + week : null,
  );
  const tasks = useData("/household/tasks?state=open&limit=100");
  const groceries = useData("/household/groceries?state=open&limit=100");
  const inbox = useData("/household/inbox?unread=true&limit=50");
  const doubles = useData<Obj>(admin ? "/files/library/duplicates" : null);
  const next = items(agenda.data)[0];
  const when = (value: string) =>
    String(value).slice(0, 10) <= day
      ? value.length > 10
        ? date(value, { hour: "2-digit", minute: "2-digit" })
        : t("today")
      : date(value.length > 10 ? value : value + "T12:00:00", { weekday: "long" });
  const mine = items(tasks.data).filter(
    (task) =>
      (task.data.assignee_id === user?.id || !task.data.assignee_id) &&
      (!task.data.due_date || task.data.due_date <= day),
  ).length;
  const parts: [string, string][] = [
    ...(next
      ? [
          [
            t("{what}, {when}")
              .replace("{what}", next.title)
              .replace("{when}", when(String(next.start))),
            "/house?tab=calendar",
          ] as [string, string],
        ]
      : []),
    ...(mine
      ? [
          [
            count(mine, "1 task for you", "{n} tasks for you", !!tasks.data?.has_more),
            "/house?tab=tasks",
          ] as [string, string],
        ]
      : []),
    ...((groceries.data?.total ?? items(groceries.data).length)
      ? [
          [
            count(
              groceries.data?.total ?? items(groceries.data).length,
              "1 grocery to buy",
              "{n} groceries to buy",
            ),
            "/house?tab=groceries",
          ] as [string, string],
        ]
      : []),
    ...(items(inbox.data).length
      ? [
          [
            count(items(inbox.data).length, "1 unread message", "{n} unread messages"),
            "/inbox",
          ] as [string, string],
        ]
      : []),
    ...(Number(doubles.data?.count) > 0
      ? [
          [
            count(
              Number(doubles.data?.count),
              "1 possible duplicate song",
              "{n} possible duplicate songs",
            ),
            "/files?scope=music",
          ] as [string, string],
        ]
      : []),
  ];
  if (!parts.length) return null; // nothing waiting: no line at all
  return (
    <p className="home-hero__tagline home-digest">
      {parts.map(([text, path], index) => (
        <span key={path}>
          {index > 0 && " · "}
          <a
            href={path}
            onClick={(e) => {
              e.preventDefault();
              go(path);
            }}
          >
            {text}
          </a>
        </span>
      ))}
    </p>
  );
}

/** Today: plans and my tasks, each opening its place. A task is finished right here. */
function Today() {
  const user = useUser();
  // The resident's day, as the House calendar counts it.
  const prefs = useData("/preferences");
  const day = dayKey(new Date(), prefs.data?.timezone || "UTC");
  // Today and the week ahead in one read: today's plans first, then what's coming.
  const week = dayKey(new Date(Date.now() + 6 * 86400000), prefs.data?.timezone || "UTC");
  const agenda = useData(
    prefs.data || prefs.error ? "/household/calendar/agenda?start=" + day + "&end=" + week : null,
  );
  const tasks = useData("/household/tasks?state=open&limit=100");
  const events = items(agenda.data).filter((event) => String(event.start).slice(0, 10) <= day);
  const coming = items(agenda.data).filter((event) => String(event.start).slice(0, 10) > day);
  const weekday = (value: string) =>
    date(value.length > 10 ? value : value + "T12:00:00", { weekday: "short", day: "numeric" });
  const mine = items(tasks.data).filter(
    (task) =>
      (task.data.assignee_id === user?.id || !task.data.assignee_id) &&
      (!task.data.due_date || task.data.due_date <= day),
  );
  const time = (value: string) =>
    value.length > 10 ? date(value, { hour: "2-digit", minute: "2-digit" }) : t("All day");
  return (
    <Panel className="home-today" icon="calendar" title={t("Today")}>
      <GroupHead
        icon="calendar"
        label={t("Calendar")}
        count={count(events.length, "{n} plan", "{n} plans")}
        href={"/house?tab=calendar&date=" + day}
      />
      {events.length > 0 && (
        <List label={t("Calendar")}>
          {events.slice(0, 3).map((event) => (
            <ListRow
              key={event.id + event.start}
              title={event.title}
              meta={event.all_day ? t("All day") : time(event.start)}
            />
          ))}
        </List>
      )}
      <GroupHead
        icon="list-todo"
        label={t("Tasks")}
        count={count(mine.length, "{n} for you", "{n} for you", !!tasks.data?.has_more)}
        href="/house?tab=tasks"
      />
      {mine.length > 0 && (
        <List label={t("Tasks")}>
          {mine.slice(0, 4).map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              late={task.data.due_date < day}
              onDone={tasks.reload}
            />
          ))}
        </List>
      )}
      {coming.length > 0 && (
        <>
          <GroupHead
            icon="clock"
            label={t("This week")}
            count={count(coming.length, "{n} plan", "{n} plans")}
            href={"/house?tab=calendar&date=" + day}
          />
          <List label={t("This week")}>
            {coming.slice(0, 4).map((event) => (
              <ListRow
                key={event.id + event.start}
                title={event.title}
                meta={weekday(String(event.start))}
              />
            ))}
          </List>
        </>
      )}
      <Problem error={agenda.error || tasks.error} />
    </Panel>
  );
}

/** The groceries: tick what's bought, add what's missing. */
function Groceries() {
  const groceries = useData("/household/groceries?state=open&limit=100");
  const [error, setError] = useState("");
  const list = items(groceries.data);
  const bought = async (row: Obj) => {
    try {
      await api("/household/groceries/" + row.id, "PATCH", {
        version: row.version,
        data: { purchased: true },
      });
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
    await groceries.reload();
  };
  return (
    <Panel
      className="home-groceries"
      icon="basket"
      title={t("Groceries")}
      href="/house?tab=groceries"
    >
      <Text style="body-s" tone="muted">
        {count(groceries.data?.total ?? list.length, "{n} to buy", "{n} to buy", false, "Empty")}
      </Text>
      {list.length > 0 && (
        <List label={t("Groceries")}>
          {list.slice(0, 5).map((row) => (
            <ListRow
              key={row.id}
              leading={
                <Checkbox
                  hideLabel
                  label={t("Bought") + " · " + row.data.label}
                  onChange={() => void bought(row)}
                />
              }
              title={row.data.label}
              meta={row.data.quantity ? "×" + row.data.quantity : undefined}
            />
          ))}
        </List>
      )}
      <QuickAdd
        label={t("Add to the groceries")}
        placeholder={t("Milk, eggs…")}
        onAdd={async (label) => {
          await api("/household/groceries", "POST", {
            data: { label },
            idempotency_key: idempotency(),
          });
          await groceries.reload();
        }}
      />
      <Problem error={error || groceries.error} />
    </Panel>
  );
}

/** A task of mine: tap the circle, confirm, and it moves to Done (Reopen brings it back). */
function TaskRow({ task, late, onDone }: { task: Obj; late: boolean; onDone: () => unknown }) {
  const [asking, setAsking] = useState(false),
    [error, setError] = useState("");
  const complete = async () => {
    try {
      await api("/household/tasks/" + task.id + "/action", "POST", {
        version: task.version,
        action: "complete",
      });
      setAsking(false);
      await onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <ListRow
      leading={
        <IconButton
          icon="check"
          size="s"
          variant={asking ? "primary" : "secondary"}
          className="task-check"
          label={(asking ? t("Yes, done") : t("Mark done")) + " · " + task.data.title}
          onClick={() => (asking ? void complete() : setAsking(true))}
        />
      }
      title={task.data.title}
      detail={asking ? t("Done?") : late ? t("late") : undefined}
      actions={
        asking && (
          <Button size="s" variant="quiet" onClick={() => setAsking(false)}>
            {t("Not yet")}
          </Button>
        )
      }
    >
      {error && <Problem error={error} />}
    </ListRow>
  );
}

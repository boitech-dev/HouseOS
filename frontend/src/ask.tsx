import { t, getLanguage } from "./i18n";
import { useState, useEffect, useLayoutEffect, useRef, type CSSProperties } from "react";
import { go } from "./nav";
import {
  api,
  ApiError,
  useData,
  useUser,
  items,
  percent,
  pretty,
  idempotency,
  time,
  type Obj,
} from "./api";
import {
  Badge,
  Button,
  Checkbox,
  ConfirmSheet,
  Icon,
  IconButton,
  type IconName,
  LinkButton,
  List,
  ListRow,
  Mascot,
  Media,
  Notice,
  Page,
  PageHeader,
  Problem,
  ReviewDetails,
  Status,
  Surface,
  Text,
  FileButton,
  Spinner,
  Textarea,
  ThemeSpecimen,
  Tile,
  toast,
  type Tone,
} from "./design";
import { allThemes, apply, reapply, useInstalled } from "./design/theme";
import type { Scheme, ThemeInfo } from "./design/generated/themes";
import "./ask.css";
import { VoiceButton, type VoiceState } from "./voice";

/** Ready-made requests. Three are answered by HouseOS itself (no AI, no cost); "watch"
 *  starts a short conversation with Nox. The server knows each by its id. */
const PRESETS = [
  {
    id: "tour",
    icon: "compass",
    title: "How does the house work?",
    hint: "A quick guided tour of every room",
    code: true,
  },
  {
    id: "favorites",
    icon: "music",
    title: "Play our favourite songs",
    hint: "10 random picks from the house's most played",
    code: true,
  },
  {
    id: "watch",
    icon: "film",
    title: "Help me find something to watch",
    hint: "A little chat, then 10 ideas with posters",
    code: false,
  },
  {
    id: "week",
    icon: "calendar",
    title: "What is planned this week?",
    hint: "Closest first, and what's worth knowing later",
    code: true,
  },
] as const satisfies readonly {
  id: string;
  icon: IconName;
  title: string;
  hint: string;
  code: boolean;
}[];
/** Setup mode's welcome: a plain message; the setup prompt starts from the checklist. */
const SETUP_PRESETS = [
  {
    id: "setup",
    icon: "wrench",
    title: "Help me set up the house",
    hint: "Nox checks what is done and takes you through the rest, one step at a time",
    code: false,
  },
] as const satisfies readonly {
  id: string;
  icon: IconName;
  title: string;
  hint: string;
  code: boolean;
}[];

/** The theme studio's openings: plain messages, Nox takes it from there. */
const THEMES_PRESETS = [
  {
    id: "theme_questions",
    icon: "list-todo",
    title: "Start with 5 quick questions",
    hint: "Answer in a line each; then three directions to choose from",
    code: true,
  },
  {
    id: "surprise",
    icon: "sparkles",
    title: "Surprise me",
    hint: "Three directions Nox thinks would suit this house",
    code: false,
  },
  {
    id: "photo",
    icon: "image",
    title: "From a photo",
    hint: "Add a picture below: a room, a place, a poster, a fabric",
    code: false,
  },
  {
    id: "place",
    icon: "compass",
    title: "From a place or an era",
    hint: "A café in Lisbon, a 70s living room, a greenhouse at dusk…",
    code: false,
  },
] as const satisfies readonly {
  id: string;
  icon: IconName;
  title: string;
  hint: string;
  code: boolean;
}[];
export type Purpose = "general" | "personal_space" | "setup" | "themes";

/** Nox, the house familiar, shows what the assistant is doing. */
type Mood = "idle" | "listening" | "thinking" | "happy" | "error";
const MOOD_WORDS: Record<Mood, string> = {
  idle: "Nox is here.",
  listening: "Nox is listening…",
  thinking: "Nox is thinking…",
  happy: "Done.",
  error: "Something went wrong.",
};
function Familiar({ state }: { state: Mood }) {
  const words = MOOD_WORDS[state];
  return (
    <div className="ask-familiar" data-mood={state} aria-hidden="true">
      <Mascot mood={state} size="l" />
      <Text style="label" tone="muted">
        {t(words)}
      </Text>
    </div>
  );
}
// Bold, italics, code, links and in-app paths. No regex lookbehind: Safari before 16.4 cannot
// parse one and the whole app would stay blank, so an in-app path right after a letter or a
// slash is skipped here instead (same parts as `line.split` with a lookbehind would give).
const RICH =
  /\*\*[^*]+\*\*|\*[^*\s][^*]*\*|_[^_\s][^_]*_|`[^`]+`|https?:\/\/[^\s<>]+[^\s<>.,;:!?)]|\/(?:watch|listen|files|house|me)\b[^\s]*/g;
function richParts(line: string) {
  const parts: string[] = [];
  let last = 0;
  RICH.lastIndex = 0;
  for (let m; (m = RICH.exec(line));) {
    if (m[0][0] === "/" && /[\w/]/.test(line[m.index - 1] ?? "")) {
      RICH.lastIndex = m.index + 1;
      continue;
    }
    parts.push(line.slice(last, m.index), m[0]);
    last = RICH.lastIndex;
  }
  parts.push(line.slice(last));
  return parts;
}
export function RichText({ text, className = "ask-text" }: { text: string; className?: string }) {
  // React escapes all content; only small, predictable formatting and links, never raw HTML.
  return (
    <div className={className}>
      {text.split("\n").map((line, i) => (
        <p key={i}>
          {richParts(line).map((part, j) =>
            part.startsWith("**") && part.endsWith("**") ? (
              <strong key={j}>{part.slice(2, -2)}</strong>
            ) : /^(\*|_).+\1$/.test(part) ? (
              <em key={j}>{part.slice(1, -1)}</em>
            ) : part.startsWith("`") && part.endsWith("`") ? (
              <code key={j}>{part.slice(1, -1)}</code>
            ) : /^https?:\/\//.test(part) ? (
              <a key={j} href={part} target="_blank" rel="noopener noreferrer">
                {part}
              </a>
            ) : part.startsWith("/") ? (
              <a
                key={j}
                href={part}
                onClick={(e) => {
                  e.preventDefault();
                  go(part);
                }}
              >
                {part}
              </a>
            ) : (
              part
            ),
          )}
        </p>
      ))}
    </div>
  );
}
const AssistantText = RichText;
const pendingChats = new Map<string, { message: string; error?: string }>();
const chatErrors = new Map<string, string>();
const chatChanged = () => window.dispatchEvent(new Event("houseos:chat"));

export function Assistant({
  quick = false,
  purpose: initialPurpose = "general",
  initialDraft = "",
  initialThread,
  onAction,
  autoSend = false,
  autoSource = "text",
  autoPreset,
}: {
  autoSend?: boolean;
  /** Run this code preset as the opening message (the tour: no AI needed). */
  autoPreset?: string;
  autoSource?: "text" | "voice";
  quick?: boolean;
  purpose?: Purpose;
  initialDraft?: string;
  initialThread?: string | null;
  onAction?: () => void;
}) {
  // Admins can switch the Nox page to setup mode: its own conversations, model and tools.
  const admin = useUser()?.role === "admin";
  const [purpose, setPurpose] = useState<Purpose>(() =>
    admin &&
    !quick &&
    location.pathname === "/assistant" &&
    new URLSearchParams(location.search).get("mode") === "setup"
      ? "setup"
      : initialPurpose,
  );
  const home = purpose === "setup" ? "/assistant?mode=setup" : "/assistant";
  const at = (id: string) =>
    home + (purpose === "setup" ? "&" : "?") + "conversation=" + encodeURIComponent(id);
  const [message, setMessage] = useState(""),
    [thread, setThread] = useState<string | null>(() => {
      // The page's conversation, never one of another mode (setup mode's sheet over the page).
      const url = new URLSearchParams(location.search);
      const page = url.get("mode") === "setup" ? "setup" : "general";
      return (
        initialThread ||
        (quick || location.pathname !== "/assistant" || page !== purpose
          ? null
          : url.get("conversation"))
      );
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [voiceState, setVoiceState] = useState<VoiceState>("idle"),
    [showList, setShowList] = useState(
      () => !quick && location.pathname === "/assistant" && innerWidth >= 900,
    ),
    [cheer, setCheer] = useState(false),
    [pictures, setPictures] = useState<{ id: string; url: string }[]>([]),
    [adding, setAdding] = useState(false);
  // The studio's pictures: each one is sent to the house (downscaled there, no metadata kept).
  const addPictures = async (files: File[]) => {
    const chosen = files
      .filter((file) => file.type.startsWith("image/"))
      .slice(0, 4 - pictures.length);
    if (!chosen.length) return;
    setAdding(true);
    try {
      for (const file of chosen) {
        const body = new FormData();
        body.append("file", file);
        const added = await api("/assistant/attachments", "POST", body);
        setPictures((current) => [
          ...current,
          { id: added.id, url: "/api/v1/assistant/attachments/" + added.id },
        ]);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdding(false);
    }
  };
  useEffect(() => {
    if (initialThread) setThread(initialThread);
  }, [initialThread]);
  const [, refreshPending] = useState(0);
  useEffect(() => {
    const changed = () => refreshPending((v) => v + 1);
    window.addEventListener("houseos:chat", changed);
    return () => window.removeEventListener("houseos:chat", changed);
  }, []);
  const [deleteThread, setDeleteThread] = useState(false),
    [deleteMemories, setDeleteMemories] = useState(false);
  const status = useData("/assistant/status?purpose=" + purpose);
  const actorId = status.data?.actor_id;
  const threadKey = actorId && thread ? actorId + ":" + thread : null;
  const pending = threadKey ? pendingChats.get(threadKey) : undefined;
  useEffect(() => {
    if (initialDraft) setMessage(initialDraft);
  }, [initialDraft]);
  // A message typed elsewhere (the Home bar) is sent as soon as the assistant is ready.
  const autoSent = useRef(false);
  useEffect(() => {
    if (!autoSend || autoSent.current || !initialDraft || !actorId) return;
    if (!status.data?.available && !autoPreset) return; // a code preset needs no AI
    if (message !== initialDraft) return;
    autoSent.current = true;
    setMessage("");
    void send(initialDraft, autoPreset ? { preset: autoPreset } : { source: autoSource });
  }, [autoSend, initialDraft, actorId, status.data?.available, message]);
  const composer = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  // While a reply is pending, the thread polls every second (shared cache, paused when hidden).
  // The list needs no poll: the assistant.updated event and houseos:chat refresh it.
  const messages = useData(
    thread ? "/assistant/conversations/" + thread + "?offset=0&limit=50" : null,
    { interval: (data) => (!!pending || !!data?.pending) && 1000 },
  );
  const conversations = useData(
    quick ? null : "/assistant/conversations?offset=0&limit=30&purpose=" + purpose,
  );
  const [olderThreads, setOlderThreads] = useState<Obj[]>([]),
    [olderMessages, setOlderMessages] = useState<Obj[]>([]),
    [threadOffset, setThreadOffset] = useState<number | null>(null),
    [messageOffset, setMessageOffset] = useState<number | null>(null),
    [loadingOlder, setLoadingOlder] = useState(false);
  useEffect(() => {
    setOlderThreads([]);
    setThreadOffset(conversations.data?.next_offset ?? null);
  }, [conversations.data]);
  useEffect(() => {
    setOlderMessages([]);
    setMessageOffset(null);
  }, [thread]);
  useEffect(() => {
    setMessageOffset(
      messages.data?.next_offset == null ? null : messages.data.next_offset + olderMessages.length,
    );
  }, [messages.data]);
  const visibleThreads = [...items(conversations.data), ...olderThreads].filter(
    (value, index, array) => array.findIndex((t) => t.id === value.id) === index,
  );
  useEffect(() => {
    if (!thread) return;
    const update = () => {
      void messages.reload();
      void conversations.reload();
    };
    window.addEventListener("houseos:chat", update);
    return () => window.removeEventListener("houseos:chat", update);
  }, [thread, messages.reload, conversations.reload]);
  const inFlight = busy || !!pending || !!messages.data?.pending;
  // A short happy flutter when a reply lands.
  const wasInFlight = useRef(false);
  useEffect(() => {
    if (wasInFlight.current && !inFlight) {
      setCheer(true);
      const id = setTimeout(() => setCheer(false), 2400);
      wasInFlight.current = inFlight;
      return () => clearTimeout(id);
    }
    wasInFlight.current = inFlight;
  }, [inFlight]);
  const mood =
    voiceState === "listening"
      ? "listening"
      : voiceState === "transcribing" || inFlight
        ? "thinking"
        : voiceState === "error" || error
          ? "error"
          : cheer
            ? "happy"
            : "idle";
  const visibleMessages = [
    ...olderMessages,
    ...items(messages.data?.messages || messages.data),
  ].filter(
    (value, index, array) => !value.id || array.findIndex((t) => t.id === value.id) === index,
  );
  // Classic chat scrolling, inside the conversation only (never the page or the list):
  // after your message, down to it; when a reply lands, to the reply's first line so you
  // read it from the top. Polls that change nothing never move you.
  const lastSeen = useRef("");
  useEffect(() => {
    const box = end.current?.parentElement;
    if (!thread || !box) return;
    const all = box.querySelectorAll<HTMLElement>(".ask-message");
    const last = all[all.length - 1];
    const key = thread + ":" + all.length + ":" + (last?.dataset.role || "");
    if (!last || key === lastSeen.current) return;
    lastSeen.current = key;
    if (last.dataset.role === "user") box.scrollTop = box.scrollHeight;
    else box.scrollTop += last.getBoundingClientRect().top - box.getBoundingClientRect().top - 8;
  }, [messages.data, pending, thread]);
  /** One path for typed messages, voice and presets. */
  const send = async (sent: string, extra: Obj = {}) => {
    if (inFlight || !sent || !actorId) return;
    setError("");
    setBusy(true);
    let identity = thread;
    try {
      if (!identity) {
        const created = await api("/assistant/conversations", "POST", {
          title: sent.slice(0, 80),
          purpose,
        });
        identity = created.id;
        setThread(identity);
      }
      const destination = identity!;
      const requestKey = actorId + ":" + destination;
      chatErrors.delete(requestKey);
      pendingChats.set(requestKey, { message: sent });
      chatChanged();
      if (quick && purpose === "general") go(at(destination));
      else if (location.pathname === "/assistant") history.replaceState({}, "", at(destination));
      try {
        await api("/assistant/chat", "POST", {
          conversation_id: destination,
          message: sent,
          idempotency_key: idempotency(),
          purpose,
          ...extra,
        });
        onAction?.();
      } catch (failure) {
        chatErrors.set(requestKey, (failure as Error).message);
        setError((failure as Error).message);
        // Stored server outcome stays visible after navigation; no hidden retry of actions.
      } finally {
        pendingChats.delete(requestKey);
        chatChanged();
      }
    } catch (failure) {
      setError((failure as Error).message);
      if (!extra.preset) setMessage(sent);
    } finally {
      setBusy(false);
    }
  };
  const failure =
    error || (threadKey ? chatErrors.get(threadKey) : "") || messages.error || conversations.error;
  // Its own page (/assistant) has the room's header; the Nox sheet and My space keep the familiar.
  const root = useRef<HTMLDivElement>(null);
  const [inSheet, setInSheet] = useState(false);
  useLayoutEffect(() => setInSheet(!!root.current?.closest(".ds-sheet")), []);
  const page = !quick && initialPurpose === "general" && !inSheet;
  const setupBadge = purpose === "setup" && (
    <Badge tone="warning">
      <Icon name="wrench" size="s" /> {t("House setup")}
    </Badge>
  );
  // Several chats can share a title ("How does the house work?"): number the repeats, oldest 1.
  const repeats = new Map<string, number>();
  const titled = [...visibleThreads].reverse().map((conversation) => {
    const title = conversation.title || t("Conversation");
    const n = (repeats.get(title) || 0) + 1;
    repeats.set(title, n);
    return { conversation, title, n };
  });
  const threadTitle = (id: string) => {
    const row = titled.find((x) => x.conversation.id === id)!;
    return repeats.get(row.title)! > 1 ? row.title + " (" + row.n + ")" : row.title;
  };
  const tools = !quick && (
    <div className="ask__tools">
      {admin && initialPurpose === "general" && (
        <Button
          size="s"
          icon="wrench"
          pressed={purpose === "setup"}
          disabled={inFlight || loadingOlder}
          onClick={() => {
            const next = purpose === "setup" ? "general" : "setup";
            history.replaceState({}, "", next === "setup" ? "/assistant?mode=setup" : "/assistant");
            setPurpose(next);
            setThread(null);
            setMessage("");
            setError("");
          }}
        >
          {t("Setup mode")}
        </Button>
      )}
      <Button
        size="s"
        icon="add"
        disabled={busy || loadingOlder}
        onClick={() => {
          if (location.pathname === "/assistant") history.replaceState({}, "", home);
          setThread(null);
          setMessage("");
          setError("");
          setShowList(false);
          composer.current?.focus();
        }}
      >
        {t("New conversation")}
      </Button>
      <Button
        size="s"
        icon="history"
        aria-expanded={showList}
        onClick={() => setShowList(!showList)}
      >
        {t("Conversations")}
      </Button>
    </div>
  );
  const chat = (
    <div
      ref={root}
      className="ask"
      data-quick={quick || undefined}
      data-setup={purpose === "setup" || undefined}
      data-page={page || undefined}
    >
      {!quick && initialPurpose !== "themes" && !page && <h1 className="visually-hidden">Nox</h1>}
      <h2 className="visually-hidden">
        {quick ? t("What can the house do for you?") : t("Your chats")}
      </h2>
      {page ? (
        <PageHeader
          room="ask"
          title={
            <span className="ask__title">
              <span aria-hidden="true">
                <Mascot mood={mood} size="m" />
              </span>
              Nox
            </span>
          }
          lead={t(MOOD_WORDS[mood])}
          actions={
            <>
              {setupBadge}
              {tools}
            </>
          }
        />
      ) : (
        <header className="ask__head">
          <Familiar state={mood} />
          {setupBadge}
          {tools}
        </header>
      )}
      <div className="ask__body">
        {!quick && showList && (
          <nav className="ask__threads" aria-label={t("Conversations")}>
            <List label={t("Conversations")}>
              {visibleThreads.map((conversation) => (
                <ListRow
                  key={conversation.id}
                  selected={thread === conversation.id}
                  title={threadTitle(conversation.id)}
                  detail={time(conversation.updated_at || conversation.created_at)}
                  onOpen={
                    busy || loadingOlder
                      ? undefined
                      : () => {
                          if (location.pathname === "/assistant")
                            history.replaceState({}, "", at(conversation.id));
                          setThread(conversation.id);
                          if (innerWidth < 900) setShowList(false);
                          setError("");
                        }
                  }
                />
              ))}
            </List>
            {threadOffset !== null && (
              <Button
                size="s"
                variant="quiet"
                busy={loadingOlder}
                onClick={async () => {
                  setLoadingOlder(true);
                  try {
                    const page = await api(
                      "/assistant/conversations?offset=" +
                        threadOffset +
                        "&limit=30&purpose=" +
                        purpose,
                    );
                    setOlderThreads((previous) => [...previous, ...items(page)]);
                    setThreadOffset(page.next_offset ?? null);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setLoadingOlder(false);
                  }
                }}
              >
                {t("Load more conversations")}
              </Button>
            )}
          </nav>
        )}
        <section className="ask__chat" aria-label={t("Conversation")}>
          {thread && (
            <div className="ask__thread-tools">
              <Button
                size="s"
                variant="link"
                icon="trash"
                disabled={busy || loadingOlder}
                onClick={() => {
                  setDeleteThread(true);
                  setDeleteMemories(false);
                }}
              >
                {t("Delete this conversation")}
              </Button>
            </div>
          )}
          {deleteThread && (
            <ConfirmSheet
              title={t("Delete this conversation")}
              confirm={t("Delete this conversation")}
              danger
              onClose={() => setDeleteThread(false)}
              onConfirm={async () => {
                await api(
                  "/assistant/conversations/" +
                    thread +
                    "?delete_derived_memories=" +
                    deleteMemories,
                  "DELETE",
                );
                if (location.pathname === "/assistant") history.replaceState({}, "", home);
                setThread(null);
                await conversations.reload();
              }}
            >
              <Text>{t("Protected backups may retain deleted data until expiry.")}</Text>
              <Checkbox
                checked={deleteMemories}
                onChange={(e) => setDeleteMemories(e.target.checked)}
                label={t("Also delete memories explicitly saved from this conversation")}
              />
            </ConfirmSheet>
          )}
          <Problem error={failure} />
          {status.data &&
            !status.data.available &&
            (purpose === "themes" ? (
              <StudioGuide admin={admin} />
            ) : purpose === "setup" ? (
              <Notice
                tone="warning"
                action={
                  <Button size="s" onClick={() => go("/control?tab=ai")}>
                    {t("Connect an AI")}
                  </Button>
                }
              >
                {t(
                  "To help you, Nox first needs an AI. Connect one (a ChatGPT or Claude sign-in, a key, or your own model); the Setup checklist guides the rest meanwhile.",
                )}
              </Notice>
            ) : (
              <Status tone="warning">{t("The house assistant is not configured yet.")}</Status>
            ))}
          {(!quick || !!thread || !!pending) && (
            <div className="ask-messages">
              {thread && messageOffset !== null && (
                <Button
                  size="s"
                  variant="quiet"
                  icon="chevron-up"
                  disabled={loadingOlder || busy}
                  onClick={async () => {
                    setLoadingOlder(true);
                    try {
                      const page = await api(
                        "/assistant/conversations/" +
                          thread +
                          "?offset=" +
                          messageOffset +
                          "&limit=50",
                      );
                      setOlderMessages((previous) => [...items(page.messages), ...previous]);
                      setMessageOffset(page.next_offset ?? null);
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setLoadingOlder(false);
                    }
                  }}
                >
                  {t("Load earlier messages")}
                </Button>
              )}
              {!thread && (
                <div className="ask__start">
                  <Text tone="muted">
                    {t("Ask in your own words, or start with one of these:")}
                  </Text>
                  <ul className="ask__presets">
                    {(purpose === "setup"
                      ? SETUP_PRESETS
                      : purpose === "themes"
                        ? THEMES_PRESETS
                        : PRESETS
                    ).map((preset) => (
                      <li key={preset.id}>
                        <Tile
                          icon={preset.icon}
                          title=""
                          value={t(preset.title)}
                          detail={t(preset.hint)}
                          disabled={
                            inFlight || !actorId || (!preset.code && !status.data?.available)
                          }
                          onOpen={() =>
                            void send(
                              t(preset.title),
                              // Setup's and the studio's presets are words for the model, except
                              // the ones HouseOS answers itself (code: the studio's questions).
                              (purpose === "setup" || purpose === "themes") && !preset.code
                                ? {}
                                : { preset: preset.id },
                            )
                          }
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {visibleMessages.map((m: Obj, i: number) => (
                <article key={m.id || i} className="ask-message" data-role={m.role}>
                  <Text style="label" tone="muted">
                    {m.role === "user" ? t("YOU") : t("YOUR HOUSE")}
                  </Text>
                  <AssistantText text={String(m.content || m.text || "")} />
                  {m.cards?.map((card: Obj, j: number) => (
                    <ActionCard
                      key={j}
                      card={card}
                      onConfirmed={messages.reload}
                      onRefine={(text) => {
                        setMessage(text);
                        requestAnimationFrame(() => composer.current?.focus());
                      }}
                    />
                  ))}
                  {m.tools?.map((tool: Obj, j: number) => (
                    <Surface material="sunken" className="ask-card" key={j}>
                      <div className="ask-card__head">
                        <strong>{pretty(tool.name)}</strong>
                        <Status tone={stateTone(tool.status)}>
                          {t(pretty(tool.status || ""))}
                        </Status>
                      </div>
                      {tool.summary && <Text style="body-s">{tool.summary}</Text>}
                    </Surface>
                  ))}
                </article>
              ))}
              {pending &&
                !visibleMessages.some(
                  (m) => m.role === "user" && m.content === pending.message,
                ) && (
                  <article className="ask-message" data-role="user">
                    <Text style="label" tone="muted">
                      {t("YOU")}
                    </Text>
                    <AssistantText text={pending.message} />
                  </article>
                )}
              <div ref={end} />
            </div>
          )}
          {purpose === "themes" && (pictures.length > 0 || adding) && (
            <ul className="ask-pictures" aria-label={t("Pictures for Nox")}>
              {pictures.map((picture) => (
                <li key={picture.id}>
                  <img src={picture.url} alt="" />
                  <IconButton
                    size="s"
                    icon="close"
                    label={t("Remove this picture")}
                    onClick={() =>
                      setPictures((current) => current.filter((p) => p.id !== picture.id))
                    }
                  />
                </li>
              ))}
              {adding && (
                <li>
                  <Spinner label={t("Adding the picture…")} />
                </li>
              )}
            </ul>
          )}
          <form
            className="ask-composer"
            onDragOver={(e) => purpose === "themes" && e.preventDefault()}
            onDrop={(e) => {
              if (purpose !== "themes") return;
              e.preventDefault();
              void addPictures([...e.dataTransfer.files]);
            }}
            onSubmit={(e) => {
              e.preventDefault();
              const sent = message.trim();
              if (inFlight || !sent || !actorId) return;
              setMessage("");
              const attachments = pictures.map((picture) => picture.id);
              setPictures([]);
              void send(sent, attachments.length ? { attachments } : {});
            }}
          >
            <Textarea
              ref={composer}
              enterKeyHint="send"
              aria-label={quick ? t("Start a new chat") : t("Message your assistant")}
              placeholder={
                purpose === "themes"
                  ? t("A feeling, a place, a picture… or what to change.")
                  : purpose === "personal_space"
                    ? t("Configure your own space here.")
                    : purpose === "setup"
                      ? t("Ask about any step of the house setup…")
                      : quick
                        ? t("Add milk to groceries, find a movie, play some music…")
                        : t("Tell the house what you need…")
              }
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onPaste={(e) => {
                const files = [...e.clipboardData.files].filter((f) => f.type.startsWith("image/"));
                if (purpose !== "themes" || !files.length) return;
                e.preventDefault();
                void addPictures(files);
              }}
              onKeyDown={(e) => {
                if (
                  e.key !== "Enter" ||
                  e.shiftKey ||
                  e.nativeEvent.isComposing ||
                  e.nativeEvent.keyCode === 229
                )
                  return;
                e.preventDefault();
                if (!inFlight && !loadingOlder && message.trim() && status.data?.available)
                  e.currentTarget.form?.requestSubmit();
              }}
              rows={2}
              required
              maxLength={6000}
            />
            {purpose === "themes" && (
              <FileButton
                label={t("Add a picture")}
                iconOnly
                icon="image"
                variant="quiet"
                accept="image/jpeg,image/png,image/webp"
                multiple
                busy={adding}
                disabled={inFlight || pictures.length >= 4}
                onFiles={(files) => void addPictures(files)}
              />
            )}
            <VoiceButton
              disabled={inFlight}
              blocked={
                status.data && !status.data.available
                  ? t("Connect Nox to an AI first (Control Room → AI).")
                  : ""
              }
              onState={setVoiceState}
              onText={(text, confident) => {
                // Clear speech goes straight to Nox; unsure words wait in the box to check.
                if (confident && !message.trim()) return void send(text, { source: "voice" });
                setMessage((current) => (current.trim() ? current.trim() + " " : "") + text);
                requestAnimationFrame(() => composer.current?.focus());
              }}
            />
            <IconButton
              type="submit"
              icon="up"
              variant="primary"
              busy={inFlight}
              disabled={
                loadingOlder ||
                !message.trim() ||
                !actorId ||
                !status.data ||
                !status.data.available
              }
              label={t("Send message")}
            />
          </form>
          {inFlight && (
            <p className="ask-progress" role="status" aria-live="polite">
              {messages.data?.progress && messages.data.progress !== "thinking"
                ? t("Working on it…") + " · " + pretty(messages.data.progress)
                : t("Thinking…")}
            </p>
          )}
          <Text style="body-s" tone="muted" className="ask__fine">
            {purpose === "personal_space" ? (
              t("This chat only customizes your personal space. Daily updates use no AI.")
            ) : purpose === "themes" ? (
              t(
                "Nox designs with you and checks every theme before it's kept. Your themes stay yours until an administrator shares one.",
              )
            ) : purpose === "setup" ? (
              t(
                "Setup mode: Nox checks the house with administrator tools and asks before changing anything.",
              )
            ) : (
              <>
                {quick
                  ? t("Every message here starts a fresh chat. ")
                  : t("Actions are checked by HouseOS. ")}
                {t("Device commands are never queued offline.")}
                {quick && (
                  <>
                    {" "}
                    <Button size="s" variant="link" onClick={() => go("/assistant")}>
                      {t("View your conversations")}
                    </Button>
                  </>
                )}
              </>
            )}
          </Text>
        </section>
      </div>
    </div>
  );
  return page ? <Page>{chat}</Page> : chat;
}
/** A state from the server as a mark's tone. */
function stateTone(state?: string): Tone {
  if (!state) return "neutral";
  if (["completed", "observed", "control_observed", "succeeded", "done", "ok"].includes(state))
    return "success";
  if (["failed", "denied", "conflict", "unavailable", "error", "expired"].includes(state))
    return "danger";
  if (/pending|accepted|running|preparing|awaiting|sent|queued/.test(state)) return "info";
  return "neutral";
}
// Assistant reviews expose the action, never a device/app inventory or internal IDs.
function actionReview(preview: Obj): Obj {
  const fields = new Set([
    "action",
    "destination",
    "value",
    "title",
    "name",
    "file",
    "folder",
    "path",
    "count",
    "quantity",
    "body",
    "subject",
    "recipient",
    "recipients",
    "recipient_names",
    "start",
    "end",
    "timezone",
    "due_date",
    "current",
    "changes",
    "impact",
    "effect",
    "service",
    "disclosure",
    "warnings",
    "offset",
    "maximum_characters",
    "video",
    "audio",
    "subtitles",
    "quality",
    "position",
    "source",
    "release",
    "tracks",
    "items",
    "targets",
    "size",
    "bytes",
    "irreversible",
    "scope",
    "scope_change",
    "visibility",
    "read_only",
    "grant_expires_at",
    "selected_title",
    "sources",
    "effects",
    "plan",
    "interrupts",
    "mode",
    "language",
    "codec",
    "channels",
    "height",
    "hdr",
    "preparation",
    "preparation_strategy",
    "temporary_bytes",
    "transformations",
  ]);
  const clean = (value: unknown, depth = 0): unknown => {
    if (depth > 3 || value == null) return undefined;
    if (Array.isArray(value))
      return value
        .slice(0, 10)
        .map((x) => clean(x, depth + 1))
        .filter((x) => x !== undefined);
    if (typeof value === "object")
      return Object.fromEntries(
        Object.entries(value)
          .filter(([key]) => fields.has(key))
          .map(([key, v]) => [t(pretty(key)), clean(v, depth + 1)])
          .filter(([, v]) => v !== undefined),
      );
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
      ? value
      : undefined;
  };
  return clean(preview) as Obj;
}
const deviceActionLabels: Record<string, string> = {
  power_off: "Turn off",
  power_on: "Turn on",
  reboot: "Restart",
  input: "Change HDMI input",
  volume: "Set volume",
  show: "Show on the TV",
};
/** Nox's film ideas: real catalogue data, Nox's one-line reason, one tap to open in Watch. */
function TitlesCard({ card }: { card: Obj }) {
  return (
    <List label={t("Ideas")}>
      {items(card).map((title: Obj) => (
        <ListRow
          key={title.id}
          href={title.href}
          leading={<Media src={title.poster} alt="" className="ask-titles__poster" />}
          title={title.title + (title.year ? " · " + title.year : "")}
          detail={[...(title.genres || []), title.runtime, title.rating && "★ " + title.rating]
            .filter(Boolean)
            .join(" · ")}
        >
          {title.synopsis && <Text style="body-s">{title.synopsis}</Text>}
          {(title.director?.length > 0 || title.cast?.length > 0) && (
            <Text style="caption" tone="muted">
              {[...(title.director || []), ...(title.cast || [])].join(", ")}
            </Text>
          )}
          {title.why && (
            <span className="ask-titles__why">
              <Mascot size="s" /> <Text style="body-s">{title.why}</Text>
            </span>
          )}
        </ListRow>
      ))}
    </List>
  );
}

function ActionCard({
  card,
  onConfirmed,
  onRefine,
}: {
  card: Obj;
  onConfirmed?: () => Promise<void>;
  onRefine?: (text: string) => void;
}) {
  if (card.kind === "titles") return <TitlesCard card={card} />;
  if (card.kind === "image")
    return (
      <img
        className="ask-picture"
        src={"/api/v1/assistant/attachments/" + encodeURIComponent(card.id)}
        alt={t("Your picture")}
      />
    );
  if (card.kind === "theme_preview") return <ThemePreviewCard card={card} onRefine={onRefine} />;
  if (card.kind === "theme_directions") return <DirectionsCard card={card} onRefine={onRefine} />;
  return <DomainCard card={card} onConfirmed={onConfirmed} />;
}

/** Nox's proposed change: the stored request, sent once from this browser with your own session. */
async function sendProposal(path: string): Promise<Obj> {
  const request = await api(path + "/take", "POST");
  const report = (outcome: Obj) => api(path + "/outcome", "POST", outcome).catch(() => undefined);
  try {
    const answer = await api(request.path, request.method, request.body ?? undefined);
    await report({ ok: true, status: 200 });
    // An invitation's link is shown here only: it never goes back to Nox.
    return { state: "completed", path: answer?.path };
  } catch (e) {
    const error = e as ApiError;
    await report({ ok: false, status: error.status || 0, detail: error.message.slice(0, 300) });
    throw e;
  }
}

function DomainCard({ card, onConfirmed }: { card: Obj; onConfirmed?: () => Promise<void> }) {
  const [continuing, setContinuing] = useState(false);
  const [operation, setOperation] = useState<Obj | null>(null);
  const refreshMessages = useRef(onConfirmed);
  refreshMessages.current = onConfirmed;
  useEffect(() => {
    if (
      card.domain !== "cinema" ||
      card.confirmation_id ||
      !/^[a-zA-Z0-9-]+$/.test(card.operation_id || "") ||
      !["accepted", "running", "preparing"].includes(card.state || card.status)
    )
      return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const deadline = Date.now() + 10 * 60 * 1000;
    const poll = async () => {
      if (document.hidden) {
        timer = setTimeout(poll, 2000);
        return;
      }
      try {
        const fresh = await api("/cinema/operations/" + card.operation_id);
        if (!live) return;
        const status = fresh.status || fresh.state;
        const pending = ["accepted", "running", "preparing"].includes(status);
        setOperation({
          ...fresh,
          state: status,
          message: pending
            ? t("Finding movie sources…")
            : status === "completed"
              ? t("Versions found. Open Watch to play one.")
              : fresh.error?.message || t("Source discovery could not be completed."),
        });
        if (!pending) {
          await refreshMessages.current?.();
          return;
        }
        if (Date.now() >= deadline) {
          setOperation((current) => ({
            ...current,
            message: t("Still working. Reopen this conversation to check again."),
          }));
          return;
        }
        timer = setTimeout(poll, 2000);
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    };
    timer = setTimeout(poll, 2000);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [card.domain, card.operation_id, card.confirmation_id, card.state, card.status]);
  const [result, setResult] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const domain = card.domain;
  const preview = card.preview || {};
  const deviceAction = preview.destination && deviceActionLabels[preview.action];
  const reported = { ...card, ...operation, ...result };
  const state = reported.state || reported.status;
  const resultMessage =
    typeof reported.message === "string"
      ? reported.message
      : typeof reported.summary === "string"
        ? reported.summary
        : null;
  const routes: Record<string, string> = {
    cinema: "/cinema/confirmations/",
    music: "/music/confirm/",
    files: "/files/confirmations/",
  };
  const destinations: Record<string, string> = {
    music: "/music",
    cinema: "/cinema",
    files: "/files",
    house: "/house",
    space: "/space",
    settings: "/settings",
  };
  const setupLink = /^\/(?:control\?[\w=&-]+|assistant\?mode=setup)$/.test(String(card.href || ""))
    ? card.href
    : null;
  // Setup mode opens as its own Nox, with the admin's own words (switch_context never enters it).
  const setupMode = setupLink === "/assistant?mode=setup";
  const openLabels: Record<string, string> = {
    music: "Open Music",
    cinema: "Open Watch",
    files: "Open Files",
    house: "Open House",
    space: "Open My space",
    settings: "Open Settings",
    setup: "Open Control Room",
  };
  const destination =
    domain === "cinema" && reported.workflow_id
      ? "/watch?workflow=" + encodeURIComponent(reported.workflow_id)
      : domain === "setup"
        ? setupLink
        : destinations[domain];
  const supplied = String(card.confirmation_path || "");
  const exact =
    /^\/(?:assistant\/(?:excerpt-confirmations|confirmations|proposals)|cinema\/(?:confirmations|device-confirmations)|files\/confirmations|music\/confirm|admin\/(?:services\/confirmations|audio\/confirm|house-actions\/confirm))\/[a-zA-Z0-9-]+$/.test(
      supplied,
    ) || /^\/music\/playlists\/[a-zA-Z0-9-]+\/confirm$/.test(supplied);
  const proposal = supplied.startsWith("/assistant/proposals/");
  const path = exact
    ? supplied
    : routes[domain] && card.confirmation_id
      ? routes[domain] + card.confirmation_id
      : null;
  return (
    <Surface material="raised" className="ask-card">
      <div className="ask-card__head">
        <strong>
          {card.label ? t(card.label) : pretty(domain)}
          {!card.label && card.confirmation_id ? " " + t("· review action") : ""}
        </strong>
        {state && <Status tone={stateTone(state)}>{t(pretty(state))}</Status>}
      </div>
      {reported.count != null && (
        <Text>
          <strong>{reported.count}</strong> {t(domain === "music" ? "tracks" : "items")}
        </Text>
      )}
      {Array.isArray(reported.items) && card.kind === "result" && (
        <List label={t("Results")}>
          {reported.items.slice(0, 10).map((item: Obj, index: number) => (
            <ListRow key={item.id || index} title={item.title || item.name} detail={item.detail} />
          ))}
        </List>
      )}
      {resultMessage ? (
        <p role="status">{t(resultMessage)}</p>
      ) : (
        domain === "cinema" &&
        card.operation_id &&
        ["accepted", "running", "preparing"].includes(state) && (
          <Status tone="info" busy>
            {t("Finding movie sources…")}
          </Status>
        )
      )}
      {deviceAction ? (
        <>
          <Text>
            <strong>
              {t(deviceAction)} · {preview.destination}
            </strong>
            {preview.value != null && (
              <> · {preview.action === "volume" ? percent(preview.value) : String(preview.value)}</>
            )}
          </Text>
          {!result && preview.may_interrupt && (
            <Text style="body-s" tone="muted">
              {t("This will interrupt the current activity on this device.")}
            </Text>
          )}
        </>
      ) : (
        <>
          {proposal && preview.route && <Text style="title-s">{String(preview.route)}</Text>}
          {typeof card.detail === "string" && (
            <Text tone={proposal ? "muted" : undefined}>{card.detail}</Text>
          )}
          {/^\/join#[\w-]+$/.test(String(reported.path || "")) && (
            <p>
              <code>{location.origin + reported.path}</code>
            </p>
          )}
          {Array.isArray(preview.lines) && (
            <pre className="ask-card__request">
              {[preview.request, ...preview.lines].join("\n")}
            </pre>
          )}
          {preview.unchanged > 0 && (
            <Text style="body-s" tone="muted">
              {t("{n} other values are sent as they are now.").replace(
                "{n}",
                String(preview.unchanged),
              )}
            </Text>
          )}
          <ReviewDetails value={actionReview(preview)} />
        </>
      )}
      {!result && preview.expires_at && card.confirmation_id && (
        <Text style="body-s" tone="muted">
          {t("Confirm before")} {time(preview.expires_at)}
        </Text>
      )}
      {card.confirmation_id && path && !result && (
        <div>
          <Button
            variant="primary"
            icon="check"
            busy={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const confirmed = proposal ? await sendProposal(path!) : await api(path!, "POST");
                setResult(confirmed);
                const continuation = String(card.continuation_path || "");
                const continuationMatch = continuation.match(
                  /^\/assistant\/conversations\/([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})\/continue-tv\/([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})$/,
                );
                try {
                  if (
                    confirmed.state === "observed" &&
                    path === "/cinema/device-confirmations/" + card.confirmation_id &&
                    continuationMatch?.[2] === card.confirmation_id
                  ) {
                    setContinuing(true);
                    await api(continuation, "POST");
                  }
                } finally {
                  setContinuing(false);
                  await onConfirmed?.();
                }
              } catch (e) {
                setError((e as Error).message);
                if (proposal) setResult({ state: "failed" }); // sent once, never twice
              } finally {
                setBusy(false);
              }
            }}
          >
            {t(deviceAction ? "Confirm" : "Confirm this exact action")}
          </Button>
        </div>
      )}
      {continuing && (
        <Status tone="info" busy>
          {t("Continuing movie selection…")}
        </Status>
      )}
      {result && !resultMessage && !continuing && (
        <p className="ask-card__note" role="status">
          {t(
            ["completed", "control_observed", "observed"].includes(state)
              ? "This action is complete."
              : ["failed", "denied", "conflict", "unavailable"].includes(state)
                ? "This action could not be completed."
                : "The command was sent. Completion has not been verified yet.",
          )}
        </p>
      )}
      {typeof reported.next_step === "string" && (
        <Text style="body-s" tone="muted">
          {reported.next_step}
        </Text>
      )}
      {destination && (
        <div>
          <LinkButton
            variant="link"
            size="s"
            icon="forward"
            href={destination}
            onClick={(event) => {
              event.preventDefault();
              if (setupMode)
                dispatchEvent(
                  new CustomEvent("houseos:ask", {
                    detail: { purpose: "setup", message: String(card.ask || "") },
                  }),
                );
              else go(destination);
            }}
          >
            {t(setupMode ? "Open setup mode" : openLabels[domain])}
          </LinkButton>
        </div>
      )}
      <Problem
        error={
          error || (reported.error?.message !== resultMessage ? reported.error?.message : "") || ""
        }
      />
    </Surface>
  );
}

/** The studio before it has a model: how to set it up (admins), or whom to ask. */
function StudioGuide({ admin }: { admin: boolean }) {
  return (
    <Notice
      tone="info"
      title={t("The theme studio needs its own AI")}
      action={
        admin ? (
          <Button size="s" onClick={() => go("/control?tab=ai#assistant-models")}>
            {t("Set it up")}
          </Button>
        ) : undefined
      }
    >
      <ol className="ask-steps">
        <li>{t("Control Room → AI → Theme studio.")}</li>
        <li>
          {t(
            "Recommended: Claude (subscription) · Claude Opus 5.5 · medium. It designs with taste, looks at pictures and searches the web.",
          )}
        </li>
        <li>
          {t(
            "A Claude subscription works only for the person who signed in with it; for everyone else, choose an API connection (Anthropic or OpenRouter), which sees pictures too.",
          )}
        </li>
      </ol>
      {!admin && <Text>{t("Ask an administrator of the house to set it up.")}</Text>}
      <Text>
        {t("Meanwhile, you can make a theme by hand, no AI needed:")}{" "}
        <Button variant="link" size="s" onClick={() => go("/workshop")}>
          {t("Open the workshop")}
        </Button>
      </Text>
      <Text style="caption" tone="muted">
        {t(
          "What you make stays yours: nothing reaches the house until an administrator shares it.",
        )}
      </Text>
    </Notice>
  );
}

/** A theme Nox made, drawn in itself: try it on (and back), keep it, or ask for changes. */
function ThemePreviewCard({ card, onRefine }: { card: Obj; onRefine?: (text: string) => void }) {
  useInstalled(); // the draft's stylesheet arrives with the list
  const theme = (allThemes().find((item) => item.id === card.id) ?? card) as ThemeInfo;
  const name = getLanguage() === "fr" ? card.names?.fr : card.names?.en;
  const [trying, setTrying] = useState(false);
  useEffect(() => () => void (trying && reapply()), [trying]);
  return (
    <Surface material="raised" className="ask-card ask-theme">
      <ThemeSpecimen theme={theme} scheme={card.scheme} />
      <div className="ask-card__actions">
        <Button
          size="s"
          icon={trying ? "undo" : "palette"}
          pressed={trying}
          onClick={() => {
            if (trying) reapply();
            else apply(card.id, card.scheme as Scheme);
            setTrying(!trying);
          }}
        >
          {trying ? t("Back to mine") : t("Try it on me")}
        </Button>
        <Button
          size="s"
          variant="primary"
          icon="check"
          onClick={async () => {
            try {
              await api("/preferences", "PUT", { theme: card.id });
              window.dispatchEvent(new Event("house-settings-updated"));
              setTrying(false);
              toast(t("You're wearing {name}.").replace("{name}", name || card.id));
            } catch (e) {
              toast((e as Error).message, { tone: "danger" });
            }
          }}
        >
          {t("Keep it")}
        </Button>
        {onRefine && (
          <Button
            size="s"
            variant="quiet"
            icon="brush"
            onClick={() => onRefine(t("Change {name}: ").replace("{name}", name || card.id))}
          >
            {t("Refine")}
          </Button>
        )}
      </div>
    </Surface>
  );
}

/** Nox's proposed directions, shown as swatches with their words (not hex codes in prose). */
function DirectionsCard({ card, onRefine }: { card: Obj; onRefine?: (text: string) => void }) {
  return (
    <ul className="ask-directions">
      {(card.directions || []).map((d: Obj, i: number) => (
        <li key={i}>
          <Surface material="raised" className="ask-card ask-direction">
            <Text as="h3" style="title-s">
              {d.name}
            </Text>
            <Text style="body-s" tone="muted">
              {d.mood}
            </Text>
            <ul className="ask-direction__swatches">
              {(d.swatches || []).map((swatch: Obj, j: number) => (
                <li key={j}>
                  <i style={{ "--swatch": swatch.hex } as CSSProperties} aria-hidden="true" />
                  <Text style="caption">{swatch.word}</Text>
                </li>
              ))}
            </ul>
            <Text style="body-s">
              {d.display_font} · {d.body_font} · {d.material}
            </Text>
            <Text style="body-s" tone="muted">
              {d.why}
            </Text>
            {onRefine && (
              <Button
                size="s"
                icon="brush"
                onClick={() => onRefine(t("Let's build {name}.").replace("{name}", d.name))}
              >
                {t("Build this one")}
              </Button>
            )}
          </Surface>
        </li>
      ))}
    </ul>
  );
}

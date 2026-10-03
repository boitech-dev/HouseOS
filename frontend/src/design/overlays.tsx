// Everything that sits above the page: sheets (one modal system for all), menus, toasts and the
// command palette. Native <dialog>: the page behind is inert, Escape closes, focus comes back.
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { t } from "../i18n";
import { Button, IconButton, useFocusTrap, type ButtonVariant } from "./controls";
import { Icon, type IconName } from "./icons";
import { Kbd } from "./display";
import { effectiveMotion } from "./motion";

export type SheetPlace = "bottom" | "side" | "center";

/** A sheet: from the bottom on phones; beside the page (`side`) or in the middle (`center`) on
 *  wide screens. The grip drags it away on touch. `footer` holds its actions (primary last). */
export function Sheet({
  title,
  onClose,
  children,
  place = "bottom",
  actions,
  footer,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  place?: SheetPlace;
  /** Small controls beside the title. */
  actions?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const [ref, trap] = useFocusTrap<HTMLDialogElement>();
  const drag = useRef<{ start: number; y: number } | null>(null);
  // Closing sinks away for a moment (not at all when motion is still), then the owner closes it.
  const [closing, setClosing] = useState(false);
  const close = () => {
    if (closing) return;
    if (effectiveMotion() === "still") return onClose();
    setClosing(true);
    const ms = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--dur-fast"),
    );
    window.setTimeout(onClose, Number.isFinite(ms) ? ms : 120);
  };
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    // The control meant to be used first (a search field), else the browser's first control.
    dialog?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    // Keep the sheet above the on-screen keyboard.
    const viewport = window.visualViewport;
    const fit = () =>
      dialog?.style.setProperty("--viewport-h", (viewport?.height ?? innerHeight) + "px");
    fit();
    viewport?.addEventListener("resize", fit);
    return () => {
      viewport?.removeEventListener("resize", fit);
      dialog?.close();
      previous?.focus();
    };
  }, []);
  const release = () => {
    const moved = drag.current?.y ?? 0;
    drag.current = null;
    ref.current?.style.removeProperty("--drag");
    if (moved > 90) close();
  };
  return (
    <dialog
      ref={ref}
      className="ds-sheet"
      data-place={place}
      data-wide={wide || undefined}
      data-closing={closing || undefined}
      aria-modal="true"
      aria-label={title}
      onCancel={(e) => {
        // React bubbles a nested sheet's cancel up the tree: only close for our own.
        if (e.target !== e.currentTarget) return;
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      onKeyDown={trap}
    >
      <div className="ds-sheet__panel">
        {place === "bottom" && (
          <span
            className="ds-sheet__grip"
            aria-hidden="true"
            onPointerDown={(e) => {
              drag.current = { start: e.clientY, y: 0 };
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              if (!drag.current) return;
              drag.current.y = Math.max(0, e.clientY - drag.current.start);
              ref.current?.style.setProperty("--drag", drag.current.y + "px");
            }}
            onPointerUp={release}
            onPointerCancel={release}
          />
        )}
        <header className="ds-sheet__head">
          <h2>{title}</h2>
          <div className="ds-sheet__actions">
            {actions}
            <IconButton icon="close" label={t("Close")} onClick={close} />
          </div>
        </header>
        <div className="ds-sheet__body">{children}</div>
        {footer && <footer className="ds-sheet__foot">{footer}</footer>}
      </div>
    </dialog>
  );
}

/** "Are you sure?": what will happen, and the one button that does it. */
export function ConfirmSheet({
  title,
  children,
  confirm,
  danger = false,
  onConfirm,
  onClose,
}: {
  title: string;
  children: ReactNode;
  confirm: string;
  danger?: boolean;
  onConfirm: () => Promise<unknown> | unknown;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Sheet
      title={title}
      onClose={onClose}
      place="center"
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t("Cancel")}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            busy={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
                onClose();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {confirm}
          </Button>
        </>
      }
    >
      <div className="ds-stack">
        {children}
        {error && (
          <p className="ds-field__error" role="alert">
            <Icon name="alert" size="s" />
            {t(error)}
          </p>
        )}
      </div>
    </Sheet>
  );
}

export type MenuItem = {
  label: string;
  icon?: IconName;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
};

/** More actions behind one button ("…"): arrow keys move, Escape closes, a click outside too. */
export function Menu({
  label,
  items,
  icon = "more",
  variant = "quiet",
}: {
  label: string;
  items: MenuItem[];
  icon?: IconName;
  variant?: ButtonVariant;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    addEventListener("pointerdown", away);
    return () => removeEventListener("pointerdown", away);
  }, [open]);
  const move = (e: KeyboardEvent) => {
    const buttons = [
      ...(list.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []),
    ];
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: buttons.length - 1 }[e.key];
    if (to !== undefined) {
      e.preventDefault();
      buttons[(to + buttons.length) % buttons.length]?.focus();
    } else if (e.key === "Escape" || e.key === "Tab") {
      setOpen(false);
      if (e.key === "Escape") box.current?.querySelector<HTMLButtonElement>("button")?.focus();
    }
  };
  return (
    <div className="ds-menu" ref={box}>
      <IconButton
        icon={icon}
        label={label}
        variant={variant}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      />
      {open && (
        <ul className="ds-menu__list" role="menu" aria-label={label} ref={list} onKeyDown={move}>
          {items.map((item) => (
            <li key={item.label} role="none">
              <button
                type="button"
                role="menuitem"
                data-danger={item.danger || undefined}
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
              >
                {item.icon && <Icon name={item.icon} size="s" />}
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A small window by its button, for a glance and a few actions (who's home, a quick setting).
 *  Not modal: a click outside, Escape or Tab away closes it. */
export function Popover({
  label,
  trigger,
  children,
}: {
  label: string;
  trigger: ReactNode;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const close = () => setOpen(false);
  // Opened in the top layer (a native popover), under its button: no box around it can clip or
  // cover it (Home's picture box clips its own overflow). Without popover support: in place.
  useLayoutEffect(() => {
    const node = panel.current;
    if (!open || !node || !("showPopover" in node)) return;
    const place = () => {
      const r = box.current!.getBoundingClientRect();
      node.style.top = `${r.bottom + 4}px`;
      node.style.left = `${Math.max(8, Math.min(r.left, innerWidth - node.offsetWidth - 8))}px`;
    };
    node.showPopover();
    place();
    addEventListener("scroll", place, true);
    addEventListener("resize", place);
    return () => {
      removeEventListener("scroll", place, true);
      removeEventListener("resize", place);
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    box.current
      ?.querySelector<HTMLElement>(".ds-popover__panel :is(button, a, input):not(:disabled)")
      ?.focus();
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    addEventListener("pointerdown", away);
    return () => removeEventListener("pointerdown", away);
  }, [open]);
  return (
    <div
      className="ds-popover"
      ref={box}
      onKeyDown={(e) => {
        if (e.key !== "Escape" || !open) return;
        e.stopPropagation();
        setOpen(false);
        box.current?.querySelector<HTMLButtonElement>(".ds-popover__trigger")?.focus();
      }}
    >
      <Button
        variant="quiet"
        className="ds-popover__trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {trigger}
      </Button>
      {open && (
        <div
          ref={panel}
          className="ds-popover__panel"
          role="dialog"
          aria-label={label}
          popover="manual"
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}

// ---------- toasts: what just happened, said once ----------
type Toast = {
  id: number;
  text: string;
  tone: "neutral" | "success" | "danger";
  action?: { label: string; run: () => void };
};
let toasts: Toast[] = [];
const listeners = new Set<() => void>();
const publish = () => listeners.forEach((listener) => listener());

/** Say what just happened ("Added to the queue."); success echoes the verb in the past tense. */
export function toast(
  text: string,
  options: { tone?: Toast["tone"]; action?: Toast["action"] } = {},
) {
  const item: Toast = {
    id: Date.now() + Math.random(),
    text,
    tone: options.tone ?? "success",
    action: options.action,
  };
  toasts = [...toasts.slice(-2), item];
  publish();
  setTimeout(
    () => {
      toasts = toasts.filter((x) => x !== item);
      publish();
    },
    options.action ? 8000 : 4000,
  );
}

/** Where toasts appear (once, in the shell), above the Now bar; read aloud politely. */
export function ToastRegion() {
  const list = useSyncExternalStore(
    (changed) => {
      listeners.add(changed);
      return () => void listeners.delete(changed);
    },
    () => toasts,
  );
  return (
    <div className="ds-toasts" role="status" aria-live="polite">
      {list.map((item) => (
        <div key={item.id} className="ds-toast" data-tone={item.tone}>
          <Icon name={item.tone === "danger" ? "alert" : "check"} size="s" />
          <span>{item.text}</span>
          {item.action && (
            <Button variant="link" size="s" onClick={item.action.run}>
              {item.action.label}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------- the command palette ----------
export type Command = {
  id: string;
  label: string;
  group: string;
  icon?: IconName;
  keywords?: string;
  /** What to do; a promise keeps the palette busy, then it closes (or stays, with `keep`). */
  run?: () => unknown;
  /** Picking it asks for more in the same box (a song to find, an item to add). */
  mode?: PaletteMode;
  /** Stays open after running, cleared, ready for the next one (groceries, one per line). */
  keep?: boolean;
  disabled?: boolean;
};

/** A question the palette asks next: the rows for what is typed and/or what Enter does with it. */
export type PaletteMode = {
  label: string;
  placeholder: string;
  rows?: (query: string) => Command[] | Promise<Command[]>;
  submit?: (query: string) => unknown;
  keep?: boolean;
};

// Case and accents aside ("theme" finds "thème").
const plain = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

/** How well one typed word fits a command: the start of a word in its name beats inside a word,
 *  beats its keywords, beats the letters in order ("gro" → Groceries, "ktch" → Kitchen). */
function fit(word: string, command: Command): number {
  const label = plain(command.label);
  const extra = plain(command.group + " " + (command.keywords ?? ""));
  if (label.startsWith(word)) return 4;
  if (label.includes(" " + word)) return 3;
  if (label.includes(word)) return 2;
  if (extra.includes(word)) return 1.5;
  let at = 0;
  for (const letter of label) if (letter === word[at]) at++;
  return at === word.length ? 1 : 0;
}

export function rank(commands: Command[], query: string) {
  const words = plain(query).split(/\s+/).filter(Boolean);
  return commands
    .map((command) => {
      const scores = words.map((word) => fit(word, command));
      return { command, score: scores.every(Boolean) ? scores.reduce((a, b) => a + b, 0) : 0 };
    })
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((row) => row.command);
}

/** ⌘K / Ctrl+K: go anywhere, do things, or ask Nox. Empty, it offers the quick actions, numbered:
 *  a digit runs one (Ctrl+K, 1, a song's name, Enter: it's queued). */
export function CommandPalette({
  commands,
  quick,
  onAsk,
  search,
  onClose,
}: {
  commands: Command[];
  quick: Command[];
  onAsk?: (text: string) => void;
  /** What the house has that matches the words (a song, a film, a game), under the commands. */
  search?: (text: string) => Promise<Command[]>;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [at, setAt] = useState(0);
  const [mode, setMode] = useState<PaletteMode | null>(null);
  const [asked, setAsked] = useState<Command[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const [found, setFound] = useState<Command[]>([]);
  // Typing something that isn't a command: a moment later, what the house has by that name.
  useEffect(() => {
    setFound([]);
    if (mode || !search || query.trim().length < 2) return;
    let live = true;
    const wait = setTimeout(
      () =>
        void search(query.trim()).then(
          (rows) => live && setFound(rows),
          () => {},
        ),
      280,
    );
    return () => {
      live = false;
      clearTimeout(wait);
    };
  }, [mode, query, search]);
  // A mode's rows: straight away when they are at hand, a moment after typing when they're fetched.
  useEffect(() => {
    if (!mode?.rows) return setAsked([]);
    let live = true;
    const load = () =>
      Promise.resolve(mode.rows!(query))
        .then((rows) => live && setAsked(rows))
        .catch((e) => live && setError((e as Error).message));
    const wait = setTimeout(load, query ? 280 : 0);
    return () => {
      live = false;
      clearTimeout(wait);
    };
  }, [mode, query]);
  const rows: Command[] = mode
    ? asked
    : query
      ? [
          ...rank(commands, query).slice(0, 12),
          ...found,
          ...(onAsk
            ? [
                {
                  id: "ask",
                  label: t("Ask Nox: {text}").replace("{text}", query),
                  group: "Nox",
                  icon: "sparkles" as const,
                  run: () => onAsk(query),
                },
              ]
            : []),
        ]
      : quick;
  const chosen = rows[Math.min(at, rows.length - 1)];
  const enter = (next: PaletteMode) => {
    setMode(next);
    setQuery("");
    setAt(0);
    setError("");
    input.current?.focus();
  };
  const act = async (thing: () => unknown, keep?: boolean) => {
    // Done with the palette: close first, so the page it opens keeps its focus; a failure is
    // then said in a toast.
    if (!keep) {
      onClose();
      try {
        await thing();
      } catch (e) {
        toast((e as Error).message, { tone: "danger" });
      }
      return;
    }
    setBusy(true);
    setError("");
    try {
      await thing();
      setQuery("");
      setAt(0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const pick = (row?: Command) => {
    if (busy) return;
    if (row && !row.disabled) {
      if (row.mode) return enter(row.mode);
      if (row.run) return void act(row.run, row.keep);
    }
    if (!row && mode?.submit && query.trim()) void act(() => mode.submit!(query.trim()), mode.keep);
  };
  return (
    <Sheet title={t("Go to, do or ask")} onClose={onClose} place="center">
      <div
        className="ds-palette"
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            if (rows.length)
              setAt((n) => (n + (e.key === "ArrowDown" ? 1 : rows.length - 1)) % rows.length);
          } else if (e.key === "Enter") {
            e.preventDefault();
            // Typed text for a mode that takes it (a grocery, a message) goes before any row.
            pick(mode?.submit && !mode.rows ? undefined : chosen);
          } else if (e.key === "Backspace" && !query && mode) {
            e.preventDefault();
            setMode(null);
            setAt(0);
          } else if (!query && !mode && /^[1-9]$/.test(e.key) && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            pick(quick[Number(e.key) - 1]);
          }
        }}
      >
        <div className="ds-palette__field">
          {mode && (
            <button
              type="button"
              className="ds-palette__mode"
              aria-label={t("Back to everything") + " · " + mode.label}
              onClick={() => {
                setMode(null);
                setQuery("");
                input.current?.focus();
              }}
            >
              {mode.label}
              <Icon name="close" size="s" />
            </button>
          )}
          <input
            ref={input}
            className="ds-input"
            data-autofocus=""
            role="combobox"
            aria-expanded="true"
            aria-controls="ds-palette-list"
            aria-activedescendant={
              chosen ? "ds-palette-" + Math.min(at, rows.length - 1) : undefined
            }
            aria-label={mode ? mode.label : t("Search places and actions")}
            aria-busy={busy || undefined}
            placeholder={mode ? mode.placeholder : t("A place, an action, or a question for Nox")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setAt(0);
            }}
          />
        </div>
        {!query && !mode && (
          <p className="ds-palette__lead">{t("Quick actions: press a number.")}</p>
        )}
        <ul id="ds-palette-list" role="listbox" aria-label={t("Results")}>
          {rows.map((row, i) => (
            <li
              key={row.id}
              id={"ds-palette-" + i}
              role="option"
              aria-selected={i === Math.min(at, rows.length - 1)}
              aria-disabled={row.disabled || undefined}
              onPointerMove={() => setAt(i)}
              onClick={() => pick(row)}
            >
              {!query && !mode && i < 9 ? (
                <Kbd>{i + 1}</Kbd>
              ) : (
                row.icon && <Icon name={row.icon} size="s" />
              )}
              <span>{row.label}</span>
              <small>{row.group}</small>
            </li>
          ))}
        </ul>
        {!query && !mode && (
          <>
            <p className="ds-palette__lead">
              {t("…or type anything: a setting, a room, a person, a song.")}
            </p>
            <p className="ds-palette__lead">
              {t("Music keys: Ctrl + ← → previous / next · Ctrl + ↑ ↓ volume · Ctrl + Space pause")}
            </p>
          </>
        )}
        {mode?.submit && query.trim() && (
          <p className="ds-palette__lead">
            <Kbd>↵</Kbd> {mode.label}: “{query.trim()}”
          </p>
        )}
        {error && (
          <p className="ds-field__error" role="alert">
            <Icon name="alert" size="s" />
            {t(error)}
          </p>
        )}
        <p className="ds-palette__keys">
          <Kbd>↑</Kbd> <Kbd>↓</Kbd> {t("to move")} · <Kbd>↵</Kbd> {t("to open")} ·{" "}
          {mode ? (
            <>
              <Kbd>⌫</Kbd> {t("to go back")}
            </>
          ) : (
            <>
              <Kbd>1</Kbd>–<Kbd>9</Kbd> {t("quick actions")}
            </>
          )}{" "}
          · <Kbd>Esc</Kbd> {t("to close")}
        </p>
      </div>
    </Sheet>
  );
}

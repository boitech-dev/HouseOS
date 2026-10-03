// Patterns: how a page is put together (docs/design/SYSTEM.md, "Page anatomy"). Rooms compose
// these; they never style raw elements. Text passed in is already translated.
import {
  Component,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";
import { t } from "../i18n";
import { go } from "../nav";
import { Button, IconButton } from "./controls";
import { Badge, Progress, Skeleton, Status, type Tone } from "./display";
import { Glyph, Icon, Mascot, type GlyphName, type IconName } from "./icons";
import { useThemeInfo } from "./theme";
import { Slot, useSlot } from "./slots";
import { ThemeLayers } from "./theme_layers";
import { useReveal } from "./motion";
import { useTip } from "../tips";

type Space = 1 | 2 | 3 | 4 | 5 | 6 | 7;

/** The page: width and the rhythm between its parts. */
export function Page({
  children,
  width = "default",
}: {
  children: ReactNode;
  width?: "narrow" | "default" | "wide";
}) {
  return (
    <div className="ds-page" data-width={width}>
      {children}
    </div>
  );
}
export const Stack = ({
  children,
  space,
  as: Tag = "div",
}: {
  children: ReactNode;
  space?: Space;
  as?: ElementType;
}) => (
  <Tag className="ds-stack" data-space={space}>
    {children}
  </Tag>
);
export const Cluster = ({
  children,
  space,
  end,
}: {
  children: ReactNode;
  space?: Space;
  end?: boolean;
}) => (
  <div className="ds-cluster" data-space={space} data-end={end || undefined}>
    {children}
  </div>
);
/** Cards that fill the width, each at least `min` wide. */
export const Grid = ({
  children,
  min = "240px",
  space,
}: {
  children: ReactNode;
  min?: string;
  space?: Space;
}) => (
  <div className="ds-grid" data-space={space} style={{ "--min": min } as CSSProperties}>
    {children}
  </div>
);

/** Shown once per person, then collected in Nox's house tour. Replaces Nox's speech bubbles. */
export function Hint({ id, children }: { id: string; children: ReactNode }) {
  const key = "houseos.hint." + id;
  const [shown, setShown] = useState(() => {
    try {
      return localStorage.getItem(key) !== "1";
    } catch {
      return true;
    }
  });
  // Two lines at most until asked: a long tip never pushes the page's content off a phone.
  const [open, setOpen] = useState(false);
  const [long, setLong] = useState(false);
  const text = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const measure = () =>
      text.current && setLong(text.current.scrollHeight > text.current.clientHeight + 1);
    measure();
    const watch = new ResizeObserver(measure);
    if (text.current) watch.observe(text.current);
    return () => watch.disconnect();
  }, [shown]);
  if (!shown) return null;
  return (
    <aside className="ds-hint">
      <Icon name="info" size="s" />
      <div className="ds-hint__text">
        <p ref={text} data-open={open || undefined}>
          {children}
        </p>
        {(long || open) && (
          <Button variant="link" size="s" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? t("Less") : t("More")}
          </Button>
        )}
      </div>
      <IconButton
        icon="close"
        size="s"
        label={t("Hide this tip")}
        onClick={() => {
          setShown(false);
          try {
            localStorage.setItem(key, "1");
          } catch {}
        }}
      />
    </aside>
  );
}

/** The top of every room: its title, a tip about it, one primary action at most. */
export function PageHeader({
  title,
  room,
  kicker,
  lead,
  actions,
  hint,
}: {
  title: ReactNode;
  /** The place: its tip under the title. */
  room?: string;
  kicker?: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  hint?: ReactNode;
}) {
  const tip = useTip(room);
  const banner = useThemeInfo()?.parts?.header === "banner";
  lead = lead ?? tip; // a real tip about the room, not the theme's words
  return (
    <header className="ds-page-header">
      <ThemeLayers where="header" under />
      {banner && (
        <div className="ds-page-header__banner" aria-hidden="true">
          <Slot id="header.banner" />
        </div>
      )}
      <ThemeLayers where="header" />
      <div className="ds-page-header__text">
        {kicker && <p className="ds-page-header__kicker">{kicker}</p>}
        <h1>{title}</h1>
        {lead && <p className="ds-page-header__lead">{lead}</p>}
      </div>
      {actions && <div className="ds-page-header__actions">{actions}</div>}
      {hint}
    </header>
  );
}

export type NavItem = { id: string; label: string; icon?: IconName; count?: number };

/** A room's own places (Board, Tasks…): navigation only, never filters or actions. */
export function SubNav({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: NavItem[];
  value: string;
  onChange: (id: string) => void;
}) {
  // A phone's strip scrolls: keep the current tab in view (sideways only, the page stays put).
  const nav = useRef<HTMLElement>(null);
  useEffect(() => {
    const reveal = () => {
      const box = nav.current,
        tab = box?.querySelector("[aria-current]");
      if (!box || !tab) return;
      const b = box.getBoundingClientRect(),
        r = tab.getBoundingClientRect();
      if (r.left < b.left) box.scrollLeft += r.left - b.left;
      else if (r.right > b.right) box.scrollLeft += r.right - b.right;
      edges();
    };
    // Which edges have more tabs past them: those fade (patterns.css).
    const edges = () => {
      const box = nav.current;
      if (!box) return;
      box.toggleAttribute("data-more-before", box.scrollLeft > 1);
      box.toggleAttribute("data-more-after", box.scrollLeft + box.clientWidth < box.scrollWidth - 1);
    };
    nav.current?.addEventListener("scroll", edges, { passive: true });
    // Measured again whenever the strip or its tabs change size (late layout, web fonts arriving).
    const watch = new ResizeObserver(reveal);
    if (nav.current) watch.observe(nav.current);
    // The tabs widen when the web fonts arrive, pushing the current one along.
    nav.current?.querySelectorAll("button").forEach((tab) => watch.observe(tab));
    const box = nav.current;
    return () => {
      watch.disconnect();
      box?.removeEventListener("scroll", edges);
    };
  }, [value]);
  return (
    <nav className="ds-subnav" aria-label={label} ref={nav}>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              aria-current={item.id === value ? "page" : undefined}
              onClick={() => onChange(item.id)}
            >
              {item.icon && <Icon name={item.icon} size="s" />}
              <span>{item.label}</span>
              {!!item.count && <Badge tone="neutral">{item.count}</Badge>}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** Search, filters and views for the list below it. */
export const Toolbar = ({ children, label }: { children: ReactNode; label?: string }) => (
  <div className="ds-toolbar" role="toolbar" aria-label={label}>
    {children}
  </div>
);

/** A titled part of a page, with no box around it. */
export function Section({
  title,
  lead,
  actions,
  children,
  id,
  level = 2,
  aside = false,
}: {
  title?: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
  level?: 2 | 3;
  /** In settings on wide screens: the title and lead beside the controls, not above them
   *  (level 3 sections always are). For a few short controls. */
  aside?: boolean;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section className="ds-section" id={id} data-level={level} data-aside={aside || undefined}>
      {(title || actions || lead) && (
        <div className="ds-section__intro">
          {(title || actions) && (
            <div className="ds-section__head">
              {title && <Heading>{title}</Heading>}
              {actions && <div className="ds-section__actions">{actions}</div>}
            </div>
          )}
          {lead && <p className="ds-section__lead">{lead}</p>}
        </div>
      )}
      <div className="ds-section__body">{children}</div>
    </section>
  );
}

/** Opens a place in the app (keeps the SPA), or runs `onOpen`. */
function Opener({
  href,
  onOpen,
  children,
  className,
  label,
  current,
  disabled,
}: {
  href?: string;
  onOpen?: () => void;
  children: ReactNode;
  className: string;
  label?: string;
  disabled?: boolean;
  /** The chosen one of a set (the episode, the version): read aloud as current. */
  current?: boolean;
}) {
  if (href)
    return (
      <a
        className={className}
        href={href}
        aria-label={label}
        onClick={(e) => {
          if (href.startsWith("/") && !e.metaKey && !e.ctrlKey) {
            e.preventDefault();
            go(href);
          }
        }}
      >
        {children}
      </a>
    );
  if (onOpen)
    return (
      <button
        type="button"
        className={className}
        onClick={onOpen}
        aria-label={label}
        aria-current={current || undefined}
        disabled={disabled}
      >
        {children}
      </button>
    );
  return <div className={className}>{children}</div>;
}

/** A module of a dashboard: a card with a head (icon, title, where it leads) and its content. */
export function Panel({
  icon,
  glyph,
  title,
  href,
  more,
  children,
  className,
}: {
  icon?: IconName;
  glyph?: GlyphName;
  title: ReactNode;
  /** Where "Open" leads: the place this module is a window onto. */
  href?: string;
  /** The word for that link (default "Open"). */
  more?: string;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section className={"ds-panel" + (className ? " " + className : "")} aria-labelledby={id}>
      <header className="ds-panel__head">
        {glyph ? <Glyph name={glyph} /> : icon && <Icon name={icon} />}
        <h2 id={id}>{title}</h2>
        {href && (
          <Opener className="ds-panel__more" href={href}>
            {more ?? t("Open")}
            <Icon name="chevron-right" size="s" />
          </Opener>
        )}
      </header>
      {children}
    </section>
  );
}

/** One line of a list: what it is, a detail, its state, and its actions at the end. The row
 *  itself opens it (when it has somewhere to go); actions stay separate buttons. */
export function ListRow({
  leading,
  title,
  detail,
  meta,
  status,
  actions,
  href,
  onOpen,
  selected,
  control,
  children,
}: {
  /** A control beside the row, outside what opens it (a selection checkbox). */
  control?: ReactNode;
  leading?: ReactNode;
  title: ReactNode;
  detail?: ReactNode;
  meta?: ReactNode;
  status?: { tone: Tone; text: string; busy?: boolean };
  actions?: ReactNode;
  href?: string;
  onOpen?: () => void;
  selected?: boolean;
  /** More under the row, full width (an inline form, a problem and its fix). */
  children?: ReactNode;
}) {
  return (
    <li
      className="ds-row"
      data-selected={selected || undefined}
      data-opens={href || onOpen ? "" : undefined}
    >
      {control && <span className="ds-row__control">{control}</span>}
      <Opener className="ds-row__main" href={href} onOpen={onOpen} current={selected}>
        {leading && <span className="ds-row__leading">{leading}</span>}
        <span className="ds-row__text">
          <span className="ds-row__title">{title}</span>
          {detail && <span className="ds-row__detail">{detail}</span>}
        </span>
        {meta && <span className="ds-row__meta">{meta}</span>}
        {status && (
          <Status tone={status.tone} busy={status.busy}>
            {status.text}
          </Status>
        )}
      </Opener>
      {actions && <span className="ds-row__actions">{actions}</span>}
      {children && <div className="ds-row__more">{children}</div>}
    </li>
  );
}

/** A heading between rows of a list ("Round 2"); read as text, not as an item. */
export const ListHeading = ({ children }: { children: ReactNode }) => (
  <li className="ds-list__heading" role="presentation">
    {children}
  </li>
);

/** A list of rows. */
export const List = ({ children, label }: { children: ReactNode; label?: string }) => (
  <ul className="ds-list" aria-label={label}>
    {children}
  </ul>
);

/** A poster or cover with its title: opens the thing. */
export function MediaCard({
  media,
  title,
  meta,
  badge,
  href,
  onOpen,
}: {
  media: ReactNode;
  title: string;
  meta?: ReactNode;
  badge?: ReactNode;
  href?: string;
  onOpen?: () => void;
}) {
  return (
    <Opener className="ds-media-card" href={href} onOpen={onOpen}>
      <span className="ds-media-card__art">
        {media}
        {badge && <span className="ds-media-card__badge">{badge}</span>}
      </span>
      <span className="ds-media-card__title">{title}</span>
      {meta && <span className="ds-media-card__meta">{meta}</span>}
    </Opener>
  );
}

/** A titled row you scroll sideways; arrows on wide screens. */
export function Shelf({
  title,
  action,
  item = "152px",
  children,
}: {
  title: ReactNode;
  action?: ReactNode;
  item?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLUListElement>(null);
  const scroll = (way: number) =>
    ref.current?.scrollBy({ left: way * ref.current.clientWidth * 0.8, behavior: "smooth" });
  return (
    <section className="ds-shelf">
      <div className="ds-section__head">
        <h2>{title}</h2>
        <div className="ds-section__actions">
          {action}
          <span className="ds-shelf__arrows">
            <IconButton
              icon="chevron-left"
              size="s"
              label={t("Scroll back")}
              onClick={() => scroll(-1)}
            />
            <IconButton
              icon="chevron-right"
              size="s"
              label={t("Scroll forward")}
              onClick={() => scroll(1)}
            />
          </span>
        </div>
      </div>
      <ul
        className="ds-shelf__items"
        ref={ref}
        aria-label={typeof title === "string" ? title : undefined}
        style={{ "--item": item } as CSSProperties}
      >
        {children}
      </ul>
    </section>
  );
}

/** More below, folded until asked for (a timer, advanced controls). */
export function Disclosure({
  summary,
  children,
  onToggle,
}: {
  summary: ReactNode;
  children: ReactNode;
  onToggle?: (open: boolean) => void;
}) {
  return (
    <details className="ds-disclosure" onToggle={(e) => onToggle?.(e.currentTarget.open)}>
      <summary>
        <Icon name="chevron-right" size="s" />
        {summary}
      </summary>
      <div className="ds-disclosure__body">{children}</div>
    </details>
  );
}

/** True once the element comes within `margin` of the screen, and stays true. */
export function useNear<T extends HTMLElement>(margin = "800px") {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const node = ref.current;
    if (near || !node) return;
    const watch = new IntersectionObserver(
      (entries) => entries.some((entry) => entry.isIntersecting) && setNear(true),
      { rootMargin: margin },
    );
    watch.observe(node);
    return () => watch.disconnect();
  }, [near, margin]);
  return [near, ref] as const;
}

/** The end of a list that grows as you scroll: loads the next page as it nears view (inside
 *  whatever scrolls: page, sheet, or a shelf), with a plain button for keyboards and when
 *  observing is off. Inside a list or a shelf, pass `item` so it is a list item. */
export function MoreBelow({
  pages,
  item = false,
}: {
  pages: { more?: () => void; loading: boolean; items: unknown[] };
  item?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  const more = useRef(pages.more);
  more.current = pages.more;
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    let root: HTMLElement | null = node.parentElement;
    const scrolls = (el: HTMLElement) => {
      const style = getComputedStyle(el);
      return /(auto|scroll)/.test(style.overflowY + " " + style.overflowX);
    };
    while (root && !scrolls(root)) root = root.parentElement;
    const watch = new IntersectionObserver(
      (entries) => entries.some((entry) => entry.isIntersecting) && more.current?.(),
      { root, rootMargin: "600px" },
    );
    watch.observe(node);
    return () => watch.disconnect();
    // A new page may leave the end still in view: observe again so it keeps loading.
  }, [pages.items.length]);
  const Tag = item ? "li" : "div";
  return (
    <Tag ref={ref as never} className="ds-more">
      {pages.loading && <Progress busy label={t("Loading…")} />}
      {pages.more && (
        <Button variant="quiet" onClick={pages.more}>
          {t("Show more")}
        </Button>
      )}
    </Tag>
  );
}

/** A live summary that opens its place ("3 in the queue", "2 unread"). */
export function Tile({
  glyph,
  icon,
  title,
  value,
  detail,
  href,
  onOpen,
  disabled,
}: {
  glyph?: GlyphName;
  icon?: IconName;
  title: string;
  value?: ReactNode;
  detail?: ReactNode;
  href?: string;
  onOpen?: () => void;
  /** Can't be used right now (it says why nearby). */
  disabled?: boolean;
}) {
  return (
    <Opener className="ds-tile" href={href} onOpen={onOpen} disabled={disabled}>
      <span className="ds-tile__head">
        {glyph ? <Glyph name={glyph} /> : icon && <Icon name={icon} />}
        <span className="ds-tile__title">{title}</span>
        <Icon name="chevron-right" size="s" />
      </span>
      {value !== undefined && <span className="ds-tile__value">{value}</span>}
      {detail && <span className="ds-tile__detail">{detail}</span>}
    </Opener>
  );
}

export type StateKind =
  "empty" | "loading" | "error" | "offline" | "not-configured" | "no-permission";
const STATE: Record<StateKind, { icon: IconName; title: () => string }> = {
  empty: { icon: "inbox", title: () => t("Nothing here yet") },
  loading: { icon: "loading", title: () => t("Loading…") },
  error: { icon: "alert", title: () => t("This didn't load") },
  offline: { icon: "offline", title: () => t("You're offline") },
  "not-configured": { icon: "plug", title: () => t("Not set up yet") },
  "no-permission": { icon: "lock", title: () => t("Not for this account") },
};

/** Every non-content state, one way: what it is, what to do. Art is optional and never moves the
 *  layout (art slot `empty.<room>` in a theme). */
export function State({
  kind,
  title,
  children,
  action,
  onRetry,
  art,
}: {
  kind: StateKind;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  onRetry?: () => void;
  art?: ReactNode;
}) {
  const look = STATE[kind];
  // The theme's picture for an empty state (slot state.empty) instead of Nox. Words stay the
  // house's own: what is empty and what to do (a theme's look is pictures, not sentences).
  const picture = useSlot("state.empty");
  if (kind === "loading" && !title)
    return (
      <div className="ds-state" data-kind={kind} role="status" aria-label={t("Loading…")}>
        <Skeleton />
      </div>
    );
  return (
    <div className="ds-state" data-kind={kind} role={kind === "error" ? "alert" : undefined}>
      <span className="ds-state__art" aria-hidden="true">
        {art ??
          (kind === "empty" ? (
            picture ? (
              <Slot id="state.empty" className="ds-state__picture" />
            ) : (
              <Mascot size="l" />
            )
          ) : (
            <Icon name={look.icon} size="l" />
          ))}
      </span>
      <h3>{title ?? look.title()}</h3>
      {children && <div className="ds-state__text">{children}</div>}
      {(action || onRetry) && (
        <div className="ds-cluster">
          {onRetry && (
            <Button icon="refresh" onClick={onRetry}>
              {t("Try again")}
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}

/** Something that stays true until it is dealt with (a toast is for what just happened). */
export function Notice({
  tone = "info",
  title,
  children,
  action,
  onDismiss,
}: {
  tone?: Tone;
  title?: ReactNode;
  children: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
}) {
  const icon: IconName =
    tone === "danger"
      ? "alert"
      : tone === "warning"
        ? "warning"
        : tone === "success"
          ? "check"
          : "info";
  return (
    <div className="ds-notice" data-tone={tone} role={tone === "danger" ? "alert" : "status"}>
      <Icon name={icon} size="s" />
      <div className="ds-notice__body">
        <div className="ds-notice__text">
          {title && <strong>{title}</strong>}
          <div>{children}</div>
        </div>
        {action && <div className="ds-notice__action">{action}</div>}
      </div>
      {onDismiss && (
        <IconButton
          icon="close"
          size="s"
          label={t("Dismiss")}
          className="ds-notice__dismiss"
          onClick={onDismiss}
        />
      )}
    </div>
  );
}

/** Something failed: what, in words, and a way to try again. Scrolls into view once. */
export function Problem({ error, onRetry }: { error?: string | null; onRetry?: () => void }) {
  const ref = useReveal<HTMLDivElement>(error);
  if (!error) return null;
  return (
    <div ref={ref}>
      <Notice
        tone="danger"
        action={
          onRetry && (
            <Button variant="quiet" size="s" icon="refresh" onClick={onRetry}>
              {t("Retry")}
            </Button>
          )
        }
      >
        {t(error)}
      </Notice>
    </div>
  );
}

/** A form that sends itself: `onSubmit` gets its fields; the button shows the work, a failure
 *  shows under the fields in words. `secondary` sits beside the submit button. */
export function Form({
  onSubmit,
  submit,
  children,
  disabled = false,
  secondary,
  reset = false,
}: {
  onSubmit: (fields: FormData) => Promise<unknown> | unknown;
  submit?: string;
  children: ReactNode;
  disabled?: boolean;
  secondary?: ReactNode;
  /** Empty the fields after a success (a composer that stays open). */
  reset?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="ds-form"
      onSubmit={async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        setBusy(true);
        try {
          await onSubmit(new FormData(form));
          setError("");
          if (reset) form.reset();
        } catch (failure) {
          setError((failure as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
      <Problem error={error} />
      <div className="ds-form__actions">
        {secondary}
        <Button type="submit" variant="primary" busy={busy} disabled={disabled}>
          {submit ?? t("Save")}
        </Button>
      </div>
    </form>
  );
}

/** One field and one button to add something to a list. */
export function QuickAdd({
  label,
  placeholder,
  onAdd,
  submit,
}: {
  label: string;
  placeholder?: string;
  onAdd: (text: string) => Promise<unknown>;
  submit?: string;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="ds-quick-add"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!value.trim()) return;
        setBusy(true);
        try {
          await onAdd(value.trim());
          setValue("");
          setError("");
        } catch (e) {
          setError(t((e as Error).message));
        } finally {
          setBusy(false);
        }
      }}
    >
      <input
        className="ds-input"
        aria-label={label}
        placeholder={placeholder ?? label}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        required
      />
      <Button type="submit" variant="primary" icon="add" busy={busy}>
        {submit ?? t("Add")}
      </Button>
      {error && (
        <p className="ds-field__error" role="alert">
          <Icon name="alert" size="s" />
          {error}
        </p>
      )}
    </form>
  );
}

export type SettingsGroup = {
  label: string;
  items: { id: string; label: string; icon: IconName; badge?: ReactNode }[];
};

/** Settings as a list of places and the chosen one beside it (desktop), or the list then the
 *  place with a way back (phone). No walls of tabs. `value` "" shows the overview. */
export function SettingsLayout({
  label,
  groups,
  value,
  onChange,
  overview,
  mapped = false,
  children,
}: {
  label: string;
  groups: SettingsGroup[];
  value: string;
  onChange: (id: string) => void;
  overview?: ReactNode;
  /** The overview links every place itself: phones show it instead of the list. */
  mapped?: boolean;
  children: ReactNode;
}) {
  const current = groups.flatMap((g) => g.items).find((item) => item.id === value);
  const group = groups.find((g) => g.items.includes(current!));
  return (
    <div
      className="ds-settings"
      data-open={current ? "" : undefined}
      data-mapped={mapped || undefined}
    >
      <nav className="ds-settings__nav" aria-label={label}>
        {groups.map((group) => (
          <div key={group.label} className="ds-settings__group">
            <h2>{group.label}</h2>
            <ul>
              {group.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-current={item.id === value ? "page" : undefined}
                    onClick={() => onChange(item.id)}
                  >
                    <Icon name={item.icon} size="s" />
                    <span className="ds-settings__label">{item.label}</span>
                    {item.badge}
                    <Icon name="chevron-right" size="s" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="ds-settings__detail">
        {current ? (
          <>
            <Button
              variant="quiet"
              icon="back"
              className="ds-settings__back"
              onClick={() => onChange("")}
            >
              {label}
            </Button>
            {/* On a phone: the other places of this group, one tap away. */}
            {group && group.items.length > 1 && (
              <div className="ds-settings__siblings">
                <SubNav
                  label={group.label}
                  value={value}
                  onChange={onChange}
                  items={group.items.map(({ id, label, icon }) => ({ id, label, icon }))}
                />
              </div>
            )}
            {children}
          </>
        ) : (
          overview
        )}
      </div>
    </div>
  );
}

/** What an action will do, as the server describes it: names and values, nested as needed. */
export function ReviewDetails({ value }: { value: Record<string, any> }) {
  return (
    <dl className="ds-details">
      {Object.entries(value).map(([k, v]) => (
        <div key={k}>
          <dt>{k.replaceAll("_", " ")}</dt>
          <dd>
            {v === null ? (
              t("Not specified")
            ) : Array.isArray(v) ? (
              <ul>
                {v.map((x, i) => (
                  <li key={i}>
                    {x && typeof x === "object" ? <ReviewDetails value={x} /> : String(x)}
                  </li>
                ))}
              </ul>
            ) : typeof v === "object" ? (
              <ReviewDetails value={v} />
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A room that crashes shows this instead of taking the whole app down. */
export class PageGuard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error(error);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Notice
        tone="danger"
        action={
          <>
            <Button variant="quiet" size="s" onClick={() => history.back()}>
              {t("Go back")}
            </Button>
            <Button variant="quiet" size="s" icon="refresh" onClick={() => location.reload()}>
              {t("Reload")}
            </Button>
          </>
        }
      >
        {t("This page ran into a problem and could not open.")}
      </Notice>
    );
  }
}

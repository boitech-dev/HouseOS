// Things that show rather than act: text, status, people, progress, surfaces and media frames.
import { useId, useState, type CSSProperties, type ElementType, type ReactNode } from "react";
import { placeholderUrl, seedOf } from "../pixel";
import { Icon, AvatarPicture, AVATAR_NAMES, usePixels, type IconName } from "./icons";
import { getLanguage } from "../i18n";
import type { ThemeInfo } from "./generated/themes";
import { useTheme } from "./theme";

export type TextStyle =
  | "display-xl" | "display-l" | "display-m" | "title-l" | "title-m" | "title-s"
  | "body-l" | "body-m" | "body-s" | "action" | "label" | "caption" | "numeric"; // prettier-ignore

/** Text in one of the theme's styles (never a size). */
export function Text({
  as: Tag = "span",
  style: textStyle = "body-m",
  tone,
  children,
  className,
}: {
  as?: ElementType;
  style?: TextStyle;
  tone?: "muted" | "subtle" | "accent" | "danger";
  children: ReactNode;
  className?: string;
}) {
  return (
    <Tag
      className={"ds-text" + (className ? " " + className : "")}
      data-style={textStyle}
      data-tone={tone}
    >
      {children}
    </Tag>
  );
}

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info" | "private";
const MARK: Record<Tone, IconName> = {
  neutral: "dot", accent: "dot", success: "check", warning: "warning", danger: "alert", info: "info", private: "lock",
}; // prettier-ignore

/** A state, always as a mark and a word (never colour alone). */
export function Status({
  tone = "neutral",
  children,
  busy,
}: {
  tone?: Tone;
  children: ReactNode;
  busy?: boolean;
}) {
  return (
    <span className="ds-status" data-tone={tone} data-busy={busy || undefined}>
      <Icon name={busy ? "loading" : MARK[tone]} size="s" />
      <span>{children}</span>
    </span>
  );
}

/** A small count or word next to something (unread messages, "new"). */
export function Badge({
  tone = "accent",
  children,
  label,
}: {
  tone?: Tone;
  children: ReactNode;
  label?: string;
}) {
  return (
    <span className="ds-badge tabular" data-tone={tone} aria-label={label}>
      {children}
    </span>
  );
}

/** A person: their picture in their colour, and whether they're home. An empty `name` makes it
 *  decoration (the name is already written beside it). */
/** A resident's colour (the theme's color.person.1–8): stable per person, the same everywhere. */
export function tone(id?: string | null) {
  let hash = 0;
  for (const char of String(id || "")) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return `var(--c-person-${(Math.abs(hash) % 8) + 1})`;
}

export function Avatar({
  name,
  picture,
  tone,
  size = "m",
  home,
  decorative = false,
}: {
  name: string;
  picture?: string;
  tone?: string;
  size?: "s" | "m" | "l";
  home?: boolean;
  /** The name is written beside it: show the initials, don't announce them twice. */
  decorative?: boolean;
}) {
  const named = !!name && !decorative;
  return (
    <span
      className="ds-avatar"
      data-size={size}
      data-home={home || undefined}
      role={named ? "img" : undefined}
      aria-label={named ? name : undefined}
      aria-hidden={named ? undefined : true}
      style={tone ? ({ "--tone": tone } as CSSProperties) : undefined}
    >
      {chosen(picture) ? (
        <AvatarPicture
          name={picture}
          scale={size === "l" ? 3 : size === "s" ? 1 : 2}
          box={size === "l" ? 64 : size === "s" ? 28 : 40}
        />
      ) : (
        // Drawn by CSS (::before), so the letters never join a label's text.
        <span className="ds-avatar__initials" data-initials={initials(name)} aria-hidden="true" />
      )}
    </span>
  );
}

/** A picture the person picked. The crest is what the server reports when nobody chose, so it
 *  shows their initials instead (six identical crests say nothing about who is home). */
const chosen = (picture?: string) =>
  !!picture && picture !== "crest" && (AVATAR_NAMES as string[]).includes(picture);

/** "Ada Lovelace" → "AL"; one word → its first letter; what follows " · " is not the name. */
export const initials = (name = "") =>
  name
    .split(" · ")[0]
    .split(/[\s-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => [...word][0].toUpperCase())
    .join("");

/** How far along: `value` 0–1, or `busy` while the amount is unknown. Stepped for a count of parts. */
export function Progress({
  value = 0,
  busy = false,
  label,
  steps,
}: {
  value?: number;
  busy?: boolean;
  label: string;
  steps?: number;
}) {
  const share = Math.max(0, Math.min(1, value));
  return (
    <div
      className="ds-progress"
      data-busy={busy || undefined}
      data-steps={steps || undefined}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={busy ? undefined : Math.round(share * 100)}
      style={{ "--value": share, "--steps": steps ?? 1 } as CSSProperties}
    >
      <span />
    </div>
  );
}

/** A place holding the shape of what is loading. */
export function Skeleton({ lines = 3, media = false }: { lines?: number; media?: boolean }) {
  return (
    <div className="ds-skeleton" aria-hidden="true" data-media={media || undefined}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} />
      ))}
    </div>
  );
}

export const Divider = () => <hr className="ds-divider" />;

export const Kbd = ({ children }: { children: ReactNode }) => (
  <kbd className="ds-kbd">{children}</kbd>
);

/** A short hint shown on hover and focus, read by screen readers with the control. */
export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  const id = useId();
  return (
    <span className="ds-tooltip" aria-describedby={id}>
      {children}
      <span role="tooltip" id={id}>
        {text}
      </span>
    </span>
  );
}

export type Material = "surface" | "raised" | "sunken" | "overlay" | "inverse" | "paper" | "screen";

/** A ground for grouping, in one of the theme's materials. Most content needs none. */
export function Surface({
  material = "surface",
  as: Tag = "div",
  children,
  className,
  ...rest
}: { material?: Material; as?: ElementType; children: ReactNode; className?: string } & Record<
  string,
  unknown
>) {
  return (
    <Tag
      {...rest}
      className={"ds-surface" + (className ? " " + className : "")}
      data-material={material}
    >
      {children}
    </Tag>
  );
}

/** A poster or cover in true colour, over a placeholder in the theme's own terms: a dithered
 *  night in a pixel theme, a flat square with a cover's or a poster's mark otherwise. */
export function Media({
  src,
  alt,
  ratio = "2 / 3",
  className,
}: {
  src?: string | null;
  alt: string;
  ratio?: string;
  className?: string;
}) {
  const [loaded, setLoaded] = useState("");
  useTheme();
  const pixels = usePixels();
  return (
    <div
      className={"ds-media" + (className ? " " + className : "")}
      style={
        {
          aspectRatio: ratio,
          "--placeholder": pixels
            ? `url("${placeholderUrl("art" + (seedOf(alt || src || "art") % 8))}")`
            : "none",
        } as CSSProperties
      }
    >
      {!pixels && loaded !== src && (
        <span className="ds-media__mark" aria-hidden="true">
          <Icon name={ratio === "1 / 1" ? "music" : "film"} size="l" />
        </span>
      )}
      {src && (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          data-loaded={loaded === src || undefined}
          ref={(img) => {
            if (img?.complete && img.naturalWidth) setLoaded(src);
          }}
          onLoad={() => setLoaded(src)}
        />
      )}
    </div>
  );
}

/** A theme drawn in itself, whatever the page's theme: its colours, its letters, its accent. */
export function ThemeSpecimen({ theme, scheme }: { theme: ThemeInfo; scheme?: string }) {
  const shown = scheme && theme.schemes.includes(scheme as never) ? scheme : theme.schemes[0];
  return (
    <span className="ds-scope ds-specimen" data-theme={theme.id} data-scheme={shown}>
      <span className="ds-specimen__swatches" aria-hidden="true">
        {(theme.swatches[shown as keyof typeof theme.swatches] || [])
          .slice(0, 5)
          .map((colour, i) => (
            <i key={i} style={{ "--swatch": colour } as CSSProperties} />
          ))}
      </span>
      <strong className="ds-specimen__name">
        {getLanguage() === "fr" ? theme.names.fr : theme.names.en}
      </strong>
      <small className="ds-specimen__about">
        {getLanguage() === "fr" ? theme.description.fr : theme.description.en}
      </small>
      <span className="ds-specimen__sample" aria-hidden="true">
        <b>Aa</b>
        <i />
        <i />
      </span>
    </span>
  );
}

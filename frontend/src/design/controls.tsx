// Controls: every button, field, choice and slider in HouseOS. Text passed in is already
// translated (t() at the call site); states are data-* attributes that themes and tests can read.
import {
  cloneElement,
  useEffect,
  useId,
  useRef,
  useState,
  type AnchorHTMLAttributes,
  type ButtonHTMLAttributes,
  type ComponentProps,
  type CSSProperties,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { t } from "../i18n";
import { Glyph, Icon, type GlyphName, type IconName } from "./icons";

type Size = "s" | "m" | "l";
export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger" | "link";

export type ButtonProps = {
  variant?: ButtonVariant;
  size?: Size;
  icon?: IconName;
  /** An identity mark instead of an icon (transport): pixel or line, as the theme draws them. */
  glyph?: GlyphName;
  iconEnd?: IconName;
  /** Working: the button shows it and can't be pressed again. */
  busy?: boolean;
  /** Toggle buttons: pressed or not (aria-pressed). */
  pressed?: boolean;
  /** Stretch to the width of its place. */
  wide?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>;

/** Choose files with a button: the browser's own file field can't take the theme or the person's
 *  language. The hidden field carries the label, so assistive tech and tests find it by name. */
export function FileButton({
  label,
  accept,
  multiple = false,
  onFiles,
  icon = "upload",
  iconOnly = false,
  ...button
}: {
  label: string;
  accept?: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
  /** Only the icon (the label is its name), for tight rows like a composer. */
  iconOnly?: boolean;
} & Omit<ButtonProps, "onClick" | "children">) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        hidden
        aria-label={label}
        accept={accept}
        multiple={multiple}
        disabled={button.disabled}
        onChange={(e) => {
          const files = [...(e.currentTarget.files ?? [])];
          e.currentTarget.value = "";
          if (files.length) onFiles(files);
        }}
      />
      {iconOnly ? (
        <IconButton
          {...button}
          icon={icon ?? "upload"}
          label={label}
          onClick={() => input.current?.click()}
        />
      ) : (
        <Button {...button} icon={icon} onClick={() => input.current?.click()}>
          {label}
        </Button>
      )}
    </>
  );
}

/** One primary per view; the rest step down to secondary, then quiet (docs/design/SYSTEM.md). */
export function Button({
  variant = "secondary",
  size = "m",
  icon,
  glyph,
  iconEnd,
  busy,
  pressed,
  wide,
  children,
  type = "button",
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={"ds-button" + (rest.className ? " " + rest.className : "")}
      data-variant={variant}
      data-size={size}
      data-busy={busy || undefined}
      data-wide={wide || undefined}
      aria-pressed={pressed}
      aria-busy={busy || undefined}
      disabled={disabled || busy}
    >
      {busy ? (
        <Spinner />
      ) : glyph ? (
        <Glyph name={glyph} size={size === "l" ? "l" : "m"} />
      ) : (
        icon && <Icon name={icon} size={size === "l" ? "m" : "s"} />
      )}
      {children && <span className="ds-button__label">{children}</span>}
      {iconEnd && <Icon name={iconEnd} size={size === "l" ? "m" : "s"} />}
    </button>
  );
}

/** An icon alone: its label is required (read aloud, and shown as a hint on hover). */
export function IconButton({
  icon,
  glyph,
  label,
  variant = "quiet",
  size = "m",
  ...rest
}: {
  icon?: IconName;
  glyph?: GlyphName;
  label: string;
  variant?: ButtonVariant;
  size?: Size;
} & Omit<ButtonProps, "children" | "icon" | "glyph">) {
  return (
    <Button
      {...rest}
      variant={variant}
      size={size}
      icon={icon}
      glyph={glyph}
      aria-label={label}
      title={label}
      data-icon-only=""
    />
  );
}

/** A link that looks like a button: downloads, exports, a file opened in a new tab. Text beside
 *  the icon, or `label` alone (read aloud) for an icon-only link. */
export function LinkButton({
  href,
  variant = "secondary",
  size = "m",
  icon,
  label,
  children,
  ...rest
}: {
  href: string;
  variant?: ButtonVariant;
  size?: Size;
  icon?: IconName;
  label?: string;
  children?: ReactNode;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return (
    <a
      {...rest}
      href={href}
      className="ds-button"
      data-variant={variant}
      data-size={size}
      data-icon-only={children ? undefined : ""}
      aria-label={label}
      title={label}
    >
      {icon && <Icon name={icon} size={size === "l" ? "m" : "s"} />}
      {children && <span className="ds-button__label">{children}</span>}
    </a>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span
      className="ds-spinner"
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}

/** A label, the control, a hint and an error, wired together for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
  inline = false,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string;
  children: ReactElement;
  /** Label beside the control (switches, checkboxes). */
  inline?: boolean;
}) {
  const id = useId();
  const described =
    [hint && id + "-hint", error && id + "-error"].filter(Boolean).join(" ") || undefined;
  const control = cloneElement(children as ReactElement<any>, {
    id: (children.props as any).id ?? id,
    "aria-describedby": described,
    "aria-invalid": error ? true : undefined,
  });
  return (
    <div
      className="ds-field"
      data-inline={inline || undefined}
      data-invalid={error ? "" : undefined}
    >
      <label className="ds-field__label" htmlFor={(children.props as any).id ?? id}>
        {label}
      </label>
      {control}
      {hint && (
        <p className="ds-field__hint" id={id + "-hint"}>
          {hint}
        </p>
      )}
      {error && (
        <p className="ds-field__error" id={id + "-error"} role="alert">
          <Icon name="alert" size="s" />
          {error}
        </p>
      )}
    </div>
  );
}

export function Input(props: ComponentProps<"input">) {
  return (
    <input {...props} className={"ds-input" + (props.className ? " " + props.className : "")} />
  );
}

export function Textarea(props: ComponentProps<"textarea">) {
  return (
    <textarea
      {...props}
      className={"ds-input ds-textarea" + (props.className ? " " + props.className : "")}
    />
  );
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="ds-select">
      <select {...props} className="ds-input">
        {children}
      </select>
      <Icon name="chevron-down" size="s" />
    </span>
  );
}

/** A text field with suggestions (the browser's own list, keyboard and screen-reader ready). */
export function Combobox({
  options,
  ...props
}: { options: string[] } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <>
      <Input {...props} list={id} autoComplete="off" />
      <datalist id={id}>
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </>
  );
}

const MASKABLE = typeof CSS !== "undefined" && CSS.supports?.("-webkit-text-security", "disc");
/** A key or token: masked, with a button to show it. Not a password field, so browsers and
 *  password managers don't offer saved logins or generate one. */
export function SecretInput(props: ComponentProps<"input">) {
  const [shown, setShown] = useState(false);
  return (
    <span className="ds-secret">
      <Input
        {...props}
        type={shown || MASKABLE ? "text" : "password"}
        data-masked={!shown || undefined}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        data-1p-ignore=""
        data-lpignore="true"
        data-bwignore=""
        data-form-type="other"
      />
      <IconButton
        icon={shown ? "hide" : "show"}
        label={shown ? t("Hide") : t("Show")}
        pressed={shown}
        onClick={() => setShown((value) => !value)}
      />
    </span>
  );
}

/** A search field: the icon, and a clear button once there is text. */
export function SearchInput({
  value,
  onChange,
  label,
  ...rest
}: { value: string; onChange: (value: string) => void; label: string } & Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange"
>) {
  return (
    <span className="ds-search">
      <Icon name="search" size="s" />
      <Input
        {...rest}
        type="search"
        value={value}
        aria-label={label}
        placeholder={rest.placeholder ?? label}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button
          type="button"
          className="ds-search__clear"
          aria-label={t("Clear")}
          onClick={() => onChange("")}
        >
          <Icon name="close" size="s" />
        </button>
      )}
    </span>
  );
}

/** On/off, applied at once (use Checkbox for choices that are saved with a form). */
export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (on: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="ds-switch" data-disabled={disabled || undefined}>
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        aria-describedby={hint ? id + "-hint" : undefined}
        onChange={(e) => onChange(e.target.checked)}
      />
      <label htmlFor={id}>
        <span>{label}</span>
        {hint && (
          <small id={id + "-hint"} className="ds-field__hint">
            {hint}
          </small>
        )}
      </label>
    </div>
  );
}

export function Checkbox({
  label,
  hint,
  hideLabel,
  ...props
}: {
  label: ReactNode;
  hint?: ReactNode;
  hideLabel?: boolean;
} & ComponentProps<"input">) {
  const id = useId();
  return (
    <div className="ds-check" data-bare={hideLabel || undefined}>
      <input {...props} id={props.id ?? id} type="checkbox" />
      <label htmlFor={props.id ?? id}>
        <span className={hideLabel ? "visually-hidden" : undefined}>{label}</span>
        {hint && <small className="ds-field__hint">{hint}</small>}
      </label>
    </div>
  );
}

export function Radio({
  label,
  ...props
}: { label: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="ds-check" data-radio="">
      <input {...props} id={props.id ?? id} type="radio" />
      <label htmlFor={props.id ?? id}>{label}</label>
    </div>
  );
}

export type Option<T extends string = string> = { value: T; label: ReactNode; icon?: IconName };

/** A few exclusive choices side by side (a radio group underneath). */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  size = "m",
  disabled = false,
}: {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: Size;
  disabled?: boolean;
}) {
  const name = useId();
  return (
    <div className="ds-segmented" role="radiogroup" aria-label={label} data-size={size}>
      {options.map((option) => (
        <label key={option.value} data-selected={option.value === value || undefined}>
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={option.value === value}
            disabled={disabled}
            onChange={() => onChange(option.value)}
          />
          {option.icon && <Icon name={option.icon} size="s" />}
          <span>{option.label}</span>
        </label>
      ))}
    </div>
  );
}

/** A range: `commit` fires once when you let go (pointer or keys), so devices get one command. */
export function Slider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  onCommit,
  showLabel = false,
  format,
  icon,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange?: (value: number) => void;
  onCommit?: (value: number) => void;
  showLabel?: boolean;
  format?: (value: number) => string;
  /** A small picture before the track, standing in for a visible label (volume, brightness). */
  icon?: IconName;
}) {
  // While dragging, and after letting go until the device reports its new value, the slider shows
  // what you chose (no snap back while the device answers).
  const [draft, setDraft] = useState<number | null>(null);
  const sent = useRef(false);
  useEffect(() => {
    if (!sent.current) return;
    sent.current = false;
    setDraft(null);
  }, [value]);
  const shown = draft ?? value;
  const commit = (next: number) => {
    sent.current = true;
    onCommit?.(next);
  };
  return (
    <label
      className="ds-slider"
      data-icon={icon ? "" : undefined}
      style={{ "--value": (shown - min) / (max - min || 1) } as CSSProperties}
    >
      <span className={showLabel ? "ds-field__label" : "visually-hidden"}>{label}</span>
      {icon && <Icon name={icon} size="s" />}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={shown}
        aria-label={label}
        aria-valuetext={format?.(shown)}
        onChange={(e) => {
          const next = Number(e.target.value);
          setDraft(next);
          onChange?.(next);
        }}
        onPointerUp={(e) => commit(Number(e.currentTarget.value))}
        onKeyUp={(e) => {
          if (
            [
              "ArrowLeft",
              "ArrowRight",
              "ArrowUp",
              "ArrowDown",
              "Home",
              "End",
              "PageUp",
              "PageDown",
            ].includes(e.key)
          )
            commit(Number(e.currentTarget.value));
        }}
      />
      {format && <output className="tabular">{format(shown)}</output>}
    </label>
  );
}

// A light's own colours (a bulb, not the theme): hue in degrees, full colour, as #rrggbb.
const LIGHT_HUES: [string, number][] = [
  ["Red", 0],
  ["Orange", 28],
  ["Yellow", 52],
  ["Green", 120],
  ["Cyan", 185],
  ["Blue", 225],
  ["Purple", 275],
  ["Pink", 320],
];
const hueHex = (hue: number) =>
  "#" +
  [0, 8, 4]
    .map((n) => {
      const k = (n + hue / 30) % 12;
      const level = 0.5 - 0.5 * Math.max(-1, Math.min(k - 3, 9 - k, 1));
      return Math.round(level * 255)
        .toString(16)
        .padStart(2, "0");
    })
    .join("");

/** The colour of something in the room (a bulb): common light colours, or any other. The value
 *  is #rrggbb; the choice is sent when picked (the browser's picker: when it closes). */
export function ColorField({
  label,
  value,
  onCommit,
  disabled,
}: {
  label: string;
  value?: string;
  onCommit: (hex: string) => void;
  disabled?: boolean;
}) {
  const other = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const input = other.current;
    const done = () => input && onCommit(input.value);
    input?.addEventListener("change", done);
    return () => input?.removeEventListener("change", done);
  }, [onCommit]);
  const current = value?.toLowerCase();
  return (
    <div className="ds-color" role="group" aria-label={label}>
      <span className="ds-field__label">{label}</span>
      <div className="ds-color__swatches">
        {LIGHT_HUES.map(([name, hue]) => {
          const hex = hueHex(hue);
          return (
            <button
              type="button"
              key={name}
              className="ds-color__swatch"
              style={{ "--swatch": hex } as CSSProperties}
              aria-label={t(name)}
              aria-pressed={current === hex}
              disabled={disabled}
              onClick={() => onCommit(hex)}
            />
          );
        })}
        <label className="ds-color__other" style={{ "--swatch": value || hueHex(40) } as CSSProperties}>
          <input
            ref={other}
            type="color"
            defaultValue={value || hueHex(40)}
            aria-label={t("Another colour")}
            disabled={disabled}
          />
          <Icon name="palette" size="s" />
        </label>
      </div>
    </div>
  );
}

/** Any CSS colour (oklch, a name, a var() already resolved) as #rrggbb, the only form the
 *  browser's colour picker takes: the browser paints it on a pixel and reads it back. */
export function toHex(css: string): string {
  if (/^#[0-9a-f]{6}$/i.test(css)) return css.toLowerCase();
  const pixel = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!pixel) return css;
  pixel.fillStyle = css;
  pixel.fillRect(0, 0, 1, 1);
  const [r, g, b] = pixel.getImageData(0, 0, 1, 1).data;
  return "#" + [r, g, b].map((n) => n.toString(16).padStart(2, "0")).join("");
}

/** A theme colour: its swatch (any CSS colour, oklch too) and the browser's picker, which gives
 *  #rrggbb. The choice is sent when the picker closes. */
export function ColorInput({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (hex: string) => void;
  hint?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const box = input.current;
    const done = () => box && onChange(box.value);
    box?.addEventListener("change", done);
    return () => box?.removeEventListener("change", done);
  }, [onChange]);
  const hex = toHex(value);
  return (
    <label className="ds-colorinput">
      <span className="ds-colorinput__swatch" style={{ "--swatch": value } as CSSProperties} />
      <span className="ds-colorinput__text">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </span>
      <input ref={input} type="color" key={hex} defaultValue={hex} aria-label={label} />
    </label>
  );
}

/** One colour out of a few, as swatches (a pixel editor's inks): a radio group, arrow keys. */
export function SwatchPicker({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: string; label: string; color: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  const name = useId();
  return (
    <div className="ds-swatches" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <label key={option.value} className="ds-swatches__one" title={option.label}>
          <input
            type="radio"
            name={name}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            aria-label={option.label}
          />
          <span style={{ "--swatch": option.color } as CSSProperties} />
        </label>
      ))}
    </div>
  );
}

export type ChipKind = "filter" | "tag" | "person" | "count";

/** One chip for everything: a filter you toggle, a tag, a person, a count; removable if asked.
 *  Chips filter or label; they never navigate (use SubNav) and never act (use Button). */
export function Chip({
  kind = "tag",
  selected,
  onToggle,
  onRemove,
  icon,
  tone,
  count,
  children,
}: {
  kind?: ChipKind;
  selected?: boolean;
  onToggle?: () => void;
  onRemove?: () => void;
  icon?: IconName;
  /** A person's colour (tone(id)), for person chips. */
  tone?: string;
  count?: number;
  children: ReactNode;
}) {
  const inner = (
    <>
      {selected && onToggle && !icon ? <Icon name="check" size="s" /> : icon && <Icon name={icon} size="s" />}
      <span className="ds-chip__label">{children}</span>
      {count !== undefined && <span className="ds-chip__count tabular">{count}</span>}
    </>
  );
  const style = tone ? ({ "--tone": tone } as CSSProperties) : undefined;
  return (
    <span className="ds-chip" data-kind={kind} data-selected={selected || undefined} style={style}>
      {onToggle ? (
        <button
          type="button"
          className="ds-chip__main"
          aria-pressed={!!selected}
          onClick={onToggle}
        >
          {inner}
        </button>
      ) : (
        <span className="ds-chip__main">{inner}</span>
      )}
      {onRemove && (
        <button
          type="button"
          className="ds-chip__remove"
          aria-label={t("Remove") + " " + String(children)}
          onClick={onRemove}
        >
          <Icon name="close" size="s" />
        </button>
      )}
    </span>
  );
}

/** A labelled row of chips that wraps. */
export function ChipGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ds-chips" role="group" aria-label={label}>
      {children}
    </div>
  );
}

/** Focus stays in the element (for sheets and menus): Tab and Shift+Tab wrap around. */
export function useFocusTrap<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const onKeyDown = (e: KeyboardEvent<T>) => {
    if (e.key !== "Tab" || !ref.current) return;
    const controls = [
      ...ref.current.querySelectorAll<HTMLElement>(
        'button, input:not([type="hidden"]), select, textarea, a[href], summary, [tabindex]:not([tabindex="-1"])',
      ),
    ].filter(
      (el) =>
        el.getClientRects().length > 0 &&
        !el.matches(":disabled") &&
        !el.closest("details:not([open]) > :not(summary)"),
    );
    const first = controls[0],
      last = controls[controls.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  };
  return [ref, onKeyDown] as const;
}

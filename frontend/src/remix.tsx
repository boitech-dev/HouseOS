// Remix (/workshop/remix?id=…): make a theme by hand, no AI needed. Colours, type, corners,
// surfaces, parts, pictures, pixel pieces and words, with the app drawn live beside them. Every
// change is previewed through the theme kit (compiled, not kept); Save keeps it only when every
// check passes (remix.py on the server; the same checks as everywhere).
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { api, useData, type Obj } from "./api";
import { t } from "./i18n";
import { go } from "./nav";
import {
  Badge,
  Button,
  Cluster,
  ColorInput,
  Disclosure,
  Field,
  FileButton,
  Input,
  Page,
  PageHeader,
  Problem,
  Section,
  Segmented,
  Select,
  Slider,
  Stack,
  State,
  SubNav,
  Switch,
  SwatchPicker,
  Text,
  toast,
  toHex,
  token,
} from "./design";
import { builtInPiece } from "./design/icons";
import { setInstalled, type Installed } from "./design/theme";
import { PARTS, PIECES, SLOTS, type ThemeInfo } from "./design/generated/themes";
import { ThemePreview, handToNox } from "./theme_preview";
import "./workshop.css";

type Tree = Record<string, any>;
type Draft = {
  theme: Tree;
  tokens: Tree;
  tokens_light?: Tree | null;
  tokens_dark?: Tree | null;
  flavor?: Tree | null;
  sprites?: Tree | null;
};
type Preview = { css?: string; info?: ThemeInfo; passed?: boolean; failures?: string[] };

const SEEDS: [string, string, string][] = [
  ["neutral", "Neutral", "Grounds and text"],
  ["accent", "Accent", "The one colour that acts"],
  ["success", "Success", "Done, all good"],
  ["warning", "Warning", "Careful"],
  ["danger", "Danger", "Stop, failed"],
  ["info", "Info", "For your information"],
  ["private", "Private", "Private things"],
];
const ROOMS = [
  "home",
  "listen",
  "watch",
  "house",
  "inbox",
  "files",
  "smart-home",
  "ask",
  "space",
  "me",
  "control",
  "party",
];
const ROOM_NAMES: Record<string, string> = {
  home: "Home", listen: "Listen", watch: "Watch", house: "House", inbox: "Inbox", files: "Files",
  "smart-home": "Smart home", ask: "Ask", space: "Space", me: "Me", control: "Control", party: "Party",
}; // prettier-ignore
const PART_NAMES: Record<string, string> = {
  header: "Header",
  panel: "Panel",
  dock: "Dock",
  nowbar: "The Now bar",
};
const VARIANT_NAMES: Record<string, string> = {
  plain: "plain", banner: "banner", ribbon: "ribbon", card: "card", flat: "flat",
  outlined: "outlined", flush: "flush", floating: "floating", docked: "docked",
}; // prettier-ignore
const RADII: [string, string, number][] = [
  ["control", "Buttons and fields", 6],
  ["card", "Cards and panels", 10],
  ["sheet", "Sheets", 14],
  ["chip", "Chips", 999],
  ["media", "Posters and covers", 6],
  ["avatar", "People's pictures", 999],
];
const PART_COLOURS: [string, string][] = [
  ["part.page.bg", "The page"],
  ["part.status.bg", "The top bar"],
  ["part.rail.bg", "The rail"],
  ["part.dock.bg", "The dock (phones)"],
  ["part.panel.bg", "Panels"],
  ["part.nowbar.bg", "The Now bar"],
  ["part.sheet.bg", "Sheets"],
];
// The sprite colours, by the letters the pixel editor paints with (the same as sprites.ts).
const INKS: [string, string][] = [
  ["k", "outline"], ["n", "dark"], ["l", "mid-dark"], ["L", "mid"], ["m", "mist"], ["c", "light"],
  ["C", "light-dim"], ["e", "accent"], ["E", "accent-hi"], ["r", "accent-deep"], ["v", "familiar"],
  ["V", "familiar-mid"], ["w", "familiar-deep"], ["g", "good"], ["p", "alert"], ["P", "paper"], ["i", "ink"],
]; // prettier-ignore
const TITLES = ["dj", "explorer", "night_owl", "early_bird", "weekend", "genre_guardian", "broken_record", "marathon", "radio_host", "task_hero", "grocery_runner", "planner", "wall_poet", "courier", "curator"]; // prettier-ignore

const SECTIONS = ["colours", "type", "shape", "parts", "art", "pixels", "words"] as const;
type SectionId = (typeof SECTIONS)[number];

/** A token's value in a DTCG tree ("seed.accent" → its $value), or undefined. */
function read(tree: Tree | null | undefined, path: string) {
  let node: any = tree;
  for (const key of path.split(".")) node = node?.[key];
  return node?.$value;
}
/** The tree with one token set (a copy; the editor never changes what React holds). */
function write(tree: Tree | null | undefined, path: string, value: unknown): Tree {
  const copy: Tree = structuredClone(tree ?? {});
  const keys = path.split(".");
  let node = copy;
  for (const key of keys.slice(0, -1)) node = node[key] ??= {};
  const last = keys[keys.length - 1];
  if (value === undefined) delete node[last];
  else node[last] = { ...(node[last] ?? {}), $value: value };
  return copy;
}

export function Remix() {
  const id = new URLSearchParams(location.search).get("id") || "";
  const loaded = useData<Obj>(id ? "/themes/remix/" + encodeURIComponent(id) : null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [art, setArt] = useState<string[]>([]);
  const [section, setSection] = useState<SectionId>("colours");
  const [preview, setPreview] = useState<Preview>({});
  const [saving, setSaving] = useState(false);
  const [changed, setChanged] = useState(false);
  useEffect(() => {
    if (!loaded.data || draft) return;
    const { theme, tokens, tokens_light, tokens_dark, flavor, sprites } = loaded.data;
    setDraft({ theme, tokens, tokens_light, tokens_dark, flavor, sprites });
    setArt(loaded.data.art || []);
  }, [loaded.data, draft]);
  const change = useCallback((next: (draft: Draft) => Draft) => {
    setDraft((current) => current && next(current));
    setChanged(true);
  }, []);
  // The live preview: compiled a moment after each change, never kept.
  useEffect(() => {
    if (!draft) return;
    let live = true;
    const wait = setTimeout(() => {
      api<Preview>("/themes/remix/" + encodeURIComponent(id) + "/preview", "POST", draft)
        .then((result) => live && setPreview(result))
        .catch((e) => live && setPreview({ passed: false, failures: [(e as Error).message] }));
    }, 350);
    return () => {
      live = false;
      clearTimeout(wait);
    };
  }, [draft, id]);
  useEffect(() => {
    if (!preview.css) return;
    const style = document.createElement("style");
    style.dataset.remixPreview = id;
    style.textContent = "@layer theme {\n" + preview.css + "\n}";
    document.head.append(style);
    return () => style.remove();
  }, [preview.css, id]);
  if (!id) return <State kind="empty" title={t("Pick a theme to remix in the workshop.")} />;
  if (loaded.error)
    return (
      <Page>
        <Problem error={loaded.error} onRetry={loaded.reload} />
      </Page>
    );
  if (!draft) return <State kind="loading" />;
  const scheme = draft.theme.schemes?.[0] || "dark";
  const save = async () => {
    setSaving(true);
    try {
      const result = await api("/themes/remix/" + encodeURIComponent(id), "PUT", draft);
      if (!result.passed) {
        toast(
          t("Not saved: {n} checks to fix.").replace("{n}", String(result.failures?.length ?? 1)),
          {
            tone: "danger",
          },
        );
        return false;
      }
      setChanged(false);
      setInstalled((await api<{ items: Installed[] }>("/themes")).items);
      toast(t("Saved."), { tone: "success" });
      return true;
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
      return false;
    } finally {
      setSaving(false);
    }
  };
  const wear = async () => {
    if (changed && !(await save())) return;
    await api("/preferences", "PUT", { theme: id });
    dispatchEvent(new Event("house-settings-updated"));
    toast(t("You're wearing it."), { tone: "success" });
  };
  const reload = async () => {
    const fresh = await api<Obj>("/themes/remix/" + encodeURIComponent(id));
    setDraft({
      theme: fresh.theme,
      tokens: fresh.tokens,
      tokens_light: fresh.tokens_light,
      tokens_dark: fresh.tokens_dark,
      flavor: fresh.flavor,
      sprites: fresh.sprites,
    });
    setArt(fresh.art || []);
  };
  const failures = preview.failures ?? [];
  return (
    <Page width="wide">
      <PageHeader
        room="me"
        kicker={t("Remix")}
        title={draft.theme.names?.en || id}
        actions={
          <Cluster space={2}>
            <Button variant="quiet" icon="back" onClick={() => go("/workshop")}>
              {t("Workshop")}
            </Button>
            <Button
              icon="sparkles"
              onClick={async () => {
                if (!changed || (await save())) handToNox(id, draft.theme.names?.en || id);
              }}
            >
              {t("Hand it to Nox")}
            </Button>
            <Button icon="show" onClick={() => void wear()}>
              {t("Wear it")}
            </Button>
            <Button variant="primary" busy={saving} disabled={!changed} onClick={() => void save()}>
              {changed ? t("Save") : t("Saved")}
            </Button>
          </Cluster>
        }
      />
      <div className="remix">
        <div className="remix__controls">
          <SubNav
            label={t("What to change")}
            value={section}
            onChange={(next) => setSection(next as SectionId)}
            items={[
              { id: "colours", label: t("Colours"), icon: "palette" },
              { id: "type", label: t("Type"), icon: "file-text" },
              { id: "shape", label: t("Shape"), icon: "sliders" },
              { id: "parts", label: t("Parts"), icon: "home" },
              { id: "art", label: t("Pictures"), icon: "image" },
              { id: "pixels", label: t("Pixels"), icon: "brush" },
              { id: "words", label: t("Words"), icon: "message" },
            ]}
          />
          {section === "colours" && <Colours draft={draft} change={change} />}
          {section === "type" && <Type id={id} draft={draft} onDone={reload} />}
          {section === "shape" && <Shape draft={draft} change={change} />}
          {section === "parts" && <Parts id={id} draft={draft} change={change} onDone={reload} />}
          {section === "art" && (
            <Pictures id={id} draft={draft} art={art} change={change} onDone={reload} />
          )}
          {section === "pixels" && <Pixels id={id} draft={draft} change={change} />}
          {section === "words" && <Words draft={draft} change={change} />}
        </div>
        <aside className="remix__preview" aria-label={t("Live preview")}>
          <div className="remix__verdict">
            {preview.passed === undefined ? (
              <Badge tone="neutral">{t("Drawing…")}</Badge>
            ) : preview.passed ? (
              <Badge tone="success">{t("Every check passes")}</Badge>
            ) : (
              <Badge tone="danger">
                {t("{n} checks to fix").replace("{n}", String(failures.length))}
              </Badge>
            )}
          </div>
          {preview.info && (
            <div className="remix__stage">
              <ThemePreview
                theme={id + "--preview"}
                scheme={scheme}
                info={preview.info}
                scale={0.42}
              />
            </div>
          )}
          {failures.length > 0 && (
            <ul className="remix__failures">
              {failures.slice(0, 6).map((failure) => (
                <li key={failure}>{failure}</li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </Page>
  );
}

type Edit = { draft: Draft; change: (next: (draft: Draft) => Draft) => void };

// ---------- colours ----------
function Colours({ draft, change }: Edit) {
  const set = (path: string) => (hex: string) =>
    change((d) => ({ ...d, tokens: write(d.tokens, path, hex) }));
  return (
    <Stack space={5}>
      <Section
        title={t("Seed colours")}
        lead={t(
          "Seven colours make every shade the theme uses. Text stays legible: the checks say if it doesn't.",
        )}
      >
        <div className="remix__swatches">
          {SEEDS.map(([seed, label, hint]) => (
            <ColorInput
              key={seed}
              label={t(label)}
              hint={t(hint)}
              value={read(draft.tokens, "seed." + seed) ?? "transparent"}
              onChange={set("seed." + seed)}
            />
          ))}
        </div>
      </Section>
      <Disclosure summary={t("Each room's own light")}>
        <div className="remix__swatches">
          {ROOMS.map((room) => (
            <ColorInput
              key={room}
              label={t(ROOM_NAMES[room])}
              value={read(draft.tokens, "color.room." + room) ?? "transparent"}
              onChange={set("color.room." + room)}
            />
          ))}
        </div>
      </Disclosure>
      <Section title={t("Light or dark")}>
        <Segmented
          label={t("Light or dark")}
          value={draft.theme.schemes?.[0] || "dark"}
          onChange={(scheme) => change((d) => ({ ...d, theme: { ...d.theme, schemes: [scheme] } }))}
          options={[
            { value: "dark", label: t("Dark"), icon: "moon" },
            { value: "light", label: t("Light"), icon: "sun" },
          ]}
        />
        <Text style="caption" tone="muted">
          {t(
            "Light grounds need darker seeds: switch, then adjust the seeds until every check passes.",
          )}
        </Text>
      </Section>
    </Stack>
  );
}

// ---------- type ----------
function Type({ id, draft, onDone }: { id: string; draft: Draft; onDone: () => Promise<void> }) {
  const catalogue = useData<Obj>("/themes/remix/fonts");
  const [busy, setBusy] = useState("");
  const pick = async (role: string, family: string) => {
    const font = (catalogue.data?.fonts || []).find((f: Obj) => f.family === family);
    if (!font) return;
    setBusy(role);
    try {
      const result = await api("/themes/remix/" + encodeURIComponent(id) + "/font", "POST", {
        id,
        fontsource: font.fontsource,
        role,
        weights: font.weights
          .filter((w: number) => [300, 400, 500, 600, 700, 800].includes(w))
          .slice(0, 4),
      });
      if (result.status === "no_result" || result.passed === false)
        throw new Error(result.error || (result.failures || []).join(" · "));
      await onDone();
      toast(t("{font} is in.").replace("{font}", family), { tone: "success" });
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    } finally {
      setBusy("");
    }
  };
  return (
    <Section
      title={t("Three faces")}
      lead={t(
        "One for titles, one for reading, one for numbers. Each comes with its open licence and French letters.",
      )}
    >
      <Problem error={catalogue.error} onRetry={catalogue.reload} />
      {(["display", "body", "mono"] as const).map((role) => (
        <Field
          key={role}
          label={t(role === "display" ? "Titles" : role === "body" ? "Reading" : "Numbers")}
          hint={
            (catalogue.data?.fonts || []).find((f: Obj) => f.family === draft.theme.fonts?.[role])
              ?.character
          }
        >
          <Select
            value={draft.theme.fonts?.[role] || ""}
            disabled={!!busy}
            onChange={(e) => void pick(role, e.target.value)}
          >
            {!(catalogue.data?.fonts || []).some(
              (f: Obj) => f.family === draft.theme.fonts?.[role],
            ) && (
              <option value={draft.theme.fonts?.[role] || ""}>{draft.theme.fonts?.[role]}</option>
            )}
            {(catalogue.data?.fonts || [])
              .filter((f: Obj) => f.roles.includes(role))
              .map((f: Obj) => (
                <option key={f.family} value={f.family}>
                  {f.family} · {f.class}
                </option>
              ))}
          </Select>
        </Field>
      ))}
      {busy && <Text tone="muted">{t("Fetching the font…")}</Text>}
    </Section>
  );
}

// ---------- shape ----------
function Shape({ draft, change }: Edit) {
  return (
    <Section
      title={t("Corners")}
      lead={t("How round each kind of box is. Sizes never change; only the corners do.")}
    >
      {RADII.map(([name, label, fallback]) => {
        const value = read(draft.tokens, "radius." + name);
        const shown = typeof value === "number" ? Math.min(value, 32) : Math.min(fallback, 32);
        return (
          <Slider
            key={name}
            showLabel
            label={t(label)}
            value={shown}
            max={32}
            format={(v) => (v >= 32 ? t("Round") : v + " px")}
            onCommit={(v) =>
              change((d) => ({
                ...d,
                tokens: write(d.tokens, "radius." + name, v >= 32 ? 999 : v),
              }))
            }
          />
        );
      })}
    </Section>
  );
}

// ---------- parts: variants, colours, textures ----------
function Parts({ id, draft, change, onDone }: Edit & { id: string; onDone: () => Promise<void> }) {
  const [texture, setTexture] = useState(() => ({
    kind: "grain",
    opacity: 0.08,
    size: 8,
    ink: toHex(token("--c-fg-muted")),
  }));
  const [busy, setBusy] = useState(false);
  const pattern = async (where: "page" | "panel") => {
    setBusy(true);
    try {
      const name = where + "-" + texture.kind;
      const made = await api("/themes/remix/" + encodeURIComponent(id) + "/pattern", "POST", {
        id,
        name,
        ...texture,
      });
      if (!made.passed) throw new Error((made.failures || []).join(" · "));
      await onDone();
      change((d) => ({
        ...d,
        tokens: write(d.tokens, `part.${where}.texture`, `url(art/${name}.svg)`),
      }));
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack space={5}>
      <Section title={t("Variants")} lead={t("The same boxes, treated differently.")}>
        {Object.entries(PARTS).map(([part, spec]) => (
          <Field key={part} label={t(PART_NAMES[part] ?? part)}>
            <Segmented
              label={t(PART_NAMES[part] ?? part)}
              value={draft.theme.parts?.[part] || spec.default}
              onChange={(variant) =>
                change((d) => ({
                  ...d,
                  theme: { ...d.theme, parts: { ...d.theme.parts, [part]: variant } },
                }))
              }
              options={Object.keys(spec.variants).map((variant) => ({
                value: variant,
                label: t(VARIANT_NAMES[variant] ?? variant),
              }))}
            />
          </Field>
        ))}
      </Section>
      <Section
        title={t("Each part's colour")}
        lead={t("Leave one alone and it follows the theme's materials.")}
      >
        <div className="remix__swatches">
          {PART_COLOURS.map(([path, label]) => (
            <ColorInput
              key={path}
              label={t(label)}
              value={read(draft.tokens, path) ?? "transparent"}
              onChange={(hex) => change((d) => ({ ...d, tokens: write(d.tokens, path, hex) }))}
            />
          ))}
        </div>
      </Section>
      <Section
        title={t("A texture")}
        lead={t(
          "A faint repeating pattern, drawn by code: text on it must read as on plain colour.",
        )}
      >
        <Field label={t("Pattern")}>
          <Select
            value={texture.kind}
            onChange={(e) => setTexture({ ...texture, kind: e.target.value })}
          >
            {["grain", "dots", "hatch", "grid", "stripes", "weave", "scanlines"].map((kind) => (
              <option key={kind} value={kind}>
                {t(kind)}
              </option>
            ))}
          </Select>
        </Field>
        <ColorInput
          label={t("Its ink")}
          value={texture.ink}
          onChange={(ink) => setTexture({ ...texture, ink })}
        />
        <Slider
          showLabel
          label={t("How strong")}
          value={Math.round(texture.opacity * 100)}
          min={2}
          max={30}
          format={(v) => v + " %"}
          onCommit={(v) => setTexture({ ...texture, opacity: v / 100 })}
        />
        <Slider
          showLabel
          label={t("Tile size")}
          value={texture.size}
          min={2}
          max={48}
          format={(v) => v + " px"}
          onCommit={(v) => setTexture({ ...texture, size: v })}
        />
        <Cluster space={2}>
          <Button size="s" busy={busy} onClick={() => void pattern("page")}>
            {t("On the page")}
          </Button>
          <Button size="s" busy={busy} onClick={() => void pattern("panel")}>
            {t("On panels")}
          </Button>
        </Cluster>
      </Section>
    </Stack>
  );
}

// ---------- pictures: the art slots ----------
function Pictures({
  id,
  draft,
  art,
  change,
  onDone,
}: Edit & { id: string; art: string[]; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState("");
  const [pixel, setPixel] = useState(false);
  const upload = async (slot: string, file?: File) => {
    if (!file) return;
    setBusy(slot);
    try {
      const crisp = pixel || (await looksPixel(file)); // small, few colours: pixel art
      const body = new FormData();
      body.append("name", slot.replace(/\./g, "-"));
      body.append("pixel", String(crisp));
      body.append("file", file);
      const made = await api("/themes/remix/" + encodeURIComponent(id) + "/art", "POST", body);
      if (!made.passed) throw new Error((made.failures || []).join(" · "));
      await onDone();
      change((d) => ({
        ...d,
        theme: {
          ...d.theme,
          slots: {
            ...d.theme.slots,
            [slot]: { image: made.path, rendering: crisp ? "pixel" : "smooth", fit: "cover" },
          },
        },
      }));
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    } finally {
      setBusy("");
    }
  };
  const setFill = (slot: string, patch: Obj | null) =>
    change((d) => {
      const slots = { ...d.theme.slots };
      if (patch === null) delete slots[slot];
      else
        slots[slot] = {
          ...(typeof slots[slot] === "string" ? { image: slots[slot] } : slots[slot]),
          ...patch,
        };
      return { ...d, theme: { ...d.theme, slots } };
    });
  return (
    <Section
      title={t("Pictures")}
      lead={t(
        "Each place a picture may go, and its size on screen. PNG, JPEG or WebP: it's made smaller to fit, and its details removed.",
      )}
    >
      <Switch
        checked={pixel}
        onChange={setPixel}
        label={t("My pictures are pixel art")}
        hint={t(
          "Kept crisp and sharp-edged, never smoothed. Small pictures with few colours are taken for pixel art by themselves.",
        )}
      />
      {Object.entries(SLOTS).map(([slot, spec]) => {
        const fill = draft.theme.slots?.[slot];
        const image = typeof fill === "string" ? fill : fill?.image;
        return (
          <article key={slot} className="remix__slot">
            <div>
              <strong>{t(spec.purpose[0].toUpperCase() + spec.purpose.slice(1))}</strong>
              <Text style="caption" tone="muted">
                <code>{slot}</code> · {spec.size}
                {image && " · " + image}
                {fill?.scene && " · " + t("a scene painted by HouseOS")}
              </Text>
            </div>
            <Cluster space={2}>
              <FileButton
                label={image ? t("Replace") : t("Add a picture")}
                accept="image/png,image/jpeg,image/webp,image/gif"
                size="s"
                busy={busy === slot}
                onFiles={([file]) => void upload(slot, file)}
              />
              {image && (
                <Select
                  aria-label={t("How it fills its place")}
                  value={(typeof fill === "object" && fill.fit) || "cover"}
                  onChange={(e) =>
                    setFill(slot, {
                      fit: e.target.value,
                      slice: e.target.value === "slice" ? (fill as Obj).slice || 16 : undefined,
                    })
                  }
                >
                  <option value="cover">{t("Fill the place")}</option>
                  <option value="contain">{t("Show it whole")}</option>
                  <option value="stretch">{t("Stretch it to the place")}</option>
                  {spec.kind === "surface" && (
                    <option value="slice">{t("A frame (9-slice)")}</option>
                  )}
                </Select>
              )}
              {typeof fill === "object" && fill.fit === "slice" && (
                <Input
                  type="number"
                  min={1}
                  max={400}
                  aria-label={t("Frame corner, in pixels")}
                  value={fill.slice || 16}
                  onChange={(e) =>
                    setFill(slot, { slice: Math.max(1, Number(e.target.value) || 1) })
                  }
                />
              )}
              {fill && (
                <Button size="s" variant="quiet" icon="close" onClick={() => setFill(slot, null)}>
                  {t("Remove")}
                </Button>
              )}
            </Cluster>
          </article>
        );
      })}
      {art.length > 0 && (
        <Text style="caption" tone="muted">
          {t("In this theme's pictures:")} {art.join(", ")}
        </Text>
      )}
    </Section>
  );
}

/** Pixel art, by its look: at most 256 px a side and 64 colours. */
async function looksPixel(file: File) {
  try {
    const picture = await createImageBitmap(file);
    if (picture.width > 256 || picture.height > 256) return false;
    const canvas = new OffscreenCanvas(picture.width, picture.height);
    const context = canvas.getContext("2d")!;
    context.drawImage(picture, 0, 0);
    const data = context.getImageData(0, 0, picture.width, picture.height).data;
    const colours = new Set<number>();
    for (let i = 0; i < data.length && colours.size <= 64; i += 4)
      colours.add(((data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3]) >>> 0);
    return colours.size <= 64;
  } catch {
    return false;
  }
}

// ---------- pixels: redraw a piece on a grid ----------
function Pixels({ id, draft, change }: Edit & { id: string }) {
  const ids = Object.keys(PIECES);
  const [piece, setPiece] = useState(ids[0]);
  const [ink, setInk] = useState("k");
  const [at, setAt] = useState(0);
  const painting = useRef<string | null>(null);
  const size = 16;
  const own: string[] | undefined = draft.sprites?.glyphs?.[piece];
  // The theme's own drawing (in its palette's letters, read back into ours), else HouseOS's.
  const palette: Record<string, string> = draft.sprites?.palette ?? {};
  const toOurs = Object.fromEntries(INKS.map(([letter, token]) => [token, letter]));
  const start = (own ?? builtInPiece(piece) ?? []).map((row) =>
    [...row].map((c) => (c === "." ? "." : own ? (toOurs[palette[c]] ?? ".") : c)).join(""),
  );
  const grid = Array.from({ length: size }, (_, y) =>
    (start[y] ?? "").padEnd(size, ".").slice(0, size),
  );
  const save = (rows: string[]) =>
    change((d) => ({
      ...d,
      sprites: {
        // Our letters, whatever the theme had: the grids it had are rewritten into them.
        palette: Object.fromEntries(INKS),
        glyphs: {
          ...Object.fromEntries(
            Object.entries(d.sprites?.glyphs ?? {}).map(([name, rowsOf]) => [
              name,
              (rowsOf as string[]).map((row) =>
                [...row]
                  .map((c) => (c === "." ? "." : (toOurs[(d.sprites?.palette ?? {})[c]] ?? ".")))
                  .join(""),
              ),
            ]),
          ),
          [piece]: trim(rows),
        },
      },
    }));
  const paint = (x: number, y: number, letter: string) => {
    if (grid[y][x] === letter) return;
    const rows = grid.map((row, i) =>
      i === y ? row.slice(0, x) + letter + row.slice(x + 1) : row,
    );
    save(rows);
  };
  const cell = (e: PointerEvent<HTMLDivElement>) => {
    const target = (e.target as HTMLElement).closest<HTMLElement>("[data-x]");
    return target ? [Number(target.dataset.x), Number(target.dataset.y)] : null;
  };
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -size,
      ArrowDown: size,
    };
    if (e.key in moves) {
      e.preventDefault();
      setAt((n) => Math.min(size * size - 1, Math.max(0, n + moves[e.key])));
    } else if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      paint(at % size, Math.floor(at / size), ink);
    } else if (e.key === "Backspace" || e.key === "Delete") {
      e.preventDefault();
      paint(at % size, Math.floor(at / size), ".");
    }
  };
  return (
    <Section
      title={t("Pixel pieces")}
      lead={t(
        "Redraw Nox, people's pictures, the room marks and the house titles' medals, pixel by pixel, in the theme's own colours.",
      )}
    >
      <Field label={t("The piece")} hint={PIECES[piece as keyof typeof PIECES]?.purpose}>
        <Select value={piece} onChange={(e) => setPiece(e.target.value)}>
          {ids.map((name) => (
            <option key={name} value={name}>
              {name}
              {draft.sprites?.glyphs?.[name] ? " ✓" : ""}
            </option>
          ))}
        </Select>
      </Field>
      <div
        className="remix__pixels"
        data-theme={id + "--preview"}
        data-scheme={draft.theme.schemes?.[0]}
      >
        <div
          className="remix__grid"
          role="application"
          aria-label={t("Drawing grid: arrows move, Space paints, Delete clears")}
          tabIndex={0}
          onKeyDown={keys}
          onPointerDown={(e) => {
            const found = cell(e);
            if (!found) return;
            painting.current = e.button === 2 || e.shiftKey ? "." : ink;
            (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
            paint(found[0], found[1], painting.current);
          }}
          onPointerMove={(e) => {
            if (!painting.current) return;
            const hit = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
            const x = hit?.dataset.x,
              y = hit?.dataset.y;
            if (x !== undefined && y !== undefined) paint(Number(x), Number(y), painting.current);
          }}
          onPointerUp={() => (painting.current = null)}
          onContextMenu={(e) => e.preventDefault()}
        >
          {grid.flatMap((row, y) =>
            [...row].map((letter, x) => (
              <span
                key={x + "-" + y}
                data-x={x}
                data-y={y}
                data-cursor={at === y * size + x || undefined}
                style={
                  letter === "."
                    ? undefined
                    : ({
                        "--ink": `var(--c-sprite-${INKS.find(([l]) => l === letter)?.[1]})`,
                      } as CSSProperties)
                }
              />
            )),
          )}
        </div>
        <SwatchPicker
          label={t("Colour to paint with")}
          value={ink}
          onChange={setInk}
          options={INKS.map(([letter, token]) => ({
            value: letter,
            label: token,
            color: `var(--c-sprite-${token})`,
          }))}
        />
      </div>
      <Text style="caption" tone="muted">
        {t(
          "Right-click or Shift to erase. Draw inside 16 × 16; the piece keeps the size of the one it replaces.",
        )}
      </Text>
      <Cluster space={2}>
        <Button
          size="s"
          variant="quiet"
          icon="undo"
          disabled={!own}
          onClick={() =>
            change((d) => {
              const glyphs = { ...(d.sprites?.glyphs ?? {}) };
              delete glyphs[piece];
              return {
                ...d,
                sprites: Object.keys(glyphs).length ? { ...d.sprites, glyphs } : null,
              };
            })
          }
        >
          {t("Back to HouseOS's drawing")}
        </Button>
      </Cluster>
    </Section>
  );
}

/** A grid without its empty edge rows and columns (the check measures what is drawn). */
function trim(rows: string[]) {
  const used = rows.map((row) => row.replace(/\.+$/, ""));
  while (used.length && !used[used.length - 1]) used.pop();
  return used.length ? used : ["."];
}

// ---------- words ----------
function Words({ draft, change }: Edit) {
  const flavor = draft.flavor ?? {};
  const set = (key: string, lang: "en" | "fr", text: string) =>
    change((d) => {
      const next = { ...(d.flavor ?? {}) };
      const both = { en: "", fr: "", ...(next[key] ?? {}), [lang]: text };
      if (!both.en.trim() && !both.fr.trim()) delete next[key];
      else next[key] = both;
      return { ...d, flavor: next };
    });
  const pair = (key: string, label: string, max: number) => (
    <div key={key} className="remix__words">
      <Text style="label">{label}</Text>
      {(["en", "fr"] as const).map((lang) => (
        <Input
          key={lang}
          aria-label={label + " · " + lang}
          placeholder={lang === "en" ? "English" : "Français"}
          maxLength={max}
          value={flavor[key]?.[lang] ?? ""}
          onChange={(e) => set(key, lang, e.target.value)}
        />
      ))}
    </div>
  );
  return (
    <Stack space={5}>
      <Text tone="muted">
        {t("Every line in English and French (tu). A line left empty keeps HouseOS's own words.")}
      </Text>
      <Disclosure summary={t("House titles")}>
        {pair("title.star.mark", t("The star mark (★)"), 3)}
        {TITLES.map((title) => pair(`title.${title}.name`, title.replace(/_/g, " "), 28))}
      </Disclosure>
    </Stack>
  );
}

// The one-time welcomes, chosen by <Onboarding /> in shell.tsx and loaded only when one shows
// (never two at once):
// - the owner's set-up on a new house (settings, the AI, your coding agent, the house's look);
// - a new resident's first visit (profile, look, what to know);
// - a guest from a QR code (one screen: music, and the TV when the code allows it);
// - "What's new" after an update (whats_new.ts).
// Each shows once (preferences onboarded, seen_release; the owner's welcome_dismissed) and can
// always be closed; closing the owner's set-up asks first, since the house needs it.
import { t } from "./i18n";
import { useEffect, useState, type ReactNode } from "react";
import { api, useData, useUser, type Obj } from "./api";
import { go } from "./nav";
import { AddonForm, STATE, type Step } from "./setup";
import { LookPicker } from "./theme_preview";
import { tryOn } from "./design/theme";
import type { News } from "./whats_new";
import {
  AVATAR_NAMES,
  Avatar,
  AvatarPicture,
  Button,
  ConfirmSheet,
  Disclosure,
  Field,
  Glyph,
  Icon,
  type IconName,
  Input,
  List,
  ListRow,
  Mascot,
  Progress,
  Radio,
  Segmented,
  Sheet,
  Slot,
  Text,
  toast,
  tone,
  type GlyphName,
} from "./design";
import "./onboarding.css";

// ---------- the shared frame: a picture, a few words, one step at a time ----------

/** A welcome's steps: the step's picture beside (on phones above) its words, dots for where you
 *  are, Back and Next, and a quiet way out. */
function Journey({
  title,
  step,
  steps,
  art,
  onStep,
  onFinish,
  finish,
  next,
  onClose,
  children,
}: {
  title: string;
  step: number;
  steps: number;
  art: ReactNode;
  onStep: (step: number) => void;
  onFinish: () => void;
  finish: string;
  /** The Next button's words on this step ("Let's go"). */
  next?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const last = step === steps - 1;
  return (
    <Sheet
      title={title}
      place="center"
      wide
      onClose={onClose}
      footer={
        <div className="journey__foot">
          <Button variant="link" onClick={onClose}>
            {t("Skip for now")}
          </Button>
          {step > 0 && <Button onClick={() => onStep(step - 1)}>{t("Back")}</Button>}
          <Button variant="primary" onClick={() => (last ? onFinish() : onStep(step + 1))}>
            {last ? finish : next || t("Next")}
          </Button>
        </div>
      }
    >
      <div className="journey">
        {/* The theme's own Home scene behind the step's picture (when the theme has one). */}
        <div className="journey__art" aria-hidden="true">
          <Slot
            id="home.hero.backdrop"
            className="journey__scene"
            width={240}
            height={120}
            lit={3}
          />
          <span className="journey__focal" key={"art" + step}>
            {art}
          </span>
        </div>
        <div className="journey__words" key={"words" + step}>
          {steps > 1 && (
            <Progress value={(step + 1) / steps} steps={steps} label={t("Welcome steps")} />
          )}
          {children}
        </div>
      </div>
    </Sheet>
  );
}

/** A short line with its picture: the welcomes' lists. */
function Point({
  glyph,
  icon,
  title,
  children,
}: {
  glyph?: GlyphName | "nox";
  icon?: IconName;
  title: string;
  children?: ReactNode;
}) {
  return (
    <li className="journey__point">
      <span className="journey__mark">
        {glyph === "nox" ? (
          <Mascot size="s" />
        ) : glyph ? (
          <Glyph name={glyph} />
        ) : (
          <Icon name={icon!} />
        )}
      </span>
      <span>
        <strong>{title}</strong>
        {children && <small>{children}</small>}
      </span>
    </li>
  );
}

const Big = ({ children }: { children: ReactNode }) => (
  <Text as="p" style="title-m">
    {children}
  </Text>
);

// ---------- the owner's set-up ----------

// This browser session only: "skipped", or the step to come back to after a Control Room visit.
const SESSION = "houseos.welcome";
function remember(value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(SESSION);
    else sessionStorage.setItem(SESSION, value);
  } catch {
    /* private mode: the welcome simply starts over */
  }
}
function recalled() {
  try {
    return sessionStorage.getItem(SESSION);
  } catch {
    return null;
  }
}

const OWNER_STEPS = 7;

/** What a coding agent (Claude Code, Codex…) needs to help from the HouseOS folder. */
const agentPrompt = () =>
  t(
    "You're helping me set up HouseOS, a self-hosted home app installed in this folder. Read AGENTS.md first, then README.md and docs/. Check what runs with `./houseos.sh status` and `./houseos.sh check`. Then ask me what I want to do: connect the AI, films, speakers and TVs, invites, backups, a theme, or a new feature. One small step at a time, in simple words, and ask me before restarting anything or changing my network.",
  );

/** One thing to set up: its state in a mark and a word, and the button to its setting. */
function Item({
  state,
  title,
  children,
  action,
  primary = false,
  onAction,
}: {
  state: Step["state"];
  title: string;
  children: ReactNode;
  action?: string;
  primary?: boolean;
  onAction?: () => void;
}) {
  return (
    <ListRow
      title={title}
      detail={children}
      status={{ tone: STATE[state].tone, text: STATE[state].word() }}
      actions={
        action && (
          <Button size="s" variant={primary ? "primary" : "secondary"} onClick={onAction}>
            {action}
          </Button>
        )
      }
    />
  );
}

export function OwnerSetup({
  forced,
  onDone,
  onLater,
}: {
  forced: boolean;
  onDone: () => void;
  onLater: () => void;
}) {
  const user = useUser();
  const [saved] = useState(recalled);
  const [step, setStep] = useState(() =>
    forced ? 0 : Math.min(OWNER_STEPS - 1, Number(saved) || 0),
  );
  const [asking, setAsking] = useState(false);
  const setup = useData<Obj>(saved === "skipped" && !forced ? null : "/admin/setup", {
    interval: 10000,
  });
  const house = useData<Obj>("/admin/house-settings");
  useEffect(() => {
    if (forced) history.replaceState(null, "", location.pathname);
  }, []);
  if ((saved === "skipped" && !forced) || !setup.data || !house.data) return null;
  const state = (key: string): Step["state"] =>
    setup.data?.steps?.find((s: Step) => s.key === key)?.state || "todo";
  // Opening a setting keeps the place: back on Home, this step opens again.
  const open = (path: string) => {
    remember(String(step));
    go(path);
  };
  const later = () => {
    remember("skipped");
    tryOn(null);
    onLater();
  };
  const done = () => {
    remember(null);
    tryOn(null);
    onDone();
  };
  const ai = state("ai"),
    films = state("films"),
    speakers = state("speakers"),
    tv = state("tv"),
    invite = state("invite"),
    access = state("access");
  const first = String(user?.name || "").split(" ")[0];
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(agentPrompt());
      toast(t("Copied: paste it into your coding agent."));
    } catch {
      toast(t("Select the text and copy it by hand."), { tone: "neutral" });
    }
  };
  const pick = async (theme: string) => {
    try {
      await api("/admin/house-settings", "PUT", { theme });
      house.setData((h) => (h ? { ...h, theme } : h));
      dispatchEvent(new Event("house-settings-updated"));
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    }
  };
  const ARTS: ReactNode[] = [
    <Mascot mood="happy" size="l" />,
    <Icon name="palette" />,
    <Icon name="bot" />,
    <Glyph name="room.watch" size="l" />,
    <Glyph name="room.listen" size="l" />,
    <Glyph name="room.house" size="l" />,
    <Mascot mood="listening" size="l" />,
  ];
  const TITLES = [
    t("Welcome home"),
    t("Pick a theme"),
    t("Connect an AI"),
    t("Films and series"),
    t("Speakers and TVs"),
    t("People and access"),
    t("You're set"),
  ];
  return (
    <>
      <Journey
        title={TITLES[step]}
        step={step}
        steps={OWNER_STEPS}
        art={ARTS[step]}
        onStep={setStep}
        onFinish={done}
        finish={t("Done")}
        next={step === 0 ? t("Let's set it up") : undefined}
        onClose={() => setAsking(true)}
      >
        {step === 0 && (
          <>
            <Big>
              {first
                ? t("{name}, your house is ready. Five quick steps:").replace("{name}", first)
                : t("Your house is ready. Five quick steps:")}
            </Big>
            <ol className="journey__points journey__points--numbered">
              <Point icon="palette" title={t("A theme")} />
              <Point icon="bot" title={t("An AI for Nox")} />
              <Point glyph="room.watch" title={t("A film source")} />
              <Point glyph="room.listen" title={t("Speakers and TVs")} />
              <Point glyph="room.house" title={t("Invites and a backup")} />
            </ol>
            <Text tone="muted">
              {t("About five minutes. Skip any step: it stays in Control Room → Setup.")}
            </Text>
          </>
        )}
        {step === 1 && (
          <>
            <Big>
              {t("The house's theme. Everyone starts with it and can pick their own later.")}
            </Big>
            <Text tone="muted">
              {t("Want your own? Control Room → Themes: describe it to Nox, or make it by hand.")}
            </Text>
            <LookPicker
              value={house.data.theme}
              house={house.data.theme}
              scale={0.16}
              onChange={(id) => void pick(id)}
            />
          </>
        )}
        {step === 2 && (
          <>
            <Big>{t("Nox runs on the AI you choose:")}</Big>
            <ul className="journey__points">
              <Point icon="key" title={t("Your subscription")}>
                {t("Sign in with ChatGPT or Claude.")}
              </Point>
              <Point icon="link" title={t("An API key")}>
                {t("OpenRouter, OpenAI or Anthropic.")}
              </Point>
              <Point icon="lock" title={t("A local model")}>
                {t("Ollama or LM Studio: free and private.")}
              </Point>
            </ul>
            <List>
              <Item
                state={ai}
                title={t("Connect Nox to an AI")}
                action={ai === "done" ? t("Change") : t("Connect an AI")}
                primary={ai !== "done"}
                onAction={() => open("/control?tab=ai")}
              >
                {ai === "done" ? t("Nox is connected and answers.") : t("About a minute.")}
              </Item>
            </List>
            <Text tone="muted">{t("No AI? Every feature still has its buttons.")}</Text>
          </>
        )}
        {step === 3 && (
          <>
            <Big>{t("Add a source to play films:")}</Big>
            <List>
              <Item
                state={films === "done" ? "done" : "optional"}
                title={t("A Stremio add-on and a debrid service")}
              >
                {films === "done"
                  ? t("A film source is connected.")
                  : t(
                      "Recommended: fast and reliable. No debrid service? Turn on the torrent player.",
                    )}
              </Item>
              <Item state="optional" title={t("Your own films")}>
                {t("Films in Files play as they are. Jellyfin works too.")}
              </Item>
            </List>
            <AddonForm
              onSaved={setup.reload}
              more={
                <Button
                  variant="quiet"
                  onClick={() => open("/control?tab=integrations&open=stream_addon")}
                >
                  {t("More settings")}
                </Button>
              }
            />
          </>
        )}
        {step === 4 && (
          <>
            <Big>{t("Where music plays, and which TVs films go to.")}</Big>
            <List>
              <Item
                state={speakers}
                title={t("Choose where music plays")}
                action={speakers === "done" ? t("Change") : t("Choose speakers")}
                primary={speakers === "todo" || speakers === "unavailable"}
                onAction={() => open("/control?tab=speakers")}
              >
                {speakers === "done"
                  ? t("Music plays on this computer's speakers.")
                  : t("Pick this computer, or a speaker on the Wi-Fi.")}
              </Item>
              <Item
                state={tv}
                title={t("TVs on the Wi-Fi")}
                action={t("Find TVs and speakers")}
                primary={speakers !== "todo" && tv !== "done"}
                onAction={() => {
                  void api("/admin/devices/discover", "POST").catch(() => {});
                  open("/control?tab=devices");
                }}
              >
                {tv === "done"
                  ? t("A screen is ready.")
                  : t("Chromecast, Google TV, smart TVs, Sonos.")}
              </Item>
            </List>
            <Text tone="muted">{t("Any phone can play along too: Listen → Play here.")}</Text>
          </>
        )}
        {step === 5 && (
          <>
            <Big>{t("Invite the house, and keep a backup.")}</Big>
            <List>
              <Item
                state={invite}
                title={t("Invite the house")}
                action={t("Invite someone")}
                primary={invite !== "done"}
                onAction={() => open("/control?tab=invites")}
              >
                {t("A link each: their own account, music and Nox.")}
              </Item>
              <Item
                state={access}
                title={t("Secure address")}
                action={access === "done" ? undefined : t("Set up the secure address")}
                onAction={() => open("/control?tab=access")}
              >
                {t("Phones need https:// for sign-in, voice and the app.")}
              </Item>
              <Item
                state="optional"
                title={t("Keep a backup")}
                action={t("Make a backup")}
                onAction={() => open("/control?tab=recovery")}
              >
                {t("One button; copy it to another disk.")}
              </Item>
            </List>
          </>
        )}
        {step === 6 && (
          <>
            <Big>{t("Anything else: ask Nox, in your own words.")}</Big>
            <ul className="journey__points">
              <Point glyph="nox" title={t("“Start quiet hours at 10 pm”")} />
              <Point glyph="nox" title={t("“Why is there no sound?”")} />
              <Point glyph="nox" title={t("“Cap the music volume at 70%”")} />
            </ul>
            {ai === "done" ? (
              <Button
                size="l"
                wide
                onClick={() => {
                  done();
                  dispatchEvent(
                    new CustomEvent("houseos:ask", {
                      detail: { purpose: "setup", message: t("Help me set up the house") },
                    }),
                  );
                }}
              >
                <Mascot mood="happy" size="s" />
                {t("Let Nox finish setting up")}
              </Button>
            ) : (
              <Text tone="muted">{t("Once Nox has an AI, it can walk you through the rest.")}</Text>
            )}
            <Disclosure summary={t("Or use your coding agent (Claude Code, Codex…)")}>
              <Text>
                {t("Open a terminal in the HouseOS folder, start your agent there and paste this:")}
              </Text>
              <pre className="journey__prompt">{agentPrompt()}</pre>
              <Button icon="copy" onClick={() => void copy()}>
                {t("Copy the prompt")}
              </Button>
            </Disclosure>
          </>
        )}
      </Journey>
      {asking && (
        <ConfirmSheet
          title={t("Leave the set-up for now?")}
          confirm={t("Leave for now")}
          onConfirm={later}
          onClose={() => setAsking(false)}
        >
          {t(
            "It connects Nox, films and speakers. It comes back next time, and it's always in Control Room → Setup.",
          )}
        </ConfirmSheet>
      )}
    </>
  );
}

// ---------- a new resident's first visit ----------

export function ResidentWelcome({ onDone }: { onDone: (change: Obj) => void }) {
  const user = useUser();
  const profile = useData<Obj>("/account/profile");
  const settings = useData<Obj>("/house-settings");
  const [step, setStep] = useState(0);
  const [name, setName] = useState<string | null>(null),
    [language, setLanguage] = useState<string | null>(null),
    [avatar, setAvatar] = useState<string | null>(null),
    [look, setLook] = useState<string | null>(null);
  if (!profile.data || !settings.data) return null;
  const house = settings.data.theme || "";
  const houseName = settings.data.name || "";
  const saveProfile = async () => {
    const change: Obj = {};
    if (name && name.trim() && name.trim() !== profile.data!.name) change.name = name.trim();
    if (language && language !== profile.data!.language) change.language = language;
    if (avatar && avatar !== profile.data!.avatar) change.avatar = avatar;
    if (!Object.keys(change).length) return;
    try {
      await api("/account/profile", "PATCH", change);
      dispatchEvent(new Event("house-settings-updated"));
    } catch (e) {
      toast((e as Error).message, { tone: "danger" });
    }
  };
  const finish = () => {
    tryOn(null);
    // Keeping the house's theme means following it (the owner may change it later).
    onDone(look && look !== house ? { theme: look } : {});
  };
  const ARTS = [
    <Mascot mood="happy" size="l" />,
    <Avatar
      name={name ?? profile.data.name}
      picture={avatar ?? profile.data.avatar}
      tone={tone(user?.id)}
      size="l"
    />,
    <Icon name="palette" />,
    <Glyph name="room.home" size="l" />,
  ];
  const TITLES = [t("Welcome home"), t("This is you"), t("Your theme"), t("Good to know")];
  return (
    <Journey
      title={TITLES[step]}
      step={step}
      steps={4}
      art={ARTS[step]}
      onStep={(next) => {
        if (step === 1) void saveProfile();
        setStep(next);
      }}
      onFinish={finish}
      finish={t("Let's go")}
      next={step === 0 ? t("Start") : undefined}
      onClose={finish}
    >
      {step === 0 && (
        <>
          <Big>
            {houseName
              ? t("Welcome to {house}!").replace("{house}", houseName)
              : t("Welcome to the house!")}
          </Big>
          <Text>{t("Three quick steps. You can change everything later.")}</Text>
        </>
      )}
      {step === 1 && (
        <>
          <Field label={t("Your name")}>
            <Input
              value={name ?? profile.data.name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
            />
          </Field>
          <Segmented
            label={t("Language")}
            value={language ?? profile.data.language}
            onChange={setLanguage}
            options={[
              { value: "en", label: "English" },
              { value: "fr", label: "Français" },
            ]}
          />
          <fieldset className="me-avatars">
            <legend>{t("Your picture")}</legend>
            {AVATAR_NAMES.map((a) => (
              <Radio
                key={a}
                name="avatar"
                value={a}
                checked={(avatar ?? profile.data!.avatar) === a}
                onChange={() => setAvatar(a)}
                aria-label={a === "crest" ? t("Initials") : t(a[0].toUpperCase() + a.slice(1))}
                label={
                  a === "crest" ? (
                    <Avatar name={name ?? profile.data!.name} tone={tone(user?.id)} />
                  ) : (
                    <AvatarPicture name={a} scale={3} />
                  )
                }
              />
            ))}
          </fieldset>
        </>
      )}
      {step === 2 && (
        <>
          <Big>{t("Keep the house's theme, or pick your own. Only you see yours.")}</Big>
          <LookPicker value={look ?? house} house={house} scale={0.16} onChange={setLook} />
        </>
      )}
      {step === 3 && (
        <ul className="journey__points">
          <Point glyph="room.listen" title={t("Listen")}>
            {t("Add songs to one queue: everyone takes turns.")}
          </Point>
          <Point glyph="room.watch" title={t("Watch")}>
            {t("Pick a film, confirm, it plays on the TV.")}
          </Point>
          <Point glyph="room.house" title={t("House")}>
            {t("Groceries, tasks, calendar, notes on the wall.")}
          </Point>
          <Point glyph="room.games" title={t("Games")}>
            {t("Your games, here or on the TV. On a phone: the dock's +.")}
          </Point>
          <Point icon="inbox" title={t("Messages")}>
            {t("A number on your picture, top right, means new messages.")}
          </Point>
          <Point glyph="nox" title={t("Nox")}>
            {t("Ask anything, typed or spoken. Tap Nox for a tour.")}
          </Point>
        </ul>
      )}
    </Journey>
  );
}

// ---------- a guest, from a QR code ----------

export function GuestWelcome({
  name,
  tv,
  onDone,
}: {
  name: string;
  tv: boolean;
  onDone: () => void;
}) {
  return (
    <Journey
      title={t("Welcome, {name}!").replace("{name}", name || t("guest"))}
      step={0}
      steps={1}
      art={<Mascot mood="happy" size="l" />}
      onStep={() => {}}
      onFinish={onDone}
      finish={t("Let's go")}
      onClose={onDone}
    >
      <ul className="journey__points">
        <Point glyph="room.listen" title={t("Add music")}>
          {t("Paste a YouTube link or search a song. It joins the queue, everyone takes turns.")}
        </Point>
        {tv && (
          <Point glyph="room.watch" title={t("Watch on the TV")}>
            {t("Open Watch, pick a film, confirm: it plays on the TV.")}
          </Point>
        )}
      </ul>
      <Text tone="muted">{t("Your pass lasts a few hours. No account needed.")}</Text>
    </Journey>
  );
}

// ---------- after an update ----------

export function WhatsNew({
  releases,
  onDone,
}: {
  releases: { version: string; items: News[] }[];
  onDone: () => void;
}) {
  return (
    <Sheet
      title={t("What's new in HouseOS")}
      place="center"
      wide
      onClose={onDone}
      footer={
        <Button variant="primary" onClick={onDone}>
          {t("Got it")}
        </Button>
      }
    >
      <div className="journey__news">
        {releases.map((release, index) => {
          const points = (
            <ul className="journey__points">
              {release.items.map((item) => (
                <li className="journey__point" key={item.title}>
                  <span className="journey__mark">
                    {item.glyph === "nox" ? <Mascot size="s" /> : <Glyph name={item.glyph} />}
                  </span>
                  <span>
                    <strong>{t(item.title)}</strong>
                    <small>{t(item.text)}</small>
                  </span>
                  {item.go && (
                    <Button
                      size="s"
                      variant="quiet"
                      iconEnd="forward"
                      onClick={() => {
                        onDone();
                        go(item.go!);
                      }}
                    >
                      {t("Go")}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          );
          // The newest is open; the ones missed before it stack below, a line each.
          return index === 0 ? (
            <section key={release.version} aria-label={"HouseOS " + release.version}>
              <Text as="h3" style="label" tone="muted">
                {release.version}
              </Text>
              {points}
            </section>
          ) : (
            <Disclosure
              key={release.version}
              summary={
                <>
                  <strong>{release.version}</strong>{" "}
                  {release.items.map((item) => t(item.title)).join(" · ")}
                </>
              }
            >
              {points}
            </Disclosure>
          );
        })}
      </div>
    </Sheet>
  );
}

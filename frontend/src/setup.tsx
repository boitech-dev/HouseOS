import { t } from "./i18n";
import { useState, type ReactNode } from "react";
import { api, items, useData, type Obj } from "./api";
import { go } from "./nav";
import {
  Badge,
  Button,
  Cluster,
  Field,
  Form,
  Icon,
  IconButton,
  type IconName,
  Input,
  LinkButton,
  List,
  ListRow,
  Problem,
  SecretInput,
  Section,
  Status,
  Text,
  type Tone,
} from "./design";
import "./setup.css";

export type Step = {
  key: string;
  state: "done" | "todo" | "optional" | "unavailable";
  tab: string;
  detail?: string;
};

const TITLES: Record<string, () => string> = {
  house: () => t("Name your house"),
  access: () => t("Open it from every device"),
  ai: () => t("Connect Nox to an AI"),
  speakers: () => t("Choose where music plays"),
  sources: () => t("Music sources"),
  films: () => t("Films and series"),
  tv: () => t("TVs and speakers on the Wi-Fi"),
  smart_home: () => t("Lights and the rest of the house"),
  voice: () => t("Talk to Nox"),
  invite: () => t("Invite the house"),
  backups: () => t("Keep a backup"),
};

export const stepTitle = (key: string) => TITLES[key]?.() || key;

// The Stremio community's own directory of add-ons (it replaced their list on GitHub). HouseOS
// builds in and names no add-on: the owner picks one there, as in Stremio, and pastes its link.
const ADDON_CATALOGUE = "https://stremio-addons.net/addons";

/** The stream add-on's link: its label and hint, in the welcome and in Control Room alike. */
export const ADDON_FIELD: [string, string] = [
  "Your stream add-on's link",
  "Its install link, ending in /manifest.json. It stays on the server and is never shown again.",
];

export const BrowseAddons = () => (
  <div>
    <LinkButton icon="forward" href={ADDON_CATALOGUE} target="_blank" rel="noopener noreferrer">
      {t("Browse add-ons")}
    </LinkButton>
  </div>
);

/** Paste a stream add-on's link (the welcome's films step); the rest stays in Control Room. */
export function AddonForm({ onSaved, more }: { onSaved: () => void; more?: ReactNode }) {
  const list = useData("/admin/integrations");
  const row = items(list.data).find((r) => r.name === "stream_addon");
  return (
    <Form
      submit={t("Save")}
      reset
      secondary={more}
      onSubmit={async (f) => {
        await api("/admin/integrations/stream_addon", "PUT", {
          enabled: true,
          config: row?.config || {},
          secret: f.get("secret"),
        });
        list.reload();
        onSaved();
      }}
    >
      <Field label={t(ADDON_FIELD[0])} hint={t(ADDON_FIELD[1])}>
        <SecretInput name="secret" required />
      </Field>
      <BrowseAddons />
    </Form>
  );
}

/** One sentence per step and state: what it gives you, or what to do next. */
function explain(step: Step, container: boolean): string {
  const on = step.state === "done";
  switch (step.key) {
    case "house":
      return on
        ? t("Named, with its time zone and language.")
        : t("Pick the house name, time zone and language everyone sees.");
    case "access":
      return on
        ? t("You're on a secure address. Add the others you use in Access.")
        : container
          ? t(
              "Phones need an https:// address for sign-in, voice and the app install. Open https://houseos.local:8443 (or the server's IP on port 8443), or use your own reverse proxy.",
            )
          : t(
              "Phones need an https:// address for sign-in, voice and the app install. Put HouseOS behind HTTPS.",
            );
    case "ai":
      return on
        ? t("Nox is connected and answers.")
        : t(
            "Sign in with ChatGPT or Claude, paste an API key, or use your own model (Ollama, LM Studio…).",
          );
    case "speakers":
      if (on)
        return t(
          "Music plays on this computer's speakers. Phones and Wi-Fi speakers or TVs can join too.",
        );
      if (step.state === "optional")
        return t(
          "This server has no speakers of its own: play on a speaker or TV on the Wi-Fi (Cast, DLNA, Sonos…) or on a phone (Speaker mode).",
        );
      return t("The speaker service isn't answering. Restart it in Services.");
    case "sources":
      return on
        ? t("YouTube, SoundCloud and radio are reachable.")
        : t("The music source service isn't answering. Restart it in Services.");
    case "films":
      if (on) return t("A film source is connected.");
      if (step.state === "unavailable")
        return t("Film preparation isn't answering. Restart it in Services.");
      return t(
        "Add a stream add-on (with a debrid service or the torrent player), or your Jellyfin.",
      );
    case "tv":
      return on
        ? t("A screen is ready.")
        : t("Find your TVs and speakers in Devices: Cast, Android TV, Google TV, DLNA, Sonos…");
    case "smart_home":
      return on
        ? t("Home Assistant is connected: see the Smart home room, or ask Nox.")
        : t(
            "Optional. Already use Home Assistant? Connect it to control lights, plugs, blinds and heating from HouseOS and Nox.",
          );
    case "voice":
      if (on)
        return step.detail === "gpu"
          ? t("Voice typing works, on the graphics card.")
          : t("Voice typing works, on the processor.");
      if (step.detail === "preparing")
        return t(
          "Getting voice typing ready: its speech model is downloading (a few minutes, once).",
        );
      return t("Voice typing isn't answering. Restart it in Services.");
    case "invite":
      return on
        ? t("Invitations are out.")
        : t("Create an invitation for each person you live with.");
    case "backups":
      return container
        ? t("Make a backup in Backups (one button), then copy it to another disk.")
        : t("See Backup and recovery for what is covered.");
  }
  return "";
}

/** How each step's state reads in Setup: a mark and a word, never colour alone. */
export const STATE: Record<Step["state"], { tone: Tone; word: () => string }> = {
  done: { tone: "success", word: () => t("Ready") },
  todo: { tone: "accent", word: () => t("To do") },
  optional: { tone: "neutral", word: () => t("Optional") },
  unavailable: { tone: "warning", word: () => t("Not answering") },
};

export function SetupAdmin({ open }: { open: (tab: string) => void }) {
  const setup = useData<Obj>("/admin/setup");
  const steps: Step[] = setup.data?.steps || [];
  return (
    <Section
      title={t("Set up your house")}
      actions={
        <Button variant="quiet" icon="refresh" onClick={setup.reload}>
          {t("Check again")}
        </Button>
      }
    >
      <Problem error={setup.error} onRetry={setup.reload} />
      {setup.data && (
        <Text as="p">
          <strong>
            {setup.data.done} / {setup.data.needed}
          </strong>{" "}
          {t("essentials ready. Optional steps add more when you want them.")}{" "}
          <Button variant="link" onClick={() => go("/?welcome")}>
            {t("Show the welcome again")}
          </Button>
        </Text>
      )}
      {steps.some((step) => step.key === "ai" && step.state === "done") && (
        <div>
          <Button variant="primary" icon="sparkles" onClick={() => go("/assistant?mode=setup")}>
            {t("Set up the house with Nox")}
          </Button>
        </div>
      )}
      <List label={t("Set up your house")}>
        {steps.map((step) => (
          <ListRow
            key={step.key}
            title={stepTitle(step.key)}
            detail={explain(step, !!setup.data?.container)}
            actions={
              // Two fixed columns, the state then its button (or nothing), so every row lines up.
              <span className="setup-trail">
                <Status tone={STATE[step.state].tone}>{STATE[step.state].word()}</Status>
                {step.state !== "done" && step.key !== "backups" && (
                  <Button size="s" onClick={() => open(step.tab)}>
                    {step.state === "unavailable" ? t("Details") : t("Set up")}
                  </Button>
                )}
              </span>
            }
          />
        ))}
      </List>
    </Section>
  );
}

/** What kind of address this is, in words, and who can use it. */
function addressKind(origin: string): [string, string] {
  const host = (() => {
    try {
      return new URL(origin).hostname;
    } catch {
      return origin;
    }
  })();
  const ip = host.split(".").map(Number);
  if (host === "localhost" || host.startsWith("127."))
    return ["This computer only", "Opens HouseOS on the server itself; nobody else can use it."];
  if (host.endsWith(".ts.net") || (ip[0] === 100 && ip[1] >= 64 && ip[1] < 128))
    return [
      "Tailscale (from anywhere)",
      "A private network between your own devices: works outside the house, on phones signed in to the same Tailscale account.",
    ];
  if (host.endsWith(".local"))
    return ["Home Wi-Fi name", "Works on phones and computers connected to the house Wi-Fi."];
  if (ip.length === 4 && ip.every((n) => n >= 0 && n <= 255))
    return [
      "Home network address",
      "Works on the house Wi-Fi; use it when the Wi-Fi name does not open on a device.",
    ];
  return [
    "Your own address",
    "A domain or reverse proxy you set up; it works wherever that address is reachable.",
  ];
}

/** How to reach the house from where you are, each explained in full (never cut to a line). */
const WAYS: [IconName, string, string][] = [
  [
    "home",
    "At home",
    "Any phone or computer on the house Wi-Fi opens https://houseos.local:8443 (or the server's address on port 8443). Nothing to install.",
  ],
  [
    "shield",
    "Away from home, privately: Tailscale",
    "Tailscale is a free private network between your own devices. Install it on the server and on each phone, sign in with the same account, then open the server's Tailscale address (it ends in .ts.net) and add it here. Nothing is opened to the internet.",
  ],
  [
    "link",
    "Your own domain",
    "If you run a reverse proxy (Caddy, nginx) with your own domain, open HouseOS once through it and add that address here.",
  ],
];

export function AccessAdmin() {
  const access = useData<Obj>("/admin/access");
  const [value, setValue] = useState(""),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  const known = new Set((access.data?.origins || []).map((o: Obj) => o.origin));
  const add = async (origin: string) => {
    setError("");
    try {
      await api("/admin/access", "POST", { origin });
      setValue("");
      await access.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <Section
        title={t("Addresses")}
        lead={t(
          "HouseOS only answers at addresses it trusts. The one you used for the setup code was added for you.",
        )}
      >
        <Problem error={access.error || error} />
        <List label={t("Addresses")}>
          {(access.data?.origins || []).map((o: Obj) => {
            const [kind, about] = addressKind(o.origin);
            const here = o.origin === access.data?.current;
            return (
              <ListRow
                key={o.origin}
                title={<code className="setup-code">{o.origin}</code>}
                // The address keeps the whole line; where it comes from reads beside its kind.
                detail={
                  <>
                    {here && <Badge>{t("you're here")}</Badge>} <strong>{t(kind)}</strong>
                    {o.source === "wifi" && " · " + t("announced on the Wi-Fi")}
                    {o.source === "settings" && " · " + t("from HOUSEOS_ALLOWED_ORIGINS")}
                    {" · "}
                    {t(about)}
                  </>
                }
                actions={
                  o.source !== "wifi" &&
                  o.source !== "settings" &&
                  !here && (
                    <IconButton
                      icon="trash"
                      label={t("Remove this address")}
                      onClick={async () => {
                        setError("");
                        try {
                          await api(
                            "/admin/access?origin=" + encodeURIComponent(o.origin),
                            "DELETE",
                          );
                          await access.reload();
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    />
                  )
                }
              />
            );
          })}
        </List>
        <form
          className="setup-add"
          onSubmit={(e) => {
            e.preventDefault();
            void add(value);
          }}
        >
          <Input
            aria-label={t("Another address")}
            placeholder="https://house.example.lan"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <Button type="submit" icon="add" disabled={!value.trim()}>
            {t("Add")}
          </Button>
        </form>
        {access.data?.current && !known.has(access.data.current) && (
          <div>
            <Button icon="check" onClick={() => void add(access.data!.current)}>
              {t("Trust the address I'm using now")}
            </Button>
          </div>
        )}
      </Section>
      <Section title={t("Ways to reach HouseOS")}>
        <ul className="setup-ways">
          {WAYS.map(([icon, title, text]) => (
            <li key={title}>
              <Icon name={icon} />
              <div>
                <Text as="h3" style="title-s">
                  {t(title)}
                </Text>
                <Text as="p" style="body-s" tone="muted">
                  {t(text)}
                </Text>
              </div>
            </li>
          ))}
        </ul>
      </Section>
      <Section title={t("Secure address (HTTPS)")}>
        <Status tone={access.data?.secure ? "success" : "warning"}>
          {access.data?.secure
            ? t("This page is on HTTPS: sign-in, voice and the app install work here.")
            : t(
                "This page is on plain HTTP: phones can't use the microphone or install the app here.",
              )}
        </Status>
        <Text as="p" style="body-s" tone="muted" className="setup-note">
          {t(
            "The Docker install has a built-in HTTPS door: https://houseos.local:8443 on the Wi-Fi (or the server's IP on port 8443). Its certificate is made on this server: browsers warn once. To remove the warning on a phone, install this certificate there and trust it.",
          )}
        </Text>
        <Cluster>
          <LinkButton href="/api/v1/access/certificate" download icon="download">
            {t("Download the certificate")}
          </LinkButton>
          {access.data?.current && (
            <Button
              icon={copied ? "check" : "copy"}
              onClick={async () => {
                const https =
                  location.protocol === "https:"
                    ? location.origin
                    : `https://${location.hostname}:8443`;
                await navigator.clipboard?.writeText(https);
                setCopied(true);
              }}
            >
              {copied ? t("Copied") : t("Copy the secure address")}
            </Button>
          )}
        </Cluster>
      </Section>
    </>
  );
}

/** Home, for the admin until the essentials are ready: how far setup is, one tap to go on. */

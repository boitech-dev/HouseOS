// The cascade layers' order, then the themes' tokens, then the design system.
import "./design/layers.css";
import "./design/generated/themes.css";
import "./design/base.css";
import "./design/controls.css";
import "./design/display.css";
import "./design/overlays.css";
import "./design/patterns.css";
import { applyChoice, reapply, restoreTheme, setInstalled } from "./design/theme";
import { t, useI18n, I18nProvider, restoreLanguage, type Language } from "./i18n";
import React, { useState, useEffect, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import {
  ApiError,
  api,
  setCSRF,
  useData,
  clearCache,
  invalidate,
  UserContext,
  type Obj,
} from "./api";
import {
  Button,
  ConfirmSheet,
  Field,
  Form,
  Input,
  Notice,
  Page,
  Problem,
  SecretInput,
  Slot,
  State,
  Text,
} from "./design";
import "./main.css";
import { Music, Speaker } from "./music";
import { Household, InboxPage } from "./household";
import { TV } from "./cinema";
import { Home } from "./home";
import { Watch } from "./watch";
import { Assistant } from "./ask";
import "@fontsource/jacquard-12/latin-400.css";
import "@fontsource/jacquard-12/latin-ext-400.css";
import "@fontsource/alegreya-sans/latin-400.css";
import "@fontsource/alegreya-sans/latin-ext-400.css";
import "@fontsource/alegreya-sans/latin-500.css";
import "@fontsource/alegreya-sans/latin-ext-500.css";
import "@fontsource/alegreya-sans/latin-700.css";
import "@fontsource/alegreya-sans/latin-ext-700.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-ext-400.css";
import { Shell, type Live } from "./shell";
import { go, canonical, normalizeLocation } from "./nav";
import { localStore } from "./local";
import { setOutboxOwner } from "./outbox";
if ("serviceWorker" in navigator && window.isSecureContext)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
// Rooms most visits never open load on demand; the rest stays in the main bundle.
// The service worker pre-caches every chunk, so offline Capture still opens.
const Files = lazy(() => import("./files").then((m) => ({ default: m.Files })));
const Capture = lazy(() => import("./files").then((m) => ({ default: m.Capture })));
const Preferences = lazy(() => import("./me").then((m) => ({ default: m.Preferences })));
const Admin = lazy(() => import("./control").then((m) => ({ default: m.Admin })));
const Party = lazy(() => import("./party").then((m) => ({ default: m.Party })));
const PersonalSpace = lazy(() =>
  import("./personal_space").then((m) => ({ default: m.PersonalSpace })),
);
const Games = lazy(() => import("./games").then((m) => ({ default: m.Games })));
const GamePlayer = lazy(() => import("./games_player").then((m) => ({ default: m.GamePlayer })));
const SmartHome = lazy(() => import("./smarthome").then((m) => ({ default: m.SmartHome })));
const Workshop = lazy(() => import("./workshop").then((m) => ({ default: m.Workshop })));
const Remix = lazy(() => import("./remix").then((m) => ({ default: m.Remix })));
// A tab left open across a release may ask for a chunk that no longer exists: reload once.
addEventListener("vite:preloadError", (event) => {
  if (sessionStorage.getItem("houseos-reloaded")) return;
  sessionStorage.setItem("houseos-reloaded", "1");
  event.preventDefault();
  location.reload();
});
// Booted fine: a later release in this tab may reload again.
setTimeout(() => sessionStorage.removeItem("houseos-reloaded"), 10000);

function Auth({ onLogin }: { onLogin: () => void }) {
  const { data, error, reload } = useData("/auth/status");
  const invite =
    location.pathname === "/join"
      ? location.hash.slice(1)
      : location.pathname.startsWith("/invite/")
        ? location.pathname.split("/").pop()
        : null;
  const bootstrap = data?.needs_setup || data?.bootstrap_required || data?.setup_required;
  const joining = bootstrap || invite;
  return (
    <main className="auth">
      <Slot id="auth.crest" className="auth__crest" />
      <Text as="p" style="label" tone="accent">
        {t("A PLACE TO COME HOME TO")}
      </Text>
      <Text as="h1" style="display-l">
        {t("MIDNIGHT HOUSE")}
      </Text>
      <Text as="p" tone="muted">
        {invite
          ? t("Your invitation is waiting.")
          : bootstrap
            ? t("Let’s open the house.")
            : t("The lights are on. Welcome back.")}
      </Text>
      <Problem error={error} onRetry={reload} />
      <Form
        submit={
          invite ? t("Join the house") : bootstrap ? t("Create administrator") : t("Come inside")
        }
        onSubmit={async (f) => {
          const body: Obj = { username: f.get("username"), password: f.get("password") };
          if (invite) {
            body.token = invite;
            body.name = f.get("name");
          } else if (bootstrap) {
            body.name = f.get("name");
            body.setup_token = f.get("setup_token");
          }
          await api(
            invite ? "/auth/redeem" : bootstrap ? "/auth/bootstrap" : "/auth/login",
            "POST",
            body,
          );
          onLogin();
        }}
      >
        {joining && (
          <Field label={t("Your name")}>
            <Input name="name" autoComplete="name" required maxLength={100} />
          </Field>
        )}
        <Field label={t("Username")}>
          <Input
            name="username"
            autoComplete="username"
            required
            minLength={3}
            maxLength={80}
            pattern="[a-zA-Z0-9_.\-]+"
          />
        </Field>
        <Field label={joining ? t("Choose a password (at least 12 characters)") : t("Password")}>
          <Input
            type="password"
            name="password"
            autoComplete={joining ? "new-password" : "current-password"}
            required
            minLength={joining ? 12 : 1}
          />
        </Field>
        {bootstrap && (
          <Field
            label={t("Setup code (from the server)")}
            hint={
              <>
                {t(
                  "A one-time code that proves you own this server. Docker: on the server, run this in the HouseOS folder and copy what it prints:",
                )}{" "}
                <code>docker compose exec api houseos-entrypoint setup-code</code>
              </>
            }
          >
            <SecretInput name="setup_token" required />
          </Field>
        )}
      </Form>
      <Text as="p" style="caption" tone="subtle">
        {t("Private by design. Your assistant and files belong to you.")}
      </Text>
    </main>
  );
}
// Plain http:// from another device (localhost counts as secure): voice, the app install and
// notifications stay off there. Dismissed for the rest of this visit.
function InsecureNotice() {
  const [shown, setShown] = useState(() => {
    try {
      return !window.isSecureContext && !sessionStorage.getItem("houseos-http-notice");
    } catch {
      return !window.isSecureContext;
    }
  });
  if (!shown) return null;
  return (
    <Notice
      onDismiss={() => {
        setShown(false);
        try {
          sessionStorage.setItem("houseos-http-notice", "1");
        } catch {
          /* private mode: this page only */
        }
      }}
    >
      {t("Open the https:// address for voice, the app install and notifications.")}
    </Notice>
  );
}
function App() {
  useEffect(() => {
    const viewport = window.visualViewport;
    const resize = () =>
      document.documentElement.style.setProperty(
        "--visible-height",
        `${viewport?.height ?? window.innerHeight}px`,
      );
    resize();
    viewport?.addEventListener("resize", resize);
    window.addEventListener("resize", resize);
    return () => {
      viewport?.removeEventListener("resize", resize);
      window.removeEventListener("resize", resize);
    };
  }, []);
  const { setLanguage } = useI18n();
  const [house, setHouse] = useState<Obj>({
    name: "MIDNIGHT HOUSE",
    preferences: { timezone: "UTC", language: "en" },
  });
  useEffect(() => {
    if (!house.preferences.sounds) return;
    let audio: AudioContext | undefined;
    const cue = () => {
      try {
        audio ||= new AudioContext();
        if (audio.state !== "running") return;
        const oscillator = audio.createOscillator(),
          gain = audio.createGain();
        oscillator.frequency.value = 660;
        gain.gain.setValueAtTime(0.025, audio.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.12);
        oscillator.connect(gain);
        gain.connect(audio.destination);
        oscillator.start();
        oscillator.stop(audio.currentTime + 0.12);
      } catch {}
    };
    const unlock = () => {
      audio ||= new AudioContext();
      void audio.resume().catch(() => {});
    };
    addEventListener("pointerdown", unlock, { once: true });
    addEventListener("keydown", unlock, { once: true });
    addEventListener("houseos:message-sent", cue);
    return () => {
      removeEventListener("pointerdown", unlock);
      removeEventListener("keydown", unlock);
      removeEventListener("houseos:message-sent", cue);
      void audio?.close().catch(() => {});
    };
  }, [house.preferences.sounds]);
  // Themes made here (your drafts, and the house's shared ones) join the bundled themes.
  const loadThemes = () =>
    api("/themes")
      .then((value) => {
        setInstalled(value.items);
        reapply();
      })
      .catch(() => {});
  const loadHouse = () =>
    api("/house-settings")
      .then((value) => {
        setHouse(value);
        setLanguage(value.preferences.language || "en");
        document.documentElement.dataset.motion = value.preferences.motion || "subtle";
        try {
          localStorage.setItem("houseos-motion", value.preferences.motion || "subtle");
        } catch {}
        applyChoice(value.preferences, value);
      })
      .catch(() => {});
  useEffect(() => {
    addEventListener("house-settings-updated", loadHouse);
    return () => removeEventListener("house-settings-updated", loadHouse);
  }, []);
  useEffect(() => {
    const visibility = () => (document.documentElement.dataset.hidden = String(document.hidden));
    document.addEventListener("visibilitychange", visibility);
    return () => document.removeEventListener("visibilitychange", visibility);
  }, []);
  const [user, setUser] = useState<Obj | null>(null),
    [checking, setChecking] = useState(true),
    [actionError, setActionError] = useState(""),
    [discard, setDiscard] = useState<"drafts" | "account" | null>(null),
    [offlineActor, setOfflineActor] = useState<Obj | null>(null),
    [path, setPath] = useState(normalizeLocation),
    [online, setOnline] = useState(navigator.onLine),
    [stream, setStream] = useState<"online" | "reconnecting">("online");
  useEffect(() => {
    const onFailure = (e: PromiseRejectionEvent) => {
      if (
        e.reason instanceof ApiError ||
        (e.reason instanceof TypeError && /fetch|network/i.test(e.reason.message))
      ) {
        e.preventDefault();
        setActionError(e.reason.message);
      }
    };
    addEventListener("unhandledrejection", onFailure);
    return () => removeEventListener("unhandledrejection", onFailure);
  }, []);
  const load = async () => {
    try {
      const me = await api("/auth/me");
      setCSRF(me.csrf_token);
      setUser(me.user || me);
      setOutboxOwner((me.user || me).id);
      void loadHouse();
      void loadThemes();
      setOfflineActor(null);
      await localStore("set", "last_account", {
        id: me.user.id,
        name: me.user.name,
      });
    } catch {
      clearCache();
      setInstalled([]);
      setUser(null);
      if (!navigator.onLine) {
        const last = await localStore("get", "last_account").catch(() => null);
        setOfflineActor(last);
        if (last?.id) setOutboxOwner(last.id); // changes made offline wait for this person
      }
    } finally {
      setChecking(false);
    }
  };
  useEffect(() => {
    void load();
    const route = () => setPath(canonical(location.pathname)),
      on = () => {
        setOnline(navigator.onLine);
        if (navigator.onLine) void load();
      };
    addEventListener("popstate", route);
    addEventListener("online", on);
    addEventListener("offline", on);
    return () => {
      removeEventListener("popstate", route);
      removeEventListener("online", on);
      removeEventListener("offline", on);
    };
  }, []);
  useEffect(() => {
    // Unless the new page already put focus on its first field (the palette's "New task").
    const main = document.getElementById("main");
    if (!main?.contains(document.activeElement)) main?.focus();
    // House names its own tabs (household.tsx).
    if (path === "/house") return;
    const names: Record<string, string> = {
      "/listen": "Listen",
      "/speaker": "Speaker mode",
      "/watch": "Watch",
      "/house": "House",
      "/files": "Files",
      "/me": "Your preferences",
      "/control": "Control Room",
      "/space": "My space",
      "/assistant": "Nox",
      "/inbox": "Inbox",
      "/smart-home": "Smart home",
      "/games": "Games",
      "/capture": "Send something home",
      "/party": "Party mode",
      "/workshop": "Theme workshop",
      "/workshop/remix": "Remix",
    };
    document.title = (names[path] ? t(names[path]) + " · " : "") + (house.name || "Midnight House");
  }, [path, house.name]);
  useEffect(() => {
    if (!user) return;
    const events = new EventSource("/api/v1/events");
    // Only report trouble when live updates have been gone for a while; refresh on return.
    let lost: ReturnType<typeof setTimeout> | undefined,
      dropped = false;
    events.onerror = () => {
      if (lost) return;
      lost = setTimeout(() => {
        dropped = true;
        setStream("reconnecting");
      }, 5000);
    };
    events.onopen = () => {
      clearTimeout(lost);
      lost = undefined;
      if (dropped) invalidate();
      dropped = false;
      setStream("online");
    };
    events.addEventListener("revoked", () => void load());
    events.addEventListener("change", (event) => {
      let topic: string | undefined;
      try {
        topic = JSON.parse((event as MessageEvent).data).topic;
      } catch {}
      if (topic === "account.updated") void load();
      if (topic === "themes.changed") void loadThemes();
      window.dispatchEvent(new CustomEvent("houseos:change", { detail: { topic } }));
    });
    return () => {
      clearTimeout(lost);
      events.close();
    };
  }, [user?.id]);
  if (checking)
    return (
      <main className="auth" aria-busy="true">
        <Slot id="auth.crest" className="auth__crest" />
        <Text as="p" tone="muted">
          {t("Opening the house…")}
        </Text>
      </main>
    );
  if (!user && offlineActor && !online)
    return (
      <Page>
        <Notice tone="warning" title={t("Offline Capture for") + " " + offlineActor.name}>
          {t(
            "These drafts stay on this device. Sign in again before uploading; household data is unavailable offline.",
          )}
        </Notice>
        <Suspense fallback={<State kind="loading" />}>
          <Capture offlineActor={offlineActor} />
        </Suspense>
        <Button variant="danger" onClick={() => setDiscard("account")}>
          {t("Clear device drafts and account label")}
        </Button>
        {discard === "account" && (
          <ConfirmSheet
            title={t("Delete this device’s drafts and offline account label?")}
            confirm={t("Clear device drafts and account label")}
            danger
            onClose={() => setDiscard(null)}
            onConfirm={async () => {
              await localStore("clear");
              setDiscard(null);
              setOfflineActor(null);
            }}
          >
            <Text>{t("The drafts on this device are lost; nothing at home changes.")}</Text>
          </ConfirmSheet>
        )}
      </Page>
    );
  if (!user)
    return (
      <Auth
        onLogin={() => {
          go(location.pathname === "/capture" ? location.pathname + location.search : "/");
          void load();
        }}
      />
    );
  const can = (route: string) => {
    if (route === "/space") return user.role === "admin" || user.role === "resident";
    if (route === "/smart-home")
      return (
        !!house.smart_home &&
        (user.role === "admin" || !!user.permissions?.includes("home.control"))
      );
    if (user.role === "admin") return true;
    const required: Record<string, string> = {
      "/listen": "music.read",
      "/party": "music.read",
      "/speaker": "music.read",
      "/house": "household.read",
      "/files": "files.read",
      "/inbox": "messages.read",
      "/assistant": "assistant.use",
      "/watch": "cinema.use",
      "/tv": "cinema.use",
      "/games": "games.play",
      "/capture": "household.write",
      "/control": "admin",
    };
    const need = required[route.startsWith("/games/") ? "/games" : route];
    return !need || user.permissions?.includes(need);
  };
  let page;
  switch (path) {
    case "/listen":
      page = <Music />;
      break;
    case "/party":
      page = <Party />;
      break;
    case "/speaker":
      page = <Speaker />;
      break;
    case "/house":
      page = <Household storage={can("/listen")} />;
      break;
    case "/inbox":
      page = <InboxPage />;
      break;
    case "/files":
      page = <Files />;
      break;
    case "/watch":
      page = <Watch />;
      break;
    case "/tv":
      page = <TV />;
      break;
    case "/assistant":
      page = <Assistant />;
      break;
    case "/space":
      page = <PersonalSpace />;
      break;
    case "/me":
      page = <Preferences user={user} />;
      break;
    case "/control":
      page =
        user.role === "admin" ? (
          <Admin />
        ) : (
          <State kind="no-permission" title={t("Administrator access required")} />
        );
      break;
    case "/capture":
      page = <Capture />;
      break;
    case "/smart-home":
      page = <SmartHome />;
      break;
    case "/games":
      page = <Games />;
      break;
    case "/workshop":
    case "/workshop/remix":
      page =
        user.role !== "admin" ? (
          <State
            kind="no-permission"
            title={t("Making themes is for the house's administrators.")}
          />
        ) : path === "/workshop" ? (
          <Workshop />
        ) : (
          <Remix />
        );
      break;
    default:
      page = path.startsWith("/games/play/") ? (
        <GamePlayer id={path.slice("/games/play/".length)} />
      ) : (
        <Home guest={user.role === "guest"} assistant={can("/assistant")} />
      );
  }
  if (!can(path))
    page = (
      <State kind="no-permission" title={t("This room isn’t included in your invitation.")}>
        {t("Your music queue is still available.")}
      </State>
    );
  const signOut = async () => {
    if ((await localStore("get", "has_drafts")) && discard !== "drafts")
      return setDiscard("drafts");
    setDiscard(null);
    await api("/auth/logout", "POST");
    await localStore("clear");
    setInstalled([]);
    clearCache();
    setCSRF("");
    setUser(null);
    setOfflineActor(null);
  };
  const changeLanguage = async (value: Language) => {
    await api("/account/profile", "PATCH", { language: value });
    setLanguage(value);
    void loadHouse();
  };
  const live: Live = !online ? "offline" : stream;
  return (
    <UserContext.Provider value={user}>
      <Shell
        user={user}
        house={house}
        path={path}
        can={can}
        live={live}
        onSignOut={signOut}
        onLanguage={changeLanguage}
      >
        {!online && (
          <Notice tone="warning">{t("You’re offline. Device commands won’t be queued.")}</Notice>
        )}
        <InsecureNotice />
        {actionError && (
          <Notice tone="danger" onDismiss={() => setActionError("")}>
            {t(actionError)}
          </Notice>
        )}
        {discard === "drafts" && (
          <ConfirmSheet
            title={t("Discard your unsent device drafts and sign out?")}
            confirm={t("Sign out")}
            danger
            onClose={() => setDiscard(null)}
            onConfirm={signOut}
          >
            <Text>{t("They were never sent, so they can’t be recovered.")}</Text>
          </ConfirmSheet>
        )}
        <Suspense fallback={<State kind="loading" />}>{page}</Suspense>
      </Shell>
    </UserContext.Provider>
  );
}
// The device's last theme, motion and language apply before the first paint, so nothing flashes.
restoreTheme();
try {
  document.documentElement.dataset.motion = localStorage.getItem("houseos-motion") || "subtle";
} catch {}
void restoreLanguage().then(() =>
  createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <I18nProvider>
        <App />
      </I18nProvider>
    </React.StrictMode>,
  ),
);

import type { IconName } from "./design/icons";
// Routes of the house. Old paths stay valid as aliases, so bookmarks and links keep working.
export const ALIASES: Record<string, string> = {
  "/music": "/listen",
  "/cinema": "/watch",
  "/settings": "/me",
  "/admin": "/control",
  "/design": "/workshop",
  "/workbench": "/workshop",
};

export const canonical = (path: string) => ALIASES[path] ?? path;

/** In-app navigation: canonical path, history entry, top of the new page. */
export function go(target: string) {
  const url = new URL(target, location.origin);
  history.pushState({}, "", canonical(url.pathname) + url.search + url.hash);
  dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}

/** On first load, an old path becomes its canonical one without a new history entry. */
export function normalizeLocation() {
  const path = canonical(location.pathname);
  if (path !== location.pathname)
    history.replaceState({}, "", path + location.search + location.hash);
  return path;
}

/** Control Room's places, by group: id, icon, name, and what you set there (shown on the
 * overview; the palette also finds a place by these words). */
export const CONTROL_GROUPS: [string, [string, IconName, string, string][]][] = [
  [
    "Status",
    [
      ["setup", "wrench", "Setup", "First steps, what is left to connect"],
      ["health", "shield-check", "Health", "Checks, disk, services, what is failing"],
      ["jobs", "clock", "Jobs", "Background work: downloads, films, backups"],
      ["logs", "newspaper", "Logs", "Who did what, and what needs you"],
    ],
  ],
  [
    "People",
    [
      ["users", "people", "Users", "Residents, guests, roles, sign-outs"],
      ["invites", "mail", "Invites", "Invite links and who can join"],
    ],
  ],
  [
    "Devices",
    [
      ["devices", "tv", "Devices", "TVs, Chromecasts, speakers, pairing"],
      ["speakers", "speaker", "Speakers", "Where the music plays, volume cap, sound test"],
    ],
  ],
  [
    "AI & connections",
    [
      ["ai", "bot", "AI", "Nox's models, sign-ins, helper updates"],
      ["integrations", "plug", "Integrations", "Home Assistant, films, YouTube, news"],
      ["usage", "trend-up", "Usage", "AI spending per person and per model"],
    ],
  ],
  [
    "Storage & backups",
    [
      ["storage", "storage", "Storage", "Space used, songs, films, uploads, quotas"],
      ["recovery", "archive", "Recovery", "Backups, schedule, how to restore"],
    ],
  ],
  [
    "House",
    [
      ["house", "home", "House", "Name, language, music rules, preloading, keeping songs"],
      ["themes", "palette", "Themes", "Default theme, making and sharing themes"],
      ["access", "shield", "Access", "Addresses, HTTPS, who can reach the house"],
      ["services", "settings", "Services", "Restart, update, the parts that run the house"],
      ["changes", "edit", "Changes", "Code changes Nox drafted: review, apply, undo"],
    ],
  ],
];
export const CONTROL_PLACES = CONTROL_GROUPS.flatMap(([, places]) => places);

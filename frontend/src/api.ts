import { getLanguage, t } from "./i18n";
import { knownCode, message } from "./messages";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
export type Obj = Record<string, any>;
let csrf = "";
export function setCSRF(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: Obj | string,
  ) {
    // Always a translated sentence: a known code's own text, else the server's words.
    super(
      Array.isArray(detail)
        ? t("Something in this form isn't valid. Check it and try again.")
        : typeof detail === "string"
          ? message(detail)
          : detail.code && knownCode(detail.code)
            ? message(detail.code)
            : message(detail.message || detail.code || "Request failed"),
    );
  }
}
/** `body` is sent as JSON, or as is when it is FormData, a file or bytes (a save, a recording).
 *  Small bytes still arrive when the page closes (browsers cap keepalive at 64 KB). */
export async function api<T = Obj>(path: string, method = "GET", body?: unknown): Promise<T> {
  const bytes = body instanceof Blob ? body.size : ArrayBuffer.isView(body) ? body.byteLength : -1;
  const raw = body instanceof FormData || bytes >= 0;
  const response = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body !== undefined && !raw ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRF-Token": csrf } : {}),
    },
    body: body === undefined ? undefined : raw ? (body as BodyInit) : JSON.stringify(body),
    keepalive: bytes >= 0 && bytes < 65536,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: "Service unavailable" }));
    throw new ApiError(response.status, data.detail || "Request failed");
  }
  // Your own change may touch anything cached: nothing counts as fresh any more (reads shown
  // right now still wait for the server's event; the next page opened revalidates).
  if (method !== "GET") for (const entry of cache.values()) entry.stale = true;
  return response.status === 204 ? (undefined as T) : response.json();
}
// Shared query cache: one entry per path, shared by every mounted useData hook.
type Snapshot = { data: unknown; error: string; loading: boolean; at: number };
type Entry = {
  snap: Snapshot;
  listeners: Set<() => void>;
  intervals: Map<symbol, number>;
  seq: number;
  stale: boolean;
  promise?: Promise<void>;
  poll?: ReturnType<typeof setInterval>;
  debounce?: ReturnType<typeof setTimeout>;
  evict?: ReturnType<typeof setTimeout>;
};
const EMPTY: Snapshot = { data: null, error: "", loading: false, at: 0 };
const cache = new Map<string, Entry>();
// Catalog/provider/network reads refresh explicitly, never on house events.
const EXCLUDED = [
  "/cinema/search",
  "/cinema/catalogs",
  "/cinema/browse",
  // Catalogue rows: opening a title emits cinema events, which must not refetch every row.
  "/cinema/explore",
  "/cinema/collections",
  "/cinema/for-you",
  "/music/radio",
  "/personal-space",
  "/cinema/cloud",
  "/music/search",
  "/admin/health",
  "/admin/services",
  "/admin/providers",
  "/admin/audio",
];
// Backend event topic prefix -> API path prefixes it can change. Unknown topics refresh everything.
const TOPICS: [string, string[]][] = [
  ["music.", ["/music", "/activity"]],
  ["cinema.", ["/cinema", "/activity"]],
  ["games.", ["/games"]],
  ["household.", ["/household"]],
  ["inbox.", ["/household"]],
  ["files.", ["/files", "/music/storage", "/admin/storage"]],
  ["assistant.", ["/assistant"]],
  ["preferences.", ["/preferences", "/house-settings", "/account"]],
  ["house.settings", ["/house-settings", "/admin/house-settings", "/preferences"]],
  ["account.", ["/account", "/auth", "/people", "/preferences", "/house-settings"]],
  ["invite.", ["/auth/invites", "/admin/users", "/people"]],
  ["audit.ai_request", ["/usage", "/admin"]],
  ["audit.tool_call", ["/usage", "/admin"]],
  ["audit.provider_failure", ["/usage", "/admin"]],
  ["audit.budget_warning", ["/usage", "/admin"]],
  ["audit.storage_reclaim", ["/admin/storage", "/files", "/music", "/cinema"]],
  ["audit.service_restart", ["/admin", "/operations"]],
  // Background notes (maintenance, language builds); unlisted they would refetch every tab's data.
  ["system.", ["/admin/activity", "/languages"]],
];
function entryFor(path: string) {
  let entry = cache.get(path);
  if (!entry)
    cache.set(
      path,
      (entry = { snap: EMPTY, listeners: new Set(), intervals: new Map(), seq: 0, stale: false }),
    );
  return entry;
}
function update(entry: Entry, change: Partial<Snapshot>) {
  entry.snap = { ...entry.snap, ...change };
  entry.listeners.forEach((listener) => listener());
}
/** Fetch into the cache. Concurrent unforced loads share one request; a forced load supersedes it. */
function load(path: string, force = false): Promise<void> {
  const entry = entryFor(path);
  if (entry.promise && !force) return entry.promise;
  const seq = ++entry.seq;
  // Background refreshes of data already shown do not flash a loading state.
  if (entry.snap.data == null || entry.snap.error) update(entry, { loading: true });
  const run: Promise<void> = api(path)
    .then(
      (data) => {
        if (seq === entry.seq) {
          entry.stale = false;
          // Unchanged answers keep the same object, so effects and lists do not re-run.
          const same = JSON.stringify(data) === JSON.stringify(entry.snap.data);
          update(entry, {
            data: same ? entry.snap.data : data,
            error: "",
            loading: false,
            at: Date.now(),
          });
        }
      },
      (e) => {
        if (seq === entry.seq) update(entry, { error: (e as Error).message, loading: false });
      },
    )
    .then(() => {
      if (seq !== entry.seq && entry.promise && entry.promise !== run) return entry.promise;
      if (entry.promise === run) entry.promise = undefined;
    });
  entry.promise = run;
  return run;
}
function schedulePoll(path: string, entry: Entry) {
  clearInterval(entry.poll);
  entry.poll = undefined;
  const ms = Math.min(...entry.intervals.values());
  if (Number.isFinite(ms) && ms > 0)
    entry.poll = setInterval(() => {
      if (!document.hidden) void load(path);
    }, ms);
}
/** Refresh cached reads affected by a server event topic (no topic: every non-excluded read). */
export function invalidate(topic?: string) {
  const prefixes = topic ? TOPICS.find(([prefix]) => topic.startsWith(prefix))?.[1] : undefined;
  for (const [path, entry] of cache) {
    if (EXCLUDED.some((prefix) => path.startsWith(prefix))) continue;
    if (prefixes && !prefixes.some((prefix) => path.startsWith(prefix))) continue;
    entry.stale = true;
    if (!entry.listeners.size || document.hidden) continue;
    clearTimeout(entry.debounce);
    entry.debounce = setTimeout(() => void load(path, true), 200);
  }
}
/** Forget every cached read (sign-out / lost session) so no account sees another's data. */
export function clearCache() {
  for (const [path, entry] of cache) {
    clearTimeout(entry.debounce);
    entry.seq++;
    entry.promise = undefined;
    if (entry.listeners.size) {
      entry.stale = true;
      update(entry, EMPTY);
    } else {
      clearInterval(entry.poll);
      clearTimeout(entry.evict);
      cache.delete(path);
    }
  }
}
addEventListener("houseos:change", (e) => invalidate((e as CustomEvent).detail?.topic));
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  for (const [path, entry] of cache)
    if (entry.listeners.size && (entry.stale || entry.intervals.size)) void load(path);
});
function subscribe(path: string, listener: () => void) {
  const entry = entryFor(path);
  clearTimeout(entry.evict);
  entry.listeners.add(listener);
  return () => {
    entry.listeners.delete(listener);
    // ponytail: unused entries are dropped after 5 minutes; add an LRU cap if paths ever explode.
    if (!entry.listeners.size && cache.get(path) === entry)
      entry.evict = setTimeout(() => {
        if (!entry.listeners.size && cache.get(path) === entry) {
          clearTimeout(entry.debounce);
          cache.delete(path);
        }
      }, 300000);
  };
}
// Same query apart from its page offset: the previous page stays visible while the next loads.
const pageless = (path: string) => path.replace(/([?&])offset=\d+(&|$)/, "$1");
/** Cached GET. `interval` (ms, or a function of the current data) polls; shared per path, paused while hidden. */
export function useData<T = Obj>(
  path: string | null,
  options: { interval?: number | ((data: T | null) => number | false | undefined) } = {},
) {
  const subscribeTo = useCallback(
    (listener: () => void) => (path ? subscribe(path, listener) : () => {}),
    [path],
  );
  const snap = useSyncExternalStore(subscribeTo, () => (path ? entryFor(path).snap : EMPTY));
  useEffect(() => {
    if (!path) return;
    // Show what is cached at once and revalidate it, unless it is fresh: fetched in the last
    // 30 s and not changed by any event since (switching tabs back and forth costs nothing).
    const entry = entryFor(path);
    const fresh = !entry.stale && !entry.snap.error && Date.now() - entry.snap.at < 30000;
    if (!entry.promise && !fresh) void load(path);
  }, [path]);
  const key = useRef(Symbol()).current;
  const interval =
    (typeof options.interval === "function"
      ? options.interval(snap.data as T | null)
      : options.interval) || 0;
  useEffect(() => {
    if (!path || !interval) return;
    const entry = entryFor(path);
    entry.intervals.set(key, interval);
    schedulePoll(path, entry);
    return () => {
      entry.intervals.delete(key);
      schedulePoll(path, entry);
    };
  }, [path, interval]);
  const previous = useRef<{ path: string; data: unknown } | null>(null);
  let data = snap.data;
  if (path && data != null) previous.current = { path, data };
  else if (
    path &&
    !snap.error &&
    previous.current &&
    pageless(previous.current.path) === pageless(path)
  )
    data = previous.current.data;
  const reload = useCallback(() => (path ? load(path, true) : Promise.resolve()), [path]);
  const setData = useCallback(
    (value: T | null | ((current: T | null) => T | null)) => {
      if (!path) return;
      const entry = entryFor(path);
      update(entry, {
        data:
          typeof value === "function"
            ? (value as (current: T | null) => T | null)(entry.snap.data as T | null)
            : value,
      });
    },
    [path],
  );
  return {
    data: (path ? data : null) as T | null,
    error: path ? snap.error : "",
    loading: snap.loading,
    reload,
    setData,
    updatedAt: snap.at,
  };
}
/** A list that grows as you scroll: `next` gives the query for the page after `data` (e.g.
 *  "offset=24"), or null at the end. Pages merge by id, so a reload refreshes rows in place;
 *  a new `base` starts over. Put `<MoreBelow pages={…} />` after the list. */
export function usePages(base: string | null, next: (data: Obj) => string | null) {
  const [cursor, setCursor] = useState(""),
    [list, setList] = useState<Obj[]>([]);
  const path = base && base + (cursor ? (base.includes("?") ? "&" : "?") + cursor : "");
  const page = useData(path);
  useEffect(() => {
    setCursor("");
    setList([]);
  }, [base]);
  useEffect(() => {
    if (!page.data) return;
    setList((all) => {
      const fresh = new Map(items(page.data).map((row) => [row.id, row]));
      const merged = all.map((row) => fresh.get(row.id) || row);
      const known = new Set(all.map((row) => row.id));
      return [...merged, ...items(page.data).filter((row) => !known.has(row.id))];
    });
  }, [page.data]);
  const following = page.data && !page.loading ? next(page.data) : null;
  return {
    items: list,
    error: page.error,
    loading: page.loading,
    reload: page.reload,
    /** Loads the next page; undefined when there is none or one is loading. */
    more: following ? () => setCursor(following) : undefined,
    /** Changes one row in place (after an action on it). */
    patch: (id: string, change: Obj) =>
      setList((all) => all.map((row) => (row.id === id ? { ...row, ...change } : row))),
  };
}
/** The signed-in account (App owns the /auth/me session). */
export const UserContext = createContext<Obj | null>(null);
export const useUser = () => useContext(UserContext);
export function items(data: any): Obj[] {
  return Array.isArray(data) ? data : data?.items || data?.results || [];
}
/** 1:13:36 or 4:05; "—" when unknown. */
export function clock(n?: number) {
  if (!Number.isFinite(n)) return "—";
  const total = Math.max(0, Math.floor(n as number)),
    h = Math.floor(total / 3600),
    m = Math.floor((total % 3600) / 60),
    s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
export const pretty = message;
// Formatters are costly to build and these run per row: one of each per language.
const formatters = new Map<string, Intl.DateTimeFormat | Intl.NumberFormat>();
export function formatter<T extends Intl.DateTimeFormat | Intl.NumberFormat>(
  kind: string,
  make: () => T,
) {
  const key = kind + ":" + getLanguage();
  if (!formatters.has(key)) formatters.set(key, make());
  return formatters.get(key) as T;
}
export function time(s?: string) {
  if (!s) return "";
  // Compact stamps (20260925T021500Z) become ISO; anything unreadable is shown as is.
  const iso = s.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/, "$1-$2-$3T$4:$5:$6");
  const date = new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z");
  return isNaN(date.getTime())
    ? s
    : formatter(
        "time",
        () => new Intl.DateTimeFormat(getLanguage(), { dateStyle: "medium", timeStyle: "short" }),
      ).format(date);
}
/** A date or time in the app's language, Intl.DateTimeFormat's options (the default: 28/09/2026). */
export function date(value: Date | string | number, options: Intl.DateTimeFormatOptions = {}) {
  return formatter(
    "date" + JSON.stringify(options),
    () => new Intl.DateTimeFormat(getLanguage(), options),
  ).format(new Date(value));
}
/** 12,345, or "12 345" in French. */
export function number(n: number) {
  return formatter("number", () => new Intl.NumberFormat(getLanguage())).format(n);
}
/** 4.2 GB, or "4,2 Go" in French (1024-based). */
export function bytes(n: number) {
  const units =
    getLanguage() === "fr" ? ["o", "Ko", "Mo", "Go", "To"] : ["B", "KB", "MB", "GB", "TB"];
  if (!(n >= 1024)) return (Number.isFinite(n) ? n : 0) + " " + units[0];
  const power = Math.min(4, Math.floor(Math.log2(n) / 10));
  const value = formatter(
    "bytes",
    () => new Intl.NumberFormat(getLanguage(), { maximumFractionDigits: 1 }),
  ).format(n / 1024 ** power);
  return value + " " + units[power];
}
/** 42 → "42%", or "42 %" in French. */
export function percent(n: number) {
  return formatter(
    "percent",
    () => new Intl.NumberFormat(getLanguage(), { style: "percent", maximumFractionDigits: 0 }),
  ).format(n / 100);
}
export function idempotency() {
  // randomUUID exists only on secure pages; a phone on plain http:// makes a v4 UUID itself.
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
export function csrfHeaders() {
  return { "X-CSRF-Token": csrf };
}

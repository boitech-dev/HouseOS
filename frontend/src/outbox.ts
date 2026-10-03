// Offline-safe actions: a few household changes (tick a grocery, add one, add or finish a task,
// leave a note) wait on this device when the house can't be reached, and are sent in order once
// it can. Each is safe to send again: adds carry an idempotency key, ticks and "done" say the
// value rather than toggle it, and a change the house made meanwhile (a newer version) is read
// back and the same value sent once more. Everything else (music, TV, AI, admin) needs the
// house's answer, so it fails in words instead. (docs/design/SYSTEM.md, "offline-safe actions")
import { useSyncExternalStore } from "react";
import { api, ApiError, idempotency, type Obj } from "./api";
import { localStore } from "./local";

type Waiting = { key: string; path: string; method: string; body: Obj; at: number };
let owner = ""; // the signed-in person: another account on this device never sends their changes
let waiting = 0;
const listeners = new Set<() => void>();
const told = () => listeners.forEach((listener) => listener());
const prefix = () => "queued:" + owner + ":";

export function setOutboxOwner(id: string) {
  owner = id;
  void flush();
}

/** Send now, or keep it for later when the house can't be reached ("queued"). A refusal from the
 *  house itself still throws: that's an answer, not a lost connection. */
export async function sendOrKeep<T = Obj>(
  path: string,
  method: string,
  body: Obj,
): Promise<T | "queued"> {
  try {
    return await api<T>(path, method, body);
  } catch (e) {
    if (e instanceof ApiError || !owner) throw e;
    const key = prefix() + Date.now() + ":" + idempotency();
    await localStore("set", key, { key, path, method, body, at: Date.now() } satisfies Waiting);
    await count();
    return "queued";
  }
}

async function count() {
  waiting = owner ? (await localStore("list", prefix()).catch(() => [])).length : 0;
  told();
}

let flushing = false;
/** Send what waits, oldest first; stop at the first lost connection. */
export async function flush() {
  if (flushing || !owner || !navigator.onLine) return count();
  flushing = true;
  try {
    const list = ((await localStore("list", prefix()).catch(() => [])) as Waiting[]).sort(
      (a, b) => a.at - b.at,
    );
    for (const item of list) {
      try {
        await api(item.path, item.method, item.body);
      } catch (e) {
        if (!(e instanceof ApiError)) break; // still unreachable: try again later
        // Changed meanwhile: read its version and send the same value once more.
        if (e.status === 409 && "version" in item.body) {
          const record = await api(item.path.replace(/\/action$/, "")).catch(() => null);
          if (record?.version)
            await api(item.path, item.method, { ...item.body, version: record.version }).catch(
              () => {},
            );
        }
        // Any other answer (already done, already on the list) is final: nothing left to send.
      }
      await localStore("delete", item.key).catch(() => {});
    }
  } finally {
    flushing = false;
    await count();
  }
}

/** How many changes wait on this device. */
export function useWaiting() {
  return useSyncExternalStore(
    (listener) => (listeners.add(listener), () => listeners.delete(listener)),
    () => waiting,
  );
}

if (typeof window !== "undefined") {
  addEventListener("online", () => void flush());
  document.addEventListener("visibilitychange", () => document.hidden || void flush());
  // Retries while something waits and the page is seen (coming back, or online, sends at once).
  setInterval(() => waiting && !document.hidden && void flush(), 30000);
}

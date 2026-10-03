import { t } from "./i18n";
// Explicit, actor-scoped drafts, and the few offline-safe household actions (outbox.ts, D22).
export async function localStore(
  action: "get" | "set" | "delete" | "clear" | "list",
  key = "",
  value?: unknown,
): Promise<any> {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open("houseos-local", 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore("drafts");
    opening.onerror = () => reject(new Error(t("Storage on this device is unavailable.")));
    opening.onsuccess = () => {
      const db = opening.result;
      const tx = db.transaction("drafts", "readwrite");
      const store = tx.objectStore("drafts");
      if (action === "list") {
        const rows: any[] = [];
        const cursor = store.openCursor();
        cursor.onsuccess = () => {
          const c = cursor.result;
          if (c) {
            if (String(c.key).startsWith(key)) rows.push(c.value);
            c.continue();
          }
        };
        tx.oncomplete = () => {
          db.close();
          resolve(rows);
        };
        tx.onerror = () => {
          db.close();
          reject(new Error(t("Could not read local drafts")));
        };
        return;
      }
      let request: IDBRequest;
      switch (action) {
        case "get":
          request = store.get(key);
          break;
        case "set":
          request = store.put(value, key);
          break;
        case "delete":
          request = store.delete(key);
          break;
        default:
          request = store.clear();
      }
      let result: unknown;
      request.onsuccess = () => {
        result = request.result;
      };
      tx.oncomplete = () => {
        db.close();
        resolve(result);
      };
      tx.onerror = () => {
        db.close();
        reject(new Error(t("Could not save on this device")));
      };
    };
  });
}

export async function claimIncomingShare(
  id: string,
  actorId: string,
): Promise<{ text: string; count: number }> {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open("houseos-local", 1);
    opening.onerror = () => reject(new Error(t("Storage on this device is unavailable.")));
    opening.onsuccess = () => {
      const db = opening.result,
        tx = db.transaction("drafts", "readwrite"),
        store = tx.objectStore("drafts");
      let result = { text: "", count: 0 };
      const request = store.get("incoming:" + id);
      request.onsuccess = () => {
        const value = request.result;
        if (!value || (value.expected_actor && value.expected_actor !== actorId)) {
          tx.abort();
          return;
        }
        for (const file of value.files || []) {
          const identity = crypto.randomUUID();
          store.put(
            { id: identity, file, name: file.name, reservation: null },
            "outbox:" + actorId + ":" + identity,
          );
        }
        if (value.text) store.put(value.text, "capture:" + actorId);
        result = { text: value.text || "", count: value.files?.length || 0 };
        store.put(true, "has_drafts");
        store.delete("incoming:" + id);
      };
      tx.oncomplete = () => {
        db.close();
        resolve(result);
      };
      tx.onabort = tx.onerror = () => {
        db.close();
        reject(new Error(t("This share is unavailable or belongs to a different account.")));
      };
    };
  });
}

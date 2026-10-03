import { api, csrfHeaders, idempotency, type Obj } from "./api";
import { localStore } from "./local";
import { t } from "./i18n";

/** Cancel a tus reservation; already-gone uploads count as cancelled. */
export async function cancelUpload(reservation: Obj) {
  const response = await fetch(reservation.upload_url, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { ...csrfHeaders(), "Tus-Resumable": "1.0.0" },
  });
  if (!response.ok && ![404, 410].includes(response.status))
    throw new Error(t("Cancellation could not be confirmed. Retry cancelling this upload."));
}

// Shared Files/Cinema/outbox transport: one reservation, authenticated resumable chunks.
// A stable idempotencyKey lets a retry find a reservation that was already stored.
export async function transferFile(
  file: File,
  options: {
    actorId: string;
    scope: string;
    parentId?: string;
    signal?: AbortSignal;
    idempotencyKey?: string;
    cancelled?: () => boolean;
    onReservation?: (reservation: Obj) => void;
    onProgress: (progress: Obj) => void;
  },
): Promise<Obj> {
  const check = () => {
    if (options.signal?.aborted || options.cancelled?.()) throw new Error(t("Upload cancelled."));
  };
  const progress = (status: string, offset: number) =>
    options.onProgress({ name: file.name, size: file.size, offset, status });
  progress("preparing", 0);
  const fingerprintBytes = await crypto.subtle.digest(
    "SHA-256",
    await new Blob([
      file.slice(0, 1048576),
      file.slice(Math.max(0, file.size - 1048576)),
    ]).arrayBuffer(),
  );
  const fingerprint = Array.from(new Uint8Array(fingerprintBytes), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  const key = [
    "upload",
    options.actorId,
    options.scope,
    options.parentId || "root",
    file.name,
    file.lastModified,
    file.size,
    fingerprint,
  ].join(":");
  let reservation: Obj | null = await localStore("get", key);
  try {
    check();
    if (reservation) {
      const head = await fetch(reservation.upload_url, {
        method: "HEAD",
        credentials: "same-origin",
        headers: { "Tus-Resumable": "1.0.0" },
        signal: options.signal,
      });
      if (head.ok) reservation.offset = Number(head.headers.get("Upload-Offset") || 0);
      else reservation = null;
    }
    if (!reservation) {
      reservation = await api("/files/uploads", "POST", {
        name: file.name,
        size: file.size,
        scope: options.scope,
        parent_id: options.parentId || null,
        idempotency_key: options.idempotencyKey || idempotency(),
      });
      await localStore("set", key, reservation);
    }
    if (!reservation) throw new Error(t("Upload reservation was not created."));
    options.onReservation?.(reservation);
    let offset = reservation.status === "stored" ? file.size : Number(reservation.offset) || 0;
    if (!Number.isSafeInteger(offset) || offset < 0 || offset > file.size)
      throw new Error(t("The server returned an invalid upload offset."));
    progress("uploading", offset);
    while (offset < file.size) {
      check();
      const chunk = file.slice(offset, offset + 8 * 1024 * 1024);
      const response = await fetch(reservation.upload_url, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          ...csrfHeaders(),
          "Tus-Resumable": "1.0.0",
          "Upload-Offset": String(offset),
          "Content-Type": "application/offset+octet-stream",
        },
        body: chunk,
        signal: options.signal,
      });
      if (!response.ok) throw new Error(t("Upload interrupted. Reselect the same file to resume."));
      const next = Number(response.headers.get("Upload-Offset"));
      if (!Number.isSafeInteger(next) || next !== offset + chunk.size)
        throw new Error(t("The server did not confirm the upload offset."));
      offset = next;
      progress("uploading", offset);
    }
    check();
    progress("server finalizing", file.size);
    const stored = await api("/files/uploads/" + reservation.id + "/finalize", "POST");
    await localStore("delete", key);
    progress("stored", file.size);
    return stored.file;
  } catch (error) {
    if (options.signal?.aborted || options.cancelled?.()) {
      if (reservation) await cancelUpload(reservation);
      await localStore("delete", key);
      throw new Error(t("Upload cancelled."));
    }
    throw error;
  }
}

/* Public shell only. Private API responses and files are never cached.
   Its page is asked for without cookies and kept under "/". */
const CACHE = "houseos-shell-77e040da4c01b14b";
const shellPath = (p) =>
  p === "/" ||
  p === "/manifest.webmanifest" ||
  p.startsWith("/assets/") ||
  p.startsWith("/art/");
self.addEventListener("install", (event) =>
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      const response = await fetch("/", {
        credentials: "omit",
        cache: "reload",
      });
      if (!response.ok) throw new Error("Shell unavailable");
      const html = await response.clone().text();
      if (!html.includes('id="root"')) throw new Error("Unexpected shell");
      await cache.put("/", response);
      const paths = [
        ...html.matchAll(/(?:src|href)="(\/assets\/[^"?]+)"/g),
      ].map((m) => m[1]);
      // Every built chunk (lazy rooms, the French dictionary), so they work offline too.
      paths.push(
        ...["/assets/browser-CiIEd6wK.js","/assets/control-DyHf4UZk.js","/assets/files-BPtyc6kW.js","/assets/files-D_wf3a4-.css","/assets/games-BLVi4Aje.css","/assets/games-DL9nKBmH.js","/assets/games_player-DwXZFFJr.js","/assets/index-CtguNO3K.css","/assets/index-DyFYBG9b.js","/assets/locale_fr-s0onLBg2.js","/assets/me-C9tUYbfq.js","/assets/me-D-2i5kM4.css","/assets/me-sOiJ0kS1.css","/assets/onboarding-BYXpER5u.css","/assets/onboarding-CE8f9R4X.js","/assets/party-BEYMQWnF.js","/assets/personal_space-C_gPwBYc.css","/assets/personal_space-cBxraIOr.js","/assets/remix-0MUXl6Jh.js","/assets/setup-D0NuYZKo.css","/assets/setup-l6Q7b4r-.js","/assets/smarthome-BVbTxYj1.js","/assets/smarthome-oyZJhs5g.css","/assets/theme_preview-12ZustTn.js","/assets/theme_preview-7s_Ott8x.css","/assets/tvremote-BQQUoLGl.js","/assets/tvremote-DjAAKyRp.css","/assets/workshop-B1gpiWvO.js","/assets/workshop-WDHM0GEx.css"],
        "/art/house-crest.png",
        "/art/icon-192.png",
      );
      await Promise.all(
        paths.map(async (p) => {
          const r = await fetch(p, { credentials: "omit" });
          if (r.ok) await cache.put(p, r);
        }),
      );
      await self.skipWaiting();
    })(),
  ),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys())
        if (key.startsWith("houseos-shell-") && key !== CACHE)
          await caches.delete(key);
      await self.clients.claim();
    })(),
  ),
);
self.addEventListener("fetch", (event) => {
  const req = event.request,
    url = new URL(req.url);
  if (
    req.method !== "GET" ||
    url.origin !== location.origin ||
    url.pathname.startsWith("/api/")
  )
    return;
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(
        async () =>
          (await (await caches.open(CACHE)).match("/")) || Response.error(),
      ),
    );
    return;
  }
  if (shellPath(url.pathname) && !url.search)
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE);
        const cached = await cache.match(req);
        if (cached) return cached;
        const response = await fetch(req);
        if (response.ok && response.type === "basic")
          await cache.put(req, response.clone());
        return response;
      })(),
    );
});
self.addEventListener("push", (event) => {
  event.waitUntil(
    self.registration.showNotification("MIDNIGHT HOUSE", {
      body: "New house message",
      icon: "/art/icon-192.png",
      tag: "house-inbox",
      data: { url: "/inbox" },
    }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow("/inbox"));
});

// Installed-PWA share transport. No server write; bytes stay in explicit local staging.
self.addEventListener("fetch", (event) => {
  const req = event.request,
    url = new URL(req.url);
  if (
    req.method !== "POST" ||
    url.origin !== location.origin ||
    url.pathname !== "/capture/share"
  )
    return;
  event.respondWith(
    (async () => {
      try {
        if (!req.headers.get("Content-Type")?.startsWith("multipart/form-data"))
          return new Response(
            "Use Capture to select files manually. This share format is unsupported.",
            { status: 400 },
          );
        if (Number(req.headers.get("Content-Length") || 0) > 110 * 1024 * 1024)
          return new Response(
            "This share exceeds the 100 MB device limit. Use a direct upload when online.",
            { status: 413 },
          );
        const form = await req.formData();
        const files = form
          .getAll("files")
          .filter((v) => v instanceof File && v.name);
        const text = ["title", "text", "url"]
          .map((k) => form.get(k))
          .filter((v) => typeof v === "string" && v)
          .join("\n");
        if (
          files.length > 50 ||
          files.reduce((n, f) => n + f.size, 0) > 100 * 1024 * 1024 ||
          text.length > 10000
        )
          return new Response(
            "Share up to 50 files totaling 100 MB and a short note. Use direct upload for larger files.",
            { status: 413 },
          );
        const id = crypto.randomUUID();
        await new Promise((resolve, reject) => {
          const request = indexedDB.open("houseos-local", 1);
          request.onupgradeneeded = () =>
            request.result.createObjectStore("drafts");
          request.onerror = () => reject(Error("Local storage unavailable"));
          request.onsuccess = () => {
            const db = request.result,
              tx = db.transaction("drafts", "readwrite"),
              store = tx.objectStore("drafts");
            let owner = null,
              total = files.reduce((n, f) => n + f.size, 0);
            const cursor = store.openCursor();
            cursor.onsuccess = () => {
              const row = cursor.result;
              if (row) {
                if (row.key === "last_account") owner = row.value.id;
                if (String(row.key).startsWith("outbox:"))
                  total += row.value.file?.size || 0;
                if (String(row.key).startsWith("incoming:"))
                  total += (row.value.files || []).reduce(
                    (n, f) => n + f.size,
                    0,
                  );
                row.continue();
              } else if (total > 100 * 1024 * 1024) tx.abort();
              else {
                store.put(
                  {
                    id,
                    files,
                    text,
                    expected_actor: owner,
                    created_at: Date.now(),
                  },
                  "incoming:" + id,
                );
                store.put(true, "has_drafts");
              }
            };
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onabort = tx.onerror = () => {
              db.close();
              reject(Error("Device staging limit or storage unavailable"));
            };
          };
        });
        return Response.redirect(
          new URL("/capture?share=" + id, location.origin).href,
          303,
        );
      } catch {
        return new Response(
          "The share could not be kept on this device. Open HouseOS and select the original files again; nothing was uploaded.",
          {
            status: 507,
            headers: {
              "Content-Type": "text/plain; charset=utf-8",
              "Cache-Control": "no-store",
            },
          },
        );
      }
    })(),
  );
});

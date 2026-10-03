const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("fs");
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext();
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(c, base);
  const p = await c.newPage();
  const errors = [];
  const writes = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/") && !["GET", "HEAD"].includes(r.method()))
      writes.push(r.method() + " " + new URL(r.url()).pathname);
  });
  await p.goto(base + "/capture", { waitUntil: "domcontentloaded" });
  await p.getByRole("heading", { name: "Device file outbox" }).waitFor();
  await p.evaluate(() => navigator.serviceWorker.ready);
  await p.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const filename = "share-target-" + Date.now() + ".txt";
  const result = await p.evaluate(async (filename) => {
    const f = new FormData();
    f.set("title", "Shared from another app");
    f.set("text", "Synthetic multipart browser verification");
    f.append("files", new File(["test shared bytes"], filename, { type: "text/plain" }));
    const r = await fetch("/capture/share", { method: "POST", body: f });
    return { status: r.status, url: r.url };
  }, filename);
  assert.equal(result.status, 200);
  assert(result.url.includes("/capture?share="));
  assert.equal(writes.length, 0, "Share invoked an API mutation");
  await p.goto(result.url, { waitUntil: "domcontentloaded" });
  await p.getByRole("heading", { name: "Incoming share" }).waitFor();
  await p.locator(".ds-row", { hasText: filename }).getByText("17 B", { exact: true }).waitFor();
  await p
    .getByRole("button", {
      name: "Keep this share for Visual test resident",
      exact: true,
    })
    .click();
  await p.getByText(filename, { exact: true }).waitFor();
  assert.equal(writes.length, 0, "Claim uploaded or mutated server state");
  const keys = await p.evaluate(async () => {
    const keys = [];
    for (const cache of await caches.keys())
      for (const r of await (await caches.open(cache)).keys()) keys.push(new URL(r.url).pathname);
    return keys;
  });
  assert(!keys.some((k) => k.startsWith("/api/") || k.includes("capture/share")));
  const staged = await p.evaluate(
    async () =>
      new Promise((resolve) => {
        const r = indexedDB.open("houseos-local", 1);
        r.onsuccess = () => {
          const d = r.result,
            t = d.transaction("drafts", "readwrite");
          t.objectStore("drafts").put(
            {
              id: "wrong-account-test",
              expected_actor: "different-fixture-account",
              text: "PRIVATE CROSS ACCOUNT TEST",
              files: [],
            },
            "incoming:wrong-account-test",
          );
          t.oncomplete = () => resolve(true);
        };
      }),
  );
  await p.goto(base + "/capture?share=wrong-account-test", {
    waitUntil: "domcontentloaded",
  });
  await p
    .getByText(
      "Sign in to the account active when this share arrived. These files have not been assigned to another resident.",
      { exact: true },
    )
    .waitFor();
  assert.equal(await p.getByText("PRIVATE CROSS ACCOUNT TEST", { exact: true }).count(), 0);
  assert.equal(errors.length, 0, errors.join(";"));
  fs.writeFileSync(
    "evidence/latest/share-target-result.json",
    JSON.stringify(
      {
        passed: true,
        evidence:
          "Synthetic multipart browser/SW test, not native Android share-sheet verification",
        checks: [
          "multipartFileandText enters bounded IDB staging",
          "no API mutations on receive or claim",
          "explicit current account confirmation",
          "atomic transfer to account file outbox",
          "cross-account staged content withheld",
          "no shared payload in Cache Storage",
        ],
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  await b.close();
  console.log("PASS multipart share staging, account confirmation and no automatic upload");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

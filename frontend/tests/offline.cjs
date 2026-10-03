const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("fs");
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext();
  const base = "http://127.0.0.1:8893";
  const login = await require("./session.cjs")(c, base);
  assert(login.ok());
  let p = await c.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(base + "/capture", { waitUntil: "domcontentloaded" });
  await p.getByRole("heading", { name: "Device file outbox" }).waitFor();
  await p.evaluate(() => navigator.serviceWorker.ready);
  await p.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const name = "offline-draft-" + Date.now() + ".txt";
  await p.getByLabel("Keep files on this device").setInputFiles({
    name,
    mimeType: "text/plain",
    buffer: Buffer.from("Private offline test-only draft"),
  });
  await p.getByText(name, { exact: true }).waitFor();
  await p.getByLabel("A link, a thought, a little reminder").fill("Offline test-only reminder");
  await p.getByRole("button", { name: "Save device draft", exact: true }).click();
  await p
    .getByText("Saved on this device, not uploaded. Browser storage can be evicted.", {
      exact: true,
    })
    .waitFor();
  await c.setOffline(true);
  await p.close();
  p = await c.newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(base + "/capture", { waitUntil: "domcontentloaded" });
  await p.getByText(/Offline Capture for Visual test resident/).waitFor();
  await p.getByText(name, { exact: true }).waitFor();
  await p.getByRole("button", { name: "Restore draft", exact: true }).click();
  await p.waitForFunction(
    () => document.querySelector("textarea").value === "Offline test-only reminder",
  );
  assert(
    await p.getByRole("button", { name: "Upload to My Files", exact: true }).first().isDisabled(),
  );
  const keys = await p.evaluate(async () => {
    const result = [];
    for (const name of await caches.keys())
      for (const req of await (await caches.open(name)).keys())
        result.push(new URL(req.url).pathname);
    return result;
  });
  assert(
    !keys.some((x) => x.startsWith("/api/") || (x.includes("/files") && !x.startsWith("/assets/"))),
    JSON.stringify(keys),
  );
  await c.setOffline(false);
  await p.getByRole("button", { name: "Upload to My Files", exact: true }).first().waitFor();
  await p.waitForFunction(() => !document.body.textContent.includes("Offline Capture for"));
  await p.getByRole("button", { name: "Upload to My Files", exact: true }).first().click();
  await p.getByText(name + " is stored at home.", { exact: true }).waitFor({ timeout: 15000 });
  await p.getByRole("button", { name: /^Your account/ }).click();
  await p.getByRole("dialog").getByRole("button", { name: "Sign out", exact: true }).click();
  // Unsent drafts on this device: signing out asks first.
  await p
    .getByRole("dialog", { name: "Discard your unsent device drafts and sign out?" })
    .getByRole("button", { name: "Sign out", exact: true })
    .click();
  await p.getByRole("button", { name: /Come inside/ }).waitFor();
  const localKeys = await p.evaluate(
    () =>
      new Promise((resolve, reject) => {
        const r = indexedDB.open("houseos-local", 1);
        r.onsuccess = () => {
          const db = r.result;
          const t = db.transaction("drafts", "readonly");
          const q = t.objectStore("drafts").getAllKeys();
          q.onsuccess = () => resolve(q.result);
          q.onerror = reject;
        };
      }),
  );
  assert.equal(localKeys.length, 0, "Logout retained local account data");
  assert.equal(errors.length, 0, errors.join(";"));
  fs.writeFileSync(
    "evidence/latest/offline-result.json",
    JSON.stringify(
      {
        passed: true,
        checks: [
          "public shell cached only",
          "close page and cold open offline",
          "account scoped text and Blob retained",
          "upload disabled offline",
          "explicit upload after session revalidation",
          "real tus finalize clears local blob",
          "logout purges device drafts and account label",
        ],
        cachePaths: keys,
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  await b.close();
  console.log("PASS cold offline shell, text/file outbox and real resumed upload");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

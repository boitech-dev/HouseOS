// Offline-safe actions: a grocery ticked with no connection ticks at once, waits on the device
// ("1 changes waiting"), and reaches the house exactly once when the connection is back.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const me = await (await require("./session.cjs")(context, base)).json();
  const headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const label = "Offline oats " + Date.now();
  const made = await (
    await context.request.post(base + "/api/v1/household/groceries", {
      headers,
      data: { data: { label }, idempotency_key: "offline-" + Date.now(), allow_duplicate: true },
    })
  ).json();
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/house?tab=groceries");
  const box = page.getByRole("checkbox", { name: "Bought · " + label });
  await box.waitFor();
  await context.setOffline(true);
  await box.click();
  assert.equal(await box.isChecked(), true, "ticked at once, offline");
  await page.getByText("1 changes waiting").waitFor();
  await context.setOffline(false);
  await page.evaluate(() => dispatchEvent(new Event("online")));
  await page.getByText("1 changes waiting").waitFor({ state: "detached", timeout: 15000 });
  const saved = await (await context.request.get(base + "/api/v1/household/groceries/" + made.id)).json();
  assert.equal(saved.data.purchased, true);
  assert.equal(saved.version, made.version + 1, "sent once");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS a grocery ticked offline waits on the device and reaches the house once");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

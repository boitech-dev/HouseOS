const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
// Auto play's next songs: seen in order with their art, moved, removed and redrawn. The API is
// mocked; nothing plays.
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [],
    puts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const url = (n) => "https://www.youtube.com/watch?v=plan" + String(n).padStart(7, "0");
  let plan = [1, 2, 3].map(url),
    version = 4;
  await page.route(/\/api\/v1\/music$/, (route) =>
    route.fulfill({
      json: { items: [], version: 1, current_id: null, desired: "playing", fair: true },
    }),
  );
  await page.route("**/api/v1/music/auto", (route) =>
    route.fulfill({ json: { mode: "library", kept: 3, genres_kept: [], can_change: true } }),
  );
  let queued = ["q1"];
  const deletes = [];
  await page.route("**/api/v1/music/queue/q1", (route) => {
    deletes.push(route.request().method());
    queued = [];
    return route.fulfill({ json: { status: "completed", version: 2 } });
  });
  await page.route("**/api/v1/music/auto/upcoming", (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      puts.push(body);
      assert.equal(body.version, version);
      plan = body.shuffle ? [...plan].reverse() : body.urls;
      version += 1;
    }
    return route.fulfill({
      json: {
        mode: "library",
        version,
        can_change: true,
        // Its next pick already sits in the queue: the list starts with it.
        queued: queued.map((id) => ({ id, source_url: url(9), title: "Queued pick", removable: true })),
        items: plan.map((u) => ({ source_url: u, title: "Song " + u.slice(-1), genre: "pop" })),
      },
    });
  });
  await page.goto(base + "/listen");
  // Under the deck: what auto play plays after the queue, and the way to change it.
  await page.locator(".listen-auto").getByText("Song 1", { exact: true }).waitFor();
  await page.getByRole("button", { name: "See and change the list" }).click();
  const sheet = page.getByRole("dialog", { name: "Auto play: next songs" });
  await sheet.getByText("Song 1", { exact: true }).waitFor();
  await sheet.getByText("Already in the queue", { exact: true }).waitFor();
  await sheet.screenshot({ path: "evidence/latest/auto-plan-queued.png" });
  await sheet.getByRole("button", { name: "Remove · Queued pick" }).click();
  await until(() => deletes.length >= 1);
  assert.deepEqual(deletes, ["DELETE"]);
  await sheet.getByText("Queued pick", { exact: true }).waitFor({ state: "detached" });
  await sheet.getByRole("button", { name: "Move down · Song 1" }).click();
  await sheet.getByRole("button", { name: "Remove · Song 3" }).waitFor();
  assert.deepEqual(puts[0].urls, [url(2), url(1), url(3)]);
  await sheet.getByRole("button", { name: "Remove · Song 3" }).click();
  await until(() => puts.length >= 2);
  assert.deepEqual(puts[1].urls, [url(2), url(1)]);
  await sheet.getByRole("button", { name: "Draw a new random list" }).click();
  await until(() => puts.length >= 3);
  assert.equal(puts[2].shuffle, true);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/auto-plan-phone.png", fullPage: true });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS auto play's next songs: the queued pick first, moved, removed and redrawn (mocked)");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

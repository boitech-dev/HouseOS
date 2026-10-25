// A dropped connection (the computer slept, the house restarted) heals by itself: a shelf whose
// read failed tries again on its own and fills in, no Retry tap or page refresh needed.
// Real isolated login; every Cinema read is intercepted.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 1440, height: 900 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    tries = {};
  page.on("pageerror", (e) => errors.push(e.message));
  const poster = fs.readFileSync(__dirname + "/../public/art/tv-bezel.png");
  await page.route(/\/api\/v1\/cinema\//, async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.replace("/api/v1/cinema", "");
    if (path.endsWith("/poster")) return route.fulfill({ body: poster, contentType: "image/png" });
    if (path === "/explore") {
      tries[url.search] = (tries[url.search] || 0) + 1;
      if (tries[url.search] <= 2) return route.abort("connectionreset"); // "Failed to fetch"
      return route.fulfill({
        json: {
          items: [
            { id: "b1", title: "Back Again", kind: "movie", year: 2020, poster: "/p/poster" },
          ],
        },
      });
    }
    const json =
      path === "/collections"
        ? {
            items: [
              {
                key: "zombies",
                title: "Zombie night",
                name: null,
                group: "niche",
                total: 30,
                sort: "known",
                filters: { tag: ["zombies"] },
                query: { tag: "zombies" },
              },
            ],
          }
        : path === "/shelves"
          ? { continue: [], watchlist: [], recent: [] }
          : { items: [] };
    await route.fulfill({ json });
  });
  await page.goto(base + "/watch");
  await page.getByText("Back Again").first().waitFor({ timeout: 15000 });
  assert(
    Object.values(tries).some((n) => n >= 3),
    "it was tried again on its own",
  );
  await page.waitForTimeout(500);
  assert.equal(await page.getByText("Failed to fetch").count(), 0, "no error left on screen");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS a shelf whose connection dropped fills in by itself");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

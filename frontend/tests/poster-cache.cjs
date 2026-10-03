const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
// A poster already in the browser cache still shows: it used to load before the component's
// "new source" reset ran, and stayed invisible (opacity 0) in the title card and some rows.
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const png = fs.readFileSync(__dirname + "/../public/art/tv-bezel.png");
  const film = {
    id: "film",
    title: "Cached Poster",
    kind: "movie",
    year: 2020,
    poster: "/api/v1/cinema/titles/film/poster",
  };
  await page.route(/\/api\/v1\/cinema\//, (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1/cinema", "");
    if (path.endsWith("/poster"))
      return route.fulfill({
        body: png,
        contentType: "image/png",
        headers: { "Cache-Control": "max-age=600" },
      });
    if (path === "/shelves")
      return route.fulfill({
        json: {
          continue: [],
          watchlist: [{ ...film, media_id: "film" }],
          recent: [],
          saved: [],
          sources: {},
        },
      });
    if (path === "/titles/film") return route.fulfill({ json: film });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto(base + "/watch");
  const card = page.getByRole("list", { name: "Your picks" }).getByText("Cached Poster");
  for (let round = 0; round < 2; round++) {
    await card.click();
    const poster = page.locator(".watch-title__poster img");
    await poster.waitFor();
    await page.waitForFunction(
      () => document.querySelector(".watch-title__poster img")?.hasAttribute("data-loaded"),
      null,
      { timeout: 5000 },
    );
    await page.keyboard.press("Escape");
    await poster.waitFor({ state: "detached" });
  }
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS a cached poster shows in the title card, first and second time");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
// Listen: an empty queue offers starts (the house's songs, stations, add a song, Nox), and a
// search shows 15 results that scroll, with more on request. The API is mocked; nothing plays.
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const puts = [],
    searches = [];
  await page.route(/\/api\/v1\/music$/, (route) =>
    route.fulfill({
      json: { items: [], version: 1, current_id: null, desired: "stopped", fair: true },
    }),
  );
  await page.route("**/api/v1/music/auto", (route) => {
    if (route.request().method() === "PUT") {
      puts.push(route.request().postDataJSON());
      return route.fulfill({ json: { status: "accepted" } });
    }
    return route.fulfill({ json: { mode: "off", kept: 42, genres_kept: [], can_change: true } });
  });
  await page.route("**/api/v1/music/radio/favorites", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route("**/api/v1/music/radio?**", (route) =>
    route.fulfill({
      json: {
        items: [
          // A news station is never offered as a way to start the music.
          { id: "d1234560-1234-1234-1234-123456789abc", name: "World News 24", tags: "news" },
          ...[1, 2, 3, 4].map((n) => ({
            id: `d123456${n}-1234-1234-1234-123456789abc`,
            name: "Fixture Station " + n,
            country: "FR",
            tags: "jazz,chill",
          })),
        ],
      },
    }),
  );
  await page.route("**/api/v1/music/search?**", (route) => {
    const url = new URL(route.request().url());
    const limit = Number(url.searchParams.get("limit"));
    searches.push(limit);
    return route.fulfill({
      json: {
        status: "completed",
        items: Array.from({ length: limit }, (_, i) => ({
          id: "c" + i,
          title: "Fixture song " + i,
          uploader: "Band",
          duration: 200,
          source_url: "https://www.youtube.com/watch?v=fixture" + i,
        })),
      },
    });
  });
  await page.route("**/api/v1/music/quick-songs", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            source_url: "https://www.youtube.com/watch?v=hothothotxx",
            title: "Hot song",
            why: "lately",
          },
          {
            source_url: "https://www.youtube.com/watch?v=missedmisse",
            title: "Old love",
            why: "missed",
          },
        ],
      },
    }),
  );
  await page.goto(base + "/listen");
  const starts = page.getByLabel("Start the music");
  await starts.getByRole("button", { name: /Hot song.*played a lot lately/ }).waitFor();
  await starts.getByRole("button", { name: /Old love.*not heard for a while/ }).waitFor();
  assert.equal(await starts.getByRole("button", { name: /World News/ }).count(), 0);
  await starts.getByRole("button", { name: /Play the house's songs/ }).waitFor();
  // Two stations (music only), next to the song picks and auto play.
  assert.equal(await starts.getByRole("button", { name: /Fixture Station/ }).count(), 2);
  await starts.getByRole("button", { name: /Play the house's songs/ }).click();
  await until(() => puts.length);
  assert.deepEqual(puts[0], { mode: "library", genres: [], stations: [] });
  await page.screenshot({ path: "evidence/latest/listen-starts.png" });
  // The add field sits beside the queue (no "Add a song" row needed); results take the ideas' place.
  await page.getByLabel("Search music", { exact: true }).fill("fixture");
  await page.keyboard.press("Enter");
  const results = page.getByRole("list", { name: "Search results" });
  await results.getByText("Fixture song 14").waitFor();
  assert.equal(await results.getByRole("listitem").filter({ hasText: "Fixture song" }).count(), 15);
  assert(
    await results.evaluate((el) => getComputedStyle(el).overflowY === "auto"),
    "results scroll",
  );
  assert.equal(await page.getByLabel("Start the music").count(), 0, "results replace the ideas");
  await page.screenshot({ path: "evidence/latest/listen-results.png" });
  await results.getByRole("button", { name: "More results" }).click();
  await results.getByText("Fixture song 29").waitFor();
  assert.deepEqual(searches, [15, 30]);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS empty queue starts, visible add bar, 15 results that scroll in the ideas' place, more on request",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

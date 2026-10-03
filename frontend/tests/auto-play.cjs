const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
// Auto play: pick kept genres, whose songs and how recent, or a radio rotation; the API is
// mocked, nothing plays.
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const puts = [];
  const station = { id: "d1234567-1234-1234-1234-123456789abc", name: "Fixture Jazz" };
  await page.route("**/api/v1/music/auto", (route) => {
    if (route.request().method() === "PUT") {
      puts.push(route.request().postDataJSON());
      return route.fulfill({ json: { status: "accepted", started: true } });
    }
    return route.fulfill({
      json: {
        mode: "off",
        kept: 12,
        genres_kept: [
          { genre: "Rock", count: 8 },
          { genre: "Jazz", count: 4 },
        ],
        people_kept: [
          { id: "p-ada", name: "Ada", count: 9 },
          { id: "p-sam", name: "Sam", count: 3 },
        ],
        can_change: true,
      },
    });
  });
  await page.route("**/api/v1/music/radio/favorites", (route) =>
    route.fulfill({ json: { items: [{ favorite_id: "f1", ...station }] } }),
  );
  const found = { id: "e1234567-1234-1234-1234-123456789abc", name: "Fixture Rock" };
  await page.route("**/api/v1/music/radio?**", (route) =>
    route.fulfill({ json: { items: [found] } }),
  );
  await page.goto(base + "/music");
  const place = async (name) => {
    await page
      .getByRole("navigation", { name: "Listen" })
      .getByRole("button", { name, exact: true })
      .click();
    return page.getByRole("region", { name, exact: true });
  };
  // Auto play is one of Listen's own places now (it was a sheet).
  const sheet = await place("Auto play");
  await sheet.locator("label", { hasText: "Kept songs" }).click();
  await sheet.getByRole("button", { name: /^Jazz/ }).click();
  // Only Sam's songs, from this month.
  await sheet.getByRole("button", { name: /^Sam/ }).click();
  await sheet.locator("label", { hasText: "This month" }).click();
  await sheet.screenshot({ path: "evidence/latest/auto-play-library.png" });
  await sheet.getByRole("button", { name: "Start auto play" }).click();
  await until(() => puts.length >= 1);
  assert.deepEqual(puts[0], {
    mode: "library",
    genres: ["Jazz"],
    people: ["p-sam"],
    days: 30,
    stations: [],
  });
  await sheet.locator("label", { hasText: "Radio rotation" }).click();
  await sheet.getByRole("button", { name: "Add", exact: true }).click();
  await sheet.getByLabel("Find a station").fill("rock");
  await sheet.getByRole("button", { name: "Search", exact: true }).click();
  await sheet.getByText("Fixture Rock").waitFor();
  await sheet.getByRole("button", { name: "Add", exact: true }).click();
  await sheet.getByLabel("How long · Fixture Jazz").fill("2");
  await sheet.screenshot({ path: "evidence/latest/auto-play-radio.png" });
  await sheet.getByRole("button", { name: "Start auto play" }).click();
  await until(() => puts.length >= 2);
  assert.equal(puts[1].mode, "radio");
  assert.deepEqual(puts[1].stations, [
    { ...station, songs: 2, minutes: null },
    { ...found, songs: 3, minutes: null },
  ]);
  await page.screenshot({ path: "evidence/latest/auto-play.png" });
  await browser.close();
  console.log("auto play: genres, people, time window and radio rotation saved");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

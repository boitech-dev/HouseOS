const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
// Filing songs under a genre by hand in My music → On this house: one song (and its artist's
// other songs), then several selected at once. The API is mocked; nothing is changed.
(async () => {
  const browser = await chromium.launch({ headless: true });
  const shots = [];
  for (const [width, height] of [
    [390, 844],
    [1440, 900],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } });
    const base = "http://127.0.0.1:8893";
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    const errors = [],
      puts = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const song = (n, genre) => ({
      id: "s" + n,
      title: "Song " + n,
      artist: n < 3 ? "Yung Beef" : "SCH",
      genre,
      source_url: "https://www.youtube.com/watch?v=genre" + String(n).padStart(6, "0"),
    });
    const songs = [song(1, "other"), song(2, "rap / hip-hop"), song(3, "other")];
    await page.route(/\/api\/v1\/files\/library\?/, (route) =>
      route.fulfill({
        json: {
          items: songs,
          total: songs.length,
          facets: { genres: [{ genre: "other", count: 2 }], types: {}, people: {} },
          next_offset: null,
        },
      }),
    );
    await page.route(/\/api\/v1\/music\/genre/, (route) => {
      if (route.request().method() === "PUT") {
        puts.push(route.request().postDataJSON());
        return route.fulfill({ json: { status: "completed", songs: 2 } });
      }
      return route.fulfill({
        json: {
          choices: ["anime", "rap / hip-hop", "latin", "pop"],
          same_artist: 1,
          artists: ["yung beef"],
        },
      });
    });
    await page.goto(base + "/listen?tab=library");
    await page.getByText("On this house", { exact: true }).click();
    await page.getByText("Song 1", { exact: true }).waitFor();
    // One song: its "+ Genre" opens the sheet; every genre is a button; its artist can follow.
    await page.getByRole("button", { name: "+ Genre" }).first().click();
    const sheet = page.getByRole("dialog", { name: "Song 1" });
    await sheet.getByRole("button", { name: "Rap / hip-hop" }).click();
    await sheet.getByLabel("Also the other song by this artist").check();
    await sheet.screenshot({ path: `evidence/latest/genre-sheet-${width}.png` });
    await sheet.getByRole("button", { name: "Save" }).click();
    await until(() => puts.length >= 1);
    assert.deepEqual(puts[0], {
      source_urls: [songs[0].source_url],
      genre: "rap / hip-hop",
      same_artist: true,
    });
    // Several at once.
    await page.getByRole("button", { name: "Select songs" }).click();
    await page.getByRole("checkbox", { name: "Song 1" }).check();
    await page.getByRole("checkbox", { name: "Song 3" }).check();
    await page.getByRole("button", { name: "Set the genre of 2 songs" }).click();
    const many = page.getByRole("dialog", { name: "Genre of 2 songs" });
    await many.getByRole("button", { name: "Latin" }).click();
    await many.getByRole("button", { name: "Save" }).click();
    await until(() => puts.length >= 2);
    assert.deepEqual(puts[1].source_urls, [songs[0].source_url, songs[2].source_url]);
    assert.equal(puts[1].genre, "latin");
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: `evidence/latest/genre-list-${width}.png` });
    shots.push(width);
    assert.deepEqual(errors, []);
    await context.close();
  }
  await browser.close();
  console.log(
    "PASS songs filed under a genre by hand, one with its artist and several at once (mocked)",
    shots,
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

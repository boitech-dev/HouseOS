// Games (D33): the room shows the house's games, a game opens its sheet with Play here, Watch
// swaps to Games, and on a phone the dock's More opens the other rooms (Games first). Real
// isolated login; the games reads are intercepted, so nothing is uploaded, fetched or played.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    base = "http://127.0.0.1:8893",
    errors = [];
  const game = {
    id: "g1", title: "Moonlit Keep", system: "snes", system_name: "Super Nintendo", year: 1994,
    genre: "Action RPG", players: 1, versions: 1, art: {}, here: true, tv: false, state: "ready",
  }; // prettier-ignore
  const detail = {
    ...game, version: 1, tags: ["Europe"], versions: [{ id: "g1", region: "Europe", tags: [] }],
    saves: { sram: null, states: [] }, can_change: true, player: { core: "snes9x", file: "/x" },
  }; // prettier-ignore
  const intercept = (page) =>
    page.route(/\/api\/v1\/games(\/.*)?(\?.*)?$/, (route) => {
      const path = new URL(route.request().url()).pathname.slice("/api/v1/games".length);
      const json =
        path === "/shelves"
          ? { total: 1, rows: [{ id: "recent", items: [game], count: 1 }], systems: { snes: { name: "Super Nintendo" } } }
          : path === "/tv"
            ? { ready: false, native: true }
            : path === "/g1"
              ? detail
              : { items: [game], total: 1, next_offset: null, facets: {} };
      return route.fulfill({ json });
    }); // prettier-ignore
  const desk = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await require("./session.cjs")(desk, base);
  let page = await desk.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await intercept(page);
  await page.goto(base + "/watch");
  await page.getByRole("button", { name: "Games" }).click();
  await page.waitForURL(/\/games$/);
  // A small library is one grid; the game opens its sheet, where it plays here.
  await page.getByRole("button", { name: /Moonlit Keep/ }).click();
  await page.getByRole("button", { name: "Play here" }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Play on the TV" }).count(), 0);
  // The rail lists Games above House.
  const rail = await page.locator(".shell__rail li").allInnerTexts();
  assert(rail.findIndex((x) => x.includes("Games")) < rail.findIndex((x) => x.includes("House")));
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await require("./session.cjs")(phone, base);
  page = await phone.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await intercept(page);
  await page.goto(base + "/games");
  await page.getByRole("button", { name: /Moonlit Keep/ }).waitFor();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.getByRole("navigation", { name: "Mobile navigation" }).getByRole("button", { name: /^More/ }).click();
  await page.getByRole("list", { name: "Rooms" }).getByText("Games").waitFor();
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS Watch → Games, a game's sheet, Games above House, the phone's More");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

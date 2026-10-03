// Song history keeps loading as you scroll (a cursor, so new plays never repeat rows).
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    asked = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const row = (n) => ({
    id: "h" + n,
    source_url: "https://soundcloud.com/fixture/song-" + n,
    title: "Song " + n,
    played_at: "2026-09-24T20:00:00Z",
    requester: { id: "p", name: "Camille", avatar: "crest" },
    plays: 1,
  });
  await page.route("**/api/v1/music/history*", (route) => {
    const url = new URL(route.request().url());
    asked.push(url.search);
    const second = url.searchParams.get("before") === "cursor-1";
    const start = second ? 30 : 0;
    return route.fulfill({
      json: {
        items: Array.from({ length: 30 }, (_, i) => row(start + i)),
        next_before: second ? null : "cursor-1",
      },
    });
  });
  await page.goto(base + "/listen");
  await page
    .getByRole("navigation", { name: "Listen" })
    .getByRole("button", { name: "History" })
    .click();
  const sheet = page.getByRole("region", { name: "History", exact: true });
  await sheet.getByText("Song 29", { exact: true }).scrollIntoViewIfNeeded();
  await sheet.getByText("Song 59", { exact: true }).waitFor({ timeout: 5000 });
  assert.equal(
    await sheet.getByText("Song 0", { exact: true }).count(),
    1,
    "rows kept, not swapped",
  );
  assert(asked.some((q) => q.includes("before=cursor-1")));
  assert.equal(await sheet.getByRole("button", { name: "Show more" }).count(), 0, "end reached");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS history grows while scrolling, keeps earlier rows, stops at the end");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

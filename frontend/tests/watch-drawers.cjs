// Watch drawers and the movie Player: downloads (progress, cancel), queue clear, history,
// the library upload control, and the movie sleep timer in the Player.
// Real isolated login; Cinema is intercepted, so nothing plays or downloads.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let download = {
    id: "dl",
    media_id: "film",
    title: "Fixture local movie",
    kind: "save_local",
    state: "preparing",
    version: 2,
    download: { bytes: 536870912, total: 1073741824, phase: "downloading" },
  };
  let queued = [{ queue_id: "q1", id: "film", title: "Queued fixture" }],
    sleep = null;
  await page.route(/\/api\/v1\/cinema\//, async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace("/api/v1/cinema", "");
    if (request.method() !== "GET") {
      const body = request.postDataJSON();
      writes.push({ path, body });
      if (path === "/workflows/dl/cancel")
        download = { ...download, state: "cancelled", version: 3 };
      if (path === "/queue/clear") queued = [];
      if (path === "/workflows/movie/sleep")
        sleep = { state: "scheduled", at: "2026-09-23T23:00:00" };
      return route.fulfill({ json: { status: "completed", version: 8, sleep_timer: sleep } });
    }
    const json =
      path === "/downloads"
        ? { items: [download] }
        : path === "/queue"
          ? { items: queued, total: queued.length, revision: 4 }
          : path === "/state"
            ? {
                items: [
                  {
                    media_id: "film",
                    title: "Seen fixture",
                    watched: true,
                    last_watched_at: "2026-09-22T20:00:00",
                  },
                ],
                next_offset: null,
              }
            : path === "/catalogs"
              ? { items: [{ id: "top", name: "Popular", genres: ["Animation", "Drama"] }] }
              : path === "/current"
                ? {
                    current: {
                      id: "movie",
                      title: "Fixture on the TV",
                      version: 7,
                      state: "playing_observed",
                      checkpoint: { position: 600 },
                      duration: 6000,
                      can_seek: true,
                    },
                  }
                : path === "/workflows/movie/sleep"
                  ? { timer: sleep, power_off_available: false }
                  : { items: [] };
    await route.fulfill({ json });
  });
  await page.goto(base + "/watch");
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await page.getByRole("button", { name: /^Copies at home/ }).click();
  const downloads = page.getByRole("dialog", { name: "Copies at home" });
  await downloads.getByRole("progressbar", { name: "Download progress" }).waitFor();
  assert(await downloads.getByText(/50%/).isVisible());
  assert.equal(await downloads.locator(".cinema-upload input[type=file]").count(), 1);
  await downloads.getByRole("button", { name: "Cancel download" }).click();
  await downloads.getByText("Download cancelled", { exact: true }).waitFor();
  assert.deepEqual(writes.find((w) => w.path === "/workflows/dl/cancel").body, { version: 2 });
  await downloads.getByRole("button", { name: "Close" }).last().click();

  await page.getByRole("button", { name: "My queue", exact: true }).click();
  const queue = page.getByRole("dialog", { name: "My queue" });
  await queue.getByText("Queued fixture").waitFor();
  await queue.getByRole("button", { name: "Clear my queue" }).click();
  await queue.getByRole("button", { name: "Confirm clear queue" }).click();
  await queue.getByText("Nothing queued.", { exact: false }).waitFor();
  assert.equal(writes.find((w) => w.path === "/queue/clear").body.revision, 4);
  await queue.getByRole("button", { name: "Close" }).last().click();

  await page.getByRole("button", { name: "History", exact: true }).click();
  const history = page.getByRole("dialog", { name: "History" });
  await history.getByText("Seen fixture").waitFor();
  await Promise.all([
    page.waitForRequest((r) => r.url().includes("/state/film/history")),
    history.getByRole("button", { name: "Forget · Seen fixture" }).click(),
  ]);
  assert(writes.some((w) => w.path === "/state/film/history"));
  await history.getByRole("button", { name: "Close" }).last().click();

  // While a film plays, the Now bar (not a tile of Watch's own) opens the Now sheet.
  await page.locator(".shell__now").getByText("Fixture on the TV").waitFor();
  assert.equal(await page.getByRole("button", { name: /^On the TV/ }).count(), 0);
  await page.locator(".shell__now-open").click();
  await page
    .getByRole("dialog", { name: "Now playing" })
    .getByRole("button", { name: "Close" })
    .click();

  // The film on the TV lives in the Player, with its sleep timer.
  await page.goto(base + "/house");
  await page.locator(".shell__now").getByText("Fixture on the TV").waitFor();
  await page.locator(".shell__now-open").click();
  const now = page.getByRole("dialog", { name: "Now playing" });
  await now.getByText("Movie sleep timer").click();
  await now.getByRole("button", { name: "Set sleep timer" }).click();
  assert.equal(writes.find((w) => w.path === "/workflows/movie/sleep").body.minutes, 60);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS downloads cancel, queue clear, history forget, upload control, movie sleep");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

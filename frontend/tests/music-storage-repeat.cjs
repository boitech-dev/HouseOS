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
  let repeat = "off";
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/\/api\/v1\/music(?:\/|\?|$)/, async (route) => {
    const path = new URL(route.request().url()).pathname.slice("/api/v1/music".length);
    let data = { items: [] };
    if (route.request().method() !== "GET") {
      const body = route.request().postDataJSON();
      writes.push(body);
      if (path === "/control" && body.action === "repeat") repeat = body.value;
      data = { status: "accepted" };
    } else if (!path)
      data = {
        version: 1,
        current_id: "loading",
        repeat_mode: repeat,
        volume: 25,
        items: [
          {
            id: "loading",
            title: "Getting your song ready",
            status: "buffering",
            download_state: "downloading",
            duration: 180,
            source_url: "https://www.youtube.com/watch?v=fixture0000",
          },
          {
            id: "failed",
            title: "Fixture exact recording",
            requester: { name: "Mira", avatar: "ghost" },
            source_url: "https://www.youtube.com/watch?v=fixture0001",
            status: "failed",
            error_code: "YOUTUBE_SIGN_IN_REQUIRED",
          },
        ],
        observation: { status: "observed", idle: true, paused: true },
      };
    else if (path === "/storage")
      data = {
        disk: {
          total_bytes: 100 * 1024 ** 3,
          used_bytes: 40 * 1024 ** 3,
          free_bytes: 60 * 1024 ** 3,
        },
        categories: {
          music: 1024 ** 3,
          movies: 20 * 1024 ** 3,
          files: 5 * 1024 ** 3,
          other: 14 * 1024 ** 3,
        },
      };
    else if (path === "/current/favorite")
      data = { item_id: "loading", supported: true, favorite: false };
    await route.fulfill({ json: data });
  });
  await page.route("**/api/v1/cinema/current", (route) =>
    route.fulfill({ json: { current: null } }),
  );
  await page.goto(base + "/");
  await page.getByText("Downloading audio…", { exact: true }).waitFor();
  await page.locator(".ds-row .listen-who").filter({ hasText: "Mira" }).waitFor();
  // The disk is in the house's numbers (House → Numbers, linked from Home).
  await page.goto(base + "/house?tab=numbers");
  await page.getByRole("heading", { name: "House storage", exact: true }).waitFor();
  await page.getByText("60 GB free", { exact: true }).waitFor();
  await page
    .getByRole("region", { name: "House storage", exact: true })
    .screenshot({ path: "evidence/latest/music-storage-dashboard-phone.png" });
  await page.goto(base + "/listen");
  await page.getByRole("button", { name: "More music", exact: true }).click();
  await page.getByRole("menuitem", { name: "Jukebox settings", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Jukebox settings" });
  // Repeat is one choice of three (off, song, queue).
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/music/control")),
    sheet.locator("label", { hasText: "Repeat song" }).click(),
  ]);
  assert.deepEqual(writes[0].action, "repeat");
  assert.deepEqual(writes[0].value, "one");
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/music/control")),
    sheet.locator("label", { hasText: "Repeat queue" }).click(),
  ]);
  assert.deepEqual(writes[1].value, "queue");
  await sheet.getByRole("button", { name: "Close" }).last().click();
  await page
    .getByRole("button", { name: "Find this song on SoundCloud", exact: true })
    .first()
    .click();
  await page.getByLabel("Search music", { exact: true }).waitFor();
  assert.equal(
    await page.getByLabel("Search music", { exact: true }).inputValue(),
    "Fixture exact recording",
  );
  assert.equal(await page.getByLabel("Music source", { exact: true }).inputValue(), "soundcloud");
  assert(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "Phone horizontal overflow",
  );
  assert.deepEqual(errors, []);
  await page.screenshot({ path: "evidence/latest/music-storage-repeat-phone.png", fullPage: true });
  await browser.close();
  console.log(
    "PASS phone storage/loading/repeat/SoundCloud fallback (mocked controls, no playback)",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

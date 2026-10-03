// Real isolated login + rendered UI, mocked device writes; never play test songs.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    writes = [],
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/\/api\/v1\/music(?:\/|\?|$)/, async (route) => {
    const path = new URL(route.request().url()).pathname.slice("/api/v1/music".length);
    let data = { items: [] };
    if (route.request().method() !== "GET") {
      writes.push({ path, body: route.request().postDataJSON() });
      data = { status: "accepted" };
    } else if (!path)
      data = {
        version: 3,
        autoplay_on_add: true,
        current_id: "old",
        desired: "paused",
        volume: 36,
        sleep_at: new Date(Date.now() + 300 * 60000).toISOString(),
        items: [
          {
            id: "old",
            title: "Previously paused song",
            status: "paused",
            position: 1,
            metadata: {},
            source_url: "https://soundcloud.com/example/track",
          },
        ],
        observation: { status: "observed", idle: false, paused: true },
      };
    else if (path === "/current/favorite")
      data = { supported: true, item_id: "old", favorite: false };
    else if (path === "/saved") data = [];
    await route.fulfill({ json: data });
  });
  await page.goto(base + "/music");
  await page.locator(".listen-deck").getByText("Previously paused song", { exact: true }).waitFor();
  await page.getByLabel("Search music", { exact: true }).fill("https://soundcloud.com/a/b");
  assert.equal((await page.locator(".listen-add__field button").textContent()).trim(), "Play");
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/music/control")),
    page.locator(".listen-deck").getByRole("button", { name: "Next track", exact: true }).click(),
  ]);
  assert(writes.some((x) => x.body.action === "skip"));
  await page.getByRole("button", { name: "More music", exact: true }).click();
  await page.getByRole("menuitem", { name: "Jukebox settings", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Jukebox settings" });
  await sheet.getByText("Music stops at", { exact: false }).waitFor();
  const timer = sheet.getByRole("combobox", { name: "Sleep timer" });
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/music/control")),
    timer.selectOption("300"),
  ]);
  assert(
    writes.some((x) => x.path === "/control" && x.body.action === "sleep" && x.body.value === 300),
  );
  await timer.selectOption("custom");
  await sheet.getByRole("spinbutton", { name: "Custom sleep minutes" }).fill("205");
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/music/control")),
    sheet.getByRole("button", { name: "Apply" }).click(),
  ]);
  assert(writes.some((x) => x.body.action === "sleep" && x.body.value === 205));
  await sheet.getByRole("button", { name: "Close" }).last().click();
  assert(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "music controls overflow phone",
  );
  let savedSettings = null;
  await page.route("**/api/v1/admin/house-settings", async (route) => {
    if (route.request().method() === "PUT") savedSettings = route.request().postDataJSON();
    await route.fulfill({
      json: {
        name: "Test house",
        timezone: "Europe/Paris",
        language: "fr",
        motion: "still",
        quiet_start: "23:00",
        quiet_end: "08:00",
        music_volume_cap: 70,
        music_round_robin: false,
        music_sleep_minutes: 300,
        file_quota_bytes: 20 * 1024 ** 3,
        max_upload_bytes: 5 * 1024 ** 3,
      },
    });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(base + "/admin");
  await page.getByRole("heading", { name: "Control Room", exact: true }).waitFor();
  await page.getByRole("button", { name: /^house$/i }).click();
  await page.locator("input[name=music_round_robin]").check();
  const settingsForm = page
    .locator("form")
    .filter({ has: page.locator("input[name=music_round_robin]") });
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/admin/house-settings") && r.request().method() === "PUT",
    ),
    settingsForm.getByRole("button", { name: "Save", exact: true }).click(),
  ]);
  assert.equal(savedSettings.music_round_robin, true);
  assert.equal(savedSettings.music_sleep_minutes, 300);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS paused Play label, 5h/custom sleep, skip, admin fair queue toggle, phone layout; writes mocked",
  );
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

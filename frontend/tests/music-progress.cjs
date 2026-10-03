const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict"),
  { until } = require("./session.cjs");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let paused = false,
    position = 20,
    cleared = false,
    writes = [];
  await page.route(/\/api\/v1\/music(?:\/|\?|$)/, async (route) => {
    const path = new URL(route.request().url()).pathname.slice("/api/v1/music".length);
    let data = { items: [] };
    if (route.request().method() !== "GET") {
      const body = route.request().postDataJSON();
      writes.push({ path, body });
      if (body?.action === "pause") paused = true;
      if (body?.action === "play") paused = false;
      if (body?.action === "seek") position = body.value;
      if (body?.action === "clear")
        data = {
          status: "needs_confirmation",
          confirmation_id: "clear-test",
          preview: { action: "clear" },
        };
      else if (path.includes("/confirm/")) {
        cleared = true;
        data = { status: "accepted" };
      } else data = { status: "accepted" };
    } else if (!path)
      data = {
        version: 1,
        current_id: cleared ? null : "song",
        desired: paused ? "paused" : "playing",
        volume: 25,
        items: cleared
          ? []
          : [
              {
                id: "song",
                title: "Timeline fixture",
                duration: 300,
                status: paused ? "paused" : "playing",
                source_url: "https://soundcloud.com/test/song",
              },
            ],
        observation: {
          status: "observed",
          item_id: cleared ? "" : "song",
          position,
          paused,
          idle: cleared,
        },
      };
    else if (path === "/current/favorite")
      data = { item_id: "song", supported: true, favorite: false };
    else if (path === "/saved") data = [];
    await route.fulfill({ json: data });
  });
  await page.goto(base + "/music");
  const timeline = page.getByRole("slider", { name: "Playback position", exact: true });
  await page.waitForFunction(
    () => Number(document.querySelector('[aria-label="Playback position"]')?.value) >= 20,
  );
  const before = Number(await timeline.inputValue());
  await page.waitForTimeout(1300);
  assert(
    Number(await timeline.inputValue()) >= before + 0.9,
    "timeline did not advance without clicking",
  );
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/music/control")),
    page.locator(".listen-deck").getByRole("button", { name: "Pause", exact: true }).click(),
  ]);
  await page.waitForFunction(() =>
    document.querySelector('.listen-deck button[aria-label="Play"]'),
  );
  const fixed = Number(await timeline.inputValue());
  await page.waitForTimeout(1200);
  assert.equal(Number(await timeline.inputValue()), fixed, "paused timeline advanced");
  await timeline.press("End");
  await page.waitForFunction(
    () => Number(document.querySelector('[aria-label="Playback position"]')?.value) === 300,
  );
  assert(writes.some((x) => x.body?.action === "seek" && x.body.value === 300));
  await page.goto(base + "/house");
  // The bar has previous, play and next; a tap on the song opens its player (Listen), with
  // the volume (the bar shows volume where there is room: wider screens).
  const now = page.getByRole("complementary", { name: "Now playing" });
  await now.getByRole("button", { name: "Previous track", exact: true }).click();
  await until(() => writes.some((x) => x.body?.action === "previous"));
  assert(writes.some((x) => x.body?.action === "previous"));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator(".shell__now-open").click();
  await page.waitForURL(base + "/listen");
  assert(await page.getByRole("slider", { name: "Volume", exact: true }).isVisible());
  await page.goto(base + "/music");
  // Clear queue sits on the player, with a one-tap inline check.
  await page.getByRole("button", { name: "Clear queue", exact: true }).first().click();
  await page
    .getByRole("group", { name: "Clear queue" })
    .getByRole("button", { name: "Remove", exact: true })
    .click();
  await page.waitForFunction(() => !document.body.textContent.includes("Timeline fixture"));
  assert.equal(await page.getByText("Timeline fixture", { exact: true }).count(), 0);
  await browser.close();
  console.log(
    "PASS smooth observed timeline, pause/seek reset, actual previous contract, banner controls, clear current UI",
  );
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

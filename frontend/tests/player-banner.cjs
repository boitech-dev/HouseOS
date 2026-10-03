const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let movie = true;
  const writes = [],
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/cinema/current", (r) =>
    r.fulfill({
      json: {
        current: movie
          ? {
              id: "movie-one",
              title: "Fixture movie on the TV with a long descriptive title",
              version: 9,
              state: "playing_observed",
              checkpoint: { position: 60 },
              duration: 3600,
              can_seek: true,
              volume_supported: true,
              volume: 30,
            }
          : null,
      },
    }),
  );
  await page.route("**/api/v1/cinema/workflows/movie-one/control", (r) => {
    const body = r.request().postDataJSON();
    writes.push(body);
    if (body.action === "stop") movie = false;
    return r.fulfill({
      json:
        body.action === "stop"
          ? {
              state: "stopped",
              error: { message: "Application session cleared; receiver stop is unverified." },
            }
          : { state: "command_sent" },
    });
  });
  await page.route("**/api/v1/music", (r) =>
    r.fulfill({
      json: {
        version: 5,
        current_id: "song-one",
        desired: "playing",
        items: [{ id: "song-one", title: "Fixture shared song", status: "playing", duration: 180 }],
        observation: {
          status: "observed",
          item_id: "song-one",
          idle: false,
          paused: false,
          position: 20,
          volume: 30,
        },
      },
    }),
  );
  await page.route("**/api/v1/music/control", (r) => {
    writes.push(r.request().postDataJSON());
    return r.fulfill({ json: { status: "accepted" } });
  });
  await page.goto(base + "/house");
  // One Now bar for both: the film first (what you're most likely controlling), a switch for the
  // music beside it.
  const bar = page.locator(".shell__now");
  await bar.getByText("Fixture movie on the TV", { exact: false }).waitFor();
  assert.equal(await bar.count(), 1);
  assert.equal(await bar.getByRole("radio", { name: "TV" }).isChecked(), true);
  await bar.getByRole("button", { name: "Pause", exact: true }).click();
  assert.equal(writes[0].action, "pause");
  assert.equal(writes[0].version, 9);
  // Volume and stop are in the expanded player.
  await bar.locator(".shell__now-open").click();
  const sheet = page.getByRole("dialog", { name: "Now playing" });
  await sheet.waitFor();
  await page.waitForFunction(
    () => !document.querySelector('dialog input[aria-label="Movie volume"]').disabled,
  );
  await sheet.getByLabel("Movie volume").focus();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/control") && r.request().postDataJSON()?.action === "volume",
    ),
    page.keyboard.press("ArrowRight"),
  ]);
  assert(
    writes.some((w) => w.action === "volume" && w.position === 31),
    JSON.stringify(writes),
  );
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/movie-banner-phone.png", fullPage: true });
  await sheet.getByRole("button", { name: "Stop the film and save my place" }).click();
  await page.keyboard.press("Escape");
  await sheet.waitFor({ state: "hidden" });
  // Truthful stop feedback stays visible, and the bar's music side keeps working.
  await bar
    .getByText("Application session cleared; receiver stop is unverified.", { exact: true })
    .waitFor();
  if (await bar.getByRole("radio", { name: "Music" }).count())
    await bar.locator("label", { hasText: "Music" }).click();
  await bar.getByText("Fixture shared song", { exact: true }).waitFor();
  await bar.getByRole("button", { name: "Pause", exact: true }).click();
  assert(writes.some((w) => w.action === "pause" && w.expected_version === 5));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator("main").focus();
  await page.screenshot({ path: "evidence/latest/music-banner-phone.png", fullPage: true });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS one Now bar: film first, transport/volume, truthful stop feedback, music side, mobile layout",
  );
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

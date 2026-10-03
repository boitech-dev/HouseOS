// The shell's promises: on a phone the bars take at most 168px (status 48 + Now 56 + dock 64)
// with music and a film playing, and every old address still opens the right place.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const me = await (await require("./session.cjs")(context, base)).json();
  // The shell's own budget, in the plain Legacy look: most themes add a raised Nox over the dock.
  await context.request.put(base + "/api/v1/preferences", {
    headers: { Origin: base, "X-CSRF-Token": me.csrf_token },
    data: { theme: "carved-night" },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/music", (r) =>
    r.fulfill({
      json: {
        version: 5,
        current_id: "song",
        desired: "playing",
        items: [{ id: "song", title: "Clair de Lune", status: "playing", duration: 300 }],
        observation: {
          status: "observed",
          item_id: "song",
          idle: false,
          paused: false,
          position: 95,
        },
      },
    }),
  );
  await page.route("**/api/v1/cinema/current", (r) =>
    r.fulfill({
      json: {
        current: {
          id: "film",
          title: "Spirited Away",
          version: 1,
          state: "playing_observed",
          checkpoint: { position: 1800 },
          duration: 7500,
        },
      },
    }),
  );
  await page.goto(base + "/house");
  await page.locator(".shell__now").waitFor();
  const height = (selector) =>
    page.locator(selector).evaluate((el) => el.getBoundingClientRect().height);
  const chrome =
    (await height(".shell__status")) +
    (await height(".shell__now")) +
    (await height(".shell__dock"));
  assert.ok(chrome <= 168, "phone chrome " + chrome + "px");
  // Old addresses and tabs land where they always did.
  for (const [from, to] of [
    ["/music", "/listen"],
    ["/cinema", "/watch"],
    ["/settings", "/me"],
    ["/admin", "/control"],
    ["/design", "/workshop"],
    ["/workbench", "/workshop"],
    ["/house?tab=groceries", "/house"],
    ["/house?tab=tasks", "/house"],
    ["/control?tab=ai", "/control"],
    ["/inbox", "/inbox"],
    ["/space", "/space"],
    ["/capture", "/capture"],
    ["/smart-home", "/smart-home"],
    ["/listen#saved", "/listen"],
  ]) {
    await page.goto(base + from);
    await page.waitForURL((url) => url.pathname === to);
    await page.locator("#main").waitFor();
    assert.equal(await page.getByText("This page ran into a problem").count(), 0, from);
  }
  assert.deepEqual(errors, []);
  await context.request.put(base + "/api/v1/preferences", {
    headers: { Origin: base, "X-CSRF-Token": me.csrf_token },
    data: { theme: "" },
  });
  await browser.close();
  console.log("shell budget: phone chrome " + chrome + "px (≤ 168); every old address lands");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

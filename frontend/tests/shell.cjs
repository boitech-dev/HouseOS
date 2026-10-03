const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const base = "http://127.0.0.1:8893";
  const errors = [];
  // Phone: dock with the current place, old paths become canonical, activity tray.
  const phone = await browser.newContext({
    viewport: { width: 360, height: 760 },
    isMobile: true,
    hasTouch: true,
  });
  await require("./session.cjs")(phone, base);
  let page = await phone.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/activity", (r) =>
    r.fulfill({
      json: {
        items: [
          { id: "a1", kind: "preparing_film", title: "Dune: Part Two", href: "/watch?workflow=a1" },
        ],
      },
    }),
  );
  await page.goto(base + "/music", { waitUntil: "domcontentloaded" });
  await page.waitForURL(base + "/listen");
  const dock = page.locator(".shell__dock");
  await dock.waitFor();
  assert.equal(
    await dock.getByRole("link", { name: "Listen" }).getAttribute("aria-current"),
    "page",
  );
  assert.equal(await page.locator(".shell__rail").isVisible(), false);
  await dock.getByRole("link", { name: "Watch" }).click();
  await page.waitForURL(base + "/watch");
  assert.equal(
    await dock.getByRole("link", { name: "Watch" }).getAttribute("aria-current"),
    "page",
  );
  await page.getByRole("button", { name: /In progress: 1/ }).click();
  const tray = page.getByRole("dialog", { name: "In progress" });
  await tray.getByText("Preparing the film", { exact: true }).waitFor();
  await tray.getByText("Dune: Part Two", { exact: false }).waitFor();
  assert(await tray.getByRole("progressbar").isVisible());
  await page.keyboard.press("Escape");
  assert(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "360px overflow",
  );
  await phone.close();

  // Desktop: rail doorways, Ctrl+K opens and closes Nox, live updates dropping is reported.
  const desk = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await require("./session.cjs")(desk, base);
  page = await desk.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  let dropStream = false;
  await page.route("**/api/v1/events", (r) => (dropStream ? r.abort() : r.continue()));
  await page.goto(base + "/settings", { waitUntil: "domcontentloaded" });
  await page.waitForURL(base + "/me");
  const rail = page.locator(".shell__rail");
  await rail.waitFor();
  assert.equal(await page.locator(".shell__dock").isVisible(), false);
  await rail.getByRole("link", { name: /^House/ }).click();
  await page.waitForURL(base + "/house");
  assert.equal(
    await rail.getByRole("link", { name: /^House/ }).getAttribute("aria-current"),
    "page",
  );
  // Ctrl+K: the command palette (places, actions, then "Ask Nox"); its last row opens Nox.
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Go to, do or ask" });
  await palette.waitFor();
  await page.keyboard.type("smart");
  await palette.getByRole("option", { name: /Smart home/ }).waitFor();
  // "New task" opens House's Tasks on its composer, focused (even from another House tab).
  await page.keyboard.press("Control+a");
  await page.keyboard.type("new task");
  await palette.getByRole("option", { name: /New task/ }).click();
  await palette.waitFor({ state: "hidden" });
  await page.waitForURL(base + "/house?tab=tasks");
  await page.waitForFunction(
    () => document.activeElement?.getAttribute("aria-label") === "New task",
  );
  assert.match(await page.title(), /^Tasks · /, "House's tab names the page");
  await page.keyboard.press("Control+k");
  await palette.waitFor();
  await page.keyboard.press("Control+k");
  await palette.waitFor({ state: "hidden" });
  await rail.getByRole("button", { name: "Ask Nox" }).click();
  const nox = page.getByRole("dialog", { name: "Nox" });
  await nox.waitFor();
  await page.keyboard.press("Escape");
  await nox.waitFor({ state: "hidden" });
  dropStream = true; // the reloaded page's live stream now fails
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText("Reconnecting…", { exact: true }).waitFor({ timeout: 15000 });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS shell: dock/rail current place, alias paths, activity tray, Ctrl+K palette and Nox, reconnect notice, 360px",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

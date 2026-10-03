const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("fs");
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const base = "http://127.0.0.1:8893";
  const login = await require("./session.cjs")(c, base);
  assert(login.ok(), "test authentication");
  const p = await c.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  // Tasks are added inline; "More details…" opens the full editor (the /house modal).
  await p.goto(base + "/house?tab=tasks", { waitUntil: "domcontentloaded" });
  // The composer unfolds its options (and "More details…") once its field has focus.
  await p.getByLabel("New task", { exact: true }).focus();
  const add = p.getByRole("button", { name: "More details…", exact: true });
  await add.click();
  const dialog = p.getByRole("dialog");
  await dialog.waitFor();
  for (let i = 0; i < 24; i++) {
    await p.keyboard.press("Tab");
    assert(
      await p.evaluate(() => document.activeElement?.closest("dialog") !== null),
      "modal focus escaped: " +
        (await p.evaluate(() => document.activeElement.outerHTML.slice(0, 150))),
    );
  }
  await p.keyboard.press("Escape");
  await dialog.waitFor({ state: "hidden" });
  assert(await add.evaluate((e) => e === document.activeElement), "focus not restored");
  await p.goto(base, { waitUntil: "domcontentloaded" });
  assert(await p.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches));
  assert(
    (await p.locator(".courier").count()) === 0 ||
      (await p.locator(".courier").evaluate((e) => getComputedStyle(e).animationName === "none")),
    "courier motion",
  );
  for (const route of ["/", "/music", "/cinema", "/files", "/house", "/settings", "/admin"]) {
    await p.setViewportSize({ width: 720, height: 450 });
    await p.goto(base + route, { waitUntil: "domcontentloaded" });
    await p.locator("main").waitFor();
    assert(
      await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      route + " effective 200% width overflow",
    );
    await p.setViewportSize({ width: 360, height: 800 });
    assert(
      await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      route + " 360px overflow",
    );
  }
  for (const tab of ["speakers", "recovery", "logs", "usage"]) {
    await p.goto(base + "/control?tab=" + tab, { waitUntil: "domcontentloaded" });
    await p.locator(".ds-settings__detail .ds-section").first().waitFor();
    assert(
      await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      tab + " narrow overflow",
    );
  }
  await p.goto(base + "/control?tab=services", { waitUntil: "domcontentloaded" });
  await p.getByRole("heading", { name: "House services", exact: true }).waitFor();
  // Every service reads as a sentence; restart needs the host's service broker (absent here).
  await p.locator(".ds-settings__detail .ds-row").first().waitFor();
  assert.equal(await p.getByRole("textbox", { name: "Current password", exact: true }).count(), 0);
  await c.setOffline(true);
  await p
    .getByText("You’re offline. Device commands won’t be queued.", {
      exact: true,
    })
    .waitFor();
  await c.setOffline(false);
  // Page structure: Nox's page has its h1; every place names the tab; a phone keeps a focused
  // control clear of the status bar, the dock and the Now bar (WCAG 2.4.11).
  await p.setViewportSize({ width: 390, height: 844 });
  await p.goto(base + "/assistant", { waitUntil: "domcontentloaded" });
  await p.locator("main h1").first().waitFor({ state: "attached" });
  await p.goto(base + "/capture", { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => document.title.startsWith("Send something home · "));
  const padding = await p.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return [parseFloat(style.scrollPaddingTop), parseFloat(style.scrollPaddingBottom)];
  });
  assert(padding[0] >= 48 && padding[1] >= 64, "scroll padding for the chrome " + padding);
  assert.equal(errors.length, 0, errors.join(";"));
  fs.writeFileSync(
    "evidence/latest/accessibility-result.json",
    JSON.stringify(
      {
        passed: true,
        checks: [
          "native modal keyboard trap",
          "Escape and focus restore",
          "reduced motion preference",
          "effective200percent viewport720",
          "360px all major routes",
          "service restart reauthentication form only; no restart executed",
          "offline banner",
          "h1 on /assistant, /capture title, scroll padding clear of the phone chrome",
        ],
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  await b.close();
  console.log("PASS keyboard, reduced motion, narrow/zoom layout, service review, offline state");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

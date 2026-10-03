// The design system by keyboard and for screen readers: the Workbench's menu, command palette,
// segmented choice, switch, chips and settings layout, and axe on every piece in two themes.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const axe = require.resolve("axe-core/axe.min.js");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  // bypassCSP: only so axe can be injected (the app itself allows no inline script).
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    reducedMotion: "reduce",
    bypassCSP: true,
  });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/workshop?tab=pieces");
  await page.getByRole("heading", { name: "Workbench", exact: true }).waitFor();
  const focused = () =>
    page.evaluate(
      () =>
        document.activeElement?.textContent?.trim() ||
        document.activeElement?.getAttribute("aria-label"),
    );

  // Menu: opens on the first item, arrows move, Escape closes and returns focus.
  const menu = page.locator('[aria-haspopup="menu"]').first();
  await menu.focus();
  await page.keyboard.press("Enter");
  assert.equal(await focused(), "Rename");
  await page.keyboard.press("ArrowDown");
  assert.equal(await focused(), "Delete");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator('[role="menu"]').count(), 0);
  assert.equal(await menu.evaluate((el) => el === document.activeElement), true);

  // Command palette: type, Enter runs the first match (here it says so in a toast).
  await page.getByRole("button", { name: "Command palette" }).click();
  await page.keyboard.type("wat");
  await page.keyboard.press("Enter");
  await page.locator(".ds-toast", { hasText: "Watch" }).waitFor();

  // Segmented: a radio group, arrows choose.
  await page.getByRole("radio", { name: "Films" }).first().focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.getByRole("radio", { name: "Series" }).first().isChecked(), true);

  // Switch and filter chips by keyboard.
  const night = page.getByRole("switch", { name: /Night mode/ });
  await night.focus();
  await page.keyboard.press("Space");
  assert.equal(await night.isChecked(), false);
  const comedy = page.getByRole("button", { name: "Comedy" });
  await comedy.focus();
  await page.keyboard.press("Enter");
  assert.equal(await comedy.getAttribute("aria-pressed"), "true");

  // Axe on the design system's pieces, in the theme in force and in Base light.
  const audit = async (label) => {
    await page.addScriptTag({ path: axe });
    const result = await page.evaluate(() =>
      window.axe.run(document.querySelector(".ds-page"), { resultTypes: ["violations"] }),
    );
    const bad = result.violations.filter((v) => ["serious", "critical"].includes(v.impact));
    assert.deepEqual(
      bad.map(
        (v) =>
          `${v.id}: ${v.nodes
            .slice(0, 3)
            .map((n) => n.target.join(" "))
            .join(" | ")}`,
      ),
      [],
      label,
    );
  };
  await audit("carved night");
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "base";
    document.documentElement.dataset.scheme = "light";
  });
  await audit("base light");

  // Settings on a phone: the list, then one place with a way back.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Profile" }).click();
  const back = page.locator(".ds-settings__back");
  await back.waitFor();
  assert.equal(await page.locator(".ds-settings__nav").isVisible(), false);
  await back.click();
  assert.equal(await page.locator(".ds-settings__nav").isVisible(), true);

  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "workbench: keyboard walkthrough, axe clean in Carved Night and Base light, settings on a phone",
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const base = "http://127.0.0.1:8893";
  const errors = [];
  for (const viewport of [
    { width: 360, height: 780 },
    { width: 1280, height: 900 },
  ]) {
    const context = await browser.newContext({ viewport });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base + "/workshop?tab=pieces", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Workbench", exact: true }).waitFor();
    // Scenes and sprites render as images from code, never external files.
    const art = await page
      .locator(".ds-scene, .ds-sprite")
      .evaluateAll((els) => els.map((el) => el.getAttribute("src").slice(0, 10)));
    assert(
      art.length > 20 && art.every((src) => src.startsWith("data:")),
      JSON.stringify(art.slice(0, 3)),
    );
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    assert(overflow <= 0, "horizontal overflow " + overflow + "px at " + viewport.width);
    // A sheet traps focus inside and closes on Escape, returning focus to its opener.
    const opener = page.getByRole("button", { name: "Open a sheet (bottom)" });
    await opener.click();
    const sheet = page.getByRole("dialog", { name: "Change the audio" });
    await sheet.waitFor();
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press("Tab");
      assert(
        await page.evaluate(() => !!document.activeElement.closest("dialog")),
        "focus left the sheet",
      );
    }
    await page.keyboard.press("Escape");
    await sheet.waitFor({ state: "hidden" });
    assert(await opener.evaluate((el) => el === document.activeElement), "focus not restored");
    // Motion: the resident's choice, with reduced motion meaning still unless "full".
    const effective = async (motion) =>
      page.evaluate(async (m) => {
        document.documentElement.dataset.motion = m;
        await new Promise((r) => setTimeout(r, 20));
        return document.documentElement.dataset.motionEffective;
      }, motion);
    assert.equal(await effective("full"), "full");
    assert.equal(await effective("subtle"), "subtle");
    assert.equal(await effective("still"), "still");
    await context.close();
  }
  const reduced = await browser.newContext({ reducedMotion: "reduce" });
  await require("./session.cjs")(reduced, base);
  const page = await reduced.newPage();
  await page.goto(base + "/workshop?tab=pieces", { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Workbench", exact: true }).waitFor();
  const still = await page.evaluate(async () => {
    document.documentElement.dataset.motion = "subtle";
    await new Promise((r) => setTimeout(r, 20));
    const subtle = document.documentElement.dataset.motionEffective;
    document.documentElement.dataset.motion = "full";
    await new Promise((r) => setTimeout(r, 20));
    return [subtle, document.documentElement.dataset.motionEffective];
  });
  assert.deepEqual(still, ["still", "full"], "reduced motion means still unless full was chosen");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS design system: code-rendered art, no overflow at 360px, sheet focus/escape, motion levels",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

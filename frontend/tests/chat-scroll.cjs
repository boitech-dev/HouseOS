// Classic chat scrolling: a long reply opens at its first line and polls never move the view.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const base = "http://127.0.0.1:8893";
  for (const [w, h] of [
    [390, 844],
    [1280, 900],
  ]) {
    const context = await browser.newContext({ viewport: { width: w, height: h } });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    await page.goto(base + "/assistant");
    await page
      .getByRole("button", { name: /How does the house work|Comment marche la maison/ })
      .click();
    await page.locator(".ask-message[data-role=assistant]").last().waitFor({ timeout: 20000 });
    await page.waitForTimeout(2500); // a few polls: they must not move the view
    const gap = await page.evaluate(() => {
      const all = document.querySelectorAll(".ask-message");
      const last = all[all.length - 1];
      const box = last.parentElement;
      return {
        top: Math.round(last.getBoundingClientRect().top - box.getBoundingClientRect().top),
        scrollable: box.scrollHeight > box.clientHeight,
      };
    });
    console.log(w, JSON.stringify(gap));
    assert(!gap.scrollable || (gap.top >= 0 && gap.top <= 20), "reply starts at the top");
    await context.close();
  }
  await browser.close();
  console.log("PASS: a new reply opens at its first line");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

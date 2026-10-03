// One interface: Legacy is a theme in Me → Appearance (no interface switch anywhere), the
// top bar carries new messages on the avatar (no Inbox icon of its own) and Inbox in its menu.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 844 } });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base + "/me?tab=appearance");
    await page.getByText("Legacy", { exact: true }).first().waitFor();
    assert.equal(await page.getByText(/before HouseOS|New interface/).count(), 0);
    const bar = page.locator(".shell__status");
    assert.equal(await bar.getByRole("button", { name: /^Inbox/ }).count(), 0, "no Inbox icon");
    await bar.getByRole("button", { name: /^Your account/ }).click();
    await page.getByRole("link", { name: /^Inbox/ }).waitFor();
    assert.deepEqual(errors, []);
    await context.close();
  }
  await browser.close();
  console.log("PASS Legacy is a theme; messages show on the avatar and its menu");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

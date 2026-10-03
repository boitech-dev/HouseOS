// "Back to top" appears only on a long, well-scrolled page, sits above the player bars and the
// dock, and brings the page back up.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const shots = process.env.HOUSEOS_SHOTS || "";
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  for (const [width, height] of [
    [390, 844],
    [1280, 800],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    await page.goto(base + "/watch");
    await page.locator("#main").waitFor();
    await page.evaluate(() => {
      const tall = document.createElement("div");
      tall.style.height = "5000px";
      document.getElementById("main").append(tall);
    });
    assert.equal(await page.locator(".shell__totop").count(), 0, "hidden at the top");
    await page.evaluate(() => scrollTo(0, 3000));
    const button = page.getByRole("button", { name: "Back to top" });
    await button.waitFor();
    const box = await button.boundingBox();
    const dock = await page.locator(".shell__dock").boundingBox();
    const bottom = dock && dock.height ? dock.y : height;
    assert.ok(
      box.y + box.height <= bottom && box.x + box.width <= width,
      "above the dock, on screen",
    );
    if (shots) await page.screenshot({ path: `${shots}/to-top-${width}.png` });
    await button.click();
    await page.waitForFunction(() => scrollY === 0);
    await page.locator(".shell__totop").waitFor({ state: "detached" });
    await context.close();
  }
  await browser.close();
  console.log("to-top: PASS");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

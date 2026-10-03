// Nothing is wider than a phone: every room at 360 and 390 px scrolls down only, never sideways,
// Nox sits raised in the middle of the dock, and the top bar has the Control Room for an admin.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const ROOMS = [
  "/",
  "/listen",
  "/listen?tab=library",
  "/listen?tab=auto",
  "/listen?tab=radio",
  "/listen?tab=history",
  "/watch",
  "/house",
  "/house?tab=groceries",
  "/house?tab=tasks",
  "/house?tab=calendar",
  "/inbox",
  "/files",
  "/smart-home",
  "/space",
  "/me",
  "/me?tab=appearance",
  "/control",
  "/control?tab=storage",
  "/control?tab=recovery",
  "/control?tab=logs",
  "/control?tab=themes",
];
(async () => {
  const browser = await chromium.launch();
  const wide = [];
  for (const width of [360, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    await require("./session.cjs")(context, "http://127.0.0.1:8893");
    const page = await context.newPage();
    for (const room of ROOMS) {
      await page.goto("http://127.0.0.1:8893" + room, { waitUntil: "networkidle" }).catch(() => {});
      await page.waitForTimeout(400);
      const over = await page.evaluate(() => {
        const edge = document.documentElement.clientWidth;
        if (document.documentElement.scrollWidth <= edge) return null;
        // The outermost element sticking out, not inside something that scrolls sideways itself.
        const scrolls = (el) => {
          for (let p = el.parentElement; p; p = p.parentElement)
            if (["auto", "scroll", "hidden", "clip"].includes(getComputedStyle(p).overflowX)) return true;
          return false;
        };
        const out = [...document.querySelectorAll("body *")].find(
          (el) => el.getBoundingClientRect().right > edge + 1 && !scrolls(el),
        );
        return (out ? out.tagName.toLowerCase() + "." + [...out.classList].join(".") : "?") +
          " +" + (document.documentElement.scrollWidth - edge) + "px";
      });
      if (over) wide.push(`${width}px ${room}: ${over}`);
    }
    if (width === 390) {
      await page.goto("http://127.0.0.1:8893/");
      await page.locator(".shell__dock .shell__door--ask").waitFor();
      await page.getByRole("button", { name: "Control Room" }).first().click();
      await page.waitForURL(/\/control/);
      // Control Room on a phone opens on its map of every place, not a long list.
      await page.getByRole("heading", { name: "Everything in the Control Room" }).waitFor();
      assert.equal(await page.locator(".ds-settings__nav").isVisible(), false);
    }
    await context.close();
  }
  await browser.close();
  assert.deepEqual(wide, [], "wider than the phone:\n" + wide.join("\n"));
  console.log("PASS every room fits 360 and 390 px; Nox in the dock, Control Room in the top bar");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

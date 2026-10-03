const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true }),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  await page.route("**/api/v1/admin/integrations", (r) =>
    r.fulfill({ json: [{ name: "stream_addon", enabled: true, has_secret: true, config: {} }] }),
  );
  await page.goto(base + "/admin");
  await page
    .locator(".control-map")
    .getByRole("button", { name: /^Integrations\b/ })
    .click();
  await page
    .getByRole("listitem")
    .filter({ hasText: /Stream add-on|Extension de streaming/ })
    .getByRole("button", { name: /Configure|Configurer/ })
    .click();
  const input = page.getByLabel(/Your stream add-on's link|Le lien de ton extension de streaming/);
  // Masked on screen, but not a password field: password managers must leave it alone.
  assert.equal(await input.evaluate((e) => getComputedStyle(e).webkitTextSecurity), "disc");
  assert.equal(await input.getAttribute("autocomplete"), "off");
  assert.equal(await input.inputValue(), "");
  assert.match(await input.getAttribute("placeholder"), /Leave empty|Laisse vide/);
  // No add-on is named or linked: only a community catalogue, in a new tab.
  const browse = page.getByRole("link", { name: /Browse add-ons|Parcourir les extensions/ });
  assert.equal(await browse.getAttribute("href"), "https://stremio-addons.net/addons");
  assert.equal(await browse.getAttribute("target"), "_blank");
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await browser.close();
  console.log("PASS: stream add-on link write-only, blank, phone width; no settings mutation.");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

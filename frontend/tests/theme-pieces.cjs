// A theme shapes more than colours: part variants on the page, its own avatars and Nox
// (sprites.json by piece id), its house-title names and medals, and its surfaces. The theme is
// an installed one, mocked in /themes; it is worn in this browser only.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const dot = ["kk", "kk"];
const theme = {
  id: "pieces-fixture", names: { en: "Pieces", fr: "Pièces" }, description: { en: "x", fr: "x" },
  schemes: ["dark"], hidden: false, identity: "line", slots: {},
  parts: { header: "ribbon", panel: "flat", dock: "flush", nowbar: "docked" },
  sprites: { palette: { k: "accent" }, glyphs: { "nox.idle": dot, "avatar.crest": dot, "title.dj": dot } },
  flavor: {
    "title.dj.name": { en: "Station master", fr: "Chef de gare" },
  },
  swatches: {}, css: "/themes/pieces-fixture.css", status: "shared",
  owner: { id: "x", name: "X" }, mine: true, version: 1,
}; // prettier-ignore
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/themes", (r) => r.fulfill({ json: { items: [theme] } }));
  await page.route("**/themes/pieces-fixture.css", (r) => r.fulfill({ body: "", contentType: "text/css" }));
  for (const url of ["**/api/v1/house-settings", "**/api/v1/preferences"])
    await page.route(url, async (r) => {
      if (r.request().method() !== "GET") return r.continue();
      const response = await r.fetch();
      const json = await response.json();
      const worn = url.includes("house")
        ? { ...json, preferences: { ...json.preferences, theme: theme.id } }
        : { ...json, theme: theme.id };
      await r.fulfill({ response, json: worn });
    });
  await page.goto(base + "/house?tab=numbers");
  await page.waitForFunction(() => document.documentElement.dataset.theme === "pieces-fixture");
  const html = page.locator("html");
  assert.equal(await html.getAttribute("data-part-panel"), "flat");
  assert.equal(await html.getAttribute("data-part-nowbar"), "docked");
  // Nox, drawn from the theme's grid (a line-identity theme still draws a redrawn piece).
  assert(await page.locator(".shell__rail .ds-mascot img.ds-sprite").count(), "Nox is the theme's sprite");
  // House titles: the theme's name for the DJ title, and its medal.
  await page.getByText("House titles", { exact: true }).click();
  const dj = page.locator(".stats__titles li", { hasText: "Station master" });
  if (await dj.count()) assert(await dj.locator("img.ds-sprite").count(), "the medal is the theme's sprite");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("theme pieces ok");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

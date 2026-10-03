// A device's panel draws what the device reports (a colour bulb: colour, warmth, effect), and an
// admin's "Look closer" keeps or takes each control off. Home Assistant is mocked.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const bulb = {
  id: "light.desk", name: "Desk lamp", domain: "light", area: "Living room", state: "on",
  sensitive: false, attributes: { brightness_pct: 70, color: "#ff8a00", color_temp_kelvin: 3000 },
  actions: ["toggle", "turn_on", "turn_off", "brightness_pct", "color", "warmth", "effect"],
  controls: [
    { id: "brightness_pct", kind: "range", shown: true },
    { id: "color", kind: "color", shown: true },
    { id: "warmth", kind: "warmth", min: 2200, max: 6500, shown: true },
    { id: "effect", kind: "choice", options: ["colorloop", "candle"], shown: true },
  ],
}; // prettier-ignore
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [], writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/\/api\/v1\/home(\?.*)?$/, (r) =>
    r.fulfill({ json: { areas: [{ name: "Living room", entities: [bulb] }], curated: true, favorites: [] } }),
  );
  // Playwright tries the latest route first: the inspect answer goes last.
  await page.route("**/api/v1/home/light.desk/*", (r) => {
    writes.push({ url: r.request().url(), body: r.request().postDataJSON() });
    return r.fulfill({ json: { status: "completed", action: "color", entity: bulb, hidden: [] } });
  });
  await page.route("**/api/v1/home/light.desk/inspect", (r) =>
    r.fulfill({ json: { ...bulb, reported: { supported_color_modes: "['color_temp', 'hs']" } } }),
  );
  await page.goto(base + "/smart-home");
  await page.getByRole("button", { name: "Blue" }).click();
  for (let i = 0; i < 50 && !writes.length; i++) await page.waitForTimeout(100);
  assert.deepEqual(writes[0].body, { action: "color", value: "#0040ff" });
  assert(await page.getByRole("slider", { name: "Warmth" }).isVisible());
  await page.getByRole("button", { name: /Look closer/ }).click();
  const sheet = page.getByRole("dialog", { name: "What Desk lamp can do" });
  await sheet.getByText("Effect", { exact: true }).click();
  for (let i = 0; i < 50 && !writes.some((w) => w.url.endsWith("/controls")); i++)
    await page.waitForTimeout(100);
  const put = writes.find((w) => w.url.endsWith("/controls"));
  assert.deepEqual(put.body, { hidden: ["effect"] });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("colour bulb ok");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

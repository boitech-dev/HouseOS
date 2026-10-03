// Smart home rooms fill rows like a wall of cards: each row reaches the right edge, a room with
// several devices lays them side by side instead of in a tall column, and room headers line up.
// Home Assistant is mocked; nothing is sent to a real house.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const light = (id, area, on) => ({
    id: "light." + id,
    name: "Lamp " + id,
    domain: "light",
    area,
    state: on ? "on" : "off",
    attributes: { brightness_pct: 40 },
    actions: ["turn_on", "turn_off", "brightness"],
  });
  const plug = (id, area) => ({
    id: "switch." + id,
    name: "Plug " + id,
    domain: "switch",
    area,
    state: "on",
    attributes: {},
    actions: ["turn_on", "turn_off"],
  });
  const counts = { Kitchen: 1, Office: 3, Salon: 2, Toilets: 1, Bedroom: 5, Hall: 1 };
  const areas = Object.entries(counts).map(([area, n]) => ({
    name: area,
    entities: Array.from({ length: n }, (_, i) => (i % 2 ? plug : light)(area + i, area, true)),
  }));
  await page.route("**/api/v1/house-settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), home_assistant: true } });
  });
  await page.route("**/api/v1/tv", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/home", (route) =>
    route.fulfill({ json: { curated: true, favorites: [], areas } }),
  );
  await page.goto(base + "/smart-home");
  await page.locator(".smart-room").first().waitFor();
  const wall = await page.locator(".smart-home__rooms").boundingBox();
  const rooms = await page.locator(".smart-home__rooms > .smart-room").evaluateAll((els) =>
    els.map((e) => {
      const r = e.getBoundingClientRect();
      const devices = [...e.querySelectorAll(".smart-device")].map((d) =>
        d.getBoundingClientRect(),
      );
      return {
        name: e.getAttribute("aria-label"),
        top: Math.round(r.top),
        right: r.right,
        head: e.querySelector(".smart-room__head").getBoundingClientRect().height,
        rows: new Set(devices.map((d) => Math.round(d.top))).size,
        devices: devices.length,
      };
    }),
  );
  assert.equal(rooms.length, Object.keys(counts).length);
  const rows = new Map();
  for (const r of rooms) rows.set(r.top, [...(rows.get(r.top) || []), r]);
  assert.ok(rows.size < rooms.length, "rooms share rows");
  for (const row of rows.values())
    assert.ok(wall.x + wall.width - Math.max(...row.map((r) => r.right)) < 2, "each row is full");
  const bedroom = rooms.find((r) => r.name === "Bedroom");
  assert.ok(bedroom.rows < bedroom.devices, "a big room lays its devices side by side");
  assert.equal(new Set(rooms.map((r) => Math.round(r.head))).size, 1, "room headers line up");
  if (process.env.HOUSEOS_SHOTS)
    await page.screenshot({ path: process.env.HOUSEOS_SHOTS + "/smart-home.png" });
  await browser.close();
  console.log("smart-home-layout: PASS");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

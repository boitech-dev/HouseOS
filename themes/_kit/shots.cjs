// Screenshots for the theme kit's visuals, from the isolated test app (test data only):
//   node themes/_kit/shots.cjs --out <folder>      then   python3 themes/_kit/visuals.py <folder>
// The theme is chosen by mocking /house-settings in this browser (as frontend/tools/screens.cjs
// does): the test account's preferences are never written, and the script checks they didn't move.
// Film posters are never shot (Watch shows other people's artwork): Listen and House only.
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("/usr/lib/node_modules/playwright");
const session = require("../../frontend/tests/session.cjs");
const base = "http://127.0.0.1:8893";
const i = process.argv.indexOf("--out");
if (i < 0) throw new Error("usage: shots.cjs --out <folder>");
const out = path.resolve(process.argv[i + 1]);
fs.mkdirSync(out, { recursive: true });
const GROCERIES = ["Rye bread", "Oat milk", "Clementines", "Coffee beans", "Basil", "Parmesan"];

async function open(browser, theme, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height }, locale: "en-GB" });
  await session(context, base);
  await context.addInitScript(() => {
    const fixed = new Date("2026-09-26T21:30:00").getTime();
    const Real = Date;
    globalThis.Date = class extends Real {
      constructor(...a) { super(...(a.length ? a : [fixed])); }
      static now() { return fixed; }
    };
  }); // prettier-ignore
  const page = await context.newPage();
  await page.route("**/api/v1/music", (r) => r.fulfill({ json: {
    version: 5, current_id: "song", desired: "playing", plays_on: "computer",
    items: [{ id: "song", title: "Clair de Lune", uploader: "Claude Debussy", status: "playing", duration: 300, owner_id: "x" }],
    observation: { status: "observed", item_id: "song", idle: false, paused: false, position: 95, volume: 40 } } })); // prettier-ignore
  await page.route("**/api/v1/house-settings", async (r) => {
    const response = await r.fetch();
    const json = await response.json();
    await r.fulfill({ response, json: { ...json, preferences: { ...json.preferences, language: "en", theme, scheme: "" } } });
  });
  // Test data reads like test data: a tidy grocery list, an empty board, no set-up notice.
  await page.route(/household\/groceries\?state=open&limit=100/, async (r) => {
    const response = await r.fetch();
    const json = await response.json();
    const items = json.items.slice(0, GROCERIES.length).map((x, n) => ({ ...x, data: { ...x.data, label: GROCERIES[n] } }));
    await r.fulfill({ response, json: { ...json, items, total: items.length, has_more: false } });
  });
  await page.route(/household\/board\?/, (r) => r.fulfill({ json: { items: [], offset: 0, limit: 24, has_more: false, total: 0 } }));
  await page.route(/admin\/setup/, (r) => r.fulfill({ status: 404, json: {} }));
  return { context, page };
}
async function go(page, where) {
  try {
    await page.goto(base + where, { waitUntil: "networkidle", timeout: 20000 });
  } catch {}
  await page.waitForTimeout(1200);
}
const boxes = (page, sel) =>
  page.evaluate((s) => [...document.querySelectorAll(s)].map((e) => e.getBoundingClientRect())
    .filter((r) => r.width > 0 && r.height > 0).map((r) => [r.x, r.y, r.width, r.height].map(Math.round)), sel); // prettier-ignore
async function prefs(browser) {
  const context = await browser.newContext();
  await session(context, base);
  const p = await (await context.request.get(base + "/api/v1/preferences")).json();
  await context.close();
  return ["theme", "scheme", "language"].map((k) => p[k]).join("|");
}
async function shoot(browser, theme, size, where, act) {
  const { context, page } = await open(browser, theme, size);
  await go(page, where);
  await act(page);
  await context.close();
}
const png = (name) => ({ path: `${out}/${name}.png`, animations: "disabled" });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const before = await prefs(browser);
  const map = {};
  // The parts map: Home on a desktop and a room on a phone, in Pure.
  await shoot(browser, "pure", [1440, 900], "/", async (p) => {
    await p.screenshot(png("map-desktop"));
    map.desktop = { rail: await boxes(p, ".shell__rail"), status: await boxes(p, ".shell__status"),
      hero: await boxes(p, ".shell__main > * > *:first-child"), panel: await boxes(p, ".ds-panel"), main: await boxes(p, ".shell__main") }; // prettier-ignore
  });
  await shoot(browser, "pure", [390, 844], "/house?tab=board", async (p) => {
    await p.screenshot(png("map-phone"));
    map.phone = { status: await boxes(p, ".shell__status"), header: await boxes(p, ".ds-page-header"),
      now: await boxes(p, ".shell__now"), dock: await boxes(p, ".shell__dock") }; // prettier-ignore
  });
  // Header variants: the same header, switched in place (Bathhouse After Hours, a banner per room).
  // A ribbon only changes a kicker (Home's date), so it isn't shown here.
  await shoot(browser, "sento-night", [1440, 900], "/house?tab=board", async (p) => {
    for (const variant of ["plain", "banner", "framed"]) {
      await p.evaluate((v) => {
        document.documentElement.setAttribute("data-part-header", v);
        for (const banner of document.querySelectorAll(".ds-page-header__banner")) banner.style.display = v === "banner" ? "" : "none";
      }, variant);
      await p.waitForTimeout(300);
      const [, y, , h] = (await boxes(p, ".ds-page-header"))[0];
      await p.screenshot({ ...png(`header-${variant}`), clip: { x: 232, y: 48, width: 1208, height: y + h - 28 } });
    }
  });
  // Panel variants: the same panel, switched in place (Pocket Hatchling: a green card on pink).
  await shoot(browser, "pocket-hatchling", [1440, 900], "/", async (p) => {
    const [x, y, w] = (await boxes(p, ".ds-panel"))[0];
    for (const variant of ["card", "flat", "outlined"]) {
      await p.evaluate((v) => document.documentElement.setAttribute("data-part-panel", v), variant);
      await p.waitForTimeout(300);
      await p.screenshot({ ...png(`panel-${variant}`), clip: { x: x - 16, y: y - 16, width: w + 32, height: 300 } });
    }
  });
  // Art behind pages: Zabiwa as shipped, then the same page with its page tokens and framed title off.
  await shoot(browser, "zabiwa", [1440, 900], "/listen", async (p) => {
    await p.screenshot(png("art-do"));
    await p.evaluate(() => {
      document.documentElement.setAttribute("data-part-header", "plain");
      const style = document.createElement("style");
      style.textContent = ":root,[data-theme]{--part-page-quiet:transparent!important;--part-page-gallery:transparent!important;--part-page-ink-shadow:none!important;--part-page-scrim:transparent!important}";
      document.head.append(style);
    });
    await p.waitForTimeout(400);
    await p.screenshot(png("art-dont"));
  });
  fs.writeFileSync(`${out}/boxes.json`, JSON.stringify(map, null, 1));
  const after = await prefs(browser);
  await browser.close();
  if (before !== after) throw new Error(`the test account's preferences moved: ${before} → ${after}`);
  console.log(`shots → ${out}`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

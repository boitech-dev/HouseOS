// Screenshots of every place, from the isolated test app (test data only), for before/after
// comparisons and theme contact sheets. Not a test: `npm run test:browser` does not run it.
//   node tools/screens.cjs --out <folder> [--theme <id>] [--scheme dark|light]
//                          [--lang en|fr] [--sizes phone,desktop] [--full] [--only name,name]
// Writes <out>/<size>/<NN-place>.png (as seen; --full adds <name>--full-page.png).
const { chromium } = require("/usr/lib/node_modules/playwright");
const fs = require("node:fs");
const mocks = require("./mocks.cjs");
const arg = (name, fallback) => {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const out = arg("out");
if (!out) throw new Error("--out <folder> is required");
const theme = arg("theme", "");
const scheme = arg("scheme", "");
const lang = arg("lang", "en");
const full = process.argv.includes("--full");
const only = (arg("only", "") || "").split(",").filter(Boolean);
const base = "http://127.0.0.1:8893";
const SIZES = { phone: [390, 844], desktop: [1440, 900], tablet: [768, 1024], small: [360, 780], laptop: [1280, 900] };
const sizes = arg("sizes", "phone,desktop").split(",");
const TABS = ["setup", "health", "jobs", "logs", "users", "invites", "devices", "speakers", "ai",
  "integrations", "usage", "storage", "recovery", "house", "themes", "access", "services"]; // prettier-ignore
const PAGES = [
  ["01-home", "/"], ["02-listen", "/listen"], ["03-listen-my-music", "/listen#saved"], ["04-watch", "/watch"],
  ["05-house-board", "/house?tab=board"], ["06-house-tasks", "/house?tab=tasks"], ["07-house-calendar", "/house?tab=calendar"],
  ["08-house-groceries", "/house?tab=groceries"], ["09-inbox", "/inbox"], ["10-files", "/files"],
  ["11-smart-home", "/smart-home"], ["12-nox-chat", "/assistant"], ["13-my-space", "/space"], ["14-preferences", "/me"],
  ["15-party", "/party"], ["16-speaker-mode", "/speaker"], ["17-workbench", "/workbench"],
  ...TABS.map((tab, i) => [`${20 + i}-control-${tab}`, "/control?tab=" + tab]),
].filter(([name]) => !only.length || only.some((o) => name.includes(o))); // prettier-ignore
(async () => {
  const browser = await chromium.launch({ headless: true });
  const session = require("../tests/session.cjs");
  for (const size of sizes) {
    const [width, height] = SIZES[size];
    fs.mkdirSync(`${out}/${size}`, { recursive: true });
    const context = await browser.newContext({ viewport: { width, height }, locale: lang === "fr" ? "fr-FR" : "en-GB" });
    await session(context, base);
    // A fixed clock, so scenes and times match between two runs.
    await context.addInitScript(() => {
      const fixed = new Date("2026-09-26T21:30:00").getTime();
      const Real = Date;
      globalThis.Date = class extends Real {
        constructor(...a) { super(...(a.length ? a : [fixed])); }
        static now() { return fixed; }
      };
    }); // prettier-ignore
    const page = await context.newPage();
    await mocks(page, { theme, scheme, lang });
    for (const [name, path] of PAGES) {
      try {
        await page.goto(base + path, { waitUntil: "networkidle", timeout: 20000 });
      } catch {}
      await page.waitForTimeout(900);
      await page.screenshot({ path: `${out}/${size}/${name}.png`, animations: "disabled" });
      if (full) {
        const hide = await page.addStyleTag({ content: ".mh-players,.mh-totop,.mh-dock,.shell__now,.shell__dock{display:none!important}" });
        await page.screenshot({ path: `${out}/${size}/${name}--full-page.png`, fullPage: true, animations: "disabled" });
        await hide.evaluate((node) => node.remove());
      }
    }
    await context.close();
  }
  await browser.close();
  console.log(`screens: ${PAGES.length} places × ${sizes.join(", ")} → ${out}`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

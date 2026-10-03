// A theme's tour: every place a theme touches, as a person sees it, and an audit of what must
// never break. For theme authors and their agents (themes/AGENT-KIT.md); needs the test app.
//   node themes/_kit/tour.cjs <theme> [--base http://127.0.0.1:5176] [--quick]
// --base: the Vite dev server (live theme changes; start it with HOUSEOS_API=http://127.0.0.1:8893
// npm run dev) or the test app itself (http://127.0.0.1:8893, the last build). --quick: desktop
// Home, Listen and the Control Room only.
// Writes themes/<theme>/shots/: <scheme>-<size>-<place>.png, contact.html to look at, audit.json;
// and art/card-<scheme>.webp (the full tour, or --cards alone): the theme's card in the pickers.
// The audit fails (exit 1) on: the page scrolling sideways, text cut off without an ellipsis, a
// control outside the screen, a layer catching a click, axe colour-contrast problems, a focused
// control without a visible ring.
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("/usr/lib/node_modules/playwright");
const frontend = path.resolve(__dirname, "../../frontend");
const session = require(frontend + "/tests/session.cjs");
const mocks = require(frontend + "/tools/mocks.cjs");
const axe = require.resolve("axe-core/axe.min.js", { paths: [frontend] });
const arg = (name, fallback) => {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const theme = process.argv[2];
if (!theme || theme.startsWith("--")) throw new Error("usage: tour.cjs <theme> [--base URL] [--quick]");
const base = arg("base", "http://127.0.0.1:5176");
const quick = process.argv.includes("--quick");
const folder = path.resolve(__dirname, "..", theme);
const out = path.join(folder, "shots");
const { schemes } = JSON.parse(fs.readFileSync(path.join(folder, "theme.json"), "utf8"));
const SIZES = { phone: [390, 844], desktop: [1440, 900] };
const PLACES = [
  ["home", "/"], ["listen", "/listen"], ["watch", "/watch"], ["games", "/games"], ["house", "/house?tab=groceries"],
  ["space", "/space"], ["me", "/me"], ["inbox", "/inbox"], ["files", "/files"], ["control-themes", "/control?tab=themes"],
  ["control-setup", "/control?tab=setup"], ["control-users", "/control?tab=users"],
]; // prettier-ignore
const QUICK = ["home", "listen", "control-setup"];

// Runs in the page: what a person would call broken.
function audit() {
  const problems = [];
  const name = (e) => (e.getAttribute("aria-label") || e.textContent || e.className || e.tagName).trim().slice(0, 50);
  const scrolls = (e) => { for (let p = e.parentElement; p; p = p.parentElement) { const s = getComputedStyle(p);
    if (/(auto|scroll)/.test(s.overflowX)) return true; } return false; }; // prettier-ignore
  if (document.documentElement.scrollWidth > innerWidth + 1)
    problems.push(`the page scrolls sideways (${document.documentElement.scrollWidth}px wide)`);
  for (const e of document.querySelectorAll("h1,h2,h3,p,span,strong,label,a,button,li,dt,dd,small")) {
    const s = getComputedStyle(e);
    const own = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || s.textOverflow === "ellipsis" || s.webkitLineClamp !== "none") continue;
    if (!(/(hidden|clip)/.test(s.overflowX + s.overflow) && e.scrollWidth > e.clientWidth + 1)) continue;
    // Only what a person sees: on screen, not a hidden label, not under something else.
    const r = e.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const hit = document.elementFromPoint(Math.min(innerWidth - 1, r.x + r.width / 2), Math.min(innerHeight - 1, Math.max(0, r.y + r.height / 2)));
    if (hit && (e.contains(hit) || hit.contains(e))) problems.push(`text cut off: "${name(e)}"`);
  }
  for (const e of document.querySelectorAll("button,a[href],input,select,[role=tab]")) {
    const r = e.getBoundingClientRect();
    if (!r.width || scrolls(e) || e.closest("[inert],[hidden],.visually-hidden")) continue;
    if (r.right > innerWidth + 1 || r.left < -1) problems.push(`off the screen: "${name(e)}"`);
    const hit = r.top >= 0 && r.bottom <= innerHeight && document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    if (hit && hit.closest(".ds-layers")) problems.push(`a layer covers "${name(e)}"`);
  }
  return [...new Set(problems)];
}

// A card is the same for every theme: desktop Home, a demo person and groceries, no setup row, motion
// still (first frames, nothing crossing), the same clock; shot at 1440 × 900 and saved 560 × 350.
const GROCERIES = ["Rye bread", "Oat milk", "Clementines", "Coffee beans", "Basil", "Parmesan"];
async function cards(browser) {
  for (const scheme of schemes) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await session(context, "http://127.0.0.1:8893");
    await context.addInitScript(() => {
      const fixed = new Date("2026-09-26T19:30:00").getTime();
      const Real = Date;
      globalThis.Date = class extends Real {
        constructor(...a) { super(...(a.length ? a : [fixed])); }
        static now() { return fixed; }
      };
    }); // prettier-ignore
    const page = await context.newPage();
    await mocks(page, { theme, scheme, lang: "en", motion: "still" });
    await page.route(/api\/v1\/auth\/me(\?|$)/, async (r) => {
      const response = await r.fetch();
      const json = await response.json();
      await r.fulfill({ response, json: { ...json, user: { ...json.user, name: "Luna" } } });
    });
    await page.route(/household\/groceries\?state=open/, async (r) => {
      const response = await r.fetch();
      const json = await response.json();
      const items = json.items.slice(0, GROCERIES.length).map((x, n) => ({ ...x, data: { ...x.data, label: GROCERIES[n] } }));
      await r.fulfill({ response, json: { ...json, items, total: items.length, has_more: false } });
    }); // prettier-ignore
    await page.route(/admin\/setup/, (r) => r.fulfill({ status: 404, json: {} }));
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.goto(base + "/", { waitUntil: "networkidle" }).catch(() => {});
      await page.waitForTimeout(1500);
      if (((await page.textContent("main h1").catch(() => "")) ?? "").includes("Luna")) break; // the demo greeting
    }
    const png = path.join(out, `card-${scheme}.png`);
    await page.screenshot({ path: png });
    execFileSync("python3", ["-c", "import sys; from PIL import Image; Image.open(sys.argv[1]).convert('RGB').resize((560, 350), Image.LANCZOS).save(sys.argv[2], quality=82, method=6)",
      png, path.join(folder, "art", `card-${scheme}.webp`)]); // prettier-ignore
    await context.close();
  }
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  if (process.argv.includes("--cards")) {
    const browser = await chromium.launch({ headless: true });
    await cards(browser);
    await browser.close();
    console.log(`tour ${theme}: cards ${schemes.map((s) => `art/card-${s}.webp`).join(", ")}`);
    return;
  }
  const browser = await chromium.launch({ headless: true });
  const report = { theme, base, pages: {}, contrast: [], focus: [], errors: [] };
  const shots = [];
  const places = PLACES.filter(([n]) => !quick || QUICK.includes(n));
  for (const scheme of schemes)
    for (const [size, [width, height]] of Object.entries(SIZES)) {
      if (quick && size === "phone") continue;
      for (const lang of size === "phone" && !quick ? ["en", "fr"] : ["en"]) {
        const context = await browser.newContext({ viewport: { width, height }, bypassCSP: true,
          locale: lang === "fr" ? "fr-FR" : "en-GB" }); // prettier-ignore
        await session(context, "http://127.0.0.1:8893"); // the cookie serves the dev server too
        const page = await context.newPage();
        page.on("pageerror", (e) => report.errors.push(String(e).slice(0, 200)));
        await mocks(page, { theme, scheme, lang, motion: "full" });
        for (const [place, where] of lang === "fr" ? places.filter(([n]) => QUICK.includes(n)) : places) {
          const file = `${scheme}-${size}${lang === "fr" ? "-fr" : ""}-${place}.png`;
          // Another theme's build reloads the dev server now and then: one more try.
          for (let attempt = 0; attempt < 2; attempt++)
            try {
              await page.goto(base + where, { waitUntil: "networkidle", timeout: 20000 }).catch(() => {});
              // Not a blank reload: the page has drawn something to read.
              await page.waitForFunction(() => (document.querySelector("main")?.textContent ?? "").trim().length > 0, null, { timeout: 10000 }); // prettier-ignore
              await page.waitForTimeout(1200);
              await page.screenshot({ path: path.join(out, file) });
              report.pages[file] = await page.evaluate(audit);
              break;
            } catch (error) {
              if (attempt) report.errors.push(`${file}: ${String(error).slice(0, 120)}`);
            }
          shots.push(file);
          if (lang === "en" && (place === "home" || place === "control-setup")) {
            await page.addScriptTag({ path: axe });
            const found = await page.evaluate(() => window.axe.run(document.body, {
              runOnly: ["color-contrast"], resultTypes: ["violations"] })); // prettier-ignore
            for (const v of found.violations)
              for (const n of v.nodes.slice(0, 6)) report.contrast.push(`${file}: ${n.target.join(" ")} ${n.any[0]?.message ?? ""}`.slice(0, 220));
          }
        }
        if (lang === "en") {
          // Focus rings: the first few controls reached by keyboard on Home.
          await page.goto(base + "/", { waitUntil: "networkidle" }).catch(() => {});
          for (let i = 0; i < 6; i++) {
            await page.keyboard.press("Tab");
            const ring = await page.evaluate(() => {
              const e = document.activeElement, s = e && getComputedStyle(e);
              return !e || e === document.body || s.outlineStyle !== "none" || s.boxShadow !== "none" ? "" : (e.textContent || e.getAttribute("aria-label") || e.tagName).trim().slice(0, 40);
            }); // prettier-ignore
            if (ring) report.focus.push(`${scheme}-${size}: no visible focus on "${ring}"`);
          }
          // Motion still: the first frame, nothing crossing or rising.
          await mocks(page, { theme, scheme, lang, motion: "still" });
          await page.goto(base + "/", { waitUntil: "networkidle" }).catch(() => {});
          await page.waitForTimeout(800);
          const file = `${scheme}-${size}-home-still.png`;
          await page.screenshot({ path: path.join(out, file) });
          shots.push(file);
        }
        await context.close();
      }
    }
  // Sign-in: a guest's first sight (the crest), in the theme this device wore last.
  for (const scheme of quick ? [] : schemes) {
    const guest = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await guest.addInitScript(([id, s]) => localStorage.setItem("houseos-theme", JSON.stringify({ theme: id, scheme: s })), [theme, scheme]); // prettier-ignore
    const door = await guest.newPage();
    await door.goto(base + "/", { waitUntil: "networkidle" }).catch(() => {});
    await door.waitForTimeout(1000);
    await door.screenshot({ path: path.join(out, `${scheme}-phone-signin.png`) });
    shots.push(`${scheme}-phone-signin.png`);
    await guest.close();
  }
  // The picker's card: Home in each scheme, tidy and still, at the card's size (art/card-<scheme>.webp).
  if (!quick) await cards(browser);
  await browser.close();
  fs.writeFileSync(path.join(out, "audit.json"), JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(out, "contact.html"), `<!doctype html><meta charset="utf-8"><title>${theme}</title>` +
    `<style>body{font:14px system-ui;margin:16px;background:#222;color:#eee}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}img{width:100%}figure{margin:0}</style>` +
    `<main>${shots.map((f) => `<figure><img loading="lazy" src="${f}"><figcaption>${f}</figcaption></figure>`).join("")}</main>`); // prettier-ignore
  const pageProblems = Object.entries(report.pages).flatMap(([f, list]) => list.map((p) => `${f}: ${p}`));
  const all = [...pageProblems, ...report.contrast, ...report.focus, ...report.errors.map((e) => "page error: " + e)];
  console.log(`tour ${theme}: ${shots.length} screenshots in themes/${theme}/shots/ (contact.html)`);
  console.log(all.length ? `${all.length} problems:\n- ` + all.slice(0, 40).join("\n- ") : "audit: nothing broken");
  process.exit(all.length ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(2);
});

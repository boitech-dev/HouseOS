// Nothing hidden from themes: each place is drawn in Base, then in Canary (every token a loud,
// different value). An element whose colours, font, corners or shadow stay the same is drawn with a
// value that doesn't come from a token. Every place must have none.
const { chromium } = require("/usr/lib/node_modules/playwright");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const PLACES = [
  ["home", "/"], ["listen", "/listen"], ["watch", "/watch"], ["house", "/house"], ["inbox", "/inbox"],
  ["files", "/files"], ["smart-home", "/smart-home"], ["ask", "/assistant"], ["me", "/me"],
  ["space", "/space"], ["control", "/control?tab=setup"], ["control-ai", "/control?tab=ai"], ["workbench", "/workshop?tab=pieces"], ["workshop", "/workshop"],
  ["party", "/party"], ["speaker", "/speaker"], ["tv", "/tv"],
]; // prettier-ignore

function styles() {
  const out = [];
  const skip = new Set([
    "IMG",
    "VIDEO",
    "CANVAS",
    "SOURCE",
    "PICTURE",
    "SCRIPT",
    "STYLE",
    "BR",
    "WBR",
  ]);
  for (const el of document.body.querySelectorAll("*")) {
    if (skip.has(el.tagName) || el.closest("svg:not(:scope)") || el.closest("[data-canary-ignore]"))
      continue;
    const box = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (!box.width || !box.height || s.visibility === "hidden" || s.display === "none") continue;
    const text = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const clear = (c) => !c || c === "rgba(0, 0, 0, 0)" || c === "transparent";
    const props = {};
    if (text) props.color = s.color;
    if (text) props.font = s.fontFamily;
    if (!clear(s.backgroundColor)) props.background = s.backgroundColor;
    for (const side of ["Top", "Right", "Bottom", "Left"])
      if (
        parseFloat(s["border" + side + "Width"]) > 0 &&
        s["border" + side + "Style"] !== "none" &&
        !clear(s["border" + side + "Color"])
      )
        props["border" + side] = s["border" + side + "Color"];
    if (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0 && !clear(s.outlineColor))
      props.outline = s.outlineColor; // like borders: a clear outline draws nothing
    if (s.borderTopLeftRadius !== "0px") props.radius = s.borderTopLeftRadius;
    if (s.boxShadow !== "none") props.shadow = s.boxShadow;
    if (el.tagName === "svg" && s.color) props.icon = s.color;
    const cls = [...el.classList].slice(0, 2).join(".");
    out.push({ at: el.tagName.toLowerCase() + (cls ? "." + cls : ""), props });
  }
  return out;
}

(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const report = {};
  const over = [];
  for (const [name, path] of PLACES) {
    await page.goto(base + path, { waitUntil: "networkidle" }).catch(() => {});
    await page.waitForTimeout(800);
    const drawn = [];
    for (const theme of ["base", "canary"]) {
      await page.evaluate((id) => {
        document.documentElement.dataset.theme = id;
        document.documentElement.dataset.scheme = "dark";
        document.documentElement.dataset.motionEffective = "still";
      }, theme);
      await page.waitForTimeout(250);
      drawn.push(await page.evaluate(styles));
    }
    const [a, b] = drawn;
    const flags = [];
    a.forEach((el, i) => {
      const other = b[i];
      if (!other || other.at !== el.at) return;
      for (const [prop, value] of Object.entries(el.props))
        if (other.props[prop] === value) flags.push(`${el.at} ${prop} ${value}`);
    });
    // Distinct misses (element kind, property, value), so the count doesn't grow with the data.
    const kinds = {};
    for (const flag of flags) kinds[flag] = (kinds[flag] || 0) + 1;
    const count = Object.keys(kinds).length;
    report[name] = { distinct: count, top: Object.entries(kinds).sort((x, y) => y[1] - x[1]) };
    console.log(`${count ? "✗" : "✓"} ${name}: ${count}`);
    if (count) over.push(name);
  }
  fs.mkdirSync("evidence/latest", { recursive: true });
  fs.writeFileSync("evidence/latest/theme-canary.json", JSON.stringify(report, null, 1));
  await browser.close();
  assert.deepEqual(
    over,
    [],
    "colours, fonts or shapes outside the tokens (evidence/latest/theme-canary.json): " + over.join(", "),
  );
  console.log("theme canary: every place drawn from the tokens");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

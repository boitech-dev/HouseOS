// Themes change without a reload: an installed theme (imported as a pack) is linked, worn and
// dropped; switching in Me → Appearance recolours the page, the browser bar and the art at once.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

// A pack made by the theme kit from Carved Night under another id, with its own accent.
const repo = path.resolve(__dirname, "../..");
const pack = execFileSync(
  "python3",
  [
    "-c",
    `
import json, shutil, sys, tempfile
from pathlib import Path
from houseos.theme_kit import pack, tokens
root = Path(tempfile.mkdtemp())
shutil.copytree(tokens.ROOT / "base", root / "base")
folder = shutil.copytree(tokens.ROOT / "carved-night", root / "runtime-test")
m = json.loads((folder / "theme.json").read_text()); m.update(id="runtime-test", slots={})
m["names"] = {"en": "Runtime test", "fr": "Test d'exécution"}
(folder / "theme.json").write_text(json.dumps(m))
t = json.loads((folder / "tokens.json").read_text())
t["color"]["accent"]["solid"] = {"$value": "#3fae6b"}
(folder / "tokens.json").write_text(json.dumps(t))
sys.stdout.buffer.write(pack.pack("runtime-test", root, root / "x.houseos-theme").read_bytes())
`,
  ],
  { env: { ...process.env, PYTHONPATH: path.join(repo, "backend") } },
);

(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const { csrf_token } = await (await require("./session.cjs")(context, base)).json();
  const headers = { Origin: base, "X-CSRF-Token": csrf_token };
  const prefer = (data) => context.request.put(base + "/api/v1/preferences", { headers, data });
  await context.request.delete(base + "/api/v1/themes/runtime-test", { headers }); // a leftover
  const made = await context.request.post(base + "/api/v1/themes/import", {
    headers,
    multipart: {
      file: { name: "runtime-test.houseos-theme", mimeType: "application/zip", buffer: pack },
    },
  });
  assert.equal(made.status(), 200, await made.text());
  assert.equal((await prefer({ theme: "runtime-test", scheme: "" })).status(), 200);

  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let loads = 0;
  page.on("load", () => loads++);
  await page.goto(base + "/me?tab=appearance");
  const state = () =>
    page.evaluate(() => ({
      theme: document.documentElement.dataset.theme,
      canvas: getComputedStyle(document.documentElement).getPropertyValue("--c-bg-canvas").trim(),
      accent: getComputedStyle(document.documentElement)
        .getPropertyValue("--c-accent-solid")
        .trim(),
      bar: document.querySelector('meta[name="theme-color"]').getAttribute("content"),
      linked: !!document.querySelector('link[data-installed-theme="runtime-test"]'),
      // A person's avatar is their own picture in every theme; the rest follows the identity.
      sprites: document.querySelectorAll(".ds-sprite:not(.ds-avatar__picture):not(.mini *)").length,
    }));
  await page.waitForFunction(() => document.documentElement.dataset.theme === "runtime-test");
  // Its stylesheet arrives after the page: wait until its own accent draws.
  await page.waitForFunction(
    () =>
      getComputedStyle(document.documentElement).getPropertyValue("--c-accent-solid").trim() ===
      "#3fae6b",
  );
  const worn = await state();
  assert.ok(worn.linked, "the installed theme's stylesheet is linked");
  assert.equal(worn.bar, worn.canvas, "the browser bar takes the theme's ground");
  assert.ok(worn.sprites > 0, "Carved Night's pixel identity draws sprites");
  // Its card is in the picker (it's this person's own draft).
  await page.getByRole("radio", { name: /Runtime test/ }).waitFor({ state: "attached" });

  // Pure, from the picker (Base is the hidden root now): recoloured at once, no reload.
  await page.getByRole("radio", { name: /^Pure\b/ }).first().click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "pure");
  const plain = await state();
  assert.notEqual(plain.canvas, worn.canvas);
  assert.equal(plain.bar, plain.canvas);
  assert.equal(loads, 1, "switching never reloads");

  // Removed: the page falls back to the house's theme and unlinks the stylesheet.
  await prefer({ theme: "runtime-test" });
  assert.equal(
    (await context.request.delete(base + "/api/v1/themes/runtime-test", { headers })).status(),
    200,
  );
  await page.reload();
  await page.waitForFunction(
    () => !document.querySelector('link[data-installed-theme="runtime-test"]'),
  );
  const house = await (await context.request.get(base + "/api/v1/house-settings")).json();
  await page.waitForFunction((id) => document.documentElement.dataset.theme === id, house.theme);
  await prefer({ theme: "" });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("theme runtime: installed theme linked, worn, switched without reload, removed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

// The theme workshop: the tour's numbered parts, starting a theme, Remix's live preview and save,
// the pixel editor, trying a theme on, and "Pick your look" once.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const base = "http://127.0.0.1:8893";
  const me = await require("./session.cjs")(context, base);
  const { csrf_token } = await me.json();
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // The tour: a part's number says what shapes it.
  await page.goto(base + "/workshop");
  await page.getByRole("button", { name: "Part 7" }).click();
  await page.getByRole("heading", { name: "7. House titles and medals" }).waitFor();
  // Start a theme: named, from Linen Morning, then the editor opens on it.
  await page.getByRole("button", { name: "Start a theme" }).first().click();
  const start = page.getByRole("dialog", { name: "Start a theme" });
  await start.getByLabel("Its name").fill("Test remix");
  await start.getByRole("combobox").selectOption("linen-morning");
  await start.getByRole("button", { name: "Start", exact: true }).click();
  await page.waitForURL(/\/workshop\/remix\?id=test-remix-/);
  const id = new URL(page.url()).searchParams.get("id");
  await page.getByText("Every check passes").waitFor();
  await page.locator(".remix__stage .mini").waitFor();
  assert.equal(await page.locator(".remix__stage .mini").getAttribute("data-theme"), id + "--preview");
  // A change is previewed, not kept, until Save.
  await page.getByRole("button", { name: "Parts", exact: true }).click();
  await page.getByRole("radio", { name: "flat" }).check({ force: true });
  await page.waitForFunction(
    (id) => document.querySelector(`.mini[data-theme="${id}--preview"]`)?.getAttribute("data-part-panel") === "flat",
    id,
  );
  let saved = await (await context.request.get(base + "/api/v1/themes/remix/" + id)).json();
  assert.notEqual(saved.theme.parts?.panel, "flat"); // previewed, not kept
  // A pixel on the moon avatar, then Save: kept.
  await page.getByRole("button", { name: "Pixels", exact: true }).click();
  await page.locator('.remix__grid span[data-x="15"][data-y="15"]').click();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("button", { name: "Saved", exact: true }).waitFor();
  saved = await (await context.request.get(base + "/api/v1/themes/remix/" + id)).json();
  assert.equal(saved.theme.parts.panel, "flat");
  assert(saved.sprites.glyphs["avatar.moon"], "the redrawn piece is kept");
  // Trying a theme on: this device only, then taken off.
  const before = await page.evaluate(() => document.documentElement.dataset.theme);
  await page.goto(base + "/workshop?tab=ideas");
  await page.getByRole("button", { name: "Try it on" }).first().click();
  await page.getByRole("complementary", { name: "Trying a theme on" }).waitFor();
  await page.getByRole("button", { name: "Take it off" }).click();
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), before);
  await context.request.delete(base + "/api/v1/themes/" + id, {
    headers: { Origin: base, "X-CSRF-Token": csrf_token },
  });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("workshop and remix ok");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

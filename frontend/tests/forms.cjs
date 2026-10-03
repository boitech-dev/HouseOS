const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const base = "http://127.0.0.1:8893";
  const r = await require("./session.cjs")(context, base);
  assert(r.ok());
  const page = await context.newPage();
  page.setDefaultNavigationTimeout(15000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // Motion applies at once (Appearance), then the film choices and Nox's memory.
  await page.goto(base + "/settings?tab=appearance", { waitUntil: "domcontentloaded" });
  // Two changes, so one of them always differs from what an earlier run left.
  for (const motion of ["Full", "Still"]) {
    await page.locator(".ds-segmented label", { hasText: motion }).first().click();
    await page.getByText("Preferences saved.", { exact: true }).first().waitFor();
  }
  const saved = await (await page.request.get(base + "/api/v1/preferences")).json();
  if (saved.motion !== "still") throw new Error("motion not saved: " + saved.motion);
  await page.goto(base + "/settings?tab=films", { waitUntil: "domcontentloaded" });
  const cinema = page.locator(".ds-settings__detail");
  // Languages you understand: add one from the list, then keep subtitles in French first.
  await cinema.getByLabel("Add a language", { exact: true }).waitFor();
  const again = cinema.getByRole("button", { name: "Remove · Polish", exact: true });
  if (await again.count()) await again.click(); // saved by an earlier run
  await cinema.getByLabel("Add a language", { exact: true }).selectOption("pl");
  await cinema.getByText("Polish", { exact: true }).waitFor();
  await cinema.getByLabel("Subtitles", { exact: true }).selectOption({ index: 0 });
  await cinema.getByRole("button", { name: "Save film choices", exact: true }).click();
  await page.getByText("Cinema defaults saved.", { exact: true }).waitFor();
  const films = await (await page.request.get(base + "/api/v1/cinema/preferences")).json();
  if (!films.languages?.includes("pl"))
    throw new Error("languages not saved: " + JSON.stringify(films));
  await page.goto(base + "/settings?tab=memory", { waitUntil: "domcontentloaded" });
  const memory = page.locator(".ds-settings__detail");
  await memory.getByLabel("Remember this").fill("Test-only explicit browser memory.");
  await memory.getByRole("button", { name: "Add to Nox's memory", exact: true }).click();
  await memory.getByText("Test-only explicit browser memory.", { exact: true }).first().waitFor();
  await memory.getByRole("button", { name: "Edit memory", exact: true }).first().click();
  await page.getByRole("dialog").getByLabel("Memory text").fill("Updated explicit test memory");
  await page.getByRole("dialog").getByRole("button", { name: "Save", exact: true }).click();
  await memory.getByText("Updated explicit test memory", { exact: true }).first().waitFor();
  await page.goto(base + "/house", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Calendar", exact: true }).click();
  await page.getByRole("button", { name: "Add an event", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title", { exact: true }).fill("UI test event");
  await dialog.getByLabel(/^Starts · /).fill("2026-09-25T18:00");
  await dialog.getByLabel(/^Ends · /).fill("2026-09-25T19:00");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await page
    .getByRole("button", { name: /UI test event/ })
    .first()
    .waitFor();
  await page.goto(base + "/assistant", { waitUntil: "domcontentloaded" });
  await page
    .getByRole("textbox", { name: "Message your assistant" })
    .fill("Test configuration state");
  await page.getByText("The house assistant is not configured yet.", { exact: false }).waitFor();
  assert(
    await page.getByRole("button", { name: "Send message", exact: true }).isDisabled(),
    "Unconfigured assistant must not submit",
  );
  assert.equal(errors.length, 0, errors.join(";"));
  console.log(
    "PASS preferences, media defaults, explicit memory, calendar create, assistant disabled contract",
  );
  await browser.close();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

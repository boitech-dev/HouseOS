// Real-API basics the room tests don't cover: a wall note, a grocery, and an invitation with its
// QR code (qrcode loads on demand). Layout and overflow are shell.cjs and phone-fit.cjs.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultNavigationTimeout(15000);
  const base = process.env.HOUSEOS_TEST_URL || "http://127.0.0.1:8893";
  const failures = [];
  page.on("pageerror", (e) => failures.push(e.message));
  await require("./session.cjs")(context, base);
  await page.goto(base + "/house", { waitUntil: "domcontentloaded" });
  const note = "Browser verified note " + Date.now();
  await page.getByLabel("Your message to the house", { exact: true }).fill(note);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByText(note, { exact: true }).first().waitFor();
  await page.getByRole("button", { name: /^Groceries/ }).click();
  await page
    .getByPlaceholder("Milk, coffee, something for tonight…")
    .fill("UI test apples " + Date.now());
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByRole("checkbox").first().waitFor();
  await page.goto(base + "/control?tab=invites", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Create invitation", exact: true }).click();
  await page.getByText("Your invitation is ready.").waitFor();
  assert.match(
    await page.getByAltText("QR code for this invitation").getAttribute("src"),
    /^data:image\/png/,
  );
  assert.equal(failures.length, 0, "Browser exceptions: " + failures.join(";"));
  await browser.close();
  console.log("PASS real API basics: wall note, grocery, invitation QR");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

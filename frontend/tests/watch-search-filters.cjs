// Searching a person's name shows their whole work; kept as a filter, the next name narrows it
// (Brad Pitt, then Angelina Jolie: the films with both); a year typed in does the same.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/watch");
  const box = page.getByRole("searchbox").first();
  const search = async (text) => {
    await box.fill(text);
    await box.press("Enter");
  };
  await search("brad pitt");
  await page.getByRole("heading", { name: "Films with Brad Pitt" }).waitFor();
  await page.getByRole("button", { name: "Keep as a filter" }).click();
  await search("Angelina Jolie");
  await page.getByRole("heading", { name: "Films with Brad Pitt & Angelina Jolie" }).waitFor();
  await page.getByText("Mr. & Mrs. Smith").first().waitFor();
  const both = Number((await page.getByText(/^\d+ titles?$/).first().textContent()).match(/\d+/)[0]);
  assert.ok(both >= 1 && both < 10, "only the films with both: " + both);
  await page.getByRole("button", { name: "Keep as a filter" }).click();
  await search("2005");
  await page.getByRole("heading", { name: "Films with Brad Pitt & Angelina Jolie · 2005" }).waitFor();
  // The titles search is still one tap away.
  await page.getByRole("button", { name: /^Titles with “2005”/ }).click();
  await page.getByRole("button", { name: "Keep as a filter" }).waitFor({ state: "detached" });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS a name or a year searched joins the filters: two people give the films with both");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let sent;
  await page.route("**/api/v1/people", (r) =>
    r.fulfill({
      json: {
        items: [
          { id: "person-one", name: "Camille" },
          { id: "person-two", name: "Max" },
        ],
      },
    }),
  );
  await page.route("**/api/v1/household/messages", (r) => {
    if (r.request().method() === "POST") {
      sent = r.request().postDataJSON();
      return r.fulfill({ json: { id: "message-fixture" } });
    }
    return r.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/v1/household/conversations", (r) => r.fulfill({ json: { items: [] } }));
  await page.goto(base + "/inbox");
  await page.getByRole("button", { name: "New message" }).click();
  await page.getByLabel("Subject", { exact: true }).fill("Tea");
  await page.getByLabel("Message", { exact: true }).fill("Meet downstairs");
  await page.getByLabel("Find a housemate").fill("Cam");
  await page.getByRole("button", { name: "Camille", exact: true }).click(); // a person chip
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  // Sent: the composer closes (the new conversation opens when there is one).
  await page.getByLabel("Subject", { exact: true }).waitFor({ state: "detached" });
  assert.equal(sent.data.title, "Tea");
  assert.deepEqual(sent.data.recipient_ids, ["person-one"]);
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page.screenshot({ path: "evidence/latest/inbox-inline-phone.png", fullPage: true });
  await page.goto(base + "/admin");
  await page.locator(".control-map").getByRole("button", { name: /^Storage\b/ }).click();
  await page.getByText("What the house keeps", { exact: true }).waitFor();
  // The drive at a glance, then the space per person (its own meters).
  await page.getByText("Space per person", { exact: true }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[role="progressbar"]').length >= 2);
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/storage-overview-phone.png", fullPage: true });
  await browser.close();
  console.log("PASS inline inbox send/reset/recipients and actual storage inventory mobile meters");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

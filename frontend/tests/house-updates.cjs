// Updates in Control Room: the new version named, "Check for updates", the night option; and
// Nox's note in the inbox. The helper's answers are mocked; nothing is installed.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const shots = process.env.HOUSEOS_SHOTS || "";
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const sent = [];
  let auto = false;
  await page.route("**/api/v1/admin/house-actions", (route) =>
    route.fulfill({
      json: {
        container: true,
        helper: true,
        auto,
        checked: true,
        tasks: [],
        effects: { update: "…" },
        about: { version: "v2.0.0", behind: "4", gpu_available: "no" },
        available: ["2.0.0", "2.1.0"],
      },
    }),
  );
  await page.route("**/api/v1/admin/house-actions/check", (route) => {
    sent.push("check");
    route.fulfill({ json: { status: "checking" } });
  });
  await page.route("**/api/v1/admin/house-actions/updates", (route) => {
    auto = route.request().postDataJSON().auto;
    sent.push("auto:" + auto);
    route.fulfill({ json: { auto } });
  });
  await page.route("**/api/v1/household/inbox?*", (route) =>
    route.fulfill({
      json: {
        items: [
          { id: "n1", record_id: "2.1.0", category: "update", created_at: "2026-09-26T08:00:00" },
        ],
      },
    }),
  );
  await page.goto(base + "/control?tab=services");
  await page.getByText("HouseOS 2.1.0 is ready (you have 2.0.0).").waitFor();
  await page.getByRole("button", { name: "Check for updates" }).click();
  await page.getByLabel(/Update by itself at night/).check();
  await page.waitForTimeout(300);
  assert.deepEqual(sent, ["check", "auto:true"]);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  if (shots)
    await page.locator(".house-actions").screenshot({ path: `${shots}/house-updates.png` });
  await page.goto(base + "/inbox");
  await page.getByText(/Nox: HouseOS 2.1.0 is out/).waitFor();
  await page.getByRole("button", { name: "See the update" }).click();
  await page.waitForURL(/tab=services/);
  await browser.close();
  console.log("house-updates: PASS");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

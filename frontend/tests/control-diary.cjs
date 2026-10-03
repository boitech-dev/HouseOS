const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
// Control Room: Services say calmly what is wrong (never all red for a missing helper), and
// Logs is a colour-coded diary of sentences with times, categories and a problems filter.
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/admin/services", (route) =>
    route.fulfill({
      json: [
        { name: "api", status: "observed", active: "active" },
        { name: "worker", status: "observed", active: "failed", exit_code: "1" },
      ],
    }),
  );
  await page.goto(base + "/control?tab=services");
  await page.getByText("1 of 2 parts need attention: see the red ones below.").waitFor();
  assert.equal(await page.locator('.ds-row .ds-status[data-tone="success"]').count(), 1);
  assert.equal(await page.locator('.ds-row .ds-status[data-tone="danger"]').count(), 1);
  await page.getByText("Stopped after an error (1)").waitFor();

  await page.route("**/api/v1/admin/activity**", (route) => {
    const problems = route.request().url().includes("needs=true");
    const lines = [
      {
        id: 3,
        at: new Date().toISOString(),
        category: "system",
        level: "problem",
        who: null,
        actor: "House",
        tried: "POST /themes/remix",
        care: "needs",
        count: 3,
        template: "Something went wrong (ref. {ref})",
        values: { ref: "abcd1234", code: "SOURCE_REMOVED" },
      },
      {
        id: 2,
        at: new Date().toISOString(),
        category: "nox",
        level: "info",
        who: "Luna",
        template: "Nox used {tool} · {status}",
        values: { tool: "music_add_candidates", status: "accepted" },
      },
      {
        id: 1,
        at: new Date().toISOString(),
        category: "music",
        level: "info",
        who: "Milo",
        template: "Playing {title}",
        values: { title: "Balade" },
      },
    ];
    return route.fulfill({ json: { items: problems ? lines.slice(0, 1) : lines, next: null } });
  });
  await page.goto(base + "/control?tab=logs");
  await page.getByText("Playing Balade").waitFor();
  await page.getByText("Nox used music_add_candidates · accepted").waitFor();
  assert.equal(await page.locator('.control-log__icon[data-care="needs"]').count(), 1);
  // grouped, with why it failed first, then who acted and what it tried
  await page.getByText("Something went wrong (ref. abcd1234) ×3").waitFor();
  await page.getByText(/This video was removed or made private\. · House · POST \/themes\/remix/).waitFor();
  assert.match(await page.locator(".ds-row time").first().innerText(), /^\d\d:\d\d:\d\d$/);
  await page.getByRole("button", { name: /Needs you/ }).click();
  await page.waitForFunction(() => document.querySelectorAll(".ds-row time").length === 1);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS services summary and fixes, colour-coded diary with times and problems filter");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

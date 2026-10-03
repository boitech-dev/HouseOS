const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true }),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    saves = [];
  await page.route("**/api/v1/admin/assistants", (r) =>
    r.fulfill({
      json: {
        items: ["general", "personal_space"].map((purpose) => ({
          purpose,
          provider: "openrouter",
          model: "small",
          reasoning_effort: "low",
        })),
        connections: [{ provider: "openrouter", enabled: true, auth_mode: "api" }],
      },
    }),
  );
  await page.route("**/api/v1/admin/assistants/*", (r) => {
    saves.push({ path: new URL(r.request().url()).pathname, ...r.request().postDataJSON() });
    return r.fulfill({ json: { status: "completed" } });
  });
  // Saving runs one real short round; here its answer is a fixture.
  await page.route("**/api/v1/admin/assistants/*/test", (r) =>
    r.fulfill({ json: { status: "verified", seconds: 2.1, model: "large" } }),
  );
  await page.route("**/api/v1/admin/providers/openrouter/models", (r) =>
    r.fulfill({
      json: {
        auth_mode: "api",
        items: ["small", "large"].map((id) => ({
          id,
          name: id,
          tool_support: "declared",
          supported_parameters: ["reasoning"],
        })),
      },
    }),
  );
  await page.goto(base + "/admin");
  await page.locator(".control-map").getByRole("button", { name: /^AI\b/ }).click();
  await page.locator("#assistant-models").waitFor(); // in sight, not folded away
  const card = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "My space setup assistant" }) });
  await card.getByLabel("Model", { exact: true }).fill("large");
  await card.getByLabel("How hard it thinks").selectOption("low");
  await card.getByText("This assistant will use").waitFor();
  await card.getByRole("button", { name: "Save and test" }).click();
  await card.getByText("Tested: answered in 2.1 s with large.").waitFor();
  assert.equal(saves[0].path, "/api/v1/admin/assistants/personal_space");
  assert.equal(saves[0].model, "large");
  assert.equal(
    await page
      .locator("article")
      .filter({ has: page.getByRole("heading", { name: "Household assistant", exact: true }) })
      .getByLabel("Model", { exact: true })
      .inputValue(),
    "small",
  );
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({
    path: "evidence/latest/assistant-assignments-phone.png",
    fullPage: true,
  });
  await browser.close();
  console.log(
    "PASS independent admin-only assistant assignments, model selection, effort and phone layout (catalog/save fixtures)",
  );
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

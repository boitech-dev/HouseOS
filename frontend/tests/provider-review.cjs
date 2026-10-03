const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict"),
  fs = require("node:fs");
(async () => {
  const browser = await chromium.launch({ headless: true }),
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    failures = [],
    saves = [];
  page.on("pageerror", (e) => failures.push(e.message));
  await page.route("**/api/v1/admin/integrations", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: (await response.json()).map((r) =>
        r.name === "openrouter"
          ? { ...r, has_secret: true, configured: true, enabled: true, config: { model: "old" } }
          : ["openai", "anthropic", "compatible"].includes(r.name)
            ? { ...r, has_secret: false, config: {}, enabled: false }
            : r,
      ),
    });
  });
  await page.route("**/api/v1/admin/integrations/*", async (route) => {
    if (route.request().method() === "PUT") {
      saves.push(route.request().postDataJSON());
      await route.fulfill({ json: { status: "completed" } });
    } else await route.continue();
  });
  await page.route("**/api/v1/admin/providers/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/models")) return route.fulfill({ json: { items: [] } });
    if (path.endsWith("/models/refresh"))
      return route.fulfill({
        json: {
          auth_mode: route.request().postDataJSON().auth_mode,
          items: Array.from({ length: 650 }, (_, i) => ({
            id: "vendor/model-" + i,
            name: "Searchable model " + i,
            tool_support: "declared",
            pricing: { input_microusd_per_million: 1000000, output_microusd_per_million: 2000000 },
          })),
        },
      });
    if (path.endsWith("/connect"))
      return route.fulfill({
        json: {
          status: "connected",
          provider: "openrouter",
          model: "vendor/model-1",
          tested: null,
        },
      });
    if (path.endsWith("/native/status"))
      return route.fulfill({ json: { status: "unavailable", logged_in: false } });
    return route.fulfill({ json: { status: "pending" } });
  });
  await page.goto(base + "/admin");
  await page.getByRole("button", { name: /^ai$/i }).click();
  const open = async (name) =>
    page
      .locator("article")
      .filter({ has: page.getByRole("heading", { name, exact: true }) })
      .getByRole("button", { name: /^(Connect|Manage)$/ })
      .click();
  await open("OpenRouter");
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("OpenRouter API key", { exact: true }).fill("fixture-only");
  await dialog.getByRole("button", { name: "Connect", exact: true }).click();
  await dialog.getByText("Connected · vendor/model-1").waitFor();
  await dialog.getByRole("button", { name: "Advanced settings" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Refresh model list", exact: true }).click();
  await dialog.getByText("650 models", { exact: false }).waitFor();
  await dialog.getByLabel("Search models").fill("model-649");
  await dialog.getByLabel("Connection test model").selectOption("vendor/model-649");
  await dialog.getByLabel("Reasoning effort", { exact: true }).selectOption("low");
  assert.equal(await dialog.locator('input[name="password"],input[name="base_url"]').count(), 0);
  await dialog.getByRole("button", { name: "Save connection and model" }).click();
  assert.equal(saves[0].config.model, "vendor/model-649");
  assert.equal(saves[0].config.reasoning_effort, "low");
  assert.equal(saves[0].config.input_microusd_per_million, 1000000);
  assert(!("current_password" in saves[0]));

  // Without their sign-in helpers, the subscription cards say so and offer nothing to open.
  for (const [name, mode] of [
    ["ChatGPT subscription", "codex"],
    ["Claude subscription", "claude_code"],
  ]) {
    const card = page
      .locator("article")
      .filter({ has: page.getByRole("heading", { name, exact: true }) });
    await card.getByText("Not available on this install", { exact: true }).waitFor();
    assert(await card.getByRole("button", { name: "Connect", exact: true }).isDisabled());
    assert.equal(await page.locator('main input[type="password"]').count(), 0);
    await card.screenshot({ path: "evidence/latest/review-" + mode + ".png" });
  }
  await page.getByRole("button", { name: /^house$/i }).click();
  await page.getByLabel("House name").waitFor();
  assert.equal(await page.locator('main input[type="password"]').count(), 0);
  await page.getByRole("button", { name: "Ask Nox" }).click();
  await page.getByRole("dialog", { name: "Nox" }).waitFor();
  await page
    .getByRole("dialog", { name: "Nox" })
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await page.getByRole("dialog", { name: "Nox" }).waitFor({ state: "hidden" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + "/control?tab=ai");
  await open("OpenRouter");
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/review-model-picker-phone.png", fullPage: true });
  assert.deepEqual(failures, []);
  fs.writeFileSync(
    "evidence/latest/provider-review-result.json",
    JSON.stringify(
      {
        passed: true,
        scope:
          "Real isolated authentication/settings; intercepted provider catalog/native replies/saves; no sign-in or inference",
        checks: [
          "650 model search",
          "OpenRouter key/model/pricing",
          "subscriptions unavailable without bridges, no API passwords",
          "house settings",
          "desktop assistant panel",
          "phone overflow",
          "no JS errors",
        ],
      },
      null,
      2,
    ),
  );
  await browser.close();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

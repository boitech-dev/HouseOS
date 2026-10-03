// Persisted setup recovery and completion UX; provider/feed fixtures, no model calls.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const base = "http://127.0.0.1:8893";
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let complete = false;
    const saved = "Votre sélection science est enregistrée. Est-ce que cela vous convient ?";
    await page.route("**/api/v1/house-settings", (route) =>
      route.fulfill({
        json: {
          name: "Maison test",
          preferences: { language: "fr", timezone: "Europe/Paris", motion: "subtle" },
        },
      }),
    );
    await page.route("**/api/v1/personal-space/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/config"))
        return route.fulfill({
          json: {
            configured: true,
            version: 1,
            setup_complete: complete,
            conversation_id: complete ? null : "persisted-space",
            config: { news_interests: ["science"], news_language: "fr" },
          },
        });
      return route.fulfill({
        json: { configured: true, day: "2026-09-21", sections: [], items: [] },
      });
    });
    await page.route("**/api/v1/assistant/status?purpose=personal_space", (route) =>
      route.fulfill({
        json: { actor_id: "fixture-actor", available: true, purpose: "personal_space" },
      }),
    );
    await page.route("**/api/v1/assistant/conversations/persisted-space*", (route) =>
      route.fulfill({
        json: {
          id: "persisted-space",
          messages: [{ id: "saved-reply", role: "assistant", content: saved, cards: [] }],
          next_offset: null,
        },
      }),
    );
    await page.route("**/api/v1/assistant/chat", (route) => {
      const body = route.request().postDataJSON();
      assert.equal(body.conversation_id, "persisted-space");
      assert.equal(body.purpose, "personal_space");
      assert.equal(body.message, "c'est bon");
      complete = true;
      return route.fulfill({
        json: {
          status: "completed",
          conversation_id: "persisted-space",
          reply: "Votre espace est prêt.",
        },
      });
    });
    await page.goto(base + "/space");
    await page.getByText(saved, { exact: true }).waitFor();
    assert.equal(await page.locator(".ask-composer").count(), 1); // Saved settings are not approval.
    await page.reload();
    await page.getByText(saved, { exact: true }).waitFor();
    assert.equal(await page.locator(".ask-composer").count(), 1);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({
      path: "evidence/latest/houseos-space-persist.png",
      fullPage: true,
    });
    await page.locator(".ask-composer textarea").fill("c'est bon");
    await page.locator(".ask-composer textarea").press("Enter");
    await page.locator(".ask-composer").waitFor({ state: "detached" });
    await page.reload();
    await page.getByRole("button", { name: "Personnaliser", exact: true }).waitFor();
    assert.equal(await page.locator(".ask-composer").count(), 0);
    await page.getByRole("button", { name: "Personnaliser", exact: true }).click();
    await page.locator(".ask-composer textarea").waitFor();
    assert.equal(await page.getByText(saved, { exact: true }).count(), 0); // Reopen is a fresh edit conversation.
    assert.deepEqual(errors, []);
    console.log(
      "PASS My Space persisted conversation reload, saved-but-unconfirmed chat, explicit completion/collapse, fresh edit chat, phone layout (fixtures; no model calls)",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

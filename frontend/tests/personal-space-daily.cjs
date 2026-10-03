const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const requests = [],
    sent = [],
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let configured = false;
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
    requests.push(path);
    if (path.endsWith("/config"))
      return route.fulfill({
        json: {
          configured,
          setup_complete: configured,
          conversation_id: null,
          version: configured ? 1 : 0,
          config: configured ? { news_interests: ["science"], news_language: "fr" } : null,
        },
      });
    if (path.endsWith("/today"))
      return route.fulfill({
        json: {
          configured: true,
          day: "2026-09-20",
          news_language: "fr",
          sections: [
            {
              kind: "news",
              sources: [{ key: "fr_science", status: "ready" }],
              items: [
                {
                  id: "fixture-1",
                  title: "Une découverte scientifique de test",
                  provider: "Le Monde",
                  url: "https://www.lemonde.fr/sciences/",
                  date: "2026-09-20",
                },
              ],
            },
          ],
        },
      });
    return route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/v1/assistant/status?purpose=personal_space", (route) =>
    route.fulfill({
      json: { actor_id: "fixture-actor", available: true, purpose: "personal_space" },
    }),
  );
  await page.route("**/api/v1/assistant/conversations", (route) =>
    route.fulfill({ json: { id: "space-fixture" } }),
  );
  await page.route("**/api/v1/assistant/chat", (route) => {
    sent.push(route.request().postDataJSON());
    return route.fulfill({
      json: {
        status: "completed",
        conversation_id: "space-fixture",
        reply: "Quels sujets souhaitez-vous ?",
      },
    });
  });
  await page.route("**/api/v1/assistant/conversations/space-fixture*", (route) =>
    route.fulfill({
      json: {
        id: "space-fixture",
        messages: [
          { id: "reply", role: "assistant", content: "Quels sujets souhaitez-vous ?", cards: [] },
        ],
        next_offset: null,
      },
    }),
  );
  await page.goto(base + "/space");
  await page.getByRole("button", { name: /^Un peu de lecture/ }).waitFor();
  await page.getByRole("button", { name: /^Un peu de lecture/ }).click();
  await page.waitForFunction(() =>
    document.querySelector(".ask-composer textarea")?.value.includes("5 titres"),
  );
  assert(!requests.some((path) => /\/(today|news|anime|favorites)$/.test(path)));
  await page.locator(".ask-composer [data-variant=primary]").click();
  await page.getByText("Quels sujets souhaitez-vous ?", { exact: true }).waitFor();
  assert.equal(sent[0].purpose, "personal_space");
  assert.equal(new URL(page.url()).pathname, "/space");
  assert.equal(await page.locator(".filters select").count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/myspace-setup-fr-phone.png", fullPage: true });
  configured = true;
  await page.reload();
  await page
    .getByRole("link", { name: "Une découverte scientifique de test", exact: true })
    .waitFor();
  assert.equal(await page.locator(".ask-composer").count(), 0);
  await page.getByRole("button", { name: "Personnaliser", exact: true }).click();
  await page.locator(".ask-composer textarea").waitFor();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/myspace-daily-fr-phone.png", fullPage: true });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS Myspace blank firstvisit/no feedcalls/French setup/dedicated inline chat/daily snapshot/discreet customization/phone layout (provider fixtures, no model calls)",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

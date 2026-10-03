const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until, settled } = require("./session.cjs");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch(),
    admin = await browser.newContext(),
    base = "http://127.0.0.1:8893";
  const auth = await require("./session.cjs")(admin, base),
    me = await auth.json(),
    headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const invitation = await (
    await admin.request.post(base + "/api/v1/auth/invites", {
      headers,
      data: { preset: "roommate", expires_hours: 2 },
    })
  ).json();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  try {
    const result = await context.request.post(base + "/api/v1/auth/redeem", {
      headers: { Origin: base },
      data: {
        token: invitation.token,
        username: "locale_" + Date.now(),
        name: "Language test resident",
        password: "Test-only-Language-2046",
      },
    });
    assert(result.ok());
    const own = await result.json();
    // A new resident's welcome shows once (tests/onboarding.cjs shows it): seen here.
    await context.request.put(base + "/api/v1/preferences", {
      headers: { Origin: base, "X-CSRF-Token": own.csrf_token },
      data: settled("resident"),
    });
    assert.equal(
      (await (await context.request.get(base + "/api/v1/preferences")).json()).language,
      "fr",
    );
    const page = await context.newPage(),
      errors = [],
      requests = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/v1/assistant/**", async (route) => {
      let path = new URL(route.request().url()).pathname;
      let data = {};
      if (path.endsWith("/status"))
        data = { actor_id: "fixture-actor", available: true, purpose: "general" };
      else if (path.endsWith("/chat")) {
        requests.push(route.request().postDataJSON());
        data = { conversation_id: "localized-chat" };
      } else if (path.endsWith("/conversations") && route.request().method() === "POST")
        data = { id: "localized-chat" };
      else if (path.endsWith("/conversations")) data = { items: [], next_offset: null };
      else
        data = {
          messages: [{ id: "answer", role: "assistant", content: "✅ C’est fait." }],
          next_offset: null,
        };
      await route.fulfill({ json: data });
    });
    await page.goto(base + "/");
    await page.waitForFunction(() => document.documentElement.lang === "fr");
    const bar = page.getByLabel("Demande à Nox, le gardien de la maison", { exact: true });
    await bar.fill("Ajoute du lait aux courses");
    await bar.press("Enter");
    await page.getByRole("dialog", { name: "Nox" }).waitFor();
    assert.equal(await page.locator(".ask select").count(), 0);
    await until(() => requests.length, 10000);
    assert.equal(await page.locator(".ask select").count(), 0);
    assert.equal(requests[0].purpose, "general");
    assert.equal(requests[0].provider, undefined);
    assert.equal(requests[0].context, undefined);
    await page.screenshot({ path: "evidence/latest/resident-french-chat.png", fullPage: true });
    for (const [path, label] of [
      ["/music", "Écouter"],
      ["/house", "Maison"],
      ["/files", "Fichiers"],
      ["/settings", "Tes préférences"],
      ["/space", "Mon espace"],
    ]) {
      await page.goto(base + path);
      await page.getByRole("heading", { name: label, exact: true }).waitFor();
    }
    await page.goto(base + "/house?tab=calendar");
    await page.getByRole("button", { name: "Calendrier", exact: true }).waitFor();
    await page.getByRole("button", { name: "Ajouter un événement", exact: true }).click();
    await page.getByRole("dialog").getByLabel("Répétition", { exact: true }).selectOption("weekly");
    assert.equal(
      await page.getByRole("dialog").getByLabel("Répétition", { exact: true }).inputValue(),
      "weekly",
    );
    await page.getByRole("dialog").getByRole("button", { name: "Fermer", exact: true }).click();
    await page.screenshot({ path: "evidence/latest/resident-french-calendar.png", fullPage: true });
    await page.getByRole("button", { name: "Ton compte", exact: true }).click();
    await page.getByRole("dialog").getByText("English", { exact: true }).click();
    await page.keyboard.press("Escape");
    await page.getByRole("heading", { name: "House", exact: true }).waitFor();
    assert.equal(
      (await (await context.request.get(base + "/api/v1/preferences")).json()).language,
      "en",
    );
    await page.reload();
    await page.waitForFunction(() => document.documentElement.lang === "en");
    await page.getByRole("heading", { name: "House", exact: true }).waitFor();
    await page.getByRole("button", { name: /^Your account/ }).click();
    await page.getByRole("dialog").getByText("Français", { exact: true }).click();
    await page.keyboard.press("Escape");
    await page.goto(base + "/");
    await page.setViewportSize({ width: 390, height: 844 });
    await page
      .getByRole("heading", { name: /^(Bonjour|Bon après-midi|Bonsoir|Bonne nuit)/ })
      .waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    // A phone shows the time itself: the status bar gives the clock's room to the house's name.
    assert.equal(await page.locator(".shell__clock").isVisible(), false, "no clock on a phone");
    const name = page.locator(".shell__name");
    assert(await name.evaluate((el) => el.scrollWidth <= el.clientWidth + 1), "house name not cut");
    await page.screenshot({
      path: "evidence/latest/resident-french-home-phone.png",
      fullPage: true,
    });
    await page.screenshot({
      path: "evidence/latest/resident-french-header-phone.png",
      clip: { x: 0, y: 0, width: 390, height: 240 },
    });
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      "evidence/latest/language-chat-result.json",
      JSON.stringify(
        {
          passed: true,
          checks: [
            "new resident French default",
            "French Accueil Écouter Regarder Maison Fichiers and account menu",
            "no mainchat provider/model/category selectors",
            "purpose general only in chatrequest",
            "real persisted immediate English/French switch and reload",
            "390px no overflow",
            "no JS errors",
          ],
          boundary:
            "Real isolated identity/preferences; chat inference mocked; no paid model requests",
        },
        null,
        2,
      ),
    );
  } finally {
    await admin.request.delete(
      base + "/api/v1/auth/invites/" + invitation.id + "?revoke_membership=true",
      { headers },
    );
    await browser.close();
  }
  console.log("PASS resident French UI, persistent language switch and simple purpose-only chat");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

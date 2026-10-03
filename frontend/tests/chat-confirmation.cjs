const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let confirmed = 0,
    continued = 0;
  const confirmationId = "11111111-1111-4111-8111-111111111111",
    conversationId = "22222222-2222-4222-8222-222222222222";
  await page.route("**/api/v1/assistant/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    let data = {};
    if (p.includes("/continue-tv/")) {
      continued++;
      await new Promise((resolve) => setTimeout(resolve, 500));
      data = { status: "completed" };
    } else if (p.endsWith("/status")) data = { actor_id: "fixture", available: true };
    else if (p.endsWith("/conversations"))
      data = { items: [{ id: "confirmation-test", title: "Movie request" }] };
    else
      data = {
        messages: [
          {
            id: "answer",
            role: "assistant",
            content: "Turn off the Chromecast?",
            cards: [
              {
                domain: "cinema",
                kind: "result",
                label: "TV control",
                status: "needs_confirmation",
                confirmation_id: confirmationId,
                confirmation_path: "/cinema/device-confirmations/" + confirmationId,
                continuation_path:
                  "/assistant/conversations/" + conversationId + "/continue-tv/" + confirmationId,
                detail: "power_off",
                preview: {
                  action: "power_off",
                  destination: "Chromecast",
                  value: null,
                  may_interrupt: true,
                  current_state: {
                    state: "on",
                    apps: Array.from({ length: 100 }, (_, i) => "Private app " + i),
                    internal_id: "hidden-id",
                  },
                },
              },
            ],
          },
        ],
      };
    await route.fulfill({ json: data });
  });
  await page.route("**/api/v1/cinema/device-confirmations/" + confirmationId, async (route) => {
    assert.equal(route.request().method(), "POST");
    confirmed++;
    await route.fulfill({
      json: { state: "command_sent", next_step: "Check the device before continuing." },
    });
  });
  await page.goto(base + "/assistant?conversation=confirmation-test");
  const card = page.locator(".ask-card");
  await card.getByRole("button", { name: "Confirm", exact: true }).waitFor();
  assert.equal(await card.getByText("power_off", { exact: true }).count(), 0);
  assert.equal(await card.getByText(/Private app|hidden-id|Current State/).count(), 0);
  assert((await card.boundingBox()).height < 320);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await card.getByRole("button", { name: "Confirm", exact: true }).click();
  await card
    .getByText("The command was sent. Completion has not been verified yet.", { exact: true })
    .waitFor();
  await card.getByText("Check the device before continuing.", { exact: true }).waitFor();
  assert.equal(confirmed, 1);
  assert.equal(await card.getByRole("button", { name: "Confirm", exact: true }).count(), 0);
  assert.equal(continued, 0);
  await page.screenshot({ path: "evidence/latest/chat-confirmation-phone.png", fullPage: true });
  await page.unroute("**/api/v1/cinema/device-confirmations/" + confirmationId);
  await page.route("**/api/v1/cinema/device-confirmations/" + confirmationId, async (route) => {
    confirmed++;
    await route.fulfill({ json: { state: "observed" } });
  });
  await page.reload();
  await card.getByRole("button", { name: "Confirm", exact: true }).click();
  await card.getByText("Continuing movie selection…", { exact: true }).waitFor();
  await card.getByText("This action is complete.", { exact: true }).waitFor();
  assert.equal(confirmed, 2);
  assert.equal(continued, 1);
  await browser.close();
  console.log(
    "PASS compact scoped confirmation, no internal inventory, single submission, truthful pending recap and verified-only continuation",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

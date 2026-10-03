// A configuration request in the everyday chat gets a card whose button opens Nox in setup mode
// (switch_context never enters it) and sends the admin's own words there.
const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  await page.route("**/api/v1/assistant/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    let data;
    if (p.endsWith("/chat")) data = { status: "completed", reply: "ok", cards: [] };
    else if (p.endsWith("/status")) data = { actor_id: "fixture", available: true };
    else if (p.endsWith("/conversations")) data = { items: [{ id: "setup-test", title: "Villa" }] };
    else
      data = {
        messages: [
          {
            id: "answer",
            role: "assistant",
            content: "Tap the button to open setup mode.",
            cards: [
              {
                kind: "result",
                label: "House setup",
                domain: "setup",
                status: "completed",
                href: "/assistant?mode=setup",
                ask: "Rename the house to Villa",
              },
            ],
          },
        ],
      };
    await route.fulfill({ json: data });
  });
  try {
    await page.goto(base + "/assistant?conversation=setup-test");
    const sent = page.waitForRequest((r) => r.url().endsWith("/assistant/chat"));
    await page.locator(".ask-card").getByRole("link", { name: "Open setup mode" }).click();
    const body = (await sent).postDataJSON();
    assert.equal(body.purpose, "setup");
    assert.equal(body.message, "Rename the house to Villa");
    assert.equal(body.conversation_id, undefined); // its own conversation, not the page's
  } finally {
    await browser.close();
  }
  console.log("PASS the setup-mode button opens Nox in setup mode with the admin's own words");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

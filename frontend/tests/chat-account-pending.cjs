const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let finished = false,
    sent = false,
    actorId = "fixture-actor";
  await page.route("**/api/v1/assistant/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    let data = {};
    if (p.endsWith("/status")) data = { actor_id: actorId, available: true };
    else if (p.endsWith("/conversations") && route.request().method() === "POST")
      data = { id: "progress-test" };
    else if (p.endsWith("/conversations"))
      data = {
        items: [{ id: "progress-test", title: "https://example.invalid/" + "longpath".repeat(50) }],
        next_offset: null,
      };
    else if (p.endsWith("/chat")) {
      sent = true;
      await new Promise((r) => setTimeout(r, 2200));
      finished = true;
      data = { conversation_id: "progress-test" };
    } else
      data = {
        messages: finished
          ? [
              { id: "user", role: "user", content: "Play a classic song." },
              { id: "answer", role: "assistant", content: "Queued the song." },
            ]
          : [],
        pending: sent && !finished,
        progress: "music_search",
      };
    await route.fulfill({ json: data });
  });
  await page.goto(base + "/assistant");
  await page.getByLabel("Message your assistant", { exact: true }).fill("Play a classic song.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.waitForURL("**/assistant?conversation=progress-test");
  assert(!finished);
  assert.equal(await page.getByLabel("Message your assistant", { exact: true }).inputValue(), "");
  await page.getByText("Play a classic song.", { exact: true }).waitFor();
  assert(await page.locator(".ask-progress").isVisible());
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  actorId = "different-actor";
  await page.evaluate(() => window.dispatchEvent(new Event("houseos:change")));
  await page.waitForFunction(() => !document.querySelector(".ask-message[data-role=user]"));
  assert.equal(await page.getByText("Play a classic song.", { exact: true }).count(), 0);
  await browser.close();
  console.log("PASS optimistic private message disappears when authenticated actor changes");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

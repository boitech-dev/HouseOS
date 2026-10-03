const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  await page.route("**/api/v1/cinema/current", (r) =>
    r.fulfill({
      json: {
        current: {
          id: "fixture",
          title: "A long movie title",
          version: 1,
          state: "playing_observed",
          checkpoint: { position: 10 },
          duration: 3600,
          can_seek: true,
          volume_supported: true,
          volume: 20,
        },
      },
    }),
  );
  await page.route("**/api/v1/music", (r) =>
    r.fulfill({
      json: {
        version: 1,
        current_id: "song",
        desired: "playing",
        items: [{ id: "song", title: "Fixture song", status: "playing", duration: 180 }],
        observation: {
          status: "observed",
          item_id: "song",
          idle: false,
          paused: false,
          position: 5,
        },
      },
    }),
  );
  await page.route("**/api/v1/assistant/**", (r) => {
    const p = new URL(r.request().url()).pathname;
    return r.fulfill({
      json: p.endsWith("/status")
        ? { available: true, actor_id: "fixture" }
        : p.endsWith("/conversations")
          ? {
              items: Array.from({ length: 8 }, (_, i) => ({
                id: "c" + i,
                title: "A long conversation title " + i,
              })),
            }
          : p.includes("/c2")
            ? { messages: [{ id: "one", role: "user", content: "Help me set up the house" }] }
            : {
                messages: Array.from({ length: 30 }, (_, i) => ({
                  id: "m" + i,
                  role: i % 2 ? "assistant" : "user",
                  content: "A long message to test internal scrolling. ".repeat(8),
                })),
              },
    });
  });
  await page.goto(base + "/assistant?conversation=c1");
  await page.locator(".ask-message").first().waitFor();
  async function check() {
    const composer = await page.locator(".ask-composer textarea").boundingBox();
    const dock = await page.locator(".shell__dock").boundingBox();
    assert(
      composer.y >= 0 && composer.y + composer.height <= (dock?.y ?? page.viewportSize().height),
      JSON.stringify({ composer, dock }),
    );
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert(await page.locator(".ask-messages").evaluate((e) => e.scrollHeight > e.clientHeight));
  }
  await check();
  await page.screenshot({ path: "evidence/latest/chat-viewport-phone.png" });
  await page.setViewportSize({ width: 390, height: 500 });
  await page.locator(".ask-composer textarea").focus();
  await check();
  await page.screenshot({ path: "evidence/latest/chat-viewport-small.png" });
  await page.setViewportSize({ width: 1280, height: 800 });
  // Desktop, one short message, music and a film playing: the bubble keeps its size and nothing
  // under the text box hides behind the player bars.
  await page.goto(base + "/assistant?conversation=c2");
  await page.locator(".ask-message").first().waitFor();
  await page.locator(".shell__now").waitFor();
  assert((await page.locator(".ask-message").first().boundingBox()).height < 120);
  const fine = await page.locator(".ask__fine").boundingBox();
  const bars = await page.locator(".shell__now").boundingBox();
  assert(fine.y + fine.height <= bars.y + 1, JSON.stringify({ fine, bars }));
  await page.screenshot({ path: "evidence/latest/chat-viewport-desktop.png" });
  await page.goto(base + "/house");
  await page.getByRole("button", { name: "Ask Nox" }).click();
  await page.getByRole("dialog", { name: "Nox" }).waitFor();
  const box = await page
    .getByRole("dialog", { name: "Nox" })
    .locator(".ask-composer textarea")
    .boundingBox();
  assert(box.y + box.height <= 800);
  await browser.close();
  console.log("PASS phone long chat composer, shortened viewport, and assistant drawer");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

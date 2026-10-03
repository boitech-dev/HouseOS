const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/assistant/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    let data = path.endsWith("/status")
      ? { available: true, actor_id: "test" }
      : path.endsWith("/conversations")
        ? { items: [], next_offset: null }
        : {
            messages: [
              {
                id: "answer",
                role: "assistant",
                content: "Queued 3 tracks. Playback is not yet verified.",
                cards: [
                  {
                    kind: "result",
                    label: "Added to music queue",
                    domain: "music",
                    status: "accepted",
                    count: 3,
                    items: ["First classic", "Second classic", "Third classic"].map((title) => ({
                      title,
                    })),
                    href: "https://untrusted.invalid/ignored",
                  },
                  {
                    kind: "result",
                    label: "House record created",
                    domain: "house",
                    status: "completed",
                    items: [{ title: "Milk", detail: "2 cartons" }],
                    href: "/house",
                  },
                ],
              },
            ],
          };
    return route.fulfill({ json: data });
  });
  await page.goto(base + "/assistant?conversation=recap-fixture");
  await page.getByText("Third classic", { exact: true }).waitFor();
  assert.equal(await page.getByText(/review action/).count(), 0);
  assert.equal(await page.getByRole("link", { name: "Open Music" }).getAttribute("href"), "/music");
  assert.equal(await page.getByRole("link", { name: "Open House" }).getAttribute("href"), "/house");
  assert(await page.getByText("3 tracks", { exact: true }).isVisible());
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/action-recaps-phone.png", fullPage: true });
  await page.getByRole("link", { name: "Open House" }).click();
  assert.equal(new URL(page.url()).pathname, "/house");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS concrete3-track/task result cards, safe domain links, nofalseapproval and390px layout",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

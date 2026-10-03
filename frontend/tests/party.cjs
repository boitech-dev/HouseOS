// Party mode: full-screen queue without navigation, a single-use join code per guest,
// a fresh code once used, and a way back. Invites and music are intercepted.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 1180, height: 820 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    created = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let redeemed = false;
  await page.route(/\/api\/v1\/auth\/invites$/, async (route) => {
    if (route.request().method() === "POST") {
      created.push(route.request().postDataJSON());
      return route.fulfill({
        json: { id: "inv" + created.length, path: "/join#fixture-token-" + created.length },
      });
    }
    return route.fulfill({ json: [{ id: "inv" + created.length, redeemed }] });
  });
  await page.route(/\/api\/v1\/music(\?|$)/, (route) =>
    route.fulfill({
      json: {
        version: 2,
        fair: true,
        current_id: null,
        items: [
          {
            id: "a",
            title: "Party fixture song",
            owner_id: "x",
            requester: { name: "Guest" },
            status: "ready",
            round: 1,
          },
        ],
        observation: {},
      },
    }),
  );
  await page.goto(base + "/listen");
  await page.getByRole("button", { name: "More music", exact: true }).click();
  await page.getByRole("menuitem", { name: "Party mode" }).click();
  await page.waitForURL("**/party");
  await page.getByRole("heading", { name: "Party" }).waitFor();
  assert.equal(await page.locator(".shell__rail").isVisible(), false);
  await page.getByText("Party fixture song").waitFor();
  // The join code opens in a sheet with the first code already made.
  await page.getByRole("button", { name: "Show a join code" }).click();
  const join = page.getByRole("dialog", { name: "Let guests add songs" });
  await join.getByRole("img", { name: "Join code for one guest" }).waitFor();
  assert.equal(created.length, 1);
  assert.deepEqual(created[0], { preset: "party", expires_hours: 2, membership_hours: 4 });
  await page.screenshot({ path: "evidence/latest/party-tablet.png" });
  redeemed = true;
  await page.getByText("Welcome in!").waitFor({ timeout: 10000 });
  await page.getByRole("button", { name: "Code for the next guest" }).click();
  redeemed = false;
  await page.getByRole("img", { name: "Join code for one guest" }).waitFor();
  assert.equal(created.length, 2);
  // One screen, no scrolling, the code in view: a 16:9 TV and a 9:16 tablet on the shelf.
  for (const [width, height] of [
    [1920, 1080],
    [1080, 1920],
  ]) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(150);
    const code = await page.getByRole("img", { name: "Join code for one guest" }).boundingBox();
    assert(code.y >= 0 && code.y + code.height <= height, "join code out of view at " + width);
    assert(
      await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1),
      "party mode scrolls at " + width + "x" + height,
    );
  }
  await join.getByRole("button", { name: "Close" }).click();
  // A phone: the queue is on screen (the page scrolls), the volume waits behind a button.
  await page.setViewportSize({ width: 360, height: 780 });
  await page.waitForTimeout(150);
  const queue = await page.locator(".listen-queue").boundingBox();
  assert(queue.height > 100, "party queue has no room on a phone: " + queue.height);
  await page.getByRole("button", { name: "Volume", exact: true }).click();
  await page.getByRole("dialog", { name: "Volume" }).getByRole("button", { name: "Close" }).click();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.getByRole("button", { name: "Leave party mode" }).click();
  await page.waitForURL("**/listen");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS party kiosk, single-use join codes renewed per guest, leave");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});

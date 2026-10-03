// Nox's proposed change: the card leads with the route's own summary and shows the exact
// request in full, wrapped (never cut); Confirm takes it once and this
// browser sends it with its own session and CSRF token (the real API), then reports the outcome.
const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  const me = await (await require("./session.cjs")(context, base)).json();
  const headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const settings = async () =>
    (await context.request.get(base + "/api/v1/admin/house-settings")).json();
  const before = (await settings()).quiet_end;
  const wanted = before === "07:30" ? "07:45" : "07:30";
  const page = await context.newPage();
  const id = "33333333-3333-4333-8333-333333333333";
  const long = "welcome_message: " + "a long value with no end in sight ".repeat(8) + "END";
  let body = { quiet_end: wanted },
    taken = 0;
  const outcomes = [];
  await page.route("**/api/v1/assistant/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    let data;
    if (p.endsWith("/take")) {
      taken++;
      data = { method: "PUT", path: "/admin/house-settings", body };
    } else if (p.endsWith("/outcome")) {
      outcomes.push(route.request().postDataJSON());
      data = { status: "completed" };
    } else if (p.endsWith("/status")) data = { actor_id: "fixture", available: true };
    else if (p.endsWith("/conversations"))
      data = { items: [{ id: "proposal-test", title: "Quiet" }] };
    else
      data = {
        messages: [
          {
            id: "answer",
            role: "assistant",
            content: "Please confirm the action below.",
            cards: [
              {
                domain: "assistant",
                label: "Change a setting",
                status: "needs_confirmation",
                detail: "Quiet hours end at " + wanted,
                confirmation_id: id,
                confirmation_path: "/assistant/proposals/" + id,
                preview: {
                  route: "Save Settings",
                  request: "PUT /admin/house-settings",
                  lines: ["quiet_end: " + wanted, long],
                  unchanged: 0,
                },
              },
            ],
          },
        ],
      };
    await route.fulfill({ json: data });
  });
  try {
    await page.goto(base + "/assistant?conversation=proposal-test");
    const card = page.locator(".ask-card");
    await card.getByText("Save Settings", { exact: true }).waitFor();
    await card.getByText("Quiet hours end at " + wanted, { exact: true }).waitFor();
    const request = card.locator(".ask-card__request");
    assert.equal(
      await request.textContent(),
      ["PUT /admin/house-settings", "quiet_end: " + wanted, long].join("\n"),
    );
    // Wrapped inside the card: every word is on screen, nothing scrolls sideways.
    assert(await request.evaluate((e) => e.scrollWidth <= e.clientWidth));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await card.getByRole("button", { name: "Confirm this exact action" }).click();
    await card.getByText("This action is complete.", { exact: true }).waitFor();
    assert.equal((await settings()).quiet_end, wanted); // the real API, this browser's session
    assert.deepEqual(outcomes, [{ ok: true, status: 200 }]);
    assert.equal(await card.getByRole("button", { name: "Confirm this exact action" }).count(), 0);
    await page.screenshot({ path: "evidence/latest/chat-proposal-phone.png", fullPage: true });
    // A request the API refuses: its own words on the card, reported once, never resent.
    body = { motion: "wild" };
    await page.reload();
    await card.getByRole("button", { name: "Confirm this exact action" }).click();
    await card.getByText("This action could not be completed.", { exact: true }).waitFor();
    assert.equal(outcomes.length, 2);
    assert.equal(outcomes[1].ok, false);
    assert.equal(outcomes[1].status, 422);
    assert.equal(taken, 2);
    assert.equal(await card.getByRole("button", { name: "Confirm this exact action" }).count(), 0);
  } finally {
    await context.request.put(base + "/api/v1/admin/house-settings", {
      headers,
      data: { quiet_end: before },
    });
    await browser.close();
  }
  console.log("PASS a proposal card sends its exact request from this browser once and reports it");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
